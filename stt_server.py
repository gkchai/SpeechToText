# author: kcgarikipati@gmail.com

"""STT server implementation in GRPC"""

from proto import stt_pb2

import argparse
import asr.goog as google
import asr.hound as hound
import asr.ibm as ibm
import itertools
import json
import os
import Queue
import random
import sys
import thread
import threading
import time
import webrtcvad
import collections

import argparse
import sys
import logging

FORMAT = '%(levelname)s: %(asctime)s: %(message)s'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('SpeechToText')


_SUPPORTED_ASRS = ["google", "hound", "ibm"]
_LOG_PATH = 'log/'
_LOG_FILE = 'log/log.json'

class IterableQueue():
	''' An iterator over queue data structure that
		stops when the predicate is false
	'''
	def __init__(self, Q, num_asrs):
		self.Q = Q
		self.endcount = 0
		self.num_asrs = num_asrs
		self.predicate = True

	def __iter__(self):
		return self

	def _check(self, x):
		if x['is_final'] == True:
			self.endcount += 1

		if self.endcount == self.num_asrs:
			self.predicate = False

	def next(self):
		if self.predicate:
			item = self.Q.get()
			self._check(item)
			return item
		else:
			raise StopIteration

def LogStream(chunkIterator, token):
	try:
		with open('%s/%s.raw'%(_LOG_PATH, token), 'wb') as f:
			for chunk in chunkIterator:
				f.write(chunk)
	except:
		logger.error('cannot write speech file')


class Listener(stt_pb2.BetaListenerServicer):

	def __init__(self):
		""" put initializaiton code e.g. db access """

		self.db_type = None
		self.db = {}

		# see if log/ can be used as a database
		try:
			f = open(_LOG_FILE)
			try:
				self.db = json.load(f)
				self.db_type = 'log'
				logger.info('Selecting log database')
			except ValueError as e:
				logger.error("'" + _LOG_FILE + "' is not a valid JSON file.")
			finally:
				f.close()

		except EnvironmentError as e:
			logger.error('Cannot establish database connection')

		logger.info('STT server initialized')

	def _write_to_database(self, record):

		if self.db_type == 'log':
			# add record to the dictionary
			self.db.update({record['token']: record})
			with open(_LOG_FILE, 'w') as f:
				json.dump(self.db, f,  sort_keys=True, indent=4)
		else:
			logger.error("Cannot write to DB")


	def _splitStream(self, request_iterator, listQueues, config):
		''' Place the items from the request_iterator into each
			queue in the list of queues. When using VAD (continuous
			= True), the end-of-speech (EOS) can occur when the
			stream ends or inactivity is detected, whichever occurs
			first.
		'''
		continuous = config['continuous']

		if continuous:
			frame_len = 10 #10ms or 20ms or 30ms
			frame_bytes = 32*frame_len #16KHz sampling @ 2Bytes/sample

			# number of frames
			inactivity_frames = config['inactivity']//frame_len
			vad = webrtcvad.Vad()
			vad.set_mode(3)
			ring_buffer = collections.deque(maxlen=inactivity_frames)
			triggered = False
			end_of_speech = False
			prev_content = b''

		counter = 0

		for chunk in request_iterator:

			counter += 1
			# we have to use custom VAD otherwise
			# we let the ASRs use their VAD for non-continuous
			if continuous:

				# break chunk into 10ms frames
				curr_content = prev_content + chunk.content
				n = len(curr_content)
				offset = 0

				while n >= frame_bytes:
					# webrtc takes chunks of only 10ms/20ms/30ms. We use 16KHz@10ms.
					is_speech = vad.is_speech(curr_content[offset:offset+frame_bytes], 16000)
					ring_buffer.append(is_speech)
					n = n - frame_bytes
					offset += frame_bytes

				if n > 0:
					prev_content = curr_content[offset:]
				else:
					prev_content = b''

				# number of voiced and unvoiced segments
				num_voiced = len([f for f in ring_buffer if f is True])
				num_unvoiced = len(ring_buffer) - num_voiced

				# logger.info("%d, %d", num_voiced, num_unvoiced)

				# TODO: if not triggered for a while then go to end-of-speech
				# in any case
				if not triggered:
					if num_voiced > 0.5*ring_buffer.maxlen:
						triggered = True
						logger.info('Triggered start of speech')
				else:
					if num_unvoiced > 0.9*ring_buffer.maxlen:
						end_of_speech = True

				if end_of_speech:
					logger.info('Got end of speech from VAD')
					for Q in listQueues:
						# logger.info('adding end of speech')
						Q.put('EOS')
					continuous = False


			for Q in listQueues:
				Q.put(chunk.content)

		for Q in listQueues:
			# logger.info('adding end of speech')
			Q.put('EOS')

	def _mergeStream(self, asr_response_iterator, responseQueue, asr):
		''' Place the item from the asr_response_iterator of asr into a common
			queue called responseQueue
		'''

		for asr_response in asr_response_iterator:
			str_response = asr_response['transcript']
			is_final = asr_response['is_final']
			toClient_json = {'asr': asr, 'transcript': str_response,
								'is_final': is_final}
			responseQueue.put(toClient_json)
		# logger.info('merge thread complete')
		return

	def DoConfig(self, request, context):

		if set(request.asrs) > set(_SUPPORTED_ASRS):
			raise Exception("STT not supported")

		if request.encoding != 'LINEAR16':
			raise Exception("encoding not supported")

		if request.sampling_rate != 16000:
			raise Exception("Rate not supported")

		logger.info('STT configuration done')
		return stt_pb2.ConfigResult(status=True,
			config=request)

	def DoSpeechToText(self, request_iterator, context):
		'''Main rpc function for converting speech to text
		   Takes in a stream of stt_pb2 SpeechChunk messages
		   and returns a stream of stt_pb2 Transcript messages
		'''

		# first item in iterator has the config and token
		first_item = next(request_iterator)

		try:
			token = first_item.token
			stt_config = first_item.config
		except:
			raise Exception("First call must pass configuration and token")

		config = {}
		config['asrs'] = stt_config.asrs
		config['encoding'] = stt_config.encoding
		config['sampling_rate'] = stt_config.sampling_rate
		config['language'] = stt_config.language
		config['max_alternatives'] = stt_config.max_alternatives
		config['profanity_filter'] = stt_config.profanity_filter
		config['interim_results'] = stt_config.interim_results
		config['continuous'] = stt_config.continuous
		config['chunksize'] = stt_config.chunksize
		config['inactivity'] = stt_config.inactivity

		record = {}
		record['token'] = token
		record['results'] = []

		all_queues = []
		for _ in range(len(config['asrs'])):
			all_queues.append(Queue.Queue())
		# additional queue for log stream
		all_queues.append(Queue.Queue())

		logger.debug('%s: Running speech to text', token)

		thread_ids = []

		t = threading.Thread(target=self._splitStream, args=(request_iterator, all_queues, config))
		t.start()
		thread_ids.append(t)
		t = threading.Thread(target=LogStream, args=(iter(all_queues[-1].get, 'EOS'), token))
		t.start()
		thread_ids.append(t)

		responseQueue = Queue.Queue()
		for ix, asr in enumerate(config['asrs']):
			if asr == 'google':
				gw = google.worker(token)
				t = threading.Thread(target=self._mergeStream, args=
					(gw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
				t.start()
				thread_ids.append(t)

			if asr == 'ibm':
				ibmw = ibm.worker(token)
				t = threading.Thread(target=self._mergeStream, args=
					(ibmw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
				t.start()
				thread_ids.append(t)

			if asr == 'hound':
				houndw = hound.worker(token)
				t = threading.Thread(target=self._mergeStream, args=
					(houndw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
				t.start()
				thread_ids.append(t)

		# keep sending transcript to client until *all* ASRs are DONE
		for item_json in IterableQueue(responseQueue, len(config['asrs'])):

			# logger.info(item_json)
			if item_json['is_final']:

				each_record = {}
				each_record['asr'] = item_json['asr']
				each_record['transcript'] = item_json['transcript']
				each_record['is_final'] = item_json['is_final']
				each_record['confidence'] = 1.0
				record['results'].append(each_record)

				# WE DONOT JOIN
				# for t in thread_ids:
				# 	t.join()

			#TODO: write each record to DB separately because the client
			#may break the call after just one ASR finishes
			yield stt_pb2.TranscriptChunk(
				asr = item_json['asr'],
				transcript = item_json['transcript'],
				is_final = item_json['is_final'],
				confidence = 1.0,
				)

		try:
			self._write_to_database(record)
		except:
			e = sys.exc_info()[0]
			logger.error('%s: Database error: %s', token, e)


def serve(port):
	server = stt_pb2.beta_create_Listener_server(Listener())
	server.add_insecure_port('[::]:%d'%port)
	server.start()
	try:
		while True:
			time.sleep(1000)
	except KeyboardInterrupt:
		server.stop(0)

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='SpeechToText service')
	parser.add_argument('-p', action='store', dest='port', type=int, default=9080,
		help='port')
	args = parser.parse_args()
	serve(args.port)

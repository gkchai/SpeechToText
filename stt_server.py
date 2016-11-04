#!/usr/bin/env python
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
import pymongo
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

	def __iter__(self):
		return self

	def _predicate(self, x):
		if x == 'DONE':
			self.endcount += 1
			if self.endcount == self.num_asrs:
				return False
			else:
				return True
		else:
			return True

	def next(self):
		item = self.Q.get()
		if self._predicate(item):
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

		# see if we can connect to mongoDB
		try:
			client = pymongo.MongoClient(serverSelectionTimeoutMS=2)
			client.server_info()
			self.db = client.SplitSys
			self.db_type = 'mongodb'
			logger.info('Selecting mongoDB database')
		except pymongo.errors.ServerSelectionTimeoutError as err:
			logger.error(err)

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

		if self.db_type == 'mongodb':
			# insert entire dictionary into mongoDB
			self.db.stt.insert(record)

		elif self.db_type == 'log':
			# add record to the dictionary
			self.db.update({record['token']: record})
			with open(_LOG_FILE, 'w') as f:
				json.dump(self.db, f,  sort_keys=True, indent=4)
		else:
			logger.error("Cannot write to DB")


	def _splitStream(self, request_iterator, listQueues, config):
		''' Place the items from the request_iterator into each
			queue in the list of queues
		'''
		frame_len = 10 #10ms or 20ms or 30ms
		frame_bytes = 32*frame_len #16KHz sampling @ 2Bytes/sample

		# number of frames
		inactivity_frames = config['inactivity']//frame_len

		vad = webrtcvad.Vad()
		vad.set_mode(3)
		ring_buffer = collections.deque(maxlen=inactivity_frames)
		continuous = config['continuous']
		triggered = False
		end_of_speech = False

		prev_content = b''
		for chunk in request_iterator:

			# we have to use custom VAD otherwise
			# we let the ASRs use their VAD for non-continuous
			if continuous:

				# break chunk into 10ms frames
				curr_content = prev_content + chunk.content
				n = len(curr_content)
				offset = 0

				while n >= frame_bytes:

					is_speech = vad.is_speech(curr_content[offset:offset+frame_bytes], 16000)
					ring_buffer.append(is_speech)
					n = n - frame_bytes
					offset += frame_bytes
				if n > 0:
					prev_content = curr_content[offset:]
				else:
					prev_content = b''

				num_voiced = len([f for f in ring_buffer if f is True])
				num_unvoiced = len(ring_buffer) - num_voiced

				# logger.info("%d, %d", num_voiced, num_unvoiced)

				if not triggered:
					if num_voiced > 0.5*ring_buffer.maxlen:
						triggered = True
						logger.info('Triggered start of speech')
				else:
					if num_unvoiced > 0.9*ring_buffer.maxlen:
						end_of_speech = True

				if end_of_speech:
					logger.info('Got end of speech from VAD')
					break


			for Q in listQueues:
				Q.put(chunk.content)

		for Q in listQueues:
			Q.put('EOS')

	def _mergeStream(self, asr_response_iterator, responseQueue, asr):
		''' Place the item from the response_iterator of asr into a common
			queue called responseQueue
		'''

		for asr_response in asr_response_iterator:
			str_response = asr_response['transcript']
			is_final = asr_response['is_final']
			toClient_json = {'asr': asr, 'transcript': str_response,
								'is_final': is_final}
			responseQueue.put(toClient_json)
		responseQueue.put('DONE')


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

		thread.start_new_thread(self._splitStream, (request_iterator, all_queues, config))
		thread.start_new_thread(LogStream, (iter(all_queues[-1].get, 'EOS'), token))

		responseQueue = Queue.Queue()
		for ix, asr in enumerate(config['asrs']):
			if asr == 'google':
				gw = google.worker(token)
				thread.start_new_thread(self._mergeStream,
					(gw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
			if asr == 'ibm':
				ibmw = ibm.worker(token)
				thread.start_new_thread(self._mergeStream,
					(ibmw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
			if asr == 'hound':
				houndw = hound.worker(token)
				thread.start_new_thread(self._mergeStream,
					(houndw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))

		for item_json in IterableQueue(responseQueue, len(config['asrs'])):
			if item_json != 'DONE':

				if item_json['is_final']:

					each_record = {}
					each_record['asr'] = item_json['asr']
					each_record['transcript'] = item_json['transcript']
					each_record['is_final'] = item_json['is_final']
					each_record['confidence'] = 1.0
					record['results'].append(each_record)

					#TODO: write each record to DB separately because the client
					#may break the call after just one ASR finishes

				# keep sending transcript to client until *all* ASRs are DONE

				yield stt_pb2.TranscriptChunk(
					asr = item_json['asr'],
					transcript = item_json['transcript'],
					is_final = item_json['is_final'],
					confidence = 1.0,
					)

		# all asrs are DONE; write record to database
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

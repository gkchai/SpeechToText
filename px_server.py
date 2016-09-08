#!/usr/bin/env python
"""Proxy ASR server implementation in GRPC"""

from proto import px_pb2
import time
import random
import asr.goog as google
import asr.hound as hound
import asr.ibm as ibm
import threading
import json
import itertools
import thread
import Queue
import uuid
import argparse
import os
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

_SUPPORTED_ASR = ["google", "hound", "ibm"]
_LOG_PATH = 'log/'
_LOG_FILE = 'log/log.json'

class IterableQueue():

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

def LogStream(chunkIterator, asr_id):

	with open('%s/%s.raw'%(_LOG_PATH, asr_id), 'wb') as f:
		for chunk in chunkIterator:
			f.write(chunk)

class Listener(px_pb2.BetaListenerServicer):

	def __init__(self):
		""" put initializaiton code e.g. db access """
		with open(_LOG_FILE) as f:
			self.db = json.load(f)
		logger.debug('PX_server initialized')

	def _write(self, db):
		with open(_LOG_FILE, 'w') as f:
			json.dump(self.db, f,  sort_keys=True, indent=4)

	def _splitStream(self, request_iterator, listQueues):

		for chunk in request_iterator:
			for Q in listQueues:
				Q.put(chunk.content)
			# print(len(chunk.content))
		for Q in listQueues:
			Q.put('EOS')

	def _mergeStream(self, asr_response_iterator, responseQueue, asr):
		for asr_response in asr_response_iterator:
			str_response = asr_response['transcript']
			is_final = asr_response['is_final']
			toClient_json = {'asr': asr, 'transcript': str_response,
								'is_final': is_final}
			responseQueue.put(toClient_json)
		responseQueue.put('DONE')


	def DoConfig(self, request, context):

		if set(request.asr) > set(_SUPPORTED_ASR):
			raise Exception("ASR not supported")


		if request.encoding != 'LINEAR16':
			raise Exception("encoding not supported")

		if request.rate != 16000:
			raise Exception("Rate not supported")

		logger.debug('ProxyASR configuration done')
		return px_pb2.ConfigResult(status=True,
			streamingConfig=request)

	def DoChunkStream(self, request_iterator, context):

		# first item in iterator has the config and token
		first_item = next(request_iterator)

		if not (first_item.token) or not (first_item.streamingConfig):
			raise Exception("First callback must pass configuration and token")

		token = first_item.token
		config = {}
		config['asrs'] = first_item.streamingConfig.asr
		config['encoding'] = first_item.streamingConfig.encoding
		config['rate'] = first_item.streamingConfig.rate
		config['language'] = first_item.streamingConfig.language
		config['max_alternatives'] = first_item.streamingConfig.max_alternatives
		config['profanity_filter'] = first_item.streamingConfig.profanity_filter
		config['interim_results'] = first_item.streamingConfig.interim_results
		config['continuous'] = first_item.streamingConfig.continuous

		asr_id = str(uuid.uuid1())
		self.db[asr_id] = {}

		logger.debug('%s: ProxyASR doing chunk stream', asr_id)

		all_queues = []
		for _ in range(len(config['asrs'])):
			all_queues.append(Queue.Queue())

		# log queue
		all_queues.append(Queue.Queue())

		thread.start_new_thread(self._splitStream, (request_iterator, all_queues))
		thread.start_new_thread(LogStream, (iter(all_queues[-1].get, 'EOS'), asr_id))

		responseQueue = Queue.Queue()
		for ix, asr in enumerate(config['asrs']):
			if asr == 'google':
				gw = google.worker(asr_id)
				thread.start_new_thread(self._mergeStream,
					(gw.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
			if asr == 'ibm':
				thread.start_new_thread(self._mergeStream,
					(ibm.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))
			if asr == 'hound':
				thread.start_new_thread(self._mergeStream,
					(hound.stream(iter(all_queues[ix].get, 'EOS'), config),
						responseQueue, asr))


		for item_json in IterableQueue(responseQueue, len(config['asrs'])):
			if item_json != 'DONE':
				if item_json['is_final']:
					self.db[asr_id][item_json['asr']] = json.dumps(item_json)
					self.db[asr_id]['token'] = token
					self._write(self.db)

				yield px_pb2.ResponseStream(asr = item_json['asr'],
					transcript = item_json['transcript'],
					is_final = item_json['is_final'],
					confidence = 1.0,
					)


def serve(port):
	server = px_pb2.beta_create_Listener_server(Listener())
	server.add_insecure_port('[::]:%d'%port)
	server.start()
	try:
		while True:
			time.sleep(1000)
	except KeyboardInterrupt:
		server.stop(0)

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Proxy ASR service')
	parser.add_argument('-p', action='store', dest='port', type=int, default=8080,
		help='port')
	args = parser.parse_args()
	serve(args.port)
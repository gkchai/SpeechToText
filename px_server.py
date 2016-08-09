#!/usr/bin/env python
"""Proxy ASR server implementation in GRPC"""

import px_pb2
import time
import random
import asr_google as google
import asr_hound as hound
import asr_ibm as ibm
import threading
import json
import itertools
import thread
import Queue
import uuid
import argparse
import os

_SUPPORTED_ASR = ["google", "hound", "ibm"]
_LOG_PATH = './log/'
_LOG_FILE = './log/log.json'

class IterableQueue():

	def __init__(self, Q, predicate):
		self.Q = Q
		self.predicate = predicate

	def __iter__(self):
		return self

	def next(self):
		item = self.Q.get()
		if self.predicate(item):
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
		self.config = {}
		self.config_set = False
		with open(_LOG_FILE) as f:
			self.db = json.load(f)

	def write(self, db):
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

	def _predicate(self, x):
		if x == 'DONE':
			self.endcount += 1
			if self.endcount == len(self.asrs):
				return False
			else:
				return True
		else:
			return True

	def DoConfig(self, request, context):

		self.asrs = request.asr
		if set(self.asrs) > set(_SUPPORTED_ASR):
			raise Exception("ASR not supported")

		self.config['encoding'] = request.encoding
		self.config['rate'] = request.rate
		self.config['language'] = request.language
		self.config['max_alternatives'] = request.max_alternatives
		self.config['profanity_filter'] = request.profanity_filter
		self.config['interim_results'] = request.interim_results
		self.config_set = True
		return px_pb2.ConfigResult(status=True)


	def DoChunkStream(self, request_iterator, context):

		if not self.config_set:
			raise Exception("Configuration not set")

		asr_id = str(uuid.uuid1())
		print "Request-id: %s"%asr_id
		self.db[asr_id] = {}

		all_queues = []
		for _ in range(len(self.asrs)):
			all_queues.append(Queue.Queue())

		# log queue
		all_queues.append(Queue.Queue())

		thread.start_new_thread(self._splitStream, (request_iterator, all_queues))
		thread.start_new_thread(LogStream, (iter(all_queues[-1].get, 'EOS'), asr_id))

		responseQueue = Queue.Queue()
		for ix, asr in enumerate(self.asrs):
			if asr == 'google':
				thread.start_new_thread(self._mergeStream,
					(google.stream(iter(all_queues[ix].get, 'EOS'), self.config), responseQueue, asr))
			if asr == 'ibm':
				thread.start_new_thread(self._mergeStream,
					(ibm.stream(iter(all_queues[ix].get, 'EOS'), self.config), responseQueue, asr))
			if asr == 'hound':
				thread.start_new_thread(self._mergeStream,
					(hound.stream(iter(all_queues[ix].get, 'EOS'), self.config), responseQueue, asr))

		self.endcount = 0
		for item_json in IterableQueue(responseQueue, self._predicate):
			if item_json != 'DONE':
				if item_json['is_final']:
					self.db[asr_id][item_json['asr']] = json.dumps(item_json)
					self.write(self.db)

				yield px_pb2.ResponseStream(asr = item_json['asr'], transcript = item_json['transcript'],
					is_final = item_json['is_final'])


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
	parser.add_argument('-p', action='store', dest='port', type=int, default=8080, help='port')
	args = parser.parse_args()
	serve(args.port)
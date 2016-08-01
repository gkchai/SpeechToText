"""Proxy ASR server implementation in GRPC"""

import px_pb2
import time
import random
import asr_google, asr_hound
import threading
import json
import itertools
import thread
import Queue
import uuid

# asrs = ["google", "ibm", "hound"]
# asrs = ["google", "ibm", "hound"]
asrs = ["google", "hound"]

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
	
	filename = "log/%s.raw"%asr_id
	with open(filename, 'wb') as f:
		for chunk in chunkIterator:
			f.write(chunk)

class Listener(px_pb2.BetaListenerServicer):

	def __init__(self):
		""" put initializaiton code e.g. db access """
		with open('log/log.json') as f:
			self.db = json.load(f)

	def write(self, db):
		with open('log/log.json', 'w') as f:
			json.dump(self.db, f,  sort_keys=True, indent=4)

	def _splitStream(self, request_iterator, listQueues):

		for chunk in request_iterator:	
			for Q in listQueues:
				Q.put(chunk.content)	
			# print(len(chunk.content))

		for Q in listQueues:
			Q.put('EOS')

	def _mergeStream(self, response_iterator, responseQueue, asr):
		for response in response_iterator:
			str_response = str(response)			
			toClient_json = {"asr": asr, "str": str_response}
			responseQueue.put(toClient_json)
		responseQueue.put('DONE')

	def predicate(self, x):
		if x == 'DONE':
			self.endcount += 1
			if self.endcount == len(asrs):
				return False
			else:
				return True
		else:
			return True


	def DoChunkStream(self, request_iterator, context):

		asr_id = str(uuid.uuid1())
		print "Request-id: %s"%asr_id
		self.db[asr_id] = {}
		
		all_queues = []
		for _ in range(len(asrs)):
			all_queues.append(Queue.Queue()) 

		# log queue
		all_queues.append(Queue.Queue())
		
		thread.start_new_thread(self._splitStream, (request_iterator, all_queues))
		thread.start_new_thread(LogStream, (iter(all_queues[-1].get, 'EOS'), asr_id))
		
		responseQueue = Queue.Queue()
		for ix, asr in enumerate(asrs):
			if asr == 'google':
				thread.start_new_thread(self._mergeStream, (asr_google.stream(iter(all_queues[ix].get, 'EOS')), responseQueue, asr))
			if asr == 'ibm':
				thread.start_new_thread(self._mergeStream, (asr_google.stream(iter(all_queues[ix].get, 'EOS')), responseQueue, asr))
			if asr == 'hound':
				thread.start_new_thread(self._mergeStream, (asr_hound.stream(iter(all_queues[ix].get, 'EOS')), responseQueue, asr))

		self.endcount = 0
		for item_json in IterableQueue(responseQueue, self.predicate):								
			if item_json != 'DONE':
				item_str = json.dumps(item_json)
				if "is_final" in item_str:
					self.db[asr_id][item_json["asr"]] = item_str
					self.write(self.db)

				yield px_pb2.StreamChunk(content = item_str)



def serve():
	server = px_pb2.beta_create_Listener_server(Listener())
	server.add_insecure_port('[::]:8888')
	server.start()
	try:
		while True:
			time.sleep(1000)
	except KeyboardInterrupt:
		server.stop(0)

if __name__ == '__main__':
	serve()
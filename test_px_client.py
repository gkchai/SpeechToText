"""Test ASR client implementation in GRPC"""

import px_pb2
from grpc.beta import implementations
import time
import argparse 
import random

_TIMEOUT_SECONDS_STREAM = 1000 	# timeout for streaming must be for entire stream 

def chunks_from_file(filename, chunkSize=1024):
	f = open(filename, 'rb')	
	while True:
		chunk = f.read(chunkSize)
		if chunk:
			# print len(chunk)
			yield px_pb2.StreamChunk(content=(chunk))
		else:
			raise StopIteration
		# time.sleep(random.uniform(0.01, 0.3))
		time.sleep(0.1)

def clientChunkStream(service, filename, chunkSize=1024):	
	""" chunk stream of bytes """
	responses = service.DoChunkStream(chunks_from_file(filename, chunkSize), _TIMEOUT_SECONDS_STREAM)
	for response in responses:
		print response.content
		print '\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n'

def createService():
	channel = implementations.insecure_channel('localhost', 8888)
	return px_pb2.beta_create_Listener_stub(channel)	
	

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Client to test the proxy ASR service')
	parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
	parser.add_argument('-type', action='store', dest='contentType', default='audio/wav', help='audio content type, for example: \'audio/l16; rate=44100\'')
	args = parser.parse_args()

	service = createService()	
	clientChunkStream(service, args.filename, 3200)
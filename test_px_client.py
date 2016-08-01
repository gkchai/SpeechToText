"""Test ASR client implementation in GRPC"""

import px_pb2
from grpc.beta import implementations
import time
import argparse 
import random
import sys
import wave

_TIMEOUT_SECONDS_STREAM = 1000 	# timeout for streaming must be for entire stream 


def chunks_from_file(filename, chunkSize=1024):

	if '.raw' in filename:
		f = open(filename, 'rb')	
		while True:
			chunk = f.read(chunkSize)
			if chunk:
				# print len(chunk)
				yield px_pb2.StreamChunk(content=(chunk))
			else:
				raise StopIteration
			time.sleep(0.1)

	elif 'stdin' in filename:
		while True:
			chunk = sys.stdin.read(chunkSize//2)
			if chunk:
				# print len(chunk)
				yield px_pb2.StreamChunk(content=(chunk))
			else:
				raise StopIteration
	
	elif '.wav' in filename:	
		audio = wave.open(filename)
        if audio.getsampwidth() != 2:
            print "%s: wrong sample width (must be 16-bit)" % filename
            raise StopIteration
        if audio.getframerate() != 8000 and audio.getframerate() != 16000:
			print "%s: unsupported sampling frequency (must be either 8 or 16 khz)" % filename
			raise StopIteration
        if audio.getnchannels() != 1:
			print "%s: must be single channel (mono)" % filename
			raise StopIteration		

        while True:
			chunk = audio.readframes(chunkSize//2) #each wav frame is 2 bytes
			if chunk:
				# print len(chunk)
				yield px_pb2.StreamChunk(content=(chunk))
			else:
				raise StopIteration
			time.sleep(0.1)

	else:
		raise StopIteration




def clientChunkStream(service, filename, chunkSize=1024):	
	""" chunk stream of bytes """
	responses = service.DoChunkStream(chunks_from_file(filename, chunkSize), _TIMEOUT_SECONDS_STREAM)
	for response in responses:
		print response.content
		print '\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n'

def createService():
	channel = implementations.insecure_channel('localhost', 8888)
	# channel = implementations.insecure_channel('10.37.163.202', 8888)
	return px_pb2.beta_create_Listener_stub(channel)	
	

if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Client to test the proxy ASR service')
	parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
	parser.add_argument('-type', action='store', dest='contentType', default='audio/wav', help='audio content type, for example: \'audio/l16; rate=44100\'')
	args = parser.parse_args()

	service = createService()	
	clientChunkStream(service, args.filename, 3072)
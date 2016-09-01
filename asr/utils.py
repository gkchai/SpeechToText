""" Common utlities """

import sys
import proto.px_pb2 as px_pb2
import time
import wave


# create an iterator that yields chunks in raw or grpc format
def generate_chunks(filename, token, grpc_on=False, chunkSize=3072):
	#raw byte file
	if '.raw' in filename:
		f = open(filename, 'rb')
		while True:
			chunk = f.read(chunkSize)
			if chunk:
				if grpc_on:
					yield px_pb2.StreamChunk(content=chunk, token=token)
				else:
					# print len(chunk)
					yield chunk
			else:
				raise StopIteration
			time.sleep(0.1)

	#piped stream from terminal
	elif 'stdin' in filename:
		while True:
			chunk = sys.stdin.read(chunkSize//2)
			if chunk:
				# print len(chunk)
				if grpc_on:
					yield px_pb2.StreamChunk(content=chunk, token=token)
				else:
					yield chunk
			else:
				raise StopIteration

	#wav file format
	elif '.wav' in filename:
		audio = wave.open(filename)
        if audio.getsampwidth() != 2:
            print ('%s: wrong sample width (must be 16-bit)' % filename)
            raise StopIteration
        if audio.getframerate() != 8000 and audio.getframerate() != 16000:
			print ('%s: unsupported sampling frequency (must be either 8 or 16 khz)' % filename)
			raise StopIteration
        if audio.getnchannels() != 1:
			print ('%s: must be single channel (mono)' % filename)
			raise StopIteration

        while True:
			chunk = audio.readframes(chunkSize//2) #each wav frame is 2 bytes
			if chunk:
				# print len(chunk)
				if grpc_on:
					yield px_pb2.StreamChunk(content=chunk, token=token)
				else:
					yield chunk
			else:
				raise StopIteration
			time.sleep(0.1)
	else:
		raise StopIteration
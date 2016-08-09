"""Test ASR client implementation in GRPC"""

from __future__ import print_function

import px_pb2
from grpc.beta import implementations
import time
import argparse
import random
import sys
import wave
import json

from blessings import Terminal

_TIMEOUT_SECONDS = 10
_TIMEOUT_SECONDS_STREAM = 100 	# timeout for streaming must be for entire stream

class Sender:

	def __init__(self, settings):
		self.settings = settings

	# create an iterator and pass it to grpc client
	def chunks_from_file(self, filename, chunkSize=1024):
		#raw byte file
		if '.raw' in filename:
			f = open(filename, 'rb')
			while True:
				chunk = f.read(chunkSize)
				if chunk:
					# print len(chunk)
					yield px_pb2.StreamChunk(content=chunk)
				else:
					raise StopIteration
				time.sleep(0.1)

		#piped stream from terminal
		elif 'stdin' in filename:
			while True:
				chunk = sys.stdin.read(chunkSize//2)
				if chunk:
					# print len(chunk)
					yield px_pb2.StreamChunk(content=chunk)
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
					yield px_pb2.StreamChunk(content=chunk)
				else:
					raise StopIteration
				time.sleep(0.1)
		else:
			raise StopIteration

	def configService(self, service):
		""" Configure ASR service with requested paramters """
		configParams = px_pb2.ConfigSpeech(
							asr = self.settings['asr'],
							rate = self.settings['rate'],
							language = self.settings['language'],
							encoding = self.settings['encoding'],
							max_alternatives = self.settings['max_alternatives'],
							interim_results = self.settings['interim_results']
						)
		configResponse = service.DoConfig(configParams, _TIMEOUT_SECONDS)
		return configResponse.status

	def printMultiple(self, response_dict, term):

		rows_pos = [3, 7, 11]
		row_pos = rows_pos[self.settings['asr'].index(response_dict['asr'])]
		# print (response_dict['str'])

		with term.location(0, row_pos):
			print (term.clear_eol) # clear till eol first
		with term.location(0, row_pos):
			if response_dict['is_final']:
				print (response_dict['transcript'] + '***')
			else:
				print (response_dict['transcript'])

	def clientChunkStream(self, service, filename, chunkSize=1024):
		""" send stream of chunks contaning audio bytes """

		responses = service.DoChunkStream(self.chunks_from_file(filename, chunkSize), _TIMEOUT_SECONDS_STREAM)


		term = Terminal()
		print(term.clear)
		rows_pos = [2, 6, 10]
		for ix, asr in enumerate(self.settings['asr']):
			with term.location(0, rows_pos[ix]):
				print ('############### %s ASR ################'%(asr))

		for response in responses:
			response_dict = {'asr': response.asr,
							  'transcript': response.transcript,
							  'is_final': response.is_final}

			self.printMultiple(response_dict, term)

		print('\n\n\n\n\n\n\n\n\n\n\n\n\n\n')
		print('\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n')


	def createService(self, port):
		channel = implementations.insecure_channel('localhost', port) # local
		# channel = implementations.insecure_channel('10.37.163.202', port) # lenovo server
		# channel = implementations.insecure_channel('52.91.17.237', port) # aws
		return px_pb2.beta_create_Listener_stub(channel)


if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Client to test the proxy ASR service')
	parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
	parser.add_argument('-p', action='store', type=int, dest='port', default=8080, help='port')
	args = parser.parse_args()

	with open('settings.json') as f:
		settings = json.load(f)

	senderObj = Sender(settings)
	service = senderObj.createService(args.port)
	senderObj.configService(service)
	senderObj.clientChunkStream(service, args.filename, 3072)
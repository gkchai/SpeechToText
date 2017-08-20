# author: kcgarikipati@gmail.com

"""Test STT client implementation in GRPC"""

from __future__ import print_function
import asr.utils as utils
from proto import stt_pb2
from grpc.beta import implementations
import argparse
import random
import sys
import json
import pprint
from blessings import Terminal
import pdb
import uuid

_TIMEOUT_SECONDS = 10
_TIMEOUT_SECONDS_STREAM = 1000 	# timeout for streaming must be for entire stream

class Sender:
	def __init__(self, settings):
		self.settings = settings

	def configService(self, service):
		""" Configure STT service with requested paramters """
		configParams = stt_pb2.ConfigSTT(
							asrs = self.settings['asrs'],
							sampling_rate = self.settings['sampling_rate'],
							language = self.settings['language'],
							encoding = self.settings['encoding'],
							max_alternatives = self.settings['max_alternatives'],
							interim_results = self.settings['interim_results'],
							continuous = self.settings['continuous'],
							inactivity = self.settings['inactivity'],
							chunksize = self.settings['chunksize']
						)
		configResponse = service.DoConfig(configParams, _TIMEOUT_SECONDS)
		# we create a random token which is used for streaming
		new_token = str(uuid.uuid1())
		return configResponse.config, new_token

	def printMultiple(self, response_dict, term):

		rows_pos = [3, 7, 11]
		row_pos = rows_pos[self.settings['asrs'].index(response_dict['asr'])]

		with term.location(0, row_pos):
			print (term.clear_eol) # clear till eol first
		with term.location(0, row_pos):
			if response_dict['is_final']:
				print (response_dict['transcript'] + '***')
			else:
				print (response_dict['transcript'])

	def clientChunkStream(self, service, filename, token, config, chunkSize=1024):
		""" send stream of chunks contaning audio bytes """

		## flow: in the the first call to the server, pass on a token, and
		## config that was returned after initial configuration. From second
		## call and later, pass on the audio chunks
		def request_stream():
			yield stt_pb2.SpeechChunk(token=token, config=config)
			for item in utils.generate_chunks(filename, grpc_on=True, chunkSize=chunkSize):
				yield item

		responses = service.DoSpeechToText(request_stream(), _TIMEOUT_SECONDS_STREAM)

		# clear terminal space for printing
		term = Terminal()
		print(term.clear)
		rows_pos = [2, 6, 10]
		for ix, asr in enumerate(self.settings['asrs']):
			with term.location(0, rows_pos[ix]):
				print ('############### %s ASR ################'%(asr))

		for response in responses:
			response_dict = {'asr': response.asr,
							  'transcript': response.transcript,
							  'is_final': response.is_final}

	  		# continuously refresh and print
	  		# print(response_dict)
			self.printMultiple(response_dict, term)

		print('\n\n\n\n\n\n\n\n\n\n\n\n\n\n')


	def createService(self, ipaddr, port):
		channel = implementations.insecure_channel(ipaddr, port)
		return stt_pb2.beta_create_Listener_stub(channel)


if __name__ == '__main__':

	parser = argparse.ArgumentParser(description='Client to test the STT service')
	parser.add_argument('-in', action='store', dest='filename', default='audio/whatistheweatherthere.wav',
		help='audio file')
	parser.add_argument('-a', action='store', dest='ipaddr',
        default='localhost',
        help='IP address of server. Default localhost.')
	parser.add_argument('-p', action='store', type=int, dest='port', default=9080, help='port')
	args = parser.parse_args()

	with open('settings.json') as f:
		settings = json.load(f)

	senderObj = Sender(settings)
	service = senderObj.createService(args.ipaddr, args.port)
	streamingconfig, token = senderObj.configService(service)
	senderObj.clientChunkStream(service, args.filename, token, streamingconfig, 3072)
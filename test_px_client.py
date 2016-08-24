"""Test ASR client implementation in GRPC"""

from __future__ import print_function
import asr.utils as utils
from proto import px_pb2
from grpc.beta import implementations
import argparse
import random
import sys
import json
import pprint
from blessings import Terminal
import pdb

_TIMEOUT_SECONDS = 10
_TIMEOUT_SECONDS_STREAM = 100 	# timeout for streaming must be for entire stream

class Sender:

	def __init__(self, settings):
		self.settings = settings

	def configService(self, service):
		""" Configure ASR service with requested paramters """
		configParams = px_pb2.ConfigSpeech(
							asr = self.settings['asr'],
							rate = self.settings['rate'],
							language = self.settings['language'],
							encoding = self.settings['encoding'],
							max_alternatives = self.settings['max_alternatives'],
							interim_results = self.settings['interim_results'],
							continuous = self.settings['continuous']
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

		responses = service.DoChunkStream(utils.generate_chunks(filename, grpc_on=True,
			chunkSize=chunkSize), _TIMEOUT_SECONDS_STREAM)

		# clear terminal space for printing
		term = Terminal()
		print(term.clear)
		rows_pos = [2, 6, 10]
		for ix, asr in enumerate(self.settings['asr']):
			with term.location(0, rows_pos[ix]):
				print ('############### %s ASR ################'%(asr))

		trans = {}
		for response in responses:
			response_dict = {'asr': response.asr,
							  'transcript': response.transcript,
							  'is_final': response.is_final}

	  		# continuously refresh and print
			self.printMultiple(response_dict, term)
			trans[response.asr] = response.transcript

		print('\n\n\n\n\n\n\n\n\n\n\n\n\n\n')
		print('\n+++++++++++++++++++ Assistant ++++++++++++++++++++++++\n')


		#### Multi-assistant API
		import requests
		url = 'http://52.91.17.237:8050/assistant'
		query = {
		"helpers": [
					"hound",
					# "ibm",
					# "apiai",
					"google_knowledge",
					"google_search"
					# "alexa"
				],
		"text": trans['google'],
		"context": {
						"loc":[41.8781, -87.6298],
						"city": "chicago"
					}
		}
		headers = {'Content-type': 'application/json',  'Accept': 'text/plain'}
		response = requests.post(url, json=query, headers=headers)
		pprint.pprint(response.json())

		print('\n++++++++++++++++++++++++++++++++++++++++++++++++++++++\n')



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
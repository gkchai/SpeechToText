# author: kcgarikipati@gmail.com


""" Interface for Google Cloud Speech ASR"""

from google.cloud import speech as cloud_speech
from google.cloud.speech import enums
from google.cloud.speech import types

from google.rpc import code_pb2
import time, random
import argparse
import utils, sys
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Audio recording parameters
RATE = 16000


class worker:

	def __init__(self, token):
		self.got_end_audio = False
		self.token = token


	def request_stream(self, chunkIterator):

		for data in chunkIterator:
			logger.debug("%s: sending to google = %d", self.token, len(data))
			if self.got_end_audio:
				raise StopIteration
			else:
				yield types.StreamingRecognizeRequest(audio_content=data)


	def stream(self, chunkIterator, config=None):

		is_final = False
		last_transcript = ''
		last_confidence = -1
		continuous_transcript = [''] # list of multiple is_final sub-transcripts
		try:
			service = cloud_speech.SpeechClient()
			logger.info("%s: Initialized", self.token)

			recognition_config = types.RecognitionConfig(
				# encoding=config['encoding'],
				encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
				sample_rate_hertz=config['sampling_rate'],
				max_alternatives=config['max_alternatives'],
				language_code=config['language'],
			)

			streaming_config = types.StreamingRecognitionConfig(
				config=recognition_config, interim_results=config['interim_results'],
				single_utterance=not (config['continuous']))

			responses = service.streaming_recognize(streaming_config, self.request_stream(chunkIterator))

			# putting a timer on responses rather than speech
			start_time = time.time()

			for response in responses:

				# logger.info(response)
				# print response, response.speech_event_type
				curr_time = time.time()

				if (curr_time - start_time) > 60:
					raise Exception('Streaming timeout')

				if response.speech_event_type == enums.StreamingRecognizeResponse.SpeechEventType.END_OF_SINGLE_UTTERANCE:
					logger.info('Got end of audio')
					self.got_end_audio = True

				if response.error.code != code_pb2.OK:
					raise RuntimeError('Server error: ' + response.error.message)

				# skip responses that contain endpoints but no results
				if not response.results:
					continue

				# There could be multiple results in each response.
				result = response.results[0]
				if not result.alternatives:
					continue


				last_transcript = result.alternatives[0].transcript
				continuous_transcript[-1] = last_transcript

				if result.is_final:
					if config['continuous']:
						continuous_transcript.append('')
					else:
						last_confidence = result.alternatives[0].confidence
						break
				else:
					yield {'transcript': (''.join(continuous_transcript) if config['continuous'] else last_transcript),
						'is_final': (False if config['continuous'] else result.is_final),
						'confidence': -1
						}

		except:
			e = sys.exc_info()[0]
			logger.error('%s: %s connection error', self.token, e)

		finally:
			yield {'transcript' : (''.join(continuous_transcript) if config['continuous'] else last_transcript),
					'is_final': True,
					'confidence': last_confidence}
			logger.info('%s: finished', self.token)

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
	args = parser.parse_args()
	config = {
	"language": "en-US",
	"encoding":"LINEAR16",
	"sampling_rate":RATE,
	"max_alternatives":5,
	"interim_results": True,
	"profanity_filter": True,
	"continuous": False,
	}

	W = worker('123456')
	responses = W.stream(utils.generate_chunks(args.filename, grpc_on=False, chunkSize=3072),
		config)
	for response in responses:
		print response
""" Interface for Google Cloud Speech ASR"""

from gcloud.credentials import get_credentials
from google.cloud.speech.v1beta1 import cloud_speech_pb2 as cloud_speech
from google.rpc import code_pb2
from grpc.beta import implementations
import time, random
import argparse
import utils, sys
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Audio recording parameters
RATE = 16000
CHANNELS = 1

# Keep the request alive for this many seconds
DEADLINE_SECS = 8 * 60 * 60
# DEADLINE_SECS = 10
SPEECH_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'

class worker:

	def __init__(self, token):
		self.got_end_audio = False
		self.token = token

	def make_channel(self, host, port):
	    """Creates an SSL channel with auth credentials from the environment."""
	    # In order to make an https call, use an ssl channel with defaults
	    ssl_channel = implementations.ssl_channel_credentials(None, None, None)

	    # Grab application default credentials from the environment
	    creds = get_credentials().create_scoped([SPEECH_SCOPE])
	    # Add a plugin to inject the creds into the header
	    auth_header = (
	        'Authorization',
	        'Bearer ' + creds.get_access_token().access_token)
	    auth_plugin = implementations.metadata_call_credentials(
	        lambda _, cb: cb([auth_header], None),
	        name='google_creds')

	    # compose the two together for both ssl and google auth
	    composite_channel = implementations.composite_channel_credentials(
	        ssl_channel, auth_plugin)
	    return implementations.secure_channel(host, port, composite_channel)

	def request_stream(self, chunkIterator, config):

		recognition_config = cloud_speech.RecognitionConfig(
			encoding= config['encoding'], sample_rate=config['sampling_rate'],
			max_alternatives=config['max_alternatives'],
			language_code = config['language'])

		streaming_config = cloud_speech.StreamingRecognitionConfig(
			config=recognition_config, interim_results=config['interim_results'],
			single_utterance=not(config['continuous']))

		yield cloud_speech.StreamingRecognizeRequest(streaming_config=streaming_config)

		for data in chunkIterator:

			logger.debug("%s: sending to google = %d", self.token, len(data))
			if self.got_end_audio:
				raise StopIteration
			else:
				yield cloud_speech.StreamingRecognizeRequest(audio_content=data)


	def stream(self, chunkIterator, config=None):

		is_final = False
		last_transcript = ''
		last_confidence = -1
		continuous_transcript = [''] # list of multiple is_final sub-transcripts
		try:
			service = cloud_speech.beta_create_Speech_stub(
				self.make_channel('speech.googleapis.com', 443))

			logger.info("%s: Initialized", self.token)
			responses = service.StreamingRecognize(self.request_stream(chunkIterator, config),
						DEADLINE_SECS)

			# putting a timer on responses rather than speech
			start_time = time.time()

			for response in responses:
				#  A good sequence of responses from ASR is
				#  1) endpointer_type: START_OF_SPEECH
				#  2) endpointer_type: END_OF_UTTERANCE
				#  3) endpointer_type: END_OF_AUDIO
				#  4) results = {alternatives {..}, ..., is_final: True}

				# An unusual sequence of responses from ASR is
				#  1) endpointer_type: START_OF_SPEECH
				#  2) endpointer_type: START_OF_SPEECH
				#  3) endpointer_type: START_OF_SPEECH
				#  4) endpointer_type: END_OF_UTTERANCE
				#  5) endpointer_type: END_OF_AUDIO
				#  6) Timeout and no result
				#  OR
				#  1) endpointer_type: START_OF_SPEECH
				#  2) endpointer_type: END_OF_AUDIO
				#  3) Timeout and no result

				# endpointer codes:
				# START_OF_SPEECH = 1
				# END_OF_UTTERANCE = 4
				# END_OF_AUDIO = 3

				# logger.info(response)
				# print response, response.endpointer_type
				curr_time = time.time()

				if (curr_time - start_time) > 60:
					raise Exception('Streaming timeout')


				if response.endpointer_type == 3:
					# logger.info('Got end of audio')
					self.got_end_audio = True

				if response.error.code != code_pb2.OK:
					raise RuntimeError('Server error: ' + response.error.message)

				# skip responses that contain endpoints but no results
				if len(response.results) > 0:

					last_transcript = response.results[0].alternatives[0].transcript
					continuous_transcript[-1] = last_transcript

					if response.results[0].is_final:
						if config['continuous']:
							continuous_transcript.append('')
						else:
							last_confidence = response.results[0].alternatives[0].confidence
							break
					else:
						yield {'transcript': (''.join(continuous_transcript) if config['continuous'] else last_transcript),
							'is_final': (False if config['continuous'] else response.results[0].is_final),
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
	"rate":16000,
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
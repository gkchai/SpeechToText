""" Interface for Google Cloud Speech ASR"""

from gcloud.credentials import get_credentials
from google.cloud.speech.v1beta1 import cloud_speech_pb2 as cloud_speech
from google.rpc import code_pb2
from grpc.beta import implementations
import time, random
import argparse 


# Audio recording parameters
RATE = 16000
CHANNELS = 1
CHUNK = int(RATE / 10)  # 100ms

# Keep the request alive for this many seconds
DEADLINE_SECS = 8 * 60 * 60
# DEADLINE_SECS = 10
SPEECH_SCOPE = 'https://www.googleapis.com/auth/cloud-platform'


def make_channel(host, port):
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

def request_stream(chunkIterator):

	recognition_config = cloud_speech.RecognitionConfig(
		encoding='LINEAR16', sample_rate=RATE, max_alternatives=5)
	
	streaming_config = cloud_speech.StreamingRecognitionConfig(
		config=recognition_config, interim_results=True, single_utterance=True)

	yield cloud_speech.StreamingRecognizeRequest(streaming_config=streaming_config)

	for data in chunkIterator:
		# Subsequent requests can all just have the content
		# time.sleep(random.uniform(0.01, 0.2))
		yield cloud_speech.StreamingRecognizeRequest(audio_content=data)


def stream(chunkIterator):	
	service = cloud_speech.beta_create_Speech_stub(
		make_channel('speech.googleapis.com', 443))
	responses = service.StreamingRecognize(request_stream(chunkIterator), DEADLINE_SECS)
	is_final = False
	try:
		for response in responses:
			if response.error.code != code_pb2.OK:
				raise RuntimeError('Server error: ' + response.error.message)

			if len(response.results) > 0:
				if response.results[0].alternatives[0].confidence:
					is_final = True
				yield response.results[0].alternatives[0].transcript

			if is_final:
				break
	except:
		yield ''
		# print len(response.results), time.time()

if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
	args = parser.parse_args()

	def generate_chunks(filename, chunkSize=3072):
	    if '.raw' in filename:
	        f = open(filename, 'rb')    
	        while True:
	            chunk = f.read(chunkSize)
	            if chunk:
	                print len(chunk)
	                yield chunk
	            else:
	                raise StopIteration
	            time.sleep(0.1)
	    
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
	                print len(chunk)
	                yield chunk
	            else:
	                raise StopIteration
	            time.sleep(0.1)
	    else:
	        raise StopIteration

	responses = stream(generate_chunks(args.filename, 3072))
	for response in responses:
		print '', #response
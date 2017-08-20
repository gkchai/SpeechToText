#  Speech-to-Text GRPC Microservice
Bi-directional streaming speech-to-text (STT or ASR) micro-service that proxies
cloud ASRs: Google Cloud Speech, IBM Bluemix STT speech and Hound STT. To avoid
cloud ASR from abruptly asserting end-of-speech, we implement custom voice-activity
detection (VAD) with tunable activity threshold.

# Install dependicies
Preferred way is to do in virtualenv (Python 2.7).
```pip install --upgrade pip```
```pip install -r requirements.txt```

# Compile .proto
```cd proto```
```bash generate_pb.sh```

# Proxy server

## Credentials

### Google ASR
Download the service account key for [Google Cloud Speech](https://cloud.google.com/speech/)
and move it to `asr/google_key.json`. Run the following command in the terminal
to set the Google ASR credential path
```export GOOGLE_APPLICATION_CREDENTIALS=asr/google_key.json```

### Hound ASR
Add clientID and ClientKey for [Hound STT](https://www.houndify.com/) under
`asr/hound_key.json`

### Hound ASR
Add credentials for [IBM Bluemix STT](https://www.ibm.com/watson/services/speech-to-text/)
under `asr/ibm_key.json`



## Database
Uses local `log` directory.

## Create log directory
Create `log` folder and `log/log.json` file with empty (`{}`) json contents.

## Start server
Start the server on a given port. Running on ports below 1024 requires root privileges.
```python stt_server.py -p 9080```

# Proxy Client

## Configuration
Edit `settings.json` to specify the ASR settings.

## Stream from recorded file
```python test_stt_client.py -p 9080 -in audio/whatistheweatherthere.wav```

## Stream from microphone (MAC OS)
Assumes rec and sox are installed. Available at http://sox.sourceforge.net/
`rec -p -q | sox - -c 1 -r 16000 -t s16 -q -L - | python test_stt_client.py -p 9080 -in stdin`

## Long running speech
Set ```continuous: true``` and ```chunksize: 3072``` (byte size of audio chunk)
in settings.json for continuous long running speech (capped at ~1min). WebRTC
VAD is utilized for silence detection.


## Running client
```
python test_stt_client.py -p 9080 -in audio/whatistheweatherthere.wav
```
shows the following output
```
############### google ASR ################
what is the weather there***


############### hound ASR ################
what is the weather there***


############### ibm ASR ################
what is the weather there ***
```


## Response format
Return type to the client  is a stream of JSON responses like:
```{
	"asr": "google",
	"transcript": "what is the weather there"
	"is_final": False
  }```

## Testing
Individual ASR blocks (XXX = goog, ibm, hound) can be tsted locally as follows.
For Google make sure the credentials are exported.
`python -m asr.XXX -in audio/whatistheweatherthere.wav`

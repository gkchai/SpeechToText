# About
Bi-directional streaming speech-to-text (STT or ASR) service that proxies existing ASRs such
as Google Cloud Speech, IBM Bluemix STT speech and Hound STT

# Install dependicies
Preferred way is to do in virtualenv (Python 2.7).
`pip install --upgrade pip`
`pip install -r requirements.txt`

# Compile .proto
`cd proto`
`python -m grpc.tools.protoc -I . --python_out=. --grpc_python_out=. stt.proto`

# Proxy server

## Credentials
Run the following command in the terminal to set the Google ASR credential path
`export GOOGLE_APPLICATION_CREDENTIALS=asr/google_key.json`

## Database
Uses MongoDB, if not present, then uses local `log` directory.

## Create log directory
Create `log` folder and `log/log.json` file with empty (`{}`) json contents.

## Start server
Start the server on a given port. Running on ports below 1024 requires root privileges.
`python stt_server.py -p 9080`

# Proxy Client

## Configuration
Edit `settings.json` to specify the ASR settings.

## Stream from recorded file
`python test_stt_client.py -p 9080 -in example.raw`
`python test_stt_client.py -p 9080 -in example.wav`

## Stream from microphone
Assumes rec and sox are installed. Available at http://sox.sourceforge.net/
`rec -p -q | sox - -c 1 -r 16000 -t s16 -q -L - | python test_stt_client.py -p 9080 -in stdin`

## Response format
Return type to the client  is a JSON string
`{
	"asr": "google",
	"transcript": "several tornadoes touch down in"
	"is_final": False
  }`

# Testing

Individual ASR blocks (XXX = goog, ibm, hound) can be tsted locally as follows:
`python -m asr.XXX -in example.raw`

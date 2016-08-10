# About
Bi-directional streaming ASR service that proxies existing ASRs such as Google Speech, IBM Bluemix speech, Hound ASR etc.

# Install dependicies
Preferred way is to do in virtualenv.
`pip install --upgrade`
`pip install -r requirements.txt`

# Compile .proto
`python -m grpc.tools.protoc -I . --python_out=. --grpc_python_out=. px.proto`

# Proxy server

## Credentials
Run the following command in the terminal to set the Google ASR credential path
`export GOOGLE_APPLICATION_CREDENTIALS=google_key.json`

## Start server
Start the server on a given port. Running on ports below 1024 requires root privileges.
`python px_server.py -p 8080`

# Proxy Client

## Configuration
Edit `settings.json` to specify the ASR settings.

## Stream from recorded file
`python test_px_client.py -p 8080 -in example.raw`
`python test_px_client.py -p 8080 -in example.wav`

## Stream from microphone
Assumes rec and sox are installed. Available at http://sox.sourceforge.net/
`rec -p -q | sox - -c 1 -r 16000 -t s16 -q -L - | python test_px_client.py -p 8080 -in stdin`

## Response format
Return type from the GRPC server
`{"asr": "google", "transcript": "several tornadoes touch down in"
  "is_final": False}`


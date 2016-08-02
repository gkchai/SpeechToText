# About
Bi-directional streaming ASR service that proxies existing ASRs such as Google Speech, IBM Bluemix speech, Hound ASR etc.

# Install dependicies
Preferred way is to do in virualenv
`pip install -r requirements.txt`

# Compile .proto 
`python -m grpc.tools.protoc -I . --python_out=. --grpc_python_out=. px.proto`

# Set ASR credentials [for runnining server only]
Run the following command in the terminal to set the Google ASR credential path
`export GOOGLE_APPLICATION_CREDENTIALS=ml-platform-7a36223d4ee9.json`

# Stream from recorded file 
`python test_px_client.py -in example.raw`
`python test_px_client.py -in example.wav`

# Stream from microphone
Assumes rec and sox are installed. Available at http://sox.sourceforge.net/
`rec -p -q | sox - -c 1 -r 16000 -t s16 -q -L - | python test_px_client.py -in stdin`

# Response format
Returned as raw bytes by grpc which is just an alias for string in Py 2.x
'{"asr": "google", "str": "several tornadoes touch down in the line of severe thunderstorm swept through Colorado on Sunday"}''
'{"asr": "hound", "str": "several tornadoes touch down is a line of severe thunderstorms swept through colorado on sunday"}'
'{"asr": "ibm", "str": "several tornadoes touch down in the line of severe thunderstorm swept through Colorado on Sunday"}'
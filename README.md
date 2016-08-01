# About
Bi-directional streaming ASR service that proxies existing ASRs such as Google Speech, IBM Bluemix speech, Hound ASR etc.

# Set ASR credentials
Run the following command in the terminal to set the Google ASR credential path
`export GOOGLE_APPLICATION_CREDENTIALS=ml-platform-7a36223d4ee9.json`

# Stream from recorded file 
`python test_px_client.py -in example.raw`
`python test_px_client.py -in example.wav`

# Stream from microphone 
`rec -p -q | sox - -c 1 -r 16000 -t s16 -q -L - | python test_px_client.py -in stdin`

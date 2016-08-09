""" Interface for IBM Bluemix Speech to Text ASR"""

import json                                      # json
import threading                                 # multi threading
import os                                        # for listing directories
import Queue                                     # queue used for thread syncronization
import sys                                       # system calls
import argparse                                  # for parsing arguments
import thread
import Queue
import wave
import time
import base64

# WebSockets
from ws4py.client.threadedclient import WebSocketClient

def get_credentials():
   with open('ibm_key.json') as f:
      creds = json.load(f)
   return creds['credentials']


class ASRClient(WebSocketClient):
    def __init__(self, url, headers, chunkIterator, responseQueue, contentType):
        self.chunkIterator = chunkIterator
        self.responseQueue = responseQueue
        self.contentType = contentType
        self.listeningMessages = 0
        WebSocketClient.__init__(self, url, headers=headers.items())


    def opened(self):
        data = {"action" : "start", "content-type" : str(self.contentType), "continuous" : True, "interim_results" : True, "inactivity_timeout": 6}
        data['word_confidence'] = True
        data['timestamps'] = True
        data['max_alternatives'] = 3

        # send the initialization parameters
        self.send(json.dumps(data).encode('utf8'))
        def send_chunk():
            try:
                for data in self.chunkIterator:
                    self.send(data, binary=True)
                self.send(b'', binary=True)
            except:
                print "Closed called by server"

        t = threading.Thread(target=send_chunk)
        t.start()

    def closed(self, code, reason=None):
        print "Closed down", code, reason
        if code != 2000:
            self.responseQueue.put('EOS')


    def received_message(self, msg):

        payload = msg.data
        jsonObject = json.loads(payload.decode('utf8'))
        if 'state' in jsonObject:
            self.listeningMessages += 1
            if (self.listeningMessages == 2):
               # close the connection
                self.close(1000)

         # if in streaming
        elif 'results' in jsonObject:
            jsonObject = json.loads(payload.decode('utf8'))
            hypothesis = ""

            # empty hypothesis
            if (len(jsonObject['results']) == 0):
                print "empty hypothesis!"
            # regular hypothesis
            else:
                jsonObject = json.loads(payload.decode('utf8'))
                hypothesis = jsonObject['results'][0]['alternatives'][0]['transcript']
                bFinal = (jsonObject['results'][0]['final'] == True)
                self.responseQueue.put(hypothesis)
                if bFinal:
                    print "got final", self.listeningMessages
                    self.responseQueue.put('EOS')
                    self.close(2000)

def stream(chunkIterator, config=None):

    # parse command line parameters
    contentType = 'audio/l16; rate=16000'
    model = 'en-US_BroadbandModel'
    optOut = False

    hostname = "stream.watsonplatform.net"
    headers = {}
    if (optOut == True):
        headers['X-WDC-PL-OPT-OUT'] = '1'

    creds = get_credentials()
    string = creds['username'] + ":" + creds['password']
    headers["Authorization"] = "Basic " + base64.b64encode(string)

    url = "wss://" + hostname + "/speech-to-text/api/v1/recognize?model=" + model

    responseQueue = Queue.Queue()
    client = ASRClient(url, headers, chunkIterator, responseQueue, contentType)
    try:
        client.connect()
        responseIterator =  iter(responseQueue.get, 'EOS')
        for response in responseIterator:
            yield {'transcript' : response, 'is_final': False}
        yield {'transcript' : response, 'is_final': True}

    except:
        e = sys.exc_info()[0]
        print >> sys.stderr, "connection error", e
        raise StopIteration


if __name__ == '__main__':

   # logging
   # log.startLogging(sys.stdout)
   parser = argparse.ArgumentParser()
   parser = argparse.ArgumentParser(description='client to do speech recognition using the WebSocket interface to the Watson STT service')
   parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
   args = parser.parse_args()
   def generate_chunks(filename, chunkSize=1024):
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
     print response
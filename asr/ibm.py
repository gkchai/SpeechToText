""" Interface for IBM Bluemix Speech to Text ASR"""

import json                                      # json
import threading                                 # multi threading
import os                                        # for listing directories
import Queue                                     # queue used for thread syncronization
import sys                                       # system calls
import argparse                                  # for parsing arguments
import thread
import Queue
import base64
import utils

# WebSocket client
from ws4py.client.threadedclient import WebSocketClient

def get_credentials():
   with open('asr/ibm_key.json') as f:
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
        data = {"action" : "start", "content-type" : str(self.contentType),
        "continuous" : False, "interim_results" : True, "inactivity_timeout": 10}
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
                print "Abort sending. Closed called by server"

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
                    # print "got final", self.listeningMessages
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

    last_transcript = ''
    try:
        client = ASRClient(url, headers, chunkIterator, responseQueue, contentType)
        client.connect()
        responseIterator =  iter(responseQueue.get, 'EOS')
        for response in responseIterator:
            last_transcript = response
            yield {'transcript' : last_transcript, 'is_final': False}
    except:
        e = sys.exc_info()[0]
        print >> sys.stderr, "ibm connection error", e
    finally:
        yield {'transcript' : last_transcript, 'is_final': True}

if __name__ == '__main__':

   # logging
   # log.startLogging(sys.stdout)
   parser = argparse.ArgumentParser()
   parser = argparse.ArgumentParser(description='speech recognition client interface to Watson STT service')
   parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
   args = parser.parse_args()

   responses = stream(utils.generate_chunks(args.filename, grpc_on=False,
       chunkSize=3072))
   for response in responses:
     print response
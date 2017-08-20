# author: kcgarikipati@gmail.com

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
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# WebSocket client
from ws4py.client.threadedclient import WebSocketClient

def get_credentials():
   with open('asr/ibm_key.json') as f:
      creds = json.load(f)
   return creds['credentials']

class ASRClient(WebSocketClient):
    def __init__(self, url, headers, chunkIterator, responseQueue, contentType, config):
        self.chunkIterator = chunkIterator
        self.responseQueue = responseQueue
        self.contentType = contentType
        self.listeningMessages = 0
        self.config = config
        WebSocketClient.__init__(self, url, headers=headers.items())
        logger.debug("IBM initialized")

    def opened(self):
        data = {"action" : "start", "content-type" : str(self.contentType),
        "continuous" : self.config['continuous'], "interim_results" : True, "inactivity_timeout": 100}

        logger.debug(data)
        data['word_confidence'] = True
        data['timestamps'] = True
        data['max_alternatives'] = 3

        # send the initialization parameters
        self.send(json.dumps(data).encode('utf8'))
        logger.debug("IBM initialization parameters sent")

        def send_chunk():
            try:
                for data in self.chunkIterator:
                    self.send(data, binary=True)
                    logger.debug("Sending to IBM = %d", len(data))
                self.send(b'', binary=True)
            except:
                logger.debug("Abort sending. Closed called by server")

        t = threading.Thread(target=send_chunk)
        t.start()

    def closed(self, code, reason=None):
        logger.debug("Closed down %s %s", code, reason)
        if code != 2000:
            self.responseQueue.put('EOS')
        logger.debug('IBM fnished')


    def received_message(self, msg):

        payload = msg.data
        jsonObject = json.loads(payload.decode('utf8'))
        if 'state' in jsonObject:
            self.listeningMessages += 1
            if (self.listeningMessages == 2):
               # close the connection
                logger.debug('closing IBM')
                self.close(1000)

         # if in streaming
        elif 'results' in jsonObject:
            jsonObject = json.loads(payload.decode('utf8'))
            hypothesis = ""

            # empty hypothesis
            if (len(jsonObject['results']) == 0):
                logger.error( "empty hypothesis!")
                self.responseQueue.put('EOS')
                self.close(2000)
            # regular hypothesis
            else:
                jsonObject = json.loads(payload.decode('utf8'))
                hypothesis = jsonObject['results'][0]['alternatives'][0]['transcript']
                bFinal = (jsonObject['results'][0]['final'] == True)
                self.responseQueue.put(hypothesis)
                if bFinal:
                    # print "got final", self.listeningMessages
                    logger.debug('IBM fnished from final hypothesis')
                    self.responseQueue.put('EOS')
                    self.close(2000)


class worker:

    def __init__(self, token):
        self.token = token

    def stream(self, chunkIterator, config=None):
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
            client = ASRClient(url, headers, chunkIterator, responseQueue, contentType, config)
            client.connect()
            logger.info("%s: Initialized", self.token)
            responseIterator =  iter(responseQueue.get, 'EOS')
            for response in responseIterator:
                last_transcript = response
                yield {'transcript' : last_transcript, 'is_final': False}
        except:
            e = sys.exc_info()[0]
            logger.error('%s: %s connection error', self.token, e)
        finally:
            yield {'transcript' : last_transcript, 'is_final': True}
            logger.info('%s: finished', self.token)


if __name__ == '__main__':

   # logging
   # log.startLogging(sys.stdout)
   parser = argparse.ArgumentParser()
   parser = argparse.ArgumentParser(description='speech recognition client interface to Watson STT service')
   parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
   args = parser.parse_args()

   W = worker('123456')
   responses = W.stream(utils.generate_chunks(args.filename, grpc_on=False,
       chunkSize=3072))
   for response in responses:
     print response
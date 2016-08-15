#!/usr/bin/env python

""" Interface for Hound Speech to Text ASR"""

import wave
import houndify
import sys
import json
import Queue
import argparse
import thread
import utils

class ResponseListener(houndify.HoundListener):
    def __init__(self, responseQueue):
        self.responseQueue = responseQueue
    def onPartialTranscript(self, transcript):
        self.responseQueue.put(transcript)
    def onFinalResponse(self, response):
        # self.responseQueue.put(response)
        self.responseQueue.put('EOS')
        print "Final response: " + response
    def onTranslatedResponse(self, response):
        print "Translated response: " + response
    def onError(self, err):
        self.responseQueue.put('EOS')
        print "ERROR"


def credentials():
    with open("hound_key.json") as f:
        creds_json = json.load(f)
    creds = {}
    creds['CLIENT_ID'] = str(creds_json["ClientID"])
    creds['CLIENT_KEY'] = str(creds_json["ClientKey"])
    return creds

# TODO: Move everything under a single class
def request_stream(client, chunkIterator, responseQueue):
    try:
        finished = False
        for data in chunkIterator:
            if not finished:
                finished = client.fill(data)
        client.finish()
    except:
        responseQueue.put('EOS')
        return

def stream(chunkIterator, config=None):
    creds = credentials()
    client = houndify.StreamingHoundClient(creds['CLIENT_ID'], creds['CLIENT_KEY'], "asr_user")
    client.setSampleRate(16000)
    client.setLocation(37.388309, -121.973968)

    responseQueue = Queue.Queue()
    client.start(ResponseListener(responseQueue))
    thread.start_new_thread(request_stream, (client, chunkIterator, responseQueue))

    responseIterator =  iter(responseQueue.get, 'EOS')
    for response in responseIterator:
        yield {'transcript' : response, 'is_final': False}
    yield {'transcript' : response, 'is_final': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-in', action='store', dest='filename', default='audio/test1.raw', help='audio file')
    args = parser.parse_args()

    responses = stream(utils.generate_chunks(args.filename, grpc_on=False, chunkSize=3072))
    for response in responses:
        print response
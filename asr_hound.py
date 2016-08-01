#!/usr/bin/env python
import wave
import houndify
import sys
import time
import json
import Queue
import argparse 
import thread

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

def request_stream(client, chunkIterator):
    finished = False
    for data in chunkIterator:
        if not finished:
            finished = client.fill(data)
    client.finish()


def stream(chunkIterator):
    creds = credentials()
    client = houndify.StreamingHoundClient(creds['CLIENT_ID'], creds['CLIENT_KEY'], "asr_user")
    client.setSampleRate(16000)
    client.setLocation(37.388309, -121.973968)
    
    responseQueue = Queue.Queue()
    client.start(ResponseListener(responseQueue))
    thread.start_new_thread(request_stream, (client, chunkIterator))

    responseIterator =  iter(responseQueue.get, 'EOS')
    for response in responseIterator:
        yield response
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
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
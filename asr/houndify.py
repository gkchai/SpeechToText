##############################################################################
# Copyright 2015 SoundHound, Incorporated.  All rights reserved.
##############################################################################
import base64
import hashlib
import hmac
import httplib
import json
import threading
import time
import uuid
import urllib
import zlib
import struct

try:
  import pySHSpeex
except ImportError:
  pass

HOUND_SERVER = "api.houndify.com"
TEXT_ENDPOINT = "/v1/text"
VOICE_ENDPOINT = "/v1/audio"
VERSION = '0.3.0'


class _BaseHoundClient:

    def setHoundRequestInfo(self, key, value):
      """
      There are various fields in the HoundRequestInfo object that can
      be set to help the server provide the best experience for the client.
      Refer to the Houndify documentation to see what fields are available
      and set them through this method before starting a request
      """
      self.HoundRequestInfo[key] = value


    def setLocation(self, latitude, longitude):
      """
      Many domains make use of the client location information to provide
      relevant results.  This method can be called to provide this information
      to the server before starting the request.

      latitude and longitude are floats (not string)
      """
      self.HoundRequestInfo['Latitude'] = latitude
      self.HoundRequestInfo['Longitude'] = longitude
      self.HoundRequestInfo['PositionTime'] = int(time.time())


    def _generateHeaders(self, requestInfo):
      requestID = str(uuid.uuid4())
      if 'RequestID' in requestInfo:
        requestID = requestInfo['RequestID']

      timestamp = str(int(time.time()))
      if 'TimeStamp' in requestInfo:
        timestamp = str(requestInfo['TimeStamp'])

      HoundRequestAuth = self.userID + ";" + requestID
      h = hmac.new(self.clientKey, (HoundRequestAuth + timestamp).encode('utf-8'), hashlib.sha256)
      signature = base64.urlsafe_b64encode(h.digest()).decode('utf-8')
      HoundClientAuth = self.clientID + ";" + timestamp + ";" + signature

      headers = { 
        'Hound-Request-Info': json.dumps(requestInfo),
        'Hound-Request-Authentication': HoundRequestAuth,
        'Hound-Client-Authentication': HoundClientAuth
      }

      if 'InputLanguageEnglishName' in requestInfo:
          headers["Hound-Input-Language-English-Name"] = requestInfo["InputLanguageEnglishName"]
      if 'InputLanguageIETFTag' in requestInfo:
          headers["Hound-Input-Language-IETF-Tag"] = requestInfo["InputLanguageIETFTag"]
          
      return headers



class TextHoundClient(_BaseHoundClient):
    """
    TextHoundClient is used for making text queries for Hound
    """
    def __init__(self, clientID, clientKey, userID, requestInfo = dict(), hostname = HOUND_SERVER):
      self.clientID = clientID
      self.userID = userID
      self.clientKey = base64.urlsafe_b64decode(clientKey)
      self.hostname = hostname

      self.HoundRequestInfo = {
        'ClientID': clientID,
        'UserID': userID,
        'SDK': 'python',
        'SDKVersion': VERSION
      }
      self.HoundRequestInfo.update(requestInfo)


    def query(self, query):
      """
      Make a text query to Hound.

      query is the string of the query
      """
      headers = self._generateHeaders(self.HoundRequestInfo)

      conn = httplib.HTTPSConnection(self.hostname)
      conn.request('GET', TEXT_ENDPOINT + '?query=' + urllib.quote(query), headers = headers)
      resp = conn.getresponse()

      return resp.read()



class StreamingHoundClient(_BaseHoundClient):
    """
    StreamingHoundClient is used to send streaming audio to the Hound
    server and receive live transcriptions back
    """
    def __init__(self, clientID, clientKey, userID, requestInfo = dict(), hostname = HOUND_SERVER, sampleRate = 16000, useSpeex = False):
      """
      clientID and clientKey are "Client ID" and "Client Key" 
      from the Houndify.com web site.
      """
      self.clientKey = base64.urlsafe_b64decode(clientKey)
      self.clientID = clientID
      self.userID = userID
      self.hostname = hostname
      self.sampleRate = sampleRate
      self.useSpeex = useSpeex

      self.HoundRequestInfo = {
        'ClientID': clientID,
        'UserID': userID,
        'SDK': 'python',
        'SDKVersion': VERSION,
        'ObjectByteCountPrefix': True, 
        'PartialTranscriptsDesired': True
      }
      self.HoundRequestInfo.update(requestInfo)


    def setSampleRate(self, sampleRate):
      """
      Override the default sample rate of 16 khz for audio.

      NOTE that only 8 khz and 16 khz are supported
      """
      if sampleRate == 8000 or sampleRate == 16000:
        self.sampleRate = sampleRate
      else:
        raise Exception("Unsupported sample rate")


    def start(self, listener):
      """
      This method is used to make the actual connection to the server and prepare
      for audio streaming.

      listener is a HoundListener (or derived class) object
      """
      self.audioFinished = False
      self.buffer = ''
    
      self.conn = httplib.HTTPSConnection(self.hostname)
      self.conn.putrequest('POST', VOICE_ENDPOINT)

      headers = self._generateHeaders(self.HoundRequestInfo)
      headers['Transfer-Encoding'] = 'chunked';
      
      for header in headers:
        self.conn.putheader(header, headers[header])
      self.conn.endheaders()
      
      audio_header = self._wavHeader(self.sampleRate)
      if self.useSpeex:
        audio_header = pySHSpeex.Init(self.sampleRate == 8000)
      self._send(audio_header)

      self.callbackTID = threading.Thread(target = self._callback, args = (listener,))
      self.callbackTID.start()


    def fill(self, data):
      """
      After successfully connecting to the server with start(), pump PCM samples
      through this method.

      data is 16-bit, 8 KHz/16 KHz little-endian PCM samples.
      Returns True if the server detected the end of audio and is processing the data
      or False if the server is still accepting audio
      """
      if self.audioFinished:
        # buffer gets flushed on next call to start()
        return True

      self.buffer += data
      
      # 20ms 16-bit audio frame = (2 * 0.02 * sampleRate) bytes
      frame_size = int(2 * 0.02 * self.sampleRate)
      while len(self.buffer) > frame_size:
        frame = self.buffer[:frame_size]
        if self.useSpeex:
          frame = pySHSpeex.EncodeFrame(frame)

        self._send(frame)

        self.buffer = self.buffer[frame_size:]

      return False


    def finish(self):
      """
      Once fill returns True, call finish() to finalize the transaction.  finish will
      wait for all the data to be received from the server.

      After finish() is called, you can start another request with start() but each
      start() call should have a corresponding finish() to wait for the threads
      """
      self._send(json.dumps({'endOfAudio': True}))
      self._send('')

      self.callbackTID.join()


    def _callback(self, listener):
      expectTranslatedResponse = False

      for line in self._readline(self.conn.sock):
        try:
          if expectTranslatedResponse:
            listener.onTranslatedResponse(msg)
            continue

          parsedMsg = json.loads(line)
          if "Format" in parsedMsg:
            if parsedMsg["Format"] == "SoundHoundVoiceSearchParialTranscript":
              ## also check SafeToStopAudio
              listener.onPartialTranscript(parsedMsg["PartialTranscript"])
              if "SafeToStopAudio" in parsedMsg and parsedMsg["SafeToStopAudio"]:
                ## Because of the GIL, simple flag assignment like this is atomic
                self.audioFinished = True

            if parsedMsg["Format"] == "SoundHoundVoiceSearchResult":
              ## Check for ConversationState and ConversationStateTime
              if "ResultsAreFinal" in parsedMsg:
                expectTranslatedResponse = True
              if "AllResults" in parsedMsg:
                for result in parsedMsg["AllResults"]:
                  if "ConversationState" in result:
                    self.HoundRequestInfo["ConversationState"] = result["ConversationState"]
                    if "ConversationStateTime" in result["ConversationState"]:
                      self.HoundRequestInfo["ConversationStateTime"] = result["ConversationState"]["ConversationStateTime"]
              listener.onFinalResponse(parsedMsg)

          elif "status" in parsedMsg:
            if parsedMsg["status"] != "ok":
              listener.onError(parsedMsg)
              break
        except:
          pass


    def _wavHeader(self, sampleRate=16000):
      genHeader = "RIFF" 
      genHeader += struct.pack('<L', 36) #ChunkSize - dummy   
      genHeader += "WAVE"
      genHeader += "fmt "                 
      genHeader += struct.pack('<L', 16) #Subchunk1Size
      genHeader += struct.pack('<H', 1)  #AudioFormat - PCM
      genHeader += struct.pack('<H', 1)  #NumChannels
      genHeader += struct.pack('<L', sampleRate) #SampleRate
      genHeader += struct.pack('<L', 8 * sampleRate) #ByteRate
      genHeader += struct.pack('<H', 2) #BlockAlign
      genHeader += struct.pack('<H', 16) #BitsPerSample
      genHeader += "data" 
      genHeader += struct.pack('<L', 0) #Subchunk2Size - dummy

      return genHeader


    def _send(self, msg):
      if self.conn:
        self.conn.send("%x\r\n" % len(msg))
        self.conn.send(msg + '\r\n')


    def _readline(self, socket):
      buffer = ''
      while True:
        if "\n" in buffer:
          (line, buffer) = buffer.split("\n", 1)
          yield line + "\n"
          continue
       
        more = socket.recv(4096)
        if not more: break
        buffer += more

      if buffer: yield buffer



class HoundListener:
    """
    HoundListener is an abstract base class that defines the callbacks
    that can be received while streaming speech to the server
    """
    def onPartialTranscript(self, transcript):
      """
      onPartialTranscript is fired when the server has sent a partial transcript
      in live transcription mode.  'transcript' is a string with the partial transcript
      """
      pass
    def onFinalResponse(self, response):
      """
      onFinalResponse is fired when the server has completed processing the query
      and has a response.  'response' is the JSON object (as a Python dict) which
      the server sends back.
      """
      pass
    def onTranslatedResponse(self, response):
      """
      onTranslatedResponse is fired if the server was requested to send the JSON
      response to an external API.  In that case, this will be fired after
      onFinalResponse and contain the raw data from the external translation API
      """
      pass
    def onError(self, err):
      """
      onError is fired if there is an error interacting with the server.  It contains
      the parsed JSON from the server.
      """
      pass


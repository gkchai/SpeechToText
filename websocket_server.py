import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.httpserver
import sys
from tornado import gen
import socket
from tornado.queues import Queue
from test_px_client import *
import json
import thread
import px_pb2
import Queue as Qu

from tornado.options import define, options, parse_command_line

define("port", default=3702, help="run on the given port", type=int)

_TIMEOUT_SECONDS_STREAM = 100     # timeout for streaming must be for entire stream
# we gonna store clients in dictionary..
clients = []


def grpc_worker(client, requestQueue):
    try:
        with open('settings.json') as f:
            settings = json.load(f)

        senderObj = Sender(settings)
        service = senderObj.createService(8090)
        senderObj.configService(service)
        responses = service.DoChunkStream(iter(requestQueue.get, 'EOS'),
            _TIMEOUT_SECONDS_STREAM)
        for response in responses:
            response_dict = {'asr': response.asr,
                              'transcript': response.transcript,
                              'is_final': response.is_final}
            resp_msg = json.dumps(response_dict)
            client.write_message(resp_msg)
            print("writing to client: %s"%(resp_msg))
    except:
        print "client connection is closed"
        if client:
            client.close()
        return

class BinaryStreamHandler(tornado.websocket.WebSocketHandler):

    @gen.coroutine
    def on_message(self, message):
        self.requestQueue.put(px_pb2.StreamChunk(content=message))
        # got this number by brute force so that all ASRs respond
        yield gen.sleep(0.07)

    def open(self, *args):
        self.stream.set_nodelay(True)
        print 'connected'
        self.requestQueue = Qu.Queue()
        thread.start_new_thread(grpc_worker, (self, self.requestQueue))

    def on_close(self):
        self.requestQueue.put('EOS')
        print 'closed'

    def check_origin(self, origin):
        return True

app = tornado.web.Application([
    (r'/ws', BinaryStreamHandler),
])

if __name__ == '__main__':
    app.listen(8899)
    myIP = socket.gethostbyname(socket.gethostname())
    print '*** Websocket Server Started at %s***' % myIP
    tornado.ioloop.IOLoop.instance().start()

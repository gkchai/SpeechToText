import tornado.ioloop
import tornado.web
import tornado.websocket
import tornado.httpserver
import sys
from tornado import gen
import socket
from tornado.queues import Queue

from tornado.options import define, options, parse_command_line

define("port", default=3702, help="run on the given port", type=int)

_TIMEOUT_SECONDS_STREAM = 1000     # timeout for streaming must be for entire stream
# we gonna store clients in dictionary..
clients = dict()


q = Queue()

@gen.coroutine
def consumer():
    while True:
        item = yield q.get()
        try:
            #print(len(item))
            sys.stdout.write(item)
            #incoming chunks are 1486 because of webaudio sampling rate
            #t = 1486/32000
            yield gen.sleep(0.046)
        finally:
            q.task_done()


class IndexHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    def get(self):
        self.write("This is your response")
        self.finish()

class BinaryStreamHandler(tornado.websocket.WebSocketHandler):

    @gen.coroutine
    def on_message(self, message):
        # echo message back to client
        #sys.stdout.write(message)
        yield q.put(message)
        #px_pb2.StreamChunk(content=(chunk))

    def open(self, *args):
        self.stream.set_nodelay(True)
        print 'connected'
        self.write_message("Hello World")

    def on_close(self):
        print 'closed'

    def check_origin(self, origin):
        return True

app = tornado.web.Application([
    (r'/', IndexHandler),
    (r'/ws', BinaryStreamHandler),
])

if __name__ == '__main__':
    app.listen(8899)
    myIP = socket.gethostbyname(socket.gethostname())
    print '*** Websocket Server Started at %s***' % myIP
    tornado.ioloop.IOLoop.current().spawn_callback(consumer)
    tornado.ioloop.IOLoop.instance().start()

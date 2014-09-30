#!/usr/bin/env python
#
# Copyright 2010 Formspring
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import json
import sys
import tornado.httpserver
import tornado.ioloop
from tornado.netutil import bind_unix_socket
import tornado.options
import tornado.web

from time import time
from tornado.options import define, options

define('address', group='webserver', default='', help='IP to bind')
define("port", help="run on the given port", type=int)
define('unix_socket', group='webserver', default=None,
       help='Path to unix socket to bind')
define("worker_id", type=int,
       help="globally unique worker_id between 0 and 1023")


class IDHandler(tornado.web.RequestHandler):
    max_time = int(time() * 1000)
    sequence = 0
    worker_id = False
    epoch = 1259193600000 # 2009-11-26
    
    def get(self):
        curr_time = int(time() * 1000)
        
        if curr_time < IDHandler.max_time:
            # stop handling requests til we've caught back up
            StatsHandler.errors += 1
            raise tornado.web.HTTPError(500, 'Clock went backwards! %d < %d' % (curr_time, IDHandler.max_time))
        
        if curr_time > IDHandler.max_time:
            IDHandler.sequence = 0
            IDHandler.max_time = curr_time
        
        IDHandler.sequence += 1
        if IDHandler.sequence > 4095:
            # Sequence overflow, bail out 
            StatsHandler.errors += 1
            raise tornado.web.HTTPError(500, 'Sequence Overflow: %d' % IDHandler.sequence)
        
        generated_id = ((curr_time - IDHandler.epoch) << 22) + (IDHandler.worker_id << 12) + IDHandler.sequence
        
        self.set_header("Content-Type", "application/json")
        self.write(str(generated_id))
        self.flush() # avoid ETag, etc generation 
        
        StatsHandler.generated_ids += 1


class StatsHandler(tornado.web.RequestHandler):
    generated_ids = 0
    errors = 0
    flush_time = time()
    
    def get(self):
        stats = {
            'timestamp': time(),
            'generated_ids': StatsHandler.generated_ids,
            'errors': StatsHandler.errors,
            'max_time_ms': IDHandler.max_time,
            'worker_id': IDHandler.worker_id,
            'time_since_flush': time() - StatsHandler.flush_time,
        }
        
        # Get values and reset
        if self.get_argument('flush', False):
            StatsHandler.generated_ids = 0
            StatsHandler.errors = 0
            StatsHandler.flush_time = time()
        
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(stats))


def main():
    tornado.options.parse_command_line()
    
    if 'worker_id' not in options:
        print('missing --worker_id argument, see %s --help' % sys.argv[0])
        sys.exit()
    
    if not 0 <= options.worker_id < 1024:
        print('invalid worker id, must be between 0 and 1023')
        sys.exit()
        
    IDHandler.worker_id = options.worker_id
    
    application = tornado.web.Application([
        (r"/", IDHandler),
        (r"/stats", StatsHandler),
    ], static_path="./static")

    http_server = tornado.httpserver.HTTPServer(application)

    if options.unix_socket:
        http_server.add_socket(bind_unix_socket(options.unix_socket, mode=0666))
    else:
        http_server.listen(options.port, options.address)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()

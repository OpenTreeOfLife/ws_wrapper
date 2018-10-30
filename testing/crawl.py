#!/usr/bin/python3

import requests
import time
from threading import Thread, Lock
import sys
import logging

try:
    # Python 3
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    # python 2.7
    from urllib import urlencode
    # noinspection PyCompatibility
    from urllib2 import HTTPError, Request, urlopen

log = logging.getLogger('ws_wrapper')

interactive_mode = False
tol_about = '/v3/tree_of_life/about'
tol_node_info = '/v3/tree_of_life/node_info'
tol_node_info_data = '{{"node_id": "{}"}}'
subtree_url='/v3/tree_of_life/subtree'
subtree_data ='{{synth_id: "opentree10.3", format: "arguson", height_limit: 3, node_id: "{n}"}}'
nodes = ['ott844192','ott93302']
nreqs=0
nreq_lock = Lock()
abort_called = False
waiting_for_user_response = Lock()

#perform an HTTP request using urllib
def _http_request_or_excep(method, url, data=None):
    log.debug('   Performing {} request: URL={}'.format(method, url))
    try:
        if isinstance(data, dict):
            data = urlencode(data.items())
        if isinstance(data ,str):
            data = data.encode('utf-8')
    except TypeError:
        log.warn('could not encode data={}'.format(repr(data)))
    req = Request(url=url, data=data)
    req.add_header('Content-Type', 'application/json')
    req.get_method = lambda: method
    try:
        response = urlopen(req)
        if response.code == 200:
            return response.read()
        log.debug("Error {}: {}".format(response.code(),response.read()))
    except HTTPError as err:
        try:
            b = err.read()
        except Exception:
            b = None
        if b:
            log.debug("Error {}: {}".format(err.code, b))
        else:
            log.debug("Error {}: could not connect to {}".format(err.code, url))
        return b

class User(Thread):
    
    def __init__(self, machine):
        Thread.__init__(self)
        self.machine = machine
        self.keep_going = True

    def post(self,url,d=None):
        global nreqs, abort_called
        with nreq_lock:
            nreqs += 1
        u = self.machine + url
        resp = _http_request_or_excep("POST",u,data=d)
#        resp = requests.post(u, data=d)
        if interactive_mode:
            with waiting_for_user_response:
                m = 'Last call to {} had status {} and payload {}.\n Abort (y/n)? '
                try:
                    j = resp.json()
                except:
                    j = '<no JSON payload decoded>'
                c = raw_input(m.format(u, resp.status_code, j))
                if c == 'y':
                    self.keep_going = False
                    abort_called = True
        return resp

    def run(self):
        while self.keep_going:
            r = self.post(tol_about)
            for node in nodes:
                if not self.keep_going:
                    return
                r = self.post(tol_node_info, tol_node_info_data.format(node))
#                r = self.post(subtree_url,subtree_data.format(n=node))

def main():
    global interactive_mode
    machine = sys.argv[1]
    # machine='http://localhost:1984'
    # machine='https://ot39.opentreeoflife.org'
    # machine='https://api.opentreeoflife.org'


#    logging.basicConfig(level=logging.DEBUG)

    # "Python threads will NOT make your program faster if it already uses 100 % CPU time.
    # In that case, you probably want to look into parallel programming."
    if len(sys.argv) < 3:
        nthreads = 40
    else:
        thread_arg = sys.argv[2]
        try:
            nthreads = int(thread_arg)
        except ValueError:
            if thread_arg == 'i':
                nthreads = 1
                interactive_mode = True
            else:
                raise

    print("Testing {}\n".format(machine))
    
    print("Starting {} threads:\n".format(nthreads))
    ts0 = time.time()
    for u in range(nthreads):
        user = User(machine)
        user.daemon = True
        user.start()

    last_count = 0
    last_t = ts0
    last_rate = 0
    smoothed_rate = 0.0
    smoothing = 0.85
    while True:
        with waiting_for_user_response:
            if abort_called:
                break
            cur_count = nreqs
            cur_t = time.time();

            delta_count = cur_count - last_count
            delta_t     = cur_t - last_t
            cur_rate = delta_count/delta_t
            smoothed_rate = smoothing*smoothed_rate + (1.0-smoothing)*cur_rate
            print("requests: {}    requests/sec = {}      smoothed requests/sec = {}".format(delta_count,cur_rate,smoothed_rate))
            last_count = cur_count
            last_t = cur_t
        time.sleep(1)

if __name__ == '__main__':
    main()

#!/usr/bin/python3

import requests
import time
from threading import Thread, Lock
import sys

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
        resp = requests.post(u, data=d)
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
    while True:
        with waiting_for_user_response:
            if abort_called:
                break
            print("requests: {}    requests/sec = {}".format(nreqs,nreqs/(time.time()-ts0)))
        time.sleep(1)

if __name__ == '__main__':
    main()

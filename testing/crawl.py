#!/usr/bin/python3

import requests
import time
from threading import Thread
import sys

machine = sys.argv[1]
# machine='http://localhost:1984'
# machine='https://ot39.opentreeoflife.org'
# machine='https://api.opentreeoflife.org'


tol_about = '/v3/tree_of_life/about'

tol_node_info = '/v3/tree_of_life/node_info'

tol_node_info_data = '{{"node_id": "{}"}}'

subtree_url='/v3/tree_of_life/subtree'

subtree_data ='{{synth_id: "opentree10.3", format: "arguson", height_limit: 3, node_id: "{n}"}}'

nodes = ['ott844192','ott93302']

nreqs=0

nthreads = 40

class User(Thread):
    
    def __init__(self, machine):
        Thread.__init__(self)
        self.machine = machine

    def post(self,url,d=None):
        global nreqs
        nreqs = nreqs+1
        return requests.post(self.machine+url,data=d)

    def run(self):
        while True:
            r = self.post(tol_about)
            for node in nodes:
                r = self.post(tol_node_info, tol_node_info_data.format(node))
#                r = self.post(subtree_url,subtree_data.format(n=node))

def main():
    print("Testing {}\n".format(machine))
    
    print("Starting {} threads:\n".format(nthreads))
    ts0 = time.time()
    for u in range(nthreads):
        user = User(machine)
        user.daemon = True
        user.start()
    while True:
        print("requests: {}    requests/sec = {}".format(nreqs,nreqs/(time.time()-ts0)))
        time.sleep(1)

if __name__ == '__main__':
    main()

#!/usr/bin/env python

import socket, sys
# Connect to the network. All messages to/from other replicas and clients will
# occur over this socket
# Your ID number
my_id = sys.argv[1]

sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
sock.connect(my_id)
import sys, select, time, json, random


# states
CANDIDATE = 'candidate'
FOLLOWER = 'follower'
LEADER_STATE = 'leader'

LEADER = 'FFFF'
VALUES = {}
ELECTION_TIMEOUT = random.uniform(.15, .3)
STATE = FOLLOWER
TERM = 0
VOTES = 0
VOTED_FOR = None
BUFFER = []
LOG = [{'term': 0}]
NEW_ENTRIES = []
RESPONSE_BUFFER = []

# The ID numbers of all the other replicas
replica_ids = sys.argv[2:]

# For leaders: dict<replica_id, index>
next_index = {} # Keeps track of the next log index to send to replicas
match_index = {} # Keeps track of the highest log entry known to be replicated for each replica

# All servers: volatile state. initialized to 0, increases monotonically
commit_index = 0 # highest log entry known to be committed.
last_applied = 0 # highest log entry *applied*.

# Timestamps
last = 0
leader_seen = 0

# Call after each election to re-initialize
def initialize_indices():
    global replica_ids, next_index, match_index
    for id in replica_ids:
        next_index[id] = len(LOG) # initialize to leader last log index + 1
        match_index[id] = 0 # initialized to 0, increases monotonically

def send_buffer():
    global BUFFER
    while (len(BUFFER) > 0):
        msg = BUFFER.pop(0)
        msg['leader'] = LEADER
        if STATE == LEADER_STATE:
            msg_leader(msg)
        else:
            msg_follower(msg)

def send_heartbeat():
    global LOG, replica_ids, next_index, commit_index, last, my_id, LEADER, TERM
    for id in replica_ids:
        end = min(len(LOG) - next_index[id], 10) + next_index[id]
        if next_index[id] == len(LOG):
            # send empty Heartbeat
            msg = {'src': my_id, 'dst': id, 'leader': LEADER, 'term': TERM, 'type': 'append_entries', 'commit_index': commit_index, 'prevLogIndex': (next_index[id] - 1), 'prevLogTerm': LOG[next_index[id] - 1], 'entries': None}
        else:
            entries = LOG[next_index[id]:end]
            msg = {'src': my_id, 'dst': id, 'leader': LEADER, 'term': TERM, 'type': 'append_entries', 'entries': entries, 'commit_index': commit_index, 'prevLogIndex': (next_index[id] - 1), 'prevLogTerm': LOG[next_index[id] - 1]['term']}
        sock.send(json.dumps(msg))
    last = clock


def begin_candidacy():
    global STATE, CANDIDATE, TERM, VOTES, ELECTION_TIMEOUT, leader_seen 
    STATE = CANDIDATE
    TERM = TERM + 1
    VOTES = 1
    ELECTION_TIMEOUT = random.uniform(.15, 3)
    leader_seen = time.time()
    last_index = len(LOG) - 1
    for id in replica_ids:
        msg = {'src': my_id, 'dst': id, 'leader': LEADER, 'type': 'request_vote', 'term': TERM, 'last_log_index': last_index, 'last_log_term': LOG[last_index]['term']}
        sock.send(json.dumps(msg))

def send_response_buffer():
    global RESPONSE_BUFFER
    while len(RESPONSE_BUFFER) > 0:
        sock.send(json.dumps(RESPONSE_BUFFER.pop(0)))
        

def handle_vote(msg):
    global LOG, TERM, leader_seen, LEADER, VOTED_FOR, CANDIDATE 
    if (TERM < msg['term']):
        last_index = len(LOG) - 1
        TERM = msg['term']
        LEADER = 'FFFF'
        STATE = FOLLOWER
        if (LOG[last_index]['term'] == msg['last_log_term'] and last_index <= msg['last_log_index']) or (LOG[last_index]['term'] < msg['last_log_term']):
            VOTED_FOR = msg['src']
            leader_seen = time.time()
            msg = {'src': my_id, 'dst': msg['src'], 'leader': 'FFFF', 'type': 'vote', 'term': TERM}
            sock.send(json.dumps(msg))

# Handler functions
def msg_leader(msg):
    global VALUES, leader_seen, LOG, LEADER, STATE, FOLLOWER, TERM, NEW_ENTRIES, next_index, match_index, RESPONSE_BUFFER, commit_index
    res = None
    if msg['type'] == 'get':
        # see if we have any uncommitted changes for that key
        ready = True
        for entry in LOG[commit_index + 1:]:
            if entry['term'] != TERM and entry['key'] == msg['key']:
                ready = False
                delayed = {'src': my_id, 'delayed': True,'dst': msg['src'], 'leader': LEADER, 'type': 'ok', 'MID': msg['MID'], 'value': entry['value']}
                RESPONSE_BUFFER.append(delayed)

        if ready: 
            res = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'ok', 'MID': msg['MID'], 'value': VALUES[msg['key']]}

    elif msg['type'] == 'put':
        LOG.append({'term': TERM, 'key': msg['key'], 'value': msg['value'], 'MID': msg['MID'], 'client': msg['src']})
        # send append_entries
        send_heartbeat()
    elif msg['type'] == 'append_entries':
        if (TERM < msg['term']):
            LEADER = msg['src']
            TERM = msg['term']
            leader_seen = time.time()
            STATE = FOLLOWER # they threw a coup :(
            RESPONSE_BUFFER = []
            send_buffer()
    elif msg['type'] == 'request_vote':
        if (TERM < msg['term']):
            handle_vote(msg)
            STATE = FOLLOWER # and we're going along with it :(
            RESPONSE_BUFFER = []
    elif msg['type'] == 'ACK':
        # update next_index and match_index
        if (msg['success']):
            received = min(msg['received_index'], len(LOG) - 1)
            next_index[msg['src']] = received + 1
            match_index[msg['src']] = received
            # see if we have a quorum
            count = 1
            new_idx = msg['received_index']
            for id in replica_ids:
                if (match_index[id] > commit_index and LOG[match_index[id]]['term'] == TERM):
                    count = count + 1
                    new_idx = min(new_idx, match_index[id])
            if count > (len(replica_ids) + 1) / 2:
                # good
                while (commit_index < new_idx):
                    entry = LOG[commit_index + 1]
                    VALUES[entry['key']] = entry['value']
                    commit_index = commit_index + 1
                    ok = {'src': my_id, 'dst': LOG[commit_index]['client'], 'leader': LEADER, 'type': 'ok', 'MID': LOG[commit_index]['MID']}
                    sock.send(json.dumps(ok))
                send_response_buffer()

        else: # Failure
            if (TERM < msg['term']): # We are not the valid leader
                # Give up the throne
                TERM = msg['term']
                STATE = FOLLOWER
            else: # Actual append_entries failure, we are ahead of this follower
                next_index[msg['src']] = max(next_index[msg['src']] - 1, 1)
    if res:
        sock.send(json.dumps(res))

def msg_candidate(msg):
    global BUFFER, leader_seen, LEADER, STATE, FOLLOWER, TERM, VOTES, LEADER_STATE
    if msg['type'] in ['get', 'put']:
    # store the message until the election is over
        BUFFER.append(msg)
    elif msg['type'] == 'append_entries' and TERM <= msg['term']:
        leader_seen = time.time()
        LEADER = msg['src']
        STATE = FOLLOWER
        RESPONSE_BUFFER = []
        send_buffer()
    elif msg['type'] == 'request_vote':
        handle_vote(msg)
    elif msg['type'] == 'vote':
        if (TERM == msg['term']):
            VOTES = VOTES + 1
            if (VOTES > (len(replica_ids) + 1) / 2):
                STATE = LEADER_STATE
                LEADER = my_id # declare victory
                initialize_indices() # configure leader indices
                send_buffer()
                VOTES = 0

def msg_follower(msg):
    global leader_seen, LEADER, TERM, BUFFER, VALUES, commit_index
    if msg['type'] in ['get', 'put']:
        msg = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'redirect', 'MID': msg['MID']}
        if (LEADER == 'FFFF'):
            BUFFER.append(msg)
        else:
            sock.send(json.dumps(msg))
    elif msg['type'] == 'request_vote':
        handle_vote(msg)
    elif msg['type'] == 'append_entries':
        leader_seen = time.time()

        if TERM > msg['term']:
            ack = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'ACK', 'success': False, 'term': TERM, 'commit_index': commit_index, 'received_index': msg['prevLogIndex'] + 1}
            sock.send(json.dumps(ack))
        elif (TERM < msg['term']):
            LEADER = msg['src']
            TERM = msg['term']
            send_buffer()
        else:
            LEADER = msg['src']
            # Commit everything that the leader has committed
            if msg['commit_index'] > commit_index:
                new_idx = min(msg['commit_index'], len(LOG) - 1)
                while (new_idx > commit_index):
                    entry = LOG[commit_index + 1]
                    VALUES[entry['key']] = entry['value']
                    commit_index = commit_index + 1


            if (msg['entries']):
                last_entry = len(LOG) - 1
                if msg['prevLogIndex'] <= last_entry and msg['prevLogTerm'] == LOG[msg['prevLogIndex']]['term']:
                    # add to log, send an ACK to the leader
                    entries = msg['entries']
                    start = msg['prevLogIndex'] + 1
                    while (start <= last_entry and len(entries) > 0):
                        LOG[start] = entries.pop(0)
                        start = start + 1
                    LOG.extend(entries)
                    ack = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'ACK', 'success': True, 'term': TERM, 'commit_index': commit_index, 'received_index': len(LOG) - 1}
                    sock.send(json.dumps(ack))
                elif msg['prevLogIndex'] <= last_entry and msg['prevLogTerm'] != LOG[msg['prevLogIndex']]['term']:
                    # actually delete stuff because we are ahead of the leader, ask them to send earlier things until we have a match
                    while msg['prevLogIndex'] < last_entry:
                        del LOG[last_entry]
                        last_entry = last_entry - 1
                    ack = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'ACK', 'success': False, 'term': TERM, 'commit_index': commit_index, 'received_index': msg['prevLogIndex'] + 1}
                    sock.send(json.dumps(ack))
                elif msg['prevLogIndex'] > last_entry:
                    # tell them to slow down
                    ack = {'src': my_id, 'dst': msg['src'], 'leader': LEADER, 'type': 'ACK', 'success': False, 'term': TERM, 'commit_index': commit_index, 'received_index': msg['prevLogIndex'] + 1}
                    sock.send(json.dumps(ack))
while True:
    ready = select.select([sock], [], [], 0.02)[0]
    if sock in ready:
        msg_raw = sock.recv(32768)

        if len(msg_raw) != 0:
            msg = json.loads(msg_raw)
            if (msg['dst'] == my_id):
                if STATE == LEADER_STATE:
                    msg_leader(msg)
                elif STATE == CANDIDATE:
                    msg_candidate(msg)
                else:
                    msg_follower(msg)

    clock = time.time()
    if STATE == LEADER_STATE and clock-last > .12:
        send_heartbeat()
    elif (STATE != LEADER_STATE) and (clock-leader_seen > ELECTION_TIMEOUT):
        begin_candidacy()
       

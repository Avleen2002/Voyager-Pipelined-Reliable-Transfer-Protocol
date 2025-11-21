#!/usr/bin/env python3
# voyager.py — Updated with correct ack_type logic, fast retransmit, and logs

import socket
import argparse
import threading
import time
import hashlib
import struct
import random

###############################################################################
# Utility
###############################################################################

def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16].encode()

###############################################################################
# Voyager Header Format
###############################################################################
HEADER_FORMAT = "!IIBIH16s"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
FLAG_SYN = 1
FLAG_ACK = 2
FLAG_FIN = 4

###############################################################################
# Congestion Control State
###############################################################################
class CongestionControl:
    def __init__(self):
        self.cwnd = 1
        self.ssthresh = 32
        self.dup_acks = 0

    def apply(self, ack_type):
        action = None
        if ack_type == "new_ack":
            self.dup_acks = 0
            if self.cwnd < self.ssthresh:
                self.cwnd += 1
                print(f"[CC] Slow start: cwnd={self.cwnd}")
            else:
                self.cwnd += 1 / self.cwnd
                print(f"[CC] Congestion avoidance: cwnd={self.cwnd:.2f}")

        elif ack_type == "dup_ack":
            self.dup_acks += 1
            print(f"[CC] Duplicate ACK detected ({self.dup_acks})")
            if self.dup_acks == 3:
                self.ssthresh = max(int(self.cwnd // 2), 1)
                self.cwnd = self.ssthresh
                print(f"[CC] Fast retransmit triggered! ssthresh={self.ssthresh}, cwnd={self.cwnd}")
                action = "fast_retx"

        elif ack_type == "timeout":
            self.ssthresh = max(int(self.cwnd // 2), 1)
            self.cwnd = 1
            self.dup_acks = 0
            print(f"[CC] Timeout: cwnd reset to {self.cwnd}, ssthresh={self.ssthresh}")

        return action

###############################################################################
# Flow Control
###############################################################################
class FlowControl:
    def __init__(self):
        self.send_window = 32 * 1024  # default max

    def apply(self, receiver_rwnd):
        self.send_window = min(self.send_window, receiver_rwnd)
        print(f"[FLOW CONTROL] Limiting window to RWND={receiver_rwnd}")

###############################################################################
# Voyager Sender
###############################################################################
class VoyagerClient:
    def __init__(self, server_ip, server_port, filename):
        self.server = (server_ip, server_port)
        self.file = filename
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.5)

        self.next_seq = 1
        self.base = 1
        self.cc = CongestionControl()
        self.fc = FlowControl()
        self.receiver_rwnd = 64 * 1024
        self.unacked = {}
        self.rto = 1.0
        self.srtt = None

    def send_header(self, seq, ack, flags, rwnd, payload):
        csum = checksum(payload)
        hdr = struct.pack(HEADER_FORMAT, seq, ack, flags, rwnd, len(payload), csum)
        return hdr + payload

    def handshake(self):
        pkt = self.send_header(0, 0, FLAG_SYN, 0, b"")
        self.sock.sendto(pkt, self.server)
        while True:
            try:
                data, _ = self.sock.recvfrom(2048)
                seq, ack, flags, rwnd, length, csum = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
                if flags & FLAG_SYN and flags & FLAG_ACK:
                    print("[HANDSHAKE] SYN+ACK received")
                    return
            except socket.timeout:
                print("[HANDSHAKE] Timeout, resending SYN")
                self.sock.sendto(pkt, self.server)

    def send_file(self):
        data = open(self.file, "rb").read()
        total = len(data)
        while self.base <= total:
            # Apply flow control
            self.fc.apply(self.receiver_rwnd)

            # Send data up to cwnd and flow control
            while len(self.unacked) < int(self.cc.cwnd) and (self.next_seq <= total):
                chunk = data[self.next_seq-1:self.next_seq+999]
                pkt = self.send_header(self.next_seq, 0, 0, 0, chunk)
                self.unacked[self.next_seq] = (pkt, time.time())
                self.sock.sendto(pkt, self.server)
                self.next_seq += len(chunk)

            # Receive ACKs
            try:
                resp, _ = self.sock.recvfrom(2048)
                seq, ack, flags, rwnd, length, csum = struct.unpack(HEADER_FORMAT, resp[:HEADER_SIZE])

                # Check for duplicate ACKs
                if ack > self.base:
                    ack_type = "new_ack"
                elif ack == self.base:
                    ack_type = "dup_ack"
                else:
                    continue  # stale ack, ignore

                action = self.cc.apply(ack_type)
                if action == "fast_retx":
                    oldest = min(self.unacked.keys())
                    self.sock.sendto(self.unacked[oldest][0], self.server)

                # Remove acknowledged packets
                for s in list(self.unacked.keys()):
                    if s < ack:
                        del self.unacked[s]
                self.base = max(self.base, ack)

            except socket.timeout:
                print("[TIMEOUT] ACK timeout, retransmitting oldest")
                self.cc.apply("timeout")
                for s, (pkt, _) in self.unacked.items():
                    self.sock.sendto(pkt, self.server)

        # Send FIN
        fin = self.send_header(self.next_seq, 0, FLAG_FIN, 0, b"")
        self.sock.sendto(fin, self.server)
        print("[TRANSFER] File transfer complete")

###############################################################################
# Voyager Server
###############################################################################
class VoyagerServer:
    def __init__(self, port, outfile, rwnd=65535):
        self.port = port
        self.outfile = outfile
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.expected_seq = 1
        self.rwnd = rwnd
        self.buf = {}
        self.output = open(outfile, "wb")

    def send_ack(self, addr):
        ack_pkt = struct.pack(HEADER_FORMAT, 0, self.expected_seq, FLAG_ACK, self.rwnd, 0, checksum(b""))
        self.sock.sendto(ack_pkt, addr)
        print(f"[ACK] Sent ACK for seq {self.expected_seq}")

    def run(self):
        while True:
            data, addr = self.sock.recvfrom(65535)
            seq, ack, flags, rwnd, length, csum = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
            payload = data[HEADER_SIZE:HEADER_SIZE+length]

            if flags & FLAG_SYN:
                synack = struct.pack(HEADER_FORMAT, 0, 1, FLAG_SYN | FLAG_ACK, self.rwnd, 0, checksum(b""))
                self.sock.sendto(synack, addr)
                print(f"[HANDSHAKE] SYN received, SYN+ACK sent")
                continue

            if seq == self.expected_seq:
                self.output.write(payload)
                self.expected_seq += len(payload)
                while self.expected_seq in self.buf:
                    self.output.write(self.buf[self.expected_seq])
                    del self.buf[self.expected_seq]
            else:
                self.buf[seq] = payload

            self.send_ack(addr)

            if flags & FLAG_FIN:
                self.output.close()
                print("[FIN] Transfer complete, file saved")
                return

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--role", choices=["client", "server"])
    p.add_argument("--server-ip")
    p.add_argument("--server-port", type=int)
    p.add_argument("--file")
    p.add_argument("--port", type=int)
    p.add_argument("--out")
    p.add_argument("--rwnd", type=int, default=65535)
    args = p.parse_args()

    if args.role == "client":
        c = VoyagerClient(args.server_ip, args.server_port, args.file)
        c.handshake()
        c.send_file()

    else:
        s = VoyagerServer(args.port, args.out, args.rwnd)
        s.run()
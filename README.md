# Voyager Protocol: Pipelined Reliable Transfer

## Introduction
The Voyager protocol is our custom, connection-oriented, reliable transfer protocol inspired by TCP. It is designed to provide **reliable, in-order delivery of data over UDP**. It implements:

- Three-way Handshake Connection Establishment  
- Reliable, pipelined data transfer  
- Flow Control  
- Congestion Control  
- Retransmission in case of loss or corruption  
- Connection Termination  

---

## Socket Type
Voyager uses **UDP sockets** (`AF_INET`, `SOCK_DGRAM`) as the underlying transport. UDP provides explicit control over:

- Packet sequencing  
- Acknowledgements  
- Window sizes  
- Timing  

Using these controls, we can create a protocol that provides **reliable, ordered, and flow-controlled data transfer**.  

---

## Connection Establishment (SYN → SYN+ACK → ACK)
The first step for transferring any data is to form a connection between the client and the server. Voyager does this using a **three-way handshake** inspired by TCP:

1. **SYN:** Client sends a SYN packet to request a connection.  
2. **SYN + ACK:** Server responds with a combined SYN and ACK packet.  
3. **ACK:** Client acknowledges receipt, and the connection is established.  

This ensures that both the client and the receiver have **initial sequence numbers** and are ready to transfer information.  

---

## Reliable Pipelined Data Transfer
Voyager uses a **sliding window mechanism** for pipelining:

- Sender and receiver maintain **send/expected sequence number windows**.  
- Multiple un-ACKed packets can be in transit simultaneously.  
- Receiver buffers **out-of-order packets** within the expected sequence window.  
- **Cumulative ACKs** indicate the highest in-order packet received.  
- Retransmissions occur upon **timeout** or **duplicate ACK detection**, ensuring no data loss.  

Pipelining improves throughput by **avoiding idle waiting for acknowledgements**.  

---

## Packet Header

| Field     | Size | Description                                         |
|-----------|------|-----------------------------------------------------|
| SEQ       | 4B   | Sequence number of the packet.                     |
| ACK       | 4B   | Cumulative acknowledgement number.                |
| FLAGS     | 1B   | Bitmask: SYN=1, ACK=2, FIN=4. Can combine bits.   |
| RWND      | 4B   | Receiver advertised window (flow control).         |
| LEN       | 2B   | Length of the payload in bytes.                    |
| CHECKSUM  | 16B  | First 16 bytes of the SHA-256 checksum of payload.|

---

## Flow Control
In Voyager, the receiver advertises a **receiver window** representing available buffer space. This prevents the sender from overwhelming the receiver. The **flow control module** enables the sender to:

- Dynamically adjust its window size  
- Pause transmission if the receiver window is too small  

---

## Congestion Control
Voyager implements a **TCP Reno-style congestion control**, handled in a dedicated module:

- **Slow Start:** cwnd doubles every round trip until it reaches the threshold (ssthresh).  
- **Congestion Avoidance:** cwnd grows linearly after reaching the threshold.  
- **Duplicate ACKs:** Three consecutive duplicate ACKs trigger **fast retransmit**.  

These events can be tracked through **sender logs**, which show the evolution of cwnd and retransmissions.

---

## Data Integrity and Connection Termination
- **Checksum:** Each packet includes a SHA-256 checksum (first 16 bytes). Corrupted packets are discarded, and retransmissions are triggered.  
- **Connection Termination:** A **FIN packet** is sent when all data is sent and acknowledged. The server acknowledges the FIN and closes the receive file. Transfer completion is logged in the client and server logs.  

---

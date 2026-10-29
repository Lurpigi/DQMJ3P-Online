"""NAT check server (nncs) for local Pia/NEX tests.

Before matchmaking, Pia (NatTraverser) and NEX send UDP messages to the NAT check servers
nncs1/nncs2.app.nintendowifi.net, ports 10025 and 10125, to learn the console's NAT mapping and
filtering and to predict its external ports. On a symmetric NAT (e.g. a carrier-grade NAT) the
detection gives mapping 2 / filtering 2 and the game stops with "Errore di comunicazione"
before any matchmaking call. With this server on two loopback addresses and the game patched to
use them (make_url_patch.py --nncs 127.0.0.1,127.0.0.2), the console sees an open NAT, which is
what two emulators on the same PC need.

Protocol (port of PretendoNetwork/nncs, src/server.ts): 16-byte big-endian messages
{u32 type, u32 external port, u32 external address, u32 local address}; the reply carries the
sender's address and port as seen by the server, plus the server's own address.
  1, 4, 5, 101, 103: reply from the same address and port
  2:                 reply from the other server's address (filtering test)
  3, 102:            reply from the same address but another port (filtering / port test)
Port 33334/33335 of nncs1 only receive (the client checks reachability), no reply.

usage (python -I): nncs_server.py [nncs1_address] [nncs2_address]   (default 127.0.0.1 127.0.0.2)
The two addresses must differ; on a public server they must be two public IPs.
"""
import selectors
import socket
import struct
import sys

PRIMARY_PORT = 10025
SECONDARY_PORT = 10125
SINK_PORTS = (33334, 33335)
SAME = {1, 4, 5, 101, 103}
OTHER_ADDRESS = {2}
OTHER_PORT = {3, 102}

addresses = (sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1",
             sys.argv[2] if len(sys.argv) > 2 else "127.0.0.2")
if addresses[0] == addresses[1]:
    sys.exit("nncs1 and nncs2 must use two different addresses")


def udp(address, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((address, port))
    return s


def ip_int(address):
    return struct.unpack(">I", socket.inet_aton(address))[0]


selector = selectors.DefaultSelector()
alternate = {}  # server address -> socket on a random port, for replies from another port/address
for index, address in enumerate(addresses):
    for port in (PRIMARY_PORT, SECONDARY_PORT):
        selector.register(udp(address, port), selectors.EVENT_READ, (index, True))
    alternate[index] = udp(address, 0)
for port in SINK_PORTS:
    selector.register(udp(addresses[0], port), selectors.EVENT_READ, (0, False))
print(f"nncs on {addresses[0]} and {addresses[1]}, ports {PRIMARY_PORT}/{SECONDARY_PORT}", flush=True)

while True:
    for key, _ in selector.select():
        index, answers = key.data
        try:
            message, (host, port) = key.fileobj.recvfrom(64)
        except ConnectionResetError:  # Windows reports ICMP port unreachable from an earlier send
            continue
        if not answers or len(message) < 16:
            continue
        kind = struct.unpack_from(">I", message)[0]
        reply = struct.pack(">IIII", kind, port, ip_int(host), ip_int(addresses[index]))
        if kind in SAME:
            sender = key.fileobj
        elif kind in OTHER_ADDRESS:
            sender = alternate[1 - index]
        elif kind in OTHER_PORT:
            sender = alternate[index]
        else:
            continue
        print(f"nncs{index + 1}:{key.fileobj.getsockname()[1]} type {kind} from {host}:{port}", flush=True)
        sender.sendto(reply, (host, port))

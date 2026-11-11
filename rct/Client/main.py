# python3
import zmq
import json
import time

ctx = zmq.Context()

# Replace with your game port (gNetworkStartPort). Example: 11753 is the main port, 11754 is reply port.
game_port = 11753                # portAddress1 (the game's ROUTER binds here)
reply_port = 11754               # portAddress2 (the game's DEALER will connect to this)

# Socket to send requests to the game (DEALER -> connects to game's ROUTER)
request_sock = ctx.socket(zmq.DEALER)
request_sock.connect(f"tcp://localhost:{game_port}")

# Socket to receive replies from the game (ROUTER -> game dealer connects to this)
reply_sock = ctx.socket(zmq.ROUTER)
reply_sock.bind(f"tcp://*:{reply_port}")

print("Bound router for replies on", reply_port, "and connected dealer to", game_port)

# Send a JSON request to the game
msg = {"action": "pause"}   # example action
request_sock.send_json(msg)
print("Sent request:", msg)

# Wait for reply (router returns a multipart: [identity, [maybe empty frame], payload])
while True:
    parts = reply_sock.recv_multipart()  # blocking
    # last frame is usually the payload
    payload = parts[-1]
    try:
        print("Received reply:", payload.decode())
    except Exception:
        print("Received reply (raw):", payload)
    break


import os
import subprocess
import traceback
import json

import zmq

from paths import *


class Bridge:
    game_port = 11753  # portAddress1 (the game's ROUTER binds here)
    reply_port = 11754  # portAddress2 (the game's DEALER will connect to this)

    def __init__(self, game_port):
        self.context = zmq.Context()
        self.bound = False
        self.game_port = game_port
        self.reply_port = 11754
        self.debug = True

    # This should be good?
    def connect(self):
        print("connecting bridge")

        # Socket to send requests to the game (DEALER -> connects to game's ROUTER)
        try:
            self.request_sock = self.context.socket(zmq.DEALER)
            self.request_sock.connect(f"tcp://localhost:{self.game_port}")
            print("connected to request socket on", self.game_port)
        except Exception as e:
            print("Error creating/connecting request socket. You broke it")
            traceback.print_exc()
            raise

        # Socket to receive replies from the game (ROUTER -> game dealer connects to this)
        try:
            self.reply_sock = self.context.socket(zmq.ROUTER)
            self.reply_sock.bind(f"tcp://*:{self.reply_port}")
            print("connected to reply socket on", self.reply_port)
        except Exception as e:
            print("Error creating/connecting reply socket. You broke it")
            traceback.print_exc()
            raise

        self.rcv_poller = zmq.Poller()
        self.rcv_poller.register(self.reply_sock, zmq.POLLIN)

        self.bound = True

    # Opens the game and keeps track of the process
    def start(self):
        args = [
            RCT_EXECUTABLE,
            PARK_PATH + "Leafy Lake (with path).park",
            # The original had the port but we are so hard coded here its not even funny
            # Also, im pretending that headless is not a thing
        ]
        self.rct_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Gets the console output from the game process
    def get_output(self):
        stdout, stderr = self.rct_process.communicate()

        # Just printing it for now I guess?
        print(stdout.decode())
        print(stderr.decode())

    # Not implemented yet
    def send_park(self, park_path):
        pass

    # Also probably good?
    # These actions are all defined in GameState.cpp. Search for "if (res[\"action\"] == \"unpause\")"
    # close to line 353 -ish
    def send_action(self, action, **kwargs):
        """
        Send an action (string name) with kwargs as parameters. Returns raw bytes reply.
        Keeps backwards-compatibility with the original send_action signature.
        """
        action_dict = {'action': action, **kwargs}
        result = self.send_action_dict(action_dict)
        return result

    def send_action_dict(self, action_dict, timeout_ms: int = None):
        """
        Send a full action dict (will be JSON-serialized). Returns raw bytes reply.
        Adds retry-with-exponential-backoff on TIMEOUTs to reduce crashes from transient problems.
        timeout_ms: if provided, total milliseconds to wait for a reply on each attempt; otherwise a default is chosen.
        """
        assert self.bound, "Bridge not connected"
        message = json.dumps(action_dict)
        # Configuration: environment overrides
        try:
            max_attempts = int(os.getenv('RCT_RETRY_MAX', '3'))
        except Exception:
            max_attempts = 3
        try:
            base_backoff = float(os.getenv('RCT_RETRY_BACKOFF_SEC', '0.5'))
        except Exception:
            base_backoff = 0.5

        a = action_dict.get('action')
        if a == 'run_sim':
            t = 60000
        elif a == 'load_park':
            # determine per-attempt timeout (ms)
            t = 30000  # assuming some value
        elif a == 'get_paths':
            t = 120000
        else:
            t = timeout_ms or 10000  # default
        timeout_ms = t

        # Attempt loop with exponential backoff
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                # send request
                self.request_sock.send_string(message)

                socks = dict(self.rcv_poller.poll(timeout_ms))
                if not socks:
                    if self.debug:
                        print(f"TIMEOUT waiting for reply to action {action_dict.get('action')} (attempt {attempt}/{max_attempts})")
                    # If we have more attempts left, backoff and retry
                    if attempt < max_attempts:
                        backoff = base_backoff * (2 ** (attempt - 1))
                        # small jitter
                        import random
                        jitter = random.uniform(0, backoff * 0.1)
                        sleep_time = backoff + jitter
                        if self.debug:
                            print(f"Retrying after {sleep_time:.2f}s...")
                        import time
                        time.sleep(sleep_time)
                        continue
                    else:
                        return b"TIMEOUT"

                if socks.get(self.reply_sock) == zmq.POLLIN:
                    reply = self.reply_sock.recv_multipart()[-1]
                    return reply
                else:
                    # Unexpected branch
                    if self.debug:
                        print("send_action_dict: no reply frame matched poll results; returning NO_REPLY")
                    return b"NO_REPLY"
            except zmq.ZMQError as e:
                if self.debug:
                    print(f"ZMQError on send_action_dict attempt {attempt}: {e}")
                if attempt < max_attempts:
                    import time
                    time.sleep(base_backoff)
                    continue
                return b"ZMQERROR"
            except Exception as e:
                # Unexpected exception: log and return a representation
                if self.debug:
                    print(f"Exception in send_action_dict: {e}")
                    import traceback
                    traceback.print_exc()
                return str(e).encode()

        # If all attempts failed
        return b"TIMEOUT"

    def recv_any(self, timeout_ms: int = None):
        """
        Poll the reply socket for any incoming message and return the last frame as bytes.
        If timeout_ms is None, poll indefinitely. If 0, perform a non-blocking poll.
        Returns bytes or None on timeout.
        """
        if timeout_ms is None:
            # poll indefinitely: small loop
            while True:
                socks = dict(self.rcv_poller.poll(1000))
                if socks and socks.get(self.reply_sock) == zmq.POLLIN:
                    return self.reply_sock.recv_multipart()[-1]
        else:
            socks = dict(self.rcv_poller.poll(timeout_ms))
            if socks and socks.get(self.reply_sock) == zmq.POLLIN:
                return self.reply_sock.recv_multipart()[-1]
            return None

    # Replaces capture_rct_window_to_file from original.
    # Should be implemented correctly.
    # Incredibly Mac OS only. yayyyyyy
    def capture_screenshot(self, filename):
        # Pycharm cant see this. It's good, I promise. (well, I might've fixed it, ignore if not red)
        from Quartz import CGWindowListCopyWindowInfo, kCGNullWindowID, kCGWindowListOptionAll

        window_name = 'OpenRCT2'
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionAll, kCGNullWindowID)
        for window in window_list:
            try:
                if window_name.lower() in window['kCGWindowOwnerName'].lower() and str(
                        window['kCGWindowStoreType']) == '1':
                    os.system(f"screencapture -l {window['kCGWindowNumber']} \"{filename}\"")
                    break
            except:
                pass
        else:
            raise Exception(f'Window {window_name} not found.')

    print("Bound router for replies on", reply_port, "and connected dealer to", game_port)

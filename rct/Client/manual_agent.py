"""
Manual interactive agent to act in place of the LLM.

Usage: python3 manual_agent.py

Commands (type 'help' in the prompt for full list):
 - pause             : pause the game
 - unpause           : unpause the game
 - run_month         : run until next month (calls run_sim num_ticks=-1)
 - get <action>      : e.g. get get_cash, get_num_guests, get_num_months, get_paths
 - place_path x y z queue
 - send <json>       : send a raw JSON action string, e.g. send {"action":"pause"}
 - exit / quit       : exit the interactive prompt

This keeps things simple and doesn't change any C++ code.
"""

from bridge import Bridge
import json
import shlex


def pretty_print_reply(reply_bytes):
    if reply_bytes is None:
        print("(no reply)")
        return
    try:
        text = reply_bytes.decode()
    except Exception:
        print(repr(reply_bytes))
        return
    try:
        parsed = json.loads(text)
        print(json.dumps(parsed, indent=2))
    except Exception:
        print(text)


def repl(bridge: Bridge):
    if not bridge.bound:
        bridge.connect()

    print("Manual agent REPL. Type 'help' for commands.")
    while True:
        try:
            line = input('> ').strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        parts = shlex.split(line)
        if not parts:
            continue
        cmd = parts[0].lower()

        if cmd in ('exit', 'quit'):
            break
        elif cmd == 'help':
            print("Commands:")
            print("  pause               - pause the game")
            print("  unpause             - unpause the game")
            print("  run_month           - run until next month (run_sim num_ticks=-1)")
            print("  get <action>        - e.g. get get_cash, get_num_guests, get_num_months, get_paths")
            print("  place_path x y z q  - place a path tile (x,y tiles, z height, queue 0/1)")
            print('  send <json>         - send raw JSON action, e.g. send "{\"action\": \"pause\"}"')
            print("  raw                 - enter raw JSON in multiple lines (end with a single '.' on a line)")
            print("  exit / quit         - exit")
            continue

        elif cmd == 'pause':
            r = bridge.pause()
            pretty_print_reply(r)
            continue
        elif cmd == 'unpause':
            r = bridge.unpause()
            pretty_print_reply(r)
            continue
        elif cmd == 'run_month':
            r = bridge.run_until_month()
            pretty_print_reply(r)
            continue
        elif cmd == 'get':
            if len(parts) < 2:
                print('usage: get <action>')
                continue
            action = parts[1]
            r = bridge.send_action(action)
            pretty_print_reply(r)
            continue
        elif cmd == 'place_path':
            if len(parts) < 5:
                print('usage: place_path x y z queue')
                continue
            try:
                x = int(parts[1])
                y = int(parts[2])
                z = int(parts[3])
                queue = 1 if parts[4] not in ('0', 'false', 'False') else 0
            except Exception as e:
                print('invalid numbers:', e)
                continue
            act = {"action": "place_path", "x": x, "y": y, "z": z, "queue": queue}
            r = bridge.send_action_dict(act)
            pretty_print_reply(r)
            continue
        elif cmd == 'send':
            if len(parts) < 2:
                print('usage: send <json>')
                continue
            raw = line.partition(' ')[2].strip()
            try:
                action = json.loads(raw)
            except Exception as e:
                print('Invalid JSON:', e)
                continue
            r = bridge.send_action_dict(action)
            pretty_print_reply(r)
            continue
        elif cmd == 'raw':
            print("Enter JSON (end with a single '.' on a line):")
            lines = []
            while True:
                try:
                    l = input()
                except EOFError:
                    break
                if l.strip() == '.':
                    break
                lines.append(l)
            raw = '\n'.join(lines).strip()
            try:
                action = json.loads(raw)
            except Exception as e:
                print('Invalid JSON:', e)
                continue
            r = bridge.send_action_dict(action)
            pretty_print_reply(r)
            continue
        else:
            print('Unknown command:', cmd)
            print("Type 'help' for available commands")


if __name__ == '__main__':
    b = Bridge(11753)
    repl(b)

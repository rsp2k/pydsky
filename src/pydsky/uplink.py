#!/usr/bin/env python3
"""Mission Control Uplink for pyDSKY / yaAGC.

Simulates the real Apollo ground-to-spacecraft digital uplink path.
Connects to yaAGC on a separate port (default 19698, the second client
slot) and sends keycodes via Channel 0173, triggering UPRUPT in the AGC
-- just like Houston did through the Deep Space Network.

The uplink encodes each 5-bit keycode with triple-redundant parity:
    value = keycode | ((keycode ^ 037) << 5) | (keycode << 10)
This allows the AGC to detect and correct single-bit transmission errors
via majority voting across the three copies.

Usage:
    pydsky-uplink V35E              # Lamp test via uplink
    pydsky-uplink V16N36E           # Monitor elapsed time
    pydsky-uplink --dsky V35E       # Via DSKY keyboard channel (ch 015)
    pydsky-uplink                   # Interactive mode

Alternative (no yaAGC connection needed):
    xdotool search --name pyDSKY key v 3 5 Return
"""

import argparse
import socket
import sys
import time

# 5-bit DSKY keycodes (octal, matching AGC DSKY interface spec)
KEYCODES = {
    '0': 0o20, '1': 0o01, '2': 0o02, '3': 0o03, '4': 0o04,
    '5': 0o05, '6': 0o06, '7': 0o07, '8': 0o10, '9': 0o11,
    'V': 0o21, 'N': 0o37, 'E': 0o34, 'R': 0o22,
    'C': 0o36, 'K': 0o31, '+': 0o32, '-': 0o33,
}

CHAN_UPLINK = 0o173   # Mission Control uplink → UPRUPT (interrupt 7)
CHAN_DSKY = 0o15      # DSKY keyboard → KEYRUPT (interrupt 5)

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 19698  # Second client slot (pyDSKY occupies 19697)
KEYSTROKE_DELAY = 0.2  # 200ms between keystrokes, matching yaUplinkBlock1


def form_packet(channel, value):
    """Encode a yaAGC 4-byte I/O packet.

    Packet format (MSB first within each byte):
        Byte 0: 00cccccc        channel bits 8..3
        Byte 1: 01cccvvv        channel bits 2..0, value bits 14..12
        Byte 2: 10vvvvvv        value bits 11..6
        Byte 3: 11vvvvvv        value bits 5..0

    The 2-bit headers (00/01/10/11) enable byte-level synchronization
    -- the receiver can always find packet boundaries by looking for
    the 00 sync pattern in byte 0.
    """
    return bytes([
        (channel >> 3) & 0x3F,
        0x40 | ((channel << 3) & 0x38) | ((value >> 12) & 0x07),
        0x80 | ((value >> 6) & 0x3F),
        0xC0 | (value & 0x3F),
    ])


def encode_uplink(keycode):
    """Triple-redundant encoding for Channel 0173.

    Packs three copies of the 5-bit keycode into a 15-bit value:
        bits 14..10: keycode (original)
        bits  9.. 5: keycode ^ 037 (inverted)
        bits  4.. 0: keycode (duplicate)
    """
    keycode &= 0o37
    return keycode | ((keycode ^ 0o37) << 5) | (keycode << 10)


def parse_command(text):
    """Parse a command string like 'V35E' into a list of (name, keycode) tuples."""
    keys = []
    unknown = []
    for ch in text.upper():
        if ch in KEYCODES:
            keys.append((ch, KEYCODES[ch]))
        elif ch == 'P':
            keys.append(('P', None))
        elif ch in (' ', '\t'):
            continue
        else:
            unknown.append(ch)
    if unknown:
        print(f"Unknown keys ignored: {' '.join(repr(c) for c in unknown)}", file=sys.stderr)
    return keys


def send_keys(sock, keys, channel, delay):
    """Send a sequence of keycodes to yaAGC.

    Raises ConnectionError if the socket fails mid-sequence.
    """
    for i, (name, keycode) in enumerate(keys):
        try:
            if keycode is None:
                if channel == CHAN_DSKY:
                    # PRO button: press then release (compound packet pair)
                    sock.sendall(
                        form_packet(0o432, 0o20000) + form_packet(0o32, 0o20000)
                    )
                    time.sleep(delay)
                    sock.sendall(
                        form_packet(0o432, 0o20000) + form_packet(0o32, 0)
                    )
                    print("  P → PRO (press+release)")
                else:
                    print("  P → PRO not available via uplink channel", file=sys.stderr)
                continue

            if channel == CHAN_UPLINK:
                value = encode_uplink(keycode)
            else:
                value = keycode

            sock.sendall(form_packet(channel, value))
            print(f"  {name} → ch {channel:04o} val {value:06o}")

        except (socket.timeout, BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"  {name} → FAILED: {e}", file=sys.stderr)
            raise ConnectionError(f"Lost connection sending '{name}'") from e

        if i < len(keys) - 1:
            time.sleep(delay)


def interactive(sock, channel, delay):
    """Interactive REPL for sending command sequences."""
    print("Type command sequences (e.g. V35E), 'q' to quit.")
    while True:
        try:
            line = input("uplink> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        line = line.strip()
        if not line or line.lower() == 'q':
            break
        keys = parse_command(line)
        if keys:
            try:
                send_keys(sock, keys, channel, delay)
            except ConnectionError as e:
                print(f"Connection lost: {e}", file=sys.stderr)
                break


def main():
    ap = argparse.ArgumentParser(
        description='Mission Control uplink for yaAGC / pyDSKY',
        epilog=(
            'examples:\n'
            '  pydsky-uplink V35E              lamp test via ground uplink\n'
            '  pydsky-uplink V16N36E           monitor AGC elapsed time\n'
            '  pydsky-uplink R                  reset\n'
            '  pydsky-uplink --dsky V35E       via DSKY keyboard channel\n'
            '  pydsky-uplink                   interactive mode\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('command', nargs='*', help='Key sequence (e.g. V35E)')
    ap.add_argument('--host', default=DEFAULT_HOST)
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument(
        '--dsky', action='store_true',
        help='Use Channel 015 (second DSKY keyboard) instead of Channel 0173 (uplink)',
    )
    ap.add_argument(
        '--delay', type=float, default=KEYSTROKE_DELAY,
        help=f'Seconds between keystrokes (default: {KEYSTROKE_DELAY})',
    )
    args = ap.parse_args()

    channel = CHAN_DSKY if args.dsky else CHAN_UPLINK
    mode = "DSKY keyboard (ch 015)" if args.dsky else "ground uplink (ch 0173)"

    try:
        sock = socket.create_connection((args.host, args.port), timeout=5)
    except ConnectionRefusedError:
        print(f"Connection refused: {args.host}:{args.port}", file=sys.stderr)
        print(
            "Is yaAGC running? pyDSKY must connect first (it takes port 19697).",
            file=sys.stderr,
        )
        sys.exit(1)
    except OSError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    sock.settimeout(5.0)
    print(f"Connected to yaAGC at {args.host}:{args.port} [{mode}]")

    try:
        if args.command:
            keys = parse_command(' '.join(args.command))
            if keys:
                send_keys(sock, keys, channel, args.delay)
        else:
            interactive(sock, channel, args.delay)
    except ConnectionError as e:
        print(f"Aborted: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        sock.close()


if __name__ == '__main__':
    main()

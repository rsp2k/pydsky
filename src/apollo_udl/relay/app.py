"""Apollo UDL Network Relay -- application entry point.

Starts the asyncio relay server in a daemon thread and launches
the Qt-based Mission Control panel in the main thread.
"""

import argparse
import asyncio
import logging
import sys
import threading

from qtpy.QtWidgets import QApplication

from .server import RelayServer, DEFAULT_CM_PORT, DEFAULT_LM_PORT, DEFAULT_RELAY_PORT
from .panel import RelayPanel


def _valid_port(value):
    port = int(value)
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError(f"Port must be 1-65535, got {port}")
    return port


def main():
    ap = argparse.ArgumentParser(
        description="Apollo UDL Network Relay with Mission Control panel"
    )
    ap.add_argument(
        "--cm-host", default="localhost", help="CM yaAGC host (default: localhost)"
    )
    ap.add_argument(
        "--cm-port",
        type=_valid_port,
        default=DEFAULT_CM_PORT,
        help=f"CM yaAGC port (default: {DEFAULT_CM_PORT})",
    )
    ap.add_argument(
        "--lm-host", default="localhost", help="LM yaAGC host (default: localhost)"
    )
    ap.add_argument(
        "--lm-port",
        type=_valid_port,
        default=DEFAULT_LM_PORT,
        help=f"LM yaAGC port (default: {DEFAULT_LM_PORT})",
    )
    ap.add_argument(
        "--port",
        type=_valid_port,
        default=DEFAULT_RELAY_PORT,
        help=f"Relay listen port for ground clients (default: {DEFAULT_RELAY_PORT})",
    )
    ap.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    relay = RelayServer(
        cm_host=args.cm_host,
        cm_port=args.cm_port,
        lm_host=args.lm_host,
        lm_port=args.lm_port,
        relay_port=args.port,
    )

    # Create a dedicated event loop for the relay thread so we can
    # signal it to stop gracefully when the GUI closes.
    loop = asyncio.new_event_loop()

    def run_relay():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(relay.run())

    thread = threading.Thread(target=run_relay, daemon=True, name="relay-server")
    thread.start()

    app = QApplication(sys.argv)
    panel = RelayPanel(relay)
    panel.show()
    ret = app.exec()

    # Signal graceful shutdown of the asyncio loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2.0)
    sys.exit(ret)


if __name__ == "__main__":
    main()

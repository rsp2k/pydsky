"""Apollo UDL relay server -- multiplexes yaAGC connections to ground clients.

Threading model
---------------
- The asyncio event loop runs in a daemon thread.
- ``_on_vehicle_data``, ``_handle_ground_client``, and ``_do_select_vehicle``
  all execute on the asyncio loop and are cooperatively serialized.
- ``status()`` and ``drain_events()`` are called from the Qt main thread.
  They read simple attributes (bool/int/str) which are atomic under CPython's
  GIL.  The returned dict is an *approximate* snapshot -- values may reflect
  different moments within a single polling cycle.
- ``select_vehicle()`` is called from the Qt main thread.  It schedules the
  actual mutation on the asyncio loop via ``call_soon_threadsafe``.
"""

import asyncio
import logging
from collections import deque
from time import time

from .vehicles import VehicleConnection

log = logging.getLogger(__name__)

DEFAULT_RELAY_PORT = 19900
DEFAULT_CM_PORT = 19697
DEFAULT_LM_PORT = 19797

# Drop ground clients whose write buffer exceeds this (64 KB)
WRITE_BUFFER_LIMIT = 64 * 1024


class RelayServer:
    """Asyncio relay that bridges two yaAGC instances to multiple ground clients.

    yaAGC only accepts one TCP client per port, so the relay connects once
    to each vehicle (CM/LM) and fans out to all ground peripherals (pyDSKY,
    yaTelecom, Test Set, etc.) on a single relay port.
    """

    def __init__(
        self,
        *,
        cm_host="localhost",
        cm_port=DEFAULT_CM_PORT,
        lm_host="localhost",
        lm_port=DEFAULT_LM_PORT,
        relay_port=DEFAULT_RELAY_PORT,
    ):
        self._relay_port = relay_port
        self._active_vehicle = "CM"
        self._total_routed = 0
        self._ground_writers = set()
        self._ground_client_count = 0
        self._next_client_id = 1
        self._events = deque(maxlen=200)
        self._loop = None

        self._cm = VehicleConnection(
            "CM",
            cm_host,
            cm_port,
            on_connected=self._on_vehicle_connected,
            on_disconnected=self._on_vehicle_disconnected,
            on_data=self._on_vehicle_data,
        )
        self._lm = VehicleConnection(
            "LM",
            lm_host,
            lm_port,
            on_connected=self._on_vehicle_connected,
            on_disconnected=self._on_vehicle_disconnected,
            on_data=self._on_vehicle_data,
        )
        self._vehicles = {"CM": self._cm, "LM": self._lm}

    # ── public API (called from Qt thread) ────────────────────

    def status(self):
        """Approximate snapshot of relay state.

        Safe to call from any thread.  Individual attribute reads are
        atomic under CPython's GIL, but the returned dict may reflect
        values from slightly different points in time.
        """
        return {
            "cm": {
                "connected": self._cm.connected,
                "host": self._cm.host,
                "port": self._cm.port,
                "rx": self._cm.rx_count,
                "tx": self._cm.tx_count,
            },
            "lm": {
                "connected": self._lm.connected,
                "host": self._lm.host,
                "port": self._lm.port,
                "rx": self._lm.rx_count,
                "tx": self._lm.tx_count,
            },
            "active_vehicle": self._active_vehicle,
            "ground_clients": self._ground_client_count,
            "total_routed": self._total_routed,
        }

    def select_vehicle(self, name):
        """Switch active vehicle.  Thread-safe: schedules on the asyncio loop."""
        name = name.upper()
        if name not in self._vehicles:
            return
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._do_select_vehicle, name)

    def drain_events(self):
        """Pop all queued events.  Thread-safe (deque ops are atomic in CPython)."""
        events = []
        while self._events:
            try:
                events.append(self._events.popleft())
            except IndexError:
                break
        return events

    # ── asyncio entry point ───────────────────────────────────

    async def run(self):
        """Start vehicle connections and ground-client server.  Blocks forever."""
        self._loop = asyncio.get_running_loop()

        server = await asyncio.start_server(
            self._handle_ground_client, "0.0.0.0", self._relay_port
        )
        self._emit(f"Relay listening on port {self._relay_port}")

        cm_task = asyncio.create_task(self._cm.run())
        lm_task = asyncio.create_task(self._lm.run())

        async with server:
            await asyncio.gather(cm_task, lm_task, server.serve_forever())

    # ── vehicle callbacks (asyncio thread) ────────────────────

    def _on_vehicle_connected(self, name):
        self._emit(f"{name} connected to yaAGC")

    def _on_vehicle_disconnected(self, name):
        self._emit(f"{name} disconnected from yaAGC")

    def _on_vehicle_data(self, name, data):
        """Forward data from the active vehicle to all ground clients.

        Called synchronously from VehicleConnection._read_loop on the
        asyncio thread.  ground_writers is only mutated on this same
        thread (cooperatively serialized), so iteration is safe.
        """
        if name != self._active_vehicle:
            return
        stale = []
        for writer in list(self._ground_writers):
            try:
                buf_size = writer.transport.get_write_buffer_size()
                if buf_size > WRITE_BUFFER_LIMIT:
                    log.warning("Ground client buffer overflow (%d bytes), dropping", buf_size)
                    stale.append(writer)
                    continue
                writer.write(data)
            except (ConnectionError, OSError) as exc:
                log.debug("Ground client write failed: %s", exc)
                stale.append(writer)
        for w in stale:
            self._ground_writers.discard(w)
        if stale:
            self._ground_client_count = len(self._ground_writers)
        self._total_routed += len(data) // 4

    def _do_select_vehicle(self, name):
        """Perform vehicle switch on the asyncio thread."""
        old = self._active_vehicle
        if old != name:
            self._active_vehicle = name
            self._emit(f"Vehicle select: {old} \u2192 {name}")

    # ── ground client handling (asyncio thread) ───────────────

    async def _handle_ground_client(self, reader, writer):
        addr = writer.get_extra_info("peername") or ("unknown", 0)
        cid = self._next_client_id
        self._next_client_id += 1

        self._ground_writers.add(writer)
        self._ground_client_count = len(self._ground_writers)
        self._emit(f"Ground client #{cid} connected from {addr[0]}:{addr[1]}")

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                vehicle = self._vehicles.get(self._active_vehicle)
                if vehicle and vehicle.connected:
                    vehicle.send(data)
                    self._total_routed += len(data) // 4
        except (ConnectionError, OSError):
            pass
        finally:
            self._ground_writers.discard(writer)
            self._ground_client_count = len(self._ground_writers)
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass
            self._emit(f"Ground client #{cid} disconnected")

    # ── event buffer ──────────────────────────────────────────

    def _emit(self, msg):
        self._events.append((time(), msg))
        log.info(msg)

"""Apollo UDL relay server -- multiplexes yaAGC connections to ground clients.

Threading model
---------------
- The asyncio event loop runs in a daemon thread.
- ``_on_vehicle_data``, ``_handle_ground_client``, and all ``_do_*`` methods
  execute on the asyncio loop and are cooperatively serialized.
- ``status()`` and ``drain_events()`` are called from the Qt main thread.
  They read simple attributes (bool/int/str) which are atomic under CPython's
  GIL.  The returned dict is an *approximate* snapshot -- values may reflect
  different moments within a single polling cycle.
- ``enable_vehicle()``, ``disable_vehicle()``, ``set_uplink_target()``, and
  ``set_client_filter()`` are called from the Qt main thread.  They schedule
  the actual mutation on the asyncio loop via ``call_soon_threadsafe``.

Routing model
-------------
- **Downlink** (yaAGC → ground): data from each *enabled* vehicle is broadcast
  to ground clients whose per-client filter permits it.  The global vehicle
  enable toggles are checked first; then the per-client filter is applied.
- **Uplink** (ground → yaAGC): data from ground clients is forwarded only to the
  designated *uplink target* vehicle.
- **Per-client filtering**: three relay ports assign default filters:

  - Base port (19900): ALL -- receives both CM and LM data
  - Base+1 (19901):    CM  -- receives CM data only
  - Base+2 (19902):    LM  -- receives LM data only

  The operator can override any client's filter from the panel.
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

# Per-client downlink filter values
FILTER_ALL = "ALL"
FILTER_CM = "CM"
FILTER_LM = "LM"
FILTER_CYCLE = [FILTER_ALL, FILTER_CM, FILTER_LM]

# Drop ground clients whose write buffer exceeds this (64 KB)
WRITE_BUFFER_LIMIT = 64 * 1024

MAX_GROUND_CLIENTS = 6


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
        self._uplink_target = "CM"
        self._cm_enabled = True
        self._lm_enabled = True
        self._total_routed = 0

        # Per-client tracking: cid → {writer, filter, addr}
        # Mutated only on the asyncio thread.
        self._ground_clients = {}
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

        ``ground_clients`` is a list of dicts (one per connected client)
        with keys: ``cid``, ``filter``, ``addr``.
        """
        # Snapshot the dict to avoid RuntimeError from concurrent mutation
        # on the asyncio thread (dict.items() returns a lazy view).
        clients = [
            {"cid": cid, "filter": info["filter"], "addr": info["addr"]}
            for cid, info in list(self._ground_clients.items())
        ]
        return {
            "cm": {
                "connected": self._cm.connected,
                "enabled": self._cm_enabled,
                "host": self._cm.host,
                "port": self._cm.port,
                "rx": self._cm.rx_count,
                "tx": self._cm.tx_count,
            },
            "lm": {
                "connected": self._lm.connected,
                "enabled": self._lm_enabled,
                "host": self._lm.host,
                "port": self._lm.port,
                "rx": self._lm.rx_count,
                "tx": self._lm.tx_count,
            },
            "uplink_target": self._uplink_target,
            "ground_clients": clients,
            "total_routed": self._total_routed,
        }

    def enable_vehicle(self, name):
        """Enable a vehicle's downlink.  Thread-safe."""
        name = name.upper()
        if name in self._vehicles and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._do_enable_vehicle, name)

    def disable_vehicle(self, name):
        """Disable a vehicle's downlink.  Thread-safe."""
        name = name.upper()
        if name in self._vehicles and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._do_disable_vehicle, name)

    def set_uplink_target(self, name):
        """Set the uplink target vehicle.  Thread-safe."""
        name = name.upper()
        if name in self._vehicles and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._do_set_uplink_target, name)

    def set_client_filter(self, cid, vehicle_filter):
        """Set a ground client's downlink filter.  Thread-safe."""
        if vehicle_filter in FILTER_CYCLE and self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(
                self._do_set_client_filter, cid, vehicle_filter
            )

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
        """Start vehicle connections and ground-client servers.  Blocks forever."""
        self._loop = asyncio.get_running_loop()

        def _make_handler(default_filter):
            async def handler(reader, writer):
                await self._handle_ground_client(reader, writer, default_filter)
            return handler

        all_srv = await asyncio.start_server(
            _make_handler(FILTER_ALL), "0.0.0.0", self._relay_port
        )
        cm_srv = await asyncio.start_server(
            _make_handler(FILTER_CM), "0.0.0.0", self._relay_port + 1
        )
        lm_srv = await asyncio.start_server(
            _make_handler(FILTER_LM), "0.0.0.0", self._relay_port + 2
        )
        self._emit(
            f"Relay listening: {self._relay_port} (ALL), "
            f"{self._relay_port + 1} (CM), {self._relay_port + 2} (LM)"
        )

        cm_task = asyncio.create_task(self._cm.run())
        lm_task = asyncio.create_task(self._lm.run())

        async with all_srv, cm_srv, lm_srv:
            await asyncio.gather(
                cm_task, lm_task,
                all_srv.serve_forever(),
                cm_srv.serve_forever(),
                lm_srv.serve_forever(),
            )

    # ── vehicle callbacks (asyncio thread) ────────────────────

    def _on_vehicle_connected(self, name):
        self._emit(f"{name} connected to yaAGC")

    def _on_vehicle_disconnected(self, name):
        self._emit(f"{name} disconnected from yaAGC")

    def _is_vehicle_enabled(self, name):
        if name == "CM":
            return self._cm_enabled
        return self._lm_enabled

    def _on_vehicle_data(self, name, data):
        """Forward data from enabled vehicles to filtered ground clients.

        Called synchronously from VehicleConnection._read_loop on the
        asyncio thread.  _ground_clients is only mutated on this same
        thread (cooperatively serialized), so iteration is safe.

        Two-stage filter:
        1. Global vehicle enable -- if the vehicle is disabled, nobody gets it.
        2. Per-client filter -- ALL passes everything, CM/LM passes only that vehicle.
        """
        if not self._is_vehicle_enabled(name):
            return
        stale = []
        sent = False
        for cid, info in list(self._ground_clients.items()):
            # Per-client filter check
            cf = info["filter"]
            if cf != FILTER_ALL and cf != name:
                continue
            writer = info["writer"]
            try:
                buf_size = writer.transport.get_write_buffer_size()
                if buf_size > WRITE_BUFFER_LIMIT:
                    log.warning("Client #%d buffer overflow (%d bytes), dropping", cid, buf_size)
                    stale.append(cid)
                    continue
                writer.write(data)
                sent = True
            except (ConnectionError, OSError) as exc:
                log.debug("Client #%d write failed: %s", cid, exc)
                stale.append(cid)
        for cid in stale:
            self._ground_clients.pop(cid, None)
        if sent:
            self._total_routed += len(data) // 4

    def _do_enable_vehicle(self, name):
        if name == "CM" and not self._cm_enabled:
            self._cm_enabled = True
            self._emit(f"{name} downlink enabled")
        elif name == "LM" and not self._lm_enabled:
            self._lm_enabled = True
            self._emit(f"{name} downlink enabled")

    def _do_disable_vehicle(self, name):
        if name == "CM" and self._cm_enabled:
            self._cm_enabled = False
            self._emit(f"{name} downlink disabled")
        elif name == "LM" and self._lm_enabled:
            self._lm_enabled = False
            self._emit(f"{name} downlink disabled")

    def _do_set_uplink_target(self, name):
        old = self._uplink_target
        if old != name:
            self._uplink_target = name
            self._emit(f"Uplink target: {old} \u2192 {name}")

    def _do_set_client_filter(self, cid, vehicle_filter):
        info = self._ground_clients.get(cid)
        if info and info["filter"] != vehicle_filter:
            old = info["filter"]
            info["filter"] = vehicle_filter
            self._emit(f"Client #{cid} filter: {old} \u2192 {vehicle_filter}")

    # ── ground client handling (asyncio thread) ───────────────

    async def _handle_ground_client(self, reader, writer, default_filter):
        addr = writer.get_extra_info("peername") or ("unknown", 0)

        if len(self._ground_clients) >= MAX_GROUND_CLIENTS:
            log.warning("Max ground clients (%d) reached, rejecting %s:%s",
                        MAX_GROUND_CLIENTS, addr[0], addr[1])
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                pass
            return

        cid = self._next_client_id
        self._next_client_id += 1

        self._ground_clients[cid] = {
            "writer": writer,
            "filter": default_filter,
            "addr": f"{addr[0]}:{addr[1]}",
        }
        self._emit(
            f"Ground client #{cid} connected from {addr[0]}:{addr[1]} "
            f"[filter: {default_filter}]"
        )

        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                vehicle = self._vehicles.get(self._uplink_target)
                if vehicle and vehicle.connected:
                    vehicle.send(data)
                    self._total_routed += len(data) // 4
        except (ConnectionError, OSError):
            pass
        finally:
            self._ground_clients.pop(cid, None)
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

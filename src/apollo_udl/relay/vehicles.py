"""Vehicle connection handler -- persistent asyncio TCP link to a yaAGC instance."""

import asyncio
import logging

log = logging.getLogger(__name__)

RECONNECT_DELAY = 2.0


class VehicleConnection:
    """Maintain a single connection to yaAGC (CM or LM) with auto-reconnect.

    The yaAGC protocol streams 4-byte packets with sync markers in the
    top two bits of each byte (00, 01, 10, 11).  This class forwards raw
    bytes transparently and counts well-framed packets for telemetry.

    Threading: all methods except ``stop()`` run on the asyncio event loop.
    ``stop()`` may be called from any thread.
    """

    def __init__(
        self,
        name,
        host,
        port,
        *,
        on_connected=None,
        on_disconnected=None,
        on_data=None,
    ):
        self.name = name
        self.host = host
        self.port = port
        self.connected = False
        self.rx_count = 0
        self.tx_count = 0

        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_data = on_data

        self._reader = None
        self._writer = None
        self._running = False
        self._rx_frame_idx = 0
        self._tx_frame_idx = 0

    # ── lifecycle ──────────────────────────────────────────────

    async def run(self):
        """Connect-read-reconnect loop.  Runs until stop() is called."""
        self._running = True
        while self._running:
            try:
                await self._connect()
                await self._read_loop()
            except (ConnectionError, OSError, asyncio.IncompleteReadError) as exc:
                log.warning("%s: %s", self.name, exc)
            finally:
                self._disconnect()
            if self._running:
                await asyncio.sleep(RECONNECT_DELAY)

    def stop(self):
        self._running = False
        if self._writer:
            try:
                self._writer.close()
            except OSError:
                pass

    # ── send data to yaAGC ────────────────────────────────────

    def send(self, data):
        """Buffer data for transmission to yaAGC (sync, non-blocking).

        Returns True if the write was buffered, False if not connected
        or the write failed.
        """
        if not (self._writer and self.connected):
            return False
        try:
            self._writer.write(data)
            self.tx_count += self._count_packets(data, tx=True)
            return True
        except (ConnectionError, OSError) as exc:
            log.warning("%s: uplink write failed: %s", self.name, exc)
            return False

    # ── internals ─────────────────────────────────────────────

    async def _connect(self):
        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        self.connected = True
        self._rx_frame_idx = 0
        self._tx_frame_idx = 0
        log.info("%s connected to yaAGC at %s:%d", self.name, self.host, self.port)
        if self._on_connected:
            self._on_connected(self.name)

    def _disconnect(self):
        was_connected = self.connected
        self.connected = False
        if self._writer:
            try:
                self._writer.close()
            except OSError:
                pass
            self._writer = None
        self._reader = None
        if was_connected:
            log.info("%s disconnected from yaAGC", self.name)
            if self._on_disconnected:
                self._on_disconnected(self.name)

    async def _read_loop(self):
        while self._running:
            data = await self._reader.read(4096)
            if not data:
                raise ConnectionError(f"{self.name} EOF from yaAGC")
            self.rx_count += self._count_packets(data, tx=False)
            if self._on_data:
                self._on_data(self.name, data)

    def _count_packets(self, data, *, tx=False):
        """Count complete 4-byte yaAGC packets using sync-byte framing.

        RX and TX maintain separate framing state so a reconnect or partial
        write in one direction doesn't corrupt the other's count.
        """
        count = 0
        idx = self._tx_frame_idx if tx else self._rx_frame_idx
        for b in data:
            expected = idx << 6
            if (b & 0xC0) == 0:
                idx = 1
            elif (b & 0xC0) == expected:
                idx += 1
                if idx == 4:
                    count += 1
                    idx = 0
            else:
                idx = 0
        if tx:
            self._tx_frame_idx = idx
        else:
            self._rx_frame_idx = idx
        return count

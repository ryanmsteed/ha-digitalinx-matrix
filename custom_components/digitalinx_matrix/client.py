"""TCP client for Liberty DigitaLinx DL-S42-H2 HDMI Matrix."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .const import COMMAND_TERMINATOR, DEFAULT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class DigitaLinxConnectionError(Exception):
    """Error connecting to the matrix switcher."""


class DigitaLinxClient:
    """Async TCP client for the DigitaLinx DL-S42-H2 matrix switcher.

    The DL-S42-H2 uses a simple ASCII protocol over TCP port 23 (telnet).
    Commands are terminated with CR+LF. Responses are also CR+LF terminated.

    Protocol reference (from DL-S42-H2 Owner's Manual):
      Video Switching:
        SET SW in{1-4} out{1-2}   -> SW in{i} out{o}
        GET SW out{1-2}           -> SW in{i} out{o}
      System:
        GET VER                    -> VER x.x
        REBOOT                     -> REBOOT
        RESET                      -> RESET

    Connection handling:
      * The socket is kept open between commands, but it is validated before
        every command (a peer-closed socket is detected via the reader's EOF).
      * If a command fails because the socket was stale or dropped, the client
        reconnects and retries the command once before giving up.
      * ``available`` reflects whether the last exchange with the matrix
        succeeded. It flips back to True on its own as soon as any command
        (including the periodic keepalive) succeeds again.
    """

    _ATTEMPTS = 2  # first try + one reconnect-and-retry

    def __init__(self, host: str, port: int, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._available = False
        self._listeners: list[Callable[[], None]] = []

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    @property
    def connected(self) -> bool:
        """Return True if the socket looks usable.

        ``is_closing()`` alone misses the case where the matrix closed an idle
        session with a FIN: the transport stays open (half-closed) but the
        reader has seen EOF. Check both.
        """
        return (
            self._writer is not None
            and self._reader is not None
            and not self._writer.is_closing()
            and not self._reader.at_eof()
        )

    @property
    def available(self) -> bool:
        """Return True if the last exchange with the matrix succeeded."""
        return self._available

    def add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired when ``available`` changes.

        Returns a function that removes the listener.
        """
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def _set_available(self, value: bool) -> None:
        """Update availability and notify listeners on change."""
        if value == self._available:
            return
        self._available = value
        if value:
            _LOGGER.info("DigitaLinx matrix at %s is available again", self._host)
        else:
            _LOGGER.warning("DigitaLinx matrix at %s is unavailable", self._host)
        for callback in list(self._listeners):
            callback()

    async def connect(self) -> None:
        """Establish TCP connection to the matrix switcher."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
            _LOGGER.debug("Connected to DigitaLinx matrix at %s:%s", self._host, self._port)
            # Some telnet implementations send a banner/greeting; drain it
            await self._drain_buffer()
        except (OSError, asyncio.TimeoutError) as err:
            await self._close()
            raise DigitaLinxConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err
        self._set_available(True)

    async def _close(self) -> None:
        """Close the socket quietly (no availability change)."""
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, asyncio.TimeoutError):
                pass
            _LOGGER.debug("Closed connection to DigitaLinx matrix at %s", self._host)

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        await self._close()

    async def _drain_buffer(self) -> None:
        """Read and discard any pending data in the buffer."""
        if self._reader is None:
            return
        try:
            while True:
                data = await asyncio.wait_for(
                    self._reader.read(1024), timeout=0.5
                )
                if not data:
                    break
        except asyncio.TimeoutError:
            pass  # No more data to drain

    async def _exchange(self, command: str) -> str:
        """Write one command on the current socket and read its response.

        Raises OSError / TimeoutError on a broken socket, including when the
        matrix has closed the connection (EOF), so the caller can reconnect.
        """
        assert self._reader is not None
        assert self._writer is not None

        full_command = command + COMMAND_TERMINATOR
        _LOGGER.debug("Sending command: %s", command)

        self._writer.write(full_command.encode("ascii"))
        await asyncio.wait_for(self._writer.drain(), timeout=self._timeout)

        # The device may echo back the command, then send a response.
        # When no route is active, GET SW just echoes with no further
        # response (observed on firmware 3.6). We read lines until
        # timeout and separate echoes from real responses.
        cmd_upper = command.strip().upper()
        for _ in range(5):  # Max lines to read
            try:
                raw = await asyncio.wait_for(
                    self._reader.readline(), timeout=self._timeout
                )
            except asyncio.TimeoutError:
                break  # echo-only reply; not an error

            if not raw:
                # readline() returns b"" only at EOF: the matrix hung up.
                raise ConnectionResetError("matrix closed the connection")

            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue

            _LOGGER.debug("Received: %s", line)

            # Skip lines that are just the echoed command
            if line.upper() == cmd_upper:
                continue

            # Got a non-echo response, we're done
            return line

        return ""

    async def _send_command(self, command: str) -> str:
        """Send a command, reconnecting and retrying once if the socket is bad.

        On final failure, marks the client unavailable and raises
        DigitaLinxConnectionError.
        """
        async with self._lock:
            last_err: Exception | None = None
            for attempt in range(1, self._ATTEMPTS + 1):
                try:
                    if not self.connected:
                        await self._close()
                        await self.connect()
                    response = await self._exchange(command)
                except (DigitaLinxConnectionError, OSError, asyncio.TimeoutError) as err:
                    last_err = err
                    _LOGGER.debug(
                        "Command %r failed on attempt %s/%s: %s",
                        command,
                        attempt,
                        self._ATTEMPTS,
                        err,
                    )
                    await self._close()
                    continue

                self._set_available(True)
                return response

            self._set_available(False)
            _LOGGER.error("Communication error with %s: %s", self._host, last_err)
            raise DigitaLinxConnectionError(
                f"Communication error: {last_err}"
            ) from last_err

    async def set_switch(self, input_num: int, output_num: int) -> str:
        """Route an HDMI input to an output.

        Args:
            input_num: Input number (1-4)
            output_num: Output number (1-2)

        Returns:
            Response string from the device.
        """
        cmd = f"SET SW in{input_num} out{output_num}"
        return await self._send_command(cmd)

    async def get_version(self) -> str:
        """Query the firmware version (also used as a keepalive)."""
        return await self._send_command("GET VER")

    async def reboot(self) -> str:
        """Reboot the device."""
        return await self._send_command("REBOOT")

    @staticmethod
    def parse_switch_response(response: str) -> int | None:
        """Parse a switch confirmation response.

        Expected format: "SW in{i} out{o}" (returned after SET SW).
        """
        if not response:
            return None
        try:
            lower = response.lower()
            for part in lower.split():
                if part.startswith("in") and part[2:].isdigit():
                    return int(part[2:])
        except (ValueError, IndexError):
            pass
        _LOGGER.warning("Could not parse switch response: %s", response)
        return None

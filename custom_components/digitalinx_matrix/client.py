"""TCP client for Liberty DigitaLinx DL-S42-H2 HDMI Matrix."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

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
    """

    def __init__(self, host: str, port: int, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    @property
    def connected(self) -> bool:
        """Return True if connected."""
        return self._writer is not None and not self._writer.is_closing()

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
            raise DigitaLinxConnectionError(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._writer = None
                self._reader = None
            _LOGGER.debug("Disconnected from DigitaLinx matrix at %s", self._host)

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

    async def _send_command(self, command: str) -> str:
        """Send a command and return the response.

        The DL-S42-H2 expects ASCII commands terminated with CR+LF
        and responds with ASCII terminated with CR+LF.
        """
        async with self._lock:
            if not self.connected:
                await self.connect()

            assert self._reader is not None
            assert self._writer is not None

            full_command = command + COMMAND_TERMINATOR
            _LOGGER.debug("Sending command: %s", command)

            try:
                self._writer.write(full_command.encode("ascii"))
                await self._writer.drain()

                # The device may echo back the command, then send a response.
                # When no route is active, GET SW just echoes with no further
                # response (observed on firmware 3.6). We read lines until
                # timeout and separate echoes from real responses.
                cmd_upper = command.strip().upper()
                response_lines: list[str] = []
                for _ in range(5):  # Max lines to read
                    try:
                        raw = await asyncio.wait_for(
                            self._reader.readline(), timeout=self._timeout
                        )
                    except asyncio.TimeoutError:
                        break

                    if not raw:
                        break

                    line = raw.decode("ascii", errors="ignore").strip()
                    if not line:
                        continue

                    _LOGGER.debug("Received: %s", line)

                    # Skip lines that are just the echoed command
                    if line.strip().upper() == cmd_upper:
                        continue

                    response_lines.append(line)
                    # Got a non-echo response, we're done
                    break

                # Return the real response, or empty string if only echo
                return response_lines[0] if response_lines else ""

            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.error("Communication error with %s: %s", self._host, err)
                await self.disconnect()
                raise DigitaLinxConnectionError(
                    f"Communication error: {err}"
                ) from err

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
        """Query the firmware version."""
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

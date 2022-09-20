"""X728 Battery module"""
from types import TracebackType
import typing
import struct
import smbus

from asyncio import AbstractEventLoop, Lock
# I2C
BATTERY_I2C_ADDR = 0x36
BATTERY_REGISTER = 2
CAPACITY_REGISTER = 4
BUS_ID = 1


class X728Battery:
    """
    Communication with the I2C battery measurment chip
    """

    def __init__(self, loop: AbstractEventLoop) -> None:
        self._smbus: smbus.SMBus = None
        self._loop = loop
        self._lock = Lock()

    def _open(self) -> None:
        self._smbus = smbus.SMBus(BUS_ID)

    def _close(self) -> None:
        self._smbus.close()

    async def connect(self) -> None:
        self._loop.run_in_executor(None, self._open)

    async def close(self) -> None:
        self._loop.run_in_executor(None, self._close)

    async def get(self) -> typing.Tuple[float, float]:
        capacity = await self._capacity()
        voltage = await self._voltage()
        return (voltage, capacity)

    async def _voltage(self) -> float:
        word = await self._i2c_read_word(BATTERY_REGISTER)
        return round(word * 1.25 / 1000 / 16, 2)

    async def _capacity(self) -> float:
        word = await self._i2c_read_word(CAPACITY_REGISTER)
        return round(word / 256, 2)

    async def _i2c_read_word(self, register: int) -> int:
        await self._lock.acquire()
        try:
            result = await self._loop.run_in_executor(None, self._smbus.read_word_data, BATTERY_I2C_ADDR, register)
        finally:
            self._lock.release()

        return struct.unpack("<H", struct.pack(">H", result))[0]

    async def __aenter__(self) -> "X728Battery":
        """Connect to the Bus."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: typing.Optional[typing.Type[BaseException]],
        exc: typing.Optional[BaseException],
        tb: typing.Optional[TracebackType],
    ) -> None:
        await self.close()

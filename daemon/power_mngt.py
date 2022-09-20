"""X728 Power Management"""
import asyncio
import logging
import time
from RPi import GPIO

from typing import Final, Callable, Awaitable, Optional, Type
from types import TracebackType

from daemon.constants import AcPower, ShutDownCmd

_LOGGER: Final[logging.Logger] = logging.getLogger("x728.daemon.power")

# GPIO Pins
GPIO_POWERLOSS_PIN = 6
GPIO_SOFT_BUTTON_PIN = 26
GPIO_PHYSICAL_BUTTON_PIN = 5
GPIO_BOOT_PIN = 12


class X728PowerManager:
    """Reads X728 button to initiate shutdown or reboot of rpi.
    Provides methods to shutdown/reboot method from the code.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        pwrloss_clb: Callable[[AcPower], Awaitable[None]],
    ) -> None:
        self._loop = loop
        self._clb = pwrloss_clb

    async def connect(self) -> None:
        GPIO.setwarnings(True)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GPIO_POWERLOSS_PIN, GPIO.IN)
        GPIO.setup(GPIO_SOFT_BUTTON_PIN, GPIO.OUT)

        # Setup power button management
        GPIO.setup(GPIO_PHYSICAL_BUTTON_PIN, GPIO.IN)
        GPIO.setup(GPIO_BOOT_PIN, GPIO.OUT)
        GPIO.output(GPIO_BOOT_PIN, GPIO.HIGH)

        def on_gpio_event_pwr_loss(_: int):
            if GPIO.input(GPIO_POWERLOSS_PIN):
                _LOGGER.warning("AC Power: LOST")
                asyncio.run_coroutine_threadsafe(self._clb(AcPower.OFF), self._loop)
            else:
                _LOGGER.warning("AC Power: ON")
                asyncio.run_coroutine_threadsafe(self._clb(AcPower.ON), self._loop)

        def on_button_pressed(_: int):
            asyncio.run_coroutine_threadsafe(self._pwr_button_pressed(), self._loop)

        GPIO.add_event_detect(GPIO_POWERLOSS_PIN, GPIO.BOTH, callback=on_gpio_event_pwr_loss)
        GPIO.add_event_detect(GPIO_PHYSICAL_BUTTON_PIN, GPIO.RISING, callback=on_button_pressed)
        await asyncio.sleep(0.01)

    async def close(self) -> None:
        GPIO.cleanup([
            GPIO_POWERLOSS_PIN,
            GPIO_SOFT_BUTTON_PIN,
            GPIO_PHYSICAL_BUTTON_PIN,
            GPIO_BOOT_PIN,
        ])
        await asyncio.sleep(0.01)

    async def press_button(self, button: ShutDownCmd):
        _LOGGER.warning("Requested %s. Executing command in 10 seconds", button)
        await asyncio.sleep(10)
        await self._press_button(button.value)

    def ac_power(self) -> AcPower:
        return AcPower.OFF if GPIO.input(GPIO_POWERLOSS_PIN) else AcPower.ON

    async def _press_button(self, press_time: int):
        GPIO.output(GPIO_SOFT_BUTTON_PIN, GPIO.HIGH)
        await asyncio.sleep(press_time)
        GPIO.output(GPIO_SOFT_BUTTON_PIN, GPIO.LOW)

    async def _pwr_button_pressed(self):
        if GPIO.input(GPIO_PHYSICAL_BUTTON_PIN):
            start_time = time.time()
            while GPIO.input(GPIO_PHYSICAL_BUTTON_PIN):
                await asyncio.sleep(0.02)
                if time.time() - start_time > 0.6:
                    _LOGGER.warning("Shuttdown forced by the button")
                    await asyncio.sleep(0.5)
                    await self._shell_command("sudo shutdown -h now")
            if time.time() - start_time > 0.2:
                _LOGGER.warning("Reboot forced by the button")
                await asyncio.sleep(0.5)
                await self._shell_command("sudo shutdown -r now")

    async def _shell_command(self, cmd):
        # Create subprocess
        process = await asyncio.create_subprocess_shell(cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        # Wait for finish
        await process.wait()

    async def __aenter__(self) -> "X728PowerManager":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

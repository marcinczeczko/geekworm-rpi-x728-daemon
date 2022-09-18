import asyncio
import logging
from types import TracebackType
import typing
import time

import RPi.GPIO as GPIO

import asyncio

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728.daemon.power")

# GPIO Pins
GPIO_POWERLOSS_PIN=6
GPIO_SOFT_BUTTON_PIN=26
GPIO_PHYSICAL_BUTTON_PIN=5
GPIO_BOOT_PIN = 12

# I2C
BATTERY_I2C_ADDR = 0x36
BATTERY_REGISTER = 2
CAPACITY_REGISTER = 4

class X728PowerManager:
    def __init__(self, loop:asyncio.AbstractEventLoop, pwrloss_clb: typing.Callable[[str], typing.Awaitable[None]]) -> None:
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
        
        def on_gpio_event_pwr_loss(channel:int):
            if GPIO.input(GPIO_POWERLOSS_PIN):
                _LOGGER.warn("AC Power: LOST")
                asyncio.run_coroutine_threadsafe(self._clb("LOST"), self._loop)
            else:
                _LOGGER.warn('AC Power: ON')
                asyncio.run_coroutine_threadsafe(self._clb("ON"), self._loop)
                
        def on_button_pressed(channel:int):
            asyncio.run_coroutine_threadsafe(self._pwr_button_pressed(), self._loop)   
        
        GPIO.add_event_detect(GPIO_POWERLOSS_PIN, GPIO.BOTH, callback=on_gpio_event_pwr_loss)
        GPIO.add_event_detect(GPIO_PHYSICAL_BUTTON_PIN, GPIO.RISING, callback=on_button_pressed)
        await asyncio.sleep(0.01)
    
    async def close(self) -> None:
        GPIO.cleanup([GPIO_POWERLOSS_PIN, GPIO_SOFT_BUTTON_PIN, GPIO_PHYSICAL_BUTTON_PIN, GPIO_BOOT_PIN])
        await asyncio.sleep(0.01)
        
    async def press_shutdown(self):
        await self._press_button(4)
        
    async def press_reboot(self):
        await self._press_button(0.5)
        
    def ac_power(self) -> str:
        return "LOST" if GPIO.input(GPIO_POWERLOSS_PIN) else "ON"
    
    async def _pwr_button_pressed(self):
        if GPIO.input(GPIO_PHYSICAL_BUTTON_PIN):
            start_time = time.time()
            while GPIO.input(GPIO_PHYSICAL_BUTTON_PIN):
                await asyncio.sleep(0.02)
                if time.time() - start_time > 0.6:
                    _LOGGER.warn("Shuttdown forced by the button")
                    await asyncio.sleep(0.5)
                    await self._shell_command('sudo shutdown -h now')
            if time.time() - start_time > 0.2:
                _LOGGER.warn("Reboot forced by the button")
                await asyncio.sleep(0.5)
                await self._shell_command('sudo shutdown -r now')
                
    async def _shell_command(self, cmd):
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            cmd,
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE
        )
        # Wait for finish
        await process.wait()
        
    async def _press_button(self, time: int):
        GPIO.output(GPIO_SOFT_BUTTON_PIN, GPIO.HIGH)
        await asyncio.sleep(time)
        GPIO.output(GPIO_SOFT_BUTTON_PIN, GPIO.LOW) 
        
    async def __aenter__(self) -> "X728PowerManager":
        """tbd"""
        await self.connect()
        return self
    
    async def __aexit__(
        self, exc_type: typing.Optional[typing.Type[BaseException]], exc: typing.Optional[BaseException], tb: typing.Optional[TracebackType]
    ) -> None:
        await self.close()
""""MQTT Daemon"""
import asyncio
import logging
import typing
import json
import sdnotify

from .configuration import Configuration
from .power_mngt import X728PowerManager
from .battery import X728Battery

from unidecode import unidecode
from datetime import datetime
from contextlib import AsyncExitStack
from asyncio_mqtt import Client as AsyncMqttClient, Will

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728.daemon")

# MQTT
CLIENT_ID = "x728-daemon"

# Message constants
LWT_ONLINE_MSG = "Online"
LWT_OFFLINE_MSG = "Offline"


class X728Daemon:
    """X728 MQTT Daemon
    """

    def __init__(self, *, loop: asyncio.AbstractEventLoop, config: Configuration) -> None:
        """Constructor

        Args:
            loop (asyncio.AbstractEventLoop): Current event loop
            config (Configuration): Configuration of the daemon
        """
        self._loop = loop
        self._config = config
        self._mqtt: AsyncMqttClient = None
        self._battery: X728Battery = None
        self._power: X728PowerManager = None
        self._will = Will(self._config.lwt_topic, LWT_OFFLINE_MSG, qos=1, retain=True)
        self._tasks = set()
        self._sdnotifier = sdnotify.SystemdNotifier()

    async def start(self) -> None:
        async with AsyncExitStack() as stack:

            self._battery = X728Battery(self._loop)
            await stack.enter_async_context(self._battery)

            self._power = X728PowerManager(self._loop, self._ac_power_clb)
            await stack.enter_async_context(self._power)
            # Connect to the MQTT broker
            self._mqtt = AsyncMqttClient(hostname=self._config.mqtt_host,
                                         port=self._config.mqtt_port,
                                         client_id=CLIENT_ID,
                                         will=self._will,
                                         keepalive=60,
                                         logger=_LOGGER)
            await stack.enter_async_context(self._mqtt)

            # Send Online LWT message
            self._tasks.add(asyncio.create_task(self._send_announcement(LWT_ONLINE_MSG)))

            # Start telemetry tasks
            self._tasks.add(asyncio.create_task(self._read_telemetry_data()))

            # Get messages generator for a given topic
            messages = await stack.enter_async_context(self._mqtt.filtered_messages(self._config.pwr_command_topic))
            # Handle received messages
            self._tasks.add(asyncio.create_task(self._process_messages(messages)))

            # Subscribe to topic(s).
            # Note that we subscribe *after* starting the message
            # callbacks. Otherwise, we may miss retained messages.
            _LOGGER.info("Subscribed to %s", self._config.pwr_command_topic)
            await self._mqtt.subscribe(self._config.pwr_command_topic)

            self._sdnotifier.notify("READY=1")
            # Wait for everything to complete
            await asyncio.gather(*self._tasks)

    async def close(self, _):
        self._sdnotifier.notify("STOPPING=1")
        await self._send_announcement(LWT_OFFLINE_MSG)

    async def _ac_power_clb(self, msg: str):
        await self._mqtt.publish(self._config.ac_power_topic, msg, qos=0, retain=False)

    async def _send_announcement(self, msg: str):
        await self._mqtt.publish(self._config.lwt_topic, msg, qos=1, retain=True)

    async def _process_messages(self, messages):
        async for message in messages:
            _LOGGER.debug("Received MQTT Topic [%s] - [%s]", message.topic, message.payload.decode())
            cmd_type = message.topic.split("/")[-1]
            cmd_val = message.payload.decode()
            if cmd_type == "POWER":
                await self._on_shutdown_cmd(cmd_val)
            else:
                await self._send_command_response(message.payload.decode())

    async def _on_shutdown_cmd(self, cmd: str):
        timestamp_sd = datetime.now().strftime("%b %d %H:%M:%S")
        if cmd.lower() == "reboot":
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested Reboot")
            await self._power.press_reboot()
        elif cmd.lower() == "shutdown":
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested Shutdown")
            await self._power.press_shutdown()
        else:
            msg = "Unknown POWER Command received."
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - {unidecode(msg)}")
            await self._send_command_response("Unknown Command")

    async def _send_command_response(self, msg) -> None:
        _LOGGER.debug("[MQTT Topic=[%s] Publishing message=[%s]", self._config.pwr_status_topic, msg)
        await asyncio.sleep(0.1)  # Give some time to roundtrip
        await self._mqtt.publish(self._config.pwr_status_topic, msg, qos=1)

    async def _read_telemetry_data(self) -> None:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            ac_power = self._power.ac_power()
            voltage = await self._battery.get_voltage()
            capacity = await self._battery.get_capacity()
            battery_low = bool(voltage < 3.5)
            battery_very_low = bool(voltage < 3.0)

            if battery_very_low:
                _LOGGER.warning("Battery way to low !. System will gracefully shutdown")
                await asyncio.sleep(2)
                await self._power.press_shutdown()

            if battery_low:
                _LOGGER.warning("Battery low !. System will shutdown soon")

            telemetry_msg = json.dumps({
                "Time": timestamp,
                "ACPower": ac_power,
                "Voltage": voltage,
                "Capacity": capacity,
                "LowBattery": battery_low,
            })
            _LOGGER.debug("MQTT Topic=[%s], Published [%s]", self._config.state_topic, telemetry_msg)
            await self._mqtt.publish(self._config.state_topic, telemetry_msg, qos=0)

            await asyncio.sleep(self._config.telemetry_interval)

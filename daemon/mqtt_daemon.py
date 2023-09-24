""""MQTT Daemon"""
from .constants import LwtValue, BatteryAlarmValue, AcPower, ShutDownCmd, MQTT_CLIENT_ID

from typing import Literal, Optional, Set, Final, overload

import asyncio
import logging
import json
import sdnotify

from .configuration import Configuration
from .power_mngt import X728PowerManager
from .battery import X728Battery

from datetime import datetime
from contextlib import AsyncExitStack
from asyncio_mqtt import Client as AsyncMqttClient, MqttError, Will

_LOGGER: Final[logging.Logger] = logging.getLogger("x728.daemon")


class MQTTDaemon:
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
        self._mqtt: Optional[AsyncMqttClient] = None
        self._battery: Optional[X728Battery] = None
        self._power: Optional[X728PowerManager] = None
        self._will = Will(self._config.lwt_topic, str(LwtValue.OFFLINE), qos=1, retain=True)
        self._tasks: Set[asyncio.Task] = set()
        self._sdnotifier = sdnotify.SystemdNotifier()
        self._battery_alarm: BatteryAlarmValue = BatteryAlarmValue.OFF

    async def start(self) -> None:
        async with AsyncExitStack() as stack:

            self._battery = X728Battery(self._loop)
            await stack.enter_async_context(self._battery)

            self._power = X728PowerManager(self._loop, self._ac_power_clb)
            await stack.enter_async_context(self._power)
            # Connect to the MQTT broker
            self._mqtt = AsyncMqttClient(hostname=self._config.mqtt_host,
                                         port=self._config.mqtt_port,
                                         client_id=MQTT_CLIENT_ID,
                                         username=self._config.mqtt_user,
                                         password=self._config.mqtt_psw,
                                         will=self._will,
                                         keepalive=60,
                                         logger=_LOGGER)
            await stack.enter_async_context(self._mqtt)

            # Send Online LWT message
            self._tasks.add(asyncio.create_task(self._send_lwt(LwtValue.ONLINE)))

            # Start sending statuses
            self._tasks.add(asyncio.create_task(self._start_status()))

            # Get messages generator for a given topic
            commands = await stack.enter_async_context(self._mqtt.filtered_messages(self._config.shutdown_cmnd_topic))
            # Handle received messages
            self._tasks.add(asyncio.create_task(self._process_shutdown_messages(commands)))

            # Subscribe to topic(s).
            # Note that we subscribe *after* starting the message
            # callbacks. Otherwise, we may miss retained messages.
            _LOGGER.info("Subscribed to %s", self._config.shutdown_cmnd_topic)
            await self._mqtt.subscribe(self._config.shutdown_cmnd_topic)

            self._sdnotifier.notify("READY=1")
            # Wait for everything to complete
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def close(self, _):
        self._sdnotifier.notify("STOPPING=1")
        try:
            await self._send_lwt(LwtValue.OFFLINE)
        except MqttError:
            _LOGGER.error("MQTT is already disconnected. Do not sent gracfull Offline message")

    async def _ac_power_clb(self, state: AcPower):
        await self._get_service("mqtt").publish(self._config.acpower_stat_topic, str(state), qos=0, retain=True)

    async def _send_lwt(self, state: LwtValue):
        await self._get_service("mqtt").publish(self._config.lwt_topic, str(state), qos=1, retain=True)

    async def _process_shutdown_messages(self, messages):
        async for message in messages:
            msg = message.payload.decode().upper()
            if hasattr(ShutDownCmd, msg):
                shutdown_cmd = ShutDownCmd[msg]
                _LOGGER.debug("Received Command  [%s]", shutdown_cmd)

                await self._do_shutdown(shutdown_cmd)
            else:
                _LOGGER.warning("Unrecognized command received [%s]", message.payload.decode())
                await self._get_service("mqtt").publish(self._config.shutdown_stat_topic, "UNKNOWN")

    async def _do_shutdown(self, cmd: ShutDownCmd):
        timestamp_sd = datetime.now().strftime("%b %d %H:%M:%S")
        self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested {cmd}")
        await self._send_command_response(cmd)
        await self._get_service("power").press_button(cmd)

    async def _send_command_response(self, cmd: ShutDownCmd) -> None:
        _LOGGER.debug("[MQTT Topic=[%s] Publishing message=[%s]", self._config.shutdown_stat_topic, cmd)
        await asyncio.sleep(0.1)  # Give some time to roundtrip
        await self._get_service("mqtt").publish(self._config.shutdown_stat_topic, str(cmd), qos=0)

    async def _start_status(self) -> None:
        while True:
            ac_power = self._get_service("power").ac_power()
            voltage, capacity = await self._get_service("battery").get()

            if ac_power == AcPower.OFF:
                if voltage < 3.0:
                    _LOGGER.warning("Battery is critical low [%0.1f V, %d %%]!.", voltage, capacity)
                    await self._send_battery_alarm(BatteryAlarmValue.CRITICAL)
                    await self._get_service("power").press_button(ShutDownCmd.SHUTDOWN)

                if voltage < 3.5:
                    _LOGGER.warning("Battery is getting too low [%0.1f V, %d %%]!.", voltage, capacity)
                    await self._send_battery_alarm(BatteryAlarmValue.WARNING)
            else:
                if self._battery_alarm != BatteryAlarmValue.OFF:
                    _LOGGER.info("Clear battery alarm. Battery is charging")
                    await self._send_battery_alarm(BatteryAlarmValue.OFF)

            _LOGGER.debug("Published to status topics")

            battery_status = json.dumps({"Voltage": voltage, "Capacity": capacity})
            await asyncio.gather(
                self._get_service("mqtt").publish(self._config.battery_stat_topic, battery_status, qos=0, retain=True),
                self._get_service("mqtt").publish(self._config.acpower_stat_topic, str(ac_power), qos=0, retain=True))

            await asyncio.sleep(self._config.status_interval)

    async def _send_battery_alarm(self, value: BatteryAlarmValue):
        self._battery_alarm = value
        await self._get_service("mqtt").publish(self._config.alert_battery_topic, str(value), qos=0, retain=False)

    @overload
    def _get_service(self, service: Literal["mqtt"]) -> AsyncMqttClient:
        ...

    @overload
    def _get_service(self, service: Literal["power"]) -> X728PowerManager:
        ...

    @overload
    def _get_service(self, service: Literal["battery"]) -> X728Battery:
        ...

    def _get_service(self, service: str):
        if hasattr(self, f"_{service}"):
            return getattr(self, f"_{service}")
        else:
            _LOGGER.error("%s is not initialized", service)
            raise DaemonNotInitialized()


class DaemonNotInitialized(Exception):
    pass

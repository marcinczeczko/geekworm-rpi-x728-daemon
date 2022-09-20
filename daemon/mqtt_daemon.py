""""MQTT Daemon"""
import asyncio
import logging
import typing
import json
import sdnotify

from .configuration import Configuration
from .power_mngt import X728PowerManager
from .battery import X728Battery

from datetime import datetime
from contextlib import AsyncExitStack
from asyncio_mqtt import Client as AsyncMqttClient, Will

from .constants import LwtValue, BatteryAlarmValue, AcPower, ShutDownCmd, MQTT_CLIENT_ID

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728.daemon")


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
        self._mqtt: AsyncMqttClient = None
        self._battery: X728Battery = None
        self._power: X728PowerManager = None
        self._will = Will(self._config.lwt_topic, LwtValue.OFFLINE.value, qos=1, retain=True)
        self._tasks = set()
        self._sdnotifier = sdnotify.SystemdNotifier()
        self._battery_alarm = BatteryAlarmValue.OFF

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
            self._tasks.add(asyncio.create_task(self._process_shutdown_cmd(commands)))

            # Subscribe to topic(s).
            # Note that we subscribe *after* starting the message
            # callbacks. Otherwise, we may miss retained messages.
            _LOGGER.info("Subscribed to %s", self._config.shutdown_cmnd_topic)
            await self._mqtt.subscribe(self._config.shutdown_cmnd_topic)

            self._sdnotifier.notify("READY=1")
            # Wait for everything to complete
            await asyncio.gather(*self._tasks)

    async def close(self, _):
        self._sdnotifier.notify("STOPPING=1")
        await self._send_lwt(LwtValue.OFFLINE)

    async def _ac_power_clb(self, state: AcPower):
        await self._mqtt.publish(self._config.ac_power_topic, state.value, qos=0, retain=True)

    async def _send_lwt(self, state: LwtValue):
        await self._mqtt.publish(self._config.lwt_topic, state.value, qos=1, retain=True)

    async def _process_shutdown_cmd(self, commands):
        async for cmd in commands:
            try:
                shutdown_cmd = ShutDownCmd(cmd.payload.decode())
                _LOGGER.debug("Received Command  [%s]", shutdown_cmd.value)

                await self._do_shutdown(shutdown_cmd)
            except ValueError:
                _LOGGER.warning("Unrecognized command received [%s]", cmd.payload.decode())

    async def _do_shutdown(self, cmd: ShutDownCmd):
        timestamp_sd = datetime.now().strftime("%b %d %H:%M:%S")
        self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested {cmd.value}")
        await self._send_command_response(cmd)

        if cmd == ShutDownCmd.REBOOT:
            await self._power.press_reboot()
        elif cmd == ShutDownCmd.SHUTDOWN:
            await self._power.press_shutdown()

    async def _send_command_response(self, cmd: ShutDownCmd) -> None:
        _LOGGER.debug("[MQTT Topic=[%s] Publishing message=[%s]", self._config.shutdown_stat_topic, cmd.value)
        await asyncio.sleep(0.1)  # Give some time to roundtrip
        await self._mqtt.publish(self._config.shutdown_stat_topic, cmd.value, qos=0)

    async def _start_status(self) -> None:
        while True:
            ac_power = self._power.ac_power()
            voltage = await self._battery.get_voltage()
            capacity = await self._battery.get_capacity()

            if ac_power == AcPower.OFF:
                if voltage < 3.0:
                    _LOGGER.warning("Battery is critical low [%0.1f V, %d %%]!.", voltage, capacity)
                    await self._send_battery_alarm(BatteryAlarmValue.CRITICAL)
                    await self._power.press_shutdown()

                if voltage < 3.5:
                    _LOGGER.warning("Battery is getting too low [%0.1f V, %d %%]!.", voltage, capacity)
                    await self._send_battery_alarm(BatteryAlarmValue.WARNING)
            else:
                if self._battery_alarm != BatteryAlarmValue.OFF:
                    _LOGGER.info("Clear battery alarm. Battery is charging")
                    await self._send_battery_alarm(BatteryAlarmValue.OFF)

            _LOGGER.debug("Published to status topics")

            battery_status = json.dumps({"Voltage": voltage, "Capacity": capacity})
            await asyncio.gather(self._mqtt.publish(self._config.battery_stat_topic, battery_status, qos=0, retain=True),
                                 self._mqtt.publish(self._config.acpower_stat_topic, ac_power.value, qos=0, retain=True))

            await asyncio.sleep(self._config.telemetry_interval)

    async def _send_battery_alarm(self, value: BatteryAlarmValue):
        self._battery_alarm = value
        await self._mqtt.publish(self._config.alert_battery_topic, self._battery_alarm.name, qos=0, retain=False)

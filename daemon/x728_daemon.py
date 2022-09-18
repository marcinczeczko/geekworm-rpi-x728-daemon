import asyncio
import logging
import typing
import json

from unidecode import unidecode
from datetime import datetime
from contextlib import AsyncExitStack
from config import Configuration
from asyncio_mqtt import Client as AsyncMqttClient, Will

from x728_battery import X728Battery
from x728_power_mngt import X728PowerManager

import sdnotify

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728.daemon")

# MQTT
# Subtopics
LWT_SUBTOPIC = 'LWT'
STATE_TOPIC = 'STATE'
RESULT_TOPIC = 'RESULT'
POWER_TOPIC = 'ACPOWER'

# Message constants
LWT_ONLINE_MSG = 'Online'
LWT_OFFLINE_MSG = 'Offline'

# GPIO Pins
GPIO_POWERLOSS_PIN=6
GPIO_SOFT_BUTTON_PIN=26
GPIO_PHYSICAL_BUTTON_PIN=5
GPIO_BOOT_PIN = 12

class X728Daemon:
    def __init__(self, *, loop:asyncio.AbstractEventLoop, config: Configuration) -> None:
        self._loop = loop
        self._config = config
        self._mqtt:AsyncMqttClient = None
        self._battery:X728Battery = None
        self._power:X728PowerManager = None
        self._will = Will(self._lwt_topic, LWT_OFFLINE_MSG, qos=2, retain=True)
        self._tasks = set()
        self._sdnotifier = sdnotify.SystemdNotifier()
        
    @property
    def _lwt_topic(self) -> None:
        return f"{self._config.telemetry_topic}/{LWT_SUBTOPIC}"
    
    @property
    def _tele_state_topic(self) -> None:
        return f"{self._config.telemetry_topic}/{STATE_TOPIC}"
    
    @property
    def _stat_result_topic(self) -> None:
        return f"{self._config.status_topic}/{RESULT_TOPIC}"
    
    @property
    def _stat_acpower_topic(self) -> None:
        return f"{self._config.status_topic}/{POWER_TOPIC}"
    
    @property
    def _command_topic_filter(self) -> None:
        return f"{self._config.command_topic}/#"
    
    async def start(self) -> None:
        async with AsyncExitStack() as stack:
            
            self._battery = X728Battery(self._loop)
            await stack.enter_async_context(self._battery)
            
            self._power = X728PowerManager(self._loop, self._ac_power_clb)
            await stack.enter_async_context(self._power)
            
            #stack.push_async_callback(self._send_announcement, LWT_OFFLINE_MSG)
            
            # Connect to the MQTT broker
            self._mqtt = AsyncMqttClient(hostname=self._config.mqtt_host, port=self._config.mqtt_port, will=self._will)
            await stack.enter_async_context(self._mqtt)
            
            # Send Online LWT message
            self._tasks.add(asyncio.create_task(self._send_announcement(LWT_ONLINE_MSG)))
            
            # Get messages generator for a given topic
            messages = await stack.enter_async_context(self._mqtt.filtered_messages(self._command_topic_filter))
            # Handle received messages
            self._tasks.add(asyncio.create_task(self._process_messages(messages)))

            # Subscribe to topic(s). Note that we subscribe *after* starting the message
            # callbacks. Otherwise, we may miss retained messages.
            _LOGGER.info("Subscribed to %s", self._command_topic_filter)
            await self._mqtt.subscribe(self._command_topic_filter)
            
            # Start telemetry tasks
            self._tasks.add(asyncio.create_task(self._read_telemetry_data()))
            
            self._sdnotifier.notify('READY=1')
            # Wait for everything to complete (or fail due to, e.g., network errors)
            await asyncio.gather(*self._tasks)
            
    async def close(self, loop):
        self._sdnotifier.notify("STOPPING=1")
        await self._send_announcement(LWT_OFFLINE_MSG)
            
    async def _ac_power_clb(self, msg: str):
        await self._mqtt.publish(self._stat_acpower_topic, msg, qos=0, retain=False)
    
    async def _send_announcement(self, msg: str):
        await self._mqtt.publish(self._lwt_topic, msg, qos=1, retain=False)      
        
    async def _process_messages(self, messages):
        async for message in messages:
            _LOGGER.debug(f"Received MQTT Topic [{message.topic}] = [{message.payload.decode()}]")
            cmd_type = message.topic.split("/")[-1]
            cmd_val = message.payload.decode()
            if cmd_type == "POWER":
                await self._on_shutdown_cmd(cmd_val)
            else:
                await self._send_command_response(message.payload.decode())
                
    async def _on_shutdown_cmd(self, cmd:str):
        timestamp_sd = datetime.now().strftime('%b %d %H:%M:%S')
        if cmd.lower() == 'reboot':
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested Reboot")
            await self._power.press_reboot()
        elif cmd.lower() == 'shutdown':
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - Requested Shutdown")
            await self._power.press_shutdown()
        else:
            msg = "Unknown POWER Command received."
            self._sdnotifier.notify(f"STATUS={timestamp_sd} - {unidecode(msg)}")
            await self._send_command_response("Unknown Command")
        
    async def _send_command_response(self, msg) -> None:
        _LOGGER.debug(f'[MQTT Topic="{self._stat_result_topic}"] Publishing message={msg}')
        await asyncio.sleep(0.1) # Give some time to roundtrip
        await self._mqtt.publish(self._stat_result_topic, msg, qos=1)
        
    async def _read_telemetry_data(self) -> None:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            ac_power = self._power.ac_power()
            voltage = await self._battery.get_voltage()
            capacity = await self._battery.get_capacity()
            battery_low = True if voltage < 3.5 else False
            battery_very_low = True if voltage < 3.0 else False
            
            if battery_very_low:
                _LOGGER.warn("Battery way to low !. System will gracefully shutdown")
                await asyncio.sleep(2)
                await self._power.press_shutdown()
        
            if battery_low:
                _LOGGER.warn("Battery low !. System will shutdown soon")
            
            telemetry_msg = json.dumps({'Time': timestamp, 'ACPower': ac_power, 'Voltage': voltage, 'Capacity': capacity, 'LowBattery': battery_low})
            _LOGGER.debug(f'MQTT Topic={self._tele_state_topic}, Published [{telemetry_msg}]')
            await self._mqtt.publish(self._tele_state_topic, telemetry_msg, qos=0)
            
            await asyncio.sleep(self._config.telemetry_interval)       

from enum import Enum

MQTT_CLIENT_ID = "x728-daemon"


class LwtValue(Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"


class BatteryAlarmValue(Enum):
    OFF = "OFF"
    WARNING = "Warning"
    CRITICAL = "Critical"


class AcPower(Enum):
    OFF = "OFF"
    ON = "ON"


class ShutDownCmd(Enum):
    """Value of enum defines how long (seconds) the shutdown button should be soft-pressed
    """
    SHUTDOWN = 4
    REBOOT = 0.5

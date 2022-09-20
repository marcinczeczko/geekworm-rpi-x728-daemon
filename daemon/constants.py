from enum import Enum, auto

MQTT_CLIENT_ID = "x728-daemon"


class LwtValue(Enum):
    ONLINE = auto()
    OFFLINE = auto()

    def __str__(self) -> str:
        return self.name


class BatteryAlarmValue(Enum):
    OFF = auto()
    WARNING = auto()
    CRITICAL = auto()

    def __str__(self) -> str:
        return self.name


class AcPower(Enum):
    OFF = auto()
    ON = auto()

    def __str__(self) -> str:
        return self.name


class ShutDownCmd(Enum):
    """Value of enum defines how long (seconds) the shutdown button should be soft-pressed
    """
    SHUTDOWN = 4
    REBOOT = 0.5

    def __str__(self) -> str:
        return self.name

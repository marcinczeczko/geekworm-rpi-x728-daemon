"""Daemon configuration file handling"""
import logging
import configparser
from typing import Union

log = logging.getLogger("x728.configuration")


class Configuration:
    """
    Class responsible for reading configuration ini file and
    parsing it to properties required by the application
    """

    def __init__(self, config_file_path: str) -> None:
        self._load_config(config_file_path)

    def _load_config(self, config_file_path: str) -> None:
        config = configparser.ConfigParser()
        #config.optionxform = str

        with open(config_file_path, encoding="utf-8") as file:
            config.read_file(file)

        self.mqtt_host = self._get_str(config, "MQTT", "mqtt_host", "localhost")
        self.mqtt_port = self._get_int(config, "MQTT", "mqtt_port", 1883)
        self.mqtt_user = self._get_str(config, "MQTT", "mqtt_user")
        self.mqtt_psw = self._get_str(config, "MQTT", "mqtt_psw")

        self.lwt_topic = self._get_str(config, "MQTT", "lwt_topic", "x728/LWT")
        self.alert_battery_topic = self._get_str(config, "MQTT", "alert_battery_topic", "x728/stat/ALARM")

        self.battery_stat_topic = self._get_str(config, "MQTT", "battery_stat_topic", "x728/stat/BATTERY")
        self.acpower_stat_topic = self._get_str(config, "MQTT", "acpower_stat_topic", "x728/stat/ACPOWER")

        self.shutdown_cmnd_topic = self._get_str(config, "MQTT", "shutdown_cmnd_topic", "x728/cmd/SHUTDOWN")
        self.shutdown_stat_topic = self._get_str(config, "MQTT", "shutdown_stat_topic", "x728/stat/SHUTDOWN")

        self.status_interval = self._get_int(config, "MQTT", "status_interval", 60)

        self.restart_on_error_timeout_sec = self._get_int(config, "Daemon", "restart_on_error_timeout_sec", 5 * 60)
        self.restart_on_error_max_retries = self._get_int(config, "Daemon", "restart_on_error_max_retries", 5)

    def _get_str(self, config, section: str, prop_name: str, default_val: Union[str, None] = None) -> Union[str, None]:
        return config[section].get(prop_name, default_val)

    def _get_int(self, config, section: str, prop_name: str, default_val: int = 0) -> int:
        return config[section].getint(prop_name, default_val)

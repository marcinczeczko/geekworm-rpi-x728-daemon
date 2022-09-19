"""Daemon configuration file handling"""
import logging
import configparser

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
        config.optionxform = str

        with open(config_file_path, encoding="utf-8") as file:
            config.read_file(file)

        self.mqtt_host = self._get_str(config, "MQTT", "mqtt_host", "localhost")
        self.mqtt_port = self._get_int(config, "MQTT", "mqtt_port", 1883)

        self.lwt_topic = self._get_str(config, "MQTT", "lwt_topic", "x728/LWT}")
        self.state_topic = self._get_str(config, "MQTT", "state_topic", "x728/STATE")
        self.ac_power_topic = self._get_str(config, "MQTT", "ac_power_topic", "x728/ACPOWER")
        self.pwr_command_topic = self._get_str(config, "MQTT", "pwr_command_topic", "x728/POWER")
        self.pwr_status_topic = self._get_str(config, "MQTT", "pwr_status_topic", "x728/STATUS")

        self.telemetry_interval = self._get_int(config, "MQTT", "telemetry_interval", 60)

    def _get_str(self, config, section: str, prop_name: str, default_val: str = None) -> str:
        return config[section].get(prop_name, default_val)

    def _get_int(self, config, section: str, prop_name: str, default_val: int = 0) -> int:
        return config[section].getint(prop_name, default_val)

import logging
from configparser import ConfigParser

log = logging.getLogger('x728.configuration')

class Configuration:
    def __init__(self, config_file_path: str) -> None:
        self._load_config(config_file_path)
        
    def _load_config(self, config_file_path: str) -> None:
        config = ConfigParser()
        config.optionxform = str
    
        with open(config_file_path) as file:
            config.read_file(file)
            
        self.mqtt_host = self._get_str(config,'MQTT', 'mqtt_host', 'localhost')
        self.mqtt_port = self._get_int(config, 'MQTT', 'mqtt_port', 1883)
        
        prefix = self._get_str(config, 'MQTT', 'prefix', '')
        topic = self._get_str(config, 'MQTT', 'topic', 'rpi-x728')
        
        telemetry_topic_pattern = self._get_str(config, 'MQTT', 'telemetry_topic_pattern', '{prefix}/tele/{topic}')
        command_topic_pattern = self._get_str(config, 'MQTT', 'command_topic_pattern', '{prefix}/cmnd/{topic}')
        status_topic_pattern = self._get_str(config, 'MQTT', 'status_topic_pattern', '{prefix}/stat/{topic}')
        
        self.telemetry_topic = telemetry_topic_pattern.format(prefix = prefix, topic = topic)
        self.command_topic = command_topic_pattern.format(prefix = prefix, topic = topic)
        self.status_topic = status_topic_pattern.format(prefix = prefix, topic = topic)
        self.telemetry_interval = self._get_int(config, 'MQTT', 'telemetry_interval', 60)
        self.log_level = logging.getLevelName(self._get_str(config, 'General', 'logLevel', 'INFO'))
    
    def _get_str(self, config, section: str, property: str, default_val: str = None) -> str:
        return config[section].get(property, default_val)
    
    def _get_int(self, config, section: str, property: str, default_val: int = 0) -> int:
        return config[section].getint(property, default_val)
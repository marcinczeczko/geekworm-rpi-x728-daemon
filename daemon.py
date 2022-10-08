"""Daemon main"""
import time
import sys
import argparse
import configparser
import os
import asyncio
import typing
import logging
import aiorun
import asyncio_mqtt
import daemon

console = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y/%m/%d %H:%M:%S")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)
logging.getLogger("").setLevel(logging.INFO)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geekworm X728 Power Management")
    parser.add_argument("-d", "--debug", help="show debug output", action="store_true")
    parser.add_argument("-c", "--config_file_path", help="set path to the configuration file")
    parse_args = parser.parse_args()
    config_file_path = parse_args.config_file_path

    if parse_args.debug:
        _LOGGER.setLevel(logging.DEBUG)
    else:
        _LOGGER.setLevel(logging.INFO)

    if not config_file_path:
        parser.error("Missing configuration file path")

    if not os.path.exists(config_file_path):
        parser.error(f"{config_file_path} file doesn't exit")

    try:
        config = daemon.Configuration(config_file_path)
    except (configparser.Error, FileNotFoundError) as e:
        _LOGGER.error("%s exception occured %s", type(e), e)
        parser.error(f"Please check {config_file_path} has wrong syntax")

    restart_retry_count: int = 0
    graceful_shutdown = False
    while restart_retry_count < config.restart_on_error_max_retries and not graceful_shutdown:
        try:
            import daemon

            loop = asyncio.get_event_loop_policy().new_event_loop()

            if parse_args.debug:
                loop.set_debug(True)

            daemon = daemon.MQTTDaemon(loop=loop, config=config)

            aiorun.run(daemon.start(), loop=loop, shutdown_callback=daemon.close, stop_on_unhandled_errors=True)
            graceful_shutdown = True
        except Exception as e:
            _LOGGER.error("MQTT Error happened: %s. Most likely AC power is lost, attempting to re-start daemon in %d seconds.", e,
                          config.restart_on_error_timeout_sec)
            loop.close()
            restart_retry_count += 1
            time.sleep(config.restart_on_error_timeout_sec)
            _LOGGER.info("Restart attempt %d/%d", restart_retry_count, config.restart_on_error_max_retries)

    if not graceful_shutdown:
        _LOGGER.critical("Reached maximum restart counts. Stopping the process")
        sys.exit(os.EX_UNAVAILABLE)
    else:
        sys.exit(os.EX_OK)

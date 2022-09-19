"""Daemon main"""
import argparse
import configparser
import os
import asyncio
import typing
import logging
import aiorun
import daemon

console = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y/%m/%d %H:%M:%S")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)
logging.getLogger("").setLevel(logging.INFO)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geekworm X728 Power Management")
    parser.add_argument("-c", "--config_file_path", help="set path to the configuration file")
    parse_args = parser.parse_args()
    config_file_path = parse_args.config_file_path

    if not config_file_path:
        parser.error("Missing configuration file path")

    if not os.path.exists(config_file_path):
        parser.error(f"{config_file_path} file doesn't exit")

    try:
        config = daemon.Configuration(config_file_path)
    except (configparser.Error, FileNotFoundError) as e:
        _LOGGER.error("%s exception occured %s", type(e), e)
        parser.error(f"Please check {config_file_path} has wrong syntax")
    _LOGGER.setLevel(config.log_level)

    loop = asyncio.get_event_loop()

    if config.log_level.upper() == "DEBUG":
        loop.set_debug(True)

    daemon = daemon.X728Daemon(loop=loop, config=config)

    aiorun.run(daemon.start(), loop=loop, shutdown_callback=daemon.close)


from argparse import ArgumentParser
import os
from config import Configuration
import asyncio
import typing
import logging

import aiorun

from x728_daemon import X728Daemon

console = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y/%m/%d %H:%M:%S')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)
logging.getLogger('').setLevel(logging.INFO)

_LOGGER: typing.Final[logging.Logger] = logging.getLogger("x728")

if __name__ == '__main__':
    parser = ArgumentParser(description='Geekworm X728 Power Management')
    parser.add_argument("-d", "--debug", 
                        help="show debug output", 
                        action="store_true")
    parser.add_argument("-c", '--config_file_path',
                        help='set path to the configuration file')
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
        config = Configuration(config_file_path)
    except Exception as e:
        _LOGGER.error("Something wrong with the configuration file", e)
        parser.error(f"Please check {config_file_path} has wrong syntax")
        
    loop = asyncio.get_event_loop()
    
    if parse_args.debug:
        loop.set_debug(True)
    
    daemon = X728Daemon(loop=loop, config=config)
    
    aiorun.run(daemon.start(), loop=loop, shutdown_callback=daemon.close)
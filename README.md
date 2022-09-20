# Overview

The [X728](https://wiki.geekworm.com/X728) is an advanced uninterruptible power supply expansion board for all current models of the Raspberry Pi using a 40 pin header.

The software provided by the vendor is a shell script and couple of python scripts showing how to communicate with board.

My goals to build my own daemon was:

- To build one script/daemon to control the board
- To be able to communicate with X728 via MQTT - so could use in my home automation system
- To be a python based using `asyncio` (as I wanted to learn more about async python)

General feaatures:
- Periodic publication to MQTT topic system status about AC power, battery voltage & capacity of X728 board
- Inform on MQTT topic AC power loss (or back)
- Listen on MQTT topic to receive commands to Reboot or Shutdown gracefully your rpi.
- Monitor battery voltage and when it drops below 3.0V RPI is gracefully shutdown
- Handle X728 microswitch button allowing to Reboot (quick push) or gracefully Shutdown (longer push) RPI

## MQTT Topics

All topic names are configurable in general. Using the `config.ini` terms, here full list of topics available:

| Topic                   | Purpose | Sample Data |
|-------------------------|---------|---------------|
| $prefix/tele/$topic/LWT |  Last Will Topic   | Online, Offline |
| $prefix/tele/$topic/STATE |  Perioding status of the X728 Board (every 2mins by default)  | JSON - `{"Time": "2022-09-18T18:02:46","ACPower": "ON","Voltage": 4.19,"Capacity": 100,"LowBattery": false}` |
| $prefix/cmnd/$topic/POWER |   Command topic to shutdown or reboot RPI | REBOOT, SHUTDOWN |
| $prefix/stat/$topic/???? |  TODO     | |

# Installation

## Prerequisites

- Python 3.10 + PIP3

## User permissions

X728 service is runnin on `pi` user by default (if you have installed on different user follow the same steps). The user running the service must be a password-less sudoers with minium required rights to execute `/sbin/shutdown` command only.

If your user has rights to `sudo` without password you're ready to go.

If not, simply create new files in `/etc/sudoers.d/` folder to enable that and restart your machine.

```sh
echo "pi ALL=NOPASSWD: /sbin/shutdown" > /etc/sudoers.d/010_shutdown
```

## Configuration

Configure your daemon by editing `config.ini`.
```ini
[General]
logLevel = DEBUG

[MQTT]
mqtt_host = 192.168.10.2
#mqtt_port = 1883

prefix = home
topic = oh-power

telemetry_topic_pattern = {prefix}/tele/{topic}
command_topic_pattern = {prefix}/cmnd/{topic}
status_topic_pattern = {prefix}/stat/{topic}

# In seconds
telemetry_interval = 2 
```

## Install python packages

`pip install -r requirements.txt`

## Install system.d service

1. Copy systemd.service file
```sh
cp systemd/x728-daemon.service /etc/systemd/system
```

2. Set appropriate permissions to file
```sh
sudo chown root:root /etc/systemd/system/x728-daemon.service
sudo chmod 644 /etc/systemd/system/x728-daemon.service
```

3. And reload systemd daemon
```sh
sudo systemctl daemon-reload
```

4. Enable and start your service
```sh
sudo systemctl enable x728-daemon.service
sudo systemctl start x728-daemon.service
```

5. You can check status of the service
```sh
sudo systemctl status x728-daemon.service
```

6. And monitor logs
```sh
sudo journalctl --unit x728-daemon.service -f
```


## TODO
AC Power should be a separate channel anyway:
- so it should show the current status of AC power and react of power lost events
- shutdown_alarm - should raise ON/OFF if the battery level reaches the critical level (3.3) - so could inform ohe the shutdown will happen
    - configurable trigger of shutdown alarm

# Overview

The [X728](https://wiki.geekworm.com/X728) is an power supply expansion board for all current models of the Raspberry Pi using a 40 pin header.
The software provided by the vendor is a shell script and couple of python scripts that rather showcases how to communicate with the board.

I instead wanted to build my own daemonized service running on Pi to does all the job, that was:

- Handling physical button on board to gracefully shutdown or reboot RPi
- Monitor battery capacity and voltage and report it via MQTT
- Send a warning via MQTT, if battery voltage is below certain value
- Send a critical warning via MQTT, if battery drops below certain level
- Gracefully shutdown RPi, if AC voltage is missing and critical warning about battery level were triggered
- Send an alert via MQTT, if AC power is off
- Finally, MQTT command topic to trigger gracefull reboot or shutdown of my RPi

Which is actually a features that are currently implemented.

## MQTT Topics

All aspects of MQTT thing is configurable via `config.ini` as follows.

| Config param name | Default value if not set | Current value | Description                                               |
| ----------------- | ------------------------ | ------------- | --------------------------------------------------------- |
| mqtt_host         | localhost                | localhost     | MQTT hostname or IP                                       |
| mqtt_port         | 1883                     | 1883          | MQTT Port                                                 |
| status_interval   | 60                       | 120           | Battery and AC Power status reporting interval in seconds |

And topics related configuration
| Config param name   | Default value if not set | Current value             | Description                                                                  | Values                                     |
| ------------------- | ------------------------ | ------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------ |
| lwt_topic           | x728/LWT                 | home/tele/oh-ups/LWT      | Last Will Topic                                                              | ONLINE/OFFLINE                             |
| alert_battery_topic | x728/stat/ALARM          | home/alert/oh-ups/BATTERY | Alerts battery reached certain level of voltage                              | WARNING (below 3.5V), CRITICAL (below3.0V) |
| battery_stat_topic  | x728/stat/BATTERY        | home/stat/oh-ups/BATTERY  | Status about UPS battery condition - Voltage and Capacity (%)                | {"Voltage": "0.0", "Capacity": "90"}       |
| acpower_stat_topic  | x728/stat/ACPOWER        | home/stat/oh-ups/ACPOWER  | Status of the AC Power. Reported every status interval, or when changes      | ON/OFF                                     |
| shutdown_cmnd_topic | x728/cmd/SHUTDOWN        | home/cmnd/oh-ups/SHUTDOWN | Command topic to gracefully shutdown or reboot RPi. Action happens after 10s | REBOOT/SHUTDOWN                            |
| shutdown_stat_topic | x728/stat/SHUTDOWN       | home/stat/oh-ups/SHUTDOWN | Status of the shutdown command - some form of confirmation                   | REBOOT/SHUTDOWN/UNKNOWN                    |

# Installation

## Prerequisites

- Python 3.10 + PIP 3

## User permissions

X728 service is running on `pi` user by default (if you have installed on different user follow the same steps). The user running the service must be a password-less sudoers with minium required rights to execute `/sbin/shutdown` command only.

If your user has rights to `sudo` without password you're ready to go.

If not, simply create new files in `/etc/sudoers.d/` folder to enable that and restart your machine.

```sh
echo "pi ALL=NOPASSWD: /sbin/shutdown" > /etc/sudoers.d/010_shutdown
```

## Configuration

Except changing the values that are currently in config.ini nothing special is required.

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

## Troubleshooting

In case of any issued. You can run your service in a standalone mode, just stop the systemd services and run the service in debug mode

```sh
python3 daemon.py -c config.ini -d
```

## TODO
- MQTT over SSL
- MQTT username/password 
- Configurable triggers of battery alerts
- Configurable delay between shutdown/reboot
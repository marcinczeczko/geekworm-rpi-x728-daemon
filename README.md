## Clone the repo into **pi** user home

`git clone ....`

## Amend configuration as needed

`config.init`


## Create systemd service
`cp systemd/x728-daemon.service /etc/systemd/system`
`sudo chown root:root /etc/systemd/system/x728-daemon.service`
`sudo chmod 644 /etc/systemd/system/x728-daemon.service`
`sudo systemctl daemon-reload`

`sudo systemctl enable x728-daemon.service`

`sudo systemctl start x728-daemon.service`

See logs
`sudo journalctl --unit x728-daemon.service`
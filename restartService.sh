#!/bin/bash

sudo systemctl stop autoAustralia.service
sleep 3
sudo systemctl start autoAustralia.service

#!/bin/bash

read -p "level: " level

sudo modprobe -r thinkpad_acpi
sudo modprobe thinkpad_acpi fan_control=1
echo level $level | sudo tee /proc/acpi/ibm/fan

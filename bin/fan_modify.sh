#!/bin/bash

level=$1

sudo modprobe -r thinkpad_acpi
sudo modprobe thinkpad_acpi fan_control=1
echo "level $level" | sudo tee /proc/acpi/ibm/fan

sleep 1
cat /proc/acpi/ibm/fan

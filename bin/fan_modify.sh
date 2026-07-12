#!/bin/bash

level=$1

echo level: $level | sudo tee /proc/acpi/ibm/fan &>/dev/null

cat /proc/acpi/ibm/fan

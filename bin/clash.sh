#!/bin/bash

sleep 2
echo "try to start clash"
date

cd ~/.clash/

./clash -f ~/.clash/config.yaml

echo "script exec ok"

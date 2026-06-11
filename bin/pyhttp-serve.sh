#!/bin/bash

ip a | grep inet

python -m http.server $1

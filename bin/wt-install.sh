#!/bin/bash

wt install $(wt search $1 | fzf)

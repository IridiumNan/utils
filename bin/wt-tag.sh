#!/bin/bash

PKG=$1

wt tag $(wt search $PKG | fzf) $(wt tag ls | fzf)

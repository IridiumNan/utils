#!/bin/bash

PKG=$(wt search $1 | fzf)

wt rm $PKG

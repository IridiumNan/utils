#!/bin/bash

PKG=$(wt search $1 | fzf)

echo "old package name ->$PKG"
read -p "enter the new package name ->" NEWPKG

wt mv $PKG $NEWPKG

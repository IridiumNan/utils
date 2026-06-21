#!/bin/bash

baseURL="https://repo.waterman.xin/share/"
fullPath="$1"
fileName=$(basename $fullPath)
shareDir="/home/${USER}/share/"
dst="${USER}@${server}:${shareDir}"

echo "upload the ${fileName} to ${server}"

if [ $# -eq 1 ]; then
    scp $fullPath $dst

    echo "visit link ->" "${baseURL}${fileName}"
    exit 0
fi

if [ $# -eq 2 ]; then
    fileName="$2"

    scp $fullPath "${dst}${fileName}"

    echo "visit link ->" "${baseURL}${fileName}"

fi

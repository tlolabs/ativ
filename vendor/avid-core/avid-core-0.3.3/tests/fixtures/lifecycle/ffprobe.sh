#!/bin/sh
if [ "$1" = '-version' ]; then echo 'ffprobe version test'; exit; fi
for arg in "$@"; do
  if [ "$arg" = 'stream=width,height' ]; then echo 64x48; exit; fi
done
echo 2

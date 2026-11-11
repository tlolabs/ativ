#!/bin/sh
if [ "$1" = '-version' ]; then echo 'ffmpeg version test'; exit; fi
if [ "$2" = '-encoders' ]; then printf ' V..... libx264 software\n V..... h264_videotoolbox hardware\n'; exit; fi
if [ "$2" = '-filters' ] || [ "$2" = '-h' ]; then
  normalization=setsar
  if [ -f "${0%/*}/normalization-mode" ]; then normalization=$(cat "${0%/*}/normalization-mode"); fi
  printf '%s\n' "$2" >> "${0%/*}/normalization-probes"
  if [ "$normalization" = 'slow' ]; then exec sleep 10; fi
  if [ "$2" = '-filters' ] && [ "$normalization" = 'setsar' ]; then printf ' ... setsar V->V Set sample aspect ratio\n'; fi
  if [ "$2" = '-h' ] && [ "$normalization" = 'scale' ]; then printf ' reset_sar <boolean> reset sample aspect ratio\n'; fi
  exit
fi
# Mode is ordinary data, separate from the immutable executable inode.
mode=$(cat "${0%/*}/fixture-mode")
encoder=''
previous=''
for arg in "$@"; do
  if [ "$previous" = '-c:v' ]; then encoder="$arg"; fi
  previous="$arg"
  output="$arg"
done
printf partial > "$output"
printf 'out_time_us=1000000\nspeed=2x\nprogress=continue\n'
if [ "$mode" = 'slow' ]; then exec sleep 10; fi
if [ "$mode" = 'fail' ] || [ "$encoder" = 'h264_videotoolbox' ]; then echo 'deliberate encoder failure' >&2; exit 7; fi
printf completed > "$output"
printf 'out_time_us=2000000\nspeed=2x\nprogress=end\n'

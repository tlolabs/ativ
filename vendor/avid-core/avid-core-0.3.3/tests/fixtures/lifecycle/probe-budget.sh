#!/bin/sh
if [ "$1" = '-version' ]; then echo 'ffprobe version test'; exit; fi
root=${0%/*}
for image do :; done
image=${image##*/}
# Shell builtins keep this fixture's process lifetime independent of helpers.
printf 'start %s\n' "$image" >> "$root/probe-events"
while [ ! -f "$root/release-all" ] && [ ! -f "$root/release-$image" ]; do :; done
printf 'end %s\n' "$image" >> "$root/probe-events"
if [ -f "$root/fail-$image" ]; then
  echo 'deliberate artwork probe failure' >&2
  exit 7
fi
echo 64x48

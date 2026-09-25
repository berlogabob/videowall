#!/usr/bin/env bash
# Boot-file edits on a fake card: adds what is missing, keeps what is there, changes nothing on a second run.
set -euo pipefail
d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
printf 'console=tty1 root=PARTUUID=abc rootwait consoleblank=5\n' > "$d/cmdline.txt"
printf '[all]\ndtoverlay=vc4-kms-v3d\n' > "$d/config.txt"
out=$(scripts/pi-setup.sh --boot "$d"); [ "$out" = "boot files updated" ]
[ "$(cat "$d/cmdline.txt")" = "console=tty1 root=PARTUUID=abc rootwait consoleblank=5 video=HDMI-A-1:1280x1024@60D vt.global_cursor_default=0" ]
[ "$(wc -l < "$d/cmdline.txt")" -eq 1 ]
grep -qx hdmi_force_hotplug=1 "$d/config.txt"; grep -qx dtoverlay=disable-bt "$d/config.txt"
cp "$d/config.txt" "$d/before"
out=$(scripts/pi-setup.sh --boot "$d"); [ "$out" = "boot files already set" ]
cmp -s "$d/config.txt" "$d/before"
echo "pi-setup boot edits: ok"

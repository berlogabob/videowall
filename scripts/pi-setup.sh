#!/usr/bin/env bash
# Set up a wall Pi (Raspberry Pi OS Lite). Safe to run again: it only changes what is missing.
#
#   On the Mac, all Pis at once:  scripts/pi-setup.sh wall-{a..e}{1..3}.local
#   On the Mac, a card before first boot:  scripts/pi-setup.sh --boot /Volumes/bootfs
#   On a Pi itself:  sudo bash pi-setup.sh
#
# Remote runs log to logs/<host>.log. A Pi whose boot files changed prints REBOOT NEEDED.
set -euo pipefail

WALL_USER=${WALL_USER:-techlab}
MODE=${MODE:-1280x1024@60}  # the Samsung 720N's native mode
WALL_SERVER=${WALL_SERVER:-192.168.1.131:8080}  # the wall server the client starts against at boot

# Boot files: force the HDMI output on at the monitor's mode (HDMI→VGA adapters often
# report no screen), keep the console from blanking, hide the cursor, switch off Bluetooth and Wi-Fi (cable only: one address per Pi, so wall-XX.local always means the wire).
boot_config() {
  local dir=$1 changed=0 p line tmp
  line=$(head -n1 "$dir/cmdline.txt")
  for p in "video=HDMI-A-1:${MODE}D" consoleblank=0 vt.global_cursor_default=0; do
    case " $line " in *" ${p%%=*}="*) ;; *) line="$line $p"; changed=1 ;; esac
  done
  if [ $changed = 1 ]; then
    tmp=$(mktemp); printf '%s\n' "$line" > "$tmp"; cat "$tmp" > "$dir/cmdline.txt"; rm "$tmp"
  fi
  for p in hdmi_force_hotplug=1 disable_overscan=1 dtoverlay=disable-bt dtoverlay=disable-wifi; do
    grep -qx "$p" "$dir/config.txt" || { printf '%s\n' "$p" >> "$dir/config.txt"; changed=1; }
  done
  return $((1 - changed))  # 0 = something changed
}

remote() {
  local key="" h target pids=() failed=0 i=0
  [ -f ~/.ssh/techlab ] && key="-i $HOME/.ssh/techlab"
  mkdir -p logs
  for h in "$@"; do
    case $h in *@*) target=$h ;; *) target=$WALL_USER@$h ;; esac
    # ponytail: plain ssh in parallel; fine for tens of Pis, a real fleet tool if it ever grows past that
    ssh $key -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$target" \
      "sudo WALL_USER=$WALL_USER MODE=$MODE WALL_SERVER=$WALL_SERVER bash -s" < "$0" > "logs/${h#*@}.log" 2>&1 &
    pids+=($!)
  done
  for i in "${pids[@]}"; do wait "$i" || failed=$((failed + 1)); done
  for h in "$@"; do printf '%-24s %s\n' "${h#*@}" "$(tail -n1 "logs/${h#*@}.log")"; done
  [ $failed = 0 ] || { echo "$failed host(s) failed, see logs/"; exit 1; }
}

on_pi() {
  [ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
  export DEBIAN_FRONTEND=noninteractive
  dpkg --configure -a  # finishes an install cut off by a power dip or dropped link
  apt-get update -q
  apt-get install -y -q mpv chrony curl  # chrony replaces systemd-timesyncd: tighter clocks for play_at
  command -v mpv >/dev/null || { echo "mpv missing after install"; exit 1; }
  timedatectl set-timezone Europe/Lisbon

  su - "$WALL_USER" -c 'command -v uv >/dev/null || [ -x ~/.local/bin/uv ] || curl -LsSf https://astral.sh/uv/install.sh | sh'

  systemctl disable --now bluetooth hciuart 2>/dev/null || true

  # Start the wall client at boot (cron @reboot, not systemd), so a screen comes back by itself after a power dip.
  # It fetches the server's current wall.py first and falls back to the copy it has if the server is not up yet.
  # Supervised: re-fetch and restart after a crash; no wall.py yet (server down at first boot) just retries.
  local line="@reboot sleep 20; while true; do curl -fsSo wall.py.new http://$WALL_SERVER/wall.py && mv wall.py.new wall.py; \
[ -f wall.py ] && ~/.local/bin/uv run --script wall.py --server ws://$WALL_SERVER/ws >> wall.log 2>&1; sleep 10; done"
  { crontab -u "$WALL_USER" -l 2>/dev/null | grep -v 'wall.py --server'; echo "$line"; } | crontab -u "$WALL_USER" -

  local boot=/boot/firmware reboot=""
  [ -f $boot/cmdline.txt ] || boot=/boot
  boot_config $boot && reboot=" REBOOT NEEDED"

  echo "--- $(hostname)"
  tr -d '\0' < /proc/device-tree/model; echo
  free -m | awk '/Mem:/ {print "memory " $2 " MB"}'
  echo "HDMI $(cat /sys/class/drm/card?-HDMI-A-1/status 2>/dev/null || echo '?')"
  echo "ok $(hostname) throttled=$(vcgencmd get_throttled | cut -d= -f2)$reboot"
}

case ${1:-} in
  --boot) boot_config "${2:?card boot folder, e.g. /Volumes/bootfs}" && echo "boot files updated" || echo "boot files already set" ;;
  -h|--help) sed -n '2,8p' "$0" ;;
  "") [ "$(uname)" = Linux ] && on_pi || { sed -n '2,8p' "$0"; exit 1; } ;;
  *) remote "$@" ;;
esac

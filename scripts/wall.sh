#!/usr/bin/env bash
# Start, stop or check the wall client on the Pis, one after another (a parallel burst through the jump host
# gets refused). Commands go over stdin, so pkill -f never matches this ssh session. Needs the ~/.ssh/config block from docs/pi-setup.md.
#
#   scripts/wall.sh start|stop|status [a1 b1 ...]     default: every code of a 5x5 grid
#   SERVER=ws://192.168.1.131:8080/ws scripts/wall.sh start
set -u
cmd=${1:-status}; shift || true
SERVER=${SERVER:-ws://192.168.1.131:8080/ws}
HTTP=${SERVER/ws:/http:}; HTTP=${HTTP%/ws}
codes="$*"
[ -n "$codes" ] || codes=$(for r in 1 2 3 4 5; do for c in a b c d e; do printf '%s%s ' $c $r; done; done)

remote() {
  case $cmd in
    start) echo "pkill -f '[w]all.py --server' ; pkill -x mpv; sleep 1; curl -fsSo wall.py $HTTP/wall.py && \
      (setsid nohup ~/.local/bin/uv run --script wall.py --server $SERVER > wall.log 2>&1 < /dev/null &) && \
      sleep 2 && pgrep -f '[w]all.py --server' > /dev/null && echo started || { echo failed; tail -3 wall.log; }" ;;
    stop) echo "pkill -f '[w]all.py --server'; pkill -x mpv; echo stopped" ;;
    status) echo "pgrep -f '[w]all.py --server' > /dev/null && echo running || echo 'not running'; tail -1 wall.log 2>/dev/null" ;;
    *) echo "usage: $0 start|stop|status [codes]" >&2; exit 2 ;;
  esac
}

for c in $codes; do
  out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes -o LogLevel=ERROR "wall-$c.local" 'bash -s' <<< "$(remote)" 2>&1 | tr '\n' ' ')
  printf '%-4s %s\n' "$c" "${out:-unreachable}"
done

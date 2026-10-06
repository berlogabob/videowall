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

# start runs the same supervised loop as the boot cron line (scripts/pi-setup.sh): fetch wall.py, run it, again 10 s
# after it exits. So a client started by hand also comes back after a crash, and the loop is never lost.
remote() {
  local loop="while true; do curl -fsSo wall.py.new $HTTP/wall.py && mv wall.py.new wall.py; [ -f wall.py ] && ~/.local/bin/uv run --script wall.py --server $SERVER >> wall.log 2>&1; sleep 10; done"
  case $cmd in
    start) echo "pkill -f '[w]all.py --server'; pkill -x mpv; sleep 1; cd ~ && \
      (setsid nohup sh -c '$loop' > /dev/null 2>&1 < /dev/null &) && sleep 4 && \
      { pgrep -f '[w]hile true; do curl' > /dev/null && pgrep -f '[u]v run --script wall.py' > /dev/null && echo started || { echo failed; tail -3 wall.log; }; }" ;;
    stop) echo "pkill -f '[w]all.py --server'; pkill -x mpv; echo stopped" ;;
    status) echo "l=\$(pgrep -f '[w]hile true; do curl' > /dev/null && echo supervised || echo 'no loop'); \
      c=\$(pgrep -f '[u]v run --script wall.py' > /dev/null && echo running || echo 'not running'); echo \"\$c, \$l\"" ;;
    *) echo "usage: $0 start|stop|status [codes]" >&2; exit 2 ;;
  esac
}

for c in $codes; do
  out=$(ssh -o ConnectTimeout=8 -o BatchMode=yes -o LogLevel=ERROR "wall-$c.local" 'bash -s' <<< "$(remote)" 2>&1 | tr '\n' ' ')
  printf '%-4s %s\n' "$c" "${out:-unreachable}"
done

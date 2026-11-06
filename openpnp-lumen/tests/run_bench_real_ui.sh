#!/bin/sh
# REAL MACHINE: Lumen Feeder Firmware Update through OpenPnP, on a copy of ~/.openpnp2 with
# HOME / MOVE commands replaced by an M118 echo (nothing can move).  OpenPnP must be closed.
#   tests/run_bench_real_ui.sh scan [LAST]
#   tests/run_bench_real_ui.sh update IMAGE.bin ADDR
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
OUT=${BENCH_OUT:-$HOME/claude/opulo/_logs}
if pgrep -f '^/usr/lib/jvm/.*openpnp' >/dev/null; then echo "close OpenPnP first (one program per serial port)" >&2; exit 2; fi
WORK=$(mktemp -d)
mkdir -p "$WORK/sandbox/scripts" "$OUT"
cp "$CFG"/*.xml "$WORK/sandbox/"
python3 - "$WORK/sandbox/machine.xml" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
n = 0
for t in ("HOME_COMMAND", "MOVE_TO_COMMAND"):
    s, k = re.subn(r'(<command type="%s">)(.*?)(</command>)' % t,
                   lambda m: m.group(1) + "<text><![CDATA[M118 LUMEN-BENCH-BLOCKED-%s]]></text>" % t + m.group(3), s, flags=re.S)
    n += k
assert n >= 2, "HOME/MOVE commands not found"
open(p, "w").write(s)
print("configuration copy: %d motion command(s) replaced by M118 echo" % n)
PY
TRACE="$OUT/bench-openpnp-trace-$(date +%Y%m%d-%H%M%S).log"
echo "OpenPnP TRACE log: $TRACE"
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/bench_real_ui.py" "$WORK/sandbox" "$TRACE" "$@" && RC=0 || RC=$?
echo "motion G-code in the trace (must be none):"
grep -E ">> *(G0|G1|G28|G92|M17|M18)\b|LUMEN-BENCH-BLOCKED" "$TRACE" | head -5 || true
grep -cE ">> *(G0|G1|G28)\b|LUMEN-BENCH-BLOCKED" "$TRACE" || true
exit $RC

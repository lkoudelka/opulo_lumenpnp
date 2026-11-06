#!/bin/sh
# REAL MACHINE: Lumen Feeder Firmware Update through OpenPnP, on a copy of ~/.openpnp2 with
# HOME / MOVE commands replaced by an M118 echo (nothing can move).  OpenPnP must be closed.
#   tests/run_bench_real_ui.sh scan [LAST]
#   tests/run_bench_real_ui.sh update IMAGE.bin ADDR
#   tests/run_bench_real_ui.sh preflight ADDR UUID     (HOMES the machine: only HOME allowed, MOVE stays blocked)
#   tests/run_bench_real_ui.sh exec SNIPPET.py [ARGS]   (MOVES: homing, then the reviewed snippet)
#   tests/run_bench_real_ui.sh verify ADDR             (MOVES: homing incl. visual homing, camera images, ONE 4 mm feed)
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
python3 - "$WORK/sandbox/machine.xml" "$1" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
n = 0
for t in {"preflight": ("MOVE_TO_COMMAND",), "verify": (), "exec": ()}.get(sys.argv[2], ("HOME_COMMAND", "MOVE_TO_COMMAND")):
    s, k = re.subn(r'(<command type="%s">)(.*?)(</command>)' % t,
                   lambda m: m.group(1) + "<text><![CDATA[M118 LUMEN-BENCH-BLOCKED-%s]]></text>" % t + m.group(3), s, flags=re.S)
    n += k
assert n >= 1 or sys.argv[2] in ("verify", "exec"), "HOME/MOVE commands not found"
open(p, "w").write(s)
print("configuration copy: %d motion command(s) replaced by M118 echo" % n)
PY
python3 - "$WORK/sandbox/machine.xml" <<'PY'
# cameras: the unique-id of the LumenPnP cameras connected NOW (V4L2 card name + bus info),
# as selecting them in OpenPnP's camera setup would store it (copy only)
import fcntl, glob, os, re, sys
p = sys.argv[1]
s = open(p).read()
for d in sorted(glob.glob("/dev/video*")):
    try:
        fd = os.open(d, os.O_RDWR)
        buf = bytearray(104)
        fcntl.ioctl(fd, 0x80685600, buf)          # VIDIOC_QUERYCAP
        os.close(fd)
    except OSError:
        continue
    card = buf[16:48].split(b"\0")[0].decode()
    bus = buf[48:80].split(b"\0")[0].decode()
    for role in ("Top", "Bottom"):
        if card.startswith("LumenPnP %s" % role):
            s, n = re.subn(r'unique-id="LumenPnP %s:[^"]*"' % role, 'unique-id="%s %s"' % (card, bus), s)
            if n:
                print("camera %s -> '%s %s' (%s)" % (role, card, bus, d))
open(p, "w").write(s)
PY
TRACE="$OUT/bench-openpnp-trace-$(date +%Y%m%d-%H%M%S).log"
echo "OpenPnP TRACE log: $TRACE"
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/bench_real_ui.py" "$WORK/sandbox" "$TRACE" "$@" && RC=0 || RC=$?
echo "motion G-code in the trace (must be none):"
grep -E ">> *(G0|G1|G28|G92|M17|M18)\b|LUMEN-BENCH-BLOCKED" "$TRACE" | head -5 || true
echo "G0/G1 moves: $(grep -cE '>> *(G0|G1)\b' "$TRACE")   G28 homing: $(grep -cE '>> *G28\b' "$TRACE")   blocked attempts: $(grep -c 'LUMEN-BENCH-BLOCKED' "$TRACE")"
exit $RC

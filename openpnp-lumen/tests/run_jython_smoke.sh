#!/bin/sh
# lib/lumen/photon.py inside OpenPnP's bundled Jython against the photon bus simulator.
#   tests/run_jython_smoke.sh photon-lumenpnp-v1.0.7.bin
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BF=${PHOTON_BUSFLASH:-$HOME/claude/opulo/_dev/photon/dev/busflash}
JY=${JYTHON_JAR:-/opt/openpnp/lib/jython-standalone-2.7.1.jar}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
PY=${PY:-python3}
WORK=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
"$PY" - "$1" "$WORK" "$BF" <<'EOF'
import sys, os
sys.path.insert(0, os.path.join(sys.argv[3], "tests"))
import run_sim_tests as rst
rel = open(sys.argv[1], "rb").read(); w = sys.argv[2]
pbl = open(os.path.join(sys.argv[3], "bootloader", "build", "pbl.bin"), "rb").read()
open(os.path.join(w, "new.bin"), "wb").write(rst.make_app(rel, "v1.1.9"))
rst.flash_file(os.path.join(w, "f1.bin"), rel)
for a in (2, 3):
    rst.flash_file(os.path.join(w, "f%d.bin" % a), rst.make_app(rel, "v1.1.8"), pbl)
EOF
"$PY" "$BF/sim/marlin_sim.py" --port-file "$WORK/port" --feeder "1:$WORK/f1.bin" --feeder "2:$WORK/f2.bin" \
    --feeder "3:$WORK/f3.bin" > /dev/null 2> "$WORK/sim.log" &
SIM=$!
trap 'kill $SIM 2>/dev/null' EXIT
for i in $(seq 1 50); do [ -s "$WORK/port" ] && break; sleep 0.1; done
"$JAVA" -jar "$JY" "$HERE/jython_smoke.py" "$WORK" "$(cat "$WORK/port")"

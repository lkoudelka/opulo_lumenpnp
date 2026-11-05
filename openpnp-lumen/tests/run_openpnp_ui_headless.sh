#!/bin/sh
# Menu scripts' own code, headless, against real OpenPnP classes + the photon bus simulator.
#   tests/run_openpnp_ui_headless.sh photon-lumenpnp-v1.0.7.bin
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
BF=${PHOTON_BUSFLASH:-$HOME/claude/opulo/_dev/photon/dev/busflash}
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
PY=${PY:-python3}
STOCK=${OPENPNP_STOCK_CONFIG:-$HOME/claude/opulo/_downloads/openpnp2-stock-defaults}
WORK=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
mkdir -p "$WORK/sandbox/scripts"; cp "$STOCK"/*.xml "$WORK/sandbox/"
"$PY" - "$1" "$WORK" "$BF" <<'PY'
import sys, os
sys.path.insert(0, os.path.join(sys.argv[3], "tests"))
import run_sim_tests as rst
rel = open(sys.argv[1], "rb").read(); w = sys.argv[2]
pbl = open(os.path.join(sys.argv[3], "bootloader", "build", "pbl.bin"), "rb").read()
open(os.path.join(w, "new.bin"), "wb").write(rst.make_app(rel, "v1.1.9"))
rst.flash_file(os.path.join(w, "f1.bin"), rel)
for a in (2, 3):
    rst.flash_file(os.path.join(w, "f%d.bin" % a), rst.make_app(rel, "v1.1.8"), pbl)
PY
"$PY" "$BF/sim/marlin_sim.py" --port-file "$WORK/port" --feeder "1:$WORK/f1.bin:$(printf 'a1%.0s' $(seq 12))" \
    --feeder "2:$WORK/f2.bin:$(printf 'a2%.0s' $(seq 12))" --feeder "3:$WORK/f3.bin:$(printf 'a3%.0s' $(seq 12))" \
    > /dev/null 2> "$WORK/sim.log" &
SIM=$!
trap 'kill $SIM 2>/dev/null' EXIT
for i in $(seq 1 50); do [ -s "$WORK/port" ] && break; sleep 0.1; done
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/openpnp_ui_headless.py" "$WORK/sandbox" "$WORK" "$(cat "$WORK/port")"

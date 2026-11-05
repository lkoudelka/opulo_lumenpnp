#!/bin/sh
# Orientation Setup headless with real OpenPnP classes and the real feeder mainboard (.kicad_pcb).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
STOCK=${OPENPNP_STOCK_CONFIG:-$HOME/claude/opulo/_downloads/openpnp2-stock-defaults}
KICAD=${KICAD_PCB:-$HOME/claude/opulo/opulo_feeder/pcb/mobo/mobo.kicad_pcb}
WORK=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
mkdir -p "$WORK/sandbox/scripts" "$WORK/png"; cp "$STOCK"/*.xml "$WORK/sandbox/"
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/openpnp_orientation_headless.py" "$WORK/sandbox" "$KICAD" "$WORK/png"

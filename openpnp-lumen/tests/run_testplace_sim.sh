#!/bin/sh
# Test placement (Orientation Setup) on OpenPnP's simulated machine (stock config), headless.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
STOCK=${OPENPNP_STOCK_CONFIG:-$HOME/claude/opulo/_downloads/openpnp2-stock-defaults}
WORK=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
mkdir -p "$WORK/sandbox/scripts" "$WORK/png"; cp "$STOCK"/*.xml "$WORK/sandbox/"
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/openpnp_testplace_sim.py" "$WORK/sandbox" "$WORK/png"

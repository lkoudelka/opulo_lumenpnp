#!/bin/sh
# Lumen library against the real OpenPnP 2.6 classes, headless, in a sandbox config dir
# (copy of OpenPnP's stock simulated configuration; ~/.openpnp2 is not used).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
STOCK=${OPENPNP_STOCK_CONFIG:-$HOME/claude/opulo/_downloads/openpnp2-stock-defaults}
SB=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
cp "$STOCK"/*.xml "$SB/"
mkdir -p "$SB/scripts"
"$JAVA" -Djava.awt.headless=true \
    --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt.color=ALL-UNNAMED -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" \
    org.python.util.jython "$HERE/openpnp_headless.py" "$SB"

#!/bin/sh
# Pick vacuum check / feed hook / identify, real OpenPnP classes, copy of ~/.openpnp2, NO machine.
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
[ -f "$CFG/machine.xml" ] || { echo "(no configuration: skipped)"; exit 0; }
W=$(mktemp -d); mkdir -p "$W/sandbox/scripts"; cp "$CFG"/*.xml "$W/sandbox/"
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/openpnp_pickvac_offline.py" "$W/sandbox"

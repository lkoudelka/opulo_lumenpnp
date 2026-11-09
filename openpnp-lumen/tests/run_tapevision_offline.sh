#!/bin/sh
# Sprocket-hole geometry with OpenPnP's OpenCV (the Java path the machine uses), offline on real images.
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
D=${FEEDER_IMAGES:-$HOME/claude/opulo/_testdata/feeder-images}
ls "$D"/look-slot4-raw*.png >/dev/null 2>&1 || { echo "(no raw bench images in $D: skipped)"; exit 0; }
exec "$JAVA" -Djava.awt.headless=true -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/openpnp_tapevision_offline.py" "$D"

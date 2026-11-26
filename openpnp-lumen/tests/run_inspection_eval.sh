#!/bin/sh
# Placement inspection over a test set (see tests/inspection_eval.py).
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
exec "$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/inspection_eval.py" "$@"

#!/bin/sh
# Install into a sandbox COPY of the real ~/.openpnp2 and check OpenPnP still loads it.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
SRC=${OPENPNP_CONFIG_SRC:-$HOME/.openpnp2}
SB=$(mktemp -d ${SIM_WORKDIR:+-p "$SIM_WORKDIR"})
cp "$SRC"/*.xml "$SB/"; mkdir -p "$SB/scripts/Events"
before=$(cd "$SB" && sha256sum *.xml)
OPENPNP_CONFIG="$SB" "$HERE/../install.sh" --journal > /dev/null
after=$(cd "$SB" && sha256sum *.xml)
[ "$before" = "$after" ] && echo "  [PASS] installer changed no configuration file" || { echo "  [FAIL] installer changed configuration files"; exit 1; }
NF=$(python3 -c "import xml.etree.ElementTree as E,sys; print(len([f for f in E.parse(sys.argv[1]).getroot().iter('feeder') if f.get('class')]))" "$SB/machine.xml")
NP=$(python3 -c "import xml.etree.ElementTree as E,sys; print(len(list(E.parse(sys.argv[1]).getroot().iter('part'))))" "$SB/parts.xml")
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt=ALL-UNNAMED --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython \
    "$HERE/openpnp_config_compat.py" "$SB" "$NF" "$NP"
OPENPNP_CONFIG="$SB" "$HERE/../uninstall.sh" > /dev/null
[ -z "$(find "$SB/scripts" -type l)" ] && echo "  [PASS] uninstall removed all links"

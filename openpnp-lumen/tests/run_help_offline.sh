#!/bin/sh
# In-tool help of every Lumen tool: headless, real OpenPnP classes, copy of ~/.openpnp2, test job, NO machine.
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
JOB=${INSPECT_JOB:-$HOME/claude/opulo/_test_session/WBA_panel_test.job.xml}
[ -f "$CFG/machine.xml" ] && [ -f "$JOB" ] || { echo "(configuration or test job missing: skipped)"; exit 0; }
W=$(mktemp -d); mkdir -p "$W/sandbox/scripts" "$W/png"; cp "$CFG"/*.xml "$W/sandbox/"
LOCAL=${INSPECT_BOARD_DIR:-$HOME/claude/opulo/pnp}
python3 - "$JOB" "$W/job.job.xml" "$LOCAL" <<'PY'
import os, re, sys
s = open(sys.argv[1]).read()
def fix(m):
    p = m.group(1); alt = os.path.join(sys.argv[3], os.path.basename(p))
    return 'file-name="%s"' % (p if os.path.exists(p) or not os.path.exists(alt) else alt)
open(sys.argv[2], "w").write(re.sub(r'file-name="([^"]+)"', fix, s))
PY
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED \
    --add-opens=java.desktop/java.awt.color=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/openpnp_help_offline.py" "$W/sandbox" "$W/job.job.xml" "$W/png"
RC=$?
[ -n "$HELP_PNG_KEEP" ] && cp "$W"/png/*.png "$HELP_PNG_KEEP"/ 2>/dev/null
exit $RC

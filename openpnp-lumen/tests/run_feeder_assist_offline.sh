#!/bin/sh
# Feeder Assistant: real OpenPnP classes, COPIES of ~/.openpnp2, the test job AND its board files, NO machine.
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
JOB=${INSPECT_JOB:-$HOME/claude/opulo/_test_session/WBA_panel_test.job.xml}
[ -f "$CFG/machine.xml" ] && [ -f "$JOB" ] || { echo "(configuration or test job missing: skipped)"; exit 0; }
W=$(mktemp -d); mkdir -p "$W/sandbox/scripts" "$W/png" "$W/boards"; cp "$CFG"/*.xml "$W/sandbox/"
LOCAL=${INSPECT_BOARD_DIR:-$HOME/claude/opulo/pnp}
# job copy whose boards are copies too (Apply saves board files: never the real ones)
python3 - "$JOB" "$W/job.job.xml" "$LOCAL" "$W/boards" <<'PY' || exit 1
import os, re, shutil, sys
s = open(sys.argv[1]).read()
def fix(m):
    p = m.group(1)
    src = p if os.path.exists(p) else os.path.join(sys.argv[3], os.path.basename(p))
    if not os.path.exists(src):
        sys.exit("board file %s not found" % p)
    dst = os.path.join(sys.argv[4], os.path.basename(p))
    shutil.copy(src, dst)
    return 'file-name="%s"' % dst
open(sys.argv[2], "w").write(re.sub(r'file-name="([^"]+)"', fix, s))
PY
"$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED \
    -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/openpnp_feeder_assist_offline.py" \
    "$W/sandbox" "$W/job.job.xml" "$W/png" "$W/boards"
RC=$?
[ -n "$ASSIST_PNG_KEEP" ] && cp "$W"/png/*.png "$ASSIST_PNG_KEEP"/ 2>/dev/null
exit $RC

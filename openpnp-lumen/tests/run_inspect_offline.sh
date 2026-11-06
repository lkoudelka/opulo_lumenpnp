#!/bin/sh
RC=0
# Placement inspection analysis with OpenPnP's OpenCV, offline (no machine): semi-synthetic images.
HERE=$(cd "$(dirname "$0")" && pwd)
OPENPNP=${OPENPNP_HOME:-/opt/openpnp}
JAVA=${JAVA:-/usr/lib/jvm/java-17-openjdk-amd64/bin/java}
D=${INSPECT_IMAGES:-$HOME/claude/opulo/_testdata/inspection}
[ -f "$D/truth.json" ] || ${PY:-python3} "$HERE/make_inspection_images.py" "$D" || { echo "(cannot make test images: skipped)"; exit 0; }
"$JAVA" -Djava.awt.headless=true -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/openpnp_inspect_offline.py" "$D" || RC=1
JOB=${INSPECT_JOB:-$HOME/claude/opulo/_test_session/WBA_panel_test.job.xml}
if [ -f "$JOB" ] && [ -f "$HOME/.openpnp2/machine.xml" ]; then
    W=$(mktemp -d); mkdir -p "$W/sandbox/scripts"; cp "$HOME"/.openpnp2/*.xml "$W/sandbox/"
    # board files the job points to but that are missing (e.g. USB stick removed): use the local copy
    LOCAL=${INSPECT_BOARD_DIR:-$HOME/claude/opulo/pnp}
    python3 - "$JOB" "$W/job.job.xml" "$LOCAL" <<'PY'
import os, re, sys
s = open(sys.argv[1]).read()
def fix(m):
    p = m.group(1)
    alt = os.path.join(sys.argv[3], os.path.basename(p))
    return 'file-name="%s"' % (p if os.path.exists(p) or not os.path.exists(alt) else alt)
open(sys.argv[2], "w").write(re.sub(r'file-name="([^"]+)"', fix, s))
PY
    JOB="$W/job.job.xml"
    "$JAVA" -Djava.awt.headless=true --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED \
        -cp "$(ls $OPENPNP/openpnp-gui-*.jar):$OPENPNP/lib/*" org.python.util.jython "$HERE/openpnp_inspect_ui_offline.py" "$W/sandbox" "$D" "$JOB" || RC=1
else
    echo "(user job / configuration not found: UI test skipped)"
fi
exit $RC

#!/bin/sh
# Install the Lumen scripts into OpenPnP (links into this checkout; nothing is copied).
#   ./install.sh             menu scripts: Scripts > Lumen > ...   (no event hooks)
#   ./install.sh --journal   additionally the placement journal hook (Events/Job.Placement.Complete.py)
#   ./uninstall.sh           removes exactly what this installed
# OpenPnP: Scripts > Refresh Scripts (or restart) afterwards.  machine.xml is not touched.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
mkdir -p "$CFG/scripts/Events" "$CFG/lumen"

link() {   # link SRC DST : refuse to replace anything that is not already our link
    if [ -L "$2" ] || [ ! -e "$2" ]; then
        ln -sfn "$1" "$2"; echo "linked $2 -> $1"
    else
        echo "NOT replacing existing $2 (not created by this installer)" >&2; exit 1
    fi
}
link "$HERE/scripts/Lumen" "$CFG/scripts/Lumen"
link "$HERE/lib" "$CFG/lumen/lib"
if [ "$1" = "--journal" ]; then
    link "$HERE/events/Job.Placement.Complete.py" "$CFG/scripts/Events/Job.Placement.Complete.py"
fi
echo "done. In OpenPnP: Scripts > Refresh Scripts, then Scripts > Lumen."

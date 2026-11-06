#!/bin/sh
# Install the Lumen scripts into OpenPnP (links into this checkout; nothing is copied).
#   ./install.sh             menu scripts: Scripts > Lumen > ... and the inert feed hook
#                            Events/Feeder.BeforeFeed.py (acts only for feeders ticked "While feeding") and
#                            Events/Nozzle.AfterPick.py (acts only with "Pick vacuum check" enabled)
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
link "$HERE/events/Feeder.BeforeFeed.py" "$CFG/scripts/Events/Feeder.BeforeFeed.py"
link "$HERE/events/Nozzle.AfterPick.py" "$CFG/scripts/Events/Nozzle.AfterPick.py"
if [ "$1" = "--journal" ]; then
    link "$HERE/events/Job.Placement.Complete.py" "$CFG/scripts/Events/Job.Placement.Complete.py"
fi
echo "done. In OpenPnP: Scripts > Refresh Scripts, then Scripts > Lumen."

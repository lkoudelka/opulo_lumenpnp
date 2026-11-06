#!/bin/sh
# Remove the links created by install.sh (settings, logs and the journal in ~/.openpnp2/lumen stay).
HERE=$(cd "$(dirname "$0")" && pwd)
CFG=${OPENPNP_CONFIG:-$HOME/.openpnp2}
for p in "$CFG/scripts/Lumen" "$CFG/lumen/lib" "$CFG/scripts/Events/Job.Placement.Complete.py" "$CFG/scripts/Events/Feeder.BeforeFeed.py"; do
    if [ -L "$p" ] && case "$(readlink "$p")" in "$HERE"/*) true;; *) false;; esac; then
        rm "$p"; echo "removed $p"
    fi
done

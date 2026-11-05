#!/bin/sh
# All tests of openpnp-lumen.   tests/run_all.sh photon-lumenpnp-v1.0.7.bin
# Needs: python3 with pyserial (PY=...), the photon fork dev worktree (PHOTON_BUSFLASH=.../busflash,
# with bootloader/build/pbl.bin and sim/pbl_sim built), OpenPnP 2.6 in /opt/openpnp.
HERE=$(cd "$(dirname "$0")" && pwd)
REL=${1:?usage: run_all.sh RELEASE.bin}
RC=0
for t in "test_photon_sim.py" "test_learning.py" "test_orientation.py" "run_jython_smoke.sh" "run_openpnp_headless.sh" "run_openpnp_ui_headless.sh" \
         "run_orientation_headless.sh" "run_config_compat.sh" "test_profiles.py"; do
    echo "=== $t"
    case $t in
        test_learning.py|test_profiles.py|test_orientation.py) ${PY:-python3} "$HERE/$t" ;;
        *.py) ${PY:-python3} "$HERE/$t" "$REL" ;;
        run_openpnp_headless.sh|run_config_compat.sh|run_orientation_headless.sh) "$HERE/$t" ;;
        *) "$HERE/$t" "$REL" ;;
    esac > "${TMPDIR:-/tmp}/lumen-test.out" 2>&1 || RC=1
    grep -E "\[FAIL\]|checks passed|SMOKE|\[PASS\] (installer|uninstall)" "${TMPDIR:-/tmp}/lumen-test.out"
done
[ $RC = 0 ] && echo "ALL TEST SUITES PASSED" || echo "SOME TESTS FAILED"
exit $RC

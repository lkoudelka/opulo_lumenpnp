#!/bin/sh
# All tests of openpnp-lumen.   tests/run_all.sh photon-lumenpnp-v1.0.7.bin
# Needs: python3 with pyserial (PY=...), the photon fork dev worktree (PHOTON_BUSFLASH=.../busflash,
# with bootloader/build/pbl.bin and sim/pbl_sim built), OpenPnP 2.6 in /opt/openpnp.
HERE=$(cd "$(dirname "$0")" && pwd)
REL=${1:?usage: run_all.sh RELEASE.bin}
RC=0
for t in "test_photon_sim.py" "test_learning.py" "test_orientation.py" "test_tapevision.py" "test_pickvac.py" "test_feederopts.py" "test_partmatch.py" "test_testplace.py" "run_jython_smoke.sh" "run_openpnp_headless.sh" "run_openpnp_ui_headless.sh" \
         "run_orientation_headless.sh" "run_inspect_offline.sh" "run_pickvac_offline.sh" "run_help_offline.sh" "run_feeder_assist_offline.sh" "run_testplace_sim.sh" "run_config_compat.sh" "test_profiles.py"; do
    echo "=== $t"
    case $t in
        test_learning.py|test_profiles.py|test_orientation.py|test_tapevision.py|test_pickvac.py|test_feederopts.py|test_partmatch.py|test_testplace.py) ${PY:-python3} "$HERE/$t" ;;
        *.py) ${PY:-python3} "$HERE/$t" "$REL" ;;
        run_openpnp_headless.sh|run_config_compat.sh|run_orientation_headless.sh|run_inspect_offline.sh|run_pickvac_offline.sh|run_help_offline.sh|run_feeder_assist_offline.sh|run_testplace_sim.sh) "$HERE/$t" ;;
        *) "$HERE/$t" "$REL" ;;
    esac > "${TMPDIR:-/tmp}/lumen-test.out" 2>&1
    trc=$?
    [ $trc = 0 ] || RC=1
    grep -E "\[FAIL\]|checks passed|SMOKE|\[PASS\] (installer|uninstall)" "${TMPDIR:-/tmp}/lumen-test.out" \
        || { echo "   (exit $trc, no result line - last lines of the output:)"; tail -15 "${TMPDIR:-/tmp}/lumen-test.out" | sed 's/^/   | /'; }
done
[ $RC = 0 ] && echo "ALL TEST SUITES PASSED" || echo "SOME TESTS FAILED"
exit $RC

# Scripting engines pooled only while a job runs (lib/lumen/enginepool.py), with OpenPnP's real Scripting object on
# the stock simulated machine, headless.  The job state comes from a list instead of the job panel.
#   tests/run_enginepool_sim.sh
import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sandbox = sys.argv[1]

from java.io import File
from java.lang import System as _Sys
from org.openpnp.model import Configuration

Configuration.initialize(File(sandbox))
Configuration.get().load()
machine = Configuration.get().getMachine()
eng = Configuration.get().getScripting()
results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    _Sys.out.println("  [%s] %s %s" % ("PASS" if cond else "FAIL", name, detail))


from lumen import enginepool as ep


class Settings(object):
    def __init__(self, d=None):
        self.data = dict(d or {})

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v


script = os.path.join(sandbox, "probe.py")
with open(script, "w") as f:
    f.write("x = 1\n")


def run_script():
    eng.execute(File(script), {})


state = ["Stopped"]
machine.setPoolScriptingEngines(False)
st = Settings()
auto = ep.start(machine, eng, st, lambda: state[0], timer="test")
check("configuration has pooling off -> automatic mode installed", auto is not None and ep.is_auto())
auto.tick()
check("Stopped: not pooled", not machine.isPoolScriptingEngines())
state[0] = "Running"
auto.tick()
run_script()
run_script()
check("Running: pooled, the engine stays in the pool between script runs",
      machine.isPoolScriptingEngines() and eng.getScriptingEnginePoolObjectCount() >= 1 and st.get(ep.MARK),
      eng.getScriptingEnginePoolObjectCount())
state[0] = "Pausing"
auto.tick()
check("Pausing (current step finishing, hooks may still run): still pooled", machine.isPoolScriptingEngines())
state[0] = "Paused"
text = auto.tick()
check("Paused: pooling off and the pool emptied (fresh code for the next run)",
      not machine.isPoolScriptingEngines() and eng.getScriptingEnginePoolObjectCount() == 0 and not st.get(ep.MARK), text)
run_script()
check("while paused a script runs on a new engine, nothing is pooled", eng.getScriptingEnginePoolObjectCount() == 0)
state[0] = "Running"
auto.tick()
state[0] = "Stopped"
auto.tick()
check("Running again -> Stopped: off again", not machine.isPoolScriptingEngines())
machine.setPoolScriptingEngines(True)
st2 = Settings({ep.MARK: True})
a2 = ep.start(machine, eng, st2, lambda: "Stopped", timer="test")
check("left on by the automatic mode (configuration saved during a job): switched off at start, automatic again",
      a2 is not None and not machine.isPoolScriptingEngines() and not st2.get(ep.MARK))
machine.setPoolScriptingEngines(True)
a3 = ep.start(machine, eng, Settings(), lambda: "Stopped", timer="test")
check("pooling on in the configuration (by the person): left alone, no automatic mode",
      a3 is None and machine.isPoolScriptingEngines() and not ep.is_auto())
_Sys.out.println("\n%d/%d checks passed" % (sum(results), len(results)))
_Sys.exit(0 if all(results) else 1)

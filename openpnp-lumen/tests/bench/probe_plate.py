from lumen import zprobe
reload(zprobe)
n1 = machine.getDefaultHead().getNozzles()[0]
r = oppnp.run_machine_task(machine, lambda: zprobe.probe(n1, 230.0, 186.0, 5.1, 3.0, max_travel=2.1, log=say))
say("  plate Z %.3f  tail %s  -> disc thickness %.2f mm" % (r["z"], r["readings"][-4:], 5.45 - r["z"]))
check("plate probed", True)

# Scripts > Lumen > Feeder Part Check on feeders 50 (empty tape) and 48 (0402 caps): camera only
g, cls = load_script("Feeder_Part_Check.py")
d = g[cls]()
names = {"0046000F4248570320363931": 50, "001980104648570520333535": 48}
for x in d.model.rows:
    x["sel"] = str(x["feeder"].getHardwareId()).upper() in names
d.check()
wait_idle(d, 300)
for i, x in enumerate(d.model.rows):
    if x["sel"]:
        say("  | " + " | ".join(str(d.model.getValueAt(i, c)) for c in range(1, 9)))
        say("    image: %s" % (x.get("res") or {}).get("image"))
r50 = [x for x in d.model.rows if str(x["feeder"].getHardwareId()).upper() == "0046000F4248570320363931"][0]["res"]
r48 = [x for x in d.model.rows if str(x["feeder"].getHardwareId()).upper() == "001980104648570520333535"][0]["res"]
check("feeder 50 found by OpenPnP on slot 50, pick location = configured", r50.get("slot") == 50 and abs(r50["pick"][0] - 29.258) < 0.01, r50.get("pick"))
check("feeder 50: tape found, pitch 2 mm, pick pocket EMPTY", r50.get("pitch_mm") and abs(r50["pitch_mm"] - 2) < 0.1 and r50.get("part_at_pick") is False, r50)
check("feeder 48: part at pick detected", r48.get("part_at_pick") is True, r48)

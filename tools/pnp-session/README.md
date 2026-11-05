# pnp-session: record what was done on the machine

For debug and usability sessions. You do things on the LumenPnP and describe them in plain words; the session folder contains the exact machine-side record. Whoever fixes it later can see precisely what happened.

```
pnp-session start "feeder setup for job X"     # before you begin
pnp-session mark "homed, now teaching feeder 3" # any time (or OpenPnP: Scripts > Session > Mark)
pnp-session stop                                # at the end, then fill in notes.md
```

## What is recorded

| File | Content |
|---|---|
| `notes.md` | Your words: goal, what you did, what was not good, ideas. Template provided. |
| `marks.log` | Timestamped marks from the CLI. The OpenPnP menu marks are in the OpenPnP log. |
| `openpnp/` | OpenPnP logs written during the session. At **TRACE** level they contain every G-code line sent and every reply (including `M485` feeder packets), every warning and every exception. |
| `tools/` | Logs from the other tools during the session (busflash, paste utility, leash; `~/claude/opulo/_logs`) |
| `config.diff` | What changed in `~/.openpnp2` (machine.xml, parts, packages, vision, scripts) between start and stop |
| `summary.md` | Timeline (your marks + homing/job/feeder events + errors), grouped warnings/errors, exceptions, G-code and feeder-bus statistics |
| `session.json` | Times, log level, config snapshot ids, git revisions of the repos, USB devices |

## What it changes
- **Log level.** OpenPnP's log level preference (Java prefs, `LogPanel.logLevel`) is set to TRACE at `start`, but only when OpenPnP is **not** running, and restored at `stop`. If OpenPnP is running, set it in the *Log* tab yourself (Global level: TRACE).
- **Config history.** The history of `~/.openpnp2` is kept in a **separate** git repository (`_sessions/.openpnp2-history.git`), so nothing is added inside `~/.openpnp2`.
- **Mark menu entry.** `pnp-session install-openpnp-script` copies `Scripts > Session > Mark` into `~/.openpnp2/scripts/Session/`. It is a menu entry only, with no event hooks.

Environment overrides for testing: `PNP_SESSION_DIR`, `OPENPNP_CONFIG`, `PNP_TOOL_LOGS`, `PNP_JAVA_PREFS`.

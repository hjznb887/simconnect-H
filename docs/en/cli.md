# CLI reference (`simconnect-h`)

Zero extra dependencies — installed with `pip install -e .`.

## Prerequisites

MSFS running, in flight, not paused (same as Python API).

## Commands

### `ping`

Test connectivity by reading `PLANE ALTITUDE`.

```powershell
simconnect-h ping
# OK  PLANE ALTITUDE = 12500.0 ft
```

### `get`

Read one SimVar.

```powershell
simconnect-h get "PLANE ALTITUDE" feet
simconnect-h get TITLE --string
simconnect-h get "AIRSPEED INDICATED" --timeout 5
```

**Unit auto-fill:** if the variable is in the built-in catalog (`common_simvars.json`, ~182 entries) and you omit the unit, the CLI uses the catalog's recommended unit. String SimVars are detected from the catalog or `--string`.

If unit is required and missing:

```
FAIL  unit required (try: simconnect-h search PLANE)
```

### `set`

Write one SimVar.

```powershell
simconnect-h set "GENERAL ENG THROTTLE LEVER POSITION:1" 0.5 percent
simconnect-h set TITLE "My Aircraft" --string
```

Unit auto-fill works like `get`.

### `watch`

Subscribe and print values for N seconds (default 10).

```powershell
simconnect-h watch "AIRSPEED INDICATED" knots --seconds 10
simconnect-h watch TITLE --string --seconds 5
```

### `trigger`

Fire an MSFS event.

```powershell
simconnect-h trigger AP_MASTER
simconnect-h trigger TOGGLE_FLIGHT_DIRECTOR 1
```

### `search`

Search the built-in catalog: **~182 SimVars** and **~69 events**.

```powershell
simconnect-h search altitude
simconnect-h search throttle
simconnect-h search ap --events-only
simconnect-h search plane --simvars-only
simconnect-h search fuel --limit 20
```

Output columns:

```
SimVar  PLANE ALTITUDE  feet  dtype=4
Event   AP_MASTER             autopilot,master
```

Flags:

| Flag | Effect |
|------|--------|
| `--events-only` | Search events only |
| `--simvars-only` | Search SimVars only |
| `--limit N` | Max rows (default 40) |

Use `search` to find variable names and units before `get` / `set`.

### `doctor`

Runs [`examples/diagnose_read.py`](../../examples/diagnose_read.py) for detailed connection diagnostics. Exit code propagates to the shell.

```powershell
simconnect-h doctor
```

## Examples

```powershell
pip install -e .

# Quick check
simconnect-h ping

# Find a variable, then read it
simconnect-h search indicated airspeed
simconnect-h get "AIRSPEED INDICATED" knots

# Live stream
simconnect-h watch "PLANE HEADING DEGREES TRUE" degrees --seconds 15

# Event
simconnect-h search gear --events-only
simconnect-h trigger GEAR_TOGGLE
```

## Catalog data

SimVar and event lists ship in `simconnect_native/data/`. They cover common flight variables — not the full MSFS SDK list. For unknown variables, pass unit manually or consult MSFS SDK documentation.

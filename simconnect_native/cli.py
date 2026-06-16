"""simconnect-h command-line tool (zero extra dependencies)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _data_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "data" / name


def _load_json(name: str) -> List[dict]:
    try:
        pkg = resources.files("simconnect_native").joinpath(f"data/{name}")
        return json.loads(pkg.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(_data_path(name).read_text(encoding="utf-8"))


def _load_simvars() -> List[dict]:
    return _load_json("common_simvars.json")


def _load_events() -> List[dict]:
    return _load_json("common_events.json")


def _simvar_index() -> Dict[str, dict]:
    idx: Dict[str, dict] = {}
    for row in _load_simvars():
        idx[row["name"].strip().upper()] = row
    return idx


def _lookup_simvar(name: str) -> Optional[dict]:
    return _simvar_index().get(name.strip().upper())


def _connect(app_name: str = "simconnect-h"):
    from simconnect_native import SimConnect

    sc = SimConnect()
    sc.connect(app_name, timeout=8.0)
    return sc


def cmd_ping(_args: argparse.Namespace) -> int:
    try:
        with _connect() as sc:
            alt = sc.get("PLANE ALTITUDE", "feet", timeout=3.0)
            print(f"OK  PLANE ALTITUDE = {alt:.1f} ft")
            return 0
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


def cmd_get(args: argparse.Namespace) -> int:
    try:
        row = _lookup_simvar(args.var)
        use_string = args.string or (row and row.get("string"))
        unit = args.unit
        if not use_string and not unit and row:
            unit = row.get("unit", "")
        with _connect() as sc:
            if use_string:
                val = sc.get_string(args.var, timeout=args.timeout)
            else:
                if not unit:
                    print(
                        "FAIL  unit required (try: simconnect-h search "
                        f"{args.var.split()[0].lower()})",
                        file=sys.stderr,
                    )
                    return 1
                val = sc.get(args.var, unit, timeout=args.timeout)
            print(val)
            return 0
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


def cmd_set(args: argparse.Namespace) -> int:
    try:
        row = _lookup_simvar(args.var)
        use_string = args.string or (row and row.get("string"))
        unit = args.unit
        if not use_string and not unit and row:
            unit = row.get("unit", "")
        with _connect() as sc:
            if use_string:
                sc.set_string(args.var, args.value)
            else:
                if not unit:
                    print("FAIL  unit required", file=sys.stderr)
                    return 1
                sc.set(args.var, float(args.value), unit)
            print("OK")
            return 0
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


def cmd_watch(args: argparse.Namespace) -> int:
    from simconnect_native import SIMCONNECT_PERIOD_SECOND

    try:
        row = _lookup_simvar(args.var)
        use_string = args.string or (row and row.get("string"))
        unit = args.unit
        if not use_string and not unit and row:
            unit = row.get("unit", "")
        with _connect() as sc:

            def on_val(v: Any) -> None:
                print(f"{args.var} = {v}")

            if use_string:
                sc.subscribe_string(args.var, on_val, period=SIMCONNECT_PERIOD_SECOND)
            else:
                if not unit:
                    print("FAIL  unit required", file=sys.stderr)
                    return 1
                sc.subscribe(args.var, unit, on_val, period=SIMCONNECT_PERIOD_SECOND)
            time.sleep(args.seconds)
            return 0
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


def cmd_trigger(args: argparse.Namespace) -> int:
    try:
        with _connect() as sc:
            sc.trigger(args.event, args.data)
            print("OK")
            return 0
    except Exception as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1


def _format_simvar_row(row: dict) -> str:
    if row.get("string"):
        dtype = "string"
    else:
        dtype = f"dtype={row.get('datatype', 4)}"
    unit = row.get("unit", "")
    return f"SimVar\t{row['name']}\t{unit}\t{dtype}"


def _format_event_row(row: dict) -> str:
    tags = ",".join(row.get("tags", []))
    return f"Event\t{row['name']}\t\t{tags}"


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query.lower()
    hits: List[Tuple[str, dict]] = []
    if not args.events_only:
        for row in _load_simvars():
            hay = " ".join([
                row.get("name", ""),
                row.get("unit", ""),
                " ".join(row.get("tags", [])),
            ]).lower()
            if query in hay:
                hits.append(("simvar", row))
    if not args.simvars_only:
        for row in _load_events():
            hay = " ".join([
                row.get("name", ""),
                " ".join(row.get("tags", [])),
            ]).lower()
            if query in hay:
                hits.append(("event", row))
    if not hits:
        print("No matches.")
        return 1
    for kind, row in hits[: args.limit]:
        if kind == "simvar":
            print(_format_simvar_row(row))
        else:
            print(_format_event_row(row))
    if len(hits) > args.limit:
        print(f"... and {len(hits) - args.limit} more (use --limit)")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    import runpy

    root = Path(__file__).resolve().parents[1]
    script = root / "examples" / "diagnose_read.py"
    if not script.is_file():
        print(f"diagnose_read.py not found: {script}", file=sys.stderr)
        return 1
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        try:
            return int(code)
        except (TypeError, ValueError):
            return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="simconnect-h", description="MSFS SimConnect CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", help="Test connection (read altitude)")

    g = sub.add_parser("get", help="Read one SimVar")
    g.add_argument("var")
    g.add_argument("unit", nargs="?", default="")
    g.add_argument("--timeout", type=float, default=3.0)
    g.add_argument("--string", action="store_true")

    s = sub.add_parser("set", help="Write one SimVar")
    s.add_argument("var")
    s.add_argument("value")
    s.add_argument("unit", nargs="?", default="")
    s.add_argument("--string", action="store_true")

    w = sub.add_parser("watch", help="Subscribe and print for N seconds")
    w.add_argument("var")
    w.add_argument("unit", nargs="?", default="")
    w.add_argument("--seconds", type=float, default=10.0)
    w.add_argument("--string", action="store_true")

    t = sub.add_parser("trigger", help="Trigger MSFS event")
    t.add_argument("event")
    t.add_argument("data", type=int, nargs="?", default=0)

    sr = sub.add_parser("search", help="Search common SimVars and events")
    sr.add_argument("query")
    sr.add_argument("--limit", type=int, default=40)
    sr.add_argument("--events-only", action="store_true")
    sr.add_argument("--simvars-only", action="store_true")

    sub.add_parser("doctor", help="Run diagnose_read.py")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "ping": cmd_ping,
        "get": cmd_get,
        "set": cmd_set,
        "watch": cmd_watch,
        "trigger": cmd_trigger,
        "search": cmd_search,
        "doctor": cmd_doctor,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

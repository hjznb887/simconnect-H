"""Build common_simvars.json and common_events.json (dev helper)."""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "simconnect_native" / "data"

# (name, unit, tags, string?)
SIMVAR_ROWS = [
    # Position / attitude
    ("PLANE ALTITUDE", "feet", ["altitude", "高度"]),
    ("INDICATED ALTITUDE", "feet", ["altitude", "ias"]),
    ("PLANE ALTITUDE AGL", "feet", ["altitude", "agl"]),
    ("PLANE LATITUDE", "degrees", ["lat", "纬度", "position"]),
    ("PLANE LONGITUDE", "degrees", ["lon", "经度", "position"]),
    ("PLANE HEADING DEGREES TRUE", "degrees", ["heading", "航向", "hdg"]),
    ("PLANE HEADING DEGREES MAGNETIC", "degrees", ["heading", "magnetic"]),
    ("PLANE PITCH DEGREES", "degrees", ["pitch", "俯仰"]),
    ("PLANE BANK DEGREES", "degrees", ["bank", "roll", "滚转"]),
    ("MAGNETIC COMPASS", "degrees", ["compass", "heading"]),
    ("GPS GROUND TRUE TRACK", "degrees", ["track", "gps"]),
    ("GPS GROUND MAGNETIC TRACK", "degrees", ["track", "gps"]),
    ("VERTICAL SPEED", "feet per minute", ["vs", "垂直速度", "fpm"]),
    ("ACCELERATION BODY X", "feet per second squared", ["accel"]),
    ("ACCELERATION BODY Y", "feet per second squared", ["accel"]),
    ("ACCELERATION BODY Z", "feet per second squared", ["accel"]),
    ("G FORCE", "gforce", ["g", "过载"]),
    ("INCIDENCE ALPHA", "degrees", ["aoa", "alpha"]),
    ("INCIDENCE BETA", "degrees", ["sideslip", "beta"]),
    ("RADIO HEIGHT", "feet", ["radalt", "radio"]),
    ("GROUND VELOCITY", "knots", ["gs", "地速", "speed"]),
    ("TOTAL VELOCITY", "knots", ["speed"]),
    ("SIM ON GROUND", "bool", ["ground", "地面"]),
    ("SURFACE RELATIVE GROUND SPEED", "knots", ["ground", "speed"]),
    # Airspeed
    ("AIRSPEED INDICATED", "knots", ["ias", "空速", "speed"]),
    ("AIRSPEED TRUE", "knots", ["tas", "speed"]),
    ("AIRSPEED MACH", "mach", ["mach", "speed"]),
    ("GPS GROUND SPEED", "knots", ["gps", "speed"]),
    ("GPS POSITION LAT", "degrees", ["gps", "lat"]),
    ("GPS POSITION LON", "degrees", ["gps", "lon"]),
    ("GPS POSITION ALT", "meters", ["gps", "alt"]),
    ("GPS WP DISTANCE", "nautical miles", ["gps", "fms"]),
    ("GPS WP BEARING", "degrees", ["gps", "fms"]),
    ("GPS WP CROSS TRK", "nautical miles", ["gps", "fms"]),
    ("GPS WP ETA", "seconds", ["gps", "fms"]),
    ("GPS WP ETE", "seconds", ["gps", "fms"]),
    ("GPS WP NEXT ID", "number", ["gps", "fms"]),
    ("GPS WP NEXT LAT", "degrees", ["gps", "fms"]),
    ("GPS WP NEXT LON", "degrees", ["gps", "fms"]),
    ("GPS IS ACTIVE WAY POINT", "bool", ["gps"]),
    ("GPS IS ACTIVE FLIGHT PLAN", "bool", ["gps", "fms"]),
    ("GPS DRIVES NAV1", "bool", ["gps", "nav"]),
    # Engine
    ("GENERAL ENG RPM:1", "rpm", ["engine", "rpm"]),
    ("GENERAL ENG RPM:2", "rpm", ["engine", "rpm"]),
    ("GENERAL ENG THROTTLE LEVER POSITION:1", "percent", ["throttle", "油门"]),
    ("GENERAL ENG THROTTLE LEVER POSITION:2", "percent", ["throttle"]),
    ("GENERAL ENG MANIFOLD PRESSURE:1", "inches of mercury", ["engine", "map"]),
    ("GENERAL ENG OIL PRESSURE:1", "psi", ["engine", "oil"]),
    ("GENERAL ENG OIL TEMPERATURE:1", "celsius", ["engine", "oil"]),
    ("GENERAL ENG FUEL FLOW:1", "pounds per hour", ["engine", "fuel"]),
    ("GENERAL ENG EXHAUST GAS TEMPERATURE:1", "celsius", ["engine", "egt"]),
    ("RECIP ENG CHT:1", "celsius", ["engine", "cht"]),
    ("RECIP ENG TURBINE INLET TEMPERATURE:1", "celsius", ["engine", "turbine"]),
    ("ENG COMBUSTION:1", "bool", ["engine"]),
    ("ENG ON FIRE:1", "bool", ["engine", "fire"]),
    ("ENG FAILED:1", "bool", ["engine"]),
    ("ENG ANTI ICE:1", "bool", ["engine", "ice"]),
    ("PROP RPM:1", "rpm", ["prop"]),
    ("PROP BETA:1", "degrees", ["prop"]),
    ("TURB ENG N1:1", "percent", ["jet", "n1"]),
    ("TURB ENG N2:1", "percent", ["jet", "n2"]),
    ("TURB ENG ITT:1", "celsius", ["jet", "itt"]),
    # Fuel
    ("FUEL TOTAL QUANTITY", "gallons", ["fuel", "燃油"]),
    ("FUEL TOTAL CAPACITY", "gallons", ["fuel"]),
    ("FUEL LEFT QUANTITY", "gallons", ["fuel"]),
    ("FUEL RIGHT QUANTITY", "gallons", ["fuel"]),
    ("FUEL CENTER QUANTITY", "gallons", ["fuel"]),
    ("FUEL WEIGHT PER GALLON", "pounds", ["fuel"]),
    ("FUEL PUMP", "bool", ["fuel"]),
    ("FUEL TANK SELECTOR:1", "number", ["fuel"]),
    # Electrical
    ("ELECTRICAL MASTER BATTERY", "bool", ["battery", "电瓶", "electrical"]),
    ("ELECTRICAL GENALT BUS VOLTAGE:1", "volts", ["electrical", "gen"]),
    ("ELECTRICAL GENALT BUS AMPS:1", "amperes", ["electrical", "gen"]),
    ("ELECTRICAL MAIN BUS VOLTAGE", "volts", ["electrical"]),
    ("ELECTRICAL TOTAL LOAD AMPS", "amperes", ["electrical"]),
    ("ELECTRICAL BATTERY LOAD", "amperes", ["electrical", "battery"]),
    ("CIRCUIT ON", "bool", ["electrical", "circuit"]),
    # Controls / surfaces
    ("YOKE X INDICATOR", "position", ["controls", "yoke"]),
    ("YOKE Y INDICATOR", "position", ["controls", "yoke"]),
    ("RUDDER PEDAL INDICATOR", "position", ["controls", "rudder"]),
    ("ELEVATOR POSITION", "degrees", ["controls", "elevator"]),
    ("AILERON POSITION", "degrees", ["controls", "aileron"]),
    ("RUDDER POSITION", "degrees", ["controls", "rudder"]),
    ("FLAPS HANDLE INDEX", "number", ["flaps", "襟翼"]),
    ("FLAPS HANDLE PERCENT", "percent", ["flaps"]),
    ("TRAILING EDGE FLAPS LEFT PERCENT", "percent", ["flaps"]),
    ("TRAILING EDGE FLAPS RIGHT PERCENT", "percent", ["flaps"]),
    ("SPOILERS HANDLE POSITION", "percent", ["spoilers"]),
    ("SPOILERONS LEFT POSITION", "position", ["spoilers"]),
    ("GEAR HANDLE POSITION", "bool", ["gear", "起落架"]),
    ("GEAR CENTER POSITION", "percent", ["gear"]),
    ("GEAR LEFT POSITION", "percent", ["gear"]),
    ("GEAR RIGHT POSITION", "percent", ["gear"]),
    ("BRAKE PARKING POSITION", "bool", ["brake", "parking"]),
    ("BRAKE LEFT POSITION", "position", ["brake"]),
    ("BRAKE RIGHT POSITION", "position", ["brake"]),
    ("WING FLEX PCT:1", "percent", ["wing"]),
    ("CANOPY OPEN", "percent", ["canopy"]),
    # Autopilot
    ("AUTOPILOT MASTER", "bool", ["ap", "自动驾驶"]),
    ("AUTOPILOT AVAILABLE", "bool", ["ap"]),
    ("AUTOPILOT ALTITUDE LOCK VAR", "feet", ["ap", "altitude"]),
    ("AUTOPILOT HEADING LOCK DIR", "degrees", ["ap", "heading"]),
    ("AUTOPILOT AIRSPEED HOLD VAR", "knots", ["ap", "speed"]),
    ("AUTOPILOT VERTICAL HOLD VAR", "feet per minute", ["ap", "vs"]),
    ("AUTOPILOT NAV1 LOCK", "bool", ["ap", "nav"]),
    ("AUTOPILOT GLIDESLOPE HOLD", "bool", ["ap"]),
    ("AUTOPILOT APPROACH HOLD", "bool", ["ap"]),
    ("AUTOPILOT FLIGHT DIRECTOR ACTIVE", "bool", ["ap", "fd"]),
    ("AUTOPILOT WING LEVELER", "bool", ["ap"]),
    ("AUTOPILOT YAW DAMPER", "bool", ["ap", "yd"]),
    # Avionics / NAV
    ("NAV OBS:1", "degrees", ["nav", "obs"]),
    ("NAV SIGNAL:1", "number", ["nav"]),
    ("NAV HAS NAV:1", "bool", ["nav"]),
    ("NAV HAS DME:1", "bool", ["nav", "dme"]),
    ("NAV HAS LOCALIZER:1", "bool", ["nav", "ils"]),
    ("NAV HAS GLIDE SLOPE:1", "bool", ["nav", "ils"]),
    ("NAV CDI:1", "number", ["nav", "cdi"]),
    ("NAV GSI:1", "number", ["nav", "gsi"]),
    ("NAV DME:1", "nautical miles", ["nav", "dme"]),
    ("ADF CARD", "degrees", ["adf"]),
    ("ADF RADIAL:1", "degrees", ["adf"]),
    ("HSI CDI NEEDLE", "number", ["hsi"]),
    ("HSI GSI NEEDLE", "number", ["hsi"]),
    ("HSI BEARING", "degrees", ["hsi"]),
    ("HSI STATION IDENT", "", ["hsi", "ident"], True),
    ("TRANSPONDER CODE:1", "bcn16", ["xpdr", "transponder"]),
    ("TRANSPONDER IDENT", "bool", ["xpdr"]),
    ("COM ACTIVE FREQUENCY:1", "mhz", ["com", "radio"]),
    ("COM STANDBY FREQUENCY:1", "mhz", ["com", "radio"]),
    ("NAV ACTIVE FREQUENCY:1", "mhz", ["nav", "radio"]),
    ("NAV STANDBY FREQUENCY:1", "mhz", ["nav", "radio"]),
    # Environment (read-only)
    ("AMBIENT TEMPERATURE", "celsius", ["temp", "ambient"]),
    ("AMBIENT WIND VELOCITY", "knots", ["wind"]),
    ("AMBIENT WIND DIRECTION", "degrees", ["wind"]),
    ("AMBIENT PRESSURE", "millibars", ["pressure", "qnh"]),
    ("AMBIENT VISIBILITY", "meters", ["visibility"]),
    ("BAROMETER PRESSURE", "millibars", ["baro", "qnh"]),
    ("KOHLSMAN SETTING HG", "inHg", ["baro", "altimeter"]),
    ("SEA LEVEL PRESSURE", "millibars", ["pressure"]),
    ("TOTAL AIR TEMPERATURE", "celsius", ["tat"]),
    ("WIND VELOCITY", "knots", ["wind"]),
    ("WIND DIRECTION", "degrees", ["wind"]),
    # Systems
    ("PITOT HEAT SWITCH", "bool", ["pitot", "ice"]),
    ("STRUCTURAL ICE PCT", "percent", ["ice"]),
    ("BLEED AIR SOURCE CONTROL", "number", ["bleed"]),
    ("PRESSURIZATION CABIN ALTITUDE", "feet", ["pressurization"]),
    ("PRESSURIZATION PRESSURE DIFFERENTIAL", "psi", ["pressurization"]),
    ("CABIN NO SMOKING ALERT SWITCH", "bool", ["cabin"]),
    ("LIGHT LANDING", "bool", ["lights", "landing"]),
    ("LIGHT STROBE", "bool", ["lights", "strobe"]),
    ("LIGHT BEACON", "bool", ["lights", "beacon"]),
    ("LIGHT NAV", "bool", ["lights", "nav"]),
    ("LIGHT TAXI", "bool", ["lights", "taxi"]),
    ("LIGHT PANEL", "bool", ["lights", "panel"]),
    ("LIGHT LOGO", "bool", ["lights"]),
    ("LIGHT WING", "bool", ["lights"]),
    ("LIGHT RECOGNITION", "bool", ["lights"]),
    # Time / sim
    ("ZULU TIME", "seconds", ["time", "zulu"]),
    ("LOCAL TIME", "seconds", ["time", "local"]),
    ("SIMULATION RATE", "number", ["sim", "rate"]),
    ("IS SLEW ACTIVE", "bool", ["sim", "slew"]),
    ("ATC HEAVY", "bool", ["atc"]),
    ("ATC AIRLINE", "", ["atc"], True),
    ("ATC FLIGHT NUMBER", "", ["atc"], True),
    ("ATC ID", "", ["atc", "callsign"], True),
    ("ATC TYPE", "", ["aircraft", "type"], True),
    ("TITLE", "", ["aircraft", "title", "机型"], True),
    ("ATC MODEL", "", ["aircraft"], True),
    ("CATEGORY", "", ["aircraft"], True),
    # Misc instruments
    ("TURN COORDINATOR BALL", "position", ["turn", "coordinator"]),
    ("SUCTION PRESSURE", "inches of mercury", ["vacuum"]),
    ("PARTIAL PANEL VACUUM", "bool", ["vacuum", "failure"]),
    ("PARTIAL PANEL ELECTRICAL", "bool", ["failure"]),
    ("PARTIAL PANEL PITOT", "bool", ["failure"]),
    ("PARTIAL PANEL AVIONICS", "bool", ["failure"]),
    ("WATER RUDDER HANDLE POSITION", "percent", ["seaplane"]),
    ("EXIT OPEN:1", "percent", ["door"]),
    ("INTERACTIVE POINT GOAL:0", "number", ["ground", "services"]),
    ("PUSHBACK STATE", "number", ["pushback"]),
    ("TOW CONNECTION", "bool", ["tow"]),
    ("REALISM CRASH WITH OTHERS", "bool", ["sim"]),
    ("REALISM CRASH DETECTION", "bool", ["sim"]),
]

EVENT_ROWS = [
    ("AP_MASTER", ["ap", "autopilot"]),
    ("AP_PANEL_ALTITUDE_HOLD", ["ap", "altitude"]),
    ("AP_PANEL_HEADING_HOLD", ["ap", "heading"]),
    ("AP_PANEL_SPEED_HOLD", ["ap", "speed"]),
    ("AP_PANEL_ATTITUDE_HOLD", ["ap"]),
    ("THROTTLE_FULL", ["throttle", "engine"]),
    ("THROTTLE_INCR", ["throttle"]),
    ("THROTTLE_DECR", ["throttle"]),
    ("THROTTLE_CUT", ["throttle"]),
    ("MIXTURE_INCR", ["mixture"]),
    ("MIXTURE_DECR", ["mixture"]),
    ("PROP_PITCH_INCR", ["prop"]),
    ("PROP_PITCH_DECR", ["prop"]),
    ("LANDING_LIGHTS_TOGGLE", ["lights", "landing"]),
    ("STROBES_TOGGLE", ["lights", "strobe"]),
    ("BEACONS_TOGGLE", ["lights", "beacon"]),
    ("NAV_LIGHTS_TOGGLE", ["lights", "nav"]),
    ("TAXI_LIGHTS_TOGGLE", ["lights", "taxi"]),
    ("PANEL_LIGHTS_TOGGLE", ["lights", "panel"]),
    ("GEAR_TOGGLE", ["gear", "起落架"]),
    ("PARKING_BRAKES", ["brake", "parking"]),
    ("FLAPS_INCR", ["flaps"]),
    ("FLAPS_DECR", ["flaps"]),
    ("FLAPS_UP", ["flaps"]),
    ("FLAPS_DOWN", ["flaps"]),
    ("ELEV_TRIM_UP", ["trim", "elevator"]),
    ("ELEV_TRIM_DN", ["trim", "elevator"]),
    ("AILERON_TRIM_LEFT", ["trim", "aileron"]),
    ("AILERON_TRIM_RIGHT", ["trim", "aileron"]),
    ("RUDDER_TRIM_LEFT", ["trim", "rudder"]),
    ("RUDDER_TRIM_RIGHT", ["trim", "rudder"]),
    ("TOGGLE_MASTER_BATTERY", ["battery", "electrical"]),
    ("TOGGLE_ALTERNATOR", ["alternator", "electrical"]),
    ("TOGGLE_AVIONICS_MASTER", ["avionics"]),
    ("TOGGLE_MASTER_IGNITION", ["ignition", "engine"]),
    ("TOGGLE_ENGINE", ["engine"]),
    ("SIM_RESET", ["sim", "reset"]),
    ("SITUATION_RESET", ["sim", "reset"]),
    ("REPAIR_AND_REFUEL", ["sim", "repair"]),
    ("VIEW_RESET", ["view", "camera"]),
    ("EYEPOINT_RESET", ["view", "camera"]),
    ("PAN_RESET", ["view", "camera"]),
    ("TOGGLE_GPS_DRIVES_NAV1", ["gps", "nav"]),
    ("HEADING_BUG_INC", ["heading", "bug"]),
    ("HEADING_BUG_DEC", ["heading", "bug"]),
    ("ALTITUDE_BUG_INC", ["altitude", "bug"]),
    ("ALTITUDE_BUG_DEC", ["altitude", "bug"]),
    ("AIRSPEED_BUG_INC", ["speed", "bug"]),
    ("AIRSPEED_BUG_DEC", ["speed", "bug"]),
    ("VOR1_OBS_INC", ["nav", "obs"]),
    ("VOR1_OBS_DEC", ["nav", "obs"]),
    ("VOR2_OBS_INC", ["nav", "obs"]),
    ("VOR2_OBS_DEC", ["nav", "obs"]),
    ("COM_RADIO_WHOLE_INC", ["com", "radio"]),
    ("COM_RADIO_WHOLE_DEC", ["com", "radio"]),
    ("NAV_RADIO_WHOLE_INC", ["nav", "radio"]),
    ("NAV_RADIO_WHOLE_DEC", ["nav", "radio"]),
    ("TRANSPONDER_CODE_INC", ["xpdr"]),
    ("TRANSPONDER_CODE_DEC", ["xpdr"]),
    ("TRANSPONDER_IDENT", ["xpdr", "ident"]),
    ("PITOT_HEAT_TOGGLE", ["pitot", "ice"]),
    ("FUEL_SELECTOR_2_POS", ["fuel"]),
    ("FUEL_SELECTOR_3_POS", ["fuel"]),
    ("FUEL_SELECTOR_4_POS", ["fuel"]),
    ("MAGNETO_OFF", ["magneto", "engine"]),
    ("MAGNETO_LEFT", ["magneto"]),
    ("MAGNETO_RIGHT", ["magneto"]),
    ("MAGNETO_BOTH", ["magneto"]),
    ("MAGNETO_START", ["magneto", "start"]),
]


def main() -> None:
    simvars = []
    seen = set()
    for row in SIMVAR_ROWS:
        if len(row) == 4:
            name, unit, tags, is_str = row
        else:
            name, unit, tags = row
            is_str = False
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        entry = {"name": name, "unit": unit, "tags": tags}
        if is_str:
            entry["string"] = True
            entry["datatype"] = 11
        elif unit == "bool":
            entry["datatype"] = 1
        else:
            entry["datatype"] = 4
        simvars.append(entry)

    events = [{"name": n, "tags": t} for n, t in EVENT_ROWS]

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "common_simvars.json").write_text(
        json.dumps(simvars, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (DATA / "common_events.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(simvars)} simvars, {len(events)} events -> {DATA}")


if __name__ == "__main__":
    main()

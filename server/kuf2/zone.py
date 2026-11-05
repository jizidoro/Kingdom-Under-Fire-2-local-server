"""A spot's zone content: Data/Map/<Map_File>/Mission/<Map_File>_<MissionLevel_1>.clt (spottable columns), a BMIF file
(schema Data/Script/clt.bmi in Script.pkg; decoder tools/recon/bmif.py). Finding and decoding it takes seconds, so the
parts the server uses are cached in server/data/zones/<map>_<zone>.json (FIELD-BATTLE-PLAN).
"""
import functools
import json
import pathlib
import sys

from . import tables

ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / "server" / "data" / "zones"
KEEP = ("SpotType", "ZoneID", "PlayerStartPointInfoData", "NPCTroopInfoData", "SmartPropData", "NPCInfo", "QuestBound",
        "SafeZoneObs", "GridMinX", "GridMinZ", "GridMaxX", "GridMaxZ", "GridX", "GridY", "GridXLength", "GridYLength",
        "Force",                                   # Force: {ForceID, ForceName} (waves' roles: 하드 / 헬 only, 연출 staging)
        "EventBound")                              # the mission Lua's named areas: {EventBoundName, BoundCenterX / Z,
                                                   # BoundRadius, EventBoundType 3 circle / 2 polygon BoundPoint}


def _read(name):
    """A package file by path (hash lookup over every Packages/*.pkg), or None."""
    sys.path.insert(0, str(ROOT / "tools"))
    import pkg
    h = pkg.name_hash(name.lower().replace("/", "\\"))
    for p in sorted((pkg.GAME / "Packages").glob("*.pkg")):
        try:
            P = pkg.Pkg(p)
        except Exception:
            continue
        for e in P.entries:
            if e["hash"] == h:
                return P.read(e)
    return None


@functools.cache
def content(map_file, zone):
    path = CACHE / f"{map_file}_{zone}.json"
    missing = CACHE / f"{map_file}_{zone}.missing"       # a package scan found no file (12 s); the build is pinned
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if all(k in cached for k in KEEP):
            return cached                          # a cache from before a KEEP addition is decoded again below
    if missing.exists():
        raise FileNotFoundError(f"zone file of {map_file} {zone} not in the packages (cached: {missing.name})")
    sys.path.insert(0, str(ROOT / "tools" / "recon"))
    import bmif
    schema = _read("data/script/clt.bmi")
    clt = _read(f"data/map/{map_file}/mission/{map_file}_{zone}.clt")
    if schema is None or clt is None:
        if schema is not None:
            CACHE.mkdir(parents=True, exist_ok=True)
            missing.write_text("", encoding="utf-8")
        raise FileNotFoundError(f"zone file of {map_file} {zone} not found in the packages")
    root = bmif.Decoder(schema.decode("latin-1"), clt).decode("clt_file_root")["root"]
    out = {k: root.get(k) for k in KEEP}
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, default=str), encoding="utf-8")
    return out


def for_spot(spot):
    row = tables.by_id("spottable")[str(spot)]
    return content(row["Map_File"], row["MissionLevel_1"])


@functools.cache
def available(spot):
    """Whether the spot's zone file exists (19 of spottable's 34 Field spots have none under the <map>_<zone>.clt
    name, all of them test spots (State 1, TestMap): e.g. 10201 1_BledLake_Field, an old Lake Bled whose live spot is
    10202 1_BledLake_Field_New, and 50069 1_Retford_Field); the first call for a spot decodes it (seconds, 25 s for
    Lake Bled's 2411 troops), later ones are cached."""
    try:
        for_spot(spot)
        return True
    except (FileNotFoundError, KeyError):
        return False


@functools.cache
def np_troop(table_id):
    """The nptrooptable row of a troop table id, or None."""
    return next((r for r in tables.load("nptrooptable") if r["NPTROOP_ID"] == str(table_id)), None)

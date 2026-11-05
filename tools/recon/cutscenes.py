"""Every mission cutscene in the map packages (Packages/Map*.pkg): its map, index, length, the lines it voices.

A cutscene is an XML file (`<Track m_nTotalLength="..." m_strName="9_GreySmoke_Dynamic1" ...>`, Data/Map/<map>/
Mission/<name>.csdata): camera and actor tracks with positions, RTS.* script commands the client runs itself
(Troop_MoveToArea, Troop_EnableForce, Actor_MoveToPosition ...), and SOUND events carrying m_nSubTitleID (a
missiontext id) with their voice (event:/<map>/Voice/<id>) under the speaking actor's track. The package name list
does not hold these paths: every entry whose first bytes are the XML header is read, and its map found by hashing
data\\map\\<map>\\mission\\<name>.csdata for every map of spottable.

"index" is the number the name starts with. "slot" is the number ActCutScenePlayCutScene 0x10d92 actually takes
(read from code 2026-09-30). Each map has a cutscene list, Data/Map/<map>/Mission/<map>.csset: a `<CutSceneSet>` with
one `<CutSceneData m_strFileName="...">` per scene. The client loads the files in the list's order (0x1408ad590 ->
0x1408ad7f0 -> 0x1408add00 per file) and appends each to the player's scene vector at +0x20 (0x1408ae0e0). The action's
number is a position in that vector (0x140b6ce80, 0x1408b3360). Index and slot agree on most maps. They differ where
the list skips or repeats a number (1_MistField from slot 10: 9_Refugee_camp, 10_Soldier ...), and a file the list
leaves out has no slot at all (Grey Rock's 13_StartCut, so 13 there plays 13_EndScene).

Run: py tools/recon/cutscenes.py [--game <the game's folder>] [map ...]   -> planning/scripts/cutscenes.md and .json
(the tests read cutscenes.json: build it once from your own install; about a minute)"""
import pathlib
import re
import sys
import html
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "server"))
import pkg  # noqa: E402
from kuf2 import tables  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HEAD = b"<Track m_nTotalLength"
LIST = b"<CutSceneSet"


def head(p, e, n=32):
    off, ccs, cds = e["chunks"][0]
    raw = p.data[off:off + (ccs or cds)]
    try:
        return raw[:n] if ccs == 0 else zlib.decompressobj().decompress(raw, n)
    except zlib.error:
        return b""


def parse(text):
    name = re.search(r'm_strName="([^"]*)"', text)
    total = re.search(r'm_nTotalLength="(\d+)"', text)
    name, total = (name.group(1) if name else "?"), (int(total.group(1)) if total else 0)
    lines, actor = [], None
    for m in re.finditer(r'<Track m_eType="(ACTOR|EXTRAACTOR)" m_strName="([^"]*)"|m_nTimeStart="(\d+)"[^>]*?'
                         r'm_nSubTitleID="(\d+)"', text):
        if m.group(1):
            actor = m.group(2)
        elif m.group(4) != "0":
            lines.append((int(m.group(3)), int(m.group(4)), actor))
    script = []                                   # [ms, track, [commands]]: what the client runs itself
    for tr in re.finditer(r'<Track m_eType="SCRIPT" m_strName="([^"]*)"(.*?)</Track>', text, re.S):
        for ev in re.finditer(r'<Event m_nTimeStart="(\d+)"(.*?)</Event>', tr.group(2), re.S):
            cmds = [html.unescape(c) for c in re.findall(r'<Script Command="([^"]*)"', ev.group(2))]
            if cmds:
                script.append([int(ev.group(1)), tr.group(1), cmds])
    return name, total, sorted(lines), sorted(script, key=lambda s: s[0])


def actors(text):
    """[[troop, unit, name], ...]: the ACTOR tracks, each bound to a troop of the room when the scene starts to play
    (TrackActor 0x140942bc0: the TroopManager's troop by uid, 0x140c02780, -10 the hero (0x1408b0e90), then its
    unit: 65535 the leader, 65534 troop +0x840, else units[n], 0x1407e7b70). The scene does not start until every
    one is loaded (the root's IsCompleteLoad 0x140947640 over TrackActorBase::IsCompleteLoad 0x140941f70): one
    whose troop is not in the room never binds, and the scene waits at black for ever (0x1408b3360 -> 0x1408ac020;
    live 2026-09-30 15:25, Grey Rock's 11_Kobold with the troll's force 20080 not yet in). EXTRAACTOR tracks load
    their own model (m_strResource) and wait on no troop."""
    out = []
    for m in re.finditer(r'<Track m_eType="ACTOR"([^>]*)>', text):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        troop = -10 if a.get("m_bPlayerMySelf") == "1" else int(a.get("m_nTroopID", -1))
        out.append([troop, int(a.get("m_nUnitIndex", 65535)), a.get("m_strName", "")])
    return out


def slots(p, e, maps):
    """(map, {scene name: slot}) when entry e is a map's .csset cutscene list (its files in their order), else None."""
    if LIST not in head(p, e, 96):
        return None
    where = next((m for m in maps if pkg.name_hash(f"data\\map\\{m}\\mission\\{m}.csset".lower()) == e["hash"]), None)
    files = re.findall(r'<CutSceneData m_strFileName="([^"]*)\.csdata"', p.read(e).decode("utf-8", "replace"))
    return where, {name: i for i, name in reversed(list(enumerate(files)))}


def helps(script):
    """The help-box lines a cutscene shows itself (System_GuiShowMissionHelpTextByTroopId(leader, troop, flag, id, s))."""
    return [int(m.group(1)) for _, _, cmds in script for c in cmds
            for m in [re.search(r"GuiShowMissionHelpTextByTroopId\([^,]*,[^,]*,[^,]*,\s*(\d+)", c)] if m]


def tutorials(script):
    """The missiontutorial rows a cutscene starts itself (System_StartTutorial(-1, row))."""
    return [int(m.group(1)) for _, _, cmds in script for c in cmds
            for m in [re.search(r"System_StartTutorial\(\s*-?\d+\s*,\s*(\d+)", c)] if m]


def waits(script):
    """Whether it waits on the player (System_CheckInputEvent / InputActiveKeyEvent): it ends only on their input."""
    return any("CheckInputEvent" in c or "InputActiveKeyEvent" in c for _, _, cmds in script for c in cmds)


def main():
    args = sys.argv[1:]
    game = None
    if "--game" in args:
        i = args.index("--game")
        game, args = args[i + 1], args[:i] + args[i + 2:]
    pkg.use_game(game)
    want = set(a.lower() for a in args)
    maps = sorted({str(r.get("Map_File", "")) for r in tables.load("spottable") if r.get("Map_File")})
    found, lists = [], {}
    for path in sorted((pkg.GAME / "Packages").glob("Map*.pkg")):
        p = pkg.Pkg(path)
        for e in p.entries:
            listed = slots(p, e, maps)
            if listed is not None and listed[0] is not None:
                lists[listed[0]] = listed[1]
            if not head(p, e).startswith(HEAD):
                continue
            text = p.read(e).decode("utf-8", "replace")
            name, total, lines, script = parse(text)
            where = next((m for m in maps if pkg.name_hash(f"data\\map\\{m}\\mission\\{name}.csdata".lower())
                          == e["hash"]), None)
            if want and (where or "").lower() not in want:
                continue
            found.append((where or "?", name, total, lines, script, path.name, actors(text)))
        print(path.name, len(found), file=sys.stderr)
    doc = ["# Mission cutscenes (tools/recon/cutscenes.py)", "",
           "Index = the number the name starts with; ActCutScenePlayCutScene 0x10d92 takes the slot, the scene's place "
           "in the map's <map>.csset list, shown where it differs. Lines: m_nSubTitleID at its start (ms) and the actor "
           "track that speaks it.", ""]
    for where, name, total, lines, script, pk, cast in sorted(found, key=lambda f: (f[0], int(re.match(r"\d*", f[1]).group()
                                                                                       or 999), f[1])):
        idx = re.match(r"(\d+)_", name)
        slot = lists.get(where, {}).get(name)
        told = ("" if slot is not None and idx and int(idx.group(1)) == slot else f" (slot {slot})" if slot is not None
                else " (not in the map's list)")
        doc.append(f"- **{where}** `{name}` index {idx.group(1) if idx else '-'}{told}, {total / 1000:.1f} s ({pk}); "
                   f"lines: {', '.join(f'{i}@{t / 1000:.0f}s {a}' for t, i, a in lines) or 'none'}"
                   + (f"; help box: {', '.join(map(str, helps(script)))}" if helps(script) else "")
                   + (f"; tutorials: {', '.join(map(str, tutorials(script)))}" if tutorials(script) else "")
                   + ("; waits for input" if waits(script) else "")
                   + (f"; troops it waits for: {', '.join(str(a[0]) for a in cast)}" if cast else ""))
    out = ROOT / "planning" / "scripts" / "cutscenes.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(doc) + "\n", encoding="utf-8")
    import json                                          # for tools/playthrough.py: what a played cutscene voices
    idx = lambda name: int(re.match(r"(\d+)_", name).group(1)) if re.match(r"(\d+)_", name) else None
    out.with_suffix(".json").write_text(json.dumps(
        [{"map": w, "name": n, "index": idx(n), "slot": lists.get(w, {}).get(n), "ms": t, "lines": [i for _, i, _ in ls], "help": helps(sc),
          "tutorials": tutorials(sc), "waits": waits(sc), "script": sc, "actors": ac} for w, n, t, ls, sc, _, ac in found],
        ensure_ascii=False, indent=0), encoding="utf-8")
    print(out, len(found), "cutscenes")


if __name__ == "__main__":
    main()

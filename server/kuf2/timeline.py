"""One readable line per event (LIVE-DEBUG-PLAN): the server journal's (net.journal writes them to
captures/logs/server_<start>.log beside the JSONL), the client telemetry's (tools/telemetry.py record writes
captures/logs/client_<start>.log) and both merged (tools/live.py), in one format:

  HH:MM:SS.mmm SRV step 12 'ruins' on bound 18021 at (91927, 114023): say 톰슨_1 1060, cutscene 12 2
  HH:MM:SS.mmm CLI key F2 KEY_SelectTroop3 (map 0 COMMON)

The client's packets read as one line a second (ClientStream), its heartbeats only as their gaps, the keys of one
instant as one line, a system line once. Names (Names) come from the tools' files where they are
(planning/PACKETS.md, re/actions.txt, re/input_events.txt, the missiontutorial table); the server writes numbers, and
the names of its quests and items."""
import datetime
import functools
import json
import pathlib
import re

# The default keys of the InputEvents the lessons wait for (Data/Script/ControlSetting.lua, Script.pkg;
# planning/controls/HERO-CONTROLS.md §2); the mouse buttons by their events' names (KEY_MouseLClick, KEY_MouseRClick)
DEFAULT_KEYS = {0x15: "1", 0x23: "Ctrl+1", 0x2b: "Ctrl+A", 0x30: "Tab", 0x31: "Alt", 0x32: "F", 0x33: "F4", 0x34: "`",
                0x35: "F1", 0x36: "F2", 0x37: "F3", 0x38: "Z", 0x39: "X", 0x3a: "C", 0x3f: "wheel down", 0x40: "wheel up",
                0x56: "LMB", 0x57: "RMB", 0x77: "right button up", 0x7c: "W", 0x7d: "S", 0x7e: "A", 0x7f: "D",
                0x81: "LMB (a skill's target)", 0x83: "RMB (an order)", 0x84: "RMB (a move)"}
KEY_MAPS = {0: "COMMON", 2: "CAMERAMOVE", 3: "UI_HOTKEY", 4: "SKILL_HOTKEY", 5: "MISSION", 6: "ACTION", 9: "cutscene"}
CAMERA_MAP = 2                   # a camera turn reports a key every frame (411 lines in town, live 2026-09-29 17:42):
                                 # a run of instants of this map only is one line
KEY_INSTANT_MS = 200             # ours: the clock (the recorder's tick) closes a key instant only this long after it,
                                 # so it cannot fall inside the burst of one click's keys; the next event closes it
VIEWS = {0: "Strategy", 1: "Action"}
PACKET_S = 1.0                   # the client's packets: one summary line a second
BEAT_GAP_S = 5                   # a heartbeat (every 2 s) this late is a gap worth a line
PULSE_GAP_S = 12                 # no pulse (every 5 s, from the probe's own thread) this long: the game or probe is gone
REPEAT_S = 2                     # a client log line repeated (numbers aside) within this: one summary line
SYS_TWIN_MS = 20                 # a system line both client hooks print (0x140d631c0, 0x140d63690): the same text at
                                 # the same ms live (2026-09-29 17:48:22.913); the second is dropped


@functools.lru_cache(maxsize=None)
def unit_actions():
    """The client's unit action names by id (its action enum, re/action_names.json: 50 COMBAT_CAUTION_STAND,
    601 COMMON_NORMAL_STAND); [] where the research files are absent."""
    p = pathlib.Path(__file__).resolve().parents[2] / "re" / "action_names.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


class Names:
    """Ids to names: requests and messages {id: name}, script actions {id: name}, InputEvents {value: name}, mission
    tutorials {the client's lesson id (missiontutorial %MissionTutorialType Index): MissionTutorialType}."""
    def __init__(self, packets=None, actions=None, inputs=None, lessons=None):
        self.packets, self.actions, self.inputs = packets or {}, actions or {}, inputs or {}
        self.lessons = lessons or {}

    def packet(self, i):
        """A request or message's short name: the method of planning/PACKETS.md's caller column ("UnitHero::DoHitUnit"
        -> DoHitUnit), none for a bare handler class ("[InGamePacketProcessor]")."""
        name = str(self.packets.get(i, "")).replace("(via caller)", "").strip()
        return "" if name.startswith("[") else name.split("::")[-1]


NONE = Names()


def clock(t):
    """Epoch ms -> HH:MM:SS.mmm (local time)."""
    return datetime.datetime.fromtimestamp(t / 1000).strftime("%H:%M:%S.%f")[:12]


def line(e, side, text):
    return f"{clock(e.get('t', 0))} {side} {text}"


def key_name(value, name=None, names=NONE):
    """An InputEvent as the player knows it: its default key and its name (re/input_events.txt, else the one given),
    else its value."""
    event = names.inputs.get(value) or name
    return " ".join(x for x in (DEFAULT_KEYS.get(value), event) if x) or f"InputEvent {value}"


def _v(v):
    return "(%s)" % ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)


def _pairs(d, skip=()):
    return " ".join(f"{k} {_v(v)}" for k, v in (d or {}).items() if k not in skip)


def why_text(on, why, names=NONE):
    """What fired a director step: its trigger with the values that made it hold."""
    why = why or {}
    if "then" in why:
        return f"{on}, after its needed step {why['then']!r}"
    if on == "after":
        return f"after {why.get('after')!r} +{why.get('s', 0)} s"
    if on == "prompt":
        return f"prompt {why.get('prompt')} {key_name(why.get('key', 0), why.get('name'), names)}"
    if on == "cond":
        return "cond " + cond_text(why.get("cond", 0), why.get("args") or ()) + " holds"
    if on in ("start", "won"):
        return on
    return f"{on} {_pairs(why)}"


def cond_text(cond, args):
    """A condition the director asks the client (director.COND_TUTORIAL_PAST: a lesson's page)."""
    if cond == 0xcb2b and len(args) == 2:
        return f"lesson {args[0]} " + ("showing" if args[1] < 0 else f"past page {args[1]}")
    return f"0x{cond:x} {_v(args)}"


def wait_text(w, t=None, names=NONE):
    """One entry of the director's wait list (director.waits), short."""
    on = w.get("on")
    if "then" in w:
        what = f"{on} came, waits for step {w['then']!r}"
    elif on == "prompt":
        up = w.get("prompts") or [[None, k, n] for k, n in w.get("keys", ())]
        what = " / ".join(f"key {key_name(k, n, names)}" + (f" (prompt {p})" if p is not None else "") for p, k, n in up)
    elif on == "cond":
        what = cond_text(w.get("cond", 0), w.get("args") or ())
    elif on == "bound":
        what = f"bound {w.get('name') or w.get('bound')}"
    elif on == "after":
        due = w.get("due")
        what = f"timer {max(0, round((due - t) / 1000))} s" if due and t else f"timer ({w.get('after')!r})"
    elif on in ("down", "wake", "engage"):
        who = f"troop {w['troop']}" if "troop" in w else f"force {w.get('force')}"
        what = {"down": f"{who} down", "wake": f"{who} wakes", "engage": f"a fight with {who}"}[on]
    elif on == "left":
        what = f"force {w.get('force')} down to {w.get('count')}"
    elif on == "hp":
        who = f"troop {w['troop']}" if "troop" in w else f"force {w.get('force')}"
        what = f"{who} below {w.get('below')} %"
    elif on == "skill":
        what = f"{w.get('troop')} casts on force {w.get('force')}"
    else:
        what = {"start": "the start", "won": "the win"}.get(on, f"{on} {_pairs(w, ('step', 'id', 'on'))}")
    return what


def waits_text(waits, t=None, names=NONE):
    if not waits:
        return "nothing"
    return "; ".join(f"step {w.get('step')}" + (f" {w['id']!r}" if w.get("id") else "") + ": " + wait_text(w, t, names)
                     for w in waits)


def _do(do):
    return ", ".join(" ".join(map(str, a)) for a in do or ()) or "nothing"


def server_text(e, names=NONE):
    """The readable text of a server journal event (net.journal); one it cannot read, as its fields."""
    try:
        return _server_text(e, names)
    except Exception:
        return f"{e.get('k')} " + _pairs(e, ("t", "k"))


def _server_text(e, names):
    k, g = e.get("k"), e.get
    spot = f" {g('spot')}" if g("spot") is not None else ""
    if k == "boot":
        return "server started" + (f" at commit {g('commit')}" if g("commit") else "")
    if k == "conn":
        return f"{g('role')} connection {'open' if g('ev') == 'open' else 'closed'}{spot}"
    if k == "login":
        return f"login: account {g('account')}"
    if k == "char":
        head = f"character {g('id')} {g('name')!r} chosen, at spot {g('spot')} {_v(g('pos'))}"
        if g("level") is None:
            return head
        n = len(g("quests") or ())
        return head + (f": level {g('level')}, exp {g('exp')}/{_need(g('need'))}, {g('gold')} gold, "
                       f"{n} quest{'' if n == 1 else 's'} held")
    if k == "gear":
        swaps = ", ".join(f"{w} {at} {old} -> {new if new is not None else 'removed'}"
                          for w, at, old, new in g("replaced") or ())
        hp = g("hp") or (None, None)
        return f"character {g('id')} {g('name')!r}: made-up kit replaced ({swaps}); HP {hp[0]} -> {hp[1]}"
    if k == "skill":                                # skills.level_up / world.raise_auto_skills
        ups = ", ".join(f"{a} {old} -> {new}" for a, old, new in g("levels") or ())
        why = f"level-up to {g('level')}" if g("ev") == "level" else f"at login, level {g('level')}"
        hp = g("hp")
        return f"character {g('id')} {g('name')!r}: hero skills {ups} ({why})" + (f"; HP {hp[0]} -> {hp[1]}" if hp else "")
    if k == "town":
        return f"town {g('spot')}"
    if k == "room":
        ev = g("ev")
        if ev == "enter":
            return f"room enter{spot} ({g('kind')}, difficulty {g('difficulty')})"
        if ev == "won":
            points = f" ({g('points')} points)" if g("points") is not None else ""
            of = f" of category {g('category')}" if g("category") else ""
            return f"room won{spot}: {g('secs')} s, grade {g('grade')}{points}, exp {g('exp')}, {g('cards')} cards{of}"
        if ev == "leave":
            return f"room left{spot} for {g('back')}"
        return f"room {ev}{spot}"
    if k == "step":
        ident = f" {g('id')!r}" if g("id") else ""
        return f"step {g('step')}{ident} on {why_text(g('on'), g('why'), names)}: {_do(g('do'))}"
    if k == "say":
        return f"say {g('line')} {g('speaker') or '-'}: \"{g('text')}\""
    if k == "cutscene":
        return f"cutscene {g('index')} ({g('secs')} s)"
    if k == "lesson":
        return f"lesson {g('ev')}" + (f" {g('name')}" if g("name") else "")
    if k == "notice":
        return f"notice {_v(g('ids'))}: \"{g('text') or ''}\""
    if k == "panel":
        tail = f" {g('value')}/{g('top')}" if g("top") is not None else ""
        return f"panel {g('what')} {_v(g('ids'))}{tail}"
    if k == "waits":
        if g("new") is None or len(g("new")) == len(g("waits") or ()):
            return f"waits ({len(g('waits') or ())}): " + waits_text(g("waits"), g("t"), names)
        gone = "".join(f"; -step {i}" for i in g("gone") or ())
        return f"waits ({len(g('waits') or ())}): +" + waits_text(g("new"), g("t"), names) + gone
    if k == "spawn":
        return f"spawn {g('troop')} ({g('table')}) force {g('force')} team {g('team')}: {g('units')} units"
    if k == "wake":
        return f"force {g('force')} wakes ({g('why')}): {g('n')} troops"
    if k == "barrier":
        return f"barrier {g('prop')} (type {g('type')}) opens: {g('why')}"
    if k == "march":
        return (f"march {g('who')} to area {g('area')}" + (f" {g('name')}" if g("name") else "")
                + f" ({'centre' if g('goal') == 0 else 'nearest point'}): troops {_v(g('troops'))}")
    if k == "bound":
        return f"troop {g('troop')} bound (0x50ab)" + (f", {g('orders')} orders held for it sent" if g("orders") else "")
    if k == "hand":
        return f"troop {g('troop')} handed to the player" + (" at the start" if g("start") else "")
    if k == "landed":
        return f"troop {g('troop')} force change landed (0x50e6): " + ("the player's" if g("on") else "off")
    if k == "down":
        by = f" by {g('killer')}" if g("killer") is not None else ""
        if g("hero"):
            return "hero down" + by
        if g("deck") is not None:
            return f"deck troop {g('troop')} ({g('deck')}) down{by}"
        if g("troop") is None:
            return f"force {g('force')} down"
        return f"troop {g('troop')} down (force {g('force')}){by}" + (", no credit" if g("credited") is False else "")
    if k == "left":
        return f"troop {g('troop')} leaves the battle"
    if k == "hits":
        return hits_text(e)
    if k == "volley":                               # 0x505a reports that named no troop (combat.journal_empty_volley)
        by = ", ".join(f"{u}" + (f" x{n}" if n > 1 else "") for u, n in g("empty") or ())
        return f"volley by {by}: no target hit"
    if k == "cast":
        name = f" {g('name')}" if g("name") else ""
        return f"{g('side')} troop {g('troop')} casts {g('ability')}{name} (level {g('level')}) on troop {g('target')}"
    if k == "immune":
        name = f" {g('name')}" if g("name") else ""
        by = f" from troop {g('caster')}" if g("caster") not in (None, 0xffff) else ""
        return f"troop {g('troop')} immune to status {g('status')}{name} (level {g('level')}){by}: {g('trait')} {g('value')}"
    if k == "refused":
        return f"REFUSED {_req(g('req'), names)}: {g('text')}"
    if k == "unknown":
        return f"UNKNOWN {g('role')} 0x{g('id'):04x} {names.packet(g('id'))}".rstrip() + f" len {g('len')} {g('head')}"
    if k == "warn":
        return f"WARN {_req(g('req'), names)}: {g('text')}" if g("req") else f"WARN {g('text')}"
    if k == "error":
        tb = "".join("\n    " + x for x in str(g("tb") or "").rstrip().splitlines())
        return f"ERROR {_req(g('req'), names)}: {g('text')}{tb}" if g("req") else f"ERROR {g('text')}{tb}"
    if k == "snap":
        forces = " ".join(f"{f}:{n}" for f, n in (g("forces") or {}).items())
        hp = g("hp") or ()
        return (f"snapshot{spot}: hero {_v(g('hero') or '?')}" + (f" hp {hp[0]}/{hp[1]}" if len(hp) == 2 else "")
                + f"; forces {forces or 'none'}; {len(g('waits') or ())} waits")
    if k in ECONOMY:
        return ECONOMY[k](e, g)
    return f"{k} " + _pairs(e, ("t", "k"))


def _need(need):
    return "-" if need is None else need


def _thing(code, n=None, name=None):
    """An item as the economy lines name it: its code, its English name, the count."""
    return f"{code}" + (f" {name!r}" if name else "") + (f" x{n}" if n is not None else "")


def _why(g):
    return f" ({g('why')})" if g("why") else ""


QUEST_EV = {"accept": "accepted", "progress": "progress", "done": "done, ready to hand in", "abandon": "abandoned",
            "restart": "restarted (its time ran out)", "skip": "skipped (the tutorial skip)"}


def quest_text(e, g):
    """quest.journal_quest: accept / progress / done / hand-in / abandon / restart / skip, each condition's count."""
    head = f"quest {g('id')}" + (f" {g('title')!r}" if g("title") else "")
    if g("ev") == "hand-in":
        got = ([f"{g('gold')} gold"] if g("gold") else []) + ([f"{g('exp')} exp"] if g("exp") else [])
        got += [_thing(code, n) for code, n in g("items") or ()]
        return head + " handed in" + (": " + ", ".join(got) if got else "")
    conds = ", ".join(f"{kind} {id1} {n}/{need}" for kind, id1, n, need in g("conds") or ())
    return f"{head} {QUEST_EV.get(g('ev'), g('ev'))}" + (f": {conds}" if conds else "")


def item_text(e, g):
    """An item into or out of the bag: gain / spend (world.add_item / remove_item), use (world.use_reply), a store's
    buy / sell / rebuy."""
    ev, what = g("ev"), _thing(g("code"), g("n"), g("name"))
    if ev == "gain":
        return f"item gain {what}" + (f", {g('mailed')} more mailed (the bag is full)" if g("mailed") else "") + _why(g)
    if ev == "spend":
        return f"item spent {what}{_why(g)}"
    if ev == "use":
        return f"item used {what}" + (f" ({g('kind')})" if g("kind") else "")
    price = f"{g('price')} of item {g('money')}" if g("money") else f"{g('price')} gold"
    if ev == "buy":
        return f"item bought {what} at shop {g('shop')} slot {g('slot')} for {price}"
    return {"sell": f"item sold {what} for {price}", "rebuy": f"item bought back {what} for {price}"}.get(
        ev, f"item {ev} {what}")


def loot_text(e, g):
    ev = g("ev")
    if ev == "drop":
        got = [_thing(code, n, name) for code, n, name in g("items") or ()]
        got += [f"{g('gold')} gold"] if g("gold") else []
        at = f" ({g('at')[0]}, {g('at')[1]})" if g("at") else ""
        return f"loot on the ground at {g('spot')}{at}: " + ", ".join(got)
    if ev == "card":
        return f"loot: reward card {g('card')} is {_thing(g('code'), g('n'), name=g('name'))}"
    where = f"drop {g('drop')}" if g("drop") is not None else f"box {g('box')}"
    if g("gold"):
        piles = isinstance(g("drop"), list)                 # 0x5136 (the result screen closing): every pile at once
        return f"loot picked: {g('gold')} gold (pile{'s' if piles else ''} {_v(g('drop'))})"
    return f"loot picked: {_thing(g('code'), g('n'), g('name'))} ({where})"


def mail_text(e, g):
    head = f"mail {g('id')} {g('title')!r}"
    got = ([f"{g('gold')} gold"] if g("gold") else []) + [_thing(code, n) for code, n in g("items") or ()]
    return head + {"sent": " sent", "read": " read", "taken": " taken"}.get(g("ev"), f" {g('ev')}") + (
        ": " + ", ".join(got) if got else "")


def warp_text(e, g):
    """A move between places: a portal (0x5640), a warp request (0x4071) or crystal, the world map out and back, a door
    into a spot (0x3f48), a field or mission room entry, a teleport on the map."""
    how, cost = g("how"), f", {g('cost')} gold" if g("cost") else ""
    if how == "portal":
        return f"warp portal {g('warp')} on spot {g('spot')} to {_v(g('pos'))}{cost}"
    if how in ("request", "crystal"):
        kind = f" ({g('kind')})" if g("kind") else ""
        return f"warp {how} {g('warp')}{kind} to spot {g('spot')} group {g('group')}{cost}"
    if how == "world map":
        return f"warp to the world map from spot {g('spot')}"
    if how == "travel":
        return f"warp travel to spot {g('spot')} at {_v(g('pos'))}"
    if how == "door":
        return f"warp door into spot {g('spot')} (difficulty {g('difficulty')})"
    if how == "field":
        return f"warp into field {g('spot')} start group {g('group')}" + (
            f" (warp {g('warp')})" if g("warp") is not None else "") + (
            f", leaving by room {g('escape')}'s own spot (same map)" if g("escape") is not None else "")
    if how == "mission":
        return f"warp into mission {g('spot')}" + (f" for quest {g('quest')}" if g("quest") else "") + (
            f", back to {g('back')}")
    if how == "teleport":
        return f"warp teleport on spot {g('spot')} to {_v(g('pos'))}"
    return f"warp {how} " + _pairs(e, ("t", "k", "how"))


def troop_text(e, g):
    if g("ev") == "contract":
        return f"troop {g('troop')} level {g('level')} joined the barracks (contract set {g('set')})"
    if g("ev") == "deploy":
        return "deck troops in the room: " + ", ".join(f"uid {u} troop {i} level {lv} AP {ap}"
                                                        for u, i, lv, ap in g("troops") or ())
    if g("ev") == "ap":
        return "troop AP" + _why(g) + ": " + ", ".join(f"troop {i} AP {ap}" for i, ap in g("troops") or ())
    if g("ev") == "exp":
        return (f"troop {g('troop')} exp +{g('add')}: " + (f"level up to {g('level')}" if g("up") else
                                                          f"level {g('level')}") + f", {g('exp')}/{_need(g('need'))}")
    slots = ", ".join(f"slot {i} troop {t}" for i, t in enumerate(g("slots") or (), 1) if t)
    return f"troop deck {g('deck')}: {slots or 'empty'}"


ECONOMY = {"quest": quest_text, "item": item_text, "loot": loot_text, "mail": mail_text, "warp": warp_text,
           "troop": troop_text,
           "gold": lambda e, g: f"gold {g('delta'):+d}{_why(g)}, now {g('gold')}",
           "exp": lambda e, g: (f"exp +{g('add')}{_why(g)}: " + (f"level up to {g('level')}" if g("up") else
                                                                  f"level {g('level')}")
                                + f", {g('exp')}/{_need(g('need'))}")}


def _req(req, names=NONE):
    if not req:
        return "(no request)"
    return f"{req.get('role')} 0x{req.get('id', 0):04x} {req.get('fn') or names.packet(req.get('id'))}".rstrip()


def hits_text(e, most=6):
    by = sorted(e.get("by") or (), key=lambda r: -r[2])
    on = sorted(e.get("on") or (), key=lambda r: -r[1])
    more = lambda rows: f", +{len(rows) - most} more" if len(rows) > most else ""
    dealt = ", ".join(f"{a} x{n} = {d}" for a, n, d in by[:most]) + more(by)
    taken = ", ".join(f"{u} -{d} ({hp}/{top} left)" for u, d, hp, top in on[:most]) + more(on)
    return f"hits {e.get('secs', PACKET_S)} s: {dealt} | taken: {taken}"


@functools.lru_cache(maxsize=None)
def projectile_names():
    """{projectileinfo ID: its %Basic StringID} (42 PRJ_ELF_ARCHER_AZILIA, 5 PRJ_ELF_ARCHER); {} without the game's
    Info.pkg."""
    try:
        from . import tables
        return {int(r["ID"]): r["StringID"] for r in tables.sections("projectileinfo")["Basic"] if r["ID"].isdigit()}
    except Exception:
        return {}


def proj_text(e):
    """A troop's shots in one second (telemetry.js 'proj'): its StartFire volleys (the damage report's source) and the
    arrows ProjectileGroup::ShotProjectile made (the ones drawn), the projectile type and the volley's target (0xffff:
    a ground point)."""
    g = e.get
    kind = g("type")
    name = projectile_names().get(kind, "") if isinstance(kind, int) else ""
    what = f"projectile {kind}" + (f" ({name})" if name else "")
    target = g("target")
    at = ("" if target is None else " at the ground" if target == 0xffff
          else " at troop 0 (the hero)" if target == 0 else f" at troop {target}")
    plural = lambda n, word: f"{n} {word}" + ("" if n == 1 else "s")
    counts = []
    if g("volleys"):
        counts.append(plural(g("volleys"), "volley"))
    arrows = g("arrows") or 0
    counts.append(plural(arrows, "arrow") if arrows else "no arrow")
    return f"troop {g('troop')} fires {what}{at}: " + ", ".join(counts)


def client_text(e, names=NONE):
    """The readable text of a client telemetry event (tools/frida/telemetry.js), or None for a heartbeat or a pulse
    (ClientStream reads their gaps); one it cannot read, as its fields."""
    try:
        return _client_text(e, names)
    except Exception:
        return f"{e.get('k')} " + _pairs(e, ("t", "k"))


EXIT_CODES = {                  # the game's exit code as the recorder reads it when its session detaches (Windows NTSTATUS)
    0: "normal exit", 1: "terminated (TerminateProcess / taskkill, code 1)",
    0xC0000005: "access violation", 0xC0000409: "fast fail (__fastfail / stack buffer overrun)",
    0xC00000FD: "stack overflow", 0xC0000374: "heap corruption", 0x80000003: "breakpoint",
    0xC000013A: "closed by Ctrl+C / console close", 0x40010004: "killed by a debugger or the system",
}


def _client_text(e, names):
    k, g = e.get("k"), e.get
    if k == "log":
        return f"log {g('text')}"
    if k == "send":
        return f"send 0x{g('id'):04x} {names.packet(g('id'))}".rstrip() + f" len {g('len')}"
    if k == "recv":
        act = f" act 0x{g('act'):x} {names.actions.get(g('act'), '')}".rstrip() if g("act") is not None else ""
        return f"recv 0x{g('id'):04x} {names.packet(g('id'))}".rstrip() + act
    if k == "net":
        return net_text(e, names)
    if k == "state":
        return "state " + state_text(e, e.get("changed") or (), names)
    if k == "ready":
        return "telemetry attached"
    if k == "recorder":
        return f"recorder pid {g('pid')}, checkout {g('commit')}, probe {g('probe_sha256')}"
    if k == "troop_room":
        return f"troop observer room {g('spot')} (entry {g('room_epoch')})"
    if k == "troop_error":
        return f"TROOP PROBE ERROR {g('text')}"
    if k == "troop_engage":
        return (f"troop {g('from')} reports engagement with {g('target')}" if g("engaged") else
                f"troop {g('from')} reports disengagement")
    if k == "troops":
        rows = g("rows") or []
        good = [r for r in rows if not r.get("missing") and not r.get("error")]
        return (f"troop sample room {g('spot')}: {len(good)}/{g('tracked')} read, "
                f"{sum(bool(r.get('missing')) for r in rows)} missing, "
                f"{sum(bool(r.get('error')) for r in rows)} errors, {g('deferred')} deferred, "
                f"{g('elapsed_ms')} ms" + (f", {g('skipped')}" if g("skipped") else ""))
    if k == "error":
        return f"PROBE ERROR {g('text')}"
    if k == "key":
        return keys_text([(g("ev"), g("name"), g("map"))], names)
    if k == "screen":
        return f"screen {g('name')}"
    if k == "lesson":
        return lesson_text(e, names) or "lesson closed"
    if k == "sys":
        return f"system line \"{g('text')}\""
    if k == "hero_act":
        acts, i, p = unit_actions(), g("id"), g("played")
        named = lambda a: f"{a} {acts[a] if isinstance(a, int) and 0 <= a < len(acts) else ''}".rstrip()
        mode = {1: " (combat mode)", 0: " (town mode)"}.get(g("combat"), "")
        plays = f", plays {named(p)}" if isinstance(p, int) and p != i else ""   # PlayAction maps it by the flag
        return f"hero action {named(i)}{plays}{mode}"
    if k == "stance":
        return f"stance {g('ai')}" + (f" troop {g('troop')}" if g("troop") is not None else "") + (
            " refused" if g("applied") == 0 else "")
    if k == "proj":
        return proj_text(e)
    if k == "sel":
        return f"selected troop {g('troop')}"
    if k == "crash":
        mem = f" (memory {g('mem')})" if g("mem") else ""
        return f"CRASH {g('type')} at {g('at')}{mem}, from " + " < ".join(g("bt") or [])
    if k == "exit":
        return f"process exit: {g('how')} code {g('code')}, from " + " < ".join(g("bt") or [])
    if k == "died":
        code = g("code")
        named = EXIT_CODES.get(code)
        return (f"game process ended ({g('reason')}), exit code "
                + (f"0x{code:x}" if isinstance(code, int) else "unknown") + (f": {named}" if named else ""))
    if k in ("beat", "pulse"):
        return None
    if k == "gap":
        return g("text")
    return f"{k} " + _pairs(e, ("t", "k"))


def keys_text(keys, names=NONE):
    """The InputEvents the client reported at one instant, as one line: one click reports 6-7 of them across the key
    maps (live 2026-09-29 17:42:31.653: KEY_MouseLClick, KEY_SelectTarget, KEY_SelectTargetGroup, KEY_OffensiveMove,
    KEY_Pad_A_Up_, KEY_DragEnd); the first with a default key leads. keys: [(value, name, map)]."""
    if len(keys) == 1:
        ev, name, m = keys[0]
        where = f" (map {m} {KEY_MAPS.get(m, '')}".rstrip() + ")" if m is not None else ""
        return f"key {key_name(ev, name, names)}{where}"
    lead = next((i for i, k in enumerate(keys) if k[0] in DEFAULT_KEYS), 0)
    rest = [names.inputs.get(ev) or name or f"InputEvent {ev}" for i, (ev, name, _) in enumerate(keys) if i != lead]
    maps = sorted({m for _, _, m in keys if m is not None})
    where = (f" (map {maps[0]} {KEY_MAPS.get(maps[0], '')}".rstrip() + ")" if len(maps) == 1 else
             f" (maps {', '.join(map(str, maps))})" if maps else "")
    return f"key {key_name(keys[lead][0], keys[lead][1], names)} + " + ", ".join(rest) + where


def lesson_text(e, names=NONE):
    """A lesson on screen: the client's id (the missiontutorial row's Index) with its name, the page."""
    lid = e.get("lesson", e.get("id"))
    if lid is None:
        return None
    page = e.get("page")
    return f"lesson {lid}" + (f" {names.lessons[lid]}" if lid in names.lessons else "") + (
        f" page {page}" if page is not None else "") + (" done" if e.get("done") else "")


def state_text(e, fields, names=NONE):
    out = []
    for f in fields:
        v = e.get(f)
        if f == "view":
            out.append(f"view {VIEWS.get(v, v)}")
        elif f == "cut":
            out.append("cutscene " + ("playing" if v == 5 else "idle" if v == 0 else str(v)))
        elif f == "input":
            out.append("input " + ("free" if v == 1 else "locked" if v == 0 else str(v)))
        elif f == "ui":
            out.append("ui " + ", ".join(v or ()))
        elif f == "lesson":
            out.append((lesson_text(v, names) if isinstance(v, dict) else None) or f"lesson {v}")
        else:
            out.append(f"{f} {_v(v)}")
    if e.get("hero"):
        out.append(f"hero {_v(e['hero'])}")
    return ", ".join(out)


def net_text(e, names=NONE):
    """A second of the client's packets: each id sent and received with its count, the script actions by name."""
    hexid = lambda i: f"0x{i:04x}" if isinstance(i, int) else str(i)
    part = lambda counts: ", ".join(f"{hexid(i)} {names.packet(i)}".rstrip() + (f" x{n}" if n > 1 else "")
                                    for i, n in counts)
    acts = {}
    for a in e.get("acts") or ():
        acts[a] = acts.get(a, 0) + 1
    act = ", ".join((names.actions.get(a) or hexid(a)) + (f" x{n}" if n > 1 else "") for a, n in acts.items())
    sent, got = part(e.get("sent") or ()), part(e.get("recv") or ())
    return "net: " + "; ".join(x for x in (f"sent {sent}" if sent else "", f"recv {got}" if got else "",
                                           f"actions {act}" if act else "") if x)


class ClientStream:
    """Client telemetry events -> readable lines in time order: packets as one "net" line a second (the line held
    until its second is over, with the lines of that second), heartbeats and pulses only as their gaps ("heartbeat
    back after N s", "game thread stuck", "no pulse": the game or the probe gone), the keys of one instant as one
    line (keys_text) and a run of camera keys as one, a system line once (twin)."""

    def __init__(self, names=NONE):
        self.names = names
        self.bucket, self.held = None, []
        self.beat_at = self.pulse_at = None
        self.stuck = self.gone = False
        self.reps = {}               # per channel ("log", "key": the two interleave), the line repeating (a log line
                                     # numbers aside, a key line, camera keys): {stem, t, last, text, n}
        self.instant = None          # the keys of the instant being reported: {t, keys: [(value, name, map)]}
        self.sys = None              # the last system line shown: (t, text)

    def twin(self, e):
        """Whether e is the second hook's copy of the system line just shown (SYS_TWIN_MS)."""
        return (e.get("k") == "sys" and self.sys is not None and self.sys[1] == e.get("text")
                and abs(e.get("t", 0) - self.sys[0]) <= SYS_TWIN_MS)

    def feed(self, e):
        """The lines this event lets out: [(t, text)], in time order."""
        t, k = e.get("t", 0), e.get("k")
        if self.instant is not None and t != self.instant["t"] and k != "pulse":   # a pulse comes from the probe's
            self._keys()                                                          # own thread, any time
        out = self.tick(t)
        if k != "pulse":
            self.gone = False
        if k in ("send", "recv"):
            if self.bucket is None:
                self.bucket = {"t": t, "sent": {}, "recv": {}, "acts": []}
            side = self.bucket["sent" if k == "send" else "recv"]
            side[e.get("id")] = side.get(e.get("id"), 0) + 1
            if k == "recv" and e.get("act") is not None:
                self.bucket["acts"].append(e["act"])
            return out
        if k == "beat":
            if self.beat_at is not None and t - self.beat_at > BEAT_GAP_S * 1000:
                self._hold(t, f"heartbeat back after {round((t - self.beat_at) / 1000)} s")
            self.beat_at, self.stuck = t, False
        elif k == "pulse":
            self.pulse_at = t
            age = e.get("beat_age") or 0
            if age > BEAT_GAP_S * 1000 and not self.stuck:
                self.stuck = True
                self._hold(t, f"game thread stuck: no heartbeat for {round(age / 1000)} s")
        elif k == "log":
            text = (client_text(e, self.names) or "").rstrip()
            self._line("log", t, text, re.sub(r"-?\d+(\.\d+)?", "#", text))   # a line logged every frame (a fade)
        elif k == "key":
            if self.instant is None:
                self.instant = {"t": t, "keys": []}
            self.instant["keys"].append((e.get("ev"), e.get("name"), e.get("map")))
        elif k == "sys":
            if not self.twin(e):
                self.sys = (t, e.get("text"))
                self._hold(t, client_text(e, self.names))
        else:
            text = client_text(e, self.names)
            if text is not None:
                self._hold(t, text)
        return out + self._release()

    def _line(self, channel, t, text, stem, summary=None):
        """A line, or one more of the channel's run of lines with its stem within REPEAT_S: the first is shown as it
        comes, the run as one summary line (summary, else the last line's text) once it is over (_fold)."""
        rep = self.reps.get(channel)
        if rep and rep["stem"] == stem and t - rep["last"] < REPEAT_S * 1000:
            rep.update(last=t, text=summary or text, n=rep["n"] + 1)
        else:
            self._fold(channel)
            self.reps[channel] = {"stem": stem, "t": t, "last": t, "text": summary or text, "n": 1}
            self._hold(t, text)

    def _keys(self):
        """The line of the key instant that is over: through _line, so a run of camera keys is one line."""
        g, self.instant = self.instant, None
        text = keys_text(g["keys"], self.names)
        camera = all(m == CAMERA_MAP for _, _, m in g["keys"])
        self._line("key", g["t"], text, "camera" if camera else text, "key camera" if camera else None)

    def _fold(self, channel):
        """The summary of a channel's repeated line, once its run is over (the first line was shown as it came)."""
        rep = self.reps.pop(channel, None)
        if rep and rep["n"] > 1:
            self._hold(rep["last"], f"{rep['text']} (x{rep['n']} in {(rep['last'] - rep['t']) / 1000:.1f} s)")

    def tick(self, now):
        """Close the key instant and the packet second once they are over (now: epoch ms), and say when pulses
        stopped."""
        if self.instant is not None and now - self.instant["t"] >= KEY_INSTANT_MS:
            self._keys()
        for channel in [c for c, rep in self.reps.items() if now - rep["last"] >= REPEAT_S * 1000]:
            self._fold(channel)
        if self.bucket is not None and now - self.bucket["t"] >= PACKET_S * 1000:
            self._close()
        out = self._release()
        if self.pulse_at is not None and not self.gone and now - self.pulse_at > PULSE_GAP_S * 1000:
            self.gone = True
            out.append((now, f"no pulse for {round((now - self.pulse_at) / 1000)} s: the game or the probe is gone"))
        return out

    def finish(self):
        """The lines still held (the end of a file)."""
        if self.instant is not None:
            self._keys()
        for channel in list(self.reps):
            self._fold(channel)
        self._close()
        return self._release()

    def _close(self):
        b, self.bucket = self.bucket, None
        if b is not None:
            self.held.append((b["t"], client_text({"k": "net", "sent": list(b["sent"].items()),
                                                   "recv": list(b["recv"].items()), "acts": b["acts"]}, self.names)))

    def _hold(self, t, text):
        self.held.append((t, text))

    def _release(self):
        if self.bucket is not None:              # a second still open: its lines wait for its net line
            return []
        out, self.held = sorted(self.held, key=lambda x: x[0]), []
        return out

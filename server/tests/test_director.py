"""The mission director (director.py) and its tables (kuf2/scenes/m<spot>.py)."""
import math
import pathlib
import struct

import pytest

from kuf2 import director, game, zone
from test_battle import NoSave, acts, mission_room, pkt, walk

TABLES = sorted(int(p.stem[1:]) for p in (pathlib.Path(director.__file__).parent / "scenes").glob("m*.py"))
TRIGGERS = {"start": (), "bound": ("bound",), "wake": ("force",), "down": (), "hp": ("below",), "won": (), "closed": (),
            "after": ("step",), "engage": ("force",), "left": ("force", "count"), "skill": ("troop", "force"),
            "cond": ("cond",), "prompt": ("keys",), "finish": ("troop",), "broken": ("prop",), "used": ("prop",),
            "arrive": ("force", "bound"), "near": ("troop",)}
ACTIONS = {"say": (3, 4), "wake": (2, 14), "move": (3, 4), "open": (2, 2), "heal": (1, 2), "win": (1, 1),
           "leave": (2, 2), "tutorial": (2, 2), "cutscene": (3, 3), "march": (3, 3), "march straight": (3, 3), "march line": (3, 3), "march past": (3, 3), "march one": (3, 3),
           "notice": (2, 3), "panel": (3, 3), "gauge": (4, 4), "done": (2, 2), "count": (4, 4), "state": (2, 2), "finish": (1, 1),
           "escort": (2, 9), "hand": (2, 2), "complete": (1, 1), "shoot": (3, 3), "spawn": (2, 14), "point": (2, 2), "highlight": (2, 3),
           "highlight troop": (2, 4), "fade": (4, 4), "move deck": (3, 4), "camera troop": (3, 3),
           "untouchable troop": (3, 3), "troops bar": (3, 3), "route": (3, 4), "clock": (4, 4), "clock off": (2, 2),
           "panel start": (1, 1), "banner": (2, 3), "force bar": (3, 3)}


def tutorial_steps(name):
    """The pages of a missiontutorial row (TextID1..6 that are set)."""
    from kuf2 import tables
    row = next(r for r in tables.sections("missiontutorial")["MissionTutorialType"] if r["MissionTutorialType"] == name)
    return [row["TextID%d" % k] for k in range(1, 7) if str(row.get("TextID%d" % k, "")).isdigit()]


def scene_lessons(spot):
    """The lessons the cutscenes a table plays start themselves (cutscenes.json "tutorials": missiontutorial Index):
    Tower's 5_WingedWorm_Appeared starts 133_Command_X, which its table asks about."""
    import json
    from kuf2 import tables
    names = {int(r["Index"]): r["MissionTutorialType"]
             for r in tables.sections("missiontutorial")["MissionTutorialType"]}
    played = {a[1] for st in director.script(spot) for a in st.get("do", ()) if a[0] == "cutscene"}
    where = str((tables.by_id("spottable").get(str(spot)) or {}).get("Map_File", "")).lower()
    rows = json.loads((pathlib.Path(director.__file__).parents[2] / "planning" / "scripts" / "cutscenes.json")
                      .read_text(encoding="utf-8"))
    return {names.get(t) for r in rows if r["map"].lower() == where and r["slot"] in played for t in r["tutorials"]}


def lines_shown(s):
    """(speaker uid, leader flag, line id) of every 0xc76f sent, in order."""
    out = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_SCRIPT_ACTION and struct.unpack_from("<I", b)[0] == director.ACT_HELP_TEXT_BY_TROOP:
            _, lead, uid, _, line, _ = struct.unpack_from("<6I", b)
            out.append((uid, lead, line))
    return out


def shown(s):
    """What a room sent to the screen, in order: ("line", id), ("title", id), ("group", id), ("panel", line),
    ("notice", NoticeTable row, (ids)), ("bar", text, ref kind, ref id, a6)."""
    out = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto != game.S2C_SCRIPT_ACTION:
            continue
        a = list(struct.unpack_from("<%dI" % (len(b) // 4), b))
        if a[0] == director.ACT_HELP_TEXT_BY_TROOP:
            out.append(("line", a[4]))
        elif a[0] == game.ACT_SITUATION_TITLE:
            out.append(("title", a[2]))
        elif a[0] == game.ACT_SITUATION_GROUP:
            out.append(("group", a[2]))
        elif a[0] == game.ACT_SITUATION_LINE:
            out.append(("panel", a[3]))
        elif a[0] == director.ACT_NOTICE_WINDOW:
            out.append(("notice", a[1], tuple(i for i in a[2:6] if i != director.NO_TEXT)))
        elif a[0] == game.ACT_SITUATION_TROOPS_BAR:
            out.append(("bar", *a[3:7]))
    return out


from conftest import run_pending  # noqa: E402,F401  (the scene tests import it from here)


@pytest.mark.parametrize("spot", TABLES)
def test_every_table_names_real_bounds_lines_forces_and_troops(spot):
    z = zone.for_spot(spot)
    forces = {t.get("ForceNum") for t in z["NPCTroopInfoData"]}
    troops = {t["TroopID"] for t in z["NPCTroopInfoData"]}
    aliases = {str(t.get("TroopAlias") or "").replace(" ", "") for t in z["NPCTroopInfoData"]}
    props = {p["SmartPropID"] for p in z["SmartPropData"]}
    lines = director.lines(spot)
    steps = director.script(spot)
    ids = {st.get("id") for st in steps} - {None}
    one = lambda a: a == "hero" or (a in troops if isinstance(a, int) else str(a).replace(" ", "") in aliases)
    actor = lambda a: all(one(x) for x in a) if isinstance(a, tuple) else one(a)     # a tuple: any of them
    of = lambda v, pool: all(x in pool for x in v) if isinstance(v, tuple) else v in pool
    assert steps
    for st in steps:
        assert st["on"] in TRIGGERS and all(k in st for k in TRIGGERS[st["on"]]), st
        if st["on"] == "bound":
            assert director.bound(spot, st["bound"]) is not None, st
        if st["on"] in ("skill", "finish", "near"):
            assert actor(st["troop"]), st
        if st["on"] in ("wake", "down", "engage", "left", "skill", "arrive") and "force" in st:
            assert of(st["force"], forces), st
        if st["on"] == "arrive":
            assert director.bound(spot, st["bound"]) is not None, st
        if st["on"] in ("broken", "used"):
            assert of(st["prop"], props), st
        if st.get("in") is not None:                    # a prompt counted only in that bound
            assert st["on"] == "prompt" and director.bound(spot, st["in"]) is not None, st
        unless = st.get("unless")
        assert unless is None or of(unless, ids), st
        if st["on"] == "down":
            assert ("force" in st) != ("troop" in st), st
            assert st.get("troop") is None or st["troop"] in troops, st
        if st["on"] == "hp":
            assert ("force" in st) != ("troop" in st) and 0 < st["below"] < 100, st
            assert st.get("force") in forces if "force" in st else actor(st["troop"]), st
            assert st.get("by") in (None, "mine") or actor(st["by"]), st      # whose hit counts
        if st["on"] == "after":
            assert st["step"] in ids, st
        if st["on"] == "cond" and st["cond"][0] == director.COND_TUTORIAL_PAST:  # (name, n): a pop-up the table shows,
            _, name, n = st["cond"]                                              # or one a scene it plays starts
            assert ("tutorial", name) in {a for x in steps for a in x.get("do", ())} or name in scene_lessons(spot), st
            assert -1 <= n < len(tutorial_steps(name)) - 1, st
        if st["on"] == "prompt":                        # InputEvent values; put up when the step it needs fires
            assert st["keys"] and all(0 < k < 0x11e for k in st["keys"]) and st.get("needs"), st
        if ("complete",) in st.get("do", ()):           # 0xc898 completes step 0 only (0x140b5db70): a one-step pop-up,
            before = next(x for x in steps if x.get("id") == st.get("needs"))    # asked for by the cond it follows
            assert before["on"] == "cond" and len(tutorial_steps(before["cond"][1])) == 1, st
        assert st.get("needs") is None or st["needs"] in ids, st
        for a in st.get("do", ()):
            lo, hi = ACTIONS[a[0]]
            assert lo <= len(a) <= hi, a
            if a[0] == "say":
                assert a[1] is None or actor(a[1]), a
                assert a[2] in lines, a
            elif a[0] == "wake":
                assert all(f in forces for f in a[1:]), a
            elif a[0] == "spawn":
                assert all(u in troops for u in a[1:]), a
            elif a[0] == "point":
                assert director.bound(spot, a[1]) is not None, a
            elif a[0] == "highlight troop":             # (who[, on 0 / 1[, seconds]])
                assert a[1] != "hero" and actor(a[1]) and (len(a) < 3 or a[2] in (0, 1)), a
            elif a[0] == "move":
                assert actor(a[1]) and director.bound(spot, a[2]) is not None, a
            elif a[0] == "move deck":
                assert a[1] in (1, 2, 3) and director.bound(spot, a[2]) is not None, a
            elif a[0] == "open":
                assert a[1] in props, a
            elif a[0] == "leave":
                assert a[1] != "hero" and actor(a[1]), a
            elif a[0] == "route":                       # (who, MissionPath id[, exit bound])
                assert a[1] != "hero" and actor(a[1]) and a[2] > 0, a
                assert len(a) < 4 or director.bound(spot, a[3]) is not None, a
            elif a[0] in ("notice", "panel", "banner"):
                assert all(i in lines for i in a[1:]), a
            elif a[0] == "done":
                assert a[1] in lines, a
            elif a[0] == "count":
                assert a[1] in lines and a[2] in lines and a[3] in forces, a
            elif a[0] == "clock":                       # (group, text, seconds)
                assert a[1] in lines and a[2] in lines and a[3] > 0, a
            elif a[0] == "clock off":                   # (group): a clock the table starts
                assert ("clock", a[1]) in {b[:2] for x in steps for b in x.get("do", ())}, a
            elif a[0] == "gauge":
                assert a[1] in lines and a[2] in lines and actor(a[3]), a
            elif a[0] == "state":
                assert a[1] < 0, a                      # a wait state; >= 0 would set camera n
            elif a[0] == "camera troop":
                assert actor(a[1]) and a[2] >= 0, a
            elif a[0] == "untouchable troop":
                assert actor(a[1]) and a[2] in (0, 1), a
            elif a[0] == "troops bar":                  # (text, troop): a missiontext label and a troop of the zone
                assert a[1] in lines and actor(a[2]) and a[2] != "hero", a
            elif a[0] == "force bar":                   # (text, force): a missiontext label and a force of the zone
                assert a[1] in lines and a[2] in forces, a
            elif a[0] == "escort":
                assert all(w in forces if isinstance(w, int) else actor(w) for w in a[1:]), a
            elif a[0] == "hand":
                assert actor(a[1]) and a[1] in director.hand_later(spot), a
            elif a[0] == "shoot":
                assert a[1] != "hero" and actor(a[1]) and (a[2] == "nearest" or actor(a[2])), a
            elif a[0] == "tutorial":                    # a row of this map whose texts the map has
                from kuf2 import tables
                row = next(r for r in tables.sections("missiontutorial")["MissionTutorialType"]
                           if r["MissionTutorialType"] == a[1])
                assert int(row["TextID1"]) in lines, a
    import importlib
    hold = getattr(importlib.import_module(f"kuf2.scenes.m{spot}"), "HOLD", ())
    assert set(hold) <= forces
    woken = {f for st in steps for a in st.get("do", ()) if a[0] == "wake" for f in a[1:]}
    spawned = {u for st in steps for a in st.get("do", ()) if a[0] == "spawn" for u in a[1:]}
    woken |= {f for f in forces if all(t["TroopID"] in spawned for t in z["NPCTroopInfoData"]      # one by one
                                       if t.get("ForceNum") == f and game.hostile(t))}
    fighting = {t.get("ForceNum") for t in z["NPCTroopInfoData"] if game.hostile(t)}
    if director.table_wins(spot):                       # won by its own step: a held force may stay out (Tower's
        assert any(a[0] == "win" for st in steps for a in st.get("do", ())), "WIN = table and no win step"   # F35000)
    else:
        assert set(hold) & fighting <= woken, "a held enemy force no step brings in: the mission could never be won"
    assert set(director.held_props(spot)) <= {a[1] for st in steps for a in st.get("do", ()) if a[0] == "open"}
    assert all(w in forces if isinstance(w, int) else actor(w) for w in director.escort(spot))
    assert set(director.hand_later(spot)) <= {a[1] for st in steps for a in st.get("do", ()) if a[0] == "hand"}


def cutscenes(s):
    return [struct.unpack_from("<3I", bytes(w.buf))[1] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_CUTSCENE]


def rooms_at_cutscenes(monkeypatch):
    """[(slot, the room's troop uids)] at each ActCutScenePlayCutScene sent from now on: what the scene's ACTOR tracks
    can bind when the client plays it."""
    seen, send = [], game.send_actions

    def spy(room, *actions):
        seen.extend((a[1], set(room.data["zone_troops"])) for a in actions if a[0] == director.ACT_CUTSCENE)
        return send(room, *actions)
    monkeypatch.setattr(game, "send_actions", spy)
    return seen


def test_grey_rock_opens_with_its_cutscene_then_glen_and_thompson():
    # live 2026-09-28: 0_Start_CutScene (53 s) voices the hanged corpses (19000-19070); then 1200 "Commander, select
    # Entire Troop..." (Glen, troop 10000, as his leader), 1201 (Thompson, 10071), then after the F4 lesson 1210 (1220
    # waits for the path out of the camp: test_scenes_10234)
    s = mission_room(10234)
    assert cutscenes(s) == [0] and lines_shown(s) == []
    assert min(d for d, _ in s.pending) > 52.9          # the lines wait for its 53 s
    run_pending(s)
    assert lines_shown(s) == [(10000, 1, 1200), (10071, 1, 1201)]     # "Everyone, let's move!" waits for the F4
    obey(s)
    assert lines_shown(s)[:3] == [(10000, 1, 1200), (10071, 1, 1201), (10000, 1, 1210)]
    assert not [line for _, _, line in lines_shown(s) if 19000 <= line < 19100]


def test_grey_rock_moves_everyone_into_the_fortress_after_its_mid_cutscene():
    # 3_Mid_CutSCene (29 s) at P1_S2_다음 서브, then the hero, Glen, Thompson and the four troops to their P2 places
    # (live: without the moves the troops stayed at the entrance hill)
    s = mission_room(10234)
    run_pending(s)
    b = director.bound(10234, "P1_S2_다음 서브")
    s.sent.clear()
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    assert not [w for w in s.sent if w.proto == game.S2C_TROOP_BACK]     # nobody moves before the cutscene
    run_pending(s)
    assert cutscenes(s) == [3]
    moved = {struct.unpack_from("<H", bytes(w.buf), 7)[0] for w in s.sent if w.proto == game.S2C_TROOP_BACK}
    assert moved == {0, 10000, 10071, 10072, 10073, 10004, 10005}
    assert s.data["hero_pos"][0] == 109228


def test_a_line_whose_speaker_is_not_in_the_room_shows_alone():
    # Golden Hammer's 19530 has no troop: uid 0xffff, leader 0 (0x140c5f230 shows the text without a name)
    s = mission_room(10234)
    run_pending(s)                               # the opening scene's lines first
    director.say(s, None, 19530)
    director.say(s, 20082, 3110)                 # the troll is held back: not spawned yet
    run_pending(s)
    assert lines_shown(s)[-2:] == [(director.NO_TROOP, 0, 19530), (director.NO_TROOP, 0, 3110)]
    director.say(s, "hero", 1000)
    run_pending(s)
    assert lines_shown(s)[-1] == (0, 1, 1000)


def test_grey_rock_plays_its_ending_before_the_victory_window():
    s = mission_room(10234)
    run_pending(s)
    game.mission_won(s, NoSave())
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)
    assert not s.data.get("mission_won")
    game.mission_won(s, NoSave())                # a second call while the lines play changes nothing
    run_pending(s)
    ending = [line for _, _, line in lines_shown(s) if line in (3130, 3140, 3150)]
    assert ending == [3130, 3140, 3150] and cutscenes(s)[-1] == 13          # 13_EndScene voices 19500-19550
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1 and s.data["mission_won"]


def test_glen_restores_the_hero_each_time_he_falls_low(monkeypatch):
    # "Take better care of yourself! I'll restore your HP for now." (1000): the hero back to full, every time his
    # line has played (adversarial 2026-09-28: ten falls within a second had queued 78 s of it ahead of the story)
    import time
    clock = [time.monotonic()]
    monkeypatch.setattr(director.time, "monotonic", lambda: clock[0])
    s = mission_room(10234)
    run_pending(s)
    hero = s.data["battle"].troops[0]
    for fall in range(3):
        hero["hp"] = 100
        director.on_hp(s, 0, 100, hero["max"])
        run_pending(s)
        assert hero["hp"] == (hero["max"] if fall != 1 else 100)        # the second fall: his line still plays
        director.on_hp(s, 0, hero["max"], hero["max"])
        clock[0] += 0.5 if fall == 0 else 120
    assert [line for _, _, line in lines_shown(s)].count(1000) == 2


def test_the_sorcerer_lets_the_wolves_loose_at_half_hp():
    s = mission_room(10234)
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20073), "test")
    assert 20060 not in s.data["zone_troops"]
    top = s.data["battle"].troops[20078]["max"]
    director.on_hp(s, 20078, top * 6 // 10, top)
    assert 20060 not in s.data["zone_troops"]
    director.on_hp(s, 20078, top * 4 // 10, top)
    assert 20060 not in s.data["zone_troops"]  # "Release the Wolves!" first
    run_pending(s)
    assert 20060 in s.data["zone_troops"]      # force 20061 "내성 : 늑대"
    assert 2360 in [line for _, _, line in lines_shown(s)]


def test_a_mission_without_a_table_runs_as_before():
    # Steel Plain 10318 (no scenes/m10318.py): no line, and the victory window at once
    assert director.script(10318) == ()
    s = mission_room(10318)
    game.mission_won(s, NoSave())
    assert not lines_shown(s) and any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)


def test_a_step_of_a_difficulty_is_for_a_room_of_it_alone():
    # Fort Valley's Ukuron and right wall: on the Hard tape only, in forces the zone does not mark for Hard
    normal, hard = mission_room(10306, 0), mission_room(10306, 1)
    assert director.for_hero(normal, {"on": "down"}) and director.for_hero(hard, {"on": "down"})
    assert director.for_hero(normal, {"on": "down", "difficulty": 0})
    assert not director.for_hero(hard, {"on": "down", "difficulty": 0})
    assert director.for_hero(hard, {"on": "down", "difficulty": 1})
    assert not director.for_hero(normal, {"on": "down", "difficulty": 1})
    ids = lambda s: [st.get("id") for _, st in director._pending(s, "down") if st.get("force") == 20100]
    assert ids(normal) == ["gate 2"] and ids(hard) == ["ukuron"]


def sync_body(records):
    """A 0x50b0 body: records of (uid, x, y, z), no leader bytes, formation 0 (game.sync_positions)."""
    from kuf2 import obf
    b = struct.pack("<H", len(records))
    for uid, x, y, z in records:
        q, p15 = obf.pos_xz(x, z)
        b += bytes([0, 0]) + struct.pack("<Hh", uid, 0) + q + struct.pack("<h", y) + bytes([p15, 0])
    return b


def test_the_lunawing_the_player_flies_reaches_the_destination():
    # Sortie I 10361: the Lunawing 10000 (루나윙_본체) is handed to the player; its position in the host's 0x50b0
    # counts as his for the destination 목적지 (191505, 272969), as the hero's does
    from test_battle import pkt
    s = mission_room(10361)
    assert 10000 in game.mission_plan(10361)["hand"]
    role = game.make(NoSave(), 0)
    sync = lambda recs: role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body(recs)))
    sync([(10000, 191505, 0, 272969 + 4000), (20000, 191505, 0, 272969)])      # an enemy there wins nothing
    assert not s.data.get("mission_won") and not s.data.get("director", {}).get("ending")
    sync([(10000, 191505, 0, 272969 + 1000)])
    run_pending(s)
    assert s.data.get("mission_won") and any(w.proto == game.S2C_MISSION_LEAVE for w in s.sent)   # no window (B2)


def test_a_force_the_table_holds_waits_for_its_step(monkeypatch):
    # HOLD: Grey Rock's troll force 20080 no longer wakes as the hero comes near nor by the fallback; a step brings it
    monkeypatch.setattr(director, "held", lambda spot: frozenset({20080}))
    s = mission_room(10234)
    walk(s, 150139, 142853 + 3000)
    assert 20082 not in s.data["zone_troops"]
    for _ in range(40):                                 # every other group by the fallback; the troll's still waits
        assert game.next_wave(s)                        # and the room is not won while it does
    assert 20082 not in s.data["zone_troops"] and any(w[0]["ForceNum"] == 20080 for w in s.data["waves"])
    director.run(s, ("wake", 20080))
    assert 20082 in s.data["zone_troops"]


def test_wake_brings_a_force_that_is_not_held_and_leave_takes_a_troop_away():
    # Grey Fog's staging force 26000 (inactive, in no wave: the "sandwich" on the south-east street) comes in on a
    # step; a troop that leaves is disabled (ActTroopSetEnableTroop 0xea6a kind 0, enable 0), down for the win rule
    # and out of the battle
    s = mission_room(10358)
    assert 26000 not in s.data["zone_troops"] and 15001 in s.data["zone_troops"]   # the villagers: the table's start
    director.run(s, ("wake", 26000))
    assert 26000 in s.data["zone_troops"]
    director.run(s, ("leave", 22003))
    sent = [list(struct.unpack_from("<5I", bytes(w.buf))) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_ENABLE_TROOP]
    assert sent == [[game.ACT_ENABLE_TROOP, 0, 22003, 0, 0]]
    assert 22003 in s.data["down"] and 22003 not in s.data["battle"].troops


def test_grey_rock_shows_its_tutorials_as_named_rows():
    # ActGuiStartTutorial 0xc896 takes the MissionTutorialType name as a C string (0x1415835b0 reads it from the
    # packet): the camp's F4 lesson after its lines, the groggy / finish lesson at the troll's 10 %
    def tutorials(s):
        return [bytes(w.buf)[4:].split(b"\0")[0].decode() for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
                and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_START_TUTORIAL]
    s = mission_room(10234)
    assert tutorials(s) == []                    # it waits for Glen's and Thompson's lines
    run_pending(s)
    assert tutorials(s) == ["134_SelectTroopSlot4"]
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20080), "test")
    top = s.data["battle"].troops[20082]["max"]
    director.on_hp(s, 20082, top // 20, top)
    run_pending(s)
    assert tutorials(s) == ["134_SelectTroopSlot4", "134_GroggyFinish"]


def test_the_cpu_leads_the_escort_to_each_story_place():
    # owner 2026-09-28 (the original's footage): "they move all commanders and all atack the enemies". Grey Rock's
    # ESCORT (Glen's force 10000 with his two troops, Thompson 10071): ActTroopMoveToArea (kind 0, uid, area, goal 1,
    # engage 1, flag 0, mode 0: the run) to each bound a step fires on; the player's handed troops take no such order
    s = mission_room(10234)
    run_pending(s)
    s.sent.clear()
    b = director.bound(10234, "P1_S2_다리 코볼트 전투")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    orders = [struct.unpack_from("<8I", bytes(w.buf)) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
              and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_MOVE_TO_AREA]
    assert {o[2] for o in orders} == {10000, 10004, 10005, 10071}
    assert all(o[3] == b["EventBoundID"] and o[4:] == (1, 1, 0, director.MOVE_RUN) for o in orders)
    assert not {10072, 10073} & {o[2] for o in orders}


def test_a_step_shows_its_lines_tutorials_and_notices_in_the_table_order():
    # Tower's wyrms (F30000, a staging force the table wakes itself), 5_WingedWorm_Appeared's end: 1330, the archer
    # lesson; then on its F2 1340, the notice 8100/8110, 1350, 8120/8130, as listed; the actions listed between two
    # lines go with the second (two timers for one moment fired in no set order: the lesson came after 1340). The
    # tape (part 2, frames 11:54-12:00): the F2 card up 11:56-11:57, F2 at 11:58, Glen's 1340 at 11:59 (harness report
    # row 'wyrms', partly)
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 30000))
    run_pending(s)
    del s.sent[:]
    wyrms = next(i for i, st in enumerate(director.script(10233)) if st.get("id") == "wyrms")
    director.fire(s, wyrms)                      # 5_WingedWorm_Appeared's end (its lesson done, its last 13 s)
    director.fire(s, wyrms)                      # once only
    run_pending(s)

    def order():
        out = []
        for w in s.sent:
            b = bytes(w.buf)
            act = struct.unpack_from("<I", b)[0] if w.proto == game.S2C_SCRIPT_ACTION else None
            if act == director.ACT_HELP_TEXT_BY_TROOP:
                out.append(struct.unpack_from("<6I", b)[4])
            elif act == director.ACT_START_TUTORIAL:
                out.append(b[4:].split(b"\0")[0].decode())
            elif act == director.ACT_NOTICE_WINDOW:
                out.append(("notice",) + struct.unpack_from("<7I", b)[1:])
        return out
    assert order() == [1330, "133_SelectTroopSlot2"]             # 1340 waits for the F2
    obey(s)                                      # the pop-up past its pages, then the player's F2
    no = director.NO_TEXT                        # ActGuiShowNoticeWindow: the left panel (NoticeTable 10003), its
    assert order() == [1330, "133_SelectTroopSlot2", 1340,                                                   # ids,
                       ("notice", 10003, 8100, 8110, no, no, director.NOTICE_S), 1350,                    # -1 ends
                       ("notice", 10003, 8120, 8130, no, no, director.NOTICE_S)]   # "Troop Skill" (the original 12:16)


def test_an_action_held_for_a_line_the_map_lacks_still_runs(monkeypatch):
    # an action between two lines goes with the second; when the map has no such line, it runs after the first
    s = mission_room(10233)
    run_pending(s)
    steps = list(director.script(10233)) + [{"on": "bound", "bound": 18020, "do": [
        ("say", "톰슨_1", 1050), ("tutorial", "133_Command_X"), ("say", "톰슨_1", 999999)]}]
    monkeypatch.setattr(director, "script", lambda spot: steps)
    del s.sent[:]
    director.fire(s, len(steps) - 1)
    run_pending(s)
    sent = [struct.unpack_from("<I", bytes(w.buf))[0] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    assert sent.index(director.ACT_START_TUTORIAL) > sent.index(director.ACT_HELP_TEXT_BY_TROOP)


def test_actions_held_behind_a_line_keep_the_queues_order_before_a_later_steps_line(monkeypatch):
    # a step's notice listed after its line waits for the line; a later step whose own notice and line are queued for
    # that same moment comes after it (two timers for one moment fire in no set order: Grey Rock's FP notice, held
    # behind 1260, came after 1270 queued by the bridge's step; the tape has 1260, 6010 / 6011, 6004 / 6005, 1270)
    steps = ({"on": "start", "do": [("say", None, 1040), ("notice", 8100, 8110)]},
             {"on": "bound", "bound": 18020, "do": [("notice", 8120, 8130), ("say", None, 1050)]})
    monkeypatch.setattr(director, "script", lambda spot: steps)
    s = mission_room(10233)
    walk(s, 67095, 70662)                        # 18020, while 1040 still shows
    run_pending(s)
    order = []
    for w in s.sent:
        b = bytes(w.buf)
        act = struct.unpack_from("<I", b)[0] if w.proto == game.S2C_SCRIPT_ACTION else None
        if act == director.ACT_HELP_TEXT_BY_TROOP:
            order.append(struct.unpack_from("<6I", b)[4])
        elif act == director.ACT_NOTICE_WINDOW:
            order.append(struct.unpack_from("<6I", b)[2])
    assert order == [1040, 8100, 8120, 1050]


def test_actions_held_behind_a_line_still_run_when_no_line_follows(monkeypatch):
    steps = ({"on": "start", "do": [("say", None, 1040), ("notice", 8100, 8110)]},)
    monkeypatch.setattr(director, "script", lambda spot: steps)
    s = mission_room(10233)
    assert not any(w.proto == game.S2C_SCRIPT_ACTION and bytes(w.buf)[:4] == director.ACT_NOTICE_WINDOW.to_bytes(
        4, "little") for w in s.sent)
    run_pending(s)
    assert sum(w.proto == game.S2C_SCRIPT_ACTION and bytes(w.buf)[:4] == director.ACT_NOTICE_WINDOW.to_bytes(
        4, "little") for w in s.sent) == 1
    assert director._state(s).get("held", []) == []


def test_a_panel_line_sends_its_group_once():
    # ActGuiAddObjectiveGroupToMissionSituation 0xc7ec for a group the panel lacks, then the line 0xc7f6; Tower's
    # start panel has group 110 (success conditions) already, the Tutorial group 200 comes with the first lesson
    s = mission_room(10233)                      # the start panel only (the lessons' timers not yet run)
    del s.sent[:]
    for group, line in ((200, 210), (200, 220), (110, 180)):
        director.run(s, ("panel", group, line))
    sent = [list(struct.unpack_from("<%dI" % (len(bytes(w.buf)) // 4), bytes(w.buf))) for w in s.sent
            if w.proto == game.S2C_SCRIPT_ACTION]
    t = game.ALL_TEAMS
    assert sent == [[game.ACT_SITUATION_GROUP, t, 200], [game.ACT_SITUATION_LINE, t, 200, 210],
                    [game.ACT_SITUATION_LINE, t, 200, 220], [game.ACT_SITUATION_LINE, t, 110, 180]]



@pytest.mark.parametrize("spot", TABLES)
def test_a_table_leaves_to_its_cutscenes_what_they_do_themselves(spot):
    # a cutscene can run a stretch of the mission itself (planning/scripts/cutscenes.json, tools/recon/cutscenes.py):
    # its help-box lines (System_GuiShowMissionHelpTextByTroopId) and a tutorial it starts and waits on
    # (System_StartTutorial + CheckCompleteTutorialSub). The table saying those lines again doubles them; starting
    # that tutorial itself closes the cutscene's, which then waits for ever (live 2026-09-28 21:21-21:25, Tower's
    # 5_WingedWorm_Appeared hung at black)
    import json
    from kuf2 import tables
    rows = json.loads((pathlib.Path(director.__file__).parents[2] / "planning" / "scripts" / "cutscenes.json")
                      .read_text(encoding="utf-8"))
    names = {int(r["Index"]): r["MissionTutorialType"] for r in tables.sections("missiontutorial")["MissionTutorialType"]}
    steps = director.script(spot)
    played = {a[1] for st in steps for a in st.get("do", ()) if a[0] == "cutscene"}
    where = str((tables.by_id("spottable").get(str(spot)) or {}).get("Map_File", "")).lower()
    mine = [r for r in rows if r["map"].lower() == where and r["slot"] in played]      # the list's place
    said = {a[2] for st in steps for a in st.get("do", ()) if a[0] == "say"}
    started = {a[1] for st in steps for a in st.get("do", ()) if a[0] == "tutorial"}
    for r in mine:
        assert not said & set(r["help"]), (r["name"], sorted(said & set(r["help"])))
        assert not started & {names.get(t) for t in r["tutorials"]}, (r["name"], r["tutorials"])


def _cutscene_rows():
    import json
    return json.loads((pathlib.Path(director.__file__).parents[2] / "planning" / "scripts" / "cutscenes.json")
                      .read_text(encoding="utf-8"))


def _scenes_played():
    """(spot, step, action index, slot) of every cutscene a table plays."""
    return [pytest.param(spot, i, k, a[1], id=f"{spot}-step{i}-slot{a[1]}") for spot in TABLES
            for i, st in enumerate(director.script(spot)) for k, a in enumerate(st.get("do", ())) if a[0] == "cutscene"]


@pytest.mark.parametrize("spot, i, k, slot", _scenes_played())
def test_a_scene_a_table_plays_has_in_the_room_every_troop_its_actor_tracks_bind(spot, i, k, slot):
    # An ACTOR track (tools/recon/cutscenes.py "actors": m_nTroopID, m_nUnitIndex) binds a troop of the room when the
    # scene is played (TrackActor 0x140942bc0: the troop by uid from the TroopManager, 0x140c02780; -10 is the hero).
    # The client starts the scene only once every track has loaded (TrackRoot 0x140947640 over
    # TrackActorBase::IsCompleteLoad 0x140941f70, polled by 0x1408b3360). A troop the room lacks is never bound, so
    # the scene waits at black for ever: 0x1408ac020 fades out and calls ShowLoadingWait (live 2026-09-30 15:25,
    # Grey Rock's 11_Kobold without the troll's force F20080). The played number is the scene's slot in the map's
    # .csset list ("slot"), not the number its name starts with: Grey Rock's 13 is 13_EndScene, and 13_StartCut is
    # not in the list. The room counted here is the room's start plus what the step brings in before the scene: its
    # "wake" / "spawn" actions listed first, and a "wake" step's own force. A troop that fell still binds: it stays
    # in the client until a 0x50cc leave (game.respawn_zone_troop). The scenes' SCRIPT commands skip a missing troop
    # (Troop_SetTroopPosition 0x140b68870, Troop_SetTroopDirectionToTroop 0x140b68a00), so they never hold a scene
    from kuf2 import tables
    where = str((tables.by_id("spottable").get(str(spot)) or {}).get("Map_File", "")).lower()
    rows = [r for r in _cutscene_rows() if r["map"].lower() == where and r["slot"] == slot]
    assert len(rows) == 1, (where, slot, [r["name"] for r in rows])       # a file of the map's list
    row = rows[0]
    s = mission_room(spot)
    st = director.script(spot)[i]
    if st["on"] == "wake":
        director.run(s, ("wake", st["force"]))
    need = st.get("needs")                                 # a prompt or cond step plays after the step it needs:
    while need is not None:                                # that step's troops are in (Grey Rock's F at 10079)
        before = next(x for x in director.script(spot) if x.get("id") == need)
        for a in before.get("do", ()):
            if a[0] in ("wake", "spawn"):
                director.run(s, a)
        need = before.get("needs")
    for a in st["do"][:k]:
        if a[0] in ("wake", "spawn"):
            director.run(s, a)
    here = set(s.data["zone_troops"]) | {0, -10}           # 0: the hero's uid; -10: the hero (0x1408b0e90)
    assert [t for t, _, _ in row["actors"] if t not in here] == []



def test_a_troops_bar_names_its_troop_for_the_client_to_follow():
    # ActGuiAddTroopsBarToMissionSituation 0xc8b4 (0x140b38f70): team, group, text, ref(kind, id), a6 -> 0x140b2e700
    # kind 0 -> HUDQuestInfo 0x140776540 (the group is dropped), 0x14077a460 sums the troop's hp itself and keeps a6;
    # UpdateTroopBar 0x140779f40 takes a6 as the troop whose portrait the bar shows (a6 > 0) and as the bar's key.
    # Lunawing Sortie I's "Lunawing Shield" (8570) over the airship 10000 (the original part 3 2:30-4:50)
    s = mission_room(10361)
    del s.sent[:]
    director.run(s, ("troops bar", 8570, 10000))
    bars = [list(struct.unpack_from("<7I", bytes(w.buf))) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_SITUATION_TROOPS_BAR]
    assert bars == [[game.ACT_SITUATION_TROOPS_BAR, game.ALL_TEAMS, 0, 8570, 0, 10000, 10000]]
    del s.sent[:]
    director.run(s, ("troops bar", 8570, 65000))     # no such troop in the room: nothing (an empty bar would stay)
    assert not s.sent


def test_a_force_bar_names_the_force_and_waits_for_every_troop_of_it_to_be_bound():
    # 0xc8b4 ref kind 2 is HUDQuestInfo::SetForceTroopBarToMissionSituation (0x140b2e700 -> 0x140c54020, its assert
    # names it): the force's Player (owner id = the zone ForceNum, game.np_owner) found by 0x140b42f20, the troops it
    # holds then summed into one bar (0x14077a460, which drops a second bar of a text already shown). The Archer camp's
    # "Your Infantry Troop" (30070) over the allied infantry F12000 (the original part 4 28:37.6-29:40)
    s = mission_room(10345)
    game.spawn_force(s, 12000)
    infantry = sorted(u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 12000)
    s.data["bound"] = {0, *infantry[:-1]}                # a client that binds: the last one not yet
    del s.sent[:]
    director.run(s, ("force bar", 30070, 12000))
    assert not [x for x in shown(s) if x[0] == "bar"]
    game.troop_bound(s, infantry[-1])
    assert [x for x in shown(s) if x[0] == "bar"] == [("bar", 30070, game.TROOPS_BAR_FORCE, 12000, infantry[0])]
    game.troop_bound(s, infantry[-1])                    # bound again: no second bar
    assert len([x for x in shown(s) if x[0] == "bar"]) == 1
    del s.sent[:]
    director.run(s, ("force bar", 30070, 31337))         # no troop of that force in the room: nothing
    assert not s.sent


def test_a_banner_is_the_centred_notice_and_a_notice_the_left_one():
    # ActGuiShowNoticeWindow 0xc8f0's first value is a NoticeTable row; its Notice_Type picks the swf
    # (0x140dc42b0: MISSION_EVENT_OPEN_MID, enum 5, "../Notice/NoticeWarSituation_default"; OPEN_LEFT 6
    # "..._misson_left"): row 6 MISSION_EVENT_OPEN_MID (Notice_System.png) for Flamegrass's "Select either the Ice or
    # Fire Troop." banner at the top (the original part 4 35:36), row 10003 OPEN_LEFT for the left panel
    s = mission_room(10303)
    del s.sent[:]
    director.run(s, ("banner", 21063, 21064))
    director.run(s, ("notice", 21204, 21207))
    assert shown(s) == [("notice", director.NOTICE_MID, (21063, 21064)), ("notice", director.NOTICE_LEFT, (21204, 21207))]
    from kuf2 import tables
    types = {int(r["Id"]): r["Notice_Type"] for r in tables.load("noticetable")}
    assert types[director.NOTICE_MID] == "MISSION_EVENT_OPEN_MID" and types[director.NOTICE_LEFT] == "MISSION_EVENT_OPEN_LEFT"


def test_a_table_that_sends_its_panel_later_starts_without_it(monkeypatch):
    # ("panel start",): the original shows the panel only as the HUD comes back after its opening camera (the Archer
    # camp part 4 25:32.9, Flamegrass 34:37.9): such a table's panel goes with that step, not at the room's start
    assert director.panel_later(10345) and director.panel_later(10303) and not director.panel_later(10233)
    s = mission_room(10233)
    assert [x for x in shown(s) if x[0] == "title"] == [("title", 100)]          # Tower: at the start
    s = mission_room(10345)
    assert not [x for x in shown(s) if x[0] in ("title", "group", "panel")]
    run_pending(s)
    seen = shown(s)
    assert seen.index(("line", 20001)) < seen.index(("title", 30000)) < seen.index(("panel", 30090)) <         seen.index(("line", 20002))


def test_a_gauge_follows_its_troops_hp_in_the_panel():
    # ActGuiAddGageObjectiveToMissionSituation 0xc81e (team, group, text, value, max): New Hampton's wall bar at its
    # hp %, sent again only when the whole percent changes
    s = mission_room(10235)
    del s.sent[:]
    director.run(s, ("gauge", 400, 401, 23504))
    top = s.data["battle"].troops[23504]["max"]
    for hp in (top * 0.5, top * 0.502, top * 0.2):
        director.on_hp(s, 23504, hp, top)
    bars = [list(struct.unpack_from("<6I", bytes(w.buf))) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_SITUATION_GAUGE]
    assert [b[4] for b in bars] == [100, 50, 20] and bars[0][1:4] == [game.ALL_TEAMS, 400, 401]



def test_thompson_restores_the_players_troop_in_the_sorcerers_scene():
    # Grey Rock: Thompson's 1010 and the player's troop 10073's living units back to full (0x505d), a line of the inner
    # castle's scene on the tape (part 2 37:45, the troop at ~64 %: test_scenes_10234), no longer an hp threshold
    s = mission_room(10234)
    run_pending(s)
    t = s.data["battle"].troops[10073]
    top = sum(t["units"])
    for i in range(len(t["units"]) - 1):
        t["units"][i] = 1
    del s.sent[:]
    b = director.bound(10234, 10230)
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)][-1] == 1010
    assert sum(t["units"]) > top * 0.9 and any(w.proto == game.S2C_TROOP_HP for w in s.sent)



def test_new_hampton_reveals_and_completes_its_objectives_in_turn():
    # the panel holds only "Enter New Hampton Castle", the failure line and the lesson "Use Trebuchet skill" as the
    # opening scene ends (the footage from 25:51.50; under its title, sent at the start); the breach's end completes
    # 210 and adds "Reach the entrance to the town with Duran" (ActGuiCompleteObjectiveToMissionSituation 0xc828, then
    # 0xc7f6)
    s = mission_room(10235)
    run_pending(s)
    lines = [struct.unpack_from("<4I", bytes(w.buf))[3] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
             and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_SITUATION_LINE]
    assert lines == [210, 310, 430]
    del s.sent[:]
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20100), "test") if any(
        w[0]["ForceNum"] == 20100 for w in s.data["waves"]) else director.run(s, ("wake", 20100))
    for u in [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 20100 and game.hostile(t)]:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    acts = [struct.unpack_from("<%dI" % (len(bytes(w.buf)) // 4), bytes(w.buf)) for w in s.sent
            if w.proto == game.S2C_SCRIPT_ACTION]
    done = [a for a in acts if a[0] == game.ACT_SITUATION_DONE]
    added = [a for a in acts if a[0] == game.ACT_SITUATION_LINE]
    assert done == [(game.ACT_SITUATION_DONE, game.ALL_TEAMS, 210, 1)] and added[0][2:] == (200, 220)


def test_tower_counts_the_winged_wyrms_as_they_fall():
    # "Defeat Winged Wyrms" with its count (ActGuiAddValueObjectiveToMissionSituation 0xc800 kind 0): 0/3 with the
    # F2 lesson's key, 1/3 when the first wyrm falls
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 30000))
    run_pending(s)
    del s.sent[:]
    director.fire(s, next(i for i, st in enumerate(director.script(10233)) if st.get("id") == "wyrms"))   # the scene's end
    obey(s)                                      # the count comes with the F2 lesson's key (tape 12:06)
    game.mission_troop_down(s, NoSave(), 30001)
    counts =[struct.unpack_from("<7I", bytes(w.buf))[2:6] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
              and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_SITUATION_VALUE]
    assert counts == [(180, 190, 0, 3), (180, 190, 1, 3)]


def test_tower_glen_leads_the_party_to_the_report_and_the_scene_plays_on_arrival():
    # the video harness (captures/harness/10233_report.md, part 2): after Glen's 1160 "Everyone, regroup!" and 1170
    # "Time to move!", the allied mark goes from (62451, 73844) at 10:00 to (58228, 77730) at 10:13, toward 18031
    # '상황보고', and 4_JoinTheMainForces starts as the hero enters it (10:13.5 -> 10:15). Ours played the scene on a
    # 3 s timer after the ring fell, with no march (owner: "the part where we have to follow glen")
    steps = director.script(10233)
    regroup = next(st for st in steps if st.get("id") == "regroup")
    report = next(st for st in steps if st.get("id") == "report")
    assert ("march", "글렌_1", 18031) in regroup["do"] and ("march", 11000, 18031) in regroup["do"]
    assert report["on"] == "bound" and report["bound"] == 18031 and report.get("needs") == "regroup"
    assert ("cutscene", 4, 21) in report["do"]
    # then the tape (10:38-11:04): "Join the Main Forces: Follow Glen." right after the scene, Glen walks to the wyrms'
    # clearing with the hero behind him while 1210-1250 play; ours made Glen's force escort the hero. Glen goes
    # alone under his marker (frames 10:36-10:46: one figure ahead under the blue pillar); his column comes from
    # behind the hero (10:48-11:04) to its own places, not ahead with him (tools/harness/tracks.py, the brief's
    # finding 3; test_scenes_10233)
    follow = next(st for st in steps if st["on"] == "after" and st.get("step") == "report")
    assert follow["s"] == 0 and ("notice", 8180, 8190) in follow["do"]
    assert ("march", "글렌_1", "가두기_윙드웜") in follow["do"] and ("highlight troop", "글렌_1") in follow["do"]
    assert not [a for a in follow["do"] if a[0] == "march" and a[1] == 11000]
    assert not any(a[0] == "escort" for st in steps for a in st.get("do", ()) if "글렌_1" in a[1:])
    assert ("say", "톰슨_1", 1210) in follow["do"]           # the tape shows Thompson over the box (harness report)


def test_tower_finds_the_tower_on_the_hilltop_where_its_cutscene_stages_the_party():
    # live 2026-09-29, two runs (23:12:58, 23:53:09): the hero reached the hilltop (55-57 k, 117 k) and could go no
    # further while step 'tower' waited on 문라이트_에리어이동 (10500), behind the camp's red curtains (10012-10014,
    # opened only after this scene; the original's 10_Defense_Camp teleports the hero into 10500 later). 8_TowerFound
    # stages the party on that hilltop (the hero at (58719, 117271) at 3.7 s): its trigger is the area there, 10100,
    # and the column marches to it
    steps = director.script(10233)
    tower = next(st for st in steps if st.get("id") == "tower")
    up = next(st for st in steps if st.get("id") == "uphill")
    b = director.bound(10233, tower["bound"])
    assert game.inside_bound(b, 56766, 117605)              # where the hero stood in both runs
    assert math.hypot(58719 - b["BoundCenterX"], 117271 - b["BoundCenterZ"]) <= b["BoundRadius"]   # the staging
    assert not game.inside_bound(director.bound(10233, 10500), 56766, 117605)
    assert {a[2] for a in up["do"] if a[0] == "march"} == {tower["bound"]}


def test_tower_marks_the_scouts_path_one_area_at_a_time():
    # live 2026-09-29 23:47:13: Thompson's 1040 "Let me mark your path on the Map" and notice 8030 "Move to the
    # highlighted area" came with no mark (owner: "when he say that he will mark a point in the map, he dodn't mark
    # it"); the tape (part 2, 6:34-7:42) shows a highlighted area ahead that moves on along the path: the client's
    # ActGuiSetHighlightArea (0xc7b0: area, seconds, on), never sent before. Each place reached clears its mark and
    # marks the next
    s = mission_room(10233)
    obey = [st for st in director.script(10233) if st.get("id") == "scouts"][0]
    assert ("highlight", 18020) in obey["do"]
    marks = lambda: [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]
    director.run(s, ("highlight", 18020))
    assert marks() == [(18020, 1)]
    steps = director.script(10233)
    for area, nxt in ((18020, 18021), (18021, 18022)):
        st = next(st for st in steps if st["on"] == "bound" and st.get("bound") == area and "troop" not in st)
        assert ("highlight", area, 0) in st["do"] and ("highlight", nxt) in st["do"]
    # the third mark is 18022 (the minimap ring 7:41.75 1.1 px from its point, 18023's 3.9 px; harness report
    # "Highlights"), taken down as the hero reaches it; the tape marks no area up the hill: the pillar there (13:07-
    # 13:39) is the blue troop marker on Glen (ActGuiSetHighlightTroop), not an area's (no MINE ring or pillar)
    last = next(st for st in steps if st["on"] == "bound" and st.get("bound") == 18022)
    assert ("highlight", 18022, 0) in last["do"]
    assert not [a for st in steps for a in st.get("do", ()) if a[0] == "highlight" and a[1] in (18023, 10100)]
    up = next(st for st in steps if st.get("id") == "uphill")
    tower = next(st for st in steps if st.get("id") == "tower")
    assert ("highlight troop", "글렌_1") in up["do"] and ("highlight troop", "글렌_1", 0) in tower["do"]


def test_a_troop_highlight_puts_the_clients_marker_on_it_and_takes_it_down():
    # ActGuiSetHighlightTroop 0xc7ba (troop, seconds, on, leader: 0x140b36aa0 reads them in that order and passes
    # them to 0x140b2e8d0; on 1 -> 0x140b5cb30 -> the HUD's highlight entry, seconds <= 0 kept until taken down; on 0 ->
    # 0x140b5cb50): the tape's blue pillar and glow on Glen (part 2, 9:21, 10:38-11:07 "Follow Glen.", 13:07-13:39 up
    # the hill; harness report "Effects", ALLIANCE marker). A troop not in the room gets nothing
    s = mission_room(10233)
    run_pending(s)
    del s.sent[:]
    director.run(s, ("highlight troop", "글렌_1"))
    director.run(s, ("highlight troop", "글렌_1", 1, 2))
    director.run(s, ("highlight troop", 10000, 0))
    director.run(s, ("highlight troop", "nobody"))
    director.run(s, ("highlight troop", 30000))        # the wyrms: not in the room yet
    lead = director.HIGHLIGHT_LEADER
    assert acts(s, director.ACT_HIGHLIGHT_TROOP) == [[0xc7ba, 10000, 0, 1, lead], [0xc7ba, 10000, 2, 1, lead],
                                                     [0xc7ba, 10000, 0, 0, lead]]


def test_a_march_is_ordered_at_the_run_mode():
    # ActTroopMoveToArea's last field, the order's mode (+0x1c), is a WALK flag: TroopCommand::Move's 0x14094b120
    # copies 0 / 1 (2: the troop's own +0x910) into the move task's +0x2c, BehaviorTroopSV_MovePosition's enter
    # (0x140579560) sets the troop's walk flag +0x910 from it, and BehaviorTroopMove::UpdateWalkMode (0x1407145c0)
    # moves a flagged troop at its walk speed (+0xcf0), else at its run speed (stat 14 MAX_MOVE_SPEED). The client's
    # own RTS.Troop_RunToArea sends 0 (0x140ba0520), Troop_WalkToArea sets the flag and sends 2 (0x140ba03d0). Live
    # 2026-09-30 14:51:55-14:52:42: Glen on 1 walked at 180 units/s, his troop type 1091's MAX_WALK_SPEED
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("march", "글렌_1", 18031))
    [a] = acts(s, director.ACT_MOVE_TO_AREA)
    assert a == [director.ACT_MOVE_TO_AREA, 0, 10000, 18031, director.MOVE_CENTRE, 1, 0, 0]
    assert director.MOVE_MODE == director.MOVE_RUN == 0 and director.MOVE_WALK == 1


def test_tower_glen_enters_from_his_entry_and_speaks_when_his_force_joins_the_fight():
    # live 2026-09-29 (session 225444): at the captain's fall Glen's force marched from the start camp to 글렌 진입
    # (34 k), came in sight 2 min 13 s later (his gauge 23:01:01), after the ring had fallen to the scouts (18) and the
    # hero (2), and "General Glen is here!" played on a 30 s timer (22:59:34) while he was far off. The tape (part 2):
    # his force joins the fight ~24 s after the notice (8:56 -> 9:20), the march from 글렌 진입 (7.9 k); his lines as
    # it arrives. Triggers: the captain's fall places and sends the force; its engaging the ring says the lines
    from kuf2 import obf
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 20010))
    run_pending(s)
    del s.sent[:]
    game.mission_troop_down(s, NoSave(), 20014)
    run_pending(s)
    entry = director.bound(10233, 18030)
    placed = {}
    for w in s.sent:
        if w.proto == game.S2C_TROOP_BACK:
            b = bytes(w.buf)
            placed[struct.unpack_from("<H", b, 7)[0]] = obf.dec_pos_xz(b[:4], b[6])
    force = [10000, 11000, 11001, 11002, 11003, 11004, 11005]
    assert set(force) <= set(placed)
    assert all(math.hypot(x - entry["BoundCenterX"], z - entry["BoundCenterZ"]) < 2500 for x, z in placed.values())
    sent_to = {a[2]: a[3] for a in acts(s, director.ACT_MOVE_TO_AREA)}
    assert all(sent_to.get(u) == 18023 for u in force)
    assert not {1140, 1150} & {line for _, _, line in lines_shown(s)}
    director.on_engage(s, 10100, 20103)                  # the scouts' fight: not Glen's arrival
    run_pending(s)
    assert not {1140, 1150} & {line for _, _, line in lines_shown(s)}
    director.on_engage(s, 11001, 20105)                  # his infantry reaches the ring
    run_pending(s)
    assert [line for _, _, line in lines_shown(s) if line in (1140, 1150)] == [1140, 1150]


def test_tower_closes_the_action_mode_lesson_after_tab():
    # live 2026-09-29: 12_Ruins_Tab's lesson (13305) completed on the client at 22:58:09.353 and its card stayed up
    # 4 min 25 s, still asking for Tab, until the next lesson replaced it (HideMissionTutorial 23:02:34.164); the
    # original's card went within 2 s of the Tab (tape part 2, 8:18 -> 8:20). The server closes it on its trigger, the
    # Tab itself (a key prompt), not on a timer
    steps = director.script(10233)
    lesson = next(st for st in steps if ("cutscene", 12, 2) in st.get("do", ()))
    tab = next(st for st in steps if st["on"] == "prompt" and director.KEY_CHANGE_CONTROL_MODE in st["keys"])
    assert tab["needs"] == lesson["id"] and ("finish",) in tab["do"]


def test_tower_opens_the_uphill_wall_before_the_column_marches():
    # live 2026-09-29 23:03:32: the wyrms down, the column's eight ActTroopMoveToArea went out while the invisible wall
    # 10015 (type 232) still stood on the uphill path; the client found no way and the column stood (Glen 37 k short
    # of the tower area 2.5 min later). The wall comes down first, then the orders
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 30000))
    run_pending(s)
    del s.sent[:]
    for u in (30000, 30001, 30002):
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    kinds = [("wall" if w.proto == game.S2C_PROP_LIST else "march") for w in s.sent
             if w.proto == game.S2C_PROP_LIST or (w.proto == game.S2C_SCRIPT_ACTION and struct.unpack_from(
                 "<I", bytes(w.buf))[0] == director.ACT_MOVE_TO_AREA)]
    assert 10015 not in s.data["barriers"]
    assert kinds[0] == "wall" and "march" in kinds


def test_steps_waiting_on_a_step_fire_after_it_in_the_tables_order(monkeypatch):
    # "needs": the places reached ahead of the story are remembered and told once the step they need has played
    steps = ({"on": "start", "id": "a", "do": []},
             {"on": "bound", "bound": 18021, "needs": "b", "do": [("say", None, 1060)]},
             {"on": "bound", "bound": 18020, "needs": "b", "do": [("say", None, 1050)]},
             {"on": "after", "step": "a", "s": 5, "id": "b", "do": [("say", None, 1040)]})
    monkeypatch.setattr(director, "script", lambda spot: steps)
    s = mission_room(10233)
    walk(s, 67095, 70662)
    walk(s, 61351, 75388)
    assert lines_shown(s) == []
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)] == [1040, 1060, 1050]


def client_answer(serial, holds, key=0, tag=0):
    """C2S 0x5089 as the client's ReturnCondition (0x140b2f0b0) writes it: X, the query's tag, Y, from the serial with
    the answer in bit 31 and the query's key, mixed by 0x1c6f034d (planning/client/mission_script.md §4)."""
    m, s = 0x1c6f034d, serial | (0x80000000 if holds else 0)
    a, y = (s & ~m) | (key & m), (key & ~m) | (s & m)
    return struct.pack("<IBI", (y ^ a) & 0xFFFFFFFF, tag, y & 0xFFFFFFFF)


def queries(s):
    """(serial, condition, its arguments) of every S2C 0x5086 sent: u32 condition, u32 serial, u8 tag, u32 key, args."""
    return [(struct.unpack_from("<I", bytes(w.buf), 4)[0], struct.unpack_from("<I", bytes(w.buf))[0], bytes(w.buf)[13:])
            for w in s.sent if w.proto == game.S2C_CONDITION]


def prompts(s):
    """{prompt id: key} of the key prompts S2C 0x50c1 (u32 key, u8 id, u32 value) put up and not taken down (0x50c3)."""
    up = {}
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_KEY_PROMPT:
            key, pid, _ = struct.unpack("<IBI", b)
            up[pid] = key
        elif w.proto == game.S2C_KEY_PROMPT_OFF:
            up = {} if b[0] == 0 else {p: k for p, k in up.items() if p != b[0]}      # id 0 empties the list
    return up


def answer(s, serial, holds):
    game.make(NoSave(), 0).handlers[game.C2S_CONDITION](s, pkt(game.C2S_CONDITION, client_answer(serial, holds)))


def press(s, key):
    """The player presses a key: the client answers each prompt up for it (C2S 0x50c2, u8 prompt id)."""
    for pid, k in list(prompts(s).items()):
        if k == key and pid not in getattr(s, "pressed", set()):
            s.pressed = getattr(s, "pressed", set()) | {pid}
            game.make(NoSave(), 0).handlers[game.C2S_KEY_PROMPT](s, pkt(game.C2S_KEY_PROMPT, bytes([pid])))


def obey(s, rounds=60):
    """The player does what the lessons ask, at once: the client answers every condition asked true and the player
    presses every key prompted, until the room asks nothing more (the scene tests play the lessons with it)."""
    for _ in range(rounds):
        run_pending(s)
        answered = getattr(s, "answered", set())
        asked = [serial for serial, _, _ in queries(s) if serial not in answered]
        keys = [k for pid, k in prompts(s).items() if k and pid not in getattr(s, "pressed", set())]
        if not asked and not keys:
            return
        s.answered = answered | set(asked)
        for serial in asked:
            answer(s, serial, True)
        for k in keys:
            press(s, k)


def test_a_condition_answer_is_read_through_the_clients_mix():
    # ReturnCondition 0x140b2f0b0: the answer rides in bit 31 of the echoed serial, mixed with the query's key; the
    # script console's form (header 0x140b2ce10, 13 bytes and more) is no answer
    for serial, holds, key, tag in ((1, True, 0, 0), (7, False, 0x12345678, 9), (0x7FFFFFFF, True, 0xFFFFFFFF, 255)):
        assert game.condition_answer(client_answer(serial, holds, key, tag)) == (serial, holds)
    assert game.condition_answer(struct.pack("<IBIII", 0, 0, 0xFFFFFFFF, 0x15FD6, 3)) is None


def test_a_cond_step_asks_the_client_until_it_holds(monkeypatch):
    # "cond": S2C 0x5086 (condition, serial, u8 tag, key, its arguments) once the step it needs has fired, again
    # POLL_S after each false answer; the answer that holds (C2S 0x5089) fires it, a stale one does nothing
    steps = ({"on": "start", "id": "a", "do": []},
             {"on": "cond", "cond": (director.COND_TUTORIAL_PAST, "133_SelectHero", 1), "needs": "a", "id": "b",
              "do": [("say", None, 1040)]})
    monkeypatch.setattr(director, "script", lambda spot: steps)
    s = mission_room(10233)
    [(first, cond, args)] = queries(s)
    body = bytes(next(w.buf for w in s.sent if w.proto == game.S2C_CONDITION))
    assert cond == director.COND_TUTORIAL_PAST and args == b"133_SelectHero\0" + struct.pack("<i", 1)
    assert body[8:13] == bytes(5)                       # tag 0 and key 0: only echoed
    answer(s, first, False)
    assert lines_shown(s) == [] and [d for d, _ in s.pending] == [director.POLL_S]
    run_pending(s)
    [second] = [serial for serial, _, _ in queries(s) if serial != first]
    answer(s, first, True)                              # already answered: nothing
    assert lines_shown(s) == []
    answer(s, second, True)
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)] == [1040] and len(queries(s)) == 2


def test_a_prompt_step_waits_for_its_key(monkeypatch):
    # "prompt": a key prompt S2C 0x50c1 per key once the step it needs has fired, after the client's list is emptied
    # (0x50c3 id 0) and one keyless prompt that stops its 30 s timeout (never checked, 0x140b25a40); the prompt the
    # player's key answers (C2S 0x50c2) fires its step and the step's other prompts come down (S2C 0x50c3)
    steps = ({"on": "start", "id": "a", "do": []},
             {"on": "prompt", "keys": (director.KEY_SELECT_TROOP3, director.KEY_CAMERA_ROTATED), "needs": "a",
              "do": [("complete",)]},
             {"on": "prompt", "keys": (director.KEY_AI_HERO_SUPPORT,), "needs": "a", "do": [("finish",)]})
    monkeypatch.setattr(director, "script", lambda spot: steps)
    s = mission_room(10233)
    put = [struct.unpack("<IBI", bytes(w.buf)) for w in s.sent if w.proto == game.S2C_KEY_PROMPT]
    first = next(n for n, w in enumerate(s.sent) if w.proto in (game.S2C_KEY_PROMPT, game.S2C_KEY_PROMPT_OFF))
    assert s.sent[first].proto == game.S2C_KEY_PROMPT_OFF and bytes(s.sent[first].buf) == b"\0"
    assert put[0] == (0, director.NO_KEY_PROMPT, 0) and [p[0] for p in put[1:]] == [0x36, 0x77, 0x3a]
    assert len({p[1] for p in put}) == 4 and all(0 < p[1] < 0x80 for p in put)
    press(s, 0x35)                                      # F1: nothing prompted for it
    assert not acts(s, director.ACT_COMPLETE_TUTORIAL)
    press(s, 0x77)
    assert acts(s, director.ACT_COMPLETE_TUTORIAL) == [[director.ACT_COMPLETE_TUTORIAL]]
    assert set(prompts(s).values()) == {0, 0x77, 0x3a}  # F2's prompt came down (0x77's the client dropped itself)
    game.make(NoSave(), 0).handlers[game.C2S_KEY_PROMPT](s, pkt(game.C2S_KEY_PROMPT, bytes([put[1][1]])))
    assert len(acts(s, director.ACT_COMPLETE_TUTORIAL)) == 1 and not acts(s, director.ACT_FINISH_TUTORIAL)
    press(s, 0x3a)
    assert acts(s, director.ACT_FINISH_TUTORIAL) == [[director.ACT_FINISH_TUTORIAL]]


def test_troops_spawned_one_by_one_leave_the_rest_of_their_group_held_with_its_allies():
    # director "spawn" (game.spawn_troops): the Archer camp takes F20009's troops out of their held group in turn;
    # the group, named by its first troop, keeps the allies that come with it until its last troop is out
    s = mission_room(10345)
    run_pending(s)
    ids = lambda: [[t["TroopID"] for t in w] for w in s.data["waves"] if w[0].get("ForceNum") == 20009]
    assert ids() == [[10123, 10135]]                    # the start took the melee's three (10117 is the zone's)
    allies = {t["TroopID"] for t in s.data["wave_allies"][10123]}
    assert {10149, 10150} <= allies
    assert game.spawn_troops(s, (10123,)) == 1
    assert ids() == [[10135]] and {t["TroopID"] for t in s.data["wave_allies"][10135]} == allies
    assert game.spawn_troops(s, (10135, 10135)) == 1
    assert ids() == [] and 10135 in s.data["zone_troops"] and not {10149, 10150} & set(s.data["zone_troops"])


def test_an_hp_step_by_a_troop_waits_for_that_troops_hit_or_the_fall():
    # {"on": "hp", ..., "by": who}: the Archer camp's "Attack the highlighted enemy Troop from a distance" is the
    # player's archer's hit (combat.apply_hits names the attacker), not the allied infantry's beside it
    s = mission_room(10345)
    run_pending(s)
    top = s.data["battle"].troops[10117]["max"]
    director.on_hp(s, 10117, top // 2, top, 10121)
    director.on_hp(s, 10117, top // 2, top)
    run_pending(s)
    assert 10123 not in s.data["zone_troops"]
    director.on_hp(s, 10117, top // 3, top, 10087)
    run_pending(s)
    assert 10123 in s.data["zone_troops"]

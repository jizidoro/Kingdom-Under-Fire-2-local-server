"""Lunawing Sortie II 10362: the director's table (kuf2/scenes/m10362.py), and how it is reached: Sortie I's win goes
on into it through warp 622 (m10361 NEXT; world.continue_mission), its own win ends at the crash site 10351."""
import json
import pathlib
import struct

import pytest

from kuf2 import director, game, obf, quest, world
from test_battle import mission_room, walk
from test_director import lines_shown, run_pending

ROOT = pathlib.Path(__file__).resolve().parents[2]
JADE, JAGER, GLEN, THOMPSON, GOLDEN_HAMMER = 10110, 10111, 10112, 10113, 10109     # force 10100, from the start
LUNAWING = 10000
PATH_X = 59000                   # the airship's way north, along the zone's numbered bounds (x 56-59k)
BEFORE_CANNONS = 84000           # z: no head cannon of force 21000 within the wake range yet
IN_CANNONS = 92000               # z: inside force 21000's field (the bound 10003, 91910)


def actions(s):
    return [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]


def cutscenes(s):
    return [struct.unpack_from("<3I", b)[1:] for b in actions(s)
            if struct.unpack_from("<I", b)[0] == director.ACT_CUTSCENE]


def fly(s, z_to, z_from=68000):
    for z in range(z_from, z_to + 1, 2000):
        walk(s, PATH_X, z)


def test_the_airship_is_immune_and_followed_before_jade_and_jager_open():
    # the tape 6:00 / 6:06; the guide: "Your Immune to all dmg regardless of what you do"; camera 30003 as Sortie I
    s = mission_room(10362)
    assert s.data["plan"]["hand"] == (LUNAWING,) and s.data["battle"].troops[LUNAWING].get("untouchable")
    acts = actions(s)
    camera = struct.pack("<II", director.ACT_CAMERA_SET, 30003)
    first_line = next(i for i, b in enumerate(acts) if struct.unpack_from("<I", b)[0] == director.ACT_HELP_TEXT_BY_TROOP)
    assert camera in acts and acts.index(camera) < first_line
    run_pending(s)
    assert lines_shown(s) == [(JADE, 0, 6100), (JAGER, 0, 6110)]
    assert not s.data.get("mission_won")


def test_the_barrage_comes_with_the_head_cannons_and_not_before():
    s = mission_room(10362)
    run_pending(s)
    fly(s, BEFORE_CANNONS)
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)] == [6100, 6110]
    assert 21000 not in {t["ForceNum"] for t in s.data["zone_troops"].values()}
    fly(s, IN_CANNONS, BEFORE_CANNONS)
    assert 21000 in {t["ForceNum"] for t in s.data["zone_troops"].values()}
    fly(s, IN_CANNONS, BEFORE_CANNONS)                             # once
    run_pending(s)
    assert lines_shown(s)[2:5] == [(THOMPSON, 0, 6150), (GLEN, 0, 6160), (GOLDEN_HAMMER, 0, 6180)]
    assert [line for _, _, line in lines_shown(s)].count(6150) == 1


def test_the_barrage_lines_keep_the_tapes_spacing_and_the_fall_comes_13_s_after():
    # the tape: 6150 at 6:18, 6160 at 6:24, 6180 at 6:30, the fall cutscene at 6:46 (28 s after the barrage begins)
    st = director.script(10362)
    barrage = next(x for x in st if x.get("id") == "barrage")
    says = [a for a in barrage["do"] if a[0] == "say"]
    assert [a[2] for a in says] == [6150, 6160, 6180]
    texts = director.lines(10362)
    lengths = [a[3] if len(a) > 3 else director.line_seconds(texts[a[2]]) for a in says]
    fall = next(x for x in st if x["on"] == "after" and x["step"] == "barrage")
    assert sum(lengths) + fall["s"] == (6 * 60 + 46) - (6 * 60 + 18)
    assert fall["do"] == [("win",)]


def test_the_shield_gives_out_the_room_is_won_and_its_ending_is_the_fall_then_the_crash():
    s = mission_room(10362)
    run_pending(s)
    fly(s, IN_CANNONS)
    run_pending(s)
    assert s.data.get("mission_won")
    assert cutscenes(s) == [(0, 0), (11, 0)]                       # 0_Lunarwing_fall, then 11_Lunawing_Crash
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 0      # no window (no grade, no reward row)
    assert sum(w.proto == game.S2C_MISSION_LEAVE for w in s.sent) == 1
    leave = next(w for w in s.sent if w.proto == game.S2C_MISSION_LEAVE)
    acts = [w for w in s.sent if w.proto in (game.S2C_SCRIPT_ACTION, game.S2C_MISSION_LEAVE)]
    last_cut = max(i for i, w in enumerate(acts) if w.proto == game.S2C_SCRIPT_ACTION
                   and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_CUTSCENE)
    assert acts.index(leave) > last_cut                           # the room is left after the crash scene


def test_the_ending_waits_for_both_cutscenes_whole():
    won = next(x for x in director.script(10362) if x["on"] == "won")
    rows = {r["name"]: r for r in json.loads((ROOT / "planning" / "scripts" / "cutscenes.json").read_text(
        encoding="utf-8")) if r["map"] == "1_NewHamptonHighway"}
    fall, crash = rows["0_Lunarwing_fall"], rows["11_Lunawing_Crash"]
    assert won["do"] == [("cutscene", fall["slot"], 88), ("cutscene", crash["slot"], 92)]   # the .csset positions
    last = lambda r: max(t for t, _, _ in r["script"])
    assert 88 * 1000 >= last(fall) and 92 * 1000 >= last(crash)
    assert fall["actors"] == [] and [a[2] for a in crash["actors"]] == ["Hero"]   # the cast: the hero, always here


def test_felling_every_hostile_troop_does_not_end_the_room_before_its_story():
    # WIN = "table": the 16 HUD-hidden primitives of force 20000 are no win target (DESIGNER-NOTES F8)
    s = mission_room(10362)
    run_pending(s)
    for uid in [u for u, t in s.data["zone_troops"].items() if t["ForceNum"] == 20000]:
        game.mission_troop_down(s, s.state, uid)
    assert not s.data.get("mission_won") and not any(w.proto == game.S2C_MISSION_LEAVE for w in s.sent)


def test_nothing_reaches_10362_but_sortie_ones_next_warp():
    # warpinfo 622 (MISSION, 10362 group 1) is the only way in, and only Sortie I's table names it
    from kuf2 import tables
    warps = [r for r in tables.load("warpinfo") if r["SpotID"] == "10362"]
    assert [(r["ID"], r["WARP_POSITION"], r["SPGroupID"]) for r in warps] == [("622", "MISSION", "1")]
    assert not any(r.get("QuestAccept_Action_Value") == "622" or r.get("QuestFinish_Action_Value") == "622"
                   for r in tables.load("questtable"))
    assert director.next_warp(10361) == 622 and director.next_warp(10362) is None
    assert world.mission_warp(10362) == 622


# Sortie I's win goes on into Sortie II: the world session sends the entry from inside the won room.

ACCT = 7


class Writer:
    def is_closing(self):
        return False


class Session:
    def __init__(self, c, **data):
        self.data = {"char": c, "account": {"id": ACCT, "characters": [c]}, **data}
        self.sent, self.pending, self.w = [], [], Writer()

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class State:
    def __init__(self):
        self.game_sessions, self.world_sessions = {}, {}

    def save(self):
        pass


def sortie_char():
    return {"id": 1, "class": 0, "level": 8, "spot": 10350, "pos": [158000, 0, 134000],
            "quests": {"active": {"1150703": {"counts": [0] * 5}}, "done": [1150702]}}


def room(st, c, spot):
    """The game session of a mission room at its start (its zone troops in), registered as the live room."""
    from kuf2 import combat
    g = Session(c, spot=spot, difficulty=0, battle=combat.Battle())
    g.state = st
    g.data["battle"].add_hero(0, 1000)
    game.spawn_zone_troops(g)
    st.game_sessions[ACCT] = g
    return g


def sent(s, proto):
    return [bytes(w.buf) for w in s.sent if w.proto == proto]


def test_the_sortie_quest_goes_from_sortie_one_into_sortie_two_and_ends_at_the_crash_site():
    st, c = State(), sortie_char()
    ws = Session(c, game_addr=("127.0.0.1", 25004), battle_spot=10350)
    st.world_sessions[ACCT] = ws
    quest.spot_warp(ws, st, 1150703)                               # Glen's accept: SpotWarp 621 -> 10361 group 1
    assert c["mission"] == {"spot": 10361, "quest": 1150703, "back": 10351}
    run_pending(ws)
    assert struct.unpack_from("<I", sent(ws, world.S2C_GAME_SERVER)[-1], 8)[0] == 10361
    ws.sent.clear()
    g = room(st, c, 10361)
    run_pending(g)
    walk(g, 191505, 272969)                                        # 목적지: Sortie I won
    assert g.data.get("mission_won")
    assert not sent(g, game.S2C_MISSION_LEAVE) and not sent(g, game.S2C_MISSION_COMPLETE)   # no window, no field
    assert c["quests"]["active"]["1150703"]["counts"][0] == 1     # its MissionLevelClear at 10361 is met
    assert c["mission"] == {"spot": 10362, "quest": 1150703, "back": 10351}
    warp = sent(ws, world.S2C_WARP_PROCESS)
    assert len(warp) == 1 and obf.dec_u32(warp[0][1:5]) == 622    # Sortie II's start group (1)
    assert len(sent(ws, world.S2C_MISSION_ESCAPE)) == 1            # out of the won room
    assert ws.data["entering"] == 10362
    run_pending(ws)
    assert struct.unpack_from("<I", sent(ws, world.S2C_GAME_SERVER)[-1], 8)[0] == 10362
    g2 = room(st, c, 10362)                                        # Sortie II
    run_pending(g2)
    fly(g2, IN_CANNONS)
    run_pending(g2)
    assert g2.data.get("mission_won")
    assert not sent(g2, game.S2C_MISSION_LEAVE)                    # the crash site is a Field of Sortie II's own map:
    into, esc = sent(ws, world.S2C_MISSION_ESCAPE)                 # a field warp naming the won room (a 0x4041 would
    assert obf.dec_u32(esc[2 + 0x17:2 + 0x1b]) == 10362            # leave the same-map flag set there:
    run_pending(ws)                                                # world.leave_for_same_map_field)
    assert struct.unpack_from("<I", sent(ws, world.S2C_GAME_SERVER)[-1], 8)[0] == 10351
    assert c["spot"] == 10351 and "mission" not in c
    from kuf2 import tables
    assert quest.done(tables.by_id("questtable")["1150703"], c["quests"]["active"]["1150703"])   # ready at Glen 6051


def test_without_a_world_session_sortie_one_still_leaves_for_the_crash_site():
    s = mission_room(10361)
    run_pending(s)
    walk(s, 191505, 272969)
    assert sum(w.proto == game.S2C_MISSION_LEAVE for w in s.sent) == 1


def won_sortie_one(world_open=True):
    st, c = State(), sortie_char()
    c["mission"] = {"spot": 10361, "quest": 1150703, "back": 10351}
    ws = Session(c, game_addr=("127.0.0.1", 25004), battle_spot=10361)
    ws.w.is_closing = lambda: not world_open
    st.world_sessions[ACCT] = ws
    g = room(st, c, 10361)
    run_pending(g)
    walk(g, 191505, 272969)
    return st, c, ws, g


def test_a_second_win_order_does_not_send_the_client_on_twice():
    st, c, ws, g = won_sortie_one()
    game.mission_won(g, st)                                        # the owner's !win on top of the destination
    assert len(sent(ws, world.S2C_MISSION_ESCAPE)) == len(sent(ws, world.S2C_WARP_PROCESS)) == 1
    assert not sent(g, game.S2C_MISSION_LEAVE)


def test_a_closing_world_session_leaves_for_the_crash_site_instead():
    st, c, ws, g = won_sortie_one(world_open=False)
    assert len(sent(g, game.S2C_MISSION_LEAVE)) == 1 and not sent(ws, world.S2C_MISSION_ESCAPE)
    assert c["spot"] == 10351 and "mission" not in c


def test_the_clients_own_entry_during_the_hand_over_is_not_a_second_one():
    from test_walk_p3 import pkt
    st, c, ws, g = won_sortie_one()
    role = world.make(st, 0, "127.0.0.1", 25004)
    role.handlers[world.C2S_ENTER_SPOT](ws, pkt(world.C2S_ENTER_SPOT, obf.u32(10362) + b"\0"))
    run_pending(ws)
    assert [struct.unpack_from("<I", b, 8)[0] for b in sent(ws, world.S2C_GAME_SERVER)] == [10362]

"""Mission results and rewards (ROADMAP C2, BATTLE-WIRING B32, UI-WIRING U26): the par-time grade (owner Q3; now the
fallback where %Mission_Grade has no row, test_loot.py), the table exp in the 0x5044 record and the reward cards
0x404c / 0x404d. Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import combat, director, game, obf, world
from kuf2.packet import Reader
from conftest import run_pending

GLEN_POOL = {101104113, 102104113, 151104113, 152104113, 153104113, 154104113, 155104113}   # 10233 Normal, categories
                                                                                         # 2041-2047, Glen's column


class Session:
    def __init__(self, c, spot=None):
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}}
        if spot is not None:                        # the game connection of a mission room
            self.data.update(spot=spot, difficulty=0, battle=combat.Battle())
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class State:
    def __init__(self):
        self.game_sessions = {}

    def save(self):
        pass


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def char(level=4, exp=0):
    return {"id": 1, "class": 0, "level": level, "exp": exp, "spot": 10354, "pos": [0, 0, 0],
            "quests": {"active": {}, "done": []}}


def press_prompts(s):
    """The player presses each key a lesson prompts (S2C 0x50c1; Tower's Z at the night attack), as the client
    answers it (director.on_prompt)."""
    for pid in list(director._state(s).get("prompts", {})):
        director.on_prompt(s, pid)


def win(s, state, seconds_ago=None):
    """Spawn the room's troops and down every hostile one, wave after wave, until the mission is won; the room started
    `seconds_ago` (None: no start recorded)."""
    s.state = state                                     # a table's ("win",) step wins with it (Tower's cannons)
    game.spawn_zone_troops(s)
    if seconds_ago is not None:
        s.data["started_at"] = time.monotonic() - seconds_ago
    for _ in range(100):
        alive = [u for u, z in s.data.get("zone_troops", {}).items()
                 if game.hostile(z) and u not in s.data.get("down", set())]
        waiting = [w for w in s.data.get("waves", ()) if w[0].get("ForceNum") in director.held(s.data["spot"])]
        if not alive and waiting and not s.data.get("mission_won"):
            director.run(s, ("wake", waiting[0][0]["ForceNum"]))      # its story step (the director's HOLD)
            continue
        if not alive or s.data.get("mission_won"):
            break
        for u in alive:
            game.mission_troop_down(s, state, u)
        press_prompts(s)
    run_pending(s)
    if director.table_wins(s.data["spot"]):             # a table's own win (Grey Fog's finale): its story places
        for st in director.script(s.data["spot"]):
            if st["on"] == "bound":
                b = director.bound(s.data["spot"], st["bound"])
                director.on_position(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)                                      # the director's ending lines, then the window
    return [w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE]


def record(w):
    out = bytes(w.buf)
    # i16 0, won 1, u32 the clear time (seconds), n 1
    assert out[:3] + out[7:8] == bytes(2) + bytes([1]) + bytes([1]) and len(out) == 8 + game.MISSION_RECORD
    return out[8:]


@pytest.mark.parametrize("elapsed, par, deaths, grade", [
    (0, 100, 0, "S"), (100, 100, 0, "S"), (100.5, 100, 0, "A"), (125, 100, 0, "A"), (125.5, 100, 0, "B"),
    (150, 100, 0, "B"), (150.5, 100, 0, "C"), (200, 100, 0, "C"), (200.5, 100, 0, "D"), (10 ** 6, 100, 0, "D"),
    (50, 100, 1, "A"), (130, 100, 2, "D"), (50, 100, 9, "D"),
    (500, 0, 0, "S"), (500, 0, 2, "B"),                 # no par from the data: only the deaths grade
])
def test_the_grade_follows_the_clear_time_against_par_and_the_hero_deaths(elapsed, par, deaths, grade):
    assert game.GRADES[game.mission_grade(elapsed, par, deaths)] == grade


def test_par_is_the_mission_base_time_of_the_hostile_troops_the_room_spawned():
    s = Session(char(), spot=10358)
    game.spawn_zone_troops(s)
    # Grey Fog: 11 hostile troops of types with MISSION_BASE_TIME 66 (x7), 37 (x2), 52 (x2); its 18 staging troops of
    # force 25000 add nothing
    assert game.mission_par(s) == 640
    s = Session(char(), spot=10233)
    win(s, State())
    assert game.mission_par(s) == 2658                  # Tower of Moonlight, every wave spawned: 45 troops


def test_a_won_mission_pays_its_table_exp_by_grade_and_fills_the_record():
    c = char(level=4, exp=1150)                         # 10233's Recom_Level_1 is 4: no level adjustment
    s = Session(c, spot=10233)
    won = win(s, State(), seconds_ago=1154)             # %Mission_Grade: 30210 + 100000 + 13021 of 220000: B
    assert len(won) == 1
    rec = record(won[0])
    assert struct.unpack_from("<I", bytes(won[0].buf), 3)[0] == 1154        # the window's Clear Time
    assert struct.unpack_from("<i2xBQxB", rec, 0x10) == (0, 4, 139, 5)     # class, level 4, B's Hero_Exp 139, level 5
    assert (rec[0x284], struct.unpack_from("<H", rec, 0x285)[0]) == (2, game.MY_SLOT)
    assert rec[0x29f:0x2a1] == obf.u16(1)               # one card at B
    assert all(rec[0x45 + 0x44 * k:0x49 + 0x44 * k] == obf.u32(0xFFFFFFFF) for k in (1, 2, 3))
    assert (c["level"], c["exp"]) == (5, 89)            # 1150 + 139 - 1200
    protos = [w.proto for w in s.sent]
    assert protos.index(world.S2C_EXP) < protos.index(game.S2C_MISSION_COMPLETE)   # the level after is in the record
    assert c["cleared"]["10233"] == [1, 0, 0]
    again = Session(c, spot=10233)                      # a second clear at 0 s, two hero deaths: 212000, S
    again.data["hero_deaths"] = 2
    game.mission_won(again, State())
    run_pending(again)
    rec = record(next(w for w in again.sent if w.proto == game.S2C_MISSION_COMPLETE))
    # 154 x Repeat_Penalty 0.66 x ExpAdjustMission 0.9 (the hero is now one level over Recom_Level_1)
    assert rec[0x284] == 0 and struct.unpack_from("<Q", rec, 0x17)[0] == 91
    assert c["exp"] == 89 + 91 and c["cleared"]["10233"] == [2, 0, 0]


def test_the_exp_modifiers_come_from_the_tables():
    d = game.reward_row(10327, 0, 4)                    # PVE_REPEAT 10327 Normal D: Hero_Exp 880, ExpRate 0.5
    assert game.mission_exp({"level": 11}, 10327, 0, d, 3) == 440       # Repeat_Penalty_Control False: no penalty
    assert game.mission_exp({"level": 14}, 10327, 0, d, 0) == 440       # RPC False: no level adjustment either (F2)
    s = game.reward_row(10233, 0, 0)
    assert game.mission_exp({"level": 7}, 10233, 0, s, 0) == 107        # 3 levels over Recom_Level_1 4: x0.7
    assert game.mission_exp({"level": 4}, 10233, 0, s, 7) == 50         # 154 x the last Repeat_Penalty row, 0.33
    assert game.mission_exp({"level": 30}, 10233, 0, s, 0) == 0         # 26 levels over: ExpAdjustMission 0
    assert game.reward_row(10540, 0, 3) is None and game.reward_row(10358, 0, 0) is None   # corridor C, Grey Fog


def test_the_reward_card_rolls_the_grades_category_for_the_hero_class():
    st = State()
    c = char()
    g = Session(c, spot=10233)
    st.game_sessions[1] = g
    rec = record(win(g, st, seconds_ago=60)[0])         # under MinTime 856: S, one card of 903111 (E급_040)
    assert rec[0x284] == 0 and rec[0x29f:0x2a1] == obf.u16(1)
    grole, wrole = game.make(st, 0), world.make(st, 0, "127.0.0.1", 0)

    def card(role, s, index):
        role.handlers[game.C2S_REWARD_CARD](s, pkt(game.C2S_REWARD_CARD, bytes([index])))
        reply = [x for x in s.sent if x.proto == game.S2C_REWARD_CARD][-1]
        out = bytes(reply.buf)
        assert len(out) == 9
        assert struct.unpack_from("<HB", out) == (game.MY_SLOT, index)
        return obf.dec_u32(out[3:7]), obf.dec_u16(out[7:9])

    w = Session(c)                                      # the world connection (the id is outside the room's range)
    code, n = card(wrole, w, 1)
    assert code in GLEN_POOL and n == 1 and [(i["code"], i["count"]) for i in c["bag"]] == [(code, 1)]
    assert not any(w.proto == 0x50d2 for w in g.sent)   # no auto-leave (0x50d2): the player leaves by Mission Complete
    assert card(grole, g, 1) == (code, 1) and len(c["bag"]) == 1        # the same card again: no second item
    assert card(grole, g, 0) == (game.EMPTY_CARD, 0) and card(grole, g, 7) == (game.EMPTY_CARD, 0)
    assert len(c["bag"]) == 1


def test_grey_fog_ends_with_no_window_and_its_quest_pays():
    # decision B2 (owner 2026-09-30, "vanilla, no window"; it replaces the 2026-09-28 card at every end): no
    # mission_reward and no %Mission_Grade row, and the tape (part 1 27:48-29:02) goes from the finale to loading and
    # the field's end scene: no 0x5044, no grade, no card; the clear counts for the quest and the room is left (0x4041)
    c = char(level=5, exp=10)
    c["quests"]["active"]["1150301"] = {"counts": [0] * 5}          # MissionLevelClear 10358 Any
    c["mission"] = {"back": 10350, "quest": 1150301}
    s = Session(c, spot=10358)
    assert win(s, State(), seconds_ago=1) == [] and "cards" not in s.data
    assert (c["level"], c["exp"]) == (5, 10) and not any(w.proto == world.S2C_EXP for w in s.sent)
    assert c["quests"]["active"]["1150301"]["counts"][0] == 1 and c["cleared"]["10358"] == [1, 0, 0]
    leave = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_MISSION_LEAVE and len(leave) == 16 and obf.dec_u32(leave[4:8]) == 10350
    assert c["spot"] == 10350 and c["mission_return"]["warp"] == 30001 and "mission" not in c
    assert [game.windowless(sp) for sp in (10358, 10361, 10362, 10233, 10540, 10349)] == [True] * 3 + [False] * 3


def test_the_win_command_completes_the_mission_room_and_its_quest():
    # owner 2026-09-28: "create a command to force completion of a mission ... no matter the mission will be concluded
    # and the quest will be completed": "!win" in chat wins the room as a clear (1150601 MissionLevelClear at 10234)
    import types
    st = State()
    c = char(level=6)
    c["name"] = "Aldric"
    c["quests"]["active"]["1150601"] = {"counts": [0] * 5}
    g = Session(c, spot=10234)
    g.w, g.state = types.SimpleNamespace(is_closing=lambda: False), st
    game.spawn_zone_troops(g)
    st.game_sessions[1] = g
    role, w = world.make(st, 0, "127.0.0.1", 0), Session(c)
    role.handlers[world.C2S_CHAT](w, pkt(world.C2S_CHAT, bytes([0]) + b"!win\0"))
    assert g.data.get("mission_won") and any(x.proto == game.S2C_MISSION_COMPLETE for x in g.sent)
    assert c["quests"]["active"]["1150601"]["counts"][0] == 1
    assert bytes(w.sent[-1].buf).endswith(b"mission 10234 completed by command\0")
    role.handlers[world.C2S_CHAT](w, pkt(world.C2S_CHAT, bytes([0]) + b"!win\0"))     # once
    assert sum(x.proto == game.S2C_MISSION_COMPLETE for x in g.sent) == 1


def test_the_quest_commands_fill_then_hand_in():
    # owner 2026-09-28: "another one to complete the quests": !quest <id> fills (ready at the NPC), !questdone hands in
    st = State()
    c = char(level=6)
    c["name"] = "Aldric"
    c["quests"]["active"]["1150316"] = {"counts": [0] * 5}            # Talk 6502 (the Mercenary's Grave)
    c["quests"]["active"]["1150306"] = {"counts": [1, 0, 0, 0, 0]}    # ItemGain 451000206 x3
    role, w = world.make(st, 0, "127.0.0.1", 0), Session(c)
    say = lambda text: role.handlers[world.C2S_CHAT](w, pkt(world.C2S_CHAT, bytes([0]) + text.encode() + b"\0"))
    say("!quest 1150316")
    assert c["quests"]["active"]["1150316"]["counts"][0] == 1 and c["quests"]["active"]["1150306"]["counts"][0] == 1
    assert bytes(w.sent[-1].buf).endswith(b"quests ready to hand in: 1150316\0")
    say("!questdone")
    assert not c["quests"]["active"] and {1150316, 1150306} <= set(c["quests"]["done"])
    assert bytes(w.sent[-1].buf).endswith(b"quests handed in: 1150316, 1150306\0")
    say("!quest 999")
    assert bytes(w.sent[-1].buf).endswith(b"none (no active quest by that id)\0")


def test_a_graded_mission_without_a_row_for_the_grade_still_pays_nothing(monkeypatch):
    # the Unknown Corridor keeps rows for S / A / B only (walkthrough: "C / D nothing"). Its own band (%Mission_Grade:
    # MaxTime 310, BRate 0) never grades it under B, and deaths cost nothing there (DeathPenaltyRate 0)
    assert game.reward_row(10540, 0, 4) is None and game.reward_row(10540, 0, 0) is not None
    s = Session(char(level=40), spot=10540)
    s.data["hero_deaths"] = 4
    game.mission_won(s, State())
    rec = record(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE))
    assert rec[0x284] == 0 and rec[0x29f:0x2a1] == obf.u16(1) and s.data["cards"]["category"] == 917111
    # on our par grade (a spot without a band) four deaths are D, a grade without a row: no card, no fallback
    monkeypatch.setattr(game.loot, "grade_row", lambda spot, level: None)
    s = Session(char(level=40), spot=10540)
    s.data["hero_deaths"] = 4
    game.mission_won(s, State())
    rec = record(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE))
    assert rec[0x284] == 4 and rec[0x29f:0x2a1] == obf.u16(0)


def test_each_fall_of_the_hero_counts_once_for_the_grade():
    role = game.make(State(), 0)
    s = Session(char(), spot=10352)
    s.data["battle"].add_hero(0, 2)
    s.data["battle"].add_np(1, 1072, 19, c=combat.combatant(10, 1, atk=(100, 100)))   # the attacker (real damage)
    target = bytes([obf.T2[0], obf.T1[0]]) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0])
    header = bytes(8) + bytes([obf.T2[0], obf.T1[1]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72)
    hit = header + struct.pack("<H", 1) + target + struct.pack("<H", 0)
    for _ in range(3):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    assert s.data["hero_deaths"] == 1                   # one fall, however many hits land on the dead hero
    game.revive_hero(s, s.data["battle"].troops[0], (0, 0, 0))
    for _ in range(3):                                      # the revive's 5 s of invincibility (status 33): none lands
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    assert s.data["hero_deaths"] == 1 and s.data["battle"].troops[0]["hp"] == 2
    s.data["statuses"][0][33]["until"] = time.monotonic() - 1                     # ran out
    for _ in range(3):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    assert s.data["hero_deaths"] == 2

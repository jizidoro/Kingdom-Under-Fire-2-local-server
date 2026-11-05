"""The missions' rules against the original (planning/rules/MISSIONS.md, the rules census of 2026-09-30; owner decisions
A and B, planning/rules/README.md): the census's two tables of the tape's result windows recomputed (X1 hero exp, X2
the window's points), and the rules built from it. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import game, loot
from kuf2.packet import Reader
from conftest import run_pending
from test_battle import acts
from test_rewards import Session, State, char, record

# MISSIONS.md X1: (tape, spot, difficulty, grade, hero level, event boost, the window's XP). The levels are the census's
# (entry-window anchors, else the level the story missions' factor fits); the boost is the ×2 hero / troop XP event the
# parts 11, 14, 15, 17 were recorded under (F6), applied to the paid integer (int(13,009 × 0.9) × 2 = 23,416).
X1 = [
    ("p2 19:20", 10233, 0, "S", 4, 1, 154),
    ("p3 41:52", 10235, 0, "S", 8, 1, 991),
    ("p6 6:06", 10212, 0, "S", 11, 1, 2384),
    ("p8 11:02", 10328, 0, "S", 15, 1, 5792),
    ("p9 11:28", 10305, 0, "S", 16, 1, 5212),
    ("p9 16:36", 10347, 0, "S", 16, 1, 2228),           # camp, Repeat_Penalty_Control False: the full row
    ("p9 32:22", 10309, 0, "S", 16, 1, 7725),
    ("p4 29:56", 10345, 0, "S", 10, 1, 839),
    ("p4 45:00", 10303, 0, "D", 10, 1, 1611),
    ("p6 18:14", 10306, 1, "D", 11, 1, 1691),           # Hard
    ("p6 ~24:00", 10327, 0, "S", 11, 1, 1100),
    ("p11 9:36", 10323, 0, "A", 20, 2, 23416),
    ("p12 7:48", 10349, 0, "C", 21, 1, 5612),           # camp, RPC False: no level adjustment
    ("p12 16:58", 10320, 0, "S", 22, 1, 18278),
    ("p12 22:02", 10327, 0, "S", 22, 1, 1100),          # subjugation, RPC False: 1,100 to a hero 11 levels over
    ("p14 8:52", 10315, 0, "S", 23, 2, 59154),
    ("p15 10:14", 20301, 0, "S", 25, 2, 75884),
    ("p17 6:44", 20304, 0, "S", 26, 2, 94162),
    ("p17 47:42", 20305, 0, "D", 27, 2, 100440),
]


@pytest.mark.parametrize("tape, spot, difficulty, grade, level, boost, xp", X1, ids=[r[0] for r in X1])
def test_the_hero_exp_reproduces_every_result_window_of_the_tape(tape, spot, difficulty, grade, level, boost, xp):
    row = game.reward_row(spot, difficulty, game.GRADES.index(grade))
    assert game.mission_exp({"level": level}, spot, difficulty, row, 0) * boost == xp


def test_the_level_adjustment_applies_only_where_the_repeat_penalty_is_on():
    # F2: the 43 spots with reward rows and Repeat_Penalty_Control False (camps, subjugations, rifts, the corridor)
    # pay the full Hero_Exp at any level; the story spots keep ExpAdjustMission (Tower at level 30: 0)
    row = game.reward_row(10327, 0, 0)
    assert [game.mission_exp({"level": lv}, 10327, 0, row, 0) for lv in (1, 11, 20, 21, 60)] == [1100] * 5
    assert game.mission_exp({"level": 30}, 10233, 0, game.reward_row(10233, 0, 0), 0) == 0


# MISSIONS.md X2: the windows beyond test_loot.FOOTAGE: (tape, spot, difficulty, seconds, hero deaths, clear, damage,
# participants, death penalty, total, grade). The damage count is 0 in all of them (full Damage Points).
X2 = [
    ("p4 45:00", 10303, 0, 611, 0, 3883, 100000, 10388, 0, 114271, "D"),
    ("p6 18:14", 10306, 1, 626, 0, 0, 100000, 5000, 0, 105000, "D"),       # Hard, Recom_Party_2 2
    ("p6 ~24:00", 10327, 0, 230, 0, 46396, 150000, 19639, 0, 216035, "S"),
    ("p12 22:02", 10327, 0, 215, 0, 50000, 150000, 20000, 0, 220000, "S"),
    ("p9 32:22", 10309, 0, 349, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p12 16:58", 10320, 0, 324, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p14 8:52", 10315, 0, 477, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p15 10:14", 20301, 0, 436, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p17 47:42", 20305, 0, 2120, 31, 0, 100000, 2500, 61999, 40501, "D"),  # Recom_Party_1 4; float32(0.02)
]


@pytest.mark.parametrize("tape, spot, difficulty, secs, deaths, clear, damage, party, death, total, grade", X2,
                         ids=[r[0] for r in X2])
def test_the_points_reproduce_every_result_window_of_the_tape(tape, spot, difficulty, secs, deaths, clear, damage,
                                                               party, death, total, grade):
    level = game.DIFFICULTY[difficulty].title()
    p = loot.grade_points(loot.grade_row(spot, level), secs, 0, deaths, game.recom_party(spot, difficulty))
    assert (p["clear"], p["damage"], p["party"], p["death"], p["total"]) == (clear, damage, party, death, total)
    assert game.GRADES[p["grade"]] == grade


def test_participants_points_divide_by_the_recommended_party_and_a_dash_is_one():
    assert [game.recom_party(10306, d) for d in (0, 1, 2)] == [1, 2, 4]
    assert game.recom_party(10233, 1) == 1 and game.recom_party(20305, 0) == 4     # "-" on 10233 Hard
    row = loot.grade_row(10233, "Normal")
    assert loot.grade_points(row, 0, 0, 0, 8)["party"] == 2500                      # 0.1 x 200,000 / 8


def test_the_won_record_carries_the_divided_participants_and_the_float_penalty():
    s = Session(char(level=27), spot=20305)              # part 17 47:42: 2,120 s, 31 deaths
    s.data["started_at"] = time.monotonic() - 2120.2
    s.data["hero_deaths"] = 31
    game.mission_won(s, State())
    rec = record(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE))
    assert struct.unpack_from("<q", rec, 0x0)[0] == -61999 and struct.unpack_from("<Q", rec, 0x28f)[0] == 2500
    assert struct.unpack_from("<Q", rec, 0x27c)[0] == 40501 and rec[0x284] == 4


def test_the_room_waits_for_mission_complete_after_the_card():
    # decision A10: the original kept the room after the card (tape part 2 19:31-19:46: "Press Alt ... then press the
    # Mission Complete button", "Get All [F]"). The client closes the result window by itself (23 s after its score
    # animation) and shows the HUD's Mission Complete button, which sends 0x4040; no 0x50d2 (the 5 s auto-leave)
    st = State()
    g = Session(char(), spot=10233)
    st.game_sessions[1] = g
    game.mission_won(g, st)
    run_pending(g)                                      # Tower's ending lines, then the window
    assert g.data["cards"]["allowed"] == 1
    game.open_card(g, g, st, bytes([0]))
    assert g.sent[-1].proto == game.S2C_REWARD_CARD and not any(w.proto == 0x50d2 for w in g.sent)
    game.make(st, 0).handlers[game.C2S_MISSION_LEAVE](g, Reader(struct.pack("<HBH", 5, 0, game.C2S_MISSION_LEAVE)))
    leave = bytes(g.sent[-1].buf)
    assert g.sent[-1].proto == game.S2C_MISSION_LEAVE and len(leave) == 16 and leave[:2] == bytes(2)


def fort_valley_troop(difficulty, troop_id=20003):
    """Fort Valley 10306's zone troop (20003: orc infantry 106050, commander 106030) spawned on a difficulty."""
    from kuf2 import combat, zone
    s = Session(char(level=12), spot=10306)
    s.data["difficulty"] = difficulty
    t = next(t for t in zone.for_spot(10306)["NPCTroopInfoData"] if t["TroopID"] == troop_id)
    assert game.spawn_zone_troop(s, t)
    return s, t


def test_hard_and_hell_add_or_scale_the_units_of_their_change_row():
    # %NP_Troop_Change Unit_Count_Hard / _Hell (247 rows), parsed as the client's loader does (0x1418becb0 ->
    # 0x14193cd90: "n%" a factor n / 100, else a count added): 106050 "4" / "10"; 118090 (20 units) "120%" / "120%"
    units = {d: len(fort_valley_troop(d)[0].data["battle"].troops[20003]["units"]) for d in (0, 1, 2)}
    assert units[1] == units[0] + 4 and units[2] == units[0] + 10
    assert [game.difficulty_units(118090, 20, d) for d in (0, 1, 2)] == [20, 24, 24]
    assert [game.difficulty_units(112170, 12, d) for d in (0, 1, 2)] == [12, 0, 12]     # an ally: "-12" on Hard
    assert game.difficulty_units(120030, 1, 1) == 1                                    # one ogre at 120%
    assert game.difficulty_units(133080, 7, 1) == 7                                    # no row: as spawned


def test_a_hard_kill_pays_its_rows_gold_and_its_commanders_gold(monkeypatch):
    # item_drop_money %Troop of the troop's variant (20106050) and %Leader of its commander's (20106030, 0-1; 143
    # leader rows pay above 1, e.g. 107050 3-4): one pile, the most of each range here
    import random
    from test_loot import hit_to_wipe
    monkeypatch.setattr(random, "randrange", lambda n: n - 1)
    for d, troop, leader in ((0, 106050, 106030), (1, 20106050, 20106030)):
        s, _ = fort_valley_troop(d)
        hit_to_wipe(game.make(State(), 0), s, 20003)
        (gold,) = s.data["gold_drops"].values()
        assert gold == game.roll_gold(troop, lambda n: n - 1) + game.roll_leader_gold(leader, lambda n: n - 1)
    assert game.roll_leader_gold(107050, lambda n: n - 1) == 4 and game.roll_leader_gold(-100) == 0


def spent_free_revives(c):
    """The day's free resurrections used up (census ECONOMY J5: three a day before the price), for the price tests."""
    c["free_revives"] = {"day": __import__("kuf2.rules", fromlist=["game_day"]).game_day(), "used": game.FREE_REVIVES}


def dead_hero(spot, cubic=0):
    s = Session(char(), spot=spot)
    s.data["char"]["cubic"] = cubic
    spent_free_revives(s.data["char"])
    s.data["battle"].add_hero(0, 1000)
    s.data["battle"].troops[0]["hp"] = 0
    return s


def revive_here(s, item=0xFFFFFFFF):
    from kuf2 import obf
    body = struct.pack("<H", 0) + obf.u32(item)
    game.make(State(), 0).handlers[game.C2S_REVIVE_HERE](s, Reader(struct.pack("<HBH", 5 + len(body), 0,
                                                                         game.C2S_REVIVE_HERE) + body))
    reply = next(w for w in reversed(s.sent) if w.proto == game.S2C_REVIVE_HERE)
    return struct.unpack_from("<H", bytes(reply.buf))[0]


def test_revive_in_place_costs_the_resurrect_cubic_and_the_camp_revive_is_free():
    # the death window's revive-here: the client's RevivalCostSetting (0x1406902f0) prices a hero's revive from
    # ItemCurrencyInfoHolder (*0x1435a6240) at (Resurrect 8, index 0): item_currency %Base Resurrect Index 0 = 70
    # Cubic (not item_consume_sub %Revive's 9, which no revive path reads); spottable %Revival PVE_NORMAL: CUBIC, no
    # limit. Q2 stands: no defeat, the camp revive (0x50d6) stays free
    from kuf2 import obf, world
    assert game.revive_cost() == 70
    s = dead_hero(10233, cubic=100)
    assert revive_here(s) == 0 and s.data["char"]["cubic"] == 30 and s.data["battle"].troops[0]["hp"] > 0
    assert any(w.proto == world.S2C_CUBIC and bytes(w.buf) == obf.u32(30) for w in s.sent)
    s = dead_hero(10233, cubic=69)                      # the client refuses first (text 0xd01b); ours refuses too
    assert revive_here(s) != 0 and s.data["char"]["cubic"] == 69 and s.data["battle"].troops[0]["hp"] == 0
    s = dead_hero(10233, cubic=0)
    game.make(State(), 0).handlers[game.C2S_REVIVE_CAMP](s, Reader(struct.pack("<HBH", 5, 0, game.C2S_REVIVE_CAMP)))
    assert s.data["battle"].troops[0]["hp"] > 0 and s.data["char"]["cubic"] == 0


def test_revive_in_place_follows_the_contents_revival_row():
    # %Revival by spottable Spot_Contents_Type, as the HUD reads it (0x14068e280: its Limit_Revive, not the spot's
    # own column): PVE_RIFT CUBIC 5, PVE_EXTREME 3, PVE_DAILY / PVE_WEEKLY IMPOSIBLE; 0x7411 no revivals left,
    # 0x7412 not allowed here
    assert game.revival(10335) == ("CUBIC", 5) and game.revival(10233) == ("CUBIC", -1)
    assert game.revival(10540)[0] == "IMPOSIBLE"
    s = dead_hero(10335, cubic=1000)
    for n in range(5):
        assert revive_here(s) == 0
        s.data["battle"].troops[0]["hp"] = 0
    assert revive_here(s) == 0x7411 and s.data["char"]["cubic"] == 1000 - 5 * 70
    assert revive_here(dead_hero(10540, cubic=1000)) == 0x7412


def test_the_camp_revive_takes_the_start_point_nearest_the_hero():
    # census I3: the free revive (0x50d6 -> 0x50d7, the position from the server) at the zone's player start point
    # nearest where the hero fell; Fort Valley 10306 has four (StartPointID 0-3), the field 10350 its groups
    s = dead_hero(10306)
    s.data["hero_pos"] = (44700, 0, 1300)
    game.make(State(), 0).handlers[game.C2S_REVIVE_CAMP](s, Reader(struct.pack("<HBH", 5, 0, game.C2S_REVIVE_CAMP)))
    z, x = struct.unpack_from("<ff", bytes(next(w for w in s.sent if w.proto == game.S2C_REVIVE_CAMP).buf), 4)
    assert (round(x), round(z)) == (44249, 1489)
    s.data["hero_pos"] = (43700, 0, 3700)
    assert game.revive_point(s) == (43722, 0, 3604)
    s.data["hero_pos"] = None
    assert game.revive_point(s) == game.start_pos(s)


def world_enter(c, spot, difficulty=0):
    """The client's 0x3f48 into `spot` from the town: the 0x3f41 result (0 = go to the game server) and the session."""
    from kuf2 import obf, world
    w = Session(c)
    body = obf.u32(spot) + bytes([difficulty, 0])
    world.make(State(), 0, "127.0.0.1", 0).handlers[world.C2S_ENTER_SPOT](
        w, Reader(struct.pack("<HBH", 5 + len(body), 0, world.C2S_ENTER_SPOT) + body))
    reply = next(x for x in w.sent if x.proto == world.S2C_GAME_SERVER)
    return struct.unpack_from("<H", bytes(reply.buf))[0], w


def test_entry_needs_the_spots_troop_minimum():
    # census A5 / Q45: spottable Min_Limit_Troop (51 spots: Grey Rock 1, New Hampton 2, the Dimensional Test 3), the
    # original server's own check (the client's loader keeps it at SpotInfo +0x1a0 and makes no check); its refusal
    # 0x1c21 prints text 7475 "At least %1% troops must be organised in order to continue."
    from test_army import army
    c, _ = army(1, deck=(1,))
    assert world_enter(c, 10234)[0] == 0                        # Grey Rock: one deck troop, enough
    c.pop("mission")
    assert world_enter(c, 10234, 1)[0] == 0                     # its Hard takes none in (Limit_Troop_2 "-") but
    c.pop("mission")                                            # still wants one organised
    assert world_enter(c, 10235)[0] == game.TROOPS_SHORT        # New Hampton wants two
    assert world_enter(dict(char(), id=1), 10234)[0] == game.TROOPS_SHORT
    assert world_enter(dict(char(), id=1), 10233)[0] == 0       # Tower: none needed


def test_the_hard_and_hell_dimensional_test_takes_its_ticket():
    # census A7: spottable 10238 Require1_Type_2 / _3 PayItem 760000150 x1 (Hard) / 760000160 x1 (Hell); the client
    # only checks the bag (entry check case 6), the entry takes it; Normal takes nothing
    from test_army import army
    c, _ = army(1, 1, 1, deck=(1, 2, 3))                        # its Min_Limit_Troop is 3
    c["bag"] = [{"code": 760000150, "count": 2, "slot": 0, "serial": 1},
                {"code": 760000160, "count": 1, "slot": 1, "serial": 2}]
    for d, left in ((0, [2, 1]), (1, [1, 1]), (2, [1])):
        assert world_enter(c, 10238, d)[0] == 0
        assert [it["count"] for it in c["bag"]] == left
        c.pop("mission", None)


def test_a_mission_left_without_a_win_costs_its_aborted_ap():
    # census A4 / Q45: spottable Troop_Mission_aborted (15 on 78 spots), each deployed troop, when the room is left
    # before its win (0x4048); a won room left by Mission Complete costs nothing more
    from kuf2 import world
    from test_army import army, entered, ap_pushes
    for won in (False, True):
        c, ts = army(1, deck=(1,))
        _, g = entered(10234, c)                                # Troop_Mission_Enter 15: AP 100 -> 85
        st = State()
        st.game_sessions[1] = g
        g.data["mission_won"] = won
        w = Session(c)
        world.make(st, 0, "127.0.0.1", 0).handlers[world.C2S_MISSION_ESCAPE](
            w, Reader(struct.pack("<HBH", 5, 0, world.C2S_MISSION_ESCAPE)))
        assert ts[0]["ap"] == (85 if won else 70) and ap_pushes(w) == ([] if won else [(ts[0]["uid"], 70)])


def test_each_day_count_is_pushed_as_it_changes():
    # census J4: 0x10b4 (0x140675cf0: one 0x10b3 entry, 13 bytes: i32 group, 8 zero bytes, u8 used) after a counted
    # entry (the subjugations' Mission_Enter groups) or clear
    from kuf2 import rules
    from test_army import army
    c, _ = army(1, deck=(1,))
    code, w = world_enter(c, 10327)                             # Grey Wood subjugation: group 110, 3 entries a day
    push = [x for x in w.sent if x.proto == rules.S2C_DAY_LIMIT]
    assert code == 0 and len(push) == 1 and bytes(push[0].buf) == struct.pack("<i", 110) + bytes(8) + bytes([1])


def test_the_hero_exp_gauge_carries_its_percent_before_and_after():
    # the result record's hero entry (0x14085b300): +0x16 / +0x20 level before / after, +0x21 / +0x1f the gauge's
    # percent before / after (PlayExp 0x14085d650: AddExp = (after - before) x 100 - start + end), as the troop slots'
    # +0x51 / +0x52; a level-4 hero at 1,150 of 1,200 gets Tower's S 154: level 5 at 104
    from kuf2 import world
    c = char(level=4, exp=1150)
    s = Session(c, spot=10233)
    game.mission_won(s, State())
    run_pending(s)
    rec = record(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE))
    assert (rec[0x16], rec[0x20], c["exp"]) == (4, 5, 1150 + 154 - world.hero_need(4))
    assert (rec[0x21], rec[0x1f]) == (1150 * 100 // world.hero_need(4), c["exp"] * 100 // world.hero_need(5))


# --- the rules hunt (2026-10-01, build/hmissions) ---

def notices(s):
    """(index in s.sent, the text ids) of every ActGuiShowNoticeWindow sent ([act, panel, ids ..., seconds])."""
    from kuf2 import director
    out = []
    for i, w in enumerate(s.sent):
        b = bytes(w.buf)
        if w.proto == game.S2C_SCRIPT_ACTION and struct.unpack_from("<I", b)[0] == director.ACT_NOTICE_WINDOW:
            out.append((i, struct.unpack_from("<%dI" % (len(b) // 4), b)[2:-1]))
    return out


def test_towers_mission_complete_notice_comes_when_the_result_window_closes():
    # K3: the tape part 2 (2 fps set 1149-1155 / 1171-1175): "Mission Succeeded" first at 19:10.0, the window gone at
    # 19:32.0, "Mission Complete / Press Alt to activate the cursor and then press the Mission Complete button"
    # (missiontext 8200 / 8210) from 19:32.5; the client closes the window by its own clock (0x14085ef60, 23 s), so the
    # notice goes out RESULT_CLOSE_S after the record, not with the ending lines before it
    s = Session(char(), spot=10233)
    game.mission_won(s, State())
    while not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent):
        s.pending.sort(key=lambda p: p[0])
        s.pending.pop(0)[1]()                           # the ending (3_SealedTower), then the window
    at = next(i for i, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_COMPLETE)
    assert (8200, 8210) not in [n[:2] for _, n in notices(s)]
    assert game.RESULT_CLOSE_S == 23 and any(d == game.RESULT_CLOSE_S for d, _ in s.pending)
    run_pending(s)
    shown = [i for i, n in notices(s) if n[:2] == (8200, 8210)]
    assert len(shown) == 1 and shown[0] > at


def colosseum_standing(s):
    return [u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", set())]


@pytest.mark.parametrize("spot, rounds", [
    # 20302 (Sunstruk Colosseum 1): the zone's round aliases 라운드1..7, as its announcer's lines name them (missiontext
    # 2_sunstrokcolosseum 501100 the Wolf King "first", 501200 the White Bear "second", 506100 the La Crete Queen,
    # 507100 the Desert Tarantula, 508100 the Armoured Beetle "fifth", 505100 the Basilisk "sixth", 511000 "the final
    # battle" the Basilisk King, 511003 "Kugash conquered the colosseum"); the Exile 20011 and F22000's seven unnamed
    # troops are an older set's (the 1100-11400 lines) and fight in no round
    (20302, [[30018], [20021], [20031, 20032, 20033], [40001, 40002], [20041], [30005, 30006, 30015], [20051]]),
    # 20319 (Colosseum 2): 보스_0<round><k> (521000 the Exile Assassin Commander, 522000 the "collabo", 523000 the
    # Ogre, 524000 the Gnoles, 525000 the last, 526000 "Kugash defeated all challengers")
    (20319, [[20011], [20021, 20022], [20031], [20041, 20042, 20043], [20051, 20052, 20053]]),
])
def test_the_colosseum_fights_its_rounds_in_order(spot, rounds):
    from kuf2 import rules
    plan = rules.plan(spot, game.mission_plan(spot))
    assert [sorted(t["TroopID"] for t in w) for w in plan["waves"]] == rounds


def test_the_colosseums_next_match_begins_15_seconds_after_a_round():
    # C6: missiontext 2_sunstrokcolosseum 60 "Next match begins in 15 sec.", 61 "Next match begins in 5 sec." (112 "Next
    # battle begins as soon as the result is confirmed"): the next round comes 15 s after the last opponent fell
    from kuf2 import rules
    from test_battle import mission_room
    s = mission_room(20302)
    assert colosseum_standing(s) == [30018]                     # round 1 at the start
    game.mission_troop_down(s, s.state, 30018)
    assert colosseum_standing(s) == [] and not s.data.get("mission_won")
    assert (rules.NEXT_MATCH,) in [n[1][:1] for n in notices(s)]
    due = sorted(d for d, _ in s.pending)
    assert rules.ROUND_WAIT_S == 15 and rules.ROUND_WAIT_S - rules.ROUND_SOON_S in due and rules.ROUND_WAIT_S in due
    s.pending.sort(key=lambda p: p[0])
    s.pending.pop(0)[1]()                                       # 5 s left
    assert notices(s)[-1][1][0] == rules.NEXT_MATCH_SOON and colosseum_standing(s) == []
    s.pending.pop(0)[1]()                                       # 15 s: round 2
    assert colosseum_standing(s) == [20021]
    for n in range(6):                                          # rounds 2..7, each after its break
        for u in colosseum_standing(s):
            game.mission_troop_down(s, s.state, u)
        if n < 5:
            assert not s.data.get("mission_won")
            s.pending.sort(key=lambda p: p[0])
            while not colosseum_standing(s):
                s.pending.pop(0)[1]()
    assert s.data.get("mission_won") and not s.data.get("round_break")    # the final round won it, no break after
    assert 20011 not in s.data["zone_troops"]                  # the Exile never came


def break_prop(s, prop_id, hits=10):
    """Hit an attackable prop (the ability execute's prop list) until it breaks."""
    from kuf2 import combat
    from test_rewards import pkt
    role = game.make(s.state, 0)
    hit = bytes(7) + struct.pack("<HH", 1, 0) + bytes([1]) + game.obf.u32(prop_id)
    for _ in range(hits):
        role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))


def test_grey_hamptons_panel_is_the_one_the_tape_shows():
    # the tape part 14 (Us8IGwvuo5M) 4:40-5:40: "Grey Hampton" 700, success 711 "Penetrate the enemy's defence and
    # neutralise Dimension Storms" / 720 "Destroy Dimension Storm Mana Supply Device", failure 740 "Let Hero and all
    # ally Troops die" (the 19001 block, with "Defeat Juggernaut" and "Timer Status Window", is not shown)
    assert game.mission_text(10315) == (700, ((710, (711, 720)), (730, (740,))))


def test_grey_hamptons_storm_closes_150_seconds_after_its_device_and_the_room_is_won():
    # C6: the tape part 14: the hero breaks the relic's "Testing Device" (smartproptable 12, the one at the dimension
    # storm 219) about 5:20; from 5:38 "Dimension storm fully closed in" (760) under 711's group reads 00:02:30 with
    # 721 "Survive until the Dimension Storm is closed" and the notice 850 / 860; 00:00:00 at 8:14, 721 (Complete),
    # "Mission Succeeded" 8:40. Before the device, the last enemy falling does not win it
    from kuf2 import rules
    from test_battle import mission_room
    s = mission_room(10315)
    assert rules.storm_device(10315) == 40188                  # beside the storm 40183, not the four corner ones
    for u in [u for u, t in s.data["zone_troops"].items() if game.hostile(t)]:
        game.mission_troop_down(s, s.state, u)
    for _ in range(20):                                        # every wave down: still no win without the device
        standing = [u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data["down"]]
        if not standing:
            break
        for u in standing:
            game.mission_troop_down(s, s.state, u)
    assert not s.data.get("mission_won")
    break_prop(s, 40184)                                       # a corner device: nothing
    assert s.data.get("clock") is None
    break_prop(s, 40188)
    assert rules.time_left(s) == pytest.approx(rules.STORM_CLOSE_S, abs=1) and rules.STORM_CLOSE_S == 150
    assert [game.ACT_SITUATION_DONE, 0xff, 720, 1] in acts(s, game.ACT_SITUATION_DONE)
    assert [game.ACT_SITUATION_LINE, 0xff, 710, 721] in [a[:4] for a in acts(s, game.ACT_SITUATION_LINE)]
    assert acts(s, rules.ACT_SITUATION_TIME)[-1][2:] == [760, 760, 150]
    assert (850, 860) in [n[1][:2] for n in notices(s)]
    s.data["clock"]["t0"] -= 150
    rules.tick(s)
    assert [game.ACT_SITUATION_DONE, 0xff, 721, 1] in acts(s, game.ACT_SITUATION_DONE)
    assert s.data.get("mission_won")


# MISSIONS.md X2, the hunt's windows (2026-10-01, tape dig): every result window the tape shows beyond X2's, with the
# damage count (the Greyrock 60 and New Hampton 1 inverted from their Damage Points) and the death count (the troop
# wipes counted on the HUD's "Resurrection [Fx]" button: New Hampton 5, Bright Spring 31, no hero death in any run)
X3 = [
    ("p2 43:44", 10234, 818, 60, 0, 100000, 76923, 17692, 0, 194615, "S"),
    ("p4 29:50", 10345, 259, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p5 15:56", 10306, 743, 0, 0, 34875, 100000, 13487, 0, 148362, "B"),
    ("p5 30:36", 10211, 409, 0, 0, 101780, 80000, 18178, 0, 199958, "S"),
    ("p7 28:34", 10319, 313, 0, 0, 120000, 80000, 20000, 0, 220000, "S"),
    ("p10 15:24", 10312, 457, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p13 14:30", 10314, 381, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p13 23:04", 10324, 446, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p15 17:56", 20325, 291, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),
    ("p3 41:46", 10235, 989, 1, 5, 100000, 99687, 19968, 19968, 199687, "S"),      # 5 troop wipes, the hero undying
    ("p16 8:52", 20303, 386, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),        # 2 wipes by a poison trap: none
]


@pytest.mark.parametrize("tape, spot, secs, damage_count, deaths, clear, damage, party, death, total, grade", X3,
                         ids=[r[0] for r in X3])
def test_the_hunts_windows_reproduce_too(tape, spot, secs, damage_count, deaths, clear, damage, party, death, total,
                                         grade):
    p = loot.grade_points(loot.grade_row(spot, "Normal"), secs, damage_count, deaths, game.recom_party(spot, 0))
    assert (p["clear"], p["damage"], p["party"], p["death"], p["total"]) == (clear, damage, party, death, total)
    assert game.GRADES[p["grade"]] == grade


def test_the_death_penalty_counts_each_wipe_of_a_deck_troop():
    # E3: the tape's death count is the player's troop wipes (20305: F1 12 + F2 7 + F3 12 = 31 with no hero death;
    # New Hampton 5 while the hero cannot die); a hero death counts too ([C] "a penalty per hero or troop death"; no
    # graded run on the tape has one). One wipe is one, however many hits report it
    from kuf2 import combat
    from test_army import army, entered
    from test_battle import enc_uid, hit_header
    from test_rewards import pkt
    c, ts = army(1)
    role, s = entered(10235, c)
    b = s.data["battle"]
    enemy = next(u for u, t in b.troops.items() if u >= 10000 and t.get("c") and t["c"]["team"] != 0
                 and t["c"]["branch"] != "PROP")
    body = lambda: (hit_header(troop=enemy) + struct.pack("<H", 1) + enc_uid(1) + struct.pack("<H", 10)
                    + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in range(10)) + struct.pack("<H", 0))
    for _ in range(2000):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
        if not any(b.troops[1]["units"]):
            break
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
    assert s.data.get("troop_wipes") == 1
    s.data["hero_deaths"] = 1
    s.data["started_at"] = time.monotonic() - 989
    game.mission_won(s, s.state if hasattr(s, "state") else State())
    s.run_later()
    rec = record(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE))
    p = loot.grade_points(loot.grade_row(10235, "Normal"), 989, 0, 2)
    assert struct.unpack_from("<q", rec, 0x0)[0] == -p["death"] and p["death"] == int(loot.float32("0.02") * 2 * 200000)


def test_essex_counts_its_totems_and_its_clock_gains_a_minute_for_each():
    # C6 / C7, the tape part 9 (9NwV8ikwLYk): the panel "Stop the contamination in the Essex Forest" (620), failure
    # "Let the Essex Forest be contaminated" (650), "Totems Destroyed" n/7 (660); the entrance ward's totem ([0-0]) falls
    # (26:40, 1030 "The ward has been lifted!") and "Forest fully contaminated in" (680) runs from 3:00 (26:55); each of
    # the seven other totems adds a minute (six jumps 27:22-31:00, to 4:59), 7/7 at 31:00 (1350 "The ward has
    # disappeared. Now, destroy the Chaos Wedge!"); the Wedge's fall wins (32:02; the clock frozen at 4:02)
    from kuf2 import rules
    from test_battle import mission_room
    s = mission_room(10309)
    assert game.mission_text(10309) == (600, ((610, (620,)), (630, (640, 650))))
    assert acts(s, game.ACT_SITUATION_VALUE)[-1][2:6] == [660, 660, 0, 7]
    assert s.data.get("clock") is None
    game.mission_troop_down(s, s.state, 20001)                 # the entrance ward's totem
    assert rules.time_left(s) == pytest.approx(180, abs=1) and acts(s, rules.ACT_SITUATION_TIME)[-1][2:4] == [680, 680]
    for n, u in enumerate((21004, 22005, 22006, 29001, 29002, 29003, 29004), 1):
        game.mission_troop_down(s, s.state, u)
        assert acts(s, game.ACT_SITUATION_VALUE)[-1][4:6] == [n, 7]
        assert rules.time_left(s) == pytest.approx(180 + 60 * n, abs=1)
    assert not s.data.get("mission_won")
    game.mission_troop_down(s, s.state, 30000)                 # the Chaos Wedge
    assert s.data.get("mission_won") and s.data["clock"].get("stopped_at") is not None


def test_kedingtons_lever_clock_runs_five_minutes_and_goes_with_the_lever():
    # C6, the tape part 12 (TrE5TmRNJno): the notice 400 / 410 ("Infiltrate the castle ..." / "Operate the Castle Gate
    # Switchgear Lever inside the castle to open the castle gate.") and "Operate Castle Gate Switchgear Lever within time
    # limit" (650) from 00:05:00 (11:50), "Fail to open the castle gate within the time limit" (670) under the failure
    # heading; the lever pulled with 1:49 left (15:06); at 15:24 the 650 group and its clock are gone, no (Complete)
    from kuf2 import rules
    from test_battle import mission_room
    s = mission_room(10320)
    assert rules.time_left(s) == pytest.approx(300, abs=1) and acts(s, rules.ACT_SITUATION_TIME)[-1][2:] == [650, 650, 300]
    assert [game.ACT_SITUATION_LINE, 0xff, 630, 670] in [a[:4] for a in acts(s, game.ACT_SITUATION_LINE)]
    assert (400, 410) in [n[1][:2] for n in notices(s)]
    rules.on_prop(s, game.zone_prop(10320, 50039))             # the lever (smartproptable 230), cast
    assert [rules.ACT_SITUATION_REMOVE_GROUP, 0xff, 650] in acts(s, rules.ACT_SITUATION_REMOVE_GROUP)
    assert s.data["clock"].get("stopped_at") is not None and not s.data.get("mission_won")
    sent = len(s.sent)
    s.data["clock"]["t0"] -= 400
    rules.tick(s)
    assert len(s.sent) == sent                                 # no clock line once the group is gone


def test_a_killed_troops_loot_lies_where_it_fell(monkeypatch):
    # G3: Packet_RewardBoxCreate 0x140d04240 puts a bag at the header's packed position when its first byte is FALSE
    # and at the local hero when TRUE (the client dig); the tape (part 4 44:32) shows the chest several metres from the
    # hero, where the enemy fell. The troop's place is its last 0x50b0 sync record; none known: at the hero
    import random
    from kuf2 import combat, obf, zone
    from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE
    from test_rewards import pkt
    from test_loot import T1, T2
    monkeypatch.setattr(random, "randrange", lambda n: 0)
    role = game.make(State(), 0)
    s = Session(char(), 10350)
    t = next(t for t in zone.for_spot(10350)["NPCTroopInfoData"] if t["TroopID"] == 10099)
    s.data["zone_troops"] = {t["TroopID"]: t}
    s.data["battle"].add_np(t["TroopID"], 1, 1)
    s.data["battle"].add_hero(0, 1000, c=game.hero_combatant(s.data["char"]))
    q, p15 = obf.pos_xz(52000, 61000)
    sync = struct.pack("<H", 1) + bytes([0, 0]) + struct.pack("<Hh", t["TroopID"], 0) + q + struct.pack("<h", 120) + \
        bytes([p15]) + bytes([0])
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync))
    hit = bytes(8) + bytes([T2[0], T1[0]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72) + \
        struct.pack("<H", 1) + bytes([T2[t["TroopID"] >> 8], T1[t["TroopID"] & 0xff]]) + \
        struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0]) + struct.pack("<H", 0)
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    box = bytes(next(w for w in s.sent if w.proto == game.S2C_REWARD_BOX).buf)
    assert box[1] == OBOOL_FALSE and box[2:6] == q and struct.unpack_from("<h", box, 6)[0] == 120 and box[8] == p15
    game.drop_loot(s, [(350000010, 1)], 0)                     # no troop (a reward dummy's): at the hero
    assert bytes(s.sent[-1].buf)[1] == OBOOL_TRUE


def wiped_deck_troop(spot=10235, cubic=0):
    """A mission room with one deck troop (uid 1) wiped by an enemy's hits."""
    from kuf2 import combat
    from test_army import army, entered
    from test_battle import enc_uid, hit_header
    from test_rewards import pkt
    c, ts = army(1)
    c["cubic"] = cubic
    spent_free_revives(c)
    role, s = entered(spot, c)
    b = s.data["battle"]
    enemy = next(u for u, t in b.troops.items() if u >= 10000 and t.get("c") and t["c"]["team"] != 0
                 and t["c"]["branch"] != "PROP")
    body = lambda: (hit_header(troop=enemy) + struct.pack("<H", 1) + enc_uid(1) + struct.pack("<H", 10)
                    + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in range(10)) + struct.pack("<H", 0))
    for _ in range(2000):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
        if not any(b.troops[1]["units"]) and not b.troops[1].get("leader"):
            break
    return role, s, ts, body


def test_a_wiped_deck_troop_is_revived_in_place_for_its_grade_and_rarity_price():
    # I5 (the client dig): in a story mission (%Revival PVE_NORMAL, CUBIC, no limit) the HUD shows a wiped troop's
    # Resurrection button with a Cubic price (0x140690200 state 1); 0x50f4 names the troop; the price is item_currency
    # Resurrect at the index %Troop_Resurrect gives its TroopGrade x TroopRarity (GRADE1 RARITY1 1 .. GRADE5 RARITY5 25,
    # NONE 26); 0x50f5 has no troop branch, so the troop comes back by 0x505c dead FALSE (reset + Troop::Enable), 0x505b
    # alive for its leader and every member, its hp (0x505d) and the revive's invincibility 34 (10 s). A troop wiped
    # again counts again in the death count; its Troop_Death AP stays once a room
    from kuf2 import combat, obf, status, troops
    from kuf2.packet import OBOOL_FALSE
    from test_rewards import pkt
    role, s, ts, body = wiped_deck_troop(cubic=500)
    t = s.data["battle"].troops[1]
    row = troops.troop_row(ts[0]["id"])
    price = game.troop_revive_cost(ts[0])
    idx = next(int(r["Index"]) for r in game.tables.sections("item_currency")["Troop_Resurrect"]
               if (r["TroopGrade"], r["TroopRarity"]) == (row["TroopGrade"], row["TroopRarity"]))
    assert price == game.items.currency("Resurrect", idx) > 0
    s.sent.clear()
    role.handlers[game.C2S_REVIVE_HERE](s, pkt(game.C2S_REVIVE_HERE, struct.pack("<H", 1) + obf.u32(0xFFFFFFFF)))
    protos = [w.proto for w in s.sent]
    assert game.S2C_REVIVE_HERE in protos and struct.unpack_from("<H", bytes(s.sent[protos.index(game.S2C_REVIVE_HERE)].buf))[0] == 0
    down = next(bytes(w.buf) for w in s.sent if w.proto == game.S2C_TROOP_DOWN)
    assert down == bytes(5) + bytes([OBOOL_FALSE]) + struct.pack("<H", 1)       # dead FALSE, troop 1
    live = next(bytes(w.buf) for w in s.sent if w.proto == combat.S2C_UNIT_LIVE)
    assert struct.unpack_from("<HH", live) == (1, len(t["units"]) + (1 if t.get("leader_max") else 0))
    assert all(hp > 0 for hp in t["units"]) and t.get("leader", 0) == t.get("leader_max", 0)
    assert s.data["char"]["cubic"] == 500 - price and s.data["revivals"] == 1
    assert any(w.proto == combat.S2C_STATUS_ADD and struct.unpack_from("<I", bytes(w.buf), 10)[0] == status.REVIVE_TROOP
               for w in s.sent)                                  # the revive's invincibility 34
    ap = ts[0]["ap"]
    status.forget(s, 1)                                         # its 10 s invincibility over
    for _ in range(2000):                                       # wiped again
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
        if not any(t["units"]) and not t.get("leader"):
            break
    assert s.data["troop_wipes"] == 2 and ts[0]["ap"] == ap


def test_a_troop_is_not_revived_where_the_content_allows_none_or_while_it_stands():
    # %Revival PVE_DAILY / WEEKLY IMPOSIBLE (the Unknown Corridor, the Dimensional Test: "troops cannot be resurrected",
    # census I8): 0x7412; a troop still standing: 0x7413; Cubic short: 0x6430 (the client refuses first, 0xd01b)
    from kuf2 import obf, world
    from test_rewards import pkt
    role, s, ts, _ = wiped_deck_troop(cubic=0)
    role.handlers[game.C2S_REVIVE_HERE](s, pkt(game.C2S_REVIVE_HERE, struct.pack("<H", 1) + obf.u32(0xFFFFFFFF)))
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf))[0] == world.CUBIC_SHORT and not any(s.data["battle"].troops[1]["units"])
    s.data["char"]["cubic"] = 500
    s.data["spot"] = 10540                                       # as if in the corridor
    role.handlers[game.C2S_REVIVE_HERE](s, pkt(game.C2S_REVIVE_HERE, struct.pack("<H", 1) + obf.u32(0xFFFFFFFF)))
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf))[0] == game.REVIVE_NOT_HERE
    s.data["spot"] = 10235
    s.data["battle"].troops[1]["units"][0] = 1                   # standing
    role.handlers[game.C2S_REVIVE_HERE](s, pkt(game.C2S_REVIVE_HERE, struct.pack("<H", 1) + obf.u32(0xFFFFFFFF)))
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf))[0] == game.REVIVE_NOT_NOW


def test_the_repeat_count_carries_over_the_days():
    # F4: Kedington 10320 on the tape twice: part 12 16:58 "Hero EXP 300%" 18,278 (first clear, before the ×2 event),
    # part 13 7:06 "Hero EXP 200%" 24,126 = 2 × 12,063 under the ×2 event of 2020-03-16 (a later day): 12,063 =
    # int(20,309 × 0.9 × 0.66), the repeat rate of one clear before. The count is every clear, not the day's (the
    # client keeps what 0x108f sends, with no day logic: the client dig)
    row = game.reward_row(10320, 0, 0)
    assert game.mission_exp({"level": 22}, 10320, 0, row, 0) == 18278
    assert game.mission_exp({"level": 22}, 10320, 0, row, 1) * 2 == 24126


def test_a_repeated_clear_pays_the_troops_their_full_exp():
    # F8: Kedington 10320's second clear (the tape part 13 7:12-7:14, under the ×2 event): the hero 24,126 = 2 ×
    # int(20,309 × 0.9 × 0.66) (the repeat penalty), the Lv 27 swordsman and bowman 2,382 = 2 × 1,191 each, the row's
    # full Troop_Exp (the first clear, part 12 17:00: 1,191 each), and Barracks Saved EXP 594 = 2 × floor(1,191 × 0.25):
    # the repeat penalty is the hero's only
    row = game.reward_row(10320, 0, 0)
    assert [game.troop_mission_exp(10320, 0, row, clears) for clears in (0, 1, 3)] == [1191] * 3

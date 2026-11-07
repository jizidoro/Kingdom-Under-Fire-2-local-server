"""Fort Valley Castle 10306: the director's table (kuf2/scenes/m10306.py) in a mission room, on both difficulties. The
times quoted are the original's, read frame by frame 2026-11-05: Normal on playthrough part 5, Hard on part 6 (the
table's docstring)."""
import random

import pytest

from kuf2 import director, game
from test_battle import NoSave, acts, down_all, mission_room, opened, pkt, read_prop, walk
from test_director import lines_shown, sync_body
from test_loot import hit_to_wipe

SPOT = 10306
NORMAL, HARD = 0, 1
JAGER, SANCHEZ, INFANTRY = 10200, 10000, 10001
MORTAR = 10308                                   # 리얼포병1: the player's share of F10502
GATE_1, GATE_2, LEFT_WALL, RIGHT_WALL, CASTLE_GATE = 10000, 10001, 20000, 20001, 20010
STAIRS = (20011, 20012, 20014)                   # the transparent walls at the stairs' feet
SCORPION, IRON_SCORPION = 30000, 30103           # 대규모스콜2 (106160 "Scorpion"), 대규모스콜1 (106030 "Iron Armour Scorpion")
YARD = (20200, 20400, 20500, 20600)              # with F20300: "inside the castle"
SHOCKWAVE, LEFT_MARK, RIGHT_MARK = "쇼크웨이브", "포병1,2-2차이동", "포병3,4-2차이동"
LINES = 40                                       # long enough for a chain of lines, short of the story's waits


def centre(name):
    b = director.bound(SPOT, name)
    return b["BoundCenterX"], b["BoundCenterZ"]


def area(name):
    return director.bound(SPOT, name)["EventBoundID"]


def said(s):
    return [line for _, _, line in lines_shown(s)]


def by(s, line):
    return next(uid for uid, _, ln in lines_shown(s) if ln == line)


def notices(s):
    return [tuple(i for i in a[2:6] if i != director.NO_TEXT) for a in acts(s, director.ACT_NOTICE_WINDOW)
            if a[1] == director.NOTICE_LEFT]


def marks(s):
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def marches(s, to):
    return {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == area(to)}


def troops_of(s, force):
    return [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == force]


def standing(s, force):
    return [u for u in troops_of(s, force) if u not in s.data.get("down", set())]


def mine(s):
    return [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)]


def wins(s):
    return sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)


class Clock:
    """The director's clock (lines take their time on it), moved by run_below: a room's waits come due in their order,
    and the tests can stop short of the story's longer ones."""
    now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(director, "time", c)
    return c


def run_below(s, secs):
    """Time goes on secs: what the room scheduled for then runs, in order."""
    stop = director.time.now + secs
    for _ in range(2000):
        due = [p for p in s.pending if p[0] <= stop]
        if not due:
            break
        first = min(due, key=lambda p: p[0])
        s.pending.remove(first)
        director.time.now = max(director.time.now, first[0])
        first[1]()
    director.time.now = stop


def run_all(s):
    run_below(s, 1000)


def room(difficulty=NORMAL):
    s = mission_room(SPOT, difficulty)
    s.state = NoSave()
    s.pending = [(director.time.now + d, fn) for d, fn in s.pending]     # due times, on the clock
    s.later = lambda delay, fn: s.pending.append((director.time.now + delay, fn))
    run_below(s, LINES)
    return s


def report(s, uid, name, secs=None):
    """The host reports troop uid inside that bound (0x50b0, game.troop_sync)."""
    x, z = centre(name)
    director.on_arrive(s, {uid: (x, 0, z)})
    run_below(s, LINES if secs is None else secs)


def fell(s, force, secs=None):
    down_all(s, standing(s, force))
    run_below(s, LINES if secs is None else secs)


def to_second(s):
    fell(s, 20000)
    walk(s, *centre("무적해제2"))
    run_below(s, LINES)


def to_yard(s):
    to_second(s)
    fell(s, 20100)
    if s.data["difficulty"] == HARD:
        fell(s, 20110)
    walk(s, *centre("예거 대사치기"))
    run_below(s, LINES)


def to_mortars(s):
    to_yard(s)
    fell(s, 20300)


def to_placing(s):
    to_mortars(s)
    for f in YARD:
        fell(s, f, 1)
    if s.data["difficulty"] == HARD:
        fell(s, 20700, 1)
    run_below(s, LINES)


def to_gate(s, secs=None):
    to_placing(s)
    report(s, MORTAR, LEFT_MARK)
    report(s, SCORPION, SHOCKWAVE, secs)


def to_reinforcements(s):
    to_gate(s)
    run_below(s, 60)                             # the timers of the sally


def test_the_bounds_the_table_names_exist():
    for name in ("무적해제2", "예거 대사치기", LEFT_MARK, RIGHT_MARK, SHOCKWAVE, "습격부대1목적지", "습격부대2목적지",
                 "스콜피온이동위치", "스콜피온강제이동", "오크 부대이동"):
        assert director.bound(SPOT, name) is not None, name


def test_the_opening_is_the_tapes_chain():
    # 3:20 Jager's opening over the camera, the panel as the HUD comes back (3:32.5), 1000, 2000, 1100
    s = room()
    assert said(s) == [10, 1000, 2000, 1100]
    assert by(s, 10) == JAGER and by(s, 1000) == INFANTRY and by(s, 2000) == 20001 and by(s, 1100) == SANCHEZ
    assert 20015 in opened(s)                    # the transparent wall just ahead of the start (the tape runs on)
    assert not {GATE_1, GATE_2, LEFT_WALL, RIGHT_WALL, CASTLE_GATE} & opened(s)


def test_the_start_holds_everything_the_lost_script_brought():
    # the generic plan handed 10308 and 10309 at the start; the tape's HUD gains its F3 at 8:41 only
    s = room()
    assert mine(s) == [] and s.data["plan"]["hand"] == ()
    assert not {10308, 10309, 10310, 10311, 30109, 10324, SCORPION, IRON_SCORPION} & set(s.data["zone_troops"])
    assert not troops_of(s, 20100) and not troops_of(s, 20110) and not troops_of(s, 20300)
    assert set(troops_of(s, 20000)) == {20000, 20001, 20002} and set(troops_of(s, 20200)) == {30113, 30115}


def test_sanchez_and_jagers_armies_cannot_be_hurt_and_deal_no_damage():
    # the walkthrough's "*AI Script Notes*: Normal Attacks Deal 0 Dmg! ... Sanchez & Jager's Army is Immune to dmg"
    s = room()
    assert director.harmless(SPOT) == {10000, 10200}
    assert {a[2] for a in acts(s, 0xea9c) if a[3] == 1} == {10000, 10001, 10200, 10203, 10209}
    assert all(s.data["battle"].troops[u]["untouchable"] for u in (10000, 10001, 10200, 10203, 10209))


def test_the_first_gate_waits_for_the_first_fight():
    s = room()
    walk(s, *centre("무적해제2"))                # past where the hero can stand: only the fall opens it
    run_below(s, LINES)
    assert GATE_1 not in opened(s) and 1001 not in said(s)
    fell(s, 20000)
    assert GATE_1 in opened(s)
    assert said(s)[4:] == [1001, 1002, 2011]     # remembered: it plays as the gate opens (4:36, 4:42, 4:48)


def test_the_second_fight_comes_as_the_hero_is_through():
    s = room()
    fell(s, 20000)
    assert not troops_of(s, 20100) and 1001 not in said(s)
    walk(s, *centre("무적해제2"))
    run_below(s, LINES)
    assert said(s)[4:] == [1001, 1002, 2011]
    assert by(s, 1002) == 10102 and by(s, 2011) == 20106
    assert len(troops_of(s, 20100)) == 7 and {10100, 10102} <= set(s.data["zone_troops"])
    assert SANCHEZ in marches(s, "무적해제2")     # the allies go on by themselves


def test_normal_has_no_ukuron_and_the_second_gate_opens_with_the_fight():
    s = room()
    to_second(s)
    fell(s, 20100)
    assert GATE_2 in opened(s) and not troops_of(s, 20110)
    assert not {1003, 2005, 1013, 2006, 2008} & set(said(s))


def test_hard_has_ukuron_at_the_second_gate():
    # part 6: 9:40 "Ogres!", 9:46 "I'll crush you all!", 10:00 "Ugh! Who are you?", 10:02 "The Ogre has fallen!"
    s = room(HARD)
    to_second(s)
    fell(s, 20100)
    assert GATE_2 not in opened(s) and troops_of(s, 20110) == [20105]
    assert said(s)[-2:] == [1003, 2005] and by(s, 2005) == 20105
    director.on_hp(s, 20105, 20, 100)
    run_below(s, LINES)
    assert said(s)[-1] == 2006
    fell(s, 20110)
    assert GATE_2 in opened(s) and said(s)[-1] == 1013


def test_ukuron_crosses_the_shut_gate_to_the_ogres_stand():
    # his row stands 369 past gate 10001, on the yard's side: left to himself he went for the allies in the yard, where
    # the hero cannot follow (live 2026-11-06 08:56). The map names his goal, west of the gate; the tape has him at the
    # hero 8 s after "Ogres!" with the gate still shut (H 9:48), so a plain march, which the gate blocks, will not do
    s = room(HARD)
    to_second(s)
    fell(s, 20100)
    assert centre("오우거목적지")[0] < 53606 < s.data["zone_troops"][20105]["PosX"]
    assert [(a[2], a[3]) for a in acts(s, director.ACT_MOVE_STRAIGHT)] == [(20105, area("오우거목적지"))]


def test_jagers_bound_brings_the_yard():
    s = room()
    to_second(s)
    fell(s, 20100)
    assert not troops_of(s, 20300) and 1004 not in said(s)
    walk(s, *centre("예거 대사치기"))
    run_below(s, LINES)
    assert said(s)[-3:] == [1004, 1005, 1006]    # 7:28, 7:34, 7:38; part 6 10:14, 10:20, 10:24: one chain
    assert by(s, 1005) == JAGER
    for force, n in ((20300, 4), (20400, 3), (20500, 4)):
        assert len(troops_of(s, force)) == n
    assert {10201, 10204, 10206, 10202, 10205, 10207, 10208} <= set(s.data["zone_troops"])
    assert not {30109, 10308, 10324} & set(s.data["zone_troops"])    # the mortars are not here yet (1009)


def test_hard_asks_after_ukuron_in_the_yard():
    s = room(HARD)
    to_yard(s)
    assert said(s)[-4:] == [1004, 1005, 1006, 2008]         # part 6 10:32


def test_the_left_wall_falls_with_the_yards_first_force():
    # part 5: the yard's Ogre 8:20, the wall 8:30 (2003), 1007 8:32, 1009 8:36
    s = room()
    to_yard(s)
    assert LEFT_WALL not in opened(s) and not troops_of(s, 20600)
    fell(s, 20300)
    assert LEFT_WALL in opened(s) and len(troops_of(s, 20600)) == 5
    assert said(s)[-3:] == [2003, 1007, 1009]
    assert by(s, 2003) == 20600 and by(s, 1007) == JAGER and by(s, 1009) == 10309
    assert 20600 in marches(s, "습격부대1목적지") and {JAGER, 10201} <= marches(s, "습격부대1목적지")


def test_normal_keeps_the_right_wall():
    # part 5's log 8:50: 2003, 1007, 1009, no 1008; F20700 waits outside for ever, and nothing waits on it
    s = room()
    to_mortars(s)
    run_all(s)
    assert RIGHT_WALL not in opened(s) and 20013 not in opened(s) and not troops_of(s, 20700)
    assert 1008 not in said(s) and 2004 not in said(s)


def test_the_mortars_arrive_and_one_is_the_players():
    s = room()
    to_mortars(s)
    assert {10308, 10309, 10310, 10311, 30109, 30110, 30111, 30112} <= set(s.data["zone_troops"])
    assert not {10324, 10325, 10326, 10327} & set(s.data["zone_troops"])    # the wall's staging troops stay out
    assert mine(s) == [MORTAR] and s.data["plan"]["hand"] == (MORTAR,)


def test_hard_loses_the_right_wall_too():
    # part 6: 1007 11:30, 1008 11:46, 1009 11:52, 2004 11:56
    s = room(HARD)
    to_yard(s)
    fell(s, 20300, 15)                           # 2003 and 1007 said, the 10 s after them not over
    assert RIGHT_WALL not in opened(s) and 1009 not in said(s) and mine(s) == []
    run_below(s, LINES)
    assert {RIGHT_WALL, 20013} <= opened(s) and len(troops_of(s, 20700)) == 6
    assert said(s)[-5:] == [2003, 1007, 1008, 1009, 2004]
    assert mine(s) == [MORTAR]
    assert 20700 in marches(s, "습격부대2목적지") and 10202 in marches(s, "습격부대2목적지")


@pytest.mark.parametrize("order", [YARD, tuple(reversed(YARD))])
def test_inside_the_castle_is_clear_in_any_order(order):
    s = room()
    to_mortars(s)
    for f in order[:-1]:
        fell(s, f)
        assert 1020 not in said(s)
    fell(s, order[-1])
    assert said(s)[-4:] == [1020, 1010, 2002, 1011]         # 9:16, 9:24, 9:26, 9:36
    assert by(s, 1010) == INFANTRY and by(s, 2002) == 30006  # the Orc Commander (leader 106030)
    assert notices(s)[-1] == (10121, 10120)
    assert len(troops_of(s, 30000)) == 12 and CASTLE_GATE not in opened(s)
    assert (area(LEFT_MARK), 1) in marks(s) and (area(RIGHT_MARK), 1) in marks(s)
    assert set(STAIRS) <= opened(s)              # "up the stairs to the battlements"


def test_hard_waits_for_the_right_walls_raiders_too():
    s = room(HARD)
    to_mortars(s)
    for f in YARD:
        fell(s, f)
    assert 1020 not in said(s)
    fell(s, 20700)
    assert said(s)[-4:] == [1020, 1010, 2002, 1011]


def test_an_army_early_at_the_castle_does_not_hurry_the_story():
    # F20200 stands from the start behind the second gate: fallen to Jager's side before the hero is there, it decides
    # nothing yet, and the end of the yard still comes
    s = room()
    fell(s, 20200)
    to_yard(s)
    fell(s, 20300)
    assert 1020 not in said(s)
    for f in (20400, 20500, 20600):
        fell(s, f)
    assert 1020 in said(s)


@pytest.mark.parametrize("mark", [LEFT_MARK, RIGHT_MARK])
def test_the_players_mortar_on_the_battlements_starts_the_scorpion(mark):
    # part 5: 1017, then 1031 and the notice at 10:18; the troop is the player's to move (Manual Mode, 9:40-10:00)
    s = room()
    to_placing(s)
    assert 1017 not in said(s) and SCORPION not in marches(s, SHOCKWAVE)
    report(s, MORTAR, mark)
    assert said(s)[-2:] == [1017, 1031] and by(s, 1017) == 10309 and by(s, 1031) == JAGER
    assert notices(s)[-1] == (10171, 10170)
    assert (area(LEFT_MARK), 0) in marks(s) and (area(RIGHT_MARK), 0) in marks(s)
    assert SCORPION in marches(s, SHOCKWAVE)
    assert 10309 in marches(s, LEFT_MARK) and {10310, 10311} <= marches(s, RIGHT_MARK)
    report(s, MORTAR, LEFT_MARK if mark == RIGHT_MARK else RIGHT_MARK)
    assert said(s).count(1017) == 1              # the other mark says nothing


def test_the_hosts_report_of_the_players_mortar_is_what_places_it():
    # the real way in: 0x50b0, game.troop_sync; a report of the hero there is not the mortar
    s = room()
    to_placing(s)
    role = game.make(NoSave(), 0)
    sync = lambda recs: role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body(recs)))
    x, z = centre(LEFT_MARK)
    sync([(0, int(x), 0, int(z))])
    run_below(s, 5)
    assert 1017 not in said(s)
    sync([(MORTAR, int(x), 0, int(z))])
    run_below(s, 20)
    assert said(s)[-2:] == [1017, 1031]


def test_a_mortar_left_below_does_not_stop_the_story():
    # ours [I]: "Put them in position before the gate breaks": the other mortars go up by themselves after a minute
    s = room()
    to_placing(s)
    assert not marches(s, LEFT_MARK)
    run_below(s, 61)
    assert 10309 in marches(s, LEFT_MARK) and 1017 not in said(s)
    report(s, 10309, LEFT_MARK)
    assert said(s)[-2:] == [1017, 1031]


def test_the_scorpion_at_the_gate_breaks_it():
    s = room()
    to_placing(s)
    report(s, MORTAR, LEFT_MARK)
    assert CASTLE_GATE not in opened(s)
    report(s, SCORPION, SHOCKWAVE, 10)
    assert CASTLE_GATE in opened(s) and said(s)[-1] == 1012 and by(s, 1012) == JAGER      # 10:36-10:40
    assert {JAGER, SANCHEZ, 10100, 10201, 10202, 10207} <= marches(s, "스콜피온강제이동")  # out over the bridge
    assert {30001, 30006} <= marches(s, "오크 부대이동")


def test_a_scorpion_killed_on_the_way_still_lets_the_army_through():
    # "We must kill it before it reaches the castle gate!": the mortars can; the army behind it must come all the same
    s = room()
    to_placing(s)
    report(s, MORTAR, LEFT_MARK)
    down_all(s, [SCORPION])
    run_below(s, LINES)
    assert CASTLE_GATE in opened(s) and said(s).count(1012) == 1


def test_the_gate_breaks_whatever_happens_to_the_mortars_and_the_scorpion():
    # ours [I]: no arrival reported (every mortar dead, the Scorpion stuck): the gate must not shut the room
    s = room()
    to_placing(s)
    assert CASTLE_GATE not in opened(s)
    run_below(s, 151)
    assert CASTLE_GATE in opened(s) and said(s).count(1012) == 1


def test_a_scorpion_held_up_on_its_way_does_not_shut_the_room():
    # ours [I]: its march ends in a shut gate; a client that never brings it inside the bound must not hang the story
    s = room()
    to_placing(s)
    report(s, MORTAR, LEFT_MARK, 20)
    assert CASTLE_GATE not in opened(s)
    run_below(s, LINES)
    assert CASTLE_GATE in opened(s) and said(s).count(1012) == 1


def test_the_gate_breaks_once():
    s = room()
    to_gate(s)
    down_all(s, [SCORPION])
    report(s, 30001, SHOCKWAVE)
    run_all(s)
    assert said(s).count(1012) == 1


def test_contact_with_the_army_and_the_reinforcements():
    # part 5: 1012 10:40, 1023 11:08 (the army met), 1027 11:46 with the boss's bar at 11:54, 1018 12:16;
    # part 6: 1023 13:54, 1027 14:38, 1018 15:04: the same 38-44 s on both, whatever falls: a clock, not a count
    s = room()
    to_gate(s, 10)
    assert not troops_of(s, 30100)
    director.on_engage(s, 0, 30002)
    run_below(s, 10)
    assert said(s)[-1] == 1023 and not troops_of(s, 30100)
    run_below(s, 33)
    assert said(s)[-1] == 1027 and len(troops_of(s, 30100)) == 11
    assert [IRON_SCORPION, 1] in [a[1:3] for a in acts(s, game.ACT_BOSS_STATUS)]
    assert IRON_SCORPION in marches(s, "스콜피온이동위치") and 30100 in marches(s, "오크 부대이동")
    run_below(s, 35)
    assert said(s)[-1] == 1018 and 1032 not in said(s)      # part 5's log 12:22: no 1032


def test_hard_tells_the_hero_to_stop_the_shock_waves():
    s = room(HARD)
    to_reinforcements(s)
    run_all(s)
    assert said(s)[-2:] == [1018, 1032]          # part 6 15:04, 15:08


def test_no_contact_reported_still_brings_the_reinforcements():
    # ours [I]: the engage report is melee only (a Gunslinger's volleys send none): 28 s after 1012 as on the tape
    s = room()
    to_gate(s, 10)
    assert 1023 not in said(s)
    run_below(s, 30)
    assert said(s)[-1] == 1023
    run_below(s, 40)
    assert troops_of(s, 30100)


def real_kill(s, uid):
    """A troop's fall the way a fight reports it: the client's hit wipes it (game's troop_down: the quest counts, then
    the mission's rule)."""
    hit_to_wipe(game.make(NoSave(), 0), s, uid)


@pytest.mark.parametrize("difficulty", [NORMAL, HARD])
def test_the_iron_scorpion_counts_for_defeat_scorpion_and_nothing_else_does(difficulty):
    # 1010203 NPNameKill 5030: the troop 106030 (20106030 on Hard), not its Orc Commander namesake (leader 106030 =
    # name 2000) nor the first Scorpion (106160 = name 20003)
    s = room(difficulty)
    active = s.data["char"].setdefault("quests", {"active": {}, "done": []})["active"]
    active["1010203"] = {"counts": [0] * 5}
    to_reinforcements(s)
    run_all(s)
    for uid in (30006, SCORPION, 30108):         # the two led by 106030, the plain Scorpion
        if uid not in s.data.get("down", set()):
            real_kill(s, uid)
    assert active["1010203"]["counts"][0] == 0
    real_kill(s, IRON_SCORPION)
    assert "1010203" in s.data["char"]["quests"]["done"] or active["1010203"]["counts"][0] == 1


def test_the_rest_after_the_iron_scorpion_is_the_tapes_1028():
    s = room()
    to_reinforcements(s)
    run_all(s)
    down_all(s, [IRON_SCORPION])
    run_below(s, LINES)
    assert said(s)[-1] == 1028 and by(s, 1028) == JAGER and wins(s) == 0    # part 5: 15:14, the reds gone 15:22


def end(s):
    for f in (30000, 30100):
        fell(s, f)
    run_all(s)


@pytest.mark.parametrize("difficulty", [NORMAL, HARD])
def test_the_win_is_the_last_of_the_armies(difficulty):
    s = room(difficulty)
    to_reinforcements(s)
    run_all(s)
    fell(s, 30100)
    assert wins(s) == 0 and not s.data.get("mission_won")
    fell(s, 30000)
    run_all(s)
    assert wins(s) == 1
    assert said(s)[-2:] == [1015, 1016]          # 15:22, 15:30
    assert [620, 1] in [a[2:4] for a in acts(s, game.ACT_SITUATION_DONE)]


def test_the_win_needs_the_iron_scorpion_even_with_the_army_gone_first():
    s = room()
    to_gate(s)
    fell(s, 30000)                               # all of the first army, before the reinforcements' clock
    assert not s.data.get("mission_won")
    run_all(s)
    assert troops_of(s, 30100) and not s.data.get("mission_won")
    fell(s, 30100)
    run_all(s)
    assert wins(s) == 1


@pytest.mark.parametrize("difficulty,quest_id,moves", [(NORMAL, "1010202", True), (HARD, "1010202", True),
                                                       (HARD, "9900228", True), (NORMAL, "9900228", False)])
def test_the_clear_counts_for_the_quests(difficulty, quest_id, moves):
    # 1010202 MissionLevelClear ANY at 10306; 9900228 HARD
    s = room(difficulty)
    c = s.data["char"]
    q = c.setdefault("quests", {"active": {}, "done": []})
    q["active"][quest_id] = {"counts": [0] * 5}
    to_reinforcements(s)
    end(s)
    assert wins(s) == 1
    done = quest_id in q["done"] or q["active"].get(quest_id, {}).get("counts", [0])[0] == 1
    assert done is moves


def reachable(s, t):
    """Whether the hero can stand next to troop t: its side of the barrier that shuts it off is open."""
    force = t.get("ForceNum")
    gates = {20100: GATE_1, 20110: GATE_1, 20200: GATE_2, 20300: GATE_2, 20400: GATE_2, 20500: GATE_2,
             20600: LEFT_WALL, 20700: RIGHT_WALL, 30000: CASTLE_GATE, 30100: CASTLE_GATE}
    return force not in gates or gates[force] in opened(s)


@pytest.mark.parametrize("difficulty", [NORMAL, HARD])
@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("pace", [3, 200])       # the player's kills between the story's clocks, or after them
def test_no_order_of_falls_leaves_the_room_unwinnable(difficulty, seed, pace):
    # any standing hostile the player can get to, in any order, with the player never moving his mortar; the room
    # always wins, and the Iron Scorpion is always in it. Nothing the story needs may wait behind a shut barrier.
    rng = random.Random(seed)
    s = room(difficulty)
    places = ["무적해제2", "예거 대사치기"]
    for _ in range(2000):
        if s.data.get("mission_won"):
            break
        for name in places:
            walk(s, *centre(name))
        run_below(s, pace)
        hostile = [u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", set())]
        open_to = [u for u in hostile if reachable(s, s.data["zone_troops"][u])]
        if open_to:
            down_all(s, [rng.choice(open_to)])
        elif not s.pending:
            break
    run_all(s)
    assert wins(s) == 1, (said(s)[-5:], [w[0].get("ForceNum") for w in s.data.get("waves", ())])
    assert IRON_SCORPION in s.data["down"]


@pytest.mark.parametrize("difficulty", [NORMAL, HARD])
def test_the_hero_coming_near_opens_nothing_of_the_story(difficulty):
    # the generic barrier rule opens a prop as the hero comes near: every one here is the story's
    s = room(difficulty)
    for prop in (GATE_1, GATE_2, LEFT_WALL, RIGHT_WALL, CASTLE_GATE, *STAIRS, 20013):
        p = game.zone_prop(SPOT, prop)
        walk(s, p["PosX"], p["PosZ"])
    assert not {GATE_1, GATE_2, LEFT_WALL, RIGHT_WALL, CASTLE_GATE, 20013, *STAIRS} & opened(s)


def test_a_table_win_does_not_wait_for_held_forces_of_the_other_difficulty():
    # Normal never wakes F20110 / F20700: they stay in the held waves, and the room still ends
    s = room()
    to_reinforcements(s)
    end(s)
    assert wins(s) == 1
    assert {w[0].get("ForceNum") for w in s.data["waves"]} == {20110, 20700}


def test_the_rooms_prop_list_keeps_the_wall_the_start_opened():
    """Live 2026-11-06 06:51:22: the start step opened 20015 inside spawn_zone_troops, and the room's whole list, sent 50 ms
    later, wrote it back hidden in its off state; a hidden prop keeps its collision (game.switch_on), so the hero stood at
    z 4801 against "Cannot move to that area." and the mission could not be started. mission_room stops before that list."""
    s = mission_room(10306)
    assert 20015 in opened(s)
    game.send_zone_props(s, 10306, s.data["char"])
    b = bytes(s.sent[-1].buf)
    recs = {r["id"]: r for r in (read_prop(b[2 + 23 * i:]) for i in range(int.from_bytes(b[:2], "little")))}
    assert recs[20015]["shown"] and recs[20015]["state"] == game.PROP_OPEN
    assert not recs[20011]["shown"] and recs[20011]["state"] == game.PROP_OFF      # the stairs' walls stay for 1011

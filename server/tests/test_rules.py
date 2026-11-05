"""Mission rules (ROADMAP Next 3; owner 2026-09-29 21:20: Q16 the Unknown Corridor, Q33 the Treasure Goblin Nest; Q2 no
defeat): the corridor's day boss within the 5:00 clock, graded by the time left; the nest's three real goblins and its
full clock from the door; the day limits (0x10b2 / 0x10b3, the 0x3f48 refusal) and their 07:00 UTC day.
Reads the installed game's tables and zone files. Run: py -m pytest -q server/tests"""
import datetime
import struct

import pytest

from kuf2 import director, game, items, loot, obf, rules, world, zone
from kuf2.packet import Reader
from test_battle import NoSave, acts, mission_room, read_prop
from conftest import run_pending

UTC = datetime.timezone.utc
DAY_BOSSES = {10540: 190040, 10541: 190240, 10542: 190080, 10543: 190110, 10544: 190270, 10545: 190150, 10546: 190190}


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def room(spot, difficulty=0, level=30):
    s = mission_room(spot, difficulty)
    s.data["char"]["level"] = level
    return s


def targets(s):
    return [u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", set())]


def window(s):
    """The 0x5044 record of the room's victory window."""
    won = [w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE]
    assert len(won) == 1
    return bytes(won[0].buf)[8:]


def paid(rec):
    """(grade, hero exp, cards) of a 0x5044 record."""
    return game.GRADES[rec[0x284]], struct.unpack_from("<Q", rec, 0x17)[0], obf.dec_u16(rec[0x29f:0x2a1])


def clock(s):
    return [a[-1] for a in acts(s, rules.ACT_SITUATION_TIME)]


def later(s, secs):
    """secs pass on the room's clock, then its next tick."""
    s.data["clock"]["t0"] -= secs
    rules.tick(s)


@pytest.mark.parametrize("spot", sorted(DAY_BOSSES))
def test_each_corridor_is_won_by_its_day_boss_alone(spot):
    # every corridor troop has EXP 0 (the exp rule counted none, proof audit C); the day's boss is its only target
    # (10545's juggernaut stands inactive: the fallback brings it at the start)
    s = room(spot)
    boss = targets(s)
    assert [s.data["zone_troops"][u]["TroopTableID"] for u in boss] == [DAY_BOSSES[spot]]
    assert acts(s, game.ACT_BOSS_STATUS)[-1] == [game.ACT_BOSS_STATUS, boss[0], 1]           # its vitality bar
    for u in [u for u in s.data["zone_troops"] if u not in boss]:
        game.mission_troop_down(s, NoSave(), u)
    assert not s.data.get("mission_won")                  # the others decide nothing
    game.mission_troop_down(s, NoSave(), boss[0])
    assert s.data.get("mission_won") and paid(window(s))[0] == "S"


def test_the_harder_corridor_brings_its_other_juggernaut_after_the_first():
    # 10545 Hard: 노말보스 10000 (F14000), then 하드보스2 10012 (F15000); the Hell-only 헬보스1 / 2 stay out
    s = room(10545, difficulty=1)
    assert targets(s) == [10000]
    game.mission_troop_down(s, NoSave(), 10000)
    assert targets(s) == [10012] and not s.data.get("mission_won")
    game.mission_troop_down(s, NoSave(), 10012)
    assert s.data.get("mission_won")


def test_the_corridor_clock_counts_down_in_its_panel():
    s = room(10540)
    # missiontext 1_angelshalo: 10210 "Timer", 10200 "Dimensional Exit disappears in", the start notice 11000 / 11010
    assert [game.ACT_SITUATION_GROUP, 0xff, 10210] in acts(s, game.ACT_SITUATION_GROUP)
    assert acts(s, rules.ACT_SITUATION_TIME) == [[rules.ACT_SITUATION_TIME, 0xff, 10210, 10200, 300]]
    notice = acts(s, 0xc8f0)
    assert len(notice) == 1 and notice[0][2:4] == [11000, 11010]
    later(s, 42.5)
    assert clock(s)[-1] == 258                              # 257.5 s left shows 00:04:18
    assert s.pending and 0 < s.pending[-1][0] <= 1.1        # the next tick when the second turns
    later(s, 300)
    assert clock(s)[-1] == 0 and s.data["clock"]["out"]
    n = len(s.sent)
    rules.tick(s)
    assert len(s.sent) == n                                 # stopped at 00:00:00
    assert not s.data.get("mission_won") and targets(s)     # no defeat (Q2): the boss stands


@pytest.mark.parametrize("left, grade", [      # a quarter second each side of the bands (the test's own time passes)
    (299, "S"), (150.25, "S"), (149.75, "A"), (75.25, "A"), (74.75, "B"), (60.25, "B"), (59.75, "C"), (30.25, "C"),
    (29.75, "D"), (15.25, "D"), (1, "D"),
])
def test_the_corridor_grade_is_the_time_left_when_the_boss_falls(left, grade):
    s = room(10540)
    s.data["clock"]["t0"] -= rules.CORRIDOR_S - left
    game.mission_troop_down(s, NoSave(), targets(s)[0])
    g, exp, cards = paid(window(s))
    assert g == grade
    if grade in "SAB":                                    # x3 / x2 / x1 (mission_reward 10540 has one item listed)
        assert exp > 0 and cards == 1
    else:                                                 # C / D: no mission_reward row, nothing
        assert exp == 0 and cards == 0
    assert s.data["char"]["day_limits"]["counts"] == {"150": 1}      # the day's one clear
    assert [game.ACT_SITUATION_DONE, 0xff, 10120, 1] in acts(s, game.ACT_SITUATION_DONE)
    assert acts(s, 0xc8f0)[-1][2:4] == [13100, 13110]     # "Defeated the Dimension Keeper before ..."
    assert rules.time_left(s) == pytest.approx(left, abs=1)          # the clock stopped


def test_a_corridor_boss_killed_after_the_clock_pays_nothing_and_keeps_the_day():
    s = room(10540)
    later(s, 305)
    game.mission_troop_down(s, NoSave(), targets(s)[0])
    assert paid(window(s)) == ("D", 0, 0)
    assert s.data["char"].get("day_limits", {}).get("counts", {}) == {}      # the original failed: no clear
    assert [game.ACT_SITUATION_DONE, 0xff, 10120, 1] not in acts(s, game.ACT_SITUATION_DONE)


def open_nest(s, prop=10003):
    role = game.make(NoSave(), 0)
    role.handlers[game.C2S_PROP_CAST](s, pkt(game.C2S_PROP_CAST, struct.pack("<H", 0) + obf.u32(prop)))
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(prop)))
    return s.data["nest"]["real"]


def test_the_nest_trial_opens_at_its_door_and_its_three_real_goblins_win_with_the_full_clock():
    s = room(10237)
    troops = s.data["zone_troops"]
    assert len(troops) == 373 and not targets(s)          # the bag goblins are the fakes; the box goblins wait
    # missiontext 1_goblindungeon: 10000 "Golden Goblin Nest", 20000 "Goblin Nest Entrance" / 20010 "Open the door ..."
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, 0xff, 10000]]
    assert acts(s, game.ACT_SITUATION_LINE) == [[game.ACT_SITUATION_LINE, 0xff, 20000, 20010]]
    assert not clock(s)
    real = open_nest(s)
    assert len(real) == 3 and targets(s) == real
    assert {troops[u]["TroopTableID"] for u in real} == {rules.BOX_GOBLIN}
    assert len({troops[u]["ForceNum"] for u in real}) == 1                 # one of the six placements
    assert acts(s, rules.ACT_SITUATION_TIME) == [[rules.ACT_SITUATION_TIME, 0xff, 10110, 10100, 300]]
    assert [game.ACT_SITUATION_DONE, 0xff, 20010, 1] in acts(s, game.ACT_SITUATION_DONE)
    assert [game.ACT_SITUATION_LINE, 0xff, 21000, 21010] in acts(s, game.ACT_SITUATION_LINE)
    opened = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_PROP_LIST]
    assert len(opened) == 1 and obf.dec_u32(opened[0][5:9]) == 10004        # the other entrance prop goes too
    pointed = len(acts(s, game.ACT_DIRECTION_TO_TROOP))
    for u in real:
        game.mission_troop_down(s, NoSave(), u)
    assert not s.data.get("mission_won")                  # "the mission always runs the full 5 min"
    assert len(acts(s, game.ACT_DIRECTION_TO_TROOP)) == pointed             # the pointer never gave them away
    assert [game.ACT_SITUATION_DONE, 0xff, 21010, 1] in acts(s, game.ACT_SITUATION_DONE)
    later(s, 299.5)
    assert not s.data.get("mission_won")
    later(s, 0.5)
    assert acts(s, 0xc8f0)[-1][2:4] == [23000, 23010]     # "Goblin Trial Complete", "The Golden Goblin Trial ..."
    g, exp, cards = paid(window(s))
    assert g == "S" and cards == 1                        # %Mission_Grade 10237 rates 0.001; one card (the footage)
    assert s.data["cards"]["category"] == 916811          # of the Golden setting's category (mission_reward S row)
    assert s.data["char"]["day_limits"]["counts"] == {"410": 1}


def test_the_real_goblins_light_up_with_two_minutes_left():
    s = room(10237)
    real = open_nest(s)
    game.mission_troop_down(s, NoSave(), real[0])
    later(s, 179)
    assert not acts(s, rules.ACT_HIGHLIGHT_TROOP)
    later(s, 1.5)
    assert acts(s, rules.ACT_HIGHLIGHT_TROOP) == [[rules.ACT_HIGHLIGHT_TROOP, u, 0, 1, 0] for u in real[1:]]
    assert not any(s.data["zone_troops"][u].get("Hidden") for u in real[1:])
    later(s, 1)
    assert len(acts(s, rules.ACT_HIGHLIGHT_TROOP)) == 2                    # once


def test_a_real_goblin_falling_after_the_clock_wins_the_nest_with_nothing():
    s = room(10237)
    real = open_nest(s, prop=10004)                       # the hero-only switch beside the door opens it as well
    assert obf.dec_u32(bytes([w for w in s.sent if w.proto == game.S2C_PROP_LIST][0].buf)[5:9]) == 10003
    for u in real[:2]:
        game.mission_troop_down(s, NoSave(), u)
    later(s, 301)
    assert not s.data.get("mission_won")                  # the trial failed; no defeat (Q2)
    game.mission_troop_down(s, NoSave(), real[2])
    assert paid(window(s)) == ("D", 0, 0) and "day_limits" not in s.data["char"]


@pytest.mark.parametrize("difficulty, texts", [(1, (10010, 20020, 21020)), (2, (10020, 20030, 21030))])
def test_the_nest_setting_is_the_entry_difficulty(difficulty, texts):
    s = room(10237, difficulty=difficulty)                # Vision / Enchanter (mission_reward 916911 / 917011)
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, 0xff, texts[0]]]
    assert acts(s, game.ACT_SITUATION_LINE) == [[game.ACT_SITUATION_LINE, 0xff, 20000, texts[1]]]
    open_nest(s)
    assert [game.ACT_SITUATION_LINE, 0xff, 21000, texts[2]] in acts(s, game.ACT_SITUATION_LINE)


class Session:
    def __init__(self, c):
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}}
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def char():
    return {"id": 1, "class": 0, "level": 30, "exp": 0, "spot": world.START_SPOT, "pos": list(world.START_POS),
            "quests": {"active": {}, "done": []}}


def day_map(w):
    """{group: used} of a 0x10b3 body (0x140675ba0)."""
    b = bytes(w.buf)
    n = struct.unpack_from("<H", b)[0]
    assert len(b) == 2 + 13 * n
    return {struct.unpack_from("<i", b, 2 + 13 * i)[0]: b[2 + 13 * i + 12] for i in range(n)}


def enter(role, s, spot, difficulty=0):
    s.sent.clear()
    s.data.pop("battle_spot", None)                   # back from the last one: entered from the town
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes([difficulty, 0])))
    reply = next(w for w in s.sent if w.proto == world.S2C_GAME_SERVER)
    return struct.unpack_from("<H", bytes(reply.buf))[0]


def with_troop(c):
    """c with one troop in its main deck: the corridor and the subjugations need one organised (Min_Limit_Troop 1)."""
    from kuf2 import troops
    t, _ = troops.grant(c, 1)
    troops.lineup(c)["slots"][1] = t["uid"]
    return c


def test_the_day_limits_count_a_corridor_clear_and_refuse_the_next_corridor():
    c = with_troop(char())
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    w = Session(c)
    role.handlers[rules.C2S_DAY_LIMITS](w, pkt(rules.C2S_DAY_LIMITS, b""))
    assert w.sent[-1].proto == rules.S2C_DAY_LIMITS and day_map(w.sent[-1]) == {}
    assert enter(role, w, 10540) == 0 and enter(role, w, 10540, 2) == 0      # quitting keeps the entry (a clear counts)
    s = room(10541)
    s.data["char"] = s.data["account"]["characters"][0] = c
    game.mission_troop_down(s, NoSave(), targets(s)[0])
    role.handlers[rules.C2S_DAY_LIMITS](w, pkt(rules.C2S_DAY_LIMITS, b""))
    assert day_map(w.sent[-1]) == {150: 1}               # the seven corridors share group 150: one clear a day
    for spot, difficulty in ((10546, 0), (10540, 1), (10543, 2)):
        assert enter(role, w, spot, difficulty) == rules.DAY_LIMIT_REFUSED      # text 53345, the client's own
        assert [x.proto for x in w.sent] == [world.S2C_GAME_SERVER]
    assert enter(role, w, 10237) == 0                     # another group


def test_a_town_entry_sends_the_day_limits_again():
    c = char()
    rules.count_day(c, 10237, 0, rules.CLEAR)
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    w = Session(c)
    role.handlers[world.C2S_ENTER_TOWN](w, pkt(world.C2S_ENTER_TOWN, obf.u32(world.START_SPOT)))
    assert day_map(next(x for x in w.sent if x.proto == rules.S2C_DAY_LIMITS)) == {410: 1}


def test_a_subjugation_counts_its_entries_three_a_day():
    # PVE_REPEAT 10327 Grey Wood: group 110, Mission_Enter 3
    c = with_troop(char())
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    w = Session(c)
    assert [enter(role, w, 10327) for _ in range(4)] == [0, 0, 0, rules.DAY_LIMIT_REFUSED]
    assert c["day_limits"]["counts"] == {"110": 3}


def test_the_day_turns_at_seven_utc():
    c = {}
    before = datetime.datetime(2026, 9, 29, 6, 59, 30, tzinfo=UTC).timestamp()
    rules.count_day(c, 10540, 0, rules.CLEAR, now=before)
    assert c["day_limits"] == {"day": "2026-09-28", "counts": {"150": 1}}
    assert rules.day_refusal(c, 10542, 1, now=before) == rules.DAY_LIMIT_REFUSED
    assert rules.day_refusal(c, 10542, 1, now=before + 30) is None           # 07:00 UTC: a new day
    assert c["day_limits"] == {"day": "2026-09-29", "counts": {}}
    assert day_map(rules.day_limits_packet(c, now=before + 30)) == {}
    rules.count_day(c, 10540, 0, rules.ENTER, now=before + 30)              # a clear group counts no entry
    assert rules.day_refusal(c, 10540, 0, now=before + 30) is None


# --- the Dimensional Test 10238 (PVE_WEEKLY; OFFICIAL-NOTES "Per-mission rules", DESIGNER-NOTES F3) ---

def storms(s):
    """The storm props a 0x50d1 showed / hid: [(prop id, shown)]."""
    out = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_PROP_LIST and struct.unpack_from("<H", b)[0] == 1:
            p = read_prop(b[2:])
            out.append((p["id"], p["shown"]))
    return out


def next_level(s):
    """The pending storm opens (its 20 s after the last level fell): the level's troops."""
    assert [d for d, _ in s.pending] == [rules.STORM_S]
    s.pending.pop()[1]()
    return targets(s)


def pass_level(s):
    for u in next_level(s):
        game.mission_troop_down(s, NoSave(), u)


def chests(s):
    """The first item of each loot bag on the ground (a stage chest's own item, the certificates after it)."""
    return [bag[0][0] for bag in s.data.get("drops", {}).values()]


def test_the_dimensional_test_brings_a_level_per_storm_and_pays_its_chests_at_the_fiftieth():
    s = room(10238)
    assert not s.data.get("zone_troops") and s.data["waves"] == []     # no fallback wave: the rule brings its levels
    # missiontext 1_testofdimensions: 1000 "Dimensional Test", 1010 / 1020 "Mission Details" / "Push yourself to the
    # limit", 1030 / 1040 "Progress"; the notice 2000 with 2020 "The dimensional test is starting." and 2060 "The next
    # dimension storm will open when there are no more enemies remaining."
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, 0xff, 1000]]
    assert [game.ACT_SITUATION_LINE, 0xff, 1010, 1020] in acts(s, game.ACT_SITUATION_LINE)
    assert acts(s, game.ACT_SITUATION_VALUE) == [[game.ACT_SITUATION_VALUE, 0xff, 1030, 1040, 0, 50, 0]]
    assert [a[2:5] for a in acts(s, 0xc8f0)] == [[2000, 2020, 2060]]
    tiers, bosses = rules.dimension_rows()
    for level in range(1, 51):
        up = next_level(s)
        tids = sorted(s.data["zone_troops"][u]["TroopTableID"] for u in up)
        if level % 5:
            assert len(tids) == 1 and tids[0] in tiers[(level - 1) // 10 + 1], level     # one troop of its tier
        else:
            assert tids == sorted(bosses[level]), level     # the boss named for the level ((5단계) .. (50단계))
        assert acts(s, 0xc8f0)[-1][2:4] == [2000, 2050]   # "A dimension storm has opened."
        prop, shown = storms(s)[-1]
        assert shown and zone.for_spot(10238)["SmartPropData"][0]["SmartPropTypeID"] == 221
        x, z = s.data["zone_troops"][up[0]]["PosX"], s.data["zone_troops"][up[0]]["PosZ"]
        storm = game.zone_prop(10238, prop)
        assert abs(storm["PosX"] - x) <= 1200 and abs(storm["PosZ"] - z) <= 1200   # they come out of the storm
        for u in up:
            game.mission_troop_down(s, NoSave(), u)
        assert storms(s)[-1] == (prop, 0)                 # it closes with its level
        if level < 50:
            assert not s.data.get("mission_won")
            assert acts(s, game.ACT_SITUATION_VALUE)[-1] == [game.ACT_SITUATION_VALUE, 0xff, 1030, 1040, level, 50, 0]
            assert acts(s, 0xc8f0)[-1][2:4] == [2000, 2070]   # "A dimension storm is about to open."
    assert bosses[35] == [191380, 191390] and bosses[50] == [191570]
    g, exp, cards = paid(window(s))
    assert g == "S" and exp == 0 and cards == 1           # %Mission_Grade 10238 rates 0.001; card 917100 (troop coins)
    assert s.data["cards"]["category"] == 917100
    # the ten stage chests, dropped at the end ("a reward every 5 levels paid at the end (10 chests)")
    assert chests(s) == [707010050 + 50 * k for k in range(10)]
    assert items.name(707010500) == "Dimensional Test Level 50 Hero Troop Conscription Paper"
    assert s.data["char"]["dimension_paid"] == rules.game_day()


def test_the_dimensional_tests_difficulty_is_its_starting_level():
    # textui 58043 / 58044 / 58045: "Level 1", "Level 16", "Level 31"; Hard and Hell take the certificate the stage
    # chests of 15 and 30 give (760000150 / 760000160, spottable Require1_Type PayItem)
    s = room(10238, difficulty=1)
    assert acts(s, game.ACT_SITUATION_VALUE) == [[game.ACT_SITUATION_VALUE, 0xff, 1030, 1040, 15, 50, 0]]
    for _ in range(5):                                    # 16 .. 20
        pass_level(s)
    assert s.data["dimension"]["passed"] == 20
    up = next_level(s)                                    # 21 stands when the room is won (!win)
    game.mission_won(s, s.state)
    assert chests(s) == [707010200]                       # only the stage passed in this run: 20
    assert s.data["zone_troops"][up[0]]["TroopTableID"] in rules.dimension_rows()[0][3]
    s = room(10238, difficulty=2)
    assert s.data["dimension"]["passed"] == 30
    assert next_level(s) and s.data["dimension"]["level"] == 31
    assert rules.dimension_rows()[1][35] and [loot.categories()[917116][0][0], loot.categories()[917134][0][0]] == \
        [760000150, 760000160]


def test_the_dimensional_test_pays_once_a_day():
    # "once a day (rewards once, retries allowed)" (OFFICIAL-NOTES): the day starts at 07:00 UTC as the day limits'
    s = room(10238)
    c = s.data["char"]
    for _ in range(5):
        pass_level(s)
    game.mission_won(s, s.state)
    assert chests(s) == [707010050] and paid(window(s))[2] == 1
    again = room(10238)
    again.data["char"] = again.data["account"]["characters"][0] = c
    for _ in range(5):
        pass_level(again)
    game.mission_won(again, again.state)
    assert chests(again) == [] and paid(window(again)) == ("S", 0, 0)
    c["dimension_paid"] = "2000-01-01"                    # another day
    third = room(10238)
    third.data["char"] = third.data["account"]["characters"][0] = c
    game.mission_won(third, third.state)
    assert chests(third) == [] and paid(window(third))[2] == 1      # no stage passed: the card only


# --- Subjugation (PVE_REPEAT 10327, 20326, 20327, 20329; OFFICIAL-NOTES, the footage part 6 20:14-24:00) ---

SUBJUGATIONS = [  # spot, the clock's group / text, the count's group / text, its value and top at the start, notice
    (10327, (670, 680), (690, 700), (1, 6), (710, 711)),      # "Remaining Time", "Wave Progression" 1/6
    (20326, (660, 661), (670, 671), (1, 6), (700, 701)),      # "Time Limit", "Wave Progression"
    (20327, (730, 731), (740, 741), (6, 6), (800, 810)),      # "Time Limit", "Remaining Waves"
    (20329, (730, 731), (740, 741), (0, 6), (800, 810)),      # "Time Limit", "Destroyed Towers"
]


@pytest.mark.parametrize("spot, clock_ids, count_ids, start, notice", SUBJUGATIONS)
def test_a_subjugation_shows_its_clock_and_its_count(spot, clock_ids, count_ids, start, notice):
    s = room(spot, level=11)
    assert acts(s, rules.ACT_SITUATION_TIME) == [[rules.ACT_SITUATION_TIME, 0xff, *clock_ids, 210]]   # 3:30
    assert acts(s, game.ACT_SITUATION_VALUE) == [[game.ACT_SITUATION_VALUE, 0xff, *count_ids, *start, 0]]
    assert acts(s, 0xc8f0)[0][2:4] == list(notice)       # "A Troop mission." / "Heroes cannot be controlled."


def test_the_grey_wood_subjugation_runs_as_the_footage():
    s = room(10327, level=11)
    # the footage's panel (part 6 20:16 / 20:54): "Grey Wood", success "Eliminate the remaining thieves" (621) only,
    # failure "Let all ally Troops die" (650), "Remaining Time", "Wave Progression 1/6"
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, 0xff, 600]]
    assert [a[2:] for a in acts(s, game.ACT_SITUATION_LINE)] == [[610, 621], [640, 650]]
    goblin = 16039                                        # 141070 보물고블린 (NP_Grade Extra, F10008), held at the start
    assert goblin not in s.data["zone_troops"]
    later(s, 59.5)
    assert goblin not in s.data["zone_troops"]
    later(s, 0.5)                                         # 2:30 left (the footage's chest notice, 21:22)
    assert goblin in s.data["zone_troops"] and not game.hostile(s.data["zone_troops"][goblin])   # no target
    assert acts(s, 0xc8f0)[-1][1:4] == [director.NOTICE_MID, 720, 721]   # centred: "Use your Troop to collect Treasure
                                                                          # Chests."
    wave = targets(s)
    for u in wave:
        game.mission_troop_down(s, NoSave(), u)
    rules.tick(s)
    assert acts(s, game.ACT_SITUATION_VALUE)[-1][4:6] == [2, 6]                  # the second wave came
    later(s, 30)                                          # 1:59 left: the goblin that was not caught runs off
    assert goblin in s.data["down"] and [game.ACT_ENABLE_TROOP, 0, goblin, 0, 0] in acts(s, game.ACT_ENABLE_TROOP)
    later(s, 60)                                          # 0:59 left
    assert acts(s, 0xc8f0)[-1][2:4] == [730, 731]         # "60 seconds remaining." / "... get more rewards."
    later(s, 30)
    assert acts(s, 0xc8f0)[-1][2:3] == [732]              # "You have 30 seconds left."
    assert not s.data.get("mission_won")
    later(s, 30)                                          # 0:00: survived
    assert [game.ACT_SITUATION_DONE, 0xff, 621, 1] in acts(s, game.ACT_SITUATION_DONE)
    g, exp, cards = paid(window(s))
    assert (g, exp, cards) == ("S", 1100, 1)              # the footage's window: S, Hero EXP 1100
    assert s.data["cards"]["category"] == 912511          # 1-41_노말_A1N: Region Visionstones or a Crazy Nose Brawler


def test_a_subjugation_cleared_before_its_clock_is_won_at_its_last_wave():
    s = room(10327, level=11)
    for _ in range(10):
        for u in targets(s):
            game.mission_troop_down(s, NoSave(), u)
    assert s.data.get("mission_won") and rules.time_left(s) > 200    # the clock stopped at the win
    assert paid(window(s))[0] == "S"


def test_the_subjugation_window_reproduces_the_footage():
    # part 6 23:58 (f_00729): Clear Time 3:50, Clear 46396, Damage 150000, Participants 19639, Total 216035, S
    p = loot.grade_points(loot.grade_row(10327, "Normal"), 230)
    assert (p["clear"], p["damage"], p["party"], p["death"], p["total"], p["grade"]) == (46396, 150000, 19639, 0,
                                                                                          216035, 0)
    # its card (f_00731): Region Visionstone Grey Wood, one of the S category's stones
    stones = {c for c, _, _, _ in loot.categories()[8300111]}
    assert 354000060 in stones and items.name(354000060) == "Region Visionstone Grey Wood"

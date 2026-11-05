"""Walkthrough part 8 (Windstone Desert, Chasm of Chaos, Forgotten Wilderness, the endgame list): HeroLevel quest
conditions, mission clears matched by their mission and difficulty, the spot schedule push 0x4078.
Reads the tables from the installed game's Info.pkg. Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import daily, game, obf, quest, rules, tables, world
from kuf2.obf import T1, T2
from kuf2.packet import Reader

RAYMOND = 2020111       # Windstone main quest "Call from Raymond": Talk 729, HeroLevel 25
ELEMENTAL_KING = 2020113  # the next main quest: Talk 632, HeroLevel 26
HUNTERS = 2021501       # Climax: MissionLevelClear NORMAL at 20309 (Hideout of Hunters)
SCARP = 2021801         # Climax: MissionLevelClear ANY at 20320 (Secluded Scarp)


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0, "level": 1, "exp": 0, "quests": {"active": {}, "done": []}}}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class State:
    saves = 0

    def save(self):
        self.saves += 1


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def accept_body(qid, mode=0):
    enc = obf.u32(qid)
    return bytes([T2[(enc[0] * 4 + mode) & 0xff]]) + enc


def progress(sent, qid):
    """The last 0x554c of quest qid: (state, 5 counts)."""
    b = next(bytes(w.buf) for w in reversed(sent) if w.proto == quest.S2C_PROGRESS and obf.dec_u32(bytes(w.buf)[13:17]) == qid)
    return b[0], struct.unpack_from("<5h", b, 1)


@pytest.fixture
def world_role():
    st = State()
    return world.make(st, 0, "127.0.0.1", 0), st


def test_hero_level_condition_is_met_as_one_once_the_level_is_reached(world_role):
    # the client counts a HeroLevel condition (type 0x14) met only at count 1 (0x554c handler 0x140d7b7c0;
    # planning/client/town_quest_npc.md Gap 2): 0 below Complete<n>_Value1, 1 from it, need 1
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c["level"] = 24
    assert quest.conditions(tables.by_id("questtable")[str(RAYMOND)])[1][::2] == ("HeroLevel", 1)
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(RAYMOND)))
    assert c["quests"]["active"][str(RAYMOND)]["counts"][:2] == [0, 0]
    assert not any(w.proto == quest.S2C_PROGRESS for w in s.sent)  # below the goal: nothing moved
    world.add_exp(s, st, world.hero_need(24))                      # exactly one level
    assert c["level"] == 25 and progress(s.sent, RAYMOND) == (0, (0, 1, 0, 0, 0))
    world.add_exp(s, st, world.hero_need(25))                      # past the goal: the count stays at 1
    assert c["quests"]["active"][str(RAYMOND)]["counts"][1] == 1
    role.handlers[quest.C2S_PROGRESS](s, pkt(quest.C2S_PROGRESS, struct.pack("<H", 1) + obf.u32(RAYMOND) + b"\0"))
    assert progress(s.sent, RAYMOND) == (1, (1, 1, 0, 0, 0))       # the Talk (JustCompleted by the client) finishes it


def test_hero_level_already_reached_is_met_on_accept(world_role):
    role, st = world_role
    s = Session()
    s.data["char"]["level"] = 27
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(ELEMENTAL_KING)))
    assert s.data["char"]["quests"]["active"][str(ELEMENTAL_KING)]["counts"][:2] == [0, 1]


def test_town_entry_lists_a_held_hero_level_condition_as_met(world_role):
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=30, spot=world.START_SPOT, pos=list(world.START_POS))
    c["quests"]["active"][str(RAYMOND)] = {"counts": [0] * 5, "time": 0, "tracked": True}  # accepted before this build
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(world.START_SPOT)))
    lst = bytes(next(w for w in s.sent if w.proto == quest.S2C_ACTIVE).buf)
    assert struct.unpack_from("<H", lst)[0] == 1 and struct.unpack_from("<5h", lst, 2 + 16)[:2] == (0, 1)
    assert not any(w.proto == quest.S2C_PROGRESS for w in s.sent)  # the list carries it


def test_a_level_stored_as_the_count_before_is_rewritten_at_town_entry(world_role):
    # a save from before the 0/1 counts holds the level (24 of 25): read against need 1 it would pass as met
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=24, spot=world.START_SPOT, pos=list(world.START_POS))
    c["quests"]["active"][str(RAYMOND)] = {"counts": [1, 24, 0, 0, 0], "time": 0, "tracked": True}
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(world.START_SPOT)))
    lst = bytes(next(w for w in s.sent if w.proto == quest.S2C_ACTIVE).buf)
    assert lst[2 + 13] == 0 and struct.unpack_from("<5h", lst, 2 + 16)[:2] == (1, 0)   # not ready to hand in
    assert not quest.hand_in(s, st, RAYMOND)


def game_session(spot, difficulty=None, active=()):
    s = Session()
    c = s.data.pop("char")
    c["quests"]["active"] = {str(q): {"counts": [0] * 5, "time": 0, "tracked": True} for q in active}
    if difficulty is not None:
        c["mission"] = {"spot": spot, "difficulty": difficulty}
    s.data.update(account={"characters": [c]}, spot=spot)
    return s, c


def test_a_mission_win_counts_only_the_conditions_naming_that_mission():
    s, c = game_session(20309, difficulty=0, active=(HUNTERS, SCARP))
    game.mission_won(s, State())
    assert any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)   # after the exp it pays (0x124a)
    assert c["quests"]["active"][str(HUNTERS)]["counts"][0] == 1   # NORMAL at 20309, won on Normal
    assert c["quests"]["active"][str(SCARP)]["counts"][0] == 0     # ANY, but at 20320


def test_a_mission_win_on_another_difficulty_leaves_a_normal_clear_open():
    s, c = game_session(20309, difficulty=1, active=(HUNTERS,))
    game.mission_won(s, State())
    assert c["quests"]["active"][str(HUNTERS)]["counts"][0] == 0   # won on Hard: the condition names NORMAL (exact)
    s, c = game_session(20320, active=(SCARP,))                    # a quest warp (no 0x3f48): Normal, ANY counts
    game.mission_won(s, State())
    assert c["quests"]["active"][str(SCARP)]["counts"][0] == 1


def test_a_hard_daily_mission_task_needs_its_mission_and_hard():
    task = next(r for r in tables.sections("dailytask")["DailyTask"]
                if r["Complete_Type"] == "MissionLevelClear" and r["Complete_ID1"] == "HARD" and r["IngSpot"] == "20310")
    for spot, diff, moved in ((20400, 1, 0), (20310, 0, 0), (20310, 1, 1)):
        s, c = game_session(spot, difficulty=diff)
        s.data["char"] = c
        c["daily"] = {"date": rules.game_day(), "tasks": [{"id": int(task["DailyTask_ID"]), "progress": 0, "state": daily.OPEN}],
                      "rewarded": 0}
        game.mission_won(s, State())
        assert c["daily"]["tasks"][0]["progress"] == moved, (spot, diff)


def test_enter_spot_keeps_the_difficulty_the_solo_room_sent(world_role):
    role, st = world_role
    s = Session()
    from kuf2 import troops
    c = s.data["char"]                                          # 20309 wants one troop organised (Min_Limit_Troop)
    troops.lineup(c)["slots"][1] = troops.grant(c, 1)[0]["uid"]
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(20309) + b"\x01\x00"))
    m = s.data["char"]["mission"]
    assert (m["spot"], m["difficulty"]) == (20309, 1) and s.data["battle_spot"] == 20309
    assert s.sent[-1].proto == world.S2C_GAME_SERVER
    s.data["char"]["mission"] = {"spot": 10358, "quest": 1150301, "back": 10350}          # a quest's mission warp
    s.data["char"]["quests"] = {"active": {"1150301": {"counts": [0] * 5}}, "done": []}  # held until handed in
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10358) + b"\0\0"))
    assert s.data["char"]["mission"] == {"spot": 10358, "quest": 1150301, "back": 10350}
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(20309) + b"\x02"))
    m = s.data["char"]["mission"]
    assert (m["spot"], m["difficulty"], m.get("quest")) == (20309, 2, None)                # another spot: no stale end


def open_now(records, spot, wday, hour):
    """The client's check 0x140d65b50 over the 0x4078 records: mask & W[tm_wday], open <= tm_hour < close."""
    w = (0x01, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02)[wday]           # 0x142e3d088, tm_wday 0 = Sunday
    return any(sp == spot and mask & w and opn <= hour < close for mask, sp, close, opn in records)


def test_spot_schedule_push_carries_every_spotschedule_row():
    b = bytes(world.spot_schedule_packet().buf)
    rows = tables.sections("spottable")["SpotSchedule"]
    n = struct.unpack_from("<H", b)[0]
    assert n == len(rows) == 20 and len(b) == 2 + 7 * n
    recs = [(b[2 + 7 * i], obf.dec_u32(b[3 + 7 * i:7 + 7 * i]), b[7 + 7 * i], b[8 + 7 * i]) for i in range(n)]
    assert (0x40, 10540, 24, 7) in recs                            # Monday 7-24: "40 <10540> 18 07" (the spec)
    assert open_now(recs, 10540, 1, 7) and open_now(recs, 10540, 2, 6) and not open_now(recs, 10540, 2, 7)
    assert open_now(recs, 20908, 3, 12) and not open_now(recs, 20908, 2, 12)  # Mon/Wed/Thu/Sat all day
    assert not open_now(recs, 10215, 1, 12)                        # not scheduled: the client leaves it open itself


def test_start_game_sends_the_spot_schedule():
    role = world.make(State(), 0, "127.0.0.1", 0)
    s = Session()
    c = {"id": 4, "name": "A", "class": 0, "level": 30, "exp": 0, "tutorial_done": True, "spot": world.START_SPOT,
         "pos": list(world.START_POS)}
    s.data["account"] = {"characters": [c]}
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
    sched = [w for w in s.sent if w.proto == world.S2C_SPOT_SCHEDULE]
    assert len(sched) == 1 and bytes(sched[0].buf) == bytes(world.spot_schedule_packet().buf)


@pytest.mark.parametrize("spot, pos", [(20200, [58609, 0, 70069]), (20600, [204365, 0, 149592]),
                                       (20940, [172638, 0, 218170])])
def test_travel_to_an_unmeasured_field_lands_on_its_zone_entry_point(world_role, spot, pos):
    """Windstone Desert, Chasm of Chaos, Forgotten Wilderness: the zone file's group-0 start point, not the spottable
    rectangle corner (TOWN_SPOT_START)."""
    role, st = world_role
    s = Session()
    s.data["char"].update(spot=world.START_SPOT, pos=list(world.START_POS))
    role.handlers[0x3744](s, pkt(0x3744, struct.pack("<I", spot)))
    out = s.sent[-1]
    assert out.proto == 0x3745 and struct.unpack_from("<HI", out.buf, 0) == (0, spot)
    assert s.data["char"]["spot"] == spot and s.data["char"]["pos"] == pos


def cleared_rows(b):
    """0x108f as the handler 0x140675a10 reads it: {spot: (idx0, idx1, idx2)} with idx = difficulty (wire +0, +8, +6)."""
    n = struct.unpack_from("<H", b)[0]
    assert len(b) == 2 + 10 * n
    out = {}
    for i in range(n):
        r = b[2 + 10 * i:12 + 10 * i]
        out[obf.dec_u32(r[2:6])] = (struct.unpack_from("<H", r, 0)[0], struct.unpack_from("<H", r, 8)[0],
                                    struct.unpack_from("<H", r, 6)[0])
    return out


def test_a_won_mission_enters_the_clear_list_by_difficulty():
    s, c = game_session(20306, difficulty=0)
    game.mission_won(s, State())
    s.data["spot"] = 20306
    s.data.pop("mission_won")                           # a second room (each room is its own game connection)
    c["mission"]["difficulty"] = 1
    game.mission_won(s, State())
    assert c["cleared"] == {"20306": [1, 1, 0]}
    assert cleared_rows(bytes(world.cleared_packet(c).buf)) == {20306: (1, 1, 0)}


def test_clear_list_answers_0x108e_and_rides_on_town_entry(world_role):
    """Urka Village North 20324 needs SpotClear 20306 (spottable Require2_Type_1): the client looks 20306 up in this
    list (0x140674b60), so it must be there once 20306 is won."""
    row = tables.by_id("spottable")["20324"]
    assert (row["Require2_Type_1"], row["Require2_Value1_1"]) == ("SpotClear", "20306")
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(spot=world.START_SPOT, pos=list(world.START_POS), cleared={"20306": [1, 0, 0]})
    role.handlers[world.C2S_CLEARED](s, pkt(world.C2S_CLEARED, b""))
    assert s.sent[-1].proto == world.S2C_CLEARED and cleared_rows(bytes(s.sent[-1].buf)) == {20306: (1, 0, 0)}
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(world.START_SPOT)))
    assert any(w.proto == world.S2C_CLEARED for w in s.sent[2:])
    assert bytes(world.cleared_packet({}).buf) == b"\0\0"            # the old empty reply

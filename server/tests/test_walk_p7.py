"""Walkthrough part 7 (Lv 21-23: Kedington, Greendale, Grey Hampton, Engelberg, Ancient Temple; planning/walkthrough/
p7-lv21-23.md): mission clears by mission and difficulty, the clear list the world map's SpotClear gate reads (0x108f),
HeroLevel conditions, and the chain walk's verdicts on these quests. Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import pathlib
import struct
import sys

import pytest

from kuf2 import combat, game, obf, quest, tables, world, zone
from kuf2.obf import T1, T2
from kuf2.packet import Reader

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools" / "recon"))

KEDINGTON, GREENDALE_OUT, GREENDALE_MID, GREY_HAMPTON, TEMPLE = 10320, 10314, 10324, 10315, 10317
ENGELBERG_IN, ENGELBERG_MID = 10213, 10214
PART7 = (ENGELBERG_IN, KEDINGTON, GREENDALE_OUT, GREENDALE_MID, ENGELBERG_MID, GREY_HAMPTON, TEMPLE)


class NoSave:
    saves = 0

    def save(self):
        self.saves += 1


class Session:
    def __init__(self, active=(), level=21, spot=None):
        c = {"id": 1, "class": 0, "level": level, "quests": {"active": {q: {"counts": [0] * 5} for q in active},
                                                            "done": []}}
        self.data = {"char": c, "account": {"characters": [c]}, "spot": spot, "battle": combat.Battle()}
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def counts(s, qid):
    return s.data["char"]["quests"]["active"][str(qid)]["counts"]


def test_the_part7_missions_load_as_mission_rooms_with_enemies():
    for spot in PART7:
        assert game.is_mission(spot), spot
        spawned = [t for t in zone.for_spot(spot)["NPCTroopInfoData"] if t["IsActivated"] and t["SpawnActivated"]]
        # Engelberg Midpoint's enemies are all script-spawned (IsActivated 0): nothing to win there offline yet
        assert any(game.hostile(t) for t in spawned) == (spot != ENGELBERG_MID), spot


def test_a_mission_clear_counts_only_for_its_own_mission():
    # 1011102 (Kedington Castle Wall) and 1012002 (Engelberg Entrance) both ask MissionLevelClear ANY; each names its
    # mission in IngSpot1. Before, any won mission moved every ANY condition.
    s = Session(active=("1011102", "1012002"), spot=ENGELBERG_IN)
    game.mission_won(s, NoSave())
    assert counts(s, 1012002)[0] == 1 and counts(s, 1011102)[0] == 0
    progress = [w for w in s.sent if w.proto == quest.S2C_PROGRESS]
    assert len(progress) == 1 and obf.dec_u32(bytes(progress[0].buf)[13:17]) == 1012002


@pytest.mark.parametrize("difficulty, counted", [(0, True), (1, False), (2, False)])
def test_the_climax_asks_a_normal_clear(difficulty, counted):
    s = Session(active=("1011402",), level=23, spot=TEMPLE)            # MissionLevelClear NORMAL at 10317
    s.data["char"]["mission"] = {"spot": TEMPLE, "difficulty": difficulty}
    game.mission_won(s, NoSave())
    assert counts(s, 1011402)[0] == (1 if counted else 0)


def test_mission_clear_difficulty_names():
    assert quest.mission_clear_matches("ANY", 2) and quest.mission_clear_matches("Any", 0)
    assert quest.mission_clear_matches("NORMAL", 0) and quest.mission_clear_matches("hell", 2)
    assert not quest.mission_clear_matches("HARD", 0) and not quest.mission_clear_matches("NORMAL", 5)


def test_the_world_map_entry_keeps_the_difficulty():
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    s = Session()
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(ENGELBERG_IN) + bytes([1])))
    m = s.data["char"]["mission"]
    assert (m["spot"], m["difficulty"]) == (ENGELBERG_IN, 1)
    assert s.sent[-1].proto == world.S2C_GAME_SERVER
    # a quest's pending mission of the same spot keeps where it ends; another spot replaces it
    s.data["char"]["mission"] = {"spot": 10358, "quest": 1150301, "back": 10350}
    s.data["char"].setdefault("quests", {"active": {}, "done": []})["active"]["1150301"] = {"counts": [0] * 5}
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10358) + bytes([0])))
    assert s.data["char"]["mission"] == {"spot": 10358, "quest": 1150301, "back": 10350}
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(KEDINGTON)))    # no byte: 0
    m = s.data["char"]["mission"]
    assert m["spot"] == KEDINGTON and m.get("difficulty", 0) == 0


def client_clear_list(b):
    """The 0x108f read as 0x140675a10 does it: u16 n, n x 10 bytes; spot from bytes 2..5 by the tables."""
    n, out = struct.unpack_from("<H", b)[0], {}
    for i in range(n):
        e = b[2 + 10 * i:12 + 10 * i]
        spot = T2[e[3]] << 24 | T1[e[4]] << 16 | T2[e[5]] << 8 | T1[e[2]]
        normal, hell, hard = struct.unpack_from("<H", e, 0)[0], struct.unpack_from("<H", e, 6)[0], \
            struct.unpack_from("<H", e, 8)[0]
        out[spot] = (normal, hard, hell)
    assert len(b) == 2 + 10 * n
    return out


def test_a_won_mission_joins_the_clear_list_the_spotclear_gate_reads():
    assert tables.by_id("spottable")[str(GREENDALE_MID)]["Require2_Type_1"] == "SpotClear"
    assert tables.by_id("spottable")[str(GREENDALE_MID)]["Require2_Value1_1"] == str(GREENDALE_OUT)
    st = NoSave()
    s = Session(active=("1011201",), level=22, spot=GREENDALE_OUT)
    game.mission_won(s, st)
    assert s.data["char"]["cleared"] == {str(GREENDALE_OUT): [1, 0, 0]} and st.saves >= 1
    s.data["char"]["mission"] = {"spot": GREENDALE_OUT, "difficulty": 1}
    s.data.pop("mission_won")
    game.mission_won(s, st)
    assert s.data["char"]["cleared"][str(GREENDALE_OUT)] == [1, 1, 0]
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[world.C2S_CLEARED](s, pkt(world.C2S_CLEARED, b""))
    assert s.sent[-1].proto == world.S2C_CLEARED
    assert client_clear_list(bytes(s.sent[-1].buf)) == {GREENDALE_OUT: (1, 1, 0)}


def test_no_clears_is_an_empty_list():
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    s = Session()
    role.handlers[world.C2S_CLEARED](s, pkt(world.C2S_CLEARED, b""))
    assert bytes(s.sent[-1].buf) == b"\0\0"


def test_a_hero_level_condition_follows_the_level():
    # 1010220 (Accolade, before Kedington): Talk + HeroLevel 21
    q = tables.by_id("questtable")["1010220"]
    assert q["Complete2_Type"] == "HeroLevel" and q["Complete2_Value1"] == "21"
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    s = Session(level=20)
    s.data.pop("battle")
    enc = obf.u32(1010220)
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, bytes([T2[(enc[0] * 4) & 0xff]]) + enc))
    assert counts(s, 1010220)[1] == 0 and not quest.done(q, s.data["char"]["quests"]["active"]["1010220"])
    world.add_exp(s, NoSave(), world.hero_need(20))
    assert s.data["char"]["level"] == 21 and counts(s, 1010220)[1] == 1     # met: 1 (0x140d7b7c0), not the level
    last = [w for w in s.sent if w.proto == quest.S2C_PROGRESS][-1]
    assert bytes(last.buf)[0] == 0 and struct.unpack_from("<5h", bytes(last.buf), 1)[1] == 1    # Talk still open


def test_a_hero_level_already_reached_is_met_on_accept():
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    s = Session(level=22)
    enc = obf.u32(1010220)
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, bytes([T2[(enc[0] * 4) & 0xff]]) + enc))
    assert counts(s, 1010220)[1] == 1

def test_a_fallen_leader_counts_by_its_leader_name():
    # 1011103 (Kedington): NPNameKill 2509 "DarkElf_Leader_KW", a name only npname %NPLeaderName_String gives (leader
    # 120030); zone troop 20041 (table 120050, activated) is led by it
    assert quest.kill_names(120050) & {"2509"} == set() and "2509" in quest.leader_names(120030)
    assert quest.leader_names(-100) == set() and quest.leader_names(None) == set()
    t = next(t for t in zone.for_spot(KEDINGTON)["NPCTroopInfoData"] if t["NPLeaderID"] == 120030 and t["IsActivated"])
    s = Session(active=("1011103",), spot=KEDINGTON)
    quest.on_kill(s, NoSave(), t["TroopTableID"], leader=t["NPLeaderID"])
    assert counts(s, 1011103)[0] == 1
    quest.on_kill(s, NoSave(), t["TroopTableID"])                        # the troop alone is not the leader
    assert counts(s, 1011103)[0] == 1


def test_a_leader_drops_its_quest_item():
    # 1011202 (Outskirts of Greendale): ItemGain 450002032 x2 from item_drop_quest %Leader 114100 (rate 100000);
    # zone troop 20200 (table 114060, activated) is led by it
    t = next(t for t in zone.for_spot(GREENDALE_OUT)["NPCTroopInfoData"] if t["TroopID"] == 20200)
    assert t["NPLeaderID"] == 114100 and t["IsActivated"]
    s = Session(active=("1011202",), level=22, spot=GREENDALE_OUT)
    assert quest.roll_drops(s, t["TroopTableID"], roll=lambda n: 0) == []
    assert quest.roll_drops(s, t["TroopTableID"], roll=lambda n: 0, leader=t["NPLeaderID"]) == [(450002032, 1)]
    s.data["char"]["quests"]["active"]["1011202"]["counts"][0] = 2       # met: no more drops
    assert quest.roll_drops(s, t["TroopTableID"], roll=lambda n: 0, leader=t["NPLeaderID"]) == []


def test_a_wiped_zone_troop_reports_its_leader():
    role = game.make(NoSave(), 0)
    s = Session(active=("1011103",), spot=KEDINGTON)
    t = next(t for t in zone.for_spot(KEDINGTON)["NPCTroopInfoData"] if t["NPLeaderID"] == 120030 and t["IsActivated"])
    s.data["zone_troops"] = {t["TroopID"]: t}
    s.data["char"]["mission"] = {"spot": KEDINGTON, "difficulty": 0}
    s.data["battle"].add_np(t["TroopID"], 1, 1)                          # one unit of 1 hp: one hit wipes it
    s.data["battle"].add_hero(0, 1000, c=game.hero_combatant(s.data["char"]))   # the hitter: header +8 = troop 0
    hit = bytes(8) + bytes([T2[0], T1[0]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72) + \
        struct.pack("<H", 1) + bytes([T2[t["TroopID"] >> 8], T1[t["TroopID"] & 0xff]]) + \
        struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0]) + struct.pack("<H", 0)
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    assert counts(s, 1011103)[0] == 1

def test_the_chain_walk_judges_the_part7_story():
    chainwalk = pytest.importorskip("chainwalk", reason="tools/recon/chainwalk.py (not published) reads the footage")
    w = chainwalk.Walk(0)
    w.level = 23
    qs = tables.by_id("questtable")
    for qid in ("1011102", "1011201", "1011301", "1011402", "1012002", "1012003", "1011204"):
        w.held[qid] = qs[qid]
    verdict = lambda qid: w.condition(qid, qs[qid], 1)
    assert verdict("1011402")[0] == "OURS"                              # NORMAL clear counted
    assert verdict("1011102")[0] == "OURS" and "20061" in verdict("1011102")[1]     # Orchakin: script-spawned
    assert verdict("1011204") == ("BREAK", f"spot {GREENDALE_MID} needs spot {GREENDALE_OUT} cleared")
    w.clears.add(GREENDALE_OUT)
    assert verdict("1011204")[0] == "OURS"
    assert verdict("1012003")[0] == "OURS"          # Engelberg Midpoint: its script-held ghosts and lich come as waves



def test_invisible_observers_are_no_one_to_fight():
    # Engelberg Midpoint's only activated enemies are 11 invisible observers (131170, TROOP_NHU_D_OBSERVER_INVISIBLE)
    # stacked at one point: not a win condition; every real enemy there (the ghosts, the lich) is script-spawned
    spawned = [t for t in zone.for_spot(ENGELBERG_MID)["NPCTroopInfoData"] if t["IsActivated"] and t["SpawnActivated"]]
    observers = [t for t in spawned if zone.np_troop(t["TroopTableID"])["r_BASE_RESOURCE"] == game.OBSERVER_MODEL]
    assert len(observers) == 11 and not any(game.hostile(t) for t in spawned)


def test_an_unknown_difficulty_is_normal():             # as the client's entry check 0x140d68040 takes it
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    s = Session(active=("1011402",), level=23, spot=TEMPLE)
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(TEMPLE) + bytes([255]) + bytes(10)))
    assert s.data["char"]["mission"]["difficulty"] == 255
    game.mission_won(s, NoSave())
    assert counts(s, 1011402)[0] == 1 and s.data["char"]["cleared"][str(TEMPLE)] == [1, 0, 0]

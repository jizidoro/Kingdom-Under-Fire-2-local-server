"""Walkthrough part 5 (Lv 10-12 missions: Flamegrass Valley 10303, Fort Valley Castle 10306, Posterus Green 10211 /
10212, Steel Plain 10318); planning/walkthrough/p5-lv10-12.md. Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import struct

from kuf2 import combat, daily, game, obf, quest, rules, world
from kuf2.packet import Reader


class Session:
    def __init__(self, quests=None, spot=10303):
        c = {"id": 1, "class": 0, "level": 12, "spot": 10001, "pos": [0, 0, 0],
             "quests": quests or {"active": {}, "done": []}}
        self.data = {"spot": spot, "account": {"id": 1, "characters": [c]}, "char": c}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def clear_mission(s, saver):
    """Down every hostile troop, wave after wave, until the mission is won (or nothing is left to fight)."""
    for _ in range(100):
        alive = [u for u, z in s.data.get("zone_troops", {}).items()
                 if game.hostile(z) and u not in s.data.get("down", set())]
        if not alive or s.data.get("mission_won"):
            return
        for u in alive:
            game.mission_troop_down(s, saver, u)


class NoSave:
    def save(self):
        pass


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def held(*qids):
    return {"active": {str(q): {"counts": [0] * 5} for q in qids}, "done": []}


def room(s, difficulty=0):
    s.data["difficulty"] = difficulty
    s.data["battle"] = combat.Battle()
    game.spawn_zone_troops(s)
    return s.data["zone_troops"]


def won(s):
    return [w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE]


def test_a_mission_clear_moves_only_the_quest_of_that_mission():
    # 1010201 opens both Fort Valley Castle (1010202, IngSpot 10306) and Flamegrass Valley (1110501, IngSpot 10303),
    # both MissionLevelClear ANY; 1010202 opens both Posterus quests (1011701 at 10211, 1011702 at 10212)
    s = Session(held(1110501, 1010202, 1011701, 1011702))
    assert quest.on_mission_clear(s, NoSave(), 10303) == [1110501]
    active = s.data["char"]["quests"]["active"]
    assert active["1110501"]["counts"][0] == 1 and active["1010202"]["counts"][0] == 0
    assert quest.on_mission_clear(s, NoSave(), 10211) == [1011701] and active["1011702"]["counts"][0] == 0


def test_the_climax_counts_only_a_normal_clear():
    # 1010204 Steel Plain: MissionLevelClear NORMAL at 10318
    s = Session(held(1010204))
    assert quest.on_mission_clear(s, NoSave(), 10318, difficulty=1) == []           # Hard
    assert quest.on_mission_clear(s, NoSave(), 10318, difficulty=0) == [1010204]    # Normal


def test_the_first_mission_still_counts_its_any_clear():
    s = Session(held(1150301))                                                       # ID1 'Any', IngSpot 10358
    assert quest.on_mission_clear(s, NoSave(), 10358) == [1150301]


def test_daily_mission_tasks_move_for_their_own_spot_and_difficulty():
    s = Session()
    c = s.data["char"]
    c["daily"] = {"date": rules.game_day(), "rewarded": 0,
                  "tasks": [{"id": 441700, "progress": 0, "state": daily.OPEN},     # MissionLevelClear ANY at 10321
                            {"id": 311700, "progress": 0, "state": daily.OPEN},     # AnyMissionClear NORMAL x4
                            {"id": 321700, "progress": 0, "state": daily.OPEN}]}    # AnyMissionClear HARD x3
    quest.on_mission_clear(s, NoSave(), 10303)
    assert [t["progress"] for t in c["daily"]["tasks"]] == [0, 1, 0]
    quest.on_mission_clear(s, NoSave(), 10321, difficulty=1)
    assert [t["progress"] for t in c["daily"]["tasks"]] == [1, 1, 1]


def test_steel_plain_has_no_enemy_until_the_mission_script_and_is_never_won_by_an_ally_falling():
    s = Session(held(1010204), spot=10318)
    troops = room(s)
    # Jager, Sanchez and three infantry (team 0) stand; every Athril troop (team 1) is IsActivated 0, so the first
    # wave (force 20100) comes at once
    assert {10000, 10001, 10002, 10003, 10010} <= set(troops)
    assert any(game.hostile(t) for t in troops.values())
    game.mission_troop_down(s, NoSave(), 10001)
    assert not won(s) and s.data["char"]["quests"]["active"]["1010204"]["counts"][0] == 0


def test_flamegrass_is_won_by_its_table_and_counts_only_its_quest():
    # its director table (scenes/m10303.py, WIN = "table"): not by the last hostile's fall, but by Ochankin's once the
    # three wagon Ogres are down (the walkthrough's "Save Villagers & Defeat the Boss"); test_scenes_10303 plays it
    from kuf2 import director
    s = Session(held(1110501, 1010202))
    troops = room(s)
    enemies = [u for u, t in troops.items() if game.hostile(t)]
    assert 24313 in enemies                                         # the boss Ochankin (103290)
    assert 31153 in troops and 31153 not in enemies                 # the treasure goblin (NP_Grade Extra) is a bonus
    assert all(troops[u]["TeamNum"] == 1 for u in enemies)
    s.state = NoSave()
    clear_mission(s, NoSave())
    assert not won(s)                                               # every hostile down: not the original's win

    def at(name):                                                   # the hero reaches a place, its lines play out
        b = director.bound(10303, name)
        combat.hero_moved(s, (b["BoundCenterX"], 0, b["BoundCenterZ"]))
        for _ in range(400):
            if not s.pending:
                return
            s.pending.sort(key=lambda p: p[0])
            s.pending.pop(0)[1]()
    at("(3)멈추시오")                                                # the scouts come
    clear_mission(s, NoSave())
    at("(4)본대만나기")                                              # the meeting, the ambush (the main force's fall
    director.on_broken(s, 10002)                                    # counts now), the barricade into the shortcut,
    at("(10)유저도착체크2")                                          # the convoy's front: the wagons and Ochankin
    assert len(won(s)) == 1                                         # fell long ago, the room is won
    active = s.data["char"]["quests"]["active"]
    assert active["1110501"]["counts"][0] == 1 and active["1010202"]["counts"][0] == 0


def test_the_entry_window_difficulty_reaches_the_room_and_its_troops():
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    w = Session()
    w.data["game_addr"] = ("127.0.0.1", 0)
    role.handlers[world.C2S_ENTER_SPOT](w, pkt(world.C2S_ENTER_SPOT, obf.u32(10303) + bytes([1])))
    c = w.data["char"]
    assert c["mission"] == {"spot": 10303, "quest": None, "back": 10001, "difficulty": 1}
    assert game.mission_difficulty(c, 10303) == 1 and game.mission_difficulty(c, 10306) == 0
    c["quests"] = held(1110501)
    s = Session()
    s.data["account"]["characters"][0] = s.data["char"] = c
    troops = room(s, game.mission_difficulty(c, 10303))
    assert troops[22002]["TroopTableID"] == 20103080               # '1-03_존1_하드_오크_경보병' for the zone's 103080
    assert s.data["battle"].troops[22002]["units"] == [1122] * 9   # the Hard row's HP_BASEUNIT, its table's 9 units (T9.3; the zone says 12)
    assert troops[24313]["TroopTableID"] == 20103290                # the Hard Ochankin
    game.mission_won(s, NoSave())                                   # its table's ending lines, then the window
    for _ in range(100):
        if not s.pending:
            break
        s.pending.sort(key=lambda p: p[0])
        s.pending.pop(0)[1]()
    assert s.data["char"]["quests"]["active"]["1110501"]["counts"][0] == 1      # ANY


def test_a_quest_warp_mission_reentered_from_its_npc_still_ends_at_the_quest_end_spot():
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    w = Session()
    w.data["game_addr"] = ("127.0.0.1", 0)
    c = w.data["char"]
    c.update(spot=10352, mission={"spot": 10358, "quest": 1150301, "back": 10350},     # 1150301's SpotWarp 613
             quests=held(1150301))                                                   # still held until handed in
    role.handlers[world.C2S_ENTER_SPOT](w, pkt(world.C2S_ENTER_SPOT, obf.u32(10358) + bytes([0])))   # Thomson
    assert c["mission"] == {"spot": 10358, "quest": 1150301, "back": 10350}
    c.update(spot=10202, mission={"spot": 10303, "back": 10001, "difficulty": 1})         # an old world-map entry
    role.handlers[world.C2S_ENTER_SPOT](w, pkt(world.C2S_ENTER_SPOT, obf.u32(10303) + bytes([0])))
    assert c["mission"] == {"spot": 10303, "quest": None, "back": 10202}


def test_difficulty_variants_fall_back_to_the_zone_troop():
    assert game.difficulty_troop(103080, 0) == 103080
    assert game.difficulty_troop(103080, 2) == 30103080
    assert game.difficulty_troop(103290, 2) == 103290               # no Hell Ochankin row
    assert game.difficulty_troop(20103080, 1) == 20103080           # already a variant (a respawn)
    assert game.difficulty_troop(103080, 7) == 103080

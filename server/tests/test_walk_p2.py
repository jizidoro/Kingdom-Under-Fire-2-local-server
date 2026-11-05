"""Walkthrough part 2 (Grey Fog Streets 10358 through Grey Rock Fortress 10234 and back; planning/walkthrough/p2-grey-fog.md):
mission entry through a MISSION door (0x3f48), the win rule's guard, MissionLevelClear bound to its spot, the way back,
and the no-death rule of the walkthrough's missions. Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import struct

from kuf2 import combat, game, obf, world
from kuf2.packet import Reader


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


class Session:
    def __init__(self, room, active=(), **char):
        c = {"id": 1, "class": 0, "level": 5, "quests": {"active": {q: {"counts": [0] * 5} for q in active}, "done": []}}
        c.update(char)
        self.data = {"spot": room, "char": c, "account": {"id": 1, "characters": [c]}}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self):
        while self.pending:
            self.pending.pop(0)[1]()


class NoSave:
    def save(self):
        pass


def start_room(spot):
    """A game session at the end of loading (0x5040 100%): the battle and the zone troops."""
    role = game.make(NoSave(), 0)
    s = Session(spot)
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    s.run_later()
    return role, s


def any_troop(s):
    """A zone troop of the room to hit the hero with (every hit takes at least 1: combat.resolve)."""
    return next(u for u, t in s.data["battle"].troops.items() if u != 0 and t.get("c"))


def test_the_hero_cannot_die_in_the_walkthrough_missions():
    for spot in game.UNDYING_MISSIONS:
        _, s = start_room(spot)
        downs = []
        combat.apply_hits(s, [(0, [0] * (game.HERO_HP + 50))], game.send_troop_hp, lambda s, uid: downs.append(uid),
                          attacker=any_troop(s), attack={"pr": 1.0, "ar": 1.0})
        hero = s.data["battle"].troops[0]
        assert hero["hp"] in (1, hero["max"]) and downs == []     # the floor, or Glen's heal (director, Grey Rock 1000)


def test_a_field_hero_still_falls():
    _, s = start_room(10352)
    downs = []
    combat.apply_hits(s, [(0, [0] * (game.HERO_HP + 50))], game.send_troop_hp, lambda s, uid: downs.append(uid),
                      attacker=any_troop(s), attack={"pr": 1.0, "ar": 1.0})
    assert s.data["battle"].troops[0]["hp"] == 0 and downs == [0]


def test_the_tutorial_missions_spawn_no_hostile_troop_and_an_ally_fall_wins_nothing():
    # 10233 and 10234 hold every enemy inactive (IsActivated 0) for the missing mission Lua: the first wave comes at
    # once (game.next_wave), and an ally's fall wins nothing
    for spot in (10233, 10234):
        _, s = start_room(spot)
        troops = s.data["zone_troops"]
        assert troops and any(game.hostile(t) for t in troops.values()) and s.data["waves"] is not None
        ally = next(u for u, t in troops.items() if not game.hostile(t))
        game.mission_troop_down(s, NoSave(), ally)
        assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")


def test_glen_and_thompson_stand_in_the_tutorial_missions():
    # zone troops with their NP leaders: 10358 Thompson 162010 (TroopID 10000) and the Encablossian leader 162020
    # (22003, hostile); 10233 Glen 133020 / Thompson 133030; 10234 Glen 134010 / Thompson 134020
    expect = {10358: {10000: 162010, 22003: 162020}, 10233: {10000: 133020, 10001: 133030},
              10234: {10000: 134010, 10071: 134020}}
    for spot, leaders in expect.items():
        _, s = start_room(spot)
        troops = s.data["zone_troops"]
        assert {u: troops[u]["NPLeaderID"] for u in leaders} == leaders
    _, s = start_room(10358)
    assert game.hostile(s.data["zone_troops"][22003]) and not game.hostile(s.data["zone_troops"][10000])


def test_a_mission_clear_counts_only_the_quests_of_that_spot():
    _, s = start_room(10358)
    c = s.data["char"]
    c["quests"]["active"] = {"1150301": {"counts": [0] * 5}, "1150406": {"counts": [0] * 5}}
    c["mission"] = {"spot": 10358, "quest": 1150301, "back": 10350}
    for u in [u for u, t in s.data["zone_troops"].items() if game.hostile(t)]:
        game.mission_troop_down(s, NoSave(), u)
    from kuf2 import director
    street = director.bound(10358, 10007)                # the finale on the street ends it (WIN = "table")
    s.state = NoSave()
    director.on_position(s, street["BoundCenterX"], street["BoundCenterZ"])
    s.run_later()                                       # the director's ending lines, then the window
    assert s.data.get("mission_won")
    assert c["quests"]["active"]["1150301"]["counts"][0] == 1          # IngSpot1 10358
    assert c["quests"]["active"]["1150406"]["counts"][0] == 0          # MissionLevelClear Any, but IngSpot1 10233


def test_a_hard_clear_does_not_count_a_normal_only_quest():
    from kuf2 import quest, tables
    q = next(r for r in tables.load("questtable") if r["Complete1_Type"] == "MissionLevelClear"
             and r["Complete1_ID1"] == "NORMAL")
    s = Session(int(q["IngSpot1"]), active=[q["ID"]])
    assert quest.count(s, NoSave(), "MissionLevelClear", "ID1", {"ANY", "HARD"}, spot=q["IngSpot1"]) == []
    assert quest.count(s, NoSave(), "MissionLevelClear", "ID1", {"ANY", "NORMAL"}, spot=q["IngSpot1"]) == [int(q["ID"])]


def enter_spot(s, spot, difficulty=0):
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes([difficulty])))


def test_the_tower_door_leaves_the_field_room_and_remembers_the_quest():
    # Glen 6008 gives 1150406 beside the warp-500 door; its solo room's Start sends 0x3f48 10233 from the field room
    s = Session(10350, active=["1150406"], spot=10350, pos=[242124, 0, 206325])
    s.data.update(battle_spot=10350, game_addr=("127.0.0.1", 25004))
    enter_spot(s, 10233)
    assert [w.proto for w in s.sent] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 500             # the mission's start group, not the field's
    assert s.data["char"]["mission"] == {"spot": 10233, "quest": 1150406, "back": 10350}
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and struct.unpack_from("<I", bytes(s.sent[-1].buf), 8)[0] == 10233
    assert s.data["char"]["spot"] == 10350 and s.data["battle_spot"] == 10233


def test_grey_rock_is_entered_from_the_other_mist_field_and_ends_in_the_first():
    # 1150601 is accepted from Glen 6010 in 10359 (zone 2) beside the warp-501 door; its EndSpot is 10350
    s = Session(10359, active=["1150601"], spot=10359, pos=[265719, 0, 222193])
    s.data.update(battle_spot=10359, game_addr=("127.0.0.1", 25004))
    from kuf2 import troops
    t, _ = troops.grant(s.data["char"], 1)             # Grey Rock wants one troop organised (Min_Limit_Troop 1)
    troops.lineup(s.data["char"])["slots"][1] = t["uid"]
    enter_spot(s, 10234, difficulty=1)
    assert s.data["char"]["mission"] == {"spot": 10234, "quest": 1150601, "back": 10350, "difficulty": 1}


def test_a_mission_from_the_world_map_goes_straight_to_the_game_server():
    s = Session(10350, spot=10350)
    s.data.update(game_addr=("127.0.0.1", 25004))
    enter_spot(s, 10358)
    assert [w.proto for w in s.sent] == [world.S2C_GAME_SERVER]
    assert s.data["char"]["mission"] == {"spot": 10358, "quest": None, "back": 10350}


def test_a_battle_spot_without_a_zone_file_is_refused(monkeypatch):
    # world_travel.md Gaps 1: no room to build (it was one endless test enemy); from inside a room too, the client
    # stays where it is and shows "There is no game available." (0x3f41 i16 0x1c0a, u8 0)
    monkeypatch.setattr(game, "is_mission", lambda spot: False)
    s = Session(10001, spot=10001)
    s.data.update(game_addr=("127.0.0.1", 25004), battle_spot=10001)
    enter_spot(s, 10303)
    assert [bytes(w.buf) for w in s.sent] == [struct.pack("<HB", world.NO_GAME, 0)] and s.data["battle_spot"] == 10001
    assert "mission" not in s.data["char"]


def leave(spot, qid, back):
    role = game.make(NoSave(), 0)
    s = Session(spot, spot=10352, mission={"spot": spot, "quest": qid, "back": back})
    role.handlers[game.C2S_MISSION_LEAVE](s, pkt(game.C2S_MISSION_LEAVE, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_MISSION_LEAVE and len(out) == 16 and out[4:8] == obf.u32(back)
    return s.data["char"]


def test_the_way_back_follows_the_mission_quests_field_warp():
    # warpinfo 30001 (FinishOrDoingQuest 1150301) is 10350 group 0; 30002 (1150406) group 2 at the Tower of Moonlight
    c = leave(10358, 1150301, 10350)
    assert c["field_group"] == [10350, 0] and c["pos"] == [278357, 0, 190736] and "mission" not in c
    c = leave(10233, 1150406, 10350)
    assert c["field_group"] == [10350, 2] and c["pos"] == [164177, 0, 131152]
    x, _, z = c["pos"]
    assert (x - 161004) ** 2 + (z - 128882) ** 2 < 5000 ** 2              # Glen 6009 (1150406's EndSpot NPC)
    c = leave(10234, 1150601, 10350)
    assert c["field_group"] == [10350, 0] and "mission_return" not in c    # no warp names 1150601
    assert game.return_group(10350, None) == (0, None)


def test_thompsons_entrance_back_to_glen():
    # NPC 6304 (ENTRANCE3) sends 0x3f48 10358 from the camp's room (10352): the client leaves the room first (0x4049;
    # the 0x3f41 handler closes the live link, BattleField's disconnect handler would show 0x1c63), and the mission
    # ends at 1150301's EndSpot 10350, group 0, beside Glen 6004 (276919, 191059) who takes the hand-in
    s = Session(10352, active=["1150301"], spot=10352, pos=[309061, 0, 182675])
    s.data.update(battle_spot=10352, game_addr=("127.0.0.1", 25004))
    enter_spot(s, 10358)
    assert [w.proto for w in s.sent] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 613             # the mission's start group, not the field's
    assert s.data["char"]["mission"] == {"spot": 10358, "quest": 1150301, "back": 10350}
    c = leave(10358, 1150301, 10350)
    x, _, z = c["pos"]
    assert c["spot"] == 10350 and (x - 276919) ** 2 + (z - 191059) ** 2 < 2000 ** 2


def field_entry_warps(c):
    s = Session(10350, **c)
    s.data["char"] = c
    s.data.update(game_addr=("127.0.0.1", 25004))
    role = world.make(NoSave(), 0, "127.0.0.1", 0)
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10350)))
    s.run_later()
    return [obf.dec_u32(bytes(w.buf)[1:5]) for w in s.sent if w.proto == world.S2C_WARP_PROCESS]


def test_the_return_warp_and_its_cutscene_come_once():
    # 0x5641 type 1 queues the warp's EnterScript for the next room entry: 30001 (11_Village_chief) after 10358 only
    c = leave(10358, 1150301, 10350)
    assert c["mission_return"] == {"spot": 10350, "group": 0, "warp": 30001}
    assert field_entry_warps(c) == [30001] and "mission_return" not in c
    assert field_entry_warps(c) == []                                         # the next entry: the default start
    c = leave(10233, 1150406, 10350)
    assert field_entry_warps(c) == [30002] and field_entry_warps(c) == [607]  # group 2's plain warp afterwards
    assert world.field_warp(10350, 0) is None and world.field_warp(10352, 2) == 620 and world.field_warp(10352, 1) == 205

def test_the_consumed_return_warp_is_saved_at_once():
    # live 2026-10-24 (AC3 leg 2): the save predated the entry that used 30001, the guest stopped, and the next login
    # replayed 11_Village_chief; the field entry saves once it has taken the way back
    class Seen:
        def __init__(self):
            self.at = []

        def save(self):
            self.at.append("mission_return" in c)
    c = leave(10358, 1150301, 10350)
    s = Session(10350, **c)
    s.data["char"] = c
    s.data.update(game_addr=("127.0.0.1", 25004))
    s.state = Seen()
    world.send_field_entry(s, 10350, 0, leave_battle=False)
    assert "mission_return" not in c and s.state.at and s.state.at[-1] is False

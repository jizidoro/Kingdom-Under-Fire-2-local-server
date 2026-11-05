"""Walkthrough part 4 (town side: training camps, their quests and troops; planning/walkthrough/p4-town-training.md).
Reads the tables and the camps' zone files from the installed game. Run: py -m pytest -q server/tests
MissionLevelClear by IngSpot and difficulty, and "no win without a hostile troop", are built and tested on the p5
branch (5fa3d17, db127c6); the camps rely on them (9900221, 9900222 and 1010202 are held together)."""
import struct

from kuf2 import combat, game, obf, quest, troops, world
from kuf2.packet import Reader

RIFLEMAN = 9900222      # [Tutorial] Rifleman Training: NPC 949 in Accolade, MissionLevelClear ANY at 10346


class Session:
    """One character seen from both roles: the world role reads data["char"], the game role data["account"]."""
    def __init__(self, quests=None, spot=None):
        c = {"id": 1, "class": 0, "level": 11, "gold": 0, "spot": 10001, "quests": quests or {"active": {}, "done": []}}
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}, "battle": combat.Battle(), "spot": spot,
                     "game_addr": ("127.0.0.1", 0)}
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


def test_the_infantry_camp_starts_at_its_zone_start_point():
    s = Session(spot=10331)
    assert game.is_mission(10331) and game.start_pos(s) == game.mission_start(10331) == (38333, 0, 33877)


def test_the_rifleman_camp_from_the_quest_to_the_barracks_and_the_deck():
    wrole = world.make(NoSave(), 0, "127.0.0.1", 0)
    grole = game.make(NoSave(), 0)
    s = Session()
    c = s.data["char"]
    enc = obf.u32(RIFLEMAN)
    wrole.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, bytes([obf.T2[(enc[0] * 4) & 0xff]]) + enc))
    assert str(RIFLEMAN) in quest.record(c)["active"]
    # NPC 949's ENTRANCE menu -> the solo waiting room's Start -> 0x3f48 (spot 10346, normal)
    wrole.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10346) + bytes(2)))
    assert s.sent[-1].proto == world.S2C_GAME_SERVER
    s.data["spot"] = 10346
    assert game.is_mission(10346) and game.start_pos(s) == game.mission_start(10346)
    game.spawn_zone_troops(s)
    enemies = [u for u, t in s.data["zone_troops"].items() if game.hostile(t)]
    assert len(enemies) >= 1                                            # the camp's ogre (123430) first
    clear_mission(s, NoSave())
    assert any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)
    assert quest.record(c)["active"][str(RIFLEMAN)]["counts"][0] == 1
    grole.handlers[game.C2S_MISSION_LEAVE](s, pkt(game.C2S_MISSION_LEAVE, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_MISSION_LEAVE and out[:4] == bytes([0, 0, 0, 2]) and out[4:8] == obf.u32(10001)
    assert c["spot"] == 10001 and "mission" not in c
    # the hand-in at NPC 949 gives the rifleman contract, which becomes troop 1100621 in the barracks
    wrole.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, enc + b"\0"))
    assert RIFLEMAN in quest.record(c)["done"]
    contract = next(i for i in c["bag"] if i["code"] == 355101501)
    use = bytes(6) + obf.u32(355101501) + bytes(2) + obf.u64(contract["serial"]) + bytes(7)
    wrole.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use))
    t = next(t for t in c["troops"] if t["id"] == 1100621)
    assert any(w.proto == troops.S2C_NEW_TROOP for w in s.sent) and not any(i["code"] == 355101501 for i in c["bag"])
    drag = bytes([1, 1]) + struct.pack("<Q", t["uid"]) + obf.u32(0xFFFFFFFF)
    wrole.handlers[troops.C2S_TO_DECK](s, pkt(troops.C2S_TO_DECK, drag))
    wrole.handlers[troops.C2S_LINEUPS](s, pkt(troops.C2S_LINEUPS, b""))
    out = bytes(s.sent[-1].buf)
    assert out[8] == 1 and out[9 + 9] == 1 and struct.unpack_from("<Q", out, 9 + 11)[0] == t["uid"]

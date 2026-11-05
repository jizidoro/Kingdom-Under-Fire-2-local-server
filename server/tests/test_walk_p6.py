"""Walkthrough part 6: the Lake Bled field (10202) and its missions (planning/walkthrough/p6-lake-bled.md).
Run: py -m pytest -q server/tests

The mission tests drive the merged mission rules (MissionLevelClear by IngSpot and difficulty, the 0x3f48 difficulty
reaching the room and its Hard / Hell troop rows, no win without a hostile fall) through the handlers only."""
import struct

import pytest

from kuf2 import combat, game, obf, quest, rules, tables, world, zone
from kuf2.packet import Reader

LAKE_BLED = 10202       # 1_BledLake_Field_New zone1 (10201 1_BledLake_Field is an old test spot without a zone file)
GREEN_FLOW = 10307      # [Lv.13] Green Flow, door 302 in Lake Bled; quest 1140211 MissionLevelClear ANY there
CLAWS = 10319           # [Lv.15] Hideout of Claws Brotherhood, door 305; quest 1140430
ESSEX_OUTSKIRTS = 10309 # [Lv.16] Outskirts of Essex Forest (totems); quest 1010901
INNER_COURT = 10321     # [Lv.17] Inner Court of the Temple of High Elves (climax); quest 1011005 MissionLevelClear NORMAL
DEATH_WOODS = 10312     # [Lv.18] Swidden Area of Death Woods; daily task 421900 MissionLevelClear HARD there

class Session:
    def __init__(self, char=None):
        self.data = {"char": char if char is not None else hero()}
        self.data["account"] = {"id": 1, "characters": [self.data["char"]]}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self):
        while self.pending:
            self.pending.pop(0)[1]()


class State:
    def __init__(self, account=None):
        self.account = account

    def save(self):
        pass

    def account_by_id(self, acct_id):
        return self.account

    def char_by_id(self, char_id):
        return self.account, self.account["characters"][0]


@pytest.fixture
def world_role():
    return world.make(State(), 0, "127.0.0.1", 0)


def hero(*qids, **kw):
    return {"id": 1, "class": 0, "level": 16, "name": "T", "look": "00" * 0x33, "gold": 0,
            "quests": {"active": {str(q): {"counts": [0] * 5} for q in qids}, "done": []}, **kw}


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def test_lake_bled_is_10202_with_a_zone_file_and_10201_is_a_test_spot():
    spots = tables.by_id("spottable")
    assert spots["10201"]["TestMap"] == "True" and spots["10201"]["State"] == "1"
    assert spots["10202"]["TestMap"] == "False" and spots["10202"]["Map_File"] == "1_BledLake_Field_New"
    assert game.is_field(LAKE_BLED) and zone.available(LAKE_BLED) and not zone.available(10201)
    z = zone.for_spot(LAKE_BLED)
    assert len(z["NPCTroopInfoData"]) == 2411 and len(z["SmartPropData"]) == 352 and len(z["NPCInfo"]) == 362


def test_the_lake_bled_doors_lead_to_its_missions():
    """The field's type-1 start points carry the MISSION warps (the doors); each warp's spot is a Battle spot whose
    parent is Lake Bled."""
    warps = {r["ID"]: r for r in tables.sections("warpinfo")["Move"]}
    doors = {p["LongWarpID"]: p for p in zone.for_spot(LAKE_BLED)["PlayerStartPointInfoData"] if p["SPTypes"] == 1}
    spots = {int(warps[str(w)]["SpotID"]) for w in doors if warps[str(w)]["WARP_POSITION"] == "MISSION"}
    assert spots == {10305, 10307, 10312, 10313, 10319, 10323, 10205, 10328}
    assert all(tables.by_id("spottable")[str(s)]["Parent_Spot"] == str(LAKE_BLED) for s in spots)
    assert int(warps["302"]["SpotID"]) == GREEN_FLOW and game.is_mission(GREEN_FLOW)


def test_lake_bled_rooms_start_at_the_zone_files_group_points(world_role):
    """Lake Bled has no measured start point (world.TOWN_ENTRY / START_POINTS); its spottable corner (-20000, 20000) is
    off the map. The world map's arrival, then the field-room redirect, leave the hero's saved position (the room's
    hero position, the camp revival point) at the zone file's group-0 start point; a group-2 entry from a room puts it
    and the escape block at the group-2 point, not (0, 0)."""
    s = Session(hero())
    s.data["char"].update(spot=10001, pos=list(world.START_POS))
    world_role.handlers[world.C2S_ENTER_TOWN_REQ](s, pkt(world.C2S_ENTER_TOWN_REQ, struct.pack("<I", LAKE_BLED)))
    world_role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(LAKE_BLED)))
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and s.data["battle_spot"] == LAKE_BLED
    assert s.data["char"]["pos"] == [95057, 0, 229733] and s.data["char"]["field_group"] == [LAKE_BLED, 0]
    s.sent.clear()
    world.send_field_entry(s, LAKE_BLED, 2, leave_battle=True)
    warp, esc = bytes(s.sent[0].buf), bytes(s.sent[1].buf)
    assert obf.dec_u32(warp[1:5]) == 602 and warp[5] == world.WARP_KIND_FIELD             # warpinfo 602: group 2
    assert obf.dec_pos_xz(esc[2 + 7:2 + 11], esc[2 + 13]) == (172172, 87442)
    assert s.data["char"]["pos"] == [172172, 0, 87442]
    assert world.start_point(10352, 0) == world.TOWN_ENTRY[10352]          # measured points still win


def test_the_outskirts_totems_are_not_what_the_win_rule_counts():
    """Walkthrough and quest 1010901 ('Destroy all 8 totems of Negation'): the totems are the objective. The offline
    rule counts the hostile troops (another team, worth exp): the orcs and the Chaotic Wedge Totem; the 8 Taint
    Totems (exp factor 0) are left out. An owner decision in the walkthrough doc."""
    troops = [t for t in zone.for_spot(ESSEX_OUTSKIRTS)["NPCTroopInfoData"] if t["IsActivated"]]
    totems = [t for t in troops if t["TroopTableID"] == 109290]
    wedge = [t for t in troops if t["TroopTableID"] == 109410]
    assert quest.kill_names(109290) == {"70001"} and quest.kill_names(109410) == {"70003"}   # Taint / Wedge Totem
    assert len(totems) == 8 and not any(game.hostile(t) for t in totems)
    assert len(wedge) == 1 and game.hostile(wedge[0])
    assert sum(game.hostile(t) for t in troops) == 18


def enter(spot, char, difficulty=0):
    """The mission door's Start (0x3f48 on the world connection), then the room's game login and its zone troops."""
    w = Session(char)
    w.data["char"].update(spot=LAKE_BLED)
    w.data.update(battle_spot=LAKE_BLED)
    world.make(State(), 0, "127.0.0.1", 0).handlers[world.C2S_ENTER_SPOT](
        w, pkt(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes([difficulty])))
    g = Session(char)
    g.data["battle"] = combat.Battle()
    game.make(State(w.data["account"]), 0).handlers[game.C2S_GAME_LOGIN](
        g, pkt(game.C2S_GAME_LOGIN, struct.pack("<IHI", 1, 0, spot)))
    game.spawn_zone_troops(g)
    return w, g


def spawned_id(g, uid):
    entry = next(bytes(w.buf) for w in g.sent if w.proto == game.S2C_ENTER_CELL_TROOP
                 and struct.unpack_from("<H", bytes(w.buf), 3 + 0x11)[0] == uid)
    return obf.dec_u32(entry[3 + 0x36:3 + 0x3a])


def win(g):
    for _ in range(100):                                # wave after wave (game.next_wave)
        alive = [u for u, t in g.data["zone_troops"].items()
                 if game.hostile(t) and u not in g.data.get("down", set())]
        if not alive or g.data.get("mission_won"):
            break
        for u in alive:
            game.mission_troop_down(g, State(), u)
    return any(w.proto == game.S2C_MISSION_COMPLETE for w in g.sent)


def test_a_green_flow_win_clears_only_green_flow():
    """Every MissionLevelClear names its mission in IngSpot: a Green Flow win must not clear the Claws Brotherhood
    (1140430) or Inner Court (1011005) quests held at the same time (ID1 ANY used to match any win)."""
    c = hero(1140211, 1140430, 1011005)
    w, g = enter(GREEN_FLOW, c)
    assert win(g)
    q = c["quests"]["active"]
    assert q["1140211"]["counts"][0] == 1 and q["1140430"]["counts"] == [0] * 5 and q["1011005"]["counts"] == [0] * 5


def test_the_door_sends_the_hero_to_the_mission_and_keeps_the_field_as_the_saved_spot():
    """Whether the room must be left first (0x4049, as for a quest's mission warp) is not verified live: walk/p2 does,
    p4 / p5 answer 0x3f41 at once. Either way the game server gets the mission and a relog lands in the field."""
    c = hero(1140211)
    w, g = enter(GREEN_FLOW, c)
    w.run_later()
    assert w.sent[-1].proto == world.S2C_GAME_SERVER
    assert struct.unpack_from("<I", bytes(w.sent[-1].buf), 8)[0] == GREEN_FLOW and c["spot"] == LAKE_BLED


def test_a_hard_door_spawns_the_hard_rows_and_counts_hard_clears():
    c = hero(daily={"date": rules.game_day(), "rewarded": 0,
                    "tasks": [{"id": 421900, "progress": 0, "state": 0}]})    # MissionLevelClear HARD at 10312
    w, g = enter(ESSEX_OUTSKIRTS, c, difficulty=1)
    totem = next(t["TroopID"] for t in zone.for_spot(ESSEX_OUTSKIRTS)["NPCTroopInfoData"]
                 if t["TroopTableID"] == 109290 and t["IsActivated"])
    assert spawned_id(g, totem) == 20109290 and g.data["battle"].troops[totem]["units"] == [2696]   # normal: 1348
    w, g = enter(DEATH_WOODS, c, difficulty=0)
    assert win(g) and c["daily"]["tasks"][0]["progress"] == 0
    w, g = enter(DEATH_WOODS, c, difficulty=1)
    assert win(g) and c["daily"]["tasks"][0]["progress"] == 1


def test_the_inner_court_is_not_won_by_an_ally_falling():
    """The Inner Court's 37 active troops are allies and staging troops worth no exp; two of its four held elf wizards
    (StringID 편입) are handed over at the start (MISSIONS-WIRING G5, Limit_Troop 2) and the other two with an elf
    blade join the first wave (G4, the nearest held force); its enemies all wait for the missing mission Lua. The
    first troop down 'won' it (no hostile troop left)."""
    c = hero(1011005)
    w, g = enter(INNER_COURT, c)
    allies = [u for u, t in g.data["zone_troops"].items() if not game.hostile(t)]
    assert len(allies) == 37 + 2 + 3 and any(game.hostile(t) for t in g.data["zone_troops"].values())   # 1st wave
    game.mission_troop_down(g, State(), allies[0])
    assert not any(x.proto == game.S2C_MISSION_COMPLETE for x in g.sent)
    assert c["quests"]["active"]["1011005"]["counts"] == [0] * 5

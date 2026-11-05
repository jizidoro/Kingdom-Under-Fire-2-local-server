"""Walkthrough part 3: Lunawing Sortie I / II (10361, 10362), the New Hampton Highway field (10351) and the New Hampton
Castle mission (10235). Data from the installed game's Info.pkg and zone files (planning/walkthrough/p3-luna-hampton.md).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import combat, game, obf, quest, tables, world, zone
from kuf2.obf import T1, T2
from kuf2.packet import Reader
from conftest import run_pending

ACCT = 7
BETTOR, VIRGIL = 1160218, 1160219       # "For the Saviours!" (NPC 6611 -> troop 155340), "Punishment for Betrayal" (6612)
CASTLE = 1160113                        # "Retaking New Hampton Castle": MissionLevelClear at 10235, EndSpot 10354


class Writer:
    def __init__(self):
        self.closing = False

    def is_closing(self):
        return self.closing


class Session:
    def __init__(self, c, spot=None):
        self.data = {"char": c, "account": {"id": ACCT, "characters": [c]}}
        if spot is not None:                        # the game connection of a field room
            self.data.update(spot=spot, battle=combat.Battle())
        self.sent, self.pending, self.w = [], [], Writer()

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


def accept_body(qid, mode=0):
    enc = obf.u32(qid)
    return bytes([T2[(enc[0] * 4 + mode) & 0xff]]) + enc


def char(active=(), done=()):
    return {"id": 1, "class": 0, "level": 8, "spot": 10351, "pos": [69000, 0, 157000],
            "quests": {"active": {str(q): {"counts": [0] * 5} for q in active}, "done": list(done)}}


def hit(uid, unit=0, by=0):
    """A 0x5053 hit report by troop `by` (the hero) on one unit of troop uid (layout as combat.parse_hit_props and
    combat.hit_source read it: +8 coded attacker troop, +0xa unit code, +0xd action 72)."""
    target = bytes([T2[uid >> 8], T1[uid & 0xff]]) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, unit + 3, 0])
    header = bytes(8) + bytes([T2[by >> 8], T1[by & 0xff]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72)
    return pkt(combat.C2S_HIT, header + struct.pack("<H", 1) + target + struct.pack("<H", 0))


def npc(spot, npc_id):
    return next(n for n in zone.for_spot(spot)["NPCInfo"] if n["TableID"] == npc_id)


@pytest.fixture
def room():
    """A world session and the game session of its field room 10351 (Lunawing Crash Site, New Hampton Highway)."""
    st = State()
    c = char(done=[1160211])
    ws, g = Session(c), Session(c, spot=10351)
    st.game_sessions[ACCT] = g
    return world.make(st, 0, "127.0.0.1", 0), game.make(st, 0), st, ws, g


def test_accepting_bettors_quest_turns_the_npc_into_his_troop_and_his_kill_counts(room):
    wrole, grole, st, ws, g = room
    wrole.handlers[quest.C2S_ACCEPT](ws, pkt(quest.C2S_ACCEPT, accept_body(BETTOR)))
    assert ws.sent[0].proto == quest.S2C_ACCEPT and bytes(ws.sent[0].buf)[:2] == bytes(2)
    uid = game.QUEST_TROOP_UID
    t = g.data["zone_troops"][uid]
    at = npc(10351, 6611)                                        # Bettor, "New Hampton Betrayer", inside QuestBound 6317
    assert (t["TroopTableID"], t["PosX"], t["PosZ"], t["TeamNum"]) == (155340, at["PosX"], at["PosZ"], game.NP_TEAM)
    enter = next(w for w in g.sent if w.proto == game.S2C_ENTER_CELL_TROOP)
    assert bytes(enter.buf)[3 + 0x36:3 + 0x3a] == obf.u32(155340) and bytes(enter.buf)[3 + 0x11:3 + 0x13] == \
        struct.pack("<H", uid)
    assert [w.proto for w in g.sent[-3:]] == [game.S2C_ENTER_CELL_TROOP, game.S2C_SET_SPAWN_AI, game.S2C_SCRIPT_ACTION]
    assert struct.unpack("<3I", bytes(g.sent[-1].buf)) == (game.ACT_ENABLE_ALL_TROOPS, 1, 1)
    assert [d for d, _ in g.pending] == [90]                    # nptrooptable QuestSpawnedNPDisable_Time
    g.data["battle"].add_hero(0, 403, c=game.hero_combatant(g.data["char"]))     # level 8, starter kit
    for _ in range(1000):                                        # 1153 hp, defence 515: about 9 a hit
        grole.handlers[combat.C2S_HIT](g, hit(uid))
        if not any(g.data["battle"].troops[uid]["units"]):
            break
    q = g.data["char"]["quests"]["active"][str(BETTOR)]
    assert q["counts"][0] == 1 and quest.done(tables.by_id("questtable")[str(BETTOR)], q)   # NPGroupKill 1000289
    assert [d for d, fn in g.pending if d != combat.PEACE_S and "expire_status" not in fn.__qualname__] == [90]
    # no respawn (the hero's peace timer and the statuses his hits put on the troop aside)
    g.sent.clear()
    g.pending[0][1]()                                            # time up: he already fell, nothing leaves
    assert g.sent == []


def test_a_betrayer_left_standing_leaves_when_his_time_is_up_and_comes_back_on_a_new_accept(room):
    wrole, grole, st, ws, g = room
    ws.data["char"]["quests"]["done"].append(1160213)
    wrole.handlers[quest.C2S_ACCEPT](ws, pkt(quest.C2S_ACCEPT, accept_body(VIRGIL)))
    uid = game.QUEST_TROOP_UID
    at = npc(10351, 6612)
    assert g.data["zone_troops"][uid]["TroopTableID"] == 155290 and g.data["zone_troops"][uid]["PosX"] == at["PosX"]
    wrole.handlers[quest.C2S_ACCEPT](ws, pkt(quest.C2S_ACCEPT, accept_body(VIRGIL)))       # refused: already held
    assert len(g.data["zone_troops"]) == 1
    g.pending.pop()[1]()
    assert bytes(g.sent[-1].buf) == struct.pack("<HH", 1, uid) and g.sent[-1].proto == game.S2C_TROOP_LEAVE
    assert uid not in g.data["zone_troops"] and uid not in g.data["battle"].troops
    wrole.handlers[quest.C2S_ABANDON](ws, pkt(quest.C2S_ABANDON, obf.u32(VIRGIL)))
    wrole.handlers[quest.C2S_ACCEPT](ws, pkt(quest.C2S_ACCEPT, accept_body(VIRGIL)))
    assert g.data["zone_troops"][uid]["Quest"] == VIRGIL          # Virgil is back where the NPC stood


def test_no_spawn_outside_a_field_room_or_for_quests_without_one(room):
    wrole, grole, st, ws, g = room
    assert game.spawn_quest_troop(g, 1160208) is None             # a kill quest on zone troops: nothing to spawn
    g.data.update(spot=10235)                                    # a mission room: not a field
    assert game.spawn_quest_troop(g, BETTOR) is None
    st.game_sessions.clear()                                     # in the town state / no room: accept still answers
    wrole.handlers[quest.C2S_ACCEPT](ws, pkt(quest.C2S_ACCEPT, accept_body(BETTOR)))
    assert ws.sent[-1].proto == quest.S2C_ACCEPT and "zone_troops" not in g.data


def test_the_castle_entered_by_its_door_ends_on_the_castle_side(room):
    wrole, grole, st, ws, g = room
    c = ws.data["char"]
    c["quests"]["active"][str(CASTLE)] = {"counts": [0] * 5}
    ws.data["game_addr"] = ("127.0.0.1", 25004)
    from kuf2 import troops
    for slot in (1, 2):                                          # New Hampton wants two organised (Min_Limit_Troop)
        troops.lineup(c)["slots"][slot] = troops.grant(c, 1)[0]["uid"]
    wrole.handlers[world.C2S_ENTER_SPOT](ws, pkt(world.C2S_ENTER_SPOT, obf.u32(10235) + bytes(2)))
    assert c["mission"] == {"spot": 10235, "quest": CASTLE, "back": 10354}
    assert ws.sent[-1].proto == world.S2C_GAME_SERVER and c["spot"] == 10351      # the save stays on the field
    m = Session(c, spot=10235)
    game.mission_won(m, st)
    run_pending(m)                                      # the director's ending lines, then the window
    assert c["quests"]["active"][str(CASTLE)]["counts"][0] == 1                    # MissionLevelClear ANY
    grole.handlers[game.C2S_MISSION_LEAVE](m, pkt(game.C2S_MISSION_LEAVE, b""))
    out = bytes(m.sent[-1].buf)
    assert m.sent[-1].proto == game.S2C_MISSION_LEAVE and out[4:8] == obf.u32(10354)
    assert c["spot"] == 10354 and c["pos"] == list(world.zone_start(10354)) and "mission" not in c
    c["mission"] = {"spot": 10358, "quest": 1150301, "back": 10350}                # left over from an escaped mission
    del c["quests"]["active"][str(CASTLE)]
    wrole.handlers[world.C2S_ENTER_SPOT](ws, pkt(world.C2S_ENTER_SPOT, obf.u32(10235) + bytes(2)))
    assert c["mission"]["quest"] is None and c["mission"]["back"] == c["spot"]   # no quest here: back to the saved spot


def test_the_castle_spawns_single_siege_engines_and_its_win_needs_the_walls_and_vert():
    c = char(active=[CASTLE])
    m = Session(c, spot=10235)
    game.spawn_zone_troops(m)
    troops, hp = m.data["zone_troops"], m.data["battle"].troops
    treb = next(u for u, t in troops.items() if t["TroopTableID"] == 135300)      # the "incorporated" trebuchet
    assert hp[treb]["units"] == [5449]                           # one engine (its zone UnitNum says 48)
    infantry = next(u for u, t in troops.items() if t["TroopTableID"] == 135040 and t["UnitNum"])
    assert len(hp[infantry]["units"]) == troops[infantry]["UnitNum"]          # a 0-unit formation keeps the zone size
    enemies = sorted(troops[u]["TroopTableID"] for u, t in troops.items() if game.hostile(t))
    assert enemies == [135200] + [135380] * 5  # the castle wall 49444 (the table's start wakes it: the siege's target)
                                              # and the five staging segments; the opening-cutscene Vert 135720 (force
                                              # 49000 "연출") spawns but is no win target (MISSIONS-WIRING G2)
    assert hp[next(u for u, t in troops.items() if t["TroopTableID"] == 135720)]["units"] == [958]
    given = [struct.unpack("<5I", bytes(w.buf)) for w in m.sent if w.proto == game.S2C_SCRIPT_ACTION
             and struct.unpack_from("<I", bytes(w.buf))[0] == game.ACT_CHANGE_FORCE]
    hs = game.TROOPAITYPE_HEROSUPPORT                            # the stance the client gives the player's troops
    assert sorted(given) == [(game.ACT_CHANGE_FORCE, 0, 10134, game.MY_SLOT, hs),   # 편입_오르간 organ cannon
                             (game.ACT_CHANGE_FORCE, 0, treb, game.MY_SLOT, hs)]     # 편입_투석기 trebuchet
    assert treb == 40100 and troops[treb]["TeamNum"] == game.PLAYER_TEAM


def test_field_troops_stay_with_their_zone_teams():
    s = Session(char(), spot=10351)
    game.spawn_zone_troops(s)
    assert not any(w.proto == game.S2C_SCRIPT_ACTION for w in s.sent)


def test_a_mission_clear_counts_only_for_the_quest_of_that_mission():
    c = char(active=[CASTLE, 1150703])
    st = State()
    game.mission_won(Session(c, spot=10233), st)                 # replaying Tower of Moonlight does not take the castle
    assert c["quests"]["active"][str(CASTLE)]["counts"][0] == 0 == c["quests"]["active"]["1150703"]["counts"][0]
    game.mission_won(Session(c, spot=10361), st)                 # Lunawing Sortie I: IngSpot1 of 1150703
    assert c["quests"]["active"]["1150703"]["counts"][0] == 1 and c["quests"]["active"][str(CASTLE)]["counts"][0] == 0


def test_the_sortie_quest_enters_lunawing_sortie_one_and_ends_at_the_crash_site():
    s = Session(char(active=[1150703]))
    s.data.update(game_addr=("127.0.0.1", 25004), battle_spot=10359)
    quest.spot_warp(s, State(), 1150703)                         # SpotWarp 621: 10361 MISSION, group 1
    assert s.data["char"]["mission"] == {"spot": 10361, "quest": 1150703, "back": 10351}
    assert game.is_mission(10361) and game.is_mission(10362) and game.is_mission(10235)


# Part 3's field chain on the New Hampton Highway (10351): every condition has an offline source in the zone.
CHAIN = [1160105, 1160102, 1160103, 1160104, 1160108, 1160101, 1160106, 1160107, 1160200, 1160201, 1160202, 1160203,
         1160204, 1160205, 1160206, 1160207, 1160208, 1160209, 1160210, 1160211, 1160218, 1160213, 1160219, 1160214,
         1160212, 1160215, 9900104, 1160216, 1160113]


def sources(qid):
    """[(condition, source)] for each condition of quest qid; source None when nothing offline can meet it."""
    q = tables.by_id("questtable")[str(qid)]
    z = zone.for_spot(10351)
    npcs = {n["TableID"] for n in z["NPCInfo"]}
    bounds = {b["QuestBoundID"] for b in z["QuestBound"]}
    boxes = {p["SmartPropTypeID"] for p in z["SmartPropData"]}
    troops = {t["TroopTableID"] for t in z["NPCTroopInfoData"] if t["IsActivated"]}
    spawn = q.get("QuestAccept_SpawnNPTroop_ID", "-")
    out = []
    for n in range(1, 6):
        kind, id1, id2 = q[f"Complete{n}_Type"], q[f"Complete{n}_ID1"], q[f"Complete{n}_ID2"]
        if kind in ("", "-"):
            continue
        src = None
        if kind == "Talk":
            src = int(id1) in npcs and f"NPC {id1}"
        elif kind == "QuestBound":
            src = int(id1) in bounds and f"area {id1}"
        elif kind == "ItemGain":
            src = next((f"box {b}" for b in boxes if (game.prop_row(b) or {}).get("GrantItem1_IB") == id1), None)
        elif kind in ("NPNameKill", "NPGroupKill"):
            names = quest.kill_names if kind == "NPNameKill" else quest.kill_groups
            src = next((f"troop {t}" for t in troops if id2 in names(t)), None) or \
                (spawn.isdigit() and id2 in names(int(spawn)) and f"quest spawn {spawn}")
        elif kind == "MissionLevelClear":
            src = game.is_mission(int(q[f"IngSpot{n}"])) and f"mission {q[f'IngSpot{n}']}"
        out.append(((kind, id1, id2), src or None))
    return out


@pytest.mark.parametrize("qid", CHAIN)
def test_every_condition_of_the_highway_chain_has_an_offline_source(qid):
    q = tables.by_id("questtable")[str(qid)]
    npcs = {n["TableID"] for n in zone.for_spot(10351)["NPCInfo"]}
    assert int(q["Start_Value"]) in npcs and (q["EndSpot"] != "10351" or int(q["Finish_Value"]) in npcs)
    assert all(src for _, src in sources(qid)), sources(qid)


def test_the_chain_links_from_the_sortie_to_the_castle():
    rows = tables.by_id("questtable")
    assert rows["1150703"]["Require1_Value"] == "1150702" and rows["1160105"]["Require1_Value"] == "1150703"
    for qid in CHAIN[1:]:
        reqs = [rows[str(qid)][f"Require{k}_Value"] for k in (1, 2, 3)
                if rows[str(qid)][f"Require{k}_Type"] in ("FinishedQuest", "FinishOrDoingQuest")]
        assert reqs and all(int(r) in CHAIN or r == "1150703" for r in reqs), (qid, reqs)


@pytest.mark.parametrize("cls", range(6))
def test_every_reward_of_the_chain_is_a_real_item_for_every_class(cls):
    for qid in [1150703] + CHAIN:
        row = tables.by_id("questtable")[str(qid)]
        wanted = sum(row[f"Item{k}_Type"] in ("Normal", "NormalCategory") for k in range(1, 6))
        assert len(quest.reward_items(row, cls)) == wanted, qid

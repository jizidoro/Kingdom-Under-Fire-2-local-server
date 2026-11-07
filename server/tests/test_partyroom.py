"""The party's mission room (server/kuf2/party.py, changetroop.py, game.send_start_header): the AI PCs a party room
employed as players on the player's team, the reserve troops and the deploy cap in the room start, each through the
registered handlers (the party's start 0x5472 on the world role, the game login 0x5084 and the loading's end on the
game role). The byte places are the client's readers' (those modules' docstrings). No shipped spot lets the client
employ an AI PC in a mission, so these rooms set the list a party's start would leave. The dig and the verdicts:
planning/agents/reports/2026-11-05_contract3-partyroom.md.
Run: py -m pytest -q server/tests"""
import random
import struct

import pytest

from kuf2 import changetroop as ct, combat, game, obf, party, pvp, skills, status, tables, world, zone
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE, Writer
from test_army import army
from test_pvp_ai import Save, Session, ask, placed, records, start_troops, state, structs, swing
from test_rewards import Session as WorldSession, State, win

RIFT, COOP, ONE_GROUP = 10335, 10305, 10310     # four start groups, Limit_SubTroop 7; two groups; one group
PLAIN, NO_RESERVE, FIELD, BARE = 10234, 10370, 10354, 20923     # no %Point; Limit_SubTroop 0; a field; a bare battle room
AIPC, AIPC2, AIPC3 = 11501, 109, 11502          # %AIPCPreset: AI sets 1, 2, 1


def login(spot, aipc=None, c=None):
    """A game session through its login, the account's world session as a party's start leaves it."""
    c = c or army(1, 2)[0]
    c.setdefault("spot", world.START_SPOT)
    st = Save(c)
    w = Session()
    st.world_sessions = {1: w}
    if aipc is not None:
        w.data["party_aipc"] = dict(aipc)
    role = game.make(st, 0)
    s = Session()
    start = ask(role, s, game.C2S_GAME_LOGIN, struct.pack("<IHI", c["id"], 0, spot))
    return role, s, st, c, start, w


def entered(spot, aipc=None, c=None):
    """The same through the loading's end, its timers run up to the room's +3 s block (the later ones repeat)."""
    role, s, st, c, start, w = login(spot, aipc, c)
    ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))
    run_start(s)
    return role, s, st, c


def run_start(s):
    for _ in range(40):
        s.pending.sort(key=lambda p: p[0])
        if not s.pending or s.pending[0][0] > 3.0:
            return
        s.pending.pop(0)[1]()


def actions(s):
    """Every 0x5087 the room sent, as lists of u32."""
    out = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_SCRIPT_ACTION and len(b) % 4 == 0:
            out.append(list(struct.unpack(f"<{len(b) // 4}I", b)))
    return out


def old_start(s, spot, c, deck):
    """The room start of a room with one player and no reserve, as game.send_start_header wrote it before them."""
    h = bytearray(0x1a)
    struct.pack_into("<H", h, 0x01, game.MY_SLOT)
    h[0x07] = game.MODE_PVE
    struct.pack_into("<H", h, 0x10, game.MY_SLOT)
    struct.pack_into("<H", h, 0x12, game.MY_SLOT)
    h[0x16:0x1a] = obf.u32(spot)
    rec = struct.pack("<HH", game.PLAYER_TEAM, game.MY_SLOT) + bytes([1]) + struct.pack("<H", 1 + len(deck))
    w = Writer(game.S2C_START_TROOP_INFO).u16(1 + len(deck))
    game.write_troop(w, slot=0, uid=1, troop_id=game.HERO_TROOP_ID, leader_id=c["class"], leader_level=c["level"],
                     abilities=sorted(skills.battle_abilities(c).items()))
    for uid, t in deck.items():
        game.write_deck_troop(w, uid, t, c)
    frames = [Writer(game.S2C_SPOT_ROOM_START).obool(False).raw(bytes(h)).u16(1).raw(rec),
              Writer(game.S2C_START_PLAYER_INFO).u16(1).raw(bytes(game.player_struct(c, spot, deck.values())))
              .cstr(c["name"]).cstr(""), w, Writer(game.S2C_SPOT_ROOM_START).obool(True)]
    return [(f.proto, bytes(f.buf)) for f in frames]


# --- the live path: a room with neither stays byte for byte what it was ---

@pytest.mark.parametrize("spot, deck", [(PLAIN, (1, 2)), (PLAIN, (1, 2, 4, 6)), (NO_RESERVE, (1, 2)), (NO_RESERVE, (1, 2, 4, 6)),
                                        (FIELD, (1, 2)), (BARE, (1, 2, 4))])
def test_a_room_without_ai_pcs_or_a_reserve_starts_byte_for_byte_as_before(spot, deck):
    c = army(1, 2, 1, 2, deck=deck)[0]
    role, s, st, c, start, w = login(spot, c=c)
    assert start[1:] == old_start(s, spot, c, s.data["deck"])
    assert "party_ai" not in s.data and s.data["reserve"] == {}
    ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))
    run_start(s)
    enemy = {1} if spot == BARE else set()              # the bare room's test enemy; the zone's own uids are above
    assert {u for u in placed(s) if u < pvp.AI_TROOP} <= {0, *s.data["deck"], *enemy}
    assert not any(a[0] == game.ACT_ENABLE_TROOP and a[3] == 0 for a in actions(s))     # no disable follows


def test_a_world_session_without_a_party_leaves_the_room_alone():
    c = army(1, 2)[0]
    st = Save(c)                                        # no world_sessions at all (the fake of older tests)
    role = game.make(st, 0)
    s = Session()
    ask(role, s, game.C2S_GAME_LOGIN, struct.pack("<IHI", c["id"], 0, PLAIN))
    assert "party_ai" not in s.data
    role, s, st, c, start, w = login(PLAIN, aipc={})    # a party's start with nobody employed
    assert "party_ai" not in s.data and records(start[1][1])[1] == [(0, game.MY_SLOT, OBOOL_FALSE, 1 + len(s.data["deck"]))]


# --- the AI PCs ---

def test_the_ai_pcs_are_more_players_of_the_players_team():
    role, s, st, c, start, w = login(COOP, {1: AIPC, 3: AIPC2})
    ai = s.data["party_ai"]
    deck = len(s.data["deck"])
    assert [p["pid"] for p in ai] == [pvp.AI_PLAYER + 1, pvp.AI_PLAYER + 3] and [p["ai"] for p in ai] == [AIPC, AIPC2]
    assert [p for p, _ in start[1:]] == [game.S2C_SPOT_ROOM_START, game.S2C_START_PLAYER_INFO, game.S2C_START_TROOP_INFO,
                                         game.S2C_SPOT_ROOM_START]
    header, recs = records(start[1][1])
    assert recs == [(game.PLAYER_TEAM, game.MY_SLOT, OBOOL_FALSE, 1 + deck)] + [
        (game.PLAYER_TEAM, p["pid"], OBOOL_FALSE, 1 + len(p["troops"])) for p in ai]
    assert header[0] == 0 and struct.unpack_from("<H", header, 1)[0] == game.MY_SLOT    # still his room: no reserve here
    # 0x3f4f: the AI flag +0xa9 is the preset's ActiveTroopAISet, and only theirs
    blocks = structs(start[2][1])
    assert [name for _, name in blocks] == [c["name"]] + [p["name"] for p in ai]
    assert [struct.unpack_from("<I", b, 0xa9)[0] for b, _ in blocks] == [0, 1, 2]
    assert blocks[0][0] == game.player_struct(c, COOP, s.data["deck"].values())
    # 0x3f50: in record order, the first of each player his hero
    got = start_troops(start[3][1])
    assert len(got) == sum(r[3] for r in recs) == struct.unpack_from("<H", start[3][1])[0]
    at = 1 + deck
    for p in ai:
        hero, rest = got[at], got[at + 1:at + 1 + len(p["troops"])]
        assert hero["uid"] == p["hero"] and hero["troop"] == game.HERO_TROOP_ID and hero["slot"] == 0
        assert hero["leader"] == (p["char"]["class"], p["char"]["level"]) and hero["hp"] == p["hp"]
        assert set(p["kit"]) == set(hero["abilities"])
        assert [(t["uid"], t["slot"], t["troop"], t["units"]) for t in rest] == [
            (t["uid"], t["slot"], t["id"], t["units"]) for t in p["troops"]]
        at += 1 + len(p["troops"])
    assert start[4] == (game.S2C_SPOT_ROOM_START, bytes([OBOOL_TRUE]))


def test_the_list_goes_to_the_next_room_only():
    role, s, st, c, start, w = login(COOP, {1: AIPC})
    assert "party_aipc" not in w.data and len(s.data["party_ai"]) == 1
    again = Session()
    got = ask(role, again, game.C2S_GAME_LOGIN, struct.pack("<IHI", c["id"], 0, COOP))
    assert "party_ai" not in again.data and len(records(got[1][1])[1]) == 1


def test_the_party_rooms_start_brings_its_ai_pcs_into_the_mission_room():
    # the whole way: the room's list on the world session (0x4063 cannot reach a mission: the module docstring), the
    # start 0x5472, the client's login on the game connection
    c = army(1, 2)[0]
    c.update(spot=world.START_SPOT, name="Aldric")
    st = State()
    st.world_sessions = {}
    world_role = world.make(st, 0, "127.0.0.1", 0)
    party.make(world_role, st)
    ws = WorldSession(c)
    st.world_sessions[1] = ws
    t = party.team(ws)
    t["party"], t["room"] = True, {"spot": COOP, "difficulty": 0, "ready": False, "aipc": {2: AIPC}, "asked": COOP}
    replies = ask(world_role, ws, party.C2S_START)
    assert replies[0] == (party.S2C_START, bytes(2)) and ws.data["party_aipc"] == {2: AIPC}
    assert 0x4065 not in [p for p, _ in replies]        # a joining member's list: a room of one has no joiner
    st.char_by_id = lambda cid: (ws.data["account"], c)
    role = game.make(st, 0)
    s = Session()
    start = ask(role, s, game.C2S_GAME_LOGIN, struct.pack("<IHI", c["id"], 0, COOP))
    assert [r[1] for r in records(start[1][1])[1]] == [game.MY_SLOT, pvp.AI_PLAYER + 2]
    assert "party_aipc" not in ws.data


def test_a_rift_map_other_than_the_rooms_keeps_the_room_s_ai_pcs():
    # the preset is the room's spot's (ActiveSpot), the mission map another: the list is read by id
    assert party.aipc_preset(AIPC, COOP) is None
    assert [p["ai"] for p in party.ai_players({1: AIPC})] == [AIPC]


def test_the_loading_end_places_them_on_their_own_start_groups():
    role, s, st, c = entered(RIFT, {1: AIPC, 3: AIPC2})
    groups = zone.for_spot(RIFT)["PlayerStartPointInfoData"]
    got = placed(s)
    for p in s.data["party_ai"]:
        places = groups[p["seat"]]["StartPointInfoData"]
        at = lambda k: (round(places[k]["PosX"]), round(places[k]["PosZ"]))
        hero = got[p["hero"]]
        assert (hero["team"], hero["owner"], hero["hp"]) == (game.PLAYER_TEAM, p["pid"], p["hp"])
        assert hero["pos"] == pytest.approx(at(0), abs=2) and hero["flags"] == game.HERO_FLAGS
        assert hero["stats"]                                # a hero's speed is in this block
        for t in p["troops"]:
            st_ = got[t["uid"]]
            assert (st_["team"], st_["owner"], st_["troop"], st_["units"]) == (game.PLAYER_TEAM, p["pid"], t["id"], t["units"])
            assert st_["hp"] == t["unit_hp"] * t["units"] and st_["pos"] == pytest.approx(at(t["slot"]), abs=2)
    # 0x50b8 for each, after every 0x50cb of theirs
    theirs = {u for p in s.data["party_ai"] for u in (p["hero"], *[t["uid"] for t in p["troops"]])}
    cells = [k for k, w in enumerate(s.sent) if w.proto == game.S2C_ENTER_CELL_TROOP and state(bytes(w.buf), 3)["uid"] in theirs]
    infos = [k for k, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_TROOP_INFO and state(bytes(w.buf))["uid"] in theirs]
    assert len(cells) == len(infos) == len(theirs) and max(cells) < min(infos)
    # the room's enable-all, three seconds on, is what shows them
    assert [game.ACT_ENABLE_ALL_TROOPS, 1, 1] in actions(s)


def test_a_map_with_fewer_start_groups_seats_them_beside_the_player():
    role, s, st, c = entered(ONE_GROUP, {1: AIPC, 2: AIPC3})
    x, _, z = game.start_pos(s)
    got = placed(s)
    a, b = s.data["party_ai"]
    assert got[a["hero"]]["pos"] == pytest.approx((x, z + 300), abs=2)
    assert got[b["hero"]]["pos"] == pytest.approx((x, z + 600), abs=2)
    assert got[b["troops"][0]["uid"]]["pos"] == pytest.approx((x + 300, z + 600), abs=2)


def test_their_battle_records_are_allies_of_the_player():
    role, s, st, c = entered(COOP, {1: AIPC})
    p, = s.data["party_ai"]
    battle = s.data["battle"]
    for uid in (p["hero"], *[t["uid"] for t in p["troops"]]):
        assert uid in battle.troops and status.side(s, uid) == 0 and not status.players(s, uid)
        assert not game.hostile(s.data["zone_troops"][uid]) and status.alive(s, uid)
    assert battle.troops[p["hero"]]["leader"] and battle.troops[p["hero"]]["c"]["team"] == game.PLAYER_TEAM
    assert not battle.troops[p["hero"]].get("hero")     # a troop's record: its fall is no death window


def hit_down(role, s, uid, foe):
    """Enemy troop foe's hero-style blows fell troop uid: its units and leader at 1 hp first, so one swing each does."""
    t = s.data["battle"].troops[uid]
    t["units"] = [1 if hp > 0 else 0 for hp in t["units"]]
    if t.get("leader"):
        t["leader"] = 1
    got = []
    for _ in range(40):
        if combat.Battle.total(t) <= 0:
            return got
        units = [i for i, hp in enumerate(t["units"]) if hp > 0] or [combat.LEADER]
        got += ask(role, s, combat.C2S_HERO_HIT, swing(foe, [(uid, units)]))
    raise AssertionError(f"troop {uid} did not fall")


def test_an_ai_pcs_fall_is_a_troops_and_pays_nothing():
    role, s, st, c = entered(COOP, {1: AIPC})
    p, = s.data["party_ai"]
    foe = next(u for u, z in s.data["zone_troops"].items() if game.hostile(z))
    exp, gold = c.get("exp", 0), c.get("gold", 0)
    s.sent.clear()
    got = hit_down(role, s, p["hero"], foe) + hit_down(role, s, p["troops"][0]["uid"], foe)
    protos = [q for q, _ in got]
    assert game.S2C_DEATH_WINDOW not in protos and game.S2C_COMBAT_BONUS not in protos
    assert s.data.get("hero_deaths", 0) == 0 and s.data.get("troop_wipes", 0) == 0
    assert (c.get("exp", 0), c.get("gold", 0)) == (exp, gold) and not s.data.get("mission_won")
    assert p["hero"] in s.data["down"] and not status.alive(s, p["hero"])
    feeds = [b[:4] for q, b in got if q == game.S2C_KILL_FEED]
    assert feeds == [struct.pack("<HH", foe, p["hero"]), struct.pack("<HH", foe, p["troops"][0]["uid"])]


def test_an_ai_pcs_kill_is_the_allys_alone():
    # status.fights_player: a troop the player never fought pays him nothing, whoever fells it; it still counts as down
    role, s, st, c = entered(COOP, {1: AIPC})
    p, = s.data["party_ai"]
    foe = next(u for u, z in s.data["zone_troops"].items() if game.hostile(z))
    exp = c.get("exp", 0)
    got = hit_down(role, s, foe, p["hero"])
    assert game.S2C_COMBAT_BONUS not in [q for q, _ in got] and c.get("exp", 0) == exp and foe in s.data["down"]


def test_the_mission_is_won_with_the_ai_pcs_standing_and_not_by_their_fall():
    random.seed(3)
    role, s, st, c, start, w = login(COOP, {1: AIPC})
    ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))
    p, = s.data["party_ai"]
    win(s, st)
    assert s.data["mission_won"] and p["hero"] not in s.data.get("down", set())


def test_no_win_comes_from_ai_pcs_alone():
    role, s, st, c = entered(COOP, {1: AIPC})
    p, = s.data["party_ai"]
    for uid in (p["hero"], *[t["uid"] for t in p["troops"]]):
        game.mission_troop_down(s, st, uid)
    assert not s.data.get("mission_won")


# --- the reserve and the cap ---

def deep_deck():
    """Five troops in the main deck's slots 1..5: the rift takes three (Limit_Troop_1), the others wait."""
    return army(1, 2, 1, 2, 1, deck=(1, 2, 3, 4, 5))[0]


def test_the_rift_room_start_carries_the_reserve_and_the_cap():
    role, s, st, c, start, w = login(RIFT, c=deep_deck())
    deck, reserve = s.data["deck"], s.data["reserve"]
    assert set(deck) == {1, 2, 3} and set(reserve) == {4, 5}
    header, recs = records(start[1][1])
    assert header[0] == 3                                # the HUD slots' cap: min(3, Limit_Troop_1)
    assert recs == [(game.PLAYER_TEAM, game.MY_SLOT, OBOOL_FALSE, 1 + 3 + 2)]
    got = start_troops(start[3][1])
    assert [t["slot"] for t in got] == [0, 1, 2, 3, 4, 5]
    assert [t["troop"] for t in got[1:]] == [t["id"] for t in (*deck.values(), *reserve.values())]
    # each entry the same as a deck troop's; the struct's pools count the deployed ones only
    (block, _), = structs(start[2][1])
    assert block == game.player_struct(c, RIFT, deck.values())


def test_the_rest_of_the_room_is_the_deployed_ones_alone():
    role, s, st, c = entered(RIFT, c=deep_deck())
    deck, reserve = s.data["deck"], s.data["reserve"]
    assert not set(placed(s)) & set(reserve)             # no 0x50cb
    infos = [state(bytes(w.buf))["uid"] for w in s.sent if w.proto == game.S2C_MISSION_TROOP_INFO]
    assert not set(infos) & set(reserve)                 # no 0x50b8
    assert not set(s.data["battle"].troops) & set(reserve)
    enabled = [a[2] for a in actions(s) if a[0] == game.ACT_ENABLE_TROOP and a[3] == 1]
    assert set(deck) <= set(enabled) and not set(enabled) & set(reserve)


def test_the_enable_all_is_followed_by_the_reserves_own_disable():
    role, s, st, c = entered(RIFT, c=deep_deck())
    acts = actions(s)
    at = acts.index([game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    assert acts[at + 1:at + 3] == [[game.ACT_ENABLE_TROOP, 0, 4, 0, 1], [game.ACT_ENABLE_TROOP, 0, 5, 0, 1]]
    # every later one too, whoever sends it, and for the reserve as it stands then
    s.sent.clear()
    ct.enter(s, 4)
    game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    assert actions(s) == [[game.ACT_ENABLE_ALL_TROOPS, 1, 1], [game.ACT_ENABLE_TROOP, 0, 5, 0, 1]]
    s.sent.clear()
    ct.leave(s, 1)
    game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    assert sorted(a[2] for a in actions(s)[1:]) == [1, 5]


def test_a_player_with_nobody_to_spare_still_gets_the_spots_cap():
    role, s, st, c, start, w = login(RIFT, c=army(1, deck=(1,))[0])
    assert s.data["reserve"] == {} and records(start[1][1])[0][0] == 3
    assert records(start[1][1])[1] == [(game.PLAYER_TEAM, game.MY_SLOT, OBOOL_FALSE, 2)]


def test_a_bare_battle_room_takes_no_reserve_though_its_spot_lists_one():
    # the test enemy is uid 1 and the room has no deck: a reserve would stand on it (game.deploy)
    assert ct.reserve_limit(BARE) == 7 and game.room_kind(BARE) == "battle"
    role, s, st, c, start, w = login(BARE, c=deep_deck())
    assert s.data["reserve"] == {} and records(start[1][1])[0][0] == 0


def test_the_ai_room_of_pvp_keeps_its_own_start():
    # 20954 goes to pvp.send_start before any of this: sixteen records, the header's first byte as it was
    role, s, st, c, start, w = login(20954)
    header, recs = records(start[1][1])
    assert len(recs) == 16 and header[0] == 0 and "reserve" not in s.data


def test_ai_pcs_and_a_reserve_share_one_room_in_record_order():
    role, s, st, c, start, w = login(RIFT, {2: AIPC}, c=deep_deck())
    p, = s.data["party_ai"]
    header, recs = records(start[1][1])
    assert header[0] == 3 and [r[3] for r in recs] == [6, 1 + len(p["troops"])]
    got = start_troops(start[3][1])
    assert [t["slot"] for t in got[:7]] == [0, 1, 2, 3, 4, 5, 0] and got[6]["uid"] == p["hero"]


# --- the panel nothing opens ---

def test_no_room_has_the_team_points_panel():
    # 0x50d9 acts only while sub 0x75 is open, and that is Spot_Type 5 alone (0x140cee6db): 880391, a TestMap with no
    # zone file, so no room is built on it
    rows = tables.by_id("spottable")
    invasion = [k for k, r in rows.items() if r.get("Spot_Type") == "Invasion"]
    assert invasion == ["880391"] and rows["880391"]["TestMap"] == "True"
    assert not game.is_mission(880391) and not zone.available(880391)
    role, s, st, c = entered(RIFT, {1: AIPC}, c=deep_deck())
    assert 0x50d9 not in [w.proto for w in s.sent]


# --- what a client's short or odd report does in such a room ---

def test_a_report_of_an_unknown_or_reserve_uid_is_harmless():
    role, s, st, c = entered(RIFT, {1: AIPC}, c=deep_deck())
    for body in (b"", b"\xff", bytes(40)):
        ask(role, s, game.C2S_TROOP_SYNC, body)
    p, = s.data["party_ai"]
    ask(role, s, game.C2S_TROOP_BOUND, struct.pack("<H", 4))            # the client binds what 0x3f50 built
    assert 4 in s.data["bound"]
    ask(role, s, combat.C2S_HERO_HIT, swing(p["hero"], [(4, [0])]))     # a blow on a troop that stands nowhere
    assert 4 in s.data["reserve"] and 4 not in s.data["battle"].troops

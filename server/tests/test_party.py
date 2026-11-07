"""The party of one, its recruitment notice and the party waiting room (planning/todo/CONTRACT-COMPLETE-PLAN.md,
family 5; server/kuf2/party.py), each request through its registered handler on the world role.
Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import struct

from kuf2 import game, obf, party, tables, world
from kuf2.packet import Reader
from test_rewards import Session, State, char

RIFT, RAID, INVASION, EXTREME = 10335, 20950, 20908, 20349     # Spot_Sub_Type RIFT, Raid_16, PVE_AGGRESSiON, "-"
COOP = 10305                    # Stalker Forest: PVE_NORMAL, Limit_Party 4, Normal and Hard, no troop minimum
STORY = 10358                   # Grey Fog: Limit_Party 1
AIPC_SPOT, AIPC = 880372, 11501 # a test spot the data offers AI PCs at, and the first of its presets (11502 the next)
GROUP_1, GROUP_2 = [10335, 10336, 10338, 10339], [10342, 20354, 20355, 20356]     # rift %Step_Group, in table order
NO_ZONE_RAID = 20952            # Flamescar: Raid_16 with no zone file
CRYSTAL, COMPASS = 351500600, 351500700         # rift %Select_Step: Dimensional Crystal (step 4), Compass (step 6)
SHARD, RIFT_CRYSTAL = 760000050, 760000090      # mission_reward_entranceui %Rift: Crack Shard, Crack Crystal
TROOP_COIN = 760000030
NO_MATCH = bytes.fromhex("0100")    # 0x5475's answer with no matching started (0x140739460: no text)


def world_role():
    state = State()
    role = world.make(state, 0, "127.0.0.1", 0)
    party.make(role, state)     # as world.make will, after role.empty_replies(EMPTY_REPLIES)
    return role, state


def player():
    c = char(level=30)
    c["name"] = "Aldric"
    return Session(c)


def ask(role, s, proto, body=b""):
    """Send one request through the role's handler table; returns the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def notice_body(spot, title="Raid tonight", difficulty=0, wanted=None, notice_id=0, password=None, new=True):
    row = tables.by_id("spottable")[str(spot)]
    b = bytearray(16)
    b[0] = int(row["State"]) & 0xFF
    b[2] = obf.T2[1 if new else 0]
    b[3] = 1 if password else 0
    b[4] = 1
    b[5:9] = obf.u32(spot)
    struct.pack_into("<I", b, 10, notice_id)
    b[14] = int(row["Limit_Party"]) if wanted is None else wanted
    b[15] = difficulty
    return title.encode() + b"\0" + bytes(b) + ((password.encode() + b"\0") if password else b"")


def setting(kind, notice_id, spot, category, wanted, difficulty, title=b"", password=b""):
    b = bytearray(22)
    b[4] = kind
    struct.pack_into("<I", b, 5, notice_id)
    b[9:13] = obf.u32(spot)
    b[0xe], b[0xf], b[0x10], b[0x11] = category, wanted, difficulty, 1 if password else 0
    return bytes(b) + title + b"\0" + password + b"\0"


def in_party(role, s, spot=COOP, **kw):
    replies = ask(role, s, party.C2S_NOTICE, notice_body(spot, **kw))
    assert replies[0] == (party.S2C_NOTICE, bytes(2))
    return replies


def test_the_spot_columns_the_client_gate_reads():
    # 0x14065b8a7: Spot_Sub_Type (row +0x14) 4 RIFT, 6 Raid_16, 8 PVE_AGGRESSiON are refused out of a party; the
    # extremes carry none, so their solo room opens (and Limit_Party >= 2 lets a party's room open for all four)
    rows = tables.by_id("spottable")
    assert [rows[str(sp)]["Spot_Sub_Type"] for sp in (RIFT, RAID, INVASION, EXTREME)] == \
        ["RIFT", "Raid_16", "PVE_AGGRESSiON", "-"]
    assert all(party.limit_party(rows[str(sp)]) >= 2 for sp in (RIFT, RAID, INVASION, EXTREME, COOP))
    assert party.limit_party(rows[str(STORY)]) == 1
    assert {r["Minimum_Entry"] for r in tables.sections("spottable")["SpotTable"]} == {"1"}


def test_a_lone_player_sees_an_empty_board_and_no_party_request_works():
    role, _ = world_role()
    s = player()
    assert ask(role, s, party.C2S_BOARD, bytes(13)) == [(party.S2C_BOARD, bytes(12))]      # the live-proven reply
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID)) == [(party.S2C_ROOM_ENTER, b"\x07\x1c")]
    assert ask(role, s, party.C2S_ROOM_LEAVE) == [(party.S2C_ROOM_LEAVE, b"\x01\x00")]
    assert ask(role, s, party.C2S_READY, b"\x01") == [(party.S2C_READY, b"\x07\x1c")]
    assert ask(role, s, party.C2S_DIFFICULTY, b"\x01") == [(party.S2C_DIFFICULTY, b"\x07\x1c")]
    assert ask(role, s, party.C2S_AIPC_EMPLOY, b"\x01" + struct.pack("<I", AIPC)) == [(party.S2C_AIPC_EMPLOY, b"\x01\x00")]
    assert ask(role, s, party.C2S_AIPC_DISMISS, b"\x01") == [(party.S2C_AIPC_DISMISS, b"\x01\x00")]
    assert ask(role, s, party.C2S_STEP, b"\x01") == [(party.S2C_STEP, b"\x07\x1c")]
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, b"\x07\x1c")]
    assert ask(role, s, party.C2S_LEAVE) == [(party.S2C_LEAVE, b"\x01\x00")]
    assert ask(role, s, party.C2S_LOOT_RULE, bytes([obf.T2[1], 0])) == [(party.S2C_LOOT_RULE, b"\x01\x00")]
    assert ask(role, s, party.C2S_GIVE_UP) == [(party.S2C_GIVE_UP, b"\x26\x34")]
    assert ask(role, s, party.C2S_NOTICE_DELETE, struct.pack("<I", 1)) == [(party.S2C_NOTICE_DELETE, b"\x1d\x34")]
    assert party.team(s) == {"char": 1, "party": False, "notice": None, "room": None, "loot": (0, 0), "next": 1}
    s.data["team"]["party"] = True              # another character on the same connection starts without a party
    s.data["char"] = dict(s.data["char"], id=2)
    assert party.team(s) == {"char": 2, "party": False, "notice": None, "room": None, "loot": (0, 0), "next": 1}


def test_registering_a_notice_makes_the_party_of_one_and_tells_its_setting():
    role, _ = world_role()
    s = player()
    state90 = int(tables.by_id("spottable")[str(RIFT)]["State"])
    assert in_party(role, s, RIFT, title="Crack 1") == [
        (party.S2C_NOTICE, bytes(2)),
        (party.S2C_CREATED, bytes(2)),          # 0x140e35e10: in a party, its leader, one member built by the client
        (party.S2C_SETTING, setting(1, 1, RIFT, state90, 4, 0, b"Crack 1"))]
    t = party.team(s)
    assert t["party"] and t["notice"] == {"id": 1, "title": "Crack 1", "spot": RIFT, "category": state90, "max": 4,
                                          "difficulty": 0, "password": None}
    # the board: entry 0 is my notice (the head's flag), no other party's
    entry = bytearray(0x13)
    entry[1:5] = obf.u32(RIFT)
    struct.pack_into("<I", entry, 10, 1)
    entry[0x10], entry[0x11], entry[0x12] = 4, 1, state90
    assert ask(role, s, party.C2S_BOARD, bytes(13)) == [
        (party.S2C_BOARD, bytes(2) + struct.pack("<iHH", 1, 0, 0) + struct.pack("<h", 1) + bytes(entry)
         + b"Crack 1\0Aldric\0")]
    # the same party names another mission (the world map's spot menu, 0x140d48d00): the notice keeps its id, no
    # second 0x5441; a password travels as the setting's second string
    assert ask(role, s, party.C2S_NOTICE, notice_body(RAID, title="", password="pw")) == [
        (party.S2C_NOTICE, bytes(2)),
        (party.S2C_SETTING, setting(1, 1, RAID, 13, 8, 0, b"", b"pw"))]


def test_a_notice_for_no_mission_or_a_wrong_head_count_is_refused():
    role, _ = world_role()
    s = player()
    assert ask(role, s, party.C2S_NOTICE, notice_body(10354)) == [(party.S2C_NOTICE, b"\x1d\x34")]     # a town
    assert ask(role, s, party.C2S_NOTICE, notice_body(COOP, difficulty=2)) == [(party.S2C_NOTICE, b"\x1d\x34")]
    assert ask(role, s, party.C2S_NOTICE, notice_body(COOP, wanted=5)) == [(party.S2C_NOTICE, b"\x1a\x34")]
    assert ask(role, s, party.C2S_NOTICE, notice_body(COOP, wanted=0)) == [(party.S2C_NOTICE, b"\x1a\x34")]
    assert ask(role, s, party.C2S_NOTICE, b"cut") == [(party.S2C_NOTICE, b"\x01\x00")]
    assert not party.team(s)["party"] and party.team(s)["notice"] is None


def test_deleting_the_notice_keeps_the_party_and_leaving_keeps_the_notice():
    role, _ = world_role()
    s = player()
    in_party(role, s)
    assert ask(role, s, party.C2S_NOTICE_DELETE, struct.pack("<I", 7)) == [(party.S2C_NOTICE_DELETE, b"\x1d\x34")]
    assert ask(role, s, party.C2S_NOTICE_DELETE, struct.pack("<I", 1)) == [(party.S2C_NOTICE_DELETE, bytes(2))]
    t = party.team(s)
    assert t["party"] and t["notice"] is None
    assert ask(role, s, party.C2S_BOARD, bytes(13)) == [(party.S2C_BOARD, bytes(12))]
    # a second notice of the same party: a new id, no second 0x5441
    assert [p for p, _ in ask(role, s, party.C2S_NOTICE, notice_body(COOP))] == [party.S2C_NOTICE, party.S2C_SETTING]
    assert t["notice"]["id"] == 2
    # leaving: 0x544a 0 (one member with a notice: the client prints nothing and keeps the notice, 0x140e35ade)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    assert ask(role, s, party.C2S_LEAVE) == [(party.S2C_LEAVE, bytes(2))]
    assert not t["party"] and t["room"] is None and t["notice"]["id"] == 2
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP)) == [(party.S2C_ROOM_ENTER, b"\x07\x1c")]


def test_the_party_room_opens_for_what_a_lone_player_is_refused():
    role, _ = world_role()
    for spot in (RIFT, RAID, INVASION, EXTREME, COOP):
        s = player()
        in_party(role, s, spot)
        assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", spot)) == [
            (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", spot, 0, 0)),         # 0x140663020
            (party.S2C_ROOM_ENTER, bytes(2) + struct.pack("<IB", 1, 0))]              # 0x140663230: me, slot 0
        assert party.team(s)["room"] == {"spot": spot, "difficulty": 0, "ready": False, "aipc": {}, "asked": spot}
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", STORY)) == [(party.S2C_ROOM_ENTER, b"\x07\x1c")]
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", 10354)) == [(party.S2C_ROOM_ENTER, b"\x07\x1c")]


def test_a_room_for_another_spot_than_the_notice_carries_its_own_setting():
    role, _ = world_role()
    s = player()
    in_party(role, s, RAID)
    replies = ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    assert replies[0] == (party.S2C_SETTING, setting(1, 1, COOP, 10, 4, 0, b"Raid tonight"))
    assert [p for p, _ in replies[1:]] == [party.S2C_ROOM_MADE, party.S2C_ROOM_ENTER]
    n = party.team(s)["notice"]                 # the notice follows the room (0x140d48d00 does it from the map)
    assert (n["id"], n["spot"], n["category"], n["max"], n["difficulty"]) == (1, COOP, 10, 4, 0)
    ask(role, s, party.C2S_NOTICE_DELETE, struct.pack("<I", 1))
    replies = ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", INVASION))          # no notice: setting id 0
    assert replies[0] == (party.S2C_SETTING, setting(1, 0, INVASION, 10, 4, 0))
    assert ask(role, s, party.C2S_DIFFICULTY, b"\x01") == [(party.S2C_DIFFICULTY, b"\x02\x04")]    # Normal only
    in_party(role, s, COOP, difficulty=1)       # the notice's difficulty is the room's
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))[0] == \
        (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", COOP, 1, 0))


def test_ready_difficulty_and_leaving_the_room():
    role, _ = world_role()
    s = player()
    in_party(role, s)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    assert ask(role, s, party.C2S_READY, b"\x01") == [(party.S2C_READY, bytes(2) + struct.pack("<IB", 1, 1))]
    assert ask(role, s, party.C2S_READY, b"\x00") == [(party.S2C_READY, bytes(2) + struct.pack("<IB", 1, 0))]
    # Hard: the reply says nothing (0x1406636e0), the room takes it from the setting push kind 0 (0x14065aef0)
    assert ask(role, s, party.C2S_DIFFICULTY, b"\x01") == [
        (party.S2C_DIFFICULTY, bytes(2)),
        (party.S2C_SETTING, setting(0, 1, COOP, 10, 4, 1, b"Raid tonight"))]
    t = party.team(s)
    assert t["room"]["difficulty"] == 1 and t["notice"]["difficulty"] == 1
    assert ask(role, s, party.C2S_DIFFICULTY, b"\x02") == [(party.S2C_DIFFICULTY, b"\x02\x04")]     # no Hell here
    assert t["room"]["difficulty"] == 1
    assert ask(role, s, party.C2S_STEP, b"\x04") == [(party.S2C_STEP, b"\x01\x00")]
    assert ask(role, s, party.C2S_ROOM_LEAVE) == [(party.S2C_ROOM_LEAVE, bytes(2) + struct.pack("<I", 1))]
    assert t["room"] is None and t["party"]


def test_ai_pcs_only_where_the_data_offers_them():
    role, _ = world_role()
    assert party.aipc_preset(AIPC, AIPC_SPOT) and party.aipc_preset(AIPC, COOP) is None
    live = {r["ActiveSpot"] for r in tables.sections("aipctrooptable")["AIPCPreset"]}
    assert not live & {str(sp) for sp in (RIFT, RAID, INVASION, EXTREME, COOP)}
    s = player()
    in_party(role, s)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    employ = lambda slot, aipc: ask(role, s, party.C2S_AIPC_EMPLOY, bytes([slot]) + struct.pack("<I", aipc))
    assert employ(1, AIPC) == [(party.S2C_AIPC_EMPLOY, b"\x01\x00")]                   # not offered at this spot
    in_party(role, s, AIPC_SPOT)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", AIPC_SPOT))
    assert employ(1, AIPC) == [(party.S2C_AIPC_EMPLOY, bytes(2) + struct.pack("<BI", 1, AIPC))]
    assert employ(2, AIPC) == [(party.S2C_AIPC_EMPLOY, b"\x01\x00")]                   # the same AI PC twice
    assert employ(0, AIPC + 1) == [(party.S2C_AIPC_EMPLOY, b"\x0f\x34")]               # my own slot
    assert employ(4, AIPC + 1) == [(party.S2C_AIPC_EMPLOY, b"\x0f\x34")]               # beyond Limit_Party 4
    assert employ(1, AIPC + 1) == [(party.S2C_AIPC_EMPLOY, b"\x0f\x34")]               # the slot is taken
    assert party.team(s)["room"]["aipc"] == {1: AIPC}
    assert ask(role, s, party.C2S_AIPC_DISMISS, b"\x02") == [(party.S2C_AIPC_DISMISS, b"\x01\x00")]
    assert ask(role, s, party.C2S_AIPC_DISMISS, b"\x01") == [(party.S2C_AIPC_DISMISS, bytes(2) + b"\x01")]
    assert party.team(s)["room"]["aipc"] == {}


def test_the_start_from_the_party_room_is_the_solo_entry():
    role, _ = world_role()
    s = player()
    in_party(role, s, COOP, difficulty=1)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    replies = ask(role, s, party.C2S_START)
    assert replies[0] == (party.S2C_START, bytes(2))
    assert replies[1][0] == world.S2C_GAME_SERVER and replies[1][1][:2] == bytes(2)
    assert struct.unpack_from("<I", replies[1][1], 8)[0] == COOP
    c = s.data["char"]
    assert c["mission"]["spot"] == COOP and c["mission"]["difficulty"] == 1 and s.data["battle_spot"] == COOP
    t = party.team(s)
    assert t["room"] is None and t["party"] and s.data["party_aipc"] == {}
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, b"\x07\x1c")]           # no room any more


def test_a_start_the_entry_refuses_unlocks_the_room_with_the_entrys_code():
    role, _ = world_role()
    s = player()
    in_party(role, s, RIFT)                     # the rifts want one deck troop (Min_Limit_Troop 1): none organised
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, struct.pack("<H", game.TROOPS_SHORT))]
    assert party.team(s)["room"]["spot"] == RIFT and "mission" not in s.data["char"]
    from test_army import army
    c, _ = army(1, deck=(1,))                   # one deck troop organised
    s = Session(c)
    in_party(role, s, NO_ZONE_RAID)             # a raid with no zone file: the server can build no room for it
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", NO_ZONE_RAID))
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, struct.pack("<H", world.NO_GAME))]
    assert party.team(s)["room"]["spot"] == NO_ZONE_RAID and not game.is_mission(NO_ZONE_RAID)
    in_party(role, s, RIFT)                     # and the rift a lone player is refused starts from the party's room,
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))         # on one of its step group's maps (rift_map)
    replies = ask(role, s, party.C2S_START)
    assert replies[0] == (party.S2C_START, bytes(2))
    assert next(b for p, b in replies if p == world.S2C_GAME_SERVER)[:2] == bytes(2)
    assert c["mission"]["spot"] in GROUP_1 and s.data["battle_spot"] == c["mission"]["spot"]


def test_the_rift_tables_and_the_clients_step_formula():
    # rift %Basic / %Step_Group: one State, six steps, two groups of four maps; 0x1418cf2d0: group * 3 + difficulty - 2
    assert party.rift_groups() == {90: {1: GROUP_1, 2: GROUP_2}} and party.max_step(90) == 6
    assert [party.step_of(sp, d) for sp in (GROUP_1[0], GROUP_1[3], GROUP_2[0], GROUP_2[3]) for d in range(3)] == \
        [1, 2, 3, 1, 2, 3, 4, 5, 6, 4, 5, 6]
    assert [party.step_parts(k) for k in range(1, 7)] == [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
    rows = tables.by_id("spottable")
    for sp in GROUP_1 + GROUP_2:                # every step's map exists at the step's difficulty, as a mission room
        assert all(party.has_difficulty(rows[str(sp)], d) for d in range(3)) and game.is_mission(sp), sp
        assert rows[str(sp)]["Spot_Sub_Type"] == "RIFT" and rows[str(sp)]["State"] == "90"
    # the other eight rift spots are in no group (the client's formula answers -1): plain party rooms
    others = [int(i) for i, r in rows.items() if r["Spot_Sub_Type"] == "RIFT" and int(i) not in GROUP_1 + GROUP_2]
    assert len(others) == 8 and all(party.rift_state(sp) is None and party.step_of(sp, 0) is None for sp in others)
    assert party.step_of(RAID, 0) is None and party.step_of(COOP, 0) is None
    # %Select_Step: a Dimensional Crystal for step 4, a Dimensional Compass for step 6; the steps' rewards
    assert [party.select_cost(90, k) for k in range(1, 7)] == [None, None, None, (CRYSTAL, 1), None, (COMPASS, 1)]
    assert [party.step_reward(90, k) for k in range(1, 7)] == \
        [(SHARD, 5), (SHARD, 10), (SHARD, 20), (RIFT_CRYSTAL, 5), (RIFT_CRYSTAL, 10), (RIFT_CRYSTAL, 100)]


def test_a_step_is_free_up_to_the_next_one_and_costs_its_item_beyond():
    c = char(level=30)
    assert party.step_entry(c, 90, 1) == (None, None)
    assert party.step_entry(c, 90, 2) == (party.SILENT, None) and party.step_entry(c, 90, 5) == (party.SILENT, None)
    assert party.step_entry(c, 90, 0) == (party.SILENT, None) and party.step_entry(c, 90, 7) == (party.SILENT, None)
    assert party.step_entry(c, 90, 4) == (party.ITEMS_SHORT, (CRYSTAL, 1))
    c["bag"] = [{"code": CRYSTAL, "slot": 0, "count": 1}]
    assert party.step_entry(c, 90, 4) == (None, (CRYSTAL, 1))
    assert party.step_entry(c, 90, 6) == (party.ITEMS_SHORT, (COMPASS, 1))
    c["rift_step"] = 3                          # the step cleared: it, the ones below and the next are free
    assert [party.step_entry(c, 90, k) for k in (1, 3, 4)] == [(None, None)] * 3
    assert party.step_entry(c, 90, 5) == (party.SILENT, None)
    c["rift_step"] = 6
    assert party.step_entry(c, 90, 6) == (None, None) and party.step_entry(c, 90, 7) == (party.SILENT, None)


def test_the_rift_room_follows_the_step_the_leader_picks():
    role, _ = world_role()
    s = player()
    c = s.data["char"]
    in_party(role, s, RIFT, title="Crack")
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))
    step = lambda k: ask(role, s, party.C2S_STEP, bytes([k]))
    room, n = party.team(s)["room"], party.team(s)["notice"]
    assert step(2) == [(party.S2C_STEP, b"\x01\x00")]                  # not the next, no %Select_Step row
    assert step(0) == [(party.S2C_STEP, b"\x01\x00")] and step(7) == [(party.S2C_STEP, b"\x01\x00")]
    assert ask(role, s, party.C2S_STEP) == [(party.S2C_STEP, b"\x01\x00")]
    assert step(4) == [(party.S2C_STEP, b"\x3c\x04")]                  # 0x43c "Not enough items." (0x140d681be)
    assert (room["spot"], room["difficulty"]) == (RIFT, 0)
    c["bag"] = [{"code": CRYSTAL, "slot": 0, "count": 1}, {"code": COMPASS, "slot": 1, "count": 1}]
    # step 4: the second group at Normal; the room's map is of the first group, so the group's first map (the one the
    # client names a group by, 0x1418cf3f0); 0x407c carries the step, the room takes it from the setting (kind 0)
    assert step(4) == [(party.S2C_STEP, bytes(2) + b"\x04"),
                       (party.S2C_SETTING, setting(0, 1, GROUP_2[0], 90, 4, 0, b"Crack"))]
    assert (room["spot"], room["difficulty"], n["spot"], n["difficulty"]) == (GROUP_2[0], 0, GROUP_2[0], 0)
    assert step(6) == [(party.S2C_STEP, bytes(2) + b"\x06"),
                       (party.S2C_SETTING, setting(0, 1, GROUP_2[0], 90, 4, 2, b"Crack"))]
    assert step(1) == [(party.S2C_STEP, bytes(2) + b"\x01"),          # back in its group: the map the room opened on
                       (party.S2C_SETTING, setting(0, 1, RIFT, 90, 4, 0, b"Crack"))]
    assert c["bag"][0]["count"] == 1 and c["bag"][1]["count"] == 1      # nothing is taken before the start
    # a room opened on another map of the group keeps it through the group's steps
    c["rift_step"] = 1
    in_party(role, s, GROUP_1[1], title="Crack")
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", GROUP_1[1]))[0] == \
        (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", GROUP_1[1], 0, 1))    # the third byte: the step cleared
    assert step(2)[1] == (party.S2C_SETTING, setting(0, 1, GROUP_1[1], 90, 4, 1, b"Crack"))
    assert party.team(s)["room"]["asked"] == GROUP_1[1]
    # a room that is no rift step's has no step list
    in_party(role, s, RAID)
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID))[0] == \
        (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", RAID, 0, 0))
    assert step(1) == [(party.S2C_STEP, b"\x01\x00")]


def test_a_rift_start_takes_the_steps_item_and_rolls_one_of_its_groups_maps(monkeypatch):
    from test_army import army
    role, _ = world_role()
    c, _ = army(1, deck=(1,))                   # one deck troop organised (the rifts' Min_Limit_Troop)
    c["bag"] = [{"code": CRYSTAL, "slot": 0, "count": 2, "serial": 1}]
    s = Session(c)
    in_party(role, s, RIFT)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))
    assert ask(role, s, party.C2S_STEP, b"\x04")[0] == (party.S2C_STEP, bytes(2) + b"\x04")
    monkeypatch.setattr(party.random, "choice", lambda maps: maps[2])
    replies = ask(role, s, party.C2S_START)
    assert replies[0] == (party.S2C_START, bytes(2))
    server = next(b for p, b in replies if p == world.S2C_GAME_SERVER)
    assert server[:2] == bytes(2) and struct.unpack_from("<I", server, 8)[0] == GROUP_2[2]
    assert c["mission"]["spot"] == GROUP_2[2] and c["mission"].get("difficulty", 0) == 0
    assert [(it["code"], it["count"]) for it in c["bag"]] == [(CRYSTAL, 1)]     # "spent when entering the mission"
    # the item gone between the pick and the start: the start is refused, the room stays
    s = Session(c)
    c.pop("mission", None)
    in_party(role, s, RIFT)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))
    ask(role, s, party.C2S_STEP, b"\x04")
    c["bag"] = []
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, b"\x3c\x04")]
    assert party.team(s)["room"]["spot"] == GROUP_2[0] and "mission" not in c
    # a room opened past the next step by its notice (Hard: step 2 for a character who cleared none) does not start
    in_party(role, s, RIFT, difficulty=1)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT))
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, b"\x02\x04")]    # "Cannot enter the room."
    assert ask(role, s, party.C2S_STEP, b"\x01")[0] == (party.S2C_STEP, bytes(2) + b"\x01")
    assert ask(role, s, party.C2S_START)[0] == (party.S2C_START, bytes(2)) and c["mission"]["spot"] == GROUP_1[2]


SARAH = bytes.fromhex("5a02971697160100000000 00".replace(" ", ""))   # live 2026-11-06 13:04:05, her rift button


def match_body(spot, difficulty=0, named=None):
    """0x5474 as OnStartMatching 0x140735290 builds it (0x140f05a60): the spot's State, 2, the coded spot, 1, team
    +0xe4, the difficulty. The spot is -1 unless named: the client's group lookup 0x1418cf3f0 answered -1 live."""
    b = bytearray(12)
    b[0] = int(tables.by_id("spottable")[str(spot)]["State"]) & 0xFF
    b[1] = 2
    b[2:6] = obf.u32(0xFFFFFFFF if named is None else named)
    b[6] = 1
    b[11] = difficulty
    return bytes(b)


def test_sarahs_rift_button_starts_the_first_step_alone(monkeypatch):
    """Owner, 2026-11-06 (ROADMAP Q74): "Open the rift for one". The matching request is answered as before (no
    "finding members" left on the client) and the step it names starts at once, on one of its group's maps. Her
    request names the rift by its State alone (spot -1), at difficulty 0: step 1."""
    from test_army import army
    role, _ = world_role()
    c, _ = army(1, deck=(1,))                   # one deck troop organised (the rifts' Min_Limit_Troop)
    s = Session(c)
    monkeypatch.setattr(party.random, "choice", lambda maps: maps[1])
    assert match_body(RIFT) == SARAH
    replies = ask(role, s, party.C2S_MATCH, SARAH)
    assert replies[0] == (party.S2C_MATCH, NO_MATCH)
    server = next(b for p, b in replies if p == world.S2C_GAME_SERVER)
    assert server[:2] == bytes(2) and struct.unpack_from("<I", server, 8)[0] == GROUP_1[1]
    assert c["mission"]["spot"] == GROUP_1[1] and c["mission"].get("difficulty", 0) == 0
    assert not party.team(s)["party"] and party.team(s)["room"] is None and not s.data.get("party_aipc")
    party.on_mission_won(s, State(), c, GROUP_1[1], 0)                  # its win is the ladder's step 1
    assert party.cleared_step(c) == 1
    c, _ = army(1, deck=(1,))                   # a request naming a rift map plays that map's step (group 2 Normal)
    c["rift_step"] = 3
    s = Session(c)
    ask(role, s, party.C2S_MATCH, match_body(RIFT, named=GROUP_2[3]))
    assert c["mission"]["spot"] in GROUP_2 and party.step_of(c["mission"]["spot"], 0) == 4


def test_sarahs_button_answers_as_before_for_anything_but_a_free_rift_step():
    from test_army import army
    role, _ = world_role()
    c, _ = army(1, deck=(1,))
    for body in (match_body(COOP), match_body(COOP, named=COOP), match_body(RIFT, difficulty=2), SARAH[:11], b""):
        s = Session(c)                          # a non-rift, step 3 for a character who cleared none, short bodies
        assert ask(role, s, party.C2S_MATCH, body) == [(party.S2C_MATCH, NO_MATCH)], body.hex()
        assert "mission" not in c
    s = player()                                # no troop organised: the entry's own refusal, as at an NPC entrance
    replies = ask(role, s, party.C2S_MATCH, match_body(RIFT))
    assert replies[0] == (party.S2C_MATCH, NO_MATCH) and replies[1][0] == world.S2C_GAME_SERVER
    assert replies[1][1][:2] != bytes(2) and "mission" not in s.data["char"]


def test_a_rift_win_raises_the_cleared_step_and_pays_the_steps_reward():
    c = char(level=30)
    s, state = Session(c, spot=GROUP_1[3]), State()
    party.on_mission_won(s, state, c, GROUP_1[3], 0)                    # step 1 on any of its group's maps
    assert party.cleared_step(c) == 1 and [(i["code"], i["count"]) for i in c["bag"]] == [(SHARD, 5)]
    party.on_mission_won(s, state, c, GROUP_2[3], 2)                    # step 6: 100 Crack Crystals (the day's cap)
    assert party.cleared_step(c) == 6
    party.on_mission_won(s, state, c, GROUP_1[0], 1)                    # a lower step again: paid, nothing lowered
    assert party.cleared_step(c) == 6
    assert [(i["code"], i["count"]) for i in c["bag"]] == [(SHARD, 15), (RIFT_CRYSTAL, 100)]
    before = dict(c, bag=[dict(i) for i in c["bag"]])
    party.on_mission_won(s, state, c, COOP, 0)                          # no rift, no raid: nothing
    assert c == before
    # the room made for him says so: the step list offers the cleared step and the next (room +0xb20)
    role, _ = world_role()
    s = Session(c)
    in_party(role, s, GROUP_2[0])
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", GROUP_2[0]))[0] == \
        (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", GROUP_2[0], 0, 6))


def test_a_raid_is_a_mission_room_the_partys_start_reaches():
    from test_army import army
    assert game.is_mission(RAID) and game.is_mission(20951) and not game.is_mission(NO_ZONE_RAID)
    assert game.windowless(RAID) and game.reward_row(RAID, 0, 0) is None     # no reward row: no result window
    role, _ = world_role()
    c, _ = army(1, deck=(1,))
    s = Session(c)
    in_party(role, s, RAID)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID))
    replies = ask(role, s, party.C2S_START)
    assert replies[0] == (party.S2C_START, bytes(2))
    server = next(b for p, b in replies if p == world.S2C_GAME_SERVER)
    assert server[:2] == bytes(2) and struct.unpack_from("<I", server, 8)[0] == RAID
    assert c["mission"]["spot"] == RAID and s.data["battle_spot"] == RAID


def test_the_raid_tables_resurrections_and_checkpoints():
    from kuf2 import zone
    assert party.raid_row(RAID)["Default_Number_Resurrection"] == "3" and party.raid_row(RAID, 2) is not None
    assert party.raid_row(20951, 1) is None and party.raid_row(EXTREME) is None and party.raid_row(RIFT) is None
    # the limit the HUD shows in a Raid_16 room (0x14068e31d); the extremes and the rifts keep %Revival's
    assert game.revival(RAID) == ("CUBIC", 3) and game.revival(RAID, 2) == ("CUBIC", 3)
    assert game.revival(EXTREME) == ("CUBIC", 3) and game.revival(RIFT) == ("CUBIC", 5)
    cps = party.checkpoints(RAID)
    assert [(cp["id"], cp["point"], cp["resurrections"], cp["boss"]) for cp in cps] == [
        (295000, 100, 3, 295410), (295010, 101, 0, 295380), (295020, 102, 3, 295390), (295030, 103, 3, 295400),
        (295040, 104, 3, 295190)]
    assert cps[0]["phase"] == (7, 1) and len(party.checkpoints(RAID, 1)) == 5 and len(party.checkpoints(20951)) == 6
    assert party.checkpoints(EXTREME) == [] and party.checkpoints(20951, 1) == []
    # every restart point is a start point of the raid's zone, of a kind of its own (SPTypes 3), beside the sixteen
    # the party enters at (SPTypes 0)
    for spot in (RAID, 20951):
        kinds = {p["StartPointID"]: p["SPTypes"] for p in zone.for_spot(spot)["PlayerStartPointInfoData"]}
        assert party.restart_points(spot) == {i for i, k in kinds.items() if k == 3}
        assert {i for i, k in kinds.items() if k == 0} == set(range(16))
    assert party.restart_points(RIFT) == frozenset()


def test_the_raids_revive_ban_runs_from_the_fall_and_is_listed():
    import time
    from test_battle import mission_room
    assert (party.revive_ban(RAID, True), party.revive_ban(RAID, False)) == (10, 10)
    assert party.revive_ban(RIFT, True) == 0 and party.revive_ban(EXTREME, False) == 0
    role = game.make(State(), 0)
    bans = lambda s: ask(role, s, game.C2S_REVIVE_BANS)
    revive = lambda s, uid=0: next(r for r in ask(role, s, game.C2S_REVIVE_HERE, struct.pack("<H", uid)
                                                    + obf.u32(0xFFFFFFFF)) if r[0] == game.S2C_REVIVE_HERE)
    s = mission_room(RIFT)                      # no ban outside the raids: the four zero bytes, as before
    party.on_troop_down(s, 0)
    assert bans(s) == [(game.S2C_REVIVE_BANS, bytes(4))] and party.ban_left(s, 0) == 0
    s = mission_room(RAID)
    assert bans(s) == [(game.S2C_REVIVE_BANS, bytes(4))]
    hero = s.data["battle"].troops[0]
    hero["hp"] = 0
    party.on_troop_down(s, 0)                   # (game.troop_down calls it: the hero fell)
    party.on_troop_down(s, 20000)               # a hostile troop's fall bans nothing
    assert 9.9 < party.ban_left(s, 0) <= 10 and party.ban_left(s, 20000) == 0
    (proto, body), = bans(s)
    n, m, uid, ms = struct.unpack("<HHHi", body)
    assert (proto, n, m, uid) == (game.S2C_REVIVE_BANS, 0, 1, 0) and 9900 < ms <= 10000
    assert revive(s) == (game.S2C_REVIVE_HERE, struct.pack("<HI", game.REVIVE_NOT_NOW, 0))     # text 0xd03d
    assert hero["hp"] == 0 and s.data.get("revivals", 0) == 0
    s.data["revive_bans"][0] = time.monotonic() - 0.1                   # the ten seconds are over
    assert bans(s) == [(game.S2C_REVIVE_BANS, bytes(4))]
    assert revive(s) == (game.S2C_REVIVE_HERE, struct.pack("<HI", 0, 1)) and hero["hp"] > 0


def test_the_camp_revive_of_a_raid_stays_off_the_checkpoints_restart_points():
    from kuf2 import zone
    from test_battle import mission_room
    s = mission_room(RAID)
    points = {p["StartPointID"]: p["StartPointInfoData"][0] for p in zone.for_spot(RAID)["PlayerStartPointInfoData"]}
    there = points[100]                         # checkpoint 295000's restart point, 60,000 units from the entry
    s.data["hero_pos"] = (round(there["PosX"]), 0, round(there["PosZ"]))
    entry = {(round(points[k]["PosX"]), 0, round(points[k]["PosZ"])) for k in range(16)}
    assert game.revive_point(s) in entry
    s = mission_room(10234)                     # a mission with no checkpoint: as before, the nearest start point
    s.data["hero_pos"] = (0, 0, 0)
    assert game.revive_point(s) in {(round(p["StartPointInfoData"][0]["PosX"]), 0, round(p["StartPointInfoData"][0]["PosZ"]))
                                    for p in zone.for_spot(10234)["PlayerStartPointInfoData"]}


def test_a_raid_win_puts_its_reward_dummies_loot_in_the_bag(monkeypatch):
    from kuf2 import loot
    dummies = game.reward_dummies(RAID, 0)
    assert sorted(tid for _, tid in dummies) == [295380, 295390, 295400, 295410]
    assert sorted(tid for _, tid in game.reward_dummies(20951, 0)) == [296800, 296810]
    monkeypatch.setattr(loot, "roll_drops", lambda spot, tid, leader=None, roll=None: [(TROOP_COIN, 2), (1, 1)])
    monkeypatch.setattr(game, "roll_gold", lambda tid, roll=None: 100)
    c = char(level=30)
    s, state = Session(c, spot=RAID), State()
    party.on_mission_won(s, state, c, RAID, 0)
    assert [(i["code"], i["count"]) for i in c["bag"]] == [(TROOP_COIN, 8)] and c["gold"] == 400
    assert "rift_step" not in c


def test_the_raid_room_is_won_by_the_wave_rule_and_left_without_a_window():
    from conftest import run_pending
    from test_battle import NoSave, mission_room
    s = mission_room(RAID)
    standing = lambda: [u for u, z in s.data.get("zone_troops", {}).items()
                        if game.hostile(z) and u not in s.data.get("down", set())]
    assert standing()
    for _ in range(100):
        alive = standing()
        if not alive or s.data.get("mission_won"):
            break
        for u in alive:
            game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    assert s.data.get("mission_won") and standing() == [] and s.data["waves"] == []
    assert sum(w.proto == game.S2C_MISSION_LEAVE for w in s.sent) == 1
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)


def test_the_loot_rule_is_kept_and_echoed():
    role, _ = world_role()
    s = player()
    in_party(role, s)
    grade, rule = 3, 2
    assert ask(role, s, party.C2S_LOOT_RULE, bytes([obf.T2[(grade * 8 + rule) & 0xFF], grade])) == [
        (party.S2C_LOOT_RULE, bytes(2) + bytes([obf.via_t1(rule), grade, 0]))]
    assert party.team(s)["loot"] == (grade, rule)
    assert obf.T1[obf.via_t1(rule)] & 7 == rule                                         # as 0x140e381c0 reads it


def test_giving_up_alone_leaves_the_mission_as_the_exit_does():
    role, _ = world_role()
    s = player()
    in_party(role, s)
    assert ask(role, s, party.C2S_GIVE_UP) == [(party.S2C_GIVE_UP, b"\x26\x34")]       # not in a mission
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", COOP))
    ask(role, s, party.C2S_START)
    assert s.data["battle_spot"] == COOP
    replies = ask(role, s, party.C2S_GIVE_UP)
    assert replies[0] == (party.S2C_GIVE_UP, bytes(2))
    assert world.S2C_MISSION_ESCAPE in [p for p, _ in replies[1:]]
    assert "mission" not in s.data["char"]

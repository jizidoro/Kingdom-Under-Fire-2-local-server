"""Room changes on one map, and the field simulation grant 0x50cf (planning/agents/reports/2026-10-24_crash10359.md).

The crash: AC3 run, 2026-10-24 13:54:21, Wolf Fang Field 10359 entered from Mist Field 10350 by quest 1150808's accept
action CurrentWarp; an access violation at 0x140d1c506 reading 0x50, inside the 0x50cf handler 0x140d1c3f0.
- [client] The handler looks the target and the reference troop up (0x1408d8520 -> 0x140c02780), takes the reference
  troop's Player id (troop +0x918, 0x1407e4f30, then +0x50; 0xffff without one: it only revokes), then compares it
  with the LOCAL Player's: 0x140b44980 (the PlayerManager) -> 0x140b431e0, which returns null when the manager's map is
  empty (+0x18), its local id (+2) is 0xffff or no Player has that id; `cmp [rax+0x50]` then faults at 0x50.
- [live] Not a troop: each of the 225 0x50cf named a target and the hero 0 that had their 0x50cb and the client's own
  0x50ab before it (test_every_simulation_grant_names_troops_the_client_has replays the room).
- [client] What went missing is the local Player. The world's 0x4049 (13:54:01) named 10359 from room 10350, both
  1_MistField: the handler 0x140d00590 makes the block's spot current (0x140d65b10 -> 0x140d65c60), which sets
  common+0x1728 = 1 (a Field on the same map; 2 for any other type), and with it set the handler neither ends the
  battle nor loads. The room start 0x3f4e ends a kept battle only for 2 (header 0x140d09380: 0x140cf2e10, then the
  state's leave vt+0x30, before it clears the PlayerManager for the player info); with 1 its go 0x140d07ec0 changes
  state (0x140cbc870 -> 0x140cbc720 calls BattleField's leave 0x140cefc00 -> 0x140cf2130), which clears the
  PlayerManager (0x140b42910 deletes every Player) and the start info the room's 0x3f4f / 0x3f50 had just made.
- [live] The order shows it: "RemoveInfo MYHERO0" (that leave) at 13:54:06.419, after the room start .220-.225, where
  warp 704 into the same field (13:30:06, its own spot: no flag) ran it at the 0x4049, 5 s before the room; in every
  other room of the run the hero bound while loading (from the start info) before its 0x50cb, in 10359 after it (built
  from the 0x50cb for an owner-0 Player, not the local one), and its 0x50b0 never carried a record (0 of 6).
`client_flag` / `escape` / `current_at_leave` below are those rules; the fix names the client's current spot: the room's
own, or the warp's when a 0x5641 went first (world.same_map_field; the 2026-11-05 warp 705 crash). Reads the
installed game's tables and zone files. Run: py -m pytest -q server/tests"""
import struct
from types import SimpleNamespace

import pytest

from kuf2 import game, obf, quest, tables, world
from test_mission_exit import Session, State, client_map, game_server_spots, pkt
from test_quest import accept_body
from test_walk_p2 import start_room


# the level-10 route's rooms (planning/ROADMAP.md), and the fields that share a map with one of them
ROUTE = [10350, 10352, 10359, 10233, 10234, 10235, 10303, 10331, 10345, 10358, 10361, 10362, 50116]
FIELDS = [10350, 10352, 10359, 10351, 10354, 10360]     # 1_MistField and 1_NewHamptonHighway

# world_20261024_125927: the two leaves out of Mist Field's room 10350 that day (S2C 0x4049 bodies)
LIVE_INTO_10359 = "000010c3c31010000001ea77120000bc00000000000000000372c3102c0100"   # 13:54:01.152697 -> the crash
LIVE_WARP_704 = "000010c3c310100000d5bf33fb0000bc0000000000000000030cc3102c0100"     # 13:30:06.555166 -> fine
LIVE_WARP_705 = "000010c3c310100000584dd9e700005800000000000000000372c3102c0100"     # 2026-11-05 07:39:03.487 -> the crash
DONE_BEFORE_1150808 = [1150801, 1150802, 1150803, 1150811, 1150804, 1150805, 1150806, 1150807]   # proventen's save


def client_flag(old, new, flag):
    """common+0x1728 once the client's current spot goes from old to new (0x140d65b10 -> 0x140d65c60): unchanged for
    the same spot; 1 / 2 on the same map (the new spot a Field / anything else); else 0."""
    if old == new:
        return flag
    a, b = client_map(old), client_map(new)
    if a == b and "_RIFT" not in b:
        return 1 if tables.by_id("spottable")[str(new)]["Spot_Type"] == "Field" else 2
    return 0


def escape(room, flag, w):
    """What the client in `room`, holding `flag`, does with the 0x4049 w (0x140d00590): (the battle ended, the flag)."""
    b = bytes(w.buf)
    assert w.proto == world.S2C_MISSION_ESCAPE and len(b) == 2 + 0x1d and b[:2] == bytes(2)
    after = client_flag(room, obf.dec_u32(b[2 + 0x17:2 + 0x1b]), flag)
    return after == 0, after


def current_at_leave(s, room):
    """The client's current spot when the 0x4049 comes: a 0x5641 type 1 before it has made its warp's own spot current
    with no flag (0x140cc0538 -> plain setter 0x140d65b00; traced live 2026-11-05 07:48:43.862)."""
    for w in s.sent:
        if w.proto == world.S2C_MISSION_ESCAPE:
            break
        if w.proto == world.S2C_WARP_PROCESS and bytes(w.buf)[0] == 1:
            room = int(tables.by_id("warpinfo")[str(obf.dec_u32(bytes(w.buf)[1:5]))]["SpotID"])
    return room


def keeps_local_player(ended, flag):
    """Whether the next room, started by 0x3f4e, keeps the local Player its 0x3f4f makes: the battle ended before it,
    or its header ends the kept one itself (flag 2, a start in place); else its go's state change deletes it."""
    return ended or flag == 2


def live(body):
    return SimpleNamespace(proto=world.S2C_MISSION_ESCAPE, buf=bytes.fromhex(body))


def escapes(s):
    return [w for w in s.sent if w.proto == world.S2C_MISSION_ESCAPE]


# --- the live crash ---

def test_the_live_leave_into_wolf_fang_kept_the_battle_and_warp_704_ended_it():
    assert obf.dec_u32(bytes.fromhex(LIVE_INTO_10359)[2 + 0x17:2 + 0x1b]) == 10359
    assert escape(10350, 0, live(LIVE_INTO_10359)) == (False, 1)
    assert not keeps_local_player(False, 1)                     # the room 10359 had no local player: 0x140d1c506
    assert escape(10350, 0, live(LIVE_WARP_704)) == (True, 0)   # the same field's own spot: WarpWait, then the room


def test_quest_1150808s_currentwarp_leaves_mist_field_by_its_own_spot():
    # the accept as the client sent it (13:54:01 C2S 0x5542), in the room the world sent the hero to (battle_spot)
    s = Session(10350, 10350, level=5, pos=[281528, 0, 204909])
    s.data["char"]["quests"]["done"] = list(DONE_BEFORE_1150808)
    role = world.make(State(), 0, "127.0.0.1", 0)
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(1150808)))
    [esc] = escapes(s)
    blk = bytes(esc.buf)[2:]
    ended, flag = escape(10350, 0, esc)
    assert ended and flag == 0 and keeps_local_player(ended, flag)
    assert obf.dec_u32(blk[0x17:0x1b]) == 10350 and blk[0x16] == world.WARP_KIND_FIELD   # the room's own spot
    x, _, z = world.start_point(10359, 0)
    assert obf.dec_pos_xz(blk[7:11], blk[13]) == (x, z)          # still the field's start point
    s.run_later()
    assert game_server_spots(s) == [10359]                      # the room the client then loads
    c = s.data["char"]
    assert c["spot"] == 10359 and c["field_group"] == [10359, 0] and s.data["battle_spot"] == 10359


@pytest.mark.parametrize("room", ROUTE + [10351, 10354, 10360])
def test_no_field_entry_from_a_room_keeps_the_battle(room):
    # every way into a field from a room goes through send_field_entry (quest warps, warp requests, the crystal, a
    # mission's Esc exit): a 0x4049 that keeps the battle leaves the next room without a local player
    for spot in FIELDS:
        s = Session(room, room)
        world.send_field_entry(s, spot, 0, leave_battle=True)
        [esc] = escapes(s)
        ended, flag = escape(current_at_leave(s, room), 0, esc)
        assert ended and flag == 0, (room, spot)
        s.run_later()
        assert game_server_spots(s) == [spot], (room, spot)


def test_the_live_leave_by_warp_705_kept_the_battle():
    # 2026-11-05 07:48:43-48 traced: 0x5641 made 10350 current, this 0x4049 named the room 10359 back: flag 1, the battle
    # kept, the go's state change deleted the Players the 0x3f4f had made; the warp poll read the null local Player
    # at 0x140b40a50, 650 ms after RenderStart
    assert obf.dec_u32(bytes.fromhex(LIVE_WARP_705)[2 + 0x17:2 + 0x1b]) == 10359
    assert escape(10350, 0, live(LIVE_WARP_705)) == (False, 1)
    assert not keeps_local_player(False, 1)


def test_quest_1150602s_warp_705_leaves_by_the_spot_its_0x5641_made_current():
    s = Session(10359, 10359)
    world.send_field_entry(s, 10350, 6, leave_battle=True)
    assert [w.proto for w in s.sent][:2] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    [esc] = escapes(s)
    assert current_at_leave(s, 10359) == 10350
    assert obf.dec_u32(bytes(esc.buf)[2 + 0x17:2 + 0x1b]) == 10350
    ended, flag = escape(10350, 0, esc)
    assert ended and flag == 0 and keeps_local_player(ended, flag)
    s.run_later()
    assert game_server_spots(s) == [10350]


@pytest.mark.parametrize("room", ROUTE + [10351, 10354, 10360])
def test_no_field_entry_by_a_warp_keeps_the_battle(room):
    # the same for every start group that has a warp of its own (0x5641 goes first)
    seen = 0
    for spot in FIELDS:
        for group in range(1, 12):
            if world.field_warp(spot, group) is None:
                continue
            seen += 1
            s = Session(room, room)
            world.send_field_entry(s, spot, group, leave_battle=True)
            [esc] = escapes(s)
            assert escape(current_at_leave(s, room), 0, esc) == (True, 0), (room, spot, group)
    assert seen


def test_a_same_map_flag_left_set_would_keep_even_the_rooms_own_spot():
    # why the flag must never be left at 1: nothing in a room clears it (only a start in place, 0x140cf3320, or another
    # spot change), and with it set no 0x4049 naming that map ends the battle
    s = Session(10350, 10350)
    world.send_field_entry(s, 10359, 0, leave_battle=True)
    assert escape(10350, 1, escapes(s)[0]) == (False, 1)


# --- the ruled-out candidates: every 0x50cf names troops the client has, in every room of the route ---

def enter_cell_uid(w):
    b = bytes(w.buf)
    assert struct.unpack_from("<H", b)[0] == 1                  # one entry per 0x50cb (send_np_troop, send_enter_cell)
    return struct.unpack_from("<H", b, 3 + 0x11)[0]


@pytest.mark.parametrize("spot", ROUTE)
def test_every_simulation_grant_names_troops_the_client_has(spot):
    # the room at the end of loading and every later step (the hero's 0x50cb, the zone troops 3 s on), the client
    # binding each troop once its 0x50cb arrives (BindTroopRes 0x50ab, the hero first, as live); a 0x50cf must name a
    # target and a reference the client was sent and has bound before it, each target once
    role, s = start_room(spot)
    have, grants, cells = set(), [], set()
    i = 0
    while i < len(s.sent):
        w = s.sent[i]
        i += 1
        if w.proto == game.S2C_ENTER_CELL_TROOP:
            uid = enter_cell_uid(w)
            cells.add(uid)
            role.handlers[game.C2S_TROOP_BOUND](s, pkt(game.C2S_TROOP_BOUND, struct.pack("<H", uid)))
            have.add(uid)
        elif w.proto == game.S2C_TROOP_SIMULATION:
            target, reference = struct.unpack("<HH", bytes(w.buf))
            assert target in have and reference in have, (spot, target, reference)
            assert reference == 0                               # the hero troop, not the player slot
            grants.append(target)
    assert len(grants) == len(set(grants))
    if game.is_field(spot):
        assert set(grants) == cells - {0} and grants
    else:
        assert grants == []                                     # missions simulate their own (FIELD-SIMULATION.md)
    if spot == 10359:
        assert len(grants) == 225 and grants[0] == 10089         # as live: 225, the first 13:54:21.733 for 10089


# --- the same pattern after a won mission: a windowless win back onto its own map ---

@pytest.mark.parametrize("spot, qid, back", [(10358, 1150301, 10350), (10362, 1150703, 10351)])
def test_a_windowless_win_back_onto_its_own_map_leaves_as_a_field_warp(spot, qid, back):
    # Grey Fog 10358 -> Mist Field 10350 (live 09:32:18 by 0x4041), Lunawing Sortie II 10362 -> the crash site 10351:
    # 0x4041 ends the battle but makes the field current, which left the flag at 1 in the field's room, and the next
    # 0x4049 there (a quest warp, an Esc to the world map) kept the battle
    from test_scenes_10362 import ACCT, State as Rooms, Session as Conn, room, sent
    st = Rooms()
    c = {"id": 1, "class": 0, "level": 8, "spot": 10350, "pos": [158000, 0, 134000],
         "quests": {"active": {str(qid): {"counts": [0] * 5}}, "done": []},
         "mission": {"spot": spot, "quest": qid, "back": back}}
    ws = Conn(c, game_addr=("127.0.0.1", 25004), battle_spot=spot)
    st.world_sessions[ACCT] = ws
    g = room(st, c, spot)
    game.end_without_window(g, st, c, spot, 0, 100)
    assert not sent(g, game.S2C_MISSION_LEAVE)
    [esc] = [w for w in ws.sent if w.proto == world.S2C_MISSION_ESCAPE]
    assert escape(current_at_leave(ws, spot), 0, esc) == (True, 0)
    while ws.pending:
        ws.pending.pop(0)[1]()
    assert [struct.unpack_from("<I", b, 8)[0] for b in sent(ws, world.S2C_GAME_SERVER)] == [back]
    assert c["spot"] == back and "mission" not in c


def test_a_windowless_win_without_a_world_session_still_leaves_by_0x4041():
    from test_battle import mission_room
    s = mission_room(10358)
    s.data["char"] = s.data.get("char") or {"id": 1, "class": 0, "quests": {"active": {}, "done": []}}
    s.data["char"]["mission"] = {"spot": 10358, "quest": 1150301, "back": 10350}
    game.end_without_window(s, SimpleNamespace(save=lambda: None), s.data["char"], 10358, 0, 100)
    leave = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_MISSION_LEAVE]
    assert len(leave) == 1 and obf.dec_u32(leave[0][4:8]) == 10350
    assert client_flag(10358, 10350, 0) == 1                    # what that 0x4041 leaves set: kept only as a fallback

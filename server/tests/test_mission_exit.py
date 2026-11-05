"""Every way out of a mission room ends in a loaded field or town (planning/research/MISSIONS-MATRIX.md shared blocker 1,
row T11; the evidence planning/quality/GREYROCK-20261009.md:640). Each test replays the captured order of messages of
one exit path, and `client_after` is the client's own rule for what it does with a MissionEscape 0x4049, so a reply the
client would sit on is caught here:

- GameStateBattleField::Packet_MissionEscape 0x140d00590 first sets the current spot to the block's spot through
  0x140d65b10 -> 0x140d65c60, which sets common+0x1728 = 1 (the new spot a Field) or 2 when the old and new spots'
  spottable Map_File (row +0x110, parser 0x141865c00) are the same map once 0x140d71c00 drops a leading
  "<number>_" / "Test_" and a trailing "_P..." part, and the new one has no "_RIFT"; else 0 (unchanged when the spot
  is the same).
- With common+0x1728 == 0 it ends the battle (0x140cffb10) and, kind 0, loads the town (+6 == 2) or the world map
  (0x140cbc870), kind 3 / 4, waits for a warp (0x140cbd370); with it set (0x140d006d8) it only stores the position.
  Either way, after 0x4048 (GameStateManager+0x129) it drops the game link (0x140791800).
- So a same-map reply, or a warp kind, leaves the client in the battle state waiting for the world's 0x3f41 into the
  next room; the native run of 2026-10-09 15:00:08 (Lunawing I 10361 -> 10350, both 1_MistField) got 0x4049 kind 0 and
  nothing after it: "ShowLoadingWait" at 15:00:11 and a black screen for more than 40 s.
- Where an early exit ends (2026-10-24, build/exit2): on another map than the spot it was entered from, the world map
  at that spot (kind 0, +6 1), where the client prints a mission exit's lost gold / exp (0x4049 +0 / +0xe, read only
  by GameStateWorldMap::OnEnter 0x140d363d0 -> 0x140d66680, texts 7382 / 7381); on the same map, that field's room.
- Every room entry runs the pending warp's EnterScript (BattleField OnEnter 0x140ceeb38, no once-only record), so a
  plain entry (login, redirect, exit) takes a group whose warp plays no cutscene; a quest's SpotWarp and a won
  mission's return warp still play theirs.
Reads the installed game's tables and zone files. Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import game, obf, quest, tables, world
from kuf2.packet import Reader


def pkt(proto, body=b""):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


class Session:
    """The world connection of a player whose client is in room `room` (the world sent it there: battle_spot)."""
    def __init__(self, room, spot, active=(), **char):
        c = {"id": 1, "class": 0, "level": 10, "spot": spot, "pos": [0, 0, 0],
             "quests": {"active": {q: {"counts": [0] * 5} for q in active}, "done": []}}
        c.update(char)
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}, "game_addr": ("127.0.0.1", 25004)}
        if room is not None:
            self.data["battle_spot"] = room
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self):
        while self.pending:
            self.pending.pop(0)[1]()


class Room:
    """The game session of the room (state.game_sessions): what the leave reads of it."""
    def __init__(self, spot, **data):
        self.data = {"spot": spot, **data}


class State:
    def __init__(self, room=None):
        self.game_sessions = {1: room} if room is not None else {}

    def save(self):
        pass


def client_map(spot):
    """The map name the client compares (0x140d71c00 on spottable Map_File)."""
    m = tables.by_id("spottable")[str(spot)]["Map_File"]
    head, _, rest = m.partition("_")
    if rest and (head.isdigit() or head == "Test"):
        m = rest
    j = m.rfind("_")
    if j > 0 and len(m) - j > 2 and m[j + 1] == "P":
        m = m[:j]
    return m


def client_after(room, w):
    """What the client in `room` does with the 0x4049 w: ("room", spot) it waits in the battle state for the world's
    0x3f41 into spot; ("town", spot) / ("worldmap", spot) it loads that state by itself."""
    b = bytes(w.buf)
    assert w.proto == world.S2C_MISSION_ESCAPE and len(b) == 2 + 0x1d and b[:2] == bytes(2)
    blk = b[2:]
    spot, kind, dest = obf.dec_u32(blk[0x17:0x1b]), blk[0x16], blk[6]
    assert struct.unpack_from("<H", blk, 0x1b)[0] == game.MY_SLOT     # else "another player left"
    assert blk[0:5] == obf.u40(0) and blk[0xe:0x16] == bytes(8)       # no gold / exp lost (texts 7382 / 7381)
    same = spot != room and client_map(spot) == client_map(room) and "_RIFT" not in client_map(spot)
    if same or kind in (3, 4):
        return "room", spot
    return ("town" if dest == world.ESCAPE_TO_TOWN else "worldmap"), spot


def battle_ends(room, w):
    """Whether the client in `room` ends its battle on the 0x4049 w (0x140d00590): only when the spot change leaves
    common+0x1728 at 0 (the room's own spot, or another map). A kept battle runs into the next room's 0x3f4e start,
    whose go then deletes the Player its 0x3f4f made (unless its header started it in place: a same-map mission), so
    that room has no local player (test_same_map_rooms: the 2026-10-24 13:54:21 crash in 10359)."""
    spot = obf.dec_u32(bytes(w.buf)[2 + 0x17:2 + 0x1b])
    return spot == room or client_map(spot) != client_map(room) or "_RIFT" in client_map(spot)


def protos(s):
    return [w.proto for w in s.sent]


def warps(s):
    """The warp ids of every 0x5641 type 1 sent."""
    return [obf.dec_u32(bytes(w.buf)[1:5]) for w in s.sent if w.proto == world.S2C_WARP_PROCESS and w.buf[0] == 1]


def scene(warp):
    """Whether a warp's EnterScript plays a cutscene (what BattleField OnEnter would replay)."""
    return "RTS.PlayCutScene" in tables.by_id("warpinfo")[str(warp)]["EnterScript"]


def game_server_spots(s):
    return [struct.unpack_from("<I", bytes(w.buf), 8)[0] for w in s.sent if w.proto == world.S2C_GAME_SERVER]


def escape(s, st):
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[world.C2S_MISSION_ESCAPE](s, pkt(world.C2S_MISSION_ESCAPE))
    return role


def ends_loaded(role, s, room):
    """Play the client's side after the exit until it stands in a room or a town; return ("field" | "town" |
    "worldmap", spot). A wait for a room that no 0x3f41 answers fails here: the 2026-10-09 15:00:08 black screen."""
    esc = [w for w in s.sent if w.proto == world.S2C_MISSION_ESCAPE]
    assert len(esc) == 1
    what, spot = client_after(room, esc[0])
    s.run_later()
    if what == "room":                                  # it waits for the world's 0x3f41, whatever room that names
        rooms = game_server_spots(s)
        assert len(rooms) == 1, "the client waits for a room the server never sends"
        assert battle_ends(room, esc[0]), "the battle is kept into the next room: no local player there"
        return "field", rooms[0]
    assert game_server_spots(s) == []                   # the client loads by itself; a 0x3f41 now would be a 2nd entry
    if what == "worldmap":
        return what, spot
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(spot)))      # the town loaded: 0x3746
    s.run_later()
    if game.is_field(spot):                             # a field runs as a battle room: the town path's redirect
        assert game_server_spots(s) == [spot]
        return "field", spot
    assert world.S2C_ENTER_TOWN in protos(s) and game_server_spots(s) == []
    return "town", spot


# --- the captured failure: Esc / MissionExit in Lunawing I, 2026-10-09 15:00:08 ---

def test_the_esc_exit_from_lunawing_returns_to_the_field_it_left():
    # world_20261009_145601: 14:57:40 quest 1150703's SpotWarp 621 took the hero from Mist Field 10350 (group 6, beside
    # Glen 6173) into 10361 (0x5641 + 0x4049 kind 3 + 0x3f41); 15:00:08.225 C2S 0x4048 -> .226 S2C 0x4049 kind 0, +6 1,
    # spot 10350, then only heartbeats. Both spots are 1_MistField: the client stayed, dropped the room and waited.
    # Group 6's only warp is 705 (16_LEV_GraySmoke, quest 1150602's SpotWarp): the exit takes the nearest plain group,
    # 3 (warp 608), so the cutscene is not replayed (the 14:56:47 relog into group 6 replayed it)
    s = Session(10361, 10350, active=["1150703"], pos=[154721, 0, 140352], field_group=[10350, 6],
                mission={"spot": 10361, "quest": 1150703, "back": 10351})
    st = State(Room(10361))
    role = escape(s, st)
    assert protos(s)[:2] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]  # the field's group, then the leave
    assert warps(s) == [608] and not scene(608) and scene(705)
    assert ends_loaded(role, s, 10361) == ("field", 10350)
    c = s.data["char"]
    assert c["spot"] == 10350 and c["field_group"] == [10350, 3] and "mission" not in c
    assert "1150703" in c["quests"]["active"] and c["quests"]["done"] == []      # the quest is kept, not cleared
    assert st.game_sessions == {} and s.data["battle_spot"] == 10350


def test_the_reply_the_capture_got_is_one_the_client_waits_on():
    # the oracle against the captured bytes themselves (15:00:08.226666): a same-map spot, so the client waits
    w = type("W", (), {})()
    w.proto, w.buf = world.S2C_MISSION_ESCAPE, bytes.fromhex(
        "000010c3c310100001584dd9e70000580000000000000000000cc3102c0100")
    assert client_after(10361, w) == ("room", 10350)
    assert client_after(10350, w) == ("worldmap", 10350)        # 13:36:46, the same reply from field 10350: world map


# --- every in-scope mission, left before its win ---

ENTRIES = [  # (mission, the spot it is entered from, its field group there or None for a town, where it ends)
    (10358, 10352, 2, "field"),         # Grey Fog: 1150301's warp 613 / Thompson 6304 in Glen's camp (1_MistField)
    (10361, 10350, 6, "field"),         # Lunawing I: Glen 6173 (1_MistField)
    (10362, 10351, 0, "field"),         # Lunawing II (1_NewHamptonHighway)
    (10233, 10350, 2, "worldmap"),      # Tower of Moonlight: door 500 beside Glen 6008 (1_TowerOfMoonlight)
    (10234, 10350, 0, "worldmap"),      # Grey Rock Fortress: door 501 (1_GrayrockFortress)
    (10235, 10354, 0, "worldmap"),      # New Hampton Castle: door 502 (1_NewHamptonCastle)
    (10235, 10001, None, "worldmap"),   # ... or NPC 7123 in Accolade
    (10303, 10001, None, "worldmap"),   # Flamegrass Valley: NPC 7125
    (10306, 10001, None, "worldmap"),   # Fort Valley Castle: NPC 7124
    (10331, 10001, None, "worldmap"),   # the training camps: NPCs 954 / 948
    (10345, 10001, None, "worldmap"),
]


@pytest.mark.parametrize("mission, left, group, ends", ENTRIES, ids=[f"{m}-from-{f}" for m, f, _, _ in ENTRIES])
def test_leaving_a_mission_before_its_win_ends_where_it_was_entered(mission, left, group, ends):
    # the same map: back into the field's room (the client's own wait for the 0x3f41); another map: the world map at
    # the spot it was entered from, where the client would print a lost-gold / exp penalty (none: no table gives one)
    char = {"field_group": [left, group]} if group is not None else {"pos": list(world.TOWN_ENTRY[left])}
    s = Session(mission, left, mission={"spot": mission, "quest": None, "back": left}, **char)
    role = escape(s, State(Room(mission)))
    assert ends_loaded(role, s, mission) == (ends, left)
    assert world.same_map(mission, left) == (ends == "field") == (client_map(mission) == client_map(left))
    assert s.data["char"]["spot"] == left and "mission" not in s.data["char"]
    assert not any(scene(w) for w in warps(s))
    if ends == "worldmap":
        assert protos(s) == [world.S2C_MISSION_ESCAPE] and s.data.get("on_worldmap") and "battle_spot" not in s.data


def test_a_mission_left_before_its_win_costs_its_aborted_ap_once():
    # spottable Troop_Mission_aborted (15 on Grey Rock): each deployed troop, when the room is left before the win
    from test_army import ap_pushes, army, entered
    c, ts = army(1, deck=(1,))
    _, g = entered(10234, c)                                    # Troop_Mission_Enter 15: AP 100 -> 85
    c.update(spot=10350, field_group=[10350, 0], mission={"spot": 10234, "quest": 1150601, "back": 10350})
    s = Session(10234, 10350)
    s.data["char"] = c
    s.data["account"]["characters"] = [c]
    role = escape(s, State(g))
    assert ts[0]["ap"] == 70 and ap_pushes(s) == [(ts[0]["uid"], 70)]
    assert ends_loaded(role, s, 10234) == ("worldmap", 10350)               # another map: the world map at the field


# --- after the win ---

def test_an_esc_exit_after_the_win_ends_where_mission_complete_would():
    # Tower of Moonlight won (its window up, Mission Complete not pressed), then Esc / MissionExit: 1150406's EndSpot
    # 10350 at the return group 2 with warp 30002 (9_Refugee_camp), as 0x4040 would; no aborted AP after a win
    s = Session(10233, 10350, active=["1150406"], field_group=[10350, 0],
                mission={"spot": 10233, "quest": 1150406, "back": 10350})
    role = escape(s, State(Room(10233, mission_won=True, deck={})))
    assert protos(s)[:2] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 30002
    assert ends_loaded(role, s, 10233) == ("field", 10350)
    c = s.data["char"]
    assert c["field_group"] == [10350, 2] and "mission" not in c and "mission_return" not in c   # the warp, once


def test_the_mission_complete_button_ends_in_the_field():
    # world_20261009_024245: 04:18:03.178 C2S 0x4040 -> .212 S2C 0x4041 (kind 0, +1 2, spot 10350); the client loads
    # the town state by itself, 04:18:27.289 C2S 0x3746 10350 -> 0x3747 ...; 04:18:29.315 S2C 0x3f41 10350
    s = Session(10234, 10350, active=["1150601"], mission={"spot": 10234, "quest": 1150601, "back": 10350})
    role = world.make(State(Room(10234, mission_won=True)), 0, "127.0.0.1", 0)
    role.handlers[game.C2S_MISSION_LEAVE](s, pkt(game.C2S_MISSION_LEAVE))
    out = bytes(s.sent[-1].buf)
    assert protos(s) == [game.S2C_MISSION_LEAVE] and out[:4] == bytes([0, 0, 0, 2]) and obf.dec_u32(out[4:8]) == 10350
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10350)))
    assert protos(s)[1] == world.S2C_ENTER_TOWN and game_server_spots(s) == []
    s.run_later()
    assert game_server_spots(s) == [10350] and s.data["char"]["field_group"] == [10350, 0]


# --- a field room and the lobby ---

def test_the_field_rooms_leave_opens_the_world_map():
    # world_20261009_132901: 13:36:46.722 C2S 0x4048 in Mist Field's room -> .723 S2C 0x4049 kind 0, +6 1, spot 10350
    # (its own spot: no same-map transfer), then the world map's 0x1049 at 13:36:53
    s = Session(10350, 10350, pos=[278506, 4687, 188899], field_group=[10350, 0])
    role = escape(s, State(Room(10350)))
    assert protos(s) == [world.S2C_MISSION_ESCAPE]
    assert ends_loaded(role, s, 10350) == ("worldmap", 10350) and s.data.get("on_worldmap")


def test_a_retry_after_the_exit_enters_the_mission_again():
    # Esc out of Lunawing I, then Glen 6173's entrance (0x3f48 10361) from the field room: the same entry as the first
    s = Session(10361, 10350, active=["1150703"], field_group=[10350, 6],
                mission={"spot": 10361, "quest": 1150703, "back": 10351})
    role = escape(s, State(Room(10361)))
    s.run_later()
    s.sent.clear()
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10361) + b"\x00"))
    s.run_later()
    assert protos(s) == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE, world.S2C_GAME_SERVER]
    assert game_server_spots(s) == [10361] and obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 621
    assert s.data["char"]["mission"] == {"spot": 10361, "quest": 1150703, "back": 10351}


def test_the_lobby_exit_from_a_mission_keeps_the_field_and_costs_its_aborted_ap():
    # the Esc menu's CurrentStateExit (0x1055 -> 0x1056) in Grey Rock: the saved spot stays the field it was entered
    # from (the relog lands there) and the abort is paid as for MissionExit
    from test_army import ap_pushes, army, entered
    c, ts = army(1, deck=(1,))
    _, g = entered(10234, c)
    c.update(spot=10350, field_group=[10350, 0], mission={"spot": 10234, "quest": 1150601, "back": 10350})
    s = Session(10234, 10350)
    s.data["char"] = c
    s.data["account"]["characters"] = [c]
    st = State(g)
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[world.C2S_TO_LOBBY](s, pkt(world.C2S_TO_LOBBY))
    assert s.sent[-1].proto == world.S2C_TO_LOBBY and st.game_sessions == {}
    assert ts[0]["ap"] == 70 and ap_pushes(s) == [(ts[0]["uid"], 70)] and c["spot"] == 10350


# --- a second leave while the first one's room change is pending ---

def test_a_second_leave_before_the_rooms_0x3f41_is_ignored():
    # report 2026-10-24_missionexit section 4: an impatient second Esc -> Exit in the 5 s before the 0x3f41 (the client
    # waits in the battle state, its Esc menu still open to it). Answering it marked the world session as on the world
    # map with no room (on_worldmap, no battle_spot) while the client went on into the field's room, and the next warp
    # from that room skipped its leave 0x4049
    s = Session(10361, 10350, active=["1150703"], field_group=[10350, 6],
                mission={"spot": 10361, "quest": 1150703, "back": 10351})
    st = State(Room(10361))
    role = escape(s, st)
    n = len(s.sent)
    role.handlers[world.C2S_MISSION_ESCAPE](s, pkt(world.C2S_MISSION_ESCAPE))       # the second leave: no answer
    assert len(s.sent) == n
    s.run_later()
    assert game_server_spots(s) == [10350] and "entering" not in s.data
    assert s.data["battle_spot"] == 10350 and not s.data.get("on_worldmap")
    s.sent.clear()
    quest.spot_warp(s, st, 1150110)             # a later warp out of that room (SpotWarp 620) still leaves it first
    assert protos(s) == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]


def test_a_leave_while_a_mission_entry_is_pending_is_ignored():
    # the same window on the way in: Glen 6173's entrance from the field room (0x5641 621, 0x4049, 0x3f41 in 5 s); a
    # leave in between used to read the mission spot from battle_spot, drop its record and send a second room change
    s = Session(10350, 10350, active=["1150703"], field_group=[10350, 3])
    role = world.make(State(), 0, "127.0.0.1", 0)
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10361) + b"\x00"))
    n = len(s.sent)
    role.handlers[world.C2S_MISSION_ESCAPE](s, pkt(world.C2S_MISSION_ESCAPE))
    assert len(s.sent) == n
    s.run_later()
    assert game_server_spots(s) == [10361] and protos(s).count(world.S2C_MISSION_ESCAPE) == 1
    assert s.data["char"]["mission"] == {"spot": 10361, "quest": 1150703, "back": 10351}


# --- arrival cutscenes: a plain entry never replays one, an arrival through the warp still plays it ---

def entered_by_login(spot, group, **char):
    """The town path's redirect into a field (a login, a world-map arrival): 0x3746, then 0x5641 and 0x3f41."""
    s = Session(None, spot, field_group=[spot, group], **char)
    role = world.make(State(), 0, "127.0.0.1", 0)
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(spot)))
    s.run_later()
    assert game_server_spots(s) == [spot]
    return s


@pytest.mark.parametrize("spot, group, plain, warp", [
    (10350, 6, 3, 608),     # 705 16_LEV_GraySmoke -> the nearest plain group (the 14:56:47 relog replayed it)
    (10350, 5, 0, None),    # 704 17_LEV_MoonLight -> group 0, the room's default (spottable SPGroupID_1): no warp
    (10352, 2, 1, 205),     # 620 15_LEV_MistForest -> group 1
    (10350, 2, 2, 607),     # a plain group stays
])
def test_a_plain_entry_takes_a_group_whose_warp_plays_no_cutscene(spot, group, plain, warp):
    s = entered_by_login(spot, group)
    assert warps(s) == ([warp] if warp else []) and not any(scene(w) for w in warps(s))
    assert s.data["char"]["field_group"] == [spot, plain]
    assert world.plain_group(spot, group) == plain


@pytest.mark.parametrize("qid, warp, spot, group", [
    (1150602, 705, 10350, 6),       # 16_LEV_GraySmoke
    (1150502, 704, 10350, 5),       # 17_LEV_MoonLight
    (1150110, 620, 10352, 2),       # 15_LEV_MistForest
])
def test_a_quests_spotwarp_arrives_with_its_cutscene_and_the_next_login_does_not(qid, warp, spot, group):
    # the scene warps are the accept SpotWarps of these quests (questtable QuestAccept_Action_Value): the accept is
    # the first arrival through the warp, so its 0x5641 carries it; the relog after it takes a plain group
    s = Session(10350, 10350, active=[str(qid)])
    quest.spot_warp(s, State(), qid)
    assert warps(s) == [warp] and scene(warp) and s.data["char"]["field_group"] == [spot, group]
    s.run_later()
    assert game_server_spots(s) == [spot]
    c = s.data["char"]
    again = entered_by_login(spot, group, pos=c["pos"])
    assert not any(scene(w) for w in warps(again)) and again.data["char"]["field_group"] != [spot, group]


def test_the_grey_fog_return_still_plays_the_village_chief_once():
    # Grey Fog won, Mission Complete (0x4040 -> 0x4041): its return warp 30001 (10350 group 0, 11_Village_chief) comes
    # with the field entry after it, once; the relog after that sends no warp (group 0 is the room's default)
    s = Session(10358, 10350, active=["1150301"], mission={"spot": 10358, "quest": 1150301, "back": 10350})
    role = world.make(State(Room(10358, mission_won=True)), 0, "127.0.0.1", 0)
    role.handlers[game.C2S_MISSION_LEAVE](s, pkt(game.C2S_MISSION_LEAVE))
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10350)))
    s.run_later()
    assert warps(s) == [30001] and scene(30001) and game_server_spots(s) == [10350]
    assert "mission_return" not in s.data["char"]
    assert warps(entered_by_login(10350, 0)) == []

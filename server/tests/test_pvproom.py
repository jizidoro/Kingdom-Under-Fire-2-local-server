"""The PvP waiting room of one (server/kuf2/pvproom.py), each request through its registered handler. read_room is the
client's parser (0x14062bef0, 0x14062c160, 0x14062c3d0, 0x14062c060), so a byte out of place fails here. The dig and
the verdicts: planning/agents/reports/2026-11-05_contract3-roomofone.md.
Run: py -m pytest -q server/tests"""
import struct
from copy import deepcopy

import pytest

from kuf2 import obf, pvproom, tables, world
from kuf2.packet import Reader
from test_army import army
from test_rewards import Session, State

GAME = ("127.0.0.1", 7777)
SPOT = 20923                    # PVP_WAR, Limit_Party 8, Limit_Troop_1 1: 16 team seats
HERO_ONLY = 10380               # PVP_HERO, Limit_Party 1, Limit_Troop_1 0: 2 team seats, no troops
AI_SPOT = 20954                 # PVP_AI: the client's own room, never a 0x3e42
TOWN = 10354                    # no PvP spot
REFUSED_MOVE = (0x3e54, struct.pack("<H", 0x1c2d))
REFUSED_READY = (0x3e5b, struct.pack("<H", 1))
LEFT = (0x3e5d, bytes(2))
CREATE = b"room\0" + bytes([1, 4, 1])


def match_create(spot):
    return b"room\0" + obf.u32(spot) + bytes([0, 1, 0])


def ask(role, s, proto, body=b""):
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


@pytest.fixture(scope="module")
def role():
    return world.make(State(), 0, *GAME)


def session(spot=None, *sets):
    c, _ = army(*sets)
    s = Session(c)
    if spot is not None:
        s.data["target_spot"] = spot
    return s


def read_room(body):
    """0x3e57 as the client reads it: {spot, x, members: [{seat, id, ready, name, records: {index: record}}]}."""
    def take(n):
        nonlocal at
        at += n
        return body[at - n:at]

    at = 0
    assert take(2) == bytes(2)
    room = {"spot": obf.dec_u32(take(4)), "x": obf.dec_u32(take(4)), "members": []}
    for _ in range(take(1)[0]):
        seat, player, _, ready = struct.unpack("<HIBB", take(8))
        end = body.index(0, at)
        name = take(end - at).decode()
        take(1)
        records = {}
        for _ in range(take(1)[0]):
            r = take(11)
            records[r[6]] = {"troop_level": r[0], "leader_level": r[1], "troop": obf.dec_u32(r[2:6]),
                             "leader": struct.unpack_from("<I", r, 7)[0]}
        room["members"].append({"seat": seat, "id": player, "ready": ready, "name": name, "records": records})
    assert at == len(body)                      # the client's reader ends here: nothing owed, nothing left over
    return room


def test_every_pvp_point_row_is_the_clients_room_making_kind():
    # Pvp_Only (row +0xc9) is what sends the list's "RoomMaking" to the prefilled window and 0x3e45 to 0x140d3ff40
    rows = [r for r in tables.by_id("spottable").values() if r.get("Spot_Type") == "PVP_POINT"]
    assert rows and all(r["Pvp_Only"] == "True" and int(r["Limit_Party"]) > 0 for r in rows)


def test_a_room_opens_at_the_markers_pvp_spot_in_the_clients_order(role):
    # 0x3e43 clears the window's flag, 0x3e45 opens the scene (0x3e57 asserts without its sub-UI), 0x3e57 seats him,
    # 0x3e4a makes him master: the start button
    s = session(SPOT)
    got = ask(role, s, 0x3e42, CREATE)
    assert [p for p, _ in got] == [0x3e43, 0x3e45, 0x3e57, 0x3e4a]
    assert got[0][1] == b""
    assert got[1][1] == bytes(2) + obf.u32(SPOT) + b"\0"
    assert got[3][1] == struct.pack("<H", 0)
    room = read_room(got[2][1])
    assert room["spot"] == SPOT and room["x"] == 0xFFFFFFFF      # X != -1 would be room mode 1, the auto-start
    assert s.data["pvproom"] == {"spot": SPOT, "seat": 0, "ready": 0}


def test_the_seat_is_the_players_own_id_with_the_hero_and_the_deck_the_spot_allows(role):
    # the id must equal common+0xd4 or room +0xc8 stays -1; index 0 the hero; Limit_Troop_1 1 draws one troop
    s = session(SPOT, 1, 2)
    c = s.data["char"]
    member, = read_room(dict(ask(role, s, 0x3e42, CREATE))[0x3e57])["members"]
    assert (member["seat"], member["id"], member["ready"], member["name"]) == (0, c["id"], 0, c["name"])
    troop = c["troops"][0]
    assert member["records"] == {
        0: {"troop_level": 0, "leader_level": c["level"], "troop": 0xFFFFFFFF, "leader": 0},
        1: {"troop_level": troop["level"], "leader_level": 0, "troop": troop["id"], "leader": 0}}


def test_a_hero_only_spot_and_an_empty_deck_send_the_hero_alone(role):
    for s in (session(HERO_ONLY, 1, 2), session(SPOT)):
        member, = read_room(dict(ask(role, s, 0x3e42, CREATE))[0x3e57])["members"]
        assert list(member["records"]) == [0]


@pytest.mark.parametrize("spot", [None, TOWN, AI_SPOT, 999999999])
def test_a_marker_on_no_pvp_spot_opens_nothing(role, spot):
    # the bare 0x3e43 of before: the window stays, no room is held
    s = session(spot)
    assert ask(role, s, 0x3e42, CREATE) == [(0x3e43, b"")]
    assert "pvproom" not in s.data


def test_the_match_windows_room_answers_last_because_it_opens_on_the_pending_flag(role):
    # 0x14061f2b0 opens only while +0xc4 is set, and 0x3e65 clears it
    s = session()
    got = ask(role, s, 0x3e61, match_create(HERO_ONLY))
    assert [p for p, _ in got] == [0x3e45, 0x3e57, 0x3e4a, 0x3e65]
    assert got[0][1] == bytes(2) + obf.u32(HERO_ONLY) + b"\0"
    assert got[3][1] == bytes(6)                # i16 0, four unread bytes
    assert read_room(got[1][1])["spot"] == HERO_ONLY


@pytest.mark.parametrize("body", [match_create(TOWN), match_create(AI_SPOT), b"", b"room", b"room\0", b"room\0\x01\x02"])
def test_the_match_window_is_refused_a_spot_that_is_not_a_pvp_point(role, body):
    s = session()
    assert ask(role, s, 0x3e61, body) == [(0x3e65, struct.pack("<H", 1))]
    assert "pvproom" not in s.data


def test_a_seat_move_echoes_only_the_players_own_id(role):
    s = session(SPOT)
    me = s.data["char"]["id"]
    ask(role, s, 0x3e42, CREATE)
    # the request's id is not echoed: another id would be slot 0xffff in 0x140629b80
    assert ask(role, s, 0x3e53, struct.pack("<HI", 8, 77)) == [(0x3e54, bytes(2) + struct.pack("<HI", 8, me))]
    assert s.data["pvproom"]["seat"] == 8
    assert read_room(bytes(pvproom.room_packet(s.data["char"], s.data["pvproom"]).buf))["members"][0]["seat"] == 8


@pytest.mark.parametrize("target", [0, 16, 19, 0xffff])
def test_a_move_onto_his_own_seat_or_past_the_teams_is_refused(role, target):
    # his own seat: the client would copy then clear it. Past Limit_Party * 2: it never lets him off it again
    s = session(SPOT)
    ask(role, s, 0x3e42, CREATE)
    assert ask(role, s, 0x3e53, struct.pack("<HI", target, 1)) == [REFUSED_MOVE]
    assert s.data["pvproom"]["seat"] == 0


def test_a_short_move_is_refused(role):
    s = session(SPOT)
    ask(role, s, 0x3e42, CREATE)
    assert ask(role, s, 0x3e53, b"\x01") == [REFUSED_MOVE]


def test_the_last_team_seat_is_a_seat(role):
    s = session(HERO_ONLY)
    ask(role, s, 0x3e42, CREATE)
    assert ask(role, s, 0x3e53, struct.pack("<HI", 2, 1)) == [REFUSED_MOVE]
    assert ask(role, s, 0x3e53, struct.pack("<HI", 1, 1)) == [(0x3e54, bytes(2) + struct.pack("<HI", 1, 1))]


def test_ready_is_told_back_at_his_seat(role):
    s = session(SPOT)
    me = s.data["char"]["id"]
    ask(role, s, 0x3e42, CREATE)
    ask(role, s, 0x3e53, struct.pack("<HI", 3, me))
    assert ask(role, s, 0x3e5a, b"\x01") == [(0x3e5b, bytes(2) + struct.pack("<HIBB", 3, me, 0, 1))]
    assert ask(role, s, 0x3e5a, b"\x00") == [(0x3e5b, bytes(2) + struct.pack("<HIBB", 3, me, 0, 0))]


def test_leaving_answers_zero_and_gives_the_ai_room_its_constants_back(role):
    # 0x3e5d non-zero only asserts and strands him; with no room the seat and ready answers are the AI room's again
    s = session(SPOT)
    ask(role, s, 0x3e42, CREATE)
    assert ask(role, s, 0x3e5c) == [LEFT]
    assert "pvproom" not in s.data
    assert ask(role, s, 0x3e53, struct.pack("<HI", 3, 1)) == [REFUSED_MOVE]
    assert ask(role, s, 0x3e5a, b"\x01") == [REFUSED_READY]
    assert ask(role, s, 0x3e5c) == [LEFT]


def test_a_second_room_starts_clean(role):
    s = session(SPOT)
    ask(role, s, 0x3e42, CREATE)
    ask(role, s, 0x3e53, struct.pack("<HI", 3, 1))
    ask(role, s, 0x3e5a, b"\x01")
    ask(role, s, 0x3e5c)
    assert [p for p, _ in ask(role, s, 0x3e42, CREATE)] == [0x3e43, 0x3e45, 0x3e57, 0x3e4a]
    assert s.data["pvproom"] == {"spot": SPOT, "seat": 0, "ready": 0}


def test_the_start_is_the_clients_refusal_and_sends_nothing_the_server_answers(role):
    # 0x1406279c0 stops at text 7559 with one seat taken; the ForceGameStart cheat's 0x3e4b has no reply handler
    s = session(SPOT)
    ask(role, s, 0x3e42, CREATE)
    assert ask(role, s, 0x3e4b) == []
    assert "pvproom" in s.data


def test_the_room_lives_in_the_session_and_never_in_the_save(role):
    s = session(SPOT, 1)
    before = deepcopy(s.data["char"])
    ask(role, s, 0x3e42, CREATE)
    ask(role, s, 0x3e53, struct.pack("<HI", 3, 1))
    ask(role, s, 0x3e5a, b"\x01")
    assert s.data["char"] == before
    ask(role, s, 0x3e5c)
    assert s.data["char"] == before
    assert session(SPOT).data.get("pvproom") is None


def test_a_seat_request_outside_any_room_is_the_ai_rooms(role):
    s = session(AI_SPOT)
    assert ask(role, s, 0x3e53, struct.pack("<HI", 3, 1)) == [REFUSED_MOVE]
    assert ask(role, s, 0x3e5a, b"\x01") == [REFUSED_READY]
    assert ask(role, s, 0x3e5c) == [LEFT]


def test_the_two_requests_left_the_constants(role):
    assert 0x3e42 not in world.EMPTY_REPLIES and 0x3e61 not in world.EMPTY_REPLIES
    assert pvproom.C2S_MOVE in world.EMPTY_REPLIES and pvproom.C2S_READY in world.EMPTY_REPLIES

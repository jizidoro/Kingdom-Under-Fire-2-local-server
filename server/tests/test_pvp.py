"""PvP rooms, matching, records and rankings on the world role (planning/todo/CONTRACT-COMPLETE-PLAN.md family 4, the
world-role half; the verdicts and their proofs: planning/agents/reports/2026-11-05_contract-pvp.md). Each request
through its registered handler: the reply the client's handler reads, never shorter than its unconditional reads.
No PvP season runs on this server (its number, dates and name travel in 0x1444 and are in no shipped table), so the
answers are the off-season ones and the client prints its own texts. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import obf, tables, world
from kuf2.packet import Reader
from test_rewards import Session, State, char

NO_SPOT = bytes.fromhex("9716971600")       # coded u32 -1, u8 0: 0x3e45's "no room" (0x140d84c20 / 0x14061f2b0 return)
AI_SPOTS = {20954: 0, 20955: 8, 20956: 0}  # aipctrooptable %AIPVP: the slot left for the player ("-")


def ask(role, s, proto, body=b""):
    """One request through the role's handler table; the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


@pytest.fixture(scope="module")
def role():
    return world.make(State(), 0, "127.0.0.1", 0)


@pytest.mark.parametrize("request_id, body, reply, answer", [
    # the room lists pop one queued page a reply (0x140d841c0, 0x14061edd0): i16 0, u16 total 0, i16 n 0
    (0x3e40, bytes([0, 1]), 0x3e41, bytes(6)),
    (0x3e63, bytes([1, 0]), 0x3e64, bytes(6)),
    # 0x3e43 (0x140cbeb80) reads nothing and clears the room-making window's pending flag
    (0x3e42, b"room\0" + bytes([1, 4, 1]), 0x3e43, b""),
    # a join names a listed room and none is ever listed: result 0 with spot -1 clears the join flag, no text
    (0x3e44, struct.pack("<I", 1) + b"\x01", 0x3e45, bytes(2) + NO_SPOT),
    (0x3e62, struct.pack("<I", 1) + b"\x01" + obf.u32(10380), 0x3e45, bytes(2) + NO_SPOT),
    # the waiting room's slot move and ready: no server room holds the player (0x1c2d / 1 -> text 7268)
    (0x3e53, struct.pack("<HI", 3, 1), 0x3e54, struct.pack("<H", 0x1c2d)),
    (0x3e5a, b"\x01", 0x3e5b, struct.pack("<H", 1)),
    (0x3e5c, b"", 0x3e5d, bytes(2)),
    # PvP against AI at a spot with no aipctrooptable %AIPVP row: 0x402 -> 0x140d680e0 text 5036 "Cannot enter the
    # room.", the start button works again (a spot with a row starts its room: pvp.py, tests/test_pvp_ai.py)
    (0x3e5e, obf.u32(10380), 0x3e5f, struct.pack("<H", 0x402)),
    # a spot that is no PVP_POINT (a PvP spot opens the room of one: pvproom.py, tests/test_pvproom.py)
    (0x3e61, b"room\0" + obf.u32(10354) + bytes([0, 1, 0]), 0x3e65, struct.pack("<H", 1)),
    (0x5742, b"", 0x5743, bytes(2)),
    (0x5748, b"", 0x5749, bytes(1)),                   # u8 n 0: no spot open for matching
    # the records: 0x42b is silent in 0x140622220; the status board then prints its own 30026
    (0x5840, struct.pack("<I", 1), 0x5841, struct.pack("<H", 0x42b)),
    (0x5846, struct.pack("<I", 1), 0x5847, struct.pack("<H", 0x42b)),
    (0x584c, struct.pack("<I", 1), 0x584d, struct.pack("<H", 0x42b)),
    # a ranking page: i16 0, u32 total 0, i16 n 0 (both read on 0: 0x140626c80); a name: 0x412 -> text 7076
    (0x5842, struct.pack("<I", 1), 0x5843, bytes(8)),
    (0x5848, struct.pack("<I", 1), 0x5849, bytes(8)),
    (0x584e, struct.pack("<I", 1), 0x584f, bytes(8)),
    (0x5844, b"Aldric\0", 0x5845, struct.pack("<H", 0x412)),
    (0x584a, b"Aldric\0", 0x584b, struct.pack("<H", 0x412)),
    (0x5850, b"Aldric\0", 0x5851, struct.pack("<H", 0x412)),
    # the matching schedule at the unlock level: a non-zero result leaves the client's schedule empty
    (0x1440, b"", 0x1441, struct.pack("<H", 1)),
])
def test_a_pvp_request_gets_the_off_season_answer_its_handler_reads(role, request_id, body, reply, answer):
    assert ask(role, Session(char(level=30)), request_id, body) == [(reply, answer)]


def test_matching_is_refused_with_a_result_code_alone(role):
    # 0x5741 (0x14061eb00) reads 6 more bytes only on 0; the code today prints "PvPMatchRequest UnKnown Error : 1",
    # 0x4408 would print the client's 70003 "Cannot engage in PvP at the moment." (the report, For the coordinator)
    (reply, body), = ask(role, Session(char(level=30)), 0x5740, b"\x01" + obf.u32(20904))
    assert reply == 0x5741 and len(body) == 2 and struct.unpack("<H", body)[0] != 0


@pytest.mark.parametrize("request_id", [0x3e4b,      # a server room's start: no 0x3e4c case in any dispatcher
                                        0x3e51,      # builder 0x140f0f3c0 has no caller; 0x3e52 is never sent
                                        0x1443])     # the season notice: unanswered, the status board says 30026
def test_nothing_is_sent_where_no_answer_is_due(role, request_id):
    assert ask(role, Session(char(level=30)), request_id) == []


def test_every_room_list_request_gets_exactly_one_reply(role):
    # each 0x3e40 / 0x3e63 pushes its page on a deque the reply pops unconditionally: one reply a request, in order
    s = Session(char(level=30))
    for page in (1, 2, 3):
        assert [p for p, _ in ask(role, s, 0x3e63, bytes([page, 0]))] == [0x3e64]
        assert [p for p, _ in ask(role, s, 0x3e40, bytes([0, page]))] == [0x3e41]


def test_the_shipped_tables_hold_no_pvp_season():
    # the season's grades are empty and the rank rewards switched off; nothing else names a season's dates
    pvp = tables.sections("pvp")
    assert pvp["SeasonGrade"] == []
    assert pvp["RankReward"] == [{"Solo_Rank": "False", "Team_Rank": "False"}]


def test_the_ai_opponents_of_the_three_tutorial_spots_are_whole_in_the_tables():
    # what the PvP-against-AI room is built from (pvp.py; tests/test_pvp_ai.py): 16 slots a spot, one the player's,
    # each other an AIPCPreset of that spot with its hero row and its troops' rows
    ai = tables.sections("aipctrooptable")
    presets = {r["AIPC_ID"]: r for r in ai["AIPCPreset"]}
    heroes = {r["AIPCHero_Id"] for r in ai["AIPCHero"]}
    troops = {r["AIPCTroop_Id"] for r in ai["AIPCTroop"]}
    rows = {int(r["SpotID"]): [r[f"AIPC_ID_{i}"] for i in range(16)] for r in ai["AIPVP"]}
    assert set(rows) == set(AI_SPOTS)
    for spot, slots in rows.items():
        spot_row = tables.by_id("spottable")[str(spot)]
        assert (spot_row["Spot_Type"], spot_row["Spot_Sub_Type"]) == ("PVP_POINT", "PVP_AI")
        assert [i for i, v in enumerate(slots) if v == "-"] == [AI_SPOTS[spot]]
        for v in slots:
            if v == "-":
                continue
            p = presets[v]
            assert p["ActiveSpot"] == str(spot) and p["AIPCHeroID"] in heroes
            mine = [p[f"AIPC_Troop_Slot_{k:02d}"] for k in range(1, 9) if p[f"AIPC_Troop_Slot_{k:02d}"] != "-"]
            assert mine and set(mine) <= troops

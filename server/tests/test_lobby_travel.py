"""Session / lobby and world-travel gaps of the client's contract (planning/client/session_lobby.md §5,
planning/client/world_travel.md §5): the server list, a taken name on create, the world-map 0x1040, 0x3f48 into a
Battle spot with no zone file, the statuses 0x10e4 answers. Reads the game tables from the installed game.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import login, obf, world
from kuf2.packet import Reader

NO_ZONE_BATTLE = 10236          # spottable Battle 1_StormpikeFortress: no zone file in the packages (144 of 260)


class Session:
    def __init__(self):
        self.data = {}
        self.sent = []
        self.pending = []
        self.now = 0.0

    def send(self, w):
        self.sent.append((self.now, w))

    def later(self, delay, fn):
        self.pending.append((self.now + delay, fn))

    def run_until(self, t):
        """Run the timers due by t in time order (a timer may schedule another)."""
        while True:
            due = sorted((p for p in self.pending if p[0] <= t), key=lambda p: p[0])
            if not due:
                self.now = t
                return
            self.pending.remove(due[0])
            self.now = due[0][0]
            due[0][1]()

    def out(self, proto):
        return [bytes(w.buf) for _, w in self.sent if w.proto == proto]


class State:
    saves = 0

    def __init__(self, *accounts):
        self.db = {"accounts": {str(a["id"]): a for a in accounts}}

    def save(self):
        self.saves += 1

    def issue_world_key(self, acct):
        return 0

    def create_character(self, acct, name, cls, look_hex):
        c = {"id": 100 + len(acct["characters"]), "name": name, "class": cls, "look": look_hex, "level": 1}
        acct["characters"].append(c)
        return c


def pkt(proto, body=b""):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def test_server_list_carries_the_server_id_at_wire_4_and_follows_the_ui_within_half_a_second():
    # 0x140e7c8e2..0x140e7c91f: wire +0 -> entry+4 (the name table key), wire +4 -> entry+0 (the server id that 0x1006
    # sends and the header pre-selects); live the list showed only at the second send, 5 s later (session_lobby.md §2)
    role = login.make(State(), 0, "127.0.0.1", 0)
    s = Session()
    s.data["account"] = {"id": 1}
    role.handlers[login.C2S_SERVER_LIST](s, pkt(login.C2S_SERVER_LIST))
    first = s.out(login.S2C_SERVER_LIST)[0]
    head, n = struct.unpack_from("<IH", first)
    key, server = struct.unpack_from("<II", first, 6)
    assert n == 1 and key == 1 and server == head == 1          # named "(EU) Curian" and pre-selected
    s.run_until(5.2)
    times = [t for t, w in s.sent if w.proto == login.S2C_SERVER_LIST]
    assert times[0] == 0 and all(b - a <= 0.5 for a, b in zip(times, times[1:])) and times[-1] >= 4.7
    role.handlers[login.C2S_SERVER_SELECT](s, pkt(login.C2S_SERVER_SELECT, struct.pack("<I", server)))
    sent = len(s.sent)
    s.run_until(60)
    assert not [w for _, w in s.sent[sent:] if w.proto == login.S2C_SERVER_LIST]      # none after the join


def test_create_refuses_a_name_already_taken():
    other = {"id": 2, "characters": [{"id": 5, "name": "Aldric", "class": 0}]}
    mine = {"id": 1, "characters": []}
    st = State(mine, other)
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["account"] = mine
    look = bytes(0x34) + struct.pack("<I", 0)
    role.handlers[world.C2S_CHAR_CREATE](s, pkt(world.C2S_CHAR_CREATE, b"Aldric\0" + look))
    assert s.out(world.S2C_CHAR_CREATE_RES)[-1] == struct.pack("<H", world.NAME_TAKEN)    # 0x100c 0x1404 -> text 77
    assert mine["characters"] == []
    role.handlers[world.C2S_CHAR_CREATE](s, pkt(world.C2S_CHAR_CREATE, b"Brenna\0" + look))
    assert s.out(world.S2C_CHAR_CREATE_RES)[-1] == struct.pack("<HI", 0, 100)
    assert [c["name"] for c in mine["characters"]] == ["Brenna"]


def test_the_world_map_position_leaves_the_town_position_alone():
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"id": 1, "pos": [100, 5, 200]}
    q, p15 = obf.pos_xz(5000, 7000)
    head = q + struct.pack("<h", 12) + bytes([p15])
    role.handlers[world.C2S_TOWN_MOVE](s, pkt(world.C2S_TOWN_MOVE, head + struct.pack("<f", 1.5) + bytes(2)))
    assert s.data["char"]["pos"] == [100, 5, 200]               # 13 bytes: the world map's (0x140efc110)
    role.handlers[world.C2S_TOWN_MOVE](s, pkt(world.C2S_TOWN_MOVE, head + bytes(3)))
    assert s.data["char"]["pos"] == [5000, 12, 7000]            # 10 bytes: the town's (0x140efc540)


def enter_spot(spot):
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"id": 1, "spot": 10352, "quests": {"active": {}, "done": []}}
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes(2)))
    return s


def test_a_battle_spot_without_a_zone_file_is_refused_not_faked():
    from kuf2 import game
    assert not game.is_mission(NO_ZONE_BATTLE) and not game.is_field(NO_ZONE_BATTLE)
    s = enter_spot(NO_ZONE_BATTLE)
    # 0x3f41 failure (0x140cbe770, reader 0x1405cee80): i16 code, u8 n; 0x1c0a -> "There is no game available."
    assert s.out(world.S2C_GAME_SERVER) == [struct.pack("<HB", 0x1c0a, 0)]
    assert "battle_spot" not in s.data and "mission" not in s.data["char"]
    s = enter_spot(10233)                                       # Tower of Moonlight: a zone file, the room as before
    assert struct.unpack_from("<H", s.out(world.S2C_GAME_SERVER)[-1])[0] == 0 and s.data["battle_spot"] == 10233


def test_status_info_lists_the_unexpired_kept_statuses_of_the_character():
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    now = time.time()
    s.data["char"] = {"id": 7, "timed_statuses": {"1000038": {"level": 1, "until": now + 600},
                                                  "1000040": {"level": 1, "until": now - 1}}}   # ran out
    role.handlers[0x10e3](s, pkt(0x10e3))
    out = s.out(0x10e4)[-1]
    # 0x140e0fc80: u32 character id (== common+0xd4), reader 0x140e145a0: u16 n, n x 9 bytes (kind, u16 seconds,
    # level, u32 status, flag); kind 0 / flag 1 is the list the hero's HUD reads (0x140e0e2f0 callers)
    char_id, n = struct.unpack_from("<IH", out)
    kind, left, level, sid, flag = struct.unpack_from("<BHBIB", out, 6)
    assert (char_id, n, len(out)) == (7, 1, 6 + 9) and (kind, level, sid, flag) == (0, 1, 1000038, 1)
    assert 598 <= left <= 600
    assert list(s.data["char"]["timed_statuses"]) == ["1000038"]      # the expired one is dropped
    s.data["char"] = {"id": 7}
    role.handlers[0x10e3](s, pkt(0x10e3))
    assert s.out(0x10e4)[-1] == struct.pack("<IH", 7, 0)

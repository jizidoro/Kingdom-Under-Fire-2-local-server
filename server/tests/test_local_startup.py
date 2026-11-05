"""Local platform login must select an existing account without touching other saves."""
import copy
import struct

import pytest

from kuf2 import login
from kuf2.packet import Reader, Writer
from kuf2.state import State


class Session:
    def __init__(self, peer="127.0.0.1"):
        self.peer = (peer, 12345)
        self.data, self.sent = {}, []

    def send(self, message):
        self.sent.append(message)


def request(identity=b"kuf2-offline:7", build=0x0131602D, flags=0x1C, tail=b""):
    return Reader(Writer(login.C2S_LOGIN_LOCAL).cstr(identity.hex()).u32(build).u32(flags).raw(tail).frame())


@pytest.fixture
def local(tmp_path):
    state = State(tmp_path / "db.json")
    state.db["accounts"] = {"steam-one": {"id": 3, "name": "Other", "characters": []},
                            "steam-two": {"id": 7, "name": "Owner", "characters": [{"id": 2, "name": "qwe123"}]}}
    state.save()
    before = state.path.read_bytes()
    role = login.make(state, 0, "127.0.0.1", 0)
    yield state, role.handlers[login.C2S_LOGIN_LOCAL]
    assert state.path.read_bytes() == before


def test_local_login_selects_requested_account_without_creating_or_renaming(local):
    state, handle = local
    before = copy.deepcopy(state.db)
    session = Session()
    handle(session, request())
    assert session.data["account"] is state.db["accounts"]["steam-two"]
    assert state.db == before
    assert [p.proto for p in session.sent] == [0x103A, 0x1021]
    assert bytes(session.sent[0].buf) == b"\0"
    result = Reader(session.sent[1].frame())
    assert result.u16() == 0
    result.take(8)
    assert result.i32() == 7


@pytest.mark.parametrize("packet", [request(b"kuf2-offline:1"), request(b"kuf2-offline:0"),
    request(b"kuf2-offline:07"), request(b"kuf2-offline:2147483648"), request(b"kuf2-offline:7\x00"),
    request(b"real-platform-ticket"), request(b"\xff"), request(build=0), request(flags=0),
    request(tail=b"extra"), Reader(Writer(0x1039).raw(b"no-null").frame()),
    Reader(Writer(0x1039).cstr("00").frame()),
    Reader(Writer(0x1039).cstr("gg").u32(0x0131602D).u32(0x1C).frame()),
    Reader(Writer(0x1039).cstr("f").u32(0x0131602D).u32(0x1C).frame())])
def test_invalid_identity_is_refused_without_mutation(local, packet):
    state, handle = local
    before = copy.deepcopy(state.db)
    session = Session()
    handle(session, packet)
    assert "account" not in session.data
    assert state.db == before
    assert len(session.sent) == 1 and session.sent[0].proto == 0x1021
    assert struct.unpack_from("<H", session.sent[0].buf)[0] != 0


@pytest.mark.parametrize("peer", ["192.168.0.2", "10.0.0.1", "::ffff:192.168.1.2", "bad-peer"])
def test_nonlocal_peer_cannot_select_a_save(local, peer):
    _, handle = local
    session = Session(peer)
    handle(session, request())
    assert "account" not in session.data


def test_repeat_login_cannot_switch_account(local):
    state, handle = local
    session = Session()
    handle(session, request())
    handle(session, request(b"kuf2-offline:3"))
    assert session.data["account"] is state.db["accounts"]["steam-two"]
    assert struct.unpack_from("<H", session.sent[-1].buf)[0] != 0

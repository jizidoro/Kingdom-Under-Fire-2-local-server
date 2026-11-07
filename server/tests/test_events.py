"""Family 7 of planning/todo/CONTRACT-COMPLETE-PLAN.md, "live service" (events.py): the event windows' empty lists,
the official boost events and their HUD push, the edition packages of the mail window's Package tab, and the Diamond
paths' refusals; each of the 17 requests through its registered handler. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import events, items, obf, tables
from kuf2.net import Role
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE, Reader

HERO_BOX, ACCOUNT_HERO_BOX = 603000012, 603000011      # item_container: the Hero Package's two boxes
SENT = 1_600_000_000


class Session:
    def __init__(self, account, c):
        self.data = {"char": c, "account": account}
        self.sent = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        pass


class State:
    """The save's shape: one account, its two characters."""
    def __init__(self):
        self.aldric = {"id": 1, "name": "Aldric", "class": 0, "level": 30, "gold": 1000, "bag": [],
                       "quests": {"active": {}, "done": []}}
        self.qwe = {"id": 2, "name": "qwe123", "class": 3, "level": 6, "gold": 50, "bag": [],
                    "quests": {"active": {}, "done": []}}
        self.account = {"id": 1, "characters": [self.aldric, self.qwe]}
        self.db = {"accounts": {"steam": self.account}}
        self.game_sessions, self.world_sessions, self.saves = {}, {}, 0

    def save(self):
        self.saves += 1


@pytest.fixture
def server():
    state = State()
    role = Role("world", 0, state)
    events.make(role, state)
    return role, state, Session(state.account, state.aldric)


def ask(role, s, proto, body=b""):
    """Send one request through the role's handler table; returns the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def packages(body):
    """S2C 0x5a4f as the client reads it (0x140e069d0): (total, page, [entry])."""
    total, page = struct.unpack_from("<HB", body, 0)
    out, at = [], 4
    if total:
        for _ in range(body[3]):
            pid, year, hour, month, left, minute, day, read, kind = struct.unpack_from("<IH7B", body, at)
            assert obf.dec_u40(body[at + 13:at + 18]) == 0
            m, at = body[at + 18], at + 19
            got = [(obf.dec_u32(body[at + 6 * k:]), obf.T1[body[at + 6 * k + 4]] << 8 | obf.T2[body[at + 6 * k + 5]])
                   for k in range(m)]
            at += 6 * m
            out.append(dict(id=pid, date=(year, month, day, hour, minute), left=left, read=bool(obf.T1[read] & 1),
                            kind=kind, items=got))
        assert at == len(body)
    return total, page, out


def english(table):
    """{"<id>/TEXT": text} of one of the game's English text tables."""
    return {r["TextID"]: r["Text"] for r in tables.sections("\\".join(("text", "eng", table + "_eng")))["TextTable"]}


# ---- everything off: the replies the server has always sent
@pytest.mark.parametrize("request_id, reply", [
    (0x1265, (0x1266, "00")),               # the live event list: no web page (CONSTANT; 362 sends at logins)
    (0x1267, (0x1268, "00")),               # the cash shop's banners (CONSTANT; 242)
    (0x126a, (0x126b, "00")),               # the attendance calendar's banners (CONSTANT; 109)
    (0x5a4e, (0x5a4f, "00000000")),         # the Package tab: nothing sent to this account (235)
    (0x4076, (0x4077, "00")),               # the realm war field's list (DEAD)
    (0x114f, (0x1150, "00")),               # the status popup's notice (DEAD): one empty cstr, never an empty body
    (0x108a, (0x108b, "000000")),           # the Diamond Storage: mode 0, total 0 (CONSTANT)
    (0x108c, (0x108d, "01c4")),             # take from it: 0xc401 -> textsystem 7268 (SOLO)
    (0x10cf, (0x10d0, "01c4")),             # take all from it (SOLO)
    (0x3757, (0x3758, "4264")),             # buy with Diamonds: 0x6442 -> 10040 "Cannot purchase it." (SOLO)
    (0x112a, (0x112b, "09c4")),             # buy a mileage good: 0xc409 -> 7144 "Mileage Shop is closed." (DEAD)
    (0x1155, (0x1156, "04000000")),         # the top-up tab: textsystem 4 (SOLO)
    (0x3751, (0x3752, "000000000000")),     # the limited sale: u32 0, i16 0 (CONSTANT)
])
def test_with_no_event_and_no_edition_each_request_gets_its_fixed_reply(server, request_id, reply):
    role, state, s = server
    body = {0x5a4e: b"\0", 0x108a: struct.pack("<I", 3), 0x108c: bytes(8),
            0x3757: b"\1" + struct.pack("<IB", 9000001, 1), 0x112a: b"\1" + struct.pack("<I", 7000001),
            0x1155: bytes(8)}.get(request_id, b"")
    assert ask(role, s, request_id, body) == [(reply[0], bytes.fromhex(reply[1]))]
    assert state.saves == 0 and "packages" not in state.account and "packages" not in state.aldric


def test_the_requests_nothing_waits_on_are_consumed_in_silence(server):
    role, state, s = server
    assert ask(role, s, 0x375b) == []                                   # the cash shop / summon board opening
    assert ask(role, s, 0x5a54, struct.pack("<IB", 11, 1)) == []        # a package opened: none exists
    assert state.saves == 0


def test_the_top_up_text_is_one_the_client_holds(server):
    # 0x1156 prints the textsystem row of its u32; an id without a row prints "nullptr" (0x140567c50)
    text = english("textsystem")
    assert text["4/TEXT"] == "This function is not supported at the moment."
    assert struct.unpack("<I", events.REPLIES[0x1155][1])[0] == 4


def test_the_dead_requests_gates_are_in_the_shipped_data():
    from kuf2 import settings
    # 0x114f: the status popup's HUD entry follows the publisher's GameStatusPopup; 0x112a: the Mileage shop's tab
    # follows MileageEnable, and its one good is paid in mileage nothing gives
    assert (settings.get("GameStatusPopup"), settings.get("MileageEnable")) == (0, 0)
    assert [(r["SellID"], r["MileagePrice"]) for r in tables.sections("item_mileage")["Base"]] == [("7000001", "10")]
    assert struct.unpack("<H", events.REPLIES[0x112a][1])[0] == 0xc409
    assert english("textsystem")["7144/TEXT"] == "Mileage Shop is closed."
    # 0x4076: only in a PVP_WAR_FIELD spot, and the one there is is closed
    field = [r for r in tables.sections("spottable")["SpotTable"] if r["Spot_Sub_Type"] == "PVP_WAR_FIELD"]
    assert [(r["ID"], r["Spot_Open"], r["TestMap"]) for r in field] == [("20507", "False", "True")]
    # the Diamond goods: every item_cash row is paid in Diamonds (1) or Cubic (2), none is free
    cash = tables.sections("item_cash")["Base"]
    assert {r["Currency"] for r in cash} == {"1", "2"} and all(int(r["CashPrice"]) > 0 for r in cash)


def test_the_fixed_replies_are_never_shorter_than_their_handlers_read():
    # crash sizes: 0x108b 3, 0x1156 4, 0x3758 2, 0x1150 a cstr (its NUL), the lists their count byte
    least = {0x1267: 1, 0x126a: 1, 0x4076: 1, 0x114f: 1, 0x108a: 3, 0x108c: 2, 0x10cf: 2, 0x3757: 2, 0x112a: 2,
             0x1155: 4, 0x3751: 6}
    assert set(least) == set(events.REPLIES)
    for request_id, (reply, body) in events.REPLIES.items():
        assert reply == request_id + 1 and len(body) >= least[request_id]
    for request_id in (0x108c, 0x10cf, 0x3757, 0x112a):                # a refusal is never the success code
        assert struct.unpack("<H", events.REPLIES[request_id][1])[0] != 0


# ---- boost events
def test_the_boosts_are_the_official_notes_rows_and_none_is_on():
    assert events.ACTIVE_BOOST is None and events.boost() is None
    assert [events.percent(k) for k in ("gold", "hero_exp", "troop_exp", "drop")] == [0, 0, 0, 0]
    assert events.boosted("gold", 85) == 85 and events.boosted("hero_exp", 11708) == 11708
    b = events.BOOSTS
    assert len(b) == 8
    assert b["boosts_2020_03"] == {"dates": "2020-03-16 .. end of April", "gold": 100, "hero_exp": 100,
                                   "troop_exp": 100, "source": "SN-boost, SN-boost2"}
    assert (b["festive_2020_12"]["gold"], b["festive_2020_12"]["drop"]) == (200, 100)
    assert all(set(row) <= {"dates", "source", "gold", "hero_exp", "troop_exp", "drop"} for row in b.values())
    with pytest.raises(KeyError):
        events.percent("silver")


def test_a_boost_that_is_on_pays_as_the_footage_and_is_named(monkeypatch):
    monkeypatch.setattr(events, "ACTIVE_BOOST", "boosts_2020_03")
    assert events.boosted("hero_exp", int(13009 * 0.9)) == 23416         # MISSIONS F6: the hero under the x2 event
    assert events.boosted("troop_exp", 1191) == 2382                     # Kedington's troops, part 13 7:14
    assert events.boosted("gold", 85) == 170 and events.boosted("drop", 2500) == 2500     # no drop boost in March
    monkeypatch.setattr(events, "ACTIVE_BOOST", "gold_2020_02")
    assert events.boosted("gold", 85) == 127                             # +50 %, rounded down
    monkeypatch.setattr(events, "ACTIVE_BOOST", "no_such_event")
    with pytest.raises(KeyError):
        events.boost()


def test_the_hud_is_told_the_boost_after_the_event_list(server, monkeypatch):
    # 0x1118 (0x140678600): obool clear, u8 n, n * (u64, u32 percent, i32 kind, coded u32 spot); the HUD's icons and
    # tooltips 7804 + kind: 0 hero exp, 1 troop exp, 2 gold, 3 item drop rate
    role, state, s = server
    monkeypatch.setattr(events, "ACTIVE_BOOST", "festive_2020_12")
    (first, listing), (second, body) = ask(role, s, 0x1265)
    assert (first, listing) == (0x1266, b"\0") and second == 0x1118
    assert body[0] == OBOOL_TRUE and body[1] == 4 and len(body) == 2 + 4 * 20
    rows = [struct.unpack_from("<QIi", body, 2 + 20 * k) + (obf.dec_u32(body[18 + 20 * k:]),) for k in range(4)]
    assert rows == [(0, 100, 0, 0), (0, 100, 1, 0), (0, 200, 2, 0), (0, 100, 3, 0)]
    monkeypatch.setattr(events, "ACTIVE_BOOST", "gold_2019_12")
    body = ask(role, s, 0x1265)[1][1]
    assert body == bytes([OBOOL_TRUE, 1]) + struct.pack("<QIi", 0, 100, events.BUFF_GOLD) + obf.u32(0)
    text = english("textui")
    assert [text[f"{7804 + k}/TEXT"].split(" increased")[0] for k in range(4)] == \
        ["Hero EXP", "Troop EXP", "Gold", "Item Drop Rate"]


# ---- edition packages
def test_the_packages_are_the_tables_editions():
    rows = events.package_rows()
    assert sorted(rows) == [10, 11, 20, 21, 22, 30, 31, 32, 33]
    assert events.contents(11, events.ACCOUNT) == [(ACCOUNT_HERO_BOX, 1)]
    assert events.contents(11, events.CHARACTER) == [(HERO_BOX, 1)]
    assert events.contents(10, events.ACCOUNT) == [] and events.contents(10, events.CHARACTER) == [(603000010, 1)]
    assert {(r["Account_Count"], r["Character_Count"]) for r in rows.values()} == {("1", "6")}
    for pid in rows:                                                    # every part is a box the bag can open
        for kind in (events.ACCOUNT, events.CHARACTER):
            assert all(items.container(code) is not None for code, n in events.contents(pid, kind))


def test_an_edition_is_sent_once_and_listed_on_the_package_tab(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    monkeypatch.setattr(time, "time", lambda: SENT)
    (reply, body), = ask(role, s, 0x5a4e, b"\0")
    total, page, shown = packages(body)
    t = time.localtime(SENT)
    assert reply == 0x5a4f and (total, page) == (2, 0)
    assert shown == [
        dict(id=11, date=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min), left=1, read=False,
             kind=events.ACCOUNT, items=[(ACCOUNT_HERO_BOX, 1)]),
        dict(id=11, date=(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min), left=6, read=False,
             kind=events.CHARACTER, items=[(HERO_BOX, 1)])]
    assert state.account["packages"] == [{"id": 11, "sent": SENT, "left": [1, 6]}] and state.saves == 1
    assert ask(role, s, 0x5a4e, b"\0") == [(reply, body)] and state.saves == 1     # not sent twice
    assert packages(ask(role, s, 0x5a4e, b"\1")[0][1]) == (2, 1, [])                # a page past the end


def test_opening_a_package_marks_it_read(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    ask(role, s, 0x5a4e, b"\0")
    assert ask(role, s, 0x5a54, struct.pack("<IB", 11, events.CHARACTER)) == []
    assert state.aldric["packages"] == {"11:1": {"read": True}}
    assert [e["read"] for e in packages(ask(role, s, 0x5a4e, b"\0")[0][1])[2]] == [False, True]
    saves = state.saves
    ask(role, s, 0x5a54, struct.pack("<IB", 11, events.CHARACTER))
    ask(role, s, 0x5a54, struct.pack("<IB", 99, events.CHARACTER))
    ask(role, s, 0x5a54, b"")
    assert state.saves == saves and state.aldric["packages"] == {"11:1": {"read": True}}


def test_taking_a_package_puts_its_box_in_the_bag_once_a_character_and_once_an_account(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    ask(role, s, 0x5a4e, b"\0")
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.CHARACTER))[-1] == (0x5a51, bytes(2))
    assert [(i["code"], i["count"]) for i in state.aldric["bag"]] == [(HERO_BOX, 1)]
    assert state.account["packages"][0]["left"] == [1, 5]
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a51, struct.pack("<H", 0x3c05))]
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.ACCOUNT))[-1] == (0x5a51, bytes(2))
    assert sorted((i["code"], i["count"]) for i in state.aldric["bag"]) == [(ACCOUNT_HERO_BOX, 1), (HERO_BOX, 1)]
    assert state.account["packages"][0]["left"] == [0, 5]
    # the taken entries stay on this character's tab, empty, as the client leaves them
    assert [(e["kind"], e["left"], e["items"], e["read"]) for e in packages(ask(role, s, 0x5a4e, b"\0")[0][1])[2]] == \
        [(events.ACCOUNT, 0, [], True), (events.CHARACTER, 5, [], True)]
    # the account's other character: the Account part is gone for good, the Character part is its own
    other = Session(state.account, state.qwe)
    total, page, shown = packages(ask(role, other, 0x5a4e, b"\0")[0][1])
    assert [(e["kind"], e["left"], e["items"]) for e in shown] == [(events.CHARACTER, 5, [(HERO_BOX, 1)])]
    assert ask(role, other, 0x5a50, struct.pack("<IB", 11, events.ACCOUNT)) == [(0x5a51, struct.pack("<H", 0x5c1d))]
    assert ask(role, other, 0x5a50, struct.pack("<IB", 11, events.CHARACTER))[-1] == (0x5a51, bytes(2))
    assert [(i["code"], i["count"]) for i in state.qwe["bag"]] == [(HERO_BOX, 1)]
    assert state.account["packages"][0]["left"] == [0, 4]


def test_the_sixth_character_part_is_the_last(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    ask(role, s, 0x5a4e, b"\0")
    state.account["packages"][0]["left"] = [0, 1]
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.CHARACTER))[-1] == (0x5a51, bytes(2))
    other = Session(state.account, state.qwe)
    assert packages(ask(role, other, 0x5a4e, b"\0")[0][1]) == (0, 0, [])
    assert ask(role, other, 0x5a50, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a51, struct.pack("<H", 0x5c1d))]
    assert state.qwe["bag"] == []


def test_a_package_is_refused_whole_when_the_bag_is_full_or_it_is_not_there(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    ask(role, s, 0x5a4e, b"\0")
    from kuf2 import world
    monkeypatch.setattr(world, "fits", lambda c, got, freed=None: False)
    saves = state.saves
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a51, struct.pack("<H", 0x3c03))]
    assert state.aldric["bag"] == [] and state.account["packages"][0]["left"] == [1, 6] and state.saves == saves
    for body in (struct.pack("<IB", 21, events.CHARACTER), struct.pack("<IB", 11, 7), b"\x0b"):
        assert ask(role, s, 0x5a50, body) == [(0x5a51, struct.pack("<H", 0x642a))]
        assert ask(role, s, 0x5a52, body) == [(0x5a53, struct.pack("<H", 0x642a))]
    assert state.saves == saves


def test_deleting_a_package_takes_it_off_this_characters_tab_only(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (11,))
    ask(role, s, 0x5a4e, b"\0")
    assert ask(role, s, 0x5a52, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a53, bytes(2))]
    assert [e["kind"] for e in packages(ask(role, s, 0x5a4e, b"\0")[0][1])[2]] == [events.ACCOUNT]
    assert state.account["packages"][0]["left"] == [1, 6] and state.aldric["bag"] == []     # no receipt was used
    assert ask(role, s, 0x5a52, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a53, struct.pack("<H", 0x642a))]
    assert ask(role, s, 0x5a50, struct.pack("<IB", 11, events.CHARACTER)) == [(0x5a51, struct.pack("<H", 0x642a))]
    other = Session(state.account, state.qwe)
    assert [e["kind"] for e in packages(ask(role, other, 0x5a4e, b"\0")[0][1])[2]] == [events.ACCOUNT, events.CHARACTER]
    # a taken one, deleted, is gone and stays taken
    ask(role, s, 0x5a50, struct.pack("<IB", 11, events.ACCOUNT))
    assert ask(role, s, 0x5a52, struct.pack("<IB", 11, events.ACCOUNT)) == [(0x5a53, bytes(2))]
    assert packages(ask(role, s, 0x5a4e, b"\0")[0][1]) == (0, 0, [])
    assert state.aldric["packages"]["11:0"] == {"taken": True, "read": True, "deleted": True}


def test_the_package_tab_pages_by_eight(server, monkeypatch):
    role, state, s = server
    monkeypatch.setattr(events, "EDITION_PACKAGES", (10, 11, 20, 21, 22, 30))      # 1 + 2 + 1 + 2 + 2 + 1 entries
    total, page, shown = packages(ask(role, s, 0x5a4e, b"\0")[0][1])
    assert (total, page, len(shown)) == (9, 0, 8)
    assert [(e["id"], e["kind"]) for e in shown] == [(10, 1), (11, 0), (11, 1), (20, 1), (21, 0), (21, 1), (22, 0),
                                                     (22, 1)]
    total, page, shown = packages(ask(role, s, 0x5a4e, b"\1")[0][1])
    assert (total, page, [(e["id"], e["kind"]) for e in shown]) == (9, 1, [(30, 1)])
    monkeypatch.setattr(events, "EDITION_PACKAGES", (10, 11, 20, 21, 22, 30, 12345))
    with pytest.raises(KeyError):                                       # a PackageID the table does not hold
        ask(role, s, 0x5a4e, b"\0")


def test_an_empty_package_entry_is_the_layout_the_client_reads():
    # 13 bytes, 5, the count, 6 an item: 0x140e07bc0 / 0x140dd97e0
    p = {"id": 11, "sent": SENT, "left": [1, 6]}
    t = time.localtime(SENT)
    b = events.entry(p, events.CHARACTER, [(HERO_BOX, 1)], False)
    assert len(b) == 13 + 5 + 1 + 6
    assert b[:13] == struct.pack("<IH", 11, t.tm_year) + bytes([t.tm_hour, t.tm_mon, 6, t.tm_min, t.tm_mday,
                                                               OBOOL_FALSE, 1])
    assert b[13:19] == obf.u40(0) + b"\1" and b[19:] == obf.u32(HERO_BOX) + obf.u16(1)
    assert events.entry(p, events.ACCOUNT, [], True)[8:13] == bytes([1, t.tm_min, t.tm_mday, OBOOL_TRUE, 0])

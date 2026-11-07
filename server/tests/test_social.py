"""Family 2 of planning/todo/CONTRACT-COMPLETE-PLAN.md, "needs another player": letters (player mail, social.py)
between the characters this server holds, each request through its registered handler; the fee the client computes;
and the constants that stay the original's "nobody there" answer. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import items, mail, obf, social, tables, world
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE, Reader

POTION = 350000010              # BIND_NONE, Tradable, MaxStack 100, SellPrice 8: the fee's floor of 1 a piece
SWORD = 101001500               # BIND_EQUIP_TIME, Tradable, MaxStack 1, SellPrice 286: 14 a piece
RAPIER = 101201110              # Supplied Adventurer Rapier: BIND_GAIN_TIME (bound in a bag) and not Tradable
DAY = 86400
ID = social.FIRST_ID + 1       # the first letter's id


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
def town():
    """(role, state, Aldric's session, qwe123's session): the world role as the coordinator wires it, social after
    mail."""
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    social.make(role, st)
    return role, st, Session(st.account, st.aldric), Session(st.account, st.qwe)


def ask(role, s, proto, body=b""):
    """One request through the role's handler table; the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def only(replies, proto):
    return next(b for p, b in replies if p == proto)


def give(c, code, count=1, slot=0, **extra):
    it = {"code": code, "slot": slot, "count": count, "serial": (c["id"] << 32) | (0x50000 + slot),
          "bound": items.bound_on_gain(code), **extra}
    c["bag"].append(it)
    return it


def letter(to, title="Supplies", body="For the road.", gold=0, pay=False, attached=()):
    """0x5244's body as the client builds it (0x140dfed40); attached: (bag record, count)."""
    b = b"".join(t.encode("latin-1") + b"\0" for t in (to, title, body))
    b += bytes([obf.via_t1(int(pay))]) + obf.u40(gold) + bytes([len(attached)])
    return b + b"".join(obf.u16(it["slot"]) + obf.u16(n) + obf.u64(it["serial"]) for it, n in attached)


def rows(body, block):
    """A list reply's entries: [(the fixed block, first cstr, second cstr)]."""
    page, total = body[0], struct.unpack_from("<H", body, 1)[0]
    out, at = [], 4
    for _ in range(body[3] if total else 0):
        head = body[at:at + block]
        a_end = body.index(0, at + block)
        b_end = body.index(0, a_end + 1)
        out.append((head, body[at + block:a_end].decode("latin-1"), body[a_end + 1:b_end].decode("latin-1")))
        at = b_end + 1
    assert at == max(len(body), 4) or not total
    return page, total, out


def test_a_character_without_letters_gets_the_bytes_the_constants_gave(town):
    # plan F4: 0x524d runs at every town entry, 0x5240 at every mailbox; an empty box answers as before
    role, st, a, q = town
    # the fixed replies world.EMPTY_REPLIES held until social.py was wired in (2026-11-05), live at every town entry
    before = {social.C2S_LIST: (0x5241, bytes(3)), social.C2S_SENT: (0x5250, bytes(3)),
              social.C2S_FLAG: (0x524e, bytes(1))}
    for req, (reply, body) in before.items():
        assert ask(role, a, req, b"" if req == social.C2S_FLAG else b"\0") == [(reply, body)]
    assert st.saves == 0


def test_the_fee_is_the_clients():
    # 0x140dfe4e0 / 0x140dfe600: max(1, x * MailFeePerc 0.05) in single precision, truncated; text alone is free
    assert social.fee(0, []) == 0
    assert [social.fee(g, []) for g in (1, 19, 20, 39, 40, 99, 100, 1000, 999_999_999)] == [1, 1, 1, 1, 2, 4, 5, 50,
                                                                                            50_000_000]
    assert items.sell_price(POTION) == 8 and items.sell_price(SWORD) == 286
    assert social.fee(0, [{"code": POTION, "count": 10}]) == 10                 # 8 x 0.05 = 0.4 -> the floor of 1 each
    assert social.fee(0, [{"code": SWORD, "count": 1}]) == 14
    assert social.fee(100, [{"code": POTION, "count": 3}, {"code": SWORD, "count": 1}]) == 5 + 3 + 14


def test_a_letter_to_the_accounts_other_character_arrives_with_its_gold_and_items(town):
    role, st, a, q = town
    stack = give(st.aldric, POTION, 10)
    sent = ask(role, a, social.C2S_SEND, letter("qwe123", gold=100, attached=[(stack, 3)]))
    assert sent[0] == (social.S2C_SEND, bytes(2)) and sent[1][0] == world.S2C_CARGO     # the answer, then the bag
    assert st.aldric["gold"] == 1000 - 100 - (5 + 3) and stack["count"] == 7            # the gold, the fee, 3 potions
    assert obf.dec_u40(sent[1][1][:5]) == 892
    assert [m["id"] for m in st.aldric["letters_sent"]] == [m["id"] for m in st.qwe["letters"]] == [ID]
    assert st.db["next_letter_id"] == ID and st.qwe.get("mail", []) == []                # not a system mail

    assert ask(role, q, social.C2S_FLAG) == [(social.S2C_FLAG, b"\x01")]                # the HUD's mail icon
    page, total, got = rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)
    head, sender, title = got[0]
    t = time.localtime(st.qwe["letters"][0]["sent"])
    assert (page, total, sender, title) == (0, 1, "Aldric", "Supplies")
    assert head == (bytes([OBOOL_FALSE, t.tm_min, t.tm_mday, t.tm_hour]) + struct.pack("<iH", ID, t.tm_year)
                    + bytes([t.tm_mon, 2, OBOOL_FALSE, OBOOL_FALSE, 2, OBOOL_FALSE]))   # unread, gold and item pending

    body = only(ask(role, q, social.C2S_READ, struct.pack("<BI", 0, ID)), social.S2C_READ)
    text_end = body.index(0, 2)
    assert body[:2] == bytes(2) and body[2:text_end] == b"For the road."
    assert obf.dec_u40(body[text_end + 1:text_end + 6]) == 100 and body[text_end + 6] == 1
    record = body[text_end + 7:]
    assert items.decode_head(record)[:3] == (POTION, 0, 3) and record[-1] == OBOOL_FALSE    # slot 0 of the window
    assert ask(role, q, social.C2S_FLAG) == [(social.S2C_FLAG, b"\0")]

    took = ask(role, q, social.C2S_TAKE_GOLD, struct.pack("<I", ID))
    assert took[-1] == (social.S2C_TAKE_GOLD, bytes(2)) and st.qwe["gold"] == 150       # the sender paid the fee
    assert only(ask(role, q, social.C2S_TAKE_GOLD, struct.pack("<I", ID)), social.S2C_TAKE_GOLD) == b"\x05\x3c"
    took = ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(4) + b"\0")
    assert took[-1] == (social.S2C_TAKE_ITEM, bytes(2)) and took[0][0] == world.S2C_CARGO
    assert [(i["code"], i["slot"], i["count"], i["serial"] >> 32) for i in st.qwe["bag"]] == [(POTION, 4, 3, 2)]
    assert only(ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(5) + b"\0"),
                social.S2C_TAKE_ITEM) == b"\x05\x3c"                                    # "Item already received."

    head = rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)[2][0][0]
    assert (head[0], head[11], head[14]) == (OBOOL_TRUE, 1, 1)                          # read, both taken
    page, total, got = rows(only(ask(role, a, social.C2S_SENT, b"\0"), social.S2C_SENT), 14)
    head, to, title = got[0]
    assert (total, to, title) == (1, "qwe123", "Supplies")                              # the sender sees it was read
    assert head == (bytes([t.tm_hour, OBOOL_TRUE, t.tm_min]) + struct.pack("<H", t.tm_year)
                    + bytes([OBOOL_FALSE, 1, 1, t.tm_mon, t.tm_mday]) + struct.pack("<i", ID))

    assert ask(role, q, social.C2S_DELETE, struct.pack("<BBI", 0, 1, ID)) == [(social.S2C_DELETE, bytes(2))]
    assert st.qwe["letters"] == [] and len(st.aldric["letters_sent"]) == 1              # the sender's copy stays
    assert only(ask(role, q, social.C2S_READ, struct.pack("<BI", 0, ID)), social.S2C_READ) == b"\x01\0"
    assert only(ask(role, a, social.C2S_READ, struct.pack("<BI", 1, ID)), social.S2C_READ)[:2] == bytes(2)
    assert ask(role, a, social.C2S_DELETE, struct.pack("<BBI", 1, 1, ID)) == [(social.S2C_DELETE, bytes(2))]
    assert st.aldric["letters_sent"] == []


def test_a_letter_is_refused_as_the_original_refused_it(town):
    role, st, a, q = town
    potion = give(st.aldric, POTION, 5, slot=0)
    bound = give(st.aldric, RAPIER, slot=1)
    quest_item = next(int(r["ItemCode"]) for r in tables.sections("item_quest")["Base"]
                      if r["Tradable"] == "False" and r["BindType"] == "BIND_NONE")
    kept = give(st.aldric, quest_item, slot=world.bag_range(st.aldric, quest_item)[0])
    assert bound["bound"] and not kept["bound"]
    before = repr(st.db)

    def refused(body):
        reply = ask(role, a, social.C2S_SEND, body)
        assert len(reply) == 1 and reply[0][0] == social.S2C_SEND and repr(st.db) == before
        return reply[0][1]
    assert refused(letter("Nobody")) == b"\x06\x04"                             # 0x406 "This player is invalid."
    assert refused(letter("aldric")) == b"\x06\x04"                             # names match as the name check does
    assert refused(letter("Aldric")) == b"\x17\x04"                             # 0x417 "... a mail to yourself."
    assert refused(letter("qwe123", attached=[(bound, 1)])) == b"\x06\x3c"      # 0x3c06 bound to a character
    assert refused(letter("qwe123", attached=[(kept, 1)])) == b"\x07\x3c"       # 0x3c07 not tradable
    assert refused(letter("qwe123", gold=1000)) == b"\x01\x3c"                  # 0x3c01: 1000 + the fee of 50
    assert refused(letter("qwe123", attached=[(potion, 6)])) == b"\x2a\x64"     # more than the stack holds
    assert refused(letter("qwe123", attached=[(potion, 3), (potion, 3)])) == b"\x2a\x64"
    assert refused(letter("qwe123", attached=[({**potion, "serial": 77}, 1)])) == b"\x2a\x64"
    assert refused(letter("qwe123")[:-3]) == b"\x2a\x64"                        # cut short: no crash, no letter

    for _ in range(social.A_DAY):
        assert ask(role, a, social.C2S_SEND, letter("qwe123"))[0] == (social.S2C_SEND, bytes(2))
    assert st.aldric["gold"] == 1000 and len(st.qwe["letters"]) == 30           # text alone costs nothing
    assert only(ask(role, a, social.C2S_SEND, letter("qwe123")), social.S2C_SEND) == b"\x0a\x3c"    # 30 a day
    st.aldric["letters_day"][0] = "2000-01-01"
    assert ask(role, a, social.C2S_SEND, letter("qwe123"))[0] == (social.S2C_SEND, bytes(2))


def test_the_recipient_pays_the_fee_once_at_the_first_take(town):
    role, st, a, q = town
    stack = give(st.aldric, POTION, 10)
    ask(role, a, social.C2S_SEND, letter("qwe123", gold=100, pay=True, attached=[(stack, 3)]))
    assert st.aldric["gold"] == 900                                             # the gold only
    head = rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)[2][0][0]
    assert (head[12], head[13]) == (OBOOL_FALSE, OBOOL_TRUE)                    # the fee is the recipient's, unpaid
    assert rows(only(ask(role, a, social.C2S_SENT, b"\0"), social.S2C_SENT), 14)[2][0][0][5] == OBOOL_TRUE

    st.qwe["gold"] = 7                                                          # the fee is 5 + 3
    before = repr(st.db)
    assert only(ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(0) + b"\0"),
                social.S2C_TAKE_ITEM) == b"\x01\x3c"                            # "You don't have enough Gold."
    assert only(ask(role, q, social.C2S_TAKE_GOLD, struct.pack("<I", ID)), social.S2C_TAKE_GOLD) == b"\x01\x3c"
    assert repr(st.db) == before
    st.qwe["gold"] = 8
    assert ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(0) + b"\0")[-1][1] == bytes(2)
    assert st.qwe["gold"] == 0 and st.qwe["letters"][0]["fee_paid"]
    assert ask(role, q, social.C2S_TAKE_GOLD, struct.pack("<I", ID))[-1][1] == bytes(2)
    assert st.qwe["gold"] == 100                                                # nothing more for the second take
    head = rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)[2][0][0]
    assert (head[12], head[13]) == (OBOOL_TRUE, OBOOL_TRUE)

    assert ask(role, a, social.C2S_SEND, letter("qwe123", pay=True))[0][1] == bytes(2)
    assert not st.qwe["letters"][1]["pay"]                                      # text alone: nothing to pay


def test_gear_arrives_as_it_was_sent_or_not_at_all(town):
    role, st, a, q = town
    options = items.roll_options(SWORD, lambda n: 0)
    sword = give(st.aldric, SWORD, enchant=3, options=options, dur=5)
    assert not sword["bound"]
    assert ask(role, a, social.C2S_SEND, letter("qwe123", attached=[(sword, 1)]))[0][1] == bytes(2)
    assert st.aldric["bag"] == [] and st.aldric["gold"] == 1000 - 14
    record = only(ask(role, q, social.C2S_READ, struct.pack("<BI", 0, ID)), social.S2C_READ)
    record = record[record.index(0, 2) + 7:]
    assert record[:-1] == items.record(SWORD, 0, sword["serial"], 1, 5, enchant=3, sockets=items.sockets(sword),
                                       options=options)

    lo, hi = world.bag_range(st.qwe, SWORD)
    for k in range(lo, hi):
        give(st.qwe, POTION, 100, slot=k)
    before = repr(st.db)
    assert only(ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(0) + b"\0"),
                social.S2C_TAKE_ITEM) == b"\x03\x3c"                            # the bag is full
    assert repr(st.db) == before
    st.qwe["bag"].pop(3)
    assert ask(role, q, social.C2S_TAKE_ITEM, struct.pack("<I", ID) + obf.u16(9) + b"\0")[-1][1] == bytes(2)
    got = st.qwe["bag"][-1]
    assert (got["code"], got["slot"], got["enchant"], got["dur"], got["bound"]) == (SWORD, 3, 3, 5, False)
    assert got["options"] == options and got["serial"] >> 32 == 2 and "taken" not in got


def test_receive_all_takes_a_letter_and_a_system_mail_in_one_request(town):
    role, st, a, q = town
    stack = give(st.aldric, POTION, 10)
    ask(role, a, social.C2S_SEND, letter("qwe123", gold=40, pay=True, attached=[(stack, 2)]))
    mail.deliver(None, st, st.qwe, "Bag full", "These did not fit.", gold=5, grant=[(POTION, 1)])
    system = st.qwe["mail"][0]["id"]

    # the pre-check of "receive selected" (0x525e): the system part as mail.py's, then the letters' part
    reply = only(ask(role, q, mail.C2S_CHECK, bytes([1]) + struct.pack("<Q", system) + bytes([1])
                     + struct.pack("<I", ID)), mail.S2C_CHECK)
    part = struct.pack("<HB", 0, 1) + struct.pack("<Q", system) + obf.u40(5) + b"\0"
    assert reply.startswith(part + bytes([1]) + obf.u40(40) + struct.pack("<i", ID) + bytes([1]))
    record = reply[len(part) + 11:]
    assert items.decode_head(record)[:3] == (POTION, 0, 2) and record[-1] == OBOOL_FALSE
    plain = bytes([1]) + struct.pack("<Q", system) + b"\0"                      # no letter chosen: mail.py's own
    assert only(ask(role, q, mail.C2S_CHECK, plain), mail.S2C_CHECK) == part + b"\0"

    replies = ask(role, q, mail.C2S_RECEIVE, bytes([2]) + struct.pack("<IQ", ID, 0) + struct.pack("<IQ", 0, system))
    answers = [b for p, b in replies if p == mail.S2C_RECEIVE]
    assert sorted(answers) == sorted([struct.pack("<HBIQ", 0, 1, ID, 0), struct.pack("<HBIQ", 0, 1, 0, system)])
    assert st.qwe["gold"] == 50 + 40 - (2 + 2) + 5                              # the letter's fee: 2 for 40, 2 potions
    assert sum(i["count"] for i in st.qwe["bag"]) == 3
    assert mail.states(st.qwe["letters"][0]) == (1, 1) and mail.states(st.aldric["letters_sent"][0]) == (1, 1)
    assert only(ask(role, q, mail.C2S_RECEIVE, bytes([1]) + struct.pack("<IQ", 9, 0)), mail.S2C_RECEIVE) == b"\x2a\x64"


def test_letters_go_after_28_days_from_both_boxes(town):
    role, st, a, q = town
    ask(role, a, social.C2S_SEND, letter("qwe123", gold=10))
    ask(role, a, social.C2S_SEND, letter("qwe123"))
    for box in (st.qwe["letters"], st.aldric["letters_sent"]):
        box[0]["sent"] -= mail.KEEP_DAYS * DAY + 1
    assert rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)[1] == 1
    assert [m["id"] for m in st.qwe["letters"]] == [ID + 1]
    assert rows(only(ask(role, a, social.C2S_SENT, b"\0"), social.S2C_SENT), 14)[1] == 1
    assert social.expire(st.qwe) == [] and st.qwe["gold"] == 50                 # the gold went with the letter


def test_a_list_is_eight_a_page_newest_first(town):
    role, st, a, q = town
    for k in range(10):
        ask(role, a, social.C2S_SEND, letter("qwe123", title=f"n{k}"))
        st.qwe["letters"][-1]["sent"] += k
    page, total, got = rows(only(ask(role, q, social.C2S_LIST, b"\0"), social.S2C_LIST), 16)
    assert (page, total, [title for _, _, title in got]) == (0, 10, [f"n{k}" for k in range(9, 1, -1)])
    page, total, got = rows(only(ask(role, q, social.C2S_LIST, b"\x01"), social.S2C_LIST), 16)
    assert (page, total, [title for _, _, title in got]) == (1, 10, ["n1", "n0"])


def test_a_friend_or_a_block_by_name_gets_the_originals_refusal(town):
    # 0x5341 (0x140dec2d0): 0x4c06 -> text 5048 "You can not add a character in the block list that is in your
    # account."; 0x406 -> the mapper 0x140deda30's 7227 "This player either is not logged in or does not exist."
    role, st, a, q = town
    def add(name, kind):
        return ask(role, a, social.C2S_ADD, name.encode("latin-1") + b"\0" + bytes([kind]))
    assert add("qwe123", social.KIND_BLOCK) == [(social.S2C_ADD, b"\x06\x4c")]
    assert add("qwe123", 0) == [(social.S2C_ADD, b"\x06\x04")]              # a friend must be there to accept
    assert add("Nobody", social.KIND_BLOCK) == add("Nobody", 0) == [(social.S2C_ADD, b"\x06\x04")]
    assert add("Aldric", 0) == add("Aldric", 1) == [(social.S2C_ADD, b"\x17\x04")]     # the client refuses first
    assert "blocked" not in st.aldric and st.saves == 0


def test_the_family_answers_as_the_original_did_with_nobody_there(town):
    # the SOLO and CONSTANT ends, through the handlers: each fixed reply is the code its handler turns into the
    # client's own "no such player" line, or the empty list of a world of one
    # (planning/agents/reports/2026-11-05_contract-social.md); 2 bytes at least where the handler dereferences its i16
    role, st, a, q = town
    fixed = {0x534e: (0x534f, ""), 0x5351: (0x5352, "0000"), 0x5353: (0x5354, "0000"), 0x5344: (0x5345, "0000"),
             0x5346: (0x5347, "0000"), 0x534c: (0x534d, "0000"), 0x3c40: (0x3c41, "0964"), 0x3c43: (0x3c44, "0964"),
             0x3c45: (0x3c46, "0000"), 0x3c49: (0x3c4a, "0100"), 0x3c4b: (0x3c4c, "0100"), 0x3c4d: (0x3c4e, "0964"),
             0x3c4f: (0x3c50, "000000000964"), 0x104b: (0x104c, "0100"), 0x107c: (0x107d, "1204"),
             0x1052: (0x1053, "0100"), 0x1064: (0x1065, "0604"), 0x1120: (0x1121, "0100"), 0x1124: (0x1125, "")}
    for req, (reply, body) in fixed.items():
        assert ask(role, a, req) == [(reply, bytes.fromhex(body))], hex(req)
    for silent in (0x5349, 0x5342, 0x3c53, 0x1123, 0x1246, 0x1248):        # nothing waits for an answer
        assert silent not in role.handlers or ask(role, a, silent) == [], hex(silent)

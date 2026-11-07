"""The markets (planning/todo/CONTRACT-COMPLETE-PLAN.md, family 6): the auction house of a server with one player
through its registered handlers (kuf2/market.py), and the Cubic exchange's constants. Reads the installed game's
tables. Run: py -m pytest -q server/tests"""
import copy
import struct
import time

import pytest

from kuf2 import items, market, obf, world
from kuf2.packet import OBOOL_FALSE, Reader
from test_rewards import Session, State, char

SWORD = 101119323       # Balanced Adjutant Longsword: RARE, Lv 19, GLEN, MAIN_WEAPON, sells for 90, BIND_EQUIP_TIME
POTION = 350000010      # [Lv 1] HP Recovery Potion: NORMAL, Lv 1, CONSUME_ITEM, sells for 8, MaxStack 100
SUPPLIED = 101201110    # Supplied Adventurer Rapier: Tradable False
ME = 1                  # char()'s id: the seller id the client compares with its own (common+0xd4)


def ask(role, s, proto, body=b""):
    """One request through the role's handler table; the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def code_of(replies, proto):
    return struct.unpack_from("<H", next(b for p, b in replies if p == proto))[0]


@pytest.fixture
def auction():
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    market.make(role, st)
    c = {**char(level=20), "name": "Aldric", "gold": 1000, "bag": [], "bag_slots": 32, "next_serial": 0x30000}
    return role, Session(c), c


def entry(code, slot, count=1, serial=None, **extra):
    return {"code": code, "slot": slot, "count": count, "serial": serial or (ME << 32) | (0x40000 + slot),
            "bound": False, **extra}


def salted(value, step, salt=0x5b):
    """A one-byte field as the client codes it: its runtime table over salt x step + value."""
    return obf.T2[(salt * step + value) & 0xff]


def register_body(it, count=1, packs=1, start=500, buyout=0, hours=6, slot=None):
    return (obf.u64(it["serial"]) + obf.u16(it["slot"] if slot is None else slot) + obf.u40(buyout) + obf.u40(start)
            + obf.u16(count) + bytes([hours]) + obf.u16(packs))


def listing_body(x):
    """0x159b / 0x159d / 0x1599: coded u16 count, coded u32 item, u64 listing id."""
    return obf.u16(x["item"]["count"]) + obf.u32(x["item"]["code"]) + struct.pack("<Q", x["id"])


def reregister_body(x, start=600, buyout=0, hours=12):
    return listing_body(x) + obf.u40(buyout) + bytes([hours]) + obf.u40(start)


def search_body(page=0, lo=0, hi=0xff, cls=7, rarity=0, kind=0, parts=0, sort=1, up=True, codes=None):
    b = bytearray(0x15)
    struct.pack_into("<h", b, 0, lo)
    struct.pack_into("<h", b, 6, hi)
    struct.pack_into("<I", b, 9, cls)
    struct.pack_into("<H", b, 0xd, page)
    b[2], b[8], b[0x10], b[0x11] = salted(parts, 0x20), salted(sort, 0x10), salted(rarity, 8), salted(kind, 0x20)
    b[0xf], b[0x12], b[0x13], b[0x14] = salted(0, 2), salted(0, 2), salted(0, 2), salted(int(up), 2)
    if codes is None:
        return bytes(b)
    return bytes(b) + bytes([len(codes)]) + b"".join(obf.u32(v) for v in codes)


def mine_body(mode, page=0, sort=1, up=True):
    return bytes([salted(mode, 4), 0xcc, salted(sort, 0x10), salted(int(up), 2)]) + struct.pack("<H", page)


def read_tail(body, at):
    """The item record's tail, as the reader 0x140619210 walks it; where it ends."""
    sockets = body[at + 8]
    options = at + 9 + 4 * sockets
    return options + 1 + 10 * body[options]


def rows(body, own):
    """A 0x1591 (own False) or 0x15a5 (own True) success, read the client's way; (total, page, rows)."""
    assert body[:2] == bytes(2)
    if own:
        page, total, n = struct.unpack_from("<HIH", body, 3)
        at = 11
    else:
        total, page, n = struct.unpack_from("<IHH", body, 2)
        at = 10
    out = []
    for _ in range(n):
        f = body[at:at + (0x3c if own else 0x2e)]
        if own:
            r = dict(flag=obf.T1[f[0]] & 1, bid=obf.dec_u40(f[1:6]), buyout=obf.dec_u40(f[6:11]),
                     flag2=obf.T1[f[11]] & 1, id=struct.unpack_from("<Q", f, 12)[0], count=obf.dec_u16(f[20:22]),
                     seller=struct.unpack_from("<I", f, 22)[0], end=obf.dec_time64(f[26:34]),
                     bidder=struct.unpack_from("<I", f, 34)[0], my_bid=obf.dec_u40(f[38:43]),
                     my_bid_id=struct.unpack_from("<Q", f, 43)[0], code=obf.dec_u32(f[51:55]),
                     start=obf.dec_u40(f[55:60]))
        else:
            r = dict(flag=obf.T1[f[0]] & 1, end=obf.dec_time64(f[1:9]), bid=obf.dec_u40(f[9:14]),
                     count=obf.dec_u16(f[14:16]), start=obf.dec_u40(f[16:21]), code=obf.dec_u32(f[21:25]),
                     buyout=obf.dec_u40(f[25:30]), bidder=struct.unpack_from("<I", f, 30)[0],
                     seller=struct.unpack_from("<I", f, 34)[0], id=struct.unpack_from("<Q", f, 38)[0])
        at += len(f)
        names = []
        for _ in range(2):
            end = body.index(0, at)
            names.append(body[at:end].decode("latin-1"))
            at = end + 1
        tail_end = read_tail(body, at)
        out.append({**r, "seller_name": names[0], "bidder_name": names[1], "tail": body[at:tail_end]})
        at = tail_end
    assert at == len(body), (at, len(body))
    return total, page, out


def search(role, s, **kw):
    return rows(dict(ask(role, s, market.C2S_SEARCH, search_body(**kw)))[market.S2C_SEARCH], own=False)


def mine(role, s, mode=market.MODE_REGISTERED, **kw):
    return rows(dict(ask(role, s, market.C2S_MINE, mine_body(mode, **kw)))[market.S2C_MINE], own=True)


def put_up(role, s, it, **kw):
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(it, **kw)), market.S2C_REGISTER) == 0
    return s.data["char"]["auction"][-1]


def holdings(c):
    """Every item the character has, in the bag or up for auction: [(serial, code, count)]."""
    held = [(i["serial"], i["code"], i["count"]) for i in c["bag"]]
    return sorted(held + [(x["item"]["serial"], x["item"]["code"], x["item"]["count"]) for x in c.get("auction", [])])


def test_the_window_opens_on_an_empty_search(auction):
    # the window's first request (0x140876d90 -> 0x1408779f0 with mode 0): 0x1590, no filter. Code 0 needs the list
    # head and count: i16 0, u32 total, u16 page, u16 n
    role, s, c = auction
    assert ask(role, s, market.C2S_SEARCH, search_body()) == [(market.S2C_SEARCH, bytes(10))]
    for mode in (market.MODE_HISTORY, market.MODE_REGISTERED, market.MODE_BIDS):   # i16 0, u8, u16 page, u32, u16
        assert ask(role, s, market.C2S_MINE, mine_body(mode)) == [(market.S2C_MINE, bytes(2) + bytes([mode])
                                                                     + bytes(8))]
    assert "auction" not in c                                   # a look saves nothing
    assert code_of(ask(role, s, market.C2S_SEARCH, bytes(4)), market.S2C_SEARCH) == market.LIST_FAILED


def test_the_deposit_is_the_register_tabs_number():
    # 0x140952bc0: max(1, trunc(SellPrice x 0.1 / 0.2 / 0.4)) in single precision, by the period; Page_in multiplies
    # by count x packs
    assert [market.deposit(SWORD, h) for h in (6, 12, 24)] == [9, 18, 36]            # sells for 90
    assert [market.deposit(POTION, h) for h in (6, 12, 24)] == [1, 1, 3]             # 8: 0.8 -> at least 1
    assert [market.deposit(350000040, h) for h in (6, 12, 24)] == [6, 13, 26]        # 67
    assert market.deposit(POTION, 24, 10) == 30


def test_registering_takes_the_item_whole_and_the_deposit(auction):
    role, s, c = auction
    sword = entry(SWORD, 3, enchant=4, sockets=[-1, 560010000], options=[[1, 1, 0.0, 25, 1001]])
    c["bag"] = [sword, entry(POTION, 0, 10)]
    kept = copy.deepcopy(sword)
    out = ask(role, s, market.C2S_REGISTER, register_body(sword, start=500, buyout=550, hours=12))
    # 0x1593: i16 0, u8 n, n x 16 bytes (the listing id; the client reads and drops them)
    assert out[0] == (market.S2C_REGISTER, bytes(2) + b"\x01" + struct.pack("<QQ", 1, 0))
    assert [p for p, _ in out] == [market.S2C_REGISTER, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert out[1][1] == struct.pack("<H", 1) + items.record(0xffffffff, 3, 0, count=0)      # the slot is cleared
    assert obf.dec_u40(out[2][1][:5]) == c["gold"] == 1000 - 18                              # 12 hours: 20 % of 90
    assert [i["code"] for i in c["bag"]] == [POTION]
    x, = c["auction"]
    assert x["item"] == {k: v for k, v in kept.items() if k != "slot"}                       # the same entry
    assert (x["id"], x["start"], x["buyout"], x["hours"], x["deposit"]) == (1, 500, 550, 12, 18)
    assert abs(x["end"] - (time.time() + 12 * 3600)) < 5


def test_a_stack_goes_up_in_packs(auction):
    role, s, c = auction
    stack = entry(POTION, 0, 10)
    c["bag"] = [stack]
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(stack, count=3, packs=2, hours=24)),
                   market.S2C_REGISTER) == 0
    assert [(i["serial"], i["count"]) for i in c["bag"]] == [(stack["serial"], 4)]
    assert [x["item"]["count"] for x in c["auction"]] == [3, 3]
    serials = [x["item"]["serial"] for x in c["auction"]]
    assert len({stack["serial"], *serials}) == 3                # each pack is its own stack with its own serial
    assert c["gold"] == 1000 - 6 * 3                            # 24 hours: 40 % of 8, per item
    put_up(role, s, stack, count=4)                             # the stack's last items go as the entry itself
    assert c["bag"] == [] and c["auction"][-1]["item"]["serial"] == stack["serial"]
    assert world.serials.allocate(c) not in {x["item"]["serial"] for x in c["auction"]}


def test_my_listing_is_on_the_register_tab_and_in_the_search(auction):
    role, s, c = auction
    sword = entry(SWORD, 3, enchant=4, options=[[1, 1, 0.0, 25, 1001]])
    c["bag"] = [sword]
    tail = items.record(SWORD, 0, sword["serial"], 1, 100, enchant=4, sockets=items.sockets(sword),
                        options=sword["options"])[items.HEAD:]            # what the bag sends after the head
    x = put_up(role, s, sword, start=500, buyout=900)
    want = dict(id=1, code=SWORD, count=1, seller=ME, bidder=0, bid=0, start=500, buyout=900, end=x["end"],
                flag=0, seller_name="Aldric", bidder_name="", tail=tail)
    total, page, found = search(role, s)
    assert (total, page) == (1, 0) and found == [want]
    total, page, listed = mine(role, s)
    assert (total, page) == (1, 0) and listed == [{**want, "flag2": 0, "my_bid": 0, "my_bid_id": 0}]
    assert mine(role, s, market.MODE_BIDS) == (0, 0, []) and mine(role, s, market.MODE_HISTORY) == (0, 0, [])
    # the busy flag's follow-up after a list with rows (0x15a8) keeps its three "new" marks off
    assert ask(role, s, 0x15a8) == [(0x15a9, bytes([OBOOL_FALSE] * 3))]


def test_the_search_filters_as_the_client_does(auction):
    # 0x14087bd70: level range, rarity, hero class, item kind, parts, and the codes the typed name matched
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0), entry(POTION, 1, 5)]
    put_up(role, s, c["bag"][0], start=500)
    put_up(role, s, c["bag"][0], count=5, start=300)
    codes = lambda **kw: [r["code"] for r in search(role, s, **kw)[2]]                       # noqa: E731
    assert codes(sort=0) == [SWORD, POTION]                                                  # listing order
    assert codes(sort=0, up=False) == [POTION, SWORD]
    assert codes(codes=[POTION]) == [POTION] and codes(codes=[SWORD, 123]) == [SWORD]
    assert codes(lo=10) == [SWORD] and codes(hi=5) == [POTION] and codes(lo=2, hi=18) == []
    assert codes(rarity=3) == [SWORD] and codes(rarity=1) == [POTION] and codes(rarity=5) == []
    assert codes(cls=0, sort=0) == [SWORD, POTION] and codes(cls=1) == [POTION]              # GLEN's; anyone's
    assert codes(kind=1) == [SWORD] and codes(kind=6) == [POTION] and codes(kind=2) == []
    assert codes(parts=1) == [SWORD] and codes(parts=3) == []
    assert codes(sort=0, rarity=8 & 7, kind=0x16, parts=0x15, cls=6) == [SWORD, POTION]      # the enums' ends: any
    assert codes(sort=4) == [POTION, SWORD] and codes(sort=5, up=False) == [SWORD, POTION]   # by level, by start


def test_the_lists_come_in_the_windows_pages(auction):
    # six rows a page in the search and on the register tab (0x14087d0f0, 0x14087c6b0's `tab == 1`)
    role, s, c = auction
    c["bag"] = [entry(POTION, 0, 7)]
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(c["bag"][0], packs=7)), market.S2C_REGISTER) == 0
    for lister in (search, mine):
        total, page, first = lister(role, s, sort=0)
        assert (total, page, [r["id"] for r in first]) == (7, 0, [1, 2, 3, 4, 5, 6])
        total, page, second = lister(role, s, sort=0, page=1)
        assert (total, page, [r["id"] for r in second]) == (7, 1, [7])
        assert lister(role, s, page=2) == (7, 2, [])            # the client then asks the page before


def test_cancelling_returns_the_item_and_keeps_the_deposit(auction):
    role, s, c = auction
    sword = entry(SWORD, 3, enchant=4, sockets=[-1], options=[[1, 1, 0.0, 25, 1001]], dur=100)
    c["bag"] = [sword, entry(POTION, 0, 10)]
    kept = copy.deepcopy(sword)
    x = put_up(role, s, sword)
    out = ask(role, s, market.C2S_CANCEL, listing_body(x))
    assert [p for p, _ in out] == [market.S2C_CANCEL, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert out[0][1] == bytes(2) and c["auction"] == []
    back = next(i for i in c["bag"] if i["code"] == SWORD)
    assert back == {**kept, "slot": 1}                          # the entry it was, in the first free slot
    assert c["gold"] == 1000 - 9                                # text 5107: the deposit is not returned
    assert code_of(ask(role, s, market.C2S_CANCEL, listing_body(x)), market.S2C_CANCEL) == market.NOT_LISTED


def test_an_ended_listing_waits_on_the_register_tab_until_it_is_taken_back(auction):
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0)]
    x = put_up(role, s, c["bag"][0])
    assert code_of(ask(role, s, market.C2S_TAKE_BACK, listing_body(x)), market.S2C_TAKE_BACK) == market.BIDDING
    x["end"] = int(time.time()) - 60                            # its six hours are over, nobody bid
    assert search(role, s) == (0, 0, [])                        # no longer for sale
    assert [r["id"] for r in mine(role, s)[2]] == [x["id"]]     # "failed": re-register or take back
    assert code_of(ask(role, s, market.C2S_CANCEL, listing_body(x)), market.S2C_CANCEL) == market.MISMATCH
    assert code_of(ask(role, s, market.C2S_BID, struct.pack("<Q", x["id"]) + obf.u40(600)),
                   market.S2C_BID) == market.NOT_LISTED
    before = holdings(c)
    out = ask(role, s, market.C2S_TAKE_BACK, listing_body(x))
    assert [p for p, _ in out] == [market.S2C_TAKE_BACK, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert out[0][1] == bytes(2) and c["auction"] == [] and holdings(c) == before
    assert [(i["code"], i["slot"]) for i in c["bag"]] == [(SWORD, 0)]
    assert code_of(ask(role, s, market.C2S_TAKE_BACK, listing_body(x)), market.S2C_TAKE_BACK) == market.ITEM_TAKEN


def test_a_full_bag_keeps_the_listing(auction):
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0), entry(POTION, 1, 40)]
    sword = put_up(role, s, c["bag"][0])
    potions = put_up(role, s, c["bag"][0], count=30)
    c["bag"] += [entry(SUPPLIED, k) for k in range(32) if k != 1]           # no free slot; 10 potions at slot 1
    before = copy.deepcopy(c)
    assert code_of(ask(role, s, market.C2S_CANCEL, listing_body(sword)), market.S2C_CANCEL) == market.BAG_FULL
    assert c == before
    out = ask(role, s, market.C2S_CANCEL, listing_body(potions))            # goes onto its own stack
    assert out[0][1] == bytes(2) and next(i for i in c["bag"] if i["code"] == POTION)["count"] == 40
    assert [x["id"] for x in c["auction"]] == [sword["id"]]


def test_an_ended_listing_is_registered_again_without_a_deposit(auction):
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0)]
    x = put_up(role, s, c["bag"][0], start=500)
    gold = c["gold"]
    assert code_of(ask(role, s, market.C2S_REREGISTER, reregister_body(x)), market.S2C_REREGISTER) == market.BIDDING
    x["end"] = int(time.time()) - 1
    for body, code in ((reregister_body(x, start=0), market.BAD_START),
                       (reregister_body(x, start=600, buyout=650), market.BAD_BUYOUT),
                       (reregister_body(x, hours=8), market.BAD_PERIOD)):
        assert code_of(ask(role, s, market.C2S_REREGISTER, body), market.S2C_REREGISTER) == code
    assert ask(role, s, market.C2S_REREGISTER, reregister_body(x, start=600, buyout=660, hours=24)) == [
        (market.S2C_REREGISTER, bytes(2))]
    assert (x["start"], x["buyout"], x["hours"], c["gold"]) == (600, 660, 24, gold)
    assert abs(x["end"] - (time.time() + 24 * 3600)) < 5 and [r["id"] for r in search(role, s)[2]] == [x["id"]]
    gone = {**x, "id": 99}
    assert code_of(ask(role, s, market.C2S_REREGISTER, reregister_body(gone)),
                   market.S2C_REREGISTER) == market.NOT_LISTED


@pytest.mark.parametrize("change, kw, code", [
    ({"bound": True}, {}, market.MISMATCH),                     # the client's own 0x13fb comes first
    ({"dur": 40}, {}, market.MISMATCH),                         # damaged (0xcff3)
    ({"code": SUPPLIED}, {}, market.MISMATCH),                  # Tradable False (0x1be0)
    ({}, {"slot": 9}, market.MISMATCH),
    ({}, {"count": 0}, market.MISMATCH),
    ({}, {"count": 2}, market.MISMATCH),                        # more than the stack holds
    ({}, {"start": 0}, market.BAD_START),
    ({}, {"start": 500, "buyout": 549}, market.BAD_BUYOUT),     # under 110 % of the start
    ({}, {"hours": 7}, market.BAD_PERIOD),
    ({}, {"hours": 24, "gold": 35}, market.NO_GOLD),            # the deposit is 36
])
def test_a_registration_the_window_would_not_send_changes_nothing(auction, change, kw, code):
    role, s, c = auction
    c["bag"] = [{**entry(SWORD, 3), **change}]
    c["gold"] = kw.pop("gold", c["gold"])
    before = copy.deepcopy(c)
    out = ask(role, s, market.C2S_REGISTER, register_body(c["bag"][0], **kw))
    assert out == [(market.S2C_REGISTER, struct.pack("<H", code))] and c == before


def test_twelve_listings_at_most(auction):
    # 0x8410: the client prints its own 12 into text 0x13ed
    role, s, c = auction
    c["bag"] = [entry(POTION, 0, 20)]
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(c["bag"][0], packs=12)), market.S2C_REGISTER) == 0
    before = copy.deepcopy(c)
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(c["bag"][0])),
                   market.S2C_REGISTER) == market.TOO_MANY and c == before


def test_ones_own_goods_cannot_be_bid_on_or_bought(auction):
    # with one player every listing is the player's own, and no bid, sale or purchase ever exists
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0)]
    x = put_up(role, s, c["bag"][0], start=500, buyout=900)
    before = copy.deepcopy(c)
    bid = lambda lid: struct.pack("<Q", lid) + obf.u40(600)                                   # noqa: E731
    buy = lambda lid: obf.u32(SWORD) + struct.pack("<Q", lid) + obf.u40(900) + obf.u16(1)     # noqa: E731
    assert ask(role, s, market.C2S_BID, bid(x["id"])) == [(market.S2C_BID, struct.pack("<H", market.OWN_ITEM))]
    assert ask(role, s, market.C2S_BID, bid(77)) == [(market.S2C_BID, struct.pack("<H", market.NOT_LISTED))]
    assert ask(role, s, market.C2S_BUY_NOW, buy(x["id"])) == [(market.S2C_BUY_NOW,
                                                               struct.pack("<H", market.NO_BUY_NOW))]
    assert ask(role, s, market.C2S_BUY_NOW, buy(77)) == [(market.S2C_BUY_NOW, struct.pack("<H", market.NOT_LISTED))]
    assert ask(role, s, market.C2S_COLLECT_WON, listing_body(x)) == [
        (market.S2C_COLLECT_WON, struct.pack("<H", market.ITEM_TAKEN))]
    assert ask(role, s, market.C2S_COLLECT_MONEY, obf.u40(900) + obf.u32(SWORD) + struct.pack("<Q", x["id"])) == [
        (market.S2C_COLLECT_MONEY, struct.pack("<H", market.MONEY_TAKEN))]
    assert ask(role, s, market.C2S_BID_BACK, obf.u40(600) + struct.pack("<Q", 5)) == [
        (market.S2C_BID_BACK, struct.pack("<H", market.NOT_LISTED))]
    assert c == before


def test_nothing_is_lost_or_duplicated_on_the_way_through_the_auction(auction):
    role, s, c = auction
    c["bag"] = [entry(SWORD, 0, enchant=2), entry(POTION, 1, 30), entry(POTION, 2, 100)]
    total = lambda: sum(n for _, code, n in holdings(c) if code == POTION)                    # noqa: E731
    sword = put_up(role, s, c["bag"][0])
    assert code_of(ask(role, s, market.C2S_REGISTER, register_body(c["bag"][0], count=7, packs=4)),
                   market.S2C_REGISTER) == 0
    assert total() == 130 and len({serial for serial, _, _ in holdings(c)}) == len(holdings(c)) == 7
    for x in list(c["auction"][1:3]):
        assert code_of(ask(role, s, market.C2S_CANCEL, listing_body(x)), market.S2C_CANCEL) == 0
    for x in c["auction"]:
        x["end"] = int(time.time()) - 1
    assert code_of(ask(role, s, market.C2S_REREGISTER, reregister_body(sword)), market.S2C_REREGISTER) == 0
    for x in [x for x in c["auction"] if x is not sword]:
        assert code_of(ask(role, s, market.C2S_TAKE_BACK, listing_body(x)), market.S2C_TAKE_BACK) == 0
    assert code_of(ask(role, s, market.C2S_CANCEL, listing_body(sword)), market.S2C_CANCEL) == 0
    assert c["auction"] == [] and total() == 130
    assert len({i["serial"] for i in c["bag"]}) == len(c["bag"]) and len({i["slot"] for i in c["bag"]}) == len(c["bag"])
    assert next(i for i in c["bag"] if i["code"] == SWORD) == {**entry(SWORD, 0, enchant=2), "slot": 6}


@pytest.mark.parametrize("request_id, reply, body", [
    (0x15a8, 0x15a9, bytes([OBOOL_FALSE] * 3)),     # the three tabs' "new" marks: off
    (0x1130, 0x1131, bytes(13)),                    # the price book: 12-byte head, no row (no order exists)
    (0x1132, 0x1133, bytes(10)),                    # recent trades: none
    (0x1139, 0x113a, bytes(4)),                     # my open orders: i16 0, u16 0
    (0x113b, 0x113c, bytes(4)),                     # my finished trades: i16 0, u16 0
    (0x1144, 0x1145, bytes.fromhex("2664")),        # charge with Cash: 0x6426 "You are low on cash."
    (0x1134, 0x1135, bytes.fromhex("0100")),        # the four the client cannot send with an empty book
    (0x113d, 0x113e, bytes.fromhex("0100")),
    (0x1140, 0x1141, bytes.fromhex("0100") + bytes(9)),
    (0x1142, 0x1143, bytes.fromhex("0100")),
])
def test_the_exchange_and_the_tab_marks_keep_their_constants(auction, request_id, reply, body):
    role, s, c = auction
    before = copy.deepcopy(c)
    assert ask(role, s, request_id, bytes(16)) == [(reply, body)] and c == before
    assert role.handlers[request_id].__name__ == f"empty_reply_{reply:04x}"


def test_the_exchange_has_no_book_a_lone_player_could_trade_in():
    # SignUpBuy / SignUpSell need two different prices of the ladder in the book (0x1418c5840); the table holds the
    # ladder alone, no order
    from kuf2 import tables
    ladder = tables.sections("cubicexchange")
    assert list(ladder) == ["ExchangeCallPrice"] and list(ladder["ExchangeCallPrice"][0]) == ["CallPriceID",
                                                                                             "CallPrice"]
    assert world.EMPTY_REPLIES[0x1130] == (0x1131, bytes(13))

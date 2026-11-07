"""The markets of a server with one player (CONTRACT-COMPLETE-PLAN family 6): the auction house (CommonSubAuction,
scene 0x1f, NPC menu AUCTION 5) and the Cubic exchange's verdicts. No buyer or seller is invented: the only goods on
the auction are the player's own, no bid or sale ever happens, and no exchange order can be placed.

The auction window (Flash UI1_ac2bd8faee07fcdb; tabs 0 search "Page_search", 1 register "Page_in", 2 bid status
"Page_status", 3 trade history "Page_tran"; ChangePage 0x140879950 turns the tab into a list mode: tab 0 -> mode 0 =
0x1590, tab 1 -> mode 2, tab 2 -> mode 3, tab 3 -> mode 1 = 0x15a4). Opening it (UI event 5, 0x140876d90) asks mode 0:
**the first request is the search 0x1590** with no filter (it stores mode 4 at +0x38 but calls 0x1408779f0 with
edx = 0, which overwrites it). Nothing locks the window: the NPC menu (0x140ea0901) refuses only when the content-lock
array common+0x16f0 has entry 2 set, and only S2C 0x125d fills that array; the server never sends it.
Every sender sets the busy flag +0xa1; every reply handler first runs the code through 0x140877420 (0 = go on; 0x041b
closes the window; the codes below print their text and clear the flag).

A listing lives in the character: c["auction"] = [{id, item (the bag entry without its slot: code, count, serial,
bound, enchant, dur, sockets, expires, options), start, buyout, hours, end (Unix s), deposit}], c["next_auction_id"].
The item leaves the bag whole (its serial stays; a part of a stack gets a new serial, as world.move_stack) and comes
back the same entry. Rules, each from the client or the publisher's settings:
  periods     6 / 12 / 24 hours (Page_in's dropdown, handleChangePeriod).
  deposit     per item max(1, trunc(SellPrice x rate)), rate = AuctionRegisterFeePerc "0.1 0.2 0.4" by period
              (UISceneAuction::AttachItem 0x140952bc0: settings +0x3bc..+0x3c4, single-precision), times count x packs
              (Page_in CalcDeposit); charged at registration, never returned (text 5107 at a cancel, 5161); a
              re-registration shows and takes none (CalcDeposit's isReregister).
  prices      start > 0; buyout 0 or >= 110 % of the start (the builder 0x140878f90's own checks: 0x13fd / 0x13fe).
  goods       not bound (text 0x13fb), Tradable (0x1be0), at full durability (0xcff3): the attach 0x140875f30.
  limit       12 listings (0x140877420 puts the number 12 into text 0x13ed).
  the end     a listing past its end with no bidder is "failed" on the register tab (0x140956e94: end < now and no
              bidder id): the seller re-registers it (0x15a6) or takes it back (0x159b). The original's 5 % sale fee
              (AuctionFeePerc, 0x14095a0aa) never applies: nothing sells.

  C2S 0x1590 search (builder 0x140878650): 0x15 bytes: +0 i16 min level, +2 parts, +6 i16 max level, +8 sort, +9 u32
      hero class (6 / 7 any), +0xd u16 page, +0x10 rarity, +0x11 item kind, +0x14 ascending, +3..5 / +0xf / +0x12 /
      +0x13 the extension search (no Flash caller: always 0); the one-byte fields are T2-coded and salted (value =
      T1[b] & mask). Then u8 n (<= 10), n * coded u32: the item codes the client matched to the typed name in
      search_text %Auction. The filters are the client's own test 0x14087bd70 (E_ItemRarity 1..7, E_ItemKind 1..21,
      E_ItemParts 1..20; 0 or the enum's end = any).
  S2C 0x1591 (0x14087d0f0, reader 0x14087ea30 -> 0x14087f530): i16; 0 -> u32 total, u16 page, u16 n, n * (0x2e bytes:
      obool, time64 end, coded u40 current bid, coded u16 count, coded u40 start, coded u32 item, coded u40 buyout,
      u32 bidder id, u32 seller id, u64 listing id; cstr seller, cstr bidder; the item record's tail: 8 bytes, u8 m +
      m * 4, u8 k + k * 10). Six a page. Code 0 without the list crashes; 2 bytes of a refusal are safe.
  C2S 0x15a4 my lists (0x140efc9b0), 6 bytes: +0 mode (T1[b] & 3: 1 trade history, 2 registered, 3 my bids), +2 sort
      (& 0xf), +3 ascending (& 1), +4 u16 page.
  S2C 0x15a5 (0x14087c6b0, reader 0x14087eaa0 -> 0x14087f6f0): i16; 0 -> u8 (not read), u16 page, u32 total, u16 n,
      n * (0x3c bytes: obool, coded u40 current bid, coded u40 buyout, obool, u64 listing id, coded u16 count, u32
      seller id, time64 end, u32 bidder id, coded u40 my bid, u64 my bid id, coded u32 item, coded u40 start; cstr,
      cstr, tail). Eight a page, six on the register tab.
  C2S 0x1592 register (0x140878f90, "RegisterItem"; missing from PACKETS.md's 497), 0x19 bytes: coded u64 serial,
      coded u16 bag slot, coded u40 buyout, coded u40 start, coded u16 count, u8 hours, coded u16 packs (each pack is
      a listing of `count`).
  S2C 0x1593 (0x14087d980): i16; 0 -> u8 n, n * 16 bytes (reader 0x14087eb10; read and dropped), text 0x13ff, the
      tab's list asked again.
  C2S 0x15a6 re-register (the same builder, flag set by ListItem_ReRegister), 0x19 bytes: coded u16 count, coded u32
      item, u64 listing id, coded u40 buyout, u8 hours, coded u40 start.   S2C 0x15a7 (0x14087dac0): i16, text 0xcfbe.
  C2S 0x159d cancel a running listing (0x140875a30 after dialog 0x13f3) and 0x159b take back an ended one
      (0x14087a790), 0xe bytes each: coded u16 count, coded u32 item, u64 listing id.   S2C 0x159e (0x14087dbc0, text
      0x1400) / 0x159c (0x14087e0c0, text 0x1403): i16; the client changes no bag: the bag follows.
  C2S 0x1595 bid (0x140876370): u64 listing id, coded u40 amount -> S2C 0x1596 i16.   C2S 0x1597 buy now (0x140879f00,
      refused by the client itself on one's own goods, text 0x13f7): coded u32 item, u64 listing id, coded u40 price,
      coded u16 count -> S2C 0x1598 i16.   C2S 0x1599 collect a won item / 0x15a2 collect sale money (0x14087b280,
      the trade-history row's seller) -> S2C 0x159a / 0x15a3 i16.   C2S 0x15a0 take a bid back (0x14087ad60): coded
      u40, u64 bid id -> S2C 0x15a1 i16.   These five need another player's listing, bid or purchase.
  S2C 0x1594 / 0x159f (a listing changed, outbid): another player's doing, never sent.   C2S 0x15a8 -> 0x15a9 three
      obools (the tabs' "new" marks; world.EMPTY_REPLIES keeps them off: their rule is the server's own).

The Cubic exchange (CommonSubExchange, scene 0x6a; 0x1130..0x1144) keeps its replies in world.EMPTY_REPLIES. SignUpSell
(0x140645af0) and SignUpBuy (0x1406461d0) return at once while +0x64 is 0, and 0x140646950 -> 0x1418c5840 leaves it 0
unless the price book (0x1131) holds two different cubicexchange prices; a book is other players' orders, so a lone
player's book is empty and no order (0x1134), no withdrawal (0x113d, a row of 0x113a) and no receipt (0x1140, a row of
0x113c) can be sent. Change (0x1142) needs exchange Cubic (+0x94, S2C 0x375e), charge (0x1144) real-money Cash."""
import copy
import struct
import time

from . import hero, items, obf, serials, settings
from .net import journal, log
from .packet import OBOOL_FALSE, Writer

C2S_SEARCH, S2C_SEARCH = 0x1590, 0x1591
C2S_REGISTER, S2C_REGISTER = 0x1592, 0x1593
C2S_BID, S2C_BID = 0x1595, 0x1596
C2S_BUY_NOW, S2C_BUY_NOW = 0x1597, 0x1598
C2S_COLLECT_WON, S2C_COLLECT_WON = 0x1599, 0x159a
C2S_TAKE_BACK, S2C_TAKE_BACK = 0x159b, 0x159c
C2S_CANCEL, S2C_CANCEL = 0x159d, 0x159e
C2S_BID_BACK, S2C_BID_BACK = 0x15a0, 0x15a1
C2S_COLLECT_MONEY, S2C_COLLECT_MONEY = 0x15a2, 0x15a3
C2S_MINE, S2C_MINE = 0x15a4, 0x15a5
C2S_REREGISTER, S2C_REREGISTER = 0x15a6, 0x15a7

# 0x140877420's codes (text ids): what the original's server answered
NO_GOLD = 0x6401                # 0x1c01 "You don't have enough money to put this item up on the auction." (mode 2)
BAG_FULL = 0x6403               # 0xce84 "You can not get the item because your bag is full."
BAD_START, BAD_BUYOUT, BAD_PERIOD = 0x640d, 0x640e, 0x640f   # 0x13ee / 0x13ef / 0x13f0 "Wrong starting price." ...
NOT_LISTED = 0x8401             # 0x13df "The item is either not listed on the auction or already sold. ..."
MONEY_TAKEN = 0x8404            # 0x13e2 "Item money already received."
ITEM_TAKEN = 0x8405             # 0x13e3 "Item already received."
BIDDING = 0x8406                # 0x13e4 "Can not do this while bidding is in progress."
LIST_FAILED = 0x8407            # 0x13e5 "Failed to load the auction list."
MISMATCH = 0x8408               # 0x13e6 "This does not match the info. from the server. Please refresh and try again."
OWN_ITEM = 0x840d               # 0x13ea "You can not bid for your own item."
NO_BUY_NOW = 0x840f             # 0x13ec "You can not make an immediate purchase for this item."
TOO_MANY = 0x8410               # 0x13ed "You have exceeded the maximum number of items ..." (the client prints 12)

PERIODS = (6, 12, 24)           # hours; the deposit rate's index
MAX_LISTINGS = 12
MODE_HISTORY, MODE_REGISTERED, MODE_BIDS = 1, 2, 3
SEARCH_PAGE, PAGE, REGISTERED_PAGE = 6, 8, 6
RARITIES = (None, "NORMAL", "MAGIC", "RARE", "HERO", "UNIQUE", "CASH", "EVENT")   # E_ItemRarity (names 0x14353c740;
                                # 8, the enum's end, is the client's "any", as 0)
KINDS = (None, "WEAPON", "ARMOR", "ACCESSORY", "LEADER_ITEM", "TROOP_ITEM", "CONSUME_ITEM", "MATERIAL_ITEM",
         "QUEST_ITEM", "ETC_ITEM", "CONTAINER", "ENCHANT_ITEM", "COMPOSE_ITEM", "FUNCTIONAL_ITEM", "GACHA_ITEM",
         "PACKAGE_ITEM", "LOOK_ITEM", "TROOP_BBOKY_ITEM", "CURRENCY_ITEM", "TOKEN_ITEM", "CHOICE_CONTAINER",
         "BOOK_ITEM")           # E_ItemKind (names 0x14353c5b0); 0x16, the enum's end, is the client's "any"
ANY_CLASS, ANY_KIND, ANY_PARTS = (6, 7), (0, len(KINDS)), (0, 21)


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def deposit(code, hours, n=1):
    """The deposit for n of item `code` listed for `hours`: what the register tab shows (0x140952bc0, CalcDeposit)."""
    rate = float(str(settings.get("AuctionRegisterFeePerc")).split()[PERIODS.index(hours)])
    return max(1, int(_f32(_f32(items.sell_price(code)) * _f32(rate)))) * n


def find(c, lid):
    return next((x for x in c.get("auction", []) if x["id"] == lid), None)


def ended(listing, now=None):
    """Past its end, as the client reads it (end - now < 0: 0x14087a790, 0x140956e94)."""
    return int(time.time() if now is None else now) > listing["end"]


def listable(it):
    """The attach's tests (0x140875f30): not bound, Tradable, undamaged."""
    r = items.row(it["code"]) or {}
    return (not it.get("bound", False) and r.get("Tradable") == "True"
            and items.durability(it) == items.full_durability(it["code"]))


def price_code(start, buyout, hours):
    """0, or the refusal of a start price, a buyout or a period the builder would not have sent."""
    if start < 1:
        return BAD_START
    if buyout and start * 110 > buyout * 100:
        return BAD_BUYOUT
    return 0 if hours in PERIODS else BAD_PERIOD


def _tail(it):
    return items.record(it["code"], 0, it["serial"], it["count"], items.durability(it), bound=it.get("bound", False),
                        enchant=it.get("enchant", 0), sockets=items.sockets(it), expiry=items.seconds_left(it),
                        options=it.get("options", ()))[items.HEAD:]


def _names(c):
    return c.get("name", "").encode("latin-1", "replace") + b"\0" + b"\0"       # the seller; no bidder


def search_record(c, x):
    """A 0x1591 row: one's own running listing, no bid on it."""
    it = x["item"]
    return (bytes([OBOOL_FALSE]) + obf.time64(x["end"]) + obf.u40(0) + obf.u16(it["count"]) + obf.u40(x["start"])
            + obf.u32(it["code"]) + obf.u40(x["buyout"]) + struct.pack("<IIQ", 0, c["id"], x["id"])
            + _names(c) + _tail(it))


def own_record(c, x):
    """A 0x15a5 row of the register tab."""
    it = x["item"]
    return (bytes([OBOOL_FALSE]) + obf.u40(0) + obf.u40(x["buyout"]) + bytes([OBOOL_FALSE])
            + struct.pack("<Q", x["id"]) + obf.u16(it["count"]) + struct.pack("<I", c["id"]) + obf.time64(x["end"])
            + struct.pack("<I", 0) + obf.u40(0) + struct.pack("<Q", 0) + obf.u32(it["code"]) + obf.u40(x["start"])
            + _names(c) + _tail(it))


def search_filter(b):
    """The 0x1590 body's fields (the module docstring)."""
    t = obf.T1
    n = b[0x15] if len(b) > 0x15 else 0
    codes = {obf.dec_u32(b[0x16 + 4 * k:0x1a + 4 * k]) for k in range(min(n, (len(b) - 0x16) // 4))}
    lo, hi = struct.unpack_from("<h", b, 0)[0], struct.unpack_from("<h", b, 6)[0]
    return {"min": lo, "max": hi, "parts": t[b[2]] & 0x1f, "sort": t[b[8]] & 0xf,
            "class": struct.unpack_from("<I", b, 9)[0], "page": struct.unpack_from("<H", b, 0xd)[0],
            "rarity": t[b[0x10]] & 7, "kind": t[b[0x11]] & 0x1f, "up": bool(t[b[0x14]] & 1), "codes": codes}


def matches(code, f):
    """The client's own filter test (0x14087bd70) on an item's row."""
    r = items.row(code) or {}
    level = int(r["ReqLevel"]) if r.get("ReqLevel", "").isdigit() else 0
    if f["codes"] and code not in f["codes"]:
        return False
    if (f["min"] != -1 and f["min"] > level) or (f["max"] != -1 and f["max"] < level):
        return False
    if f["rarity"] and RARITIES[f["rarity"]] != r.get("Rarity"):
        return False
    if (f["class"] not in ANY_CLASS and r.get("ReqHero") in hero.HERO_CODE
            and hero.HERO_CODE.index(r["ReqHero"]) != f["class"]):
        return False
    if f["kind"] not in ANY_KIND and (KINDS[f["kind"]] if f["kind"] < len(KINDS) else None) != r.get("ItemKind"):
        return False
    return f["parts"] in ANY_PARTS or items.PARTS.get(r.get("Parts")) == f["parts"]


def ordered(rows, sort, up):
    """The list by a column (the Flash headers' sort ids: 1 period, 2 current bid, 3 buyout, 4 level, 5 start; the
    rest in listing order). The direction flag is 1 on a column's first click: read as ascending (inferred)."""
    def level(x):
        v = (items.row(x["item"]["code"]) or {}).get("ReqLevel", "")
        return int(v) if v.isdigit() else 0
    key = {1: lambda x: x["end"], 2: lambda x: x["start"], 3: lambda x: x["buyout"], 4: level,
           5: lambda x: x["start"]}.get(sort, lambda x: x["id"])
    return sorted(rows, key=lambda x: (key(x), x["id"]), reverse=not up)


def make(role, state):
    from . import world

    def refuse(s, reply, code, why):
        log.warning("auction 0x%04x refused %#06x: %s", reply - 1, code, why)
        s.send(Writer(reply).u16(code))

    def give_back(c, x):
        """Put a listing's item back in the bag as the entry it was: a free slot of its range, else onto its own
        stacks. Returns the slots changed, or None when it does not fit (nothing changed)."""
        it, bag = x["item"], c.setdefault("bag", [])
        lo, hi = world.bag_range(c, it["code"])
        used = {i["slot"] for i in bag}
        free = next((k for k in range(lo, hi) if k not in used), None)
        if free is not None:
            bag.append({**it, "slot": free})
            return [free]
        cap, left, slots = items.max_stack(it["code"]), it["count"], []
        stacks = [i for i in bag if items.can_stack(i, it) and i["count"] < cap]
        if sum(cap - i["count"] for i in stacks) < left:
            return None
        for i in stacks:
            n = min(left, cap - i["count"])
            if n:
                i["count"] += n
                left -= n
                slots.append(i["slot"])
        return slots

    def returned(s, pkt, reply, running):
        """0x159d (a running listing) / 0x159b (an ended one): the item comes back; the deposit does not."""
        b = pkt.rest()
        if len(b) < 14:
            return refuse(s, reply, MISMATCH, "short body")
        c = s.data["char"]
        x = find(c, struct.unpack_from("<Q", b, 6)[0])
        if x is None:
            return refuse(s, reply, NOT_LISTED if running else ITEM_TAKEN, "no such listing")
        if ended(x) == running:
            return refuse(s, reply, MISMATCH if running else BIDDING, "the listing has ended" if running else
                          "the listing is still running")
        slots = give_back(c, x)
        if slots is None:
            return refuse(s, reply, BAG_FULL, "no room in the bag")
        c["auction"].remove(x)
        it = x["item"]
        journal("item", ev="back from the auction", code=it["code"], name=items.name(it["code"]), n=it["count"])
        state.save()
        s.send(Writer(reply).u16(0))
        world.send_cargo(s, changed_slots=slots)
        log.info("auction: listing %d (%d x%d) %s", x["id"], it["code"], it["count"],
                 "cancelled" if running else "taken back")

    @role.on(C2S_SEARCH)
    def search(s, pkt):
        b = pkt.rest()
        if len(b) < 0x15:
            return refuse(s, S2C_SEARCH, LIST_FAILED, "short body")
        f, c, now = search_filter(b), s.data["char"], time.time()
        rows = ordered([x for x in c.get("auction", []) if not ended(x, now) and matches(x["item"]["code"], f)],
                       f["sort"], f["up"])
        shown = rows[f["page"] * SEARCH_PAGE:(f["page"] + 1) * SEARCH_PAGE]
        w = Writer(S2C_SEARCH).u16(0).u32(len(rows)).u16(f["page"]).u16(len(shown))
        for x in shown:
            w.raw(search_record(c, x))
        s.send(w)

    @role.on(C2S_MINE)
    def mine(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            return refuse(s, S2C_MINE, LIST_FAILED, "short body")
        mode, sort, up = obf.T1[b[0]] & 3, obf.T1[b[2]] & 0xf, bool(obf.T1[b[3]] & 1)
        page, c = struct.unpack_from("<H", b, 4)[0], s.data["char"]
        # the bids and the trade history are other players' doing: empty
        rows = ordered(c.get("auction", []), sort, up) if mode == MODE_REGISTERED else []
        per = REGISTERED_PAGE if mode == MODE_REGISTERED else PAGE
        shown = rows[page * per:(page + 1) * per]
        w = Writer(S2C_MINE).u16(0).u8(mode).u16(page).u32(len(rows)).u16(len(shown))
        for x in shown:
            w.raw(own_record(c, x))
        s.send(w)

    @role.on(C2S_REGISTER)
    def register(s, pkt):
        b = pkt.rest()
        if len(b) < 0x19:
            return refuse(s, S2C_REGISTER, MISMATCH, "short body")
        serial, slot = obf.dec_u64(b[0:8]), obf.dec_u16(b[8:10])
        buyout, start = obf.dec_u40(b[10:15]), obf.dec_u40(b[15:20])
        count, hours, packs = obf.dec_u16(b[20:22]), b[22], obf.dec_u16(b[23:25])
        c = s.data["char"]
        it = world.bag_item(c, serial)
        if (it is None or it["slot"] != slot or count < 1 or packs < 1 or count * packs > it["count"]
                or not listable(it)):
            return refuse(s, S2C_REGISTER, MISMATCH, f"serial {serial:#x} at slot {slot}, {count} x {packs}")
        code = price_code(start, buyout, hours)
        if code:
            return refuse(s, S2C_REGISTER, code, f"start {start}, buyout {buyout}, {hours} h")
        if len(c.get("auction", [])) + packs > MAX_LISTINGS:
            return refuse(s, S2C_REGISTER, TOO_MANY, f"{len(c.get('auction', []))} listed, {packs} more")
        fee = deposit(it["code"], hours, count * packs)
        if c.get("gold", 0) < fee:
            return refuse(s, S2C_REGISTER, NO_GOLD, f"deposit {fee}, gold {c.get('gold', 0)}")
        made, end = [], int(time.time()) + hours * 3600
        whole = count * packs == it["count"]            # then the stack's last items go as the entry itself
        fresh = [serials.allocate(c) for _ in range(packs - whole)]     # before anything moves
        base = {k: v for k, v in it.items() if k != "slot"}
        for k in range(packs):
            if k < len(fresh):
                held = {**copy.deepcopy(base), "count": count, "serial": fresh[k]}
                it["count"] -= count
            else:
                c["bag"].remove(it)
                held = {**base, "count": count}
            if held["serial"] >> 32 in (0, c["id"]):    # serials.allocate looks only at the bag's boxes
                c["next_serial"] = max(c.get("next_serial", 0), held["serial"] & 0xffffffff)
            c["next_auction_id"] = c.get("next_auction_id", 0) + 1
            made.append({"id": c["next_auction_id"], "item": held, "start": start, "buyout": buyout, "hours": hours,
                         "end": end, "deposit": fee // packs})
        c.setdefault("auction", []).extend(made)
        world.change_gold(c, -fee, "auction deposit")
        journal("item", ev="put up for auction", code=it["code"], name=items.name(it["code"]), n=count * packs,
                price=fee)
        state.save()
        w = Writer(S2C_REGISTER).u16(0).u8(len(made))
        for x in made:
            w.u64(x["id"]).zeros(8)
        s.send(w)
        world.send_cargo(s, changed_slots=[slot])
        log.info("auction: %d x%d listed in %d pack(s) for %d h, start %d, buyout %d, deposit %d", it["code"], count,
                 packs, hours, start, buyout, fee)

    @role.on(C2S_REREGISTER)
    def reregister(s, pkt):
        b = pkt.rest()
        if len(b) < 0x19:
            return refuse(s, S2C_REREGISTER, MISMATCH, "short body")
        x = find(s.data["char"], struct.unpack_from("<Q", b, 6)[0])
        buyout, hours, start = obf.dec_u40(b[14:19]), b[19], obf.dec_u40(b[20:25])
        if x is None:
            return refuse(s, S2C_REREGISTER, NOT_LISTED, "no such listing")
        if not ended(x):
            return refuse(s, S2C_REREGISTER, BIDDING, "the listing is still running")
        code = price_code(start, buyout, hours)
        if code:
            return refuse(s, S2C_REREGISTER, code, f"start {start}, buyout {buyout}, {hours} h")
        x.update(start=start, buyout=buyout, hours=hours, end=int(time.time()) + hours * 3600)
        state.save()
        s.send(Writer(S2C_REREGISTER).u16(0))
        log.info("auction: listing %d registered again for %d h, start %d, buyout %d", x["id"], hours, start, buyout)

    @role.on(C2S_CANCEL)
    def cancel(s, pkt):
        returned(s, pkt, S2C_CANCEL, running=True)

    @role.on(C2S_TAKE_BACK)
    def take_back(s, pkt):
        returned(s, pkt, S2C_TAKE_BACK, running=False)

    @role.on(C2S_BID)
    def bid(s, pkt):
        b = pkt.rest()
        x = find(s.data["char"], struct.unpack_from("<Q", b, 0)[0]) if len(b) >= 8 else None
        s.send(Writer(S2C_BID).u16(OWN_ITEM if x is not None and not ended(x) else NOT_LISTED))

    @role.on(C2S_BUY_NOW)
    def buy_now(s, pkt):
        b = pkt.rest()
        x = find(s.data["char"], struct.unpack_from("<Q", b, 4)[0]) if len(b) >= 12 else None
        s.send(Writer(S2C_BUY_NOW).u16(NO_BUY_NOW if x is not None and not ended(x) else NOT_LISTED))

    @role.on(C2S_COLLECT_WON)
    def collect_won(s, pkt):
        s.send(Writer(S2C_COLLECT_WON).u16(ITEM_TAKEN))         # nothing is ever won

    @role.on(C2S_COLLECT_MONEY)
    def collect_money(s, pkt):
        s.send(Writer(S2C_COLLECT_MONEY).u16(MONEY_TAKEN))      # nothing is ever sold

    @role.on(C2S_BID_BACK)
    def bid_back(s, pkt):
        s.send(Writer(S2C_BID_BACK).u16(NOT_LISTED))            # no bid is ever placed

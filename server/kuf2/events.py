"""The live service (planning/todo/CONTRACT-COMPLETE-PLAN.md family 7): the event windows, the boost events, the
edition packages of the mail window's Package tab, and the Diamond (cash) paths of the cash shop. 17 requests; the
report with each one's proof: planning/agents/reports/2026-11-05_contract-events.md. Everything the owner chooses is
OFF here (ACTIVE_BOOST, EDITION_PACKAGES), and with both off every reply is byte for byte the constant the server sent
before (the login's 0x1265, 0x1267, 0x126a and 0x5a4e among them).

EVENT WINDOWS: web pages of the publisher; the client ships no event page, so their lists are empty (CONSTANT).
  C2S 0x1265 (builder 0x1405c0c80; the HUD's init 0x140781410 at every town or field entry, and the HUD quick menu's
      "EventBanner" 0x140781186 -> 0x1407840d0): no body.
  S2C 0x1266 (0x1405c0cd0, reader 0x1405c1970): u8 n, n * (0x11 bytes: u8, i64 start, i64 end against the client's
      clock 0x140674e60; cstr the page's image; u8 m, m * (7 bytes: [0], [1] and the key [6]; cstr) its buttons,
      0x1405c1460 -> 0x1405c1ad0). A running record's image goes to the web image loader (common +0x1620,
      0x140692380, category 0x5e: a 900 x 600 PNG it downloads and keeps as Data/UI/EventBG%d.png, "{lang}" in the
      name replaced, its hash under the client's ImageHash setting; set up at 0x140692fd2..0x14069315b); at most
      five; the HUD marker (window 0x1a, 0x140e0f0a0) is lit and sub 0x4a opens on them. n = 0: the marker goes off
      and the button opens nothing.
  C2S 0x1267 (CommonSubCashShop OnEnter 0x1405937e0, and 0x140596b00 after the start-game reply) -> S2C 0x1268
      (0x1405993b0, reader 0x1405a66a0): u8 n, n * (coded u32, u8, cstr): the shop's three banners, the same loader's
      category 0x4a ("CashShopAd%d", 1202 x 246).
  C2S 0x126a (CommonSubDiary OnEnter 0x1405bc1a0) -> S2C 0x126b (0x1405bd810, reader 0x1405bfc50): u8 n, n * (0x15
      bytes: u32, u8, i64 end, i64 start; cstr, cstr; u8 k, k * u32 weekdays): the attendance calendar's side
      banners, category 0x56 ("DiaryBanner%d", 280 x 128).
  C2S 0x4076 (builder 0x140f0d3a0; its one caller 0x14077ac70, itself called only from a HUD part's init in the
      battle state, 0x140774186) is sent only in a spot whose Spot_Sub_Type is PVP_WAR_FIELD (row +0x14 == 3: spot
      20507 alone, Spot_Open False, TestMap True) while the world map's War Info sub 0x6d holds a chosen war spot of
      `wartable` (0x1418b97b0): the realm war's field, not an event timer (DEAD). S2C 0x4077 (0x140e10130, reader
      0x14077dc20): u8 n, n * (u32 id, cstr).
  C2S 0x114f (CommonSubGameStatusPopup OnEnter 0x1405cfa60, sub 0x65) is sent when the status popup opens: the HUD
      quick menu's "StatusPopup" 0x140781166 -> 0x140784050, whose entry the HUD shows only when the publisher's
      %Content GameStatusPopup is on (flag [0xd] of 0x140781410 = settings +0x3d9; GAMEFORGE 0, settings.md), and the
      HUD init's own open under the same setting (DEAD). S2C 0x1150 (0x1405d1520): one cstr, the popup's notice
      (0x140977890); an empty body crashes (0x141583a60 does not check its read).

BOOST EVENTS: the official boosts (planning/reference/OFFICIAL-NOTES.md "Rewards x multipliers") are BOOSTS below; the
one that is on is ACTIVE_BOOST (None: no event, the rules census's MISSIONS F6). The client shows a boost on the HUD
(HUDEventBuff, widget 34: one icon a kind, tooltip textui 7804 "Hero EXP increased by %1%%", 7805 "Troop EXP ...",
7806 "Gold ...", 7807 "Item Drop Rate ...", 0x14068a810) from this push, which event_list sends after 0x1266:
  S2C 0x1118 (0x140678600, EventBuffSystem at common +0x1610): obool clear the map first; u8 n, n * 20 bytes (reader
      0x140679500): u64 (stored at +0x38 + 8 * kind, read by nothing), u32 the percent, i32 the kind 0..3 (BUFF_*,
      others dropped), coded u32 spot (0 = everywhere). The HUD adds each positive percent of the spot-0 entry
      (0x140677d30). An empty body, or fewer than n * 20 bytes, crashes.
The effect is the server's: boosted(kind, amount) at the call sites the report names (game.py is not this module's).

EDITION PACKAGES (CommonSubMail, scene 0x1e, tab 3 "Package"): what the buyer of an edition was sent, by PackageID of
item_packages_premium (11 Hero, 21 Emperor, 31 War God; 10 / 20 / 30 their pre-order gifts; 22 / 32 / 33 the
upgrades). A package has an Account part (received once an account, on the character the player picks: box 5902
"This mail is account-based...") and a Character part (received once a character, Character_Count = 6 times an
account: box 5900 "Currently, you can receive %1% packages. Receive them on %2%?"); each part is one box item
(item_container), opened from the bag (world.open_container). Sender textui 1501 "KUF2 TEAM", title and body the
row's AccountMail_* / CharacterMail_* text ids (0x14184dfb0). The account's are EDITION_PACKAGES (() = none); the
save keeps account["packages"] = [{id, sent (Unix s), left: [account receipts, character receipts]}] and the
character's tab c["packages"] = {"<id>:<kind>": {read, taken, deleted}}.
  C2S 0x5a4e (0x140efa6b0; town entry 0x140674690 with page 0, the tab and its pages): u8 page (8 a page).
  S2C 0x5a4f (0x140e069d0): u16 total, u8 page (one 3-byte read; shorter crashes); total != 0 -> u8 n, n * entry
      (0x140e08200 -> 0x140e08b20 -> 0x140e07bc0): 13 bytes (u32 PackageID, u16 year, u8 hour, u8 month, u8 receipts
      left, u8 minute, u8 day, obool read, u8 kind 0 Account / 1 Character), coded u40 (unused: no gold), u8 m, m *
      (coded u32 item, coded u16 count) (0x140dd97e0; the detail shows five). An unread entry lights the HUD's mail
      icon (+0x6a2).
  C2S 0x5a50 take all (0x140e00650, after the box 5900 / 5902; a Character part with 0 receipts left asks no box):
      u32 PackageID, u8 kind. S2C 0x5a51 (0x140e07640): i16 (shorter crashes); 0 -> text 7100 "Received all
      attachments from the mail." and the entry's items cleared; else CommonSubMail::ShowErrorMSG 0x140dfe830.
  C2S 0x5a52 delete (0x140e00a00, the open package, after the box 5060 / 53152 "Attachment remains. Do you want to
      delete the selected mail?"): u32, u8. S2C 0x5a53 (0x140e07780): i16 (shorter crashes); 0 -> text 53151
      "Deleted the selected mail.", the tab asked again.
  C2S 0x5a54 opened (0x140e00d80 from OpenPackageDetailInfo 0x140dfa320, which marks the entry read): u32, u8. No
      reply (no 0x5a55 case in any dispatcher).
Codes (ShowErrorMSG): 0x3c03 "Cannot receive the item because the inventory is full.", 0x3c05 "You've already
received the item.", 0x5c1d the box 5901 "Received all the %1% packages. You can no longer receive this package
product.", 0x642a "Cannot perform the action now. Please try again later.".

DIAMONDS (the cash shop's real-money paths; the Cubic tab is cubicshop.py). The account holds no Diamonds and nothing
offline gives one, so the list is empty and each request gets the original's refusal (REPLIES below):
  C2S 0x108a (0x140596a10 / 0x1405a1380, six a shop open: u32 page) -> S2C 0x108b (0x140598d20): u8 mode, u16 total
      (3 bytes, shorter crashes); total != 0 -> u8 n, n * 22: the Diamond Storage, what Diamond purchases wait in.
  C2S 0x108c "MoveToInven" (0x1405a1470: u64 entry) -> S2C 0x108d (0x140598fc0): u16; 0 -> u64 entry. Needs an entry.
  C2S 0x10cf "ReqMoveToInvenAll" (0x1405a1570, only while the storage list is not empty: 0x1405945b7; also after a
      bought cart) -> S2C 0x10d0 (0x1405991f0): i16.
  C2S 0x3757 buy the cart with Diamonds (0x1405a0750, a first good that is neither a mileage good nor priced in
      Cubic; the client refuses first while the balance is short, 0x14059c070 "Not enough Diamonds.") -> S2C 0x3758
      (0x140597760): i16 (shorter crashes); 0 -> u8 n, n * 5.
  C2S 0x112a the same builder for a cart whose first good is a mileage good (0x14184c820: the cash holder's map
      +0x70, which the item_mileage loader fills, 0x141848fbd): the Mileage shop, tab 7 of the menu, hidden while the
      publisher's MileageEnable is off (GAMEFORGE 0; MainMenu.as setMileageSystem), and no table gives a Mileage
      bundle (item_consume 3585000xx), so the one good (7000001, 10 mileage) cannot be bought (DEAD). S2C 0x112b
      (0x140597d10): i16; 0 -> u8, u32.
  C2S 0x1155 the "Diamond top-up" tab (the menu's fifth button, id 6: SelectTab(6) 0x14059b3b0, the first click
      only, flag +0x24c: u64 account) -> S2C 0x1156 (0x140d72790): u32 a textsystem id shown as a banner (4 bytes,
      shorter crashes; an id without a row prints "nullptr").
  C2S 0x3751 (0x140596b50, CommonSubExchange OnEnter while cash shop +0x248 is 0) -> S2C 0x3752 (0x140597590): u32 ->
      +0x248, i16 n, n * 0x11 (SellID, u8, three u32): the operator's sale state of the goods of type 7 (none).
  C2S 0x375b (0x140f09440, the cash shop and the summon board opening): no body, no reply (no 0x375c case).
The cash mapper 0x14059c6b0: 0xc401 and unknown codes -> 7268 "Cannot perform the action now. Please try again
later.", 0x6442 -> 10040 "Cannot purchase it.", 0x6437 -> 53234 "Failed to purchase Diamond item.", 0x6426 -> 53243
"Not enough Diamonds.", 0xc409 -> 7144 "Mileage Shop is closed."."""
import functools
import struct
import time

from . import items, obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_EVENTS, S2C_EVENTS = 0x1265, 0x1266
C2S_SHOP_BANNERS, S2C_SHOP_BANNERS = 0x1267, 0x1268
C2S_DIARY_BANNERS, S2C_DIARY_BANNERS = 0x126a, 0x126b
C2S_WAR_FIELD_LIST, S2C_WAR_FIELD_LIST = 0x4076, 0x4077
C2S_STATUS_NOTICE, S2C_STATUS_NOTICE = 0x114f, 0x1150
S2C_EVENT_BUFFS = 0x1118
C2S_PACKAGES, S2C_PACKAGES = 0x5a4e, 0x5a4f
C2S_PACKAGE_TAKE, S2C_PACKAGE_TAKE = 0x5a50, 0x5a51
C2S_PACKAGE_DELETE, S2C_PACKAGE_DELETE = 0x5a52, 0x5a53
C2S_PACKAGE_OPENED = 0x5a54
C2S_STORAGE, S2C_STORAGE = 0x108a, 0x108b
C2S_STORAGE_TAKE, S2C_STORAGE_TAKE = 0x108c, 0x108d
C2S_STORAGE_TAKE_ALL, S2C_STORAGE_TAKE_ALL = 0x10cf, 0x10d0
C2S_DIAMOND_BUY, S2C_DIAMOND_BUY = 0x3757, 0x3758
C2S_MILEAGE_BUY, S2C_MILEAGE_BUY = 0x112a, 0x112b
C2S_TOP_UP, S2C_TOP_UP = 0x1155, 0x1156
C2S_LIMITED_SALE, S2C_LIMITED_SALE = 0x3751, 0x3752
C2S_SHOP_OPENED = 0x375b

CANNOT_NOW = 0xc401             # cash mapper -> textsystem 7268
CANNOT_BUY = 0x6442             # -> 10040 "Cannot purchase it."
MILEAGE_CLOSED = 0xc409         # -> 7144 "Mileage Shop is closed."
TEXT_NOT_SUPPORTED = 4          # textsystem 4 "This function is not supported at the moment."

# The family's fixed replies, request -> (reply, body), each the smallest body its handler reads. make() registers
# them over world.EMPTY_REPLIES's.
REPLIES = {
    C2S_SHOP_BANNERS: (S2C_SHOP_BANNERS, b"\0"),                    # CONSTANT: no web banner
    C2S_DIARY_BANNERS: (S2C_DIARY_BANNERS, b"\0"),                  # CONSTANT: no web banner
    C2S_WAR_FIELD_LIST: (S2C_WAR_FIELD_LIST, b"\0"),                # DEAD (spot 20507 only); the empty list if ever
    C2S_STATUS_NOTICE: (S2C_STATUS_NOTICE, b"\0"),                  # DEAD (GameStatusPopup 0); an empty notice if ever
    C2S_STORAGE: (S2C_STORAGE, bytes(3)),                           # CONSTANT: mode 0, total 0
    C2S_STORAGE_TAKE: (S2C_STORAGE_TAKE, struct.pack("<H", CANNOT_NOW)),            # SOLO: no entry to take
    C2S_STORAGE_TAKE_ALL: (S2C_STORAGE_TAKE_ALL, struct.pack("<H", CANNOT_NOW)),    # SOLO: nothing stored
    C2S_DIAMOND_BUY: (S2C_DIAMOND_BUY, struct.pack("<H", CANNOT_BUY)),              # SOLO: no Diamonds
    C2S_MILEAGE_BUY: (S2C_MILEAGE_BUY, struct.pack("<H", MILEAGE_CLOSED)),          # DEAD: the Mileage shop is off
                                                                    # (was 0x6437 "Failed to purchase Diamond item.")
    C2S_TOP_UP: (S2C_TOP_UP, struct.pack("<I", TEXT_NOT_SUPPORTED)),                # SOLO: no top-up page (was 7268
                                                                    # "... Please try again later.", which misleads)
    C2S_LIMITED_SALE: (S2C_LIMITED_SALE, bytes(6)),                 # CONSTANT: u32 0, i16 0
}

# ---- boost events
BUFF_HERO_EXP, BUFF_TROOP_EXP, BUFF_GOLD, BUFF_DROP = range(4)      # 0x1118's kinds, in the HUD's tooltip order
KINDS = {"hero_exp": BUFF_HERO_EXP, "troop_exp": BUFF_TROOP_EXP, "gold": BUFF_GOLD, "drop": BUFF_DROP}
# The official boost events, percent added by kind (OFFICIAL-NOTES "Rewards x multipliers (boost events)" [O]; the
# post's id in its "Sources" table). The footage's parts 11, 14, 15 and 17 were recorded under boosts_2020_03
# (rules census MISSIONS F6: Deathwood's troops 2,052 = 2 x 1,026).
BOOSTS = {
    "gold_2019_11": {"dates": "2019-11-29 .. 12-01", "gold": 100, "source": "SN-g1"},
    "gold_2019_12": {"dates": "2019-12-09 .. 2020-01-07", "gold": 100, "source": "SN-g2"},
    "gold_2020_01": {"dates": "2020-01-17 .. 02-18", "gold": 100, "source": "SN-CU3"},
    "free_weekend_2020_02": {"dates": "2020-02-21 .. 02-23", "gold": 50, "hero_exp": 50, "troop_exp": 50,
                             "source": "SN-free"},
    "gold_2020_02": {"dates": "2020-02-25 .. open end", "gold": 50, "source": "SN-g3"},
    "boosts_2020_03": {"dates": "2020-03-16 .. end of April", "gold": 100, "hero_exp": 100, "troop_exp": 100,
                       "source": "SN-boost, SN-boost2"},
    "anniversary_2020_11": {"dates": "2020-11-16 .. 11-30", "gold": 200, "hero_exp": 100, "troop_exp": 100,
                            "drop": 100, "source": "SN-anniv"},
    "festive_2020_12": {"dates": "2020-12-17 .. 2021-01-07", "gold": 200, "hero_exp": 100, "troop_exp": 100,
                        "drop": 100, "source": "SN-fest"},
}
ACTIVE_BOOST = None             # the owner's pick: a BOOSTS key, on for good; None = no event

# ---- edition packages
ACCOUNT, CHARACTER = 0, 1       # 0x5a4f's kind byte, the part's columns of item_packages_premium
PARTS = ("Account", "Character")
EDITION_PACKAGES = ()           # the owner's pick: the PackageIDs the account bought, e.g. (11,) the Hero Package;
                                # () = none
PAGE = 8
PACKAGE_SLOTS = 6               # Account_Item1..6 / Character_Item1..6
BAG_FULL, TAKEN, ALL_RECEIVED, MISSING = 0x3c03, 0x3c05, 0x5c1d, 0x642a


def boost():
    """The boost that is on (a BOOSTS row; an unknown ACTIVE_BOOST is a KeyError), or None."""
    return BOOSTS[ACTIVE_BOOST] if ACTIVE_BOOST else None


def percent(kind):
    """The percent the boost that is on adds to `kind` ("gold", "hero_exp", "troop_exp", "drop"); 0 with none."""
    if kind not in KINDS:
        raise KeyError(f"no boost kind {kind!r}")
    return (boost() or {}).get(kind, 0)


def boosted(kind, amount):
    """`amount` (gold, exp, or a drop chance) under the boost that is on: the percent added to the rounded amount,
    as the footage pays (hero int(13,009 x 0.9) x 2 = 23,416; a troop 1,191 x 2 = 2,382)."""
    return amount + amount * percent(kind) // 100


def buff_packet():
    """S2C 0x1118: the kinds the boost that is on raises, everywhere (spot 0); the full list (clear first)."""
    b = boost() or {}
    rows = [(idx, b[kind]) for kind, idx in sorted(KINDS.items(), key=lambda k: k[1]) if b.get(kind, 0) > 0]
    w = Writer(S2C_EVENT_BUFFS).u8(OBOOL_TRUE).u8(len(rows))
    for idx, pct in rows:
        w.raw(struct.pack("<QIi", 0, pct, idx)).raw(obf.u32(0))
    return w


@functools.cache
def package_rows():
    """item_packages_premium %Packages by PackageID."""
    return {int(r["PackageID"]): r for r in tables.sections("item_packages_premium")["Packages"]}


def contents(pid, kind):
    """[(item, count)] of package `pid`'s Account or Character part ([] for a part without items: 10's Account)."""
    r = package_rows()[pid]
    return [(int(r[f"{PARTS[kind]}_Item{k}"]), int(r[f"{PARTS[kind]}_Item{k}_Value"]))
            for k in range(1, PACKAGE_SLOTS + 1) if r[f"{PARTS[kind]}_Item{k}"].isdigit()]


def deliver(state, account, now=None):
    """Send the account the EDITION_PACKAGES it has not been sent yet (once each, with the table's receipts: 1 for
    the Account part, Character_Count for the Character part). Returns the ids sent."""
    have = {p["id"] for p in account.get("packages", [])}
    new = [pid for pid in EDITION_PACKAGES if pid not in have]
    for pid in new:
        r = package_rows()[pid]
        account.setdefault("packages", []).append({
            "id": pid, "sent": int(time.time() if now is None else now),
            "left": [int(r["Account_Count"]), int(r["Character_Count"])]})
        journal("package", ev="sent", id=pid, account=account.get("id"))
        log.info("package %d sent to account %s", pid, account.get("id"))
    if new:
        state.save()
    return new


def view(c, pid, kind):
    """The character's flags of a package entry: {} until one is set."""
    return c.get("packages", {}).get(f"{pid}:{kind}", {})


def mark(c, pid, kind, **flags):
    c.setdefault("packages", {}).setdefault(f"{pid}:{kind}", {}).update(flags)


def listed(account, c):
    """The character's Package tab, [(package, kind, [(item, count)])] in the order sent: a part with items while
    receipts are left and this character has not taken it; a taken one stays, empty, until deleted."""
    out = []
    for p in account.get("packages", []):
        for kind in (ACCOUNT, CHARACTER):
            got, v = contents(p["id"], kind), view(c, p["id"], kind)
            if not got or v.get("deleted"):
                continue
            if v.get("taken"):
                out.append((p, kind, []))
            elif p["left"][kind] > 0:
                out.append((p, kind, got))
    return out


def find(account, c, pid, kind):
    return next((e for e in listed(account, c) if e[0]["id"] == pid and e[1] == kind), None)


def entry(p, kind, got, read):
    """A 0x5a4f entry (the module's docstring)."""
    t = time.localtime(p["sent"])
    b = struct.pack("<IH", p["id"], t.tm_year) + bytes([
        t.tm_hour, t.tm_mon, min(p["left"][kind], 255), t.tm_min, t.tm_mday,
        OBOOL_TRUE if read else OBOOL_FALSE, kind]) + obf.u40(0) + bytes([len(got)])
    return b + b"".join(obf.u32(code) + obf.u16(n) for code, n in got)


def packages_packet(account, c, page):
    """S2C 0x5a4f for the character's tab. An empty tab is `00 00 <page> 00`: the count byte is not read then (the
    four zero bytes the login has always been sent)."""
    entries = listed(account, c)
    shown = entries[page * PAGE:page * PAGE + PAGE]
    w = Writer(S2C_PACKAGES).u16(len(entries)).u8(page).u8(len(shown))
    for p, kind, got in shown:
        w.raw(entry(p, kind, got, view(c, p["id"], kind).get("read", False)))
    return w


def make(role, state):
    from . import world

    role.empty_replies(REPLIES)
    role.ignore(C2S_SHOP_OPENED)

    @role.on(C2S_EVENTS)
    def event_list(s, pkt):
        s.send(Writer(S2C_EVENTS).u8(0))
        if boost():
            s.send(buff_packet())

    def key(pkt):
        b = pkt.rest()
        return struct.unpack_from("<IB", b, 0) if len(b) >= 5 else (0, 0xFF)

    @role.on(C2S_PACKAGES)
    def package_list(s, pkt):
        b = pkt.rest()
        deliver(state, s.data["account"])
        s.send(packages_packet(s.data["account"], s.data["char"], b[0] if b else 0))

    @role.on(C2S_PACKAGE_OPENED)
    def package_opened(s, pkt):
        pid, kind = key(pkt)
        c = s.data["char"]
        if find(s.data["account"], c, pid, kind) and not view(c, pid, kind).get("read"):
            mark(c, pid, kind, read=True)
            state.save()

    @role.on(C2S_PACKAGE_TAKE)
    def package_take(s, pkt):
        pid, kind = key(pkt)
        account, c = s.data["account"], s.data["char"]
        e = find(account, c, pid, kind)
        if e is None:
            p = next((p for p in account.get("packages", []) if p["id"] == pid), None)
            gone = p is not None and kind in (ACCOUNT, CHARACTER) and contents(pid, kind) and p["left"][kind] <= 0
            log.warning("package %d part %d refused (%s)", pid, kind, "all received" if gone else "not in the tab")
            s.send(Writer(S2C_PACKAGE_TAKE).u16(ALL_RECEIVED if gone else MISSING))
            return
        p, _, got = e
        if not got:
            s.send(Writer(S2C_PACKAGE_TAKE).u16(TAKEN))
            return
        if not world.fits(c, got):
            s.send(Writer(S2C_PACKAGE_TAKE).u16(BAG_FULL))
            return
        p["left"][kind] -= 1
        mark(c, pid, kind, taken=True, read=True)
        journal("package", ev="taken", id=pid, part=PARTS[kind], char=c.get("name"), left=p["left"][kind],
                items=[[code, n] for code, n in got])
        for code, n in got:
            world.add_item(s, state, code, n, mail=False, why=f"package {pid} {PARTS[kind]}")
        state.save()
        s.send(Writer(S2C_PACKAGE_TAKE).u16(0))
        log.info("package %d %s part taken by %s: %s (%d left)", pid, PARTS[kind], c.get("name"),
                 [(items.name(code), n) for code, n in got], p["left"][kind])

    @role.on(C2S_PACKAGE_DELETE)
    def package_delete(s, pkt):
        pid, kind = key(pkt)
        c = s.data["char"]
        e = find(s.data["account"], c, pid, kind)
        if e is None:
            s.send(Writer(S2C_PACKAGE_DELETE).u16(MISSING))
            return
        mark(c, pid, kind, deleted=True)        # off this character's tab; an untaken part's receipts stay the
        journal("package", ev="deleted", id=pid, part=PARTS[kind], char=c.get("name"),      # account's
                items=[[code, n] for code, n in e[2]])
        state.save()
        s.send(Writer(S2C_PACKAGE_DELETE).u16(0))

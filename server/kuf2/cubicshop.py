"""The Cubic shop: the cash shop window's Cubic tab (CommonSubCashShop, scene 0xf; tab 5 "큐빅 상점" of the menu script
re/ui/UI1_58fbe8d82a00d9b3/.../cashshop/menu/MainMenu.as, switched locally). Owner decision B5 (2026-09-30): Cubic content
allowed, Cubic only from the game's own sources; rules census F7 / L13.

The goods: item_cash %Base rows of MainCategory COMMON (97, every one Currency 2 = Cubic; they hold all 80 item_cubic
SellIDs at the same price, CashPrice = item_currency Buy_Cubic_Shop[Index = SellID], plus the 9 more hero troops and the
8 Reset Entry goods of the official notes' SN-U1 / SN-U2 lists). The client lists on the tab only what 0x3756 sends
(goods list shop+0x30; it looks each SellID up in its own Item_Cash map for the category, 0x14184c630, and shows a good
on tab 5 when MainCategory is COMMON, its status is not 0 and its limit not 0, list builder 0x14059a020). Real-money
goods (Currency 1) are never listed; 0x3757, 0x112a and 0x1155 stay refused (world.EMPTY_REPLIES).

  C2S 0x3755 (CommonSubCashShop OnEnter 0x1405937e0 -> 0x1405969a0, first open only): no body.
  S2C 0x3756 (0x140596ba0, parser 0x1405a2080 -> 0x1405a2200): obool finalize, obool reset (clears the list first),
      cstr, i16 n, n * 0x51-byte entry (entry(); read at 0x140596d8a..0x14059709f); sent in chunks, reset on the first,
      finalize on the last.
  C2S 0x1128 (builder 0x1405a0750 from "Buy" 0x1405954f0, when the first cart entry's money type is 2; the client
      checked price x count <= its Cubic first, 0x14059c070, text 0xd01b): u8 count, u32 SellID (plain).
  S2C 0x1129 Process_ResBuyCubicStoreItem (0x140597af0): i16; 0 -> u8 (echo the count), u32 SellID -> the gained-item
      notice (text 7000) per cart item; any other code only logs the client's assert and clears the cart. The client
      never takes the Cubic itself: 0x375d (world.spend_cubic) carries the new balance.
"""
import functools
import struct

from . import items, obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_LIST, S2C_LIST = 0x3755, 0x3756
C2S_BUY, S2C_BUY = 0x1128, 0x1129
ENTRY = 0x51
CHUNK = 40                      # entries a 0x3756 (40 x 81 bytes; the client's largest frame is not read, 8,655 bytes
                                # of 0x50d1 were taken live)
MONEY_CUBIC = 2                 # entry +0x45 (goods+0x50): 1 cash, 2 Cubic, 3 mileage (world.py MoneyType enum, A8)
UNKNOWN_GOOD = 0x6442           # a SellID not on the tab (any non-zero 0x1129 is silent)
# Goods left off the tab: the data marks them unavailable, or what they do has no offline system (the item's use is
# refused by world.use_item), so a buy would only take the player's Cubic.
HIDDEN = {
    "8106000": "Guild Point Potion: its item row is Availability False",
    "8107000": "Guild Badge: its item row is Availability False",
    "8122000": "Rare Grindstone Chest: item_cubic Availability False",
    "8105000": "Guild Name Change Form: no guild offline",
    "8128000": "Camp Change Ticket: the realm transfer is refused offline (census Q1)",
    "8102000": "Silver Booster Pack (MEMBERSHIP_ITEM): VIP / membership is live service (census header)",
    "8103000": "Gold Booster Pack (MEMBERSHIP_ITEM): as above",
    "8126000": "Character Slot Expansion (CHARSLOT_EXPAND): not built offline",
}


@functools.cache
def goods():
    """The Cubic tab's goods: item_cash COMMON rows priced in Cubic, less HIDDEN and item_cubic's unavailable ones,
    in the table's order."""
    off = {r["SellID"] for r in tables.sections("item_cubic")["Base"] if r.get("Availability") == "False"}
    return [r for r in tables.sections("item_cash")["Base"]
            if r.get("MainCategory") == "COMMON" and r.get("Currency") == str(MONEY_CUBIC)
            and r["SellID"] not in HIDDEN and r["SellID"] not in off and items.row(r["ItemCode"]) is not None]


def good(sell_id):
    return next((r for r in goods() if r["SellID"] == str(sell_id)), None)


def entry(r):
    """A 0x51-byte 0x3756 entry: no limit, no discount, no sale window (obf.time64(0): raw zeros decode to garbage),
    status 1 (buyable), a quantity of 1, permanent (-1)."""
    zero_time = obf.time64(0)
    return (struct.pack("<ii", 0, int(r["CashPrice"])) + bytes([OBOOL_FALSE]) + zero_time + obf.u16(1)
            + struct.pack("<IBIB", 0, 1, int(r["Array"]), 0) + zero_time + struct.pack("<II", 0, 0) + zero_time
            + struct.pack("<iii", int(r["SellID"]), 0, -1) + obf.u32(int(r["ItemCode"]))
            + struct.pack("<I", MONEY_CUBIC) + zero_time)


def list_packets():
    rows = goods()
    chunks = [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)] or [[]]
    out = []
    for k, chunk in enumerate(chunks):
        w = Writer(S2C_LIST).u8(OBOOL_TRUE if k == len(chunks) - 1 else OBOOL_FALSE)
        w.u8(OBOOL_TRUE if k == 0 else OBOOL_FALSE).raw(b"\0").raw(struct.pack("<h", len(chunk)))
        for r in chunk:
            w.raw(entry(r))
        out.append(w)
    return out


def make(role, state):
    from . import world

    @role.on(C2S_LIST)
    def goods_list(s, pkt):
        for w in list_packets():
            s.send(w)

    @role.on(C2S_BUY)
    def buy(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        count, sell_id = b[0], struct.unpack_from("<I", b, 1)[0]
        r = good(sell_id)
        if r is None or count == 0:
            log.warning("Cubic shop: good %d x%d refused (not on the tab)", sell_id, count)
            s.send(Writer(S2C_BUY).u16(UNKNOWN_GOOD))
            return
        price = int(r["CashPrice"]) * count
        if not world.spend_cubic(s, state, price):
            s.send(Writer(S2C_BUY).u16(world.CUBIC_SHORT))
            return
        code, n = int(r["ItemCode"]), int(r["Quantity"]) * count
        journal("item", ev="buy", code=code, name=items.name(code), n=n, shop="cubic", slot=sell_id, price=price,
                money="Cubic")
        world.add_item(s, state, code, n, why=f"Cubic shop {sell_id}")
        s.send(Writer(S2C_BUY).u16(0).u8(count).raw(struct.pack("<I", sell_id)))
        log.info("Cubic shop: %d x%d (%d) for %d Cubic", code, n, sell_id, price)

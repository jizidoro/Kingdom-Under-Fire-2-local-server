"""NPC coin shops (CommonSubRandomShop, scene 0x10; menus STORE_COIN 19, STORE_COIN2 55, STORE_RARE_TROOP_COIN 59,
STORE_COIN3 65; offline only npctable 6239 carries one, STORE_COIN2). Goods: npcrandomshop %NPCRandomShop_Default (ID =
the menu's name, SLOT_ID, ItemID, ItemCount, Weight): one row per slot rolled by Weight and kept until a refresh;
%FreeRefresh (ID, FreeRefreshNum) refreshes a day (daily: inferred). Price = the item's BuyPrice in MoneyType (0 gold,
else a token item held in the bag; inferred from the client's currency display). Kept in c["coin_shop"][menu] =
{"items": [[code, count, sold]], "free": n, "day": iso date}. Spec: specs/items_troops_skills.md 0x154c-0x1550.

  C2S 0x154c (0x140632bf0): u32 menu type.
  S2C 0x154d Process_ResSaleList (0x140633a50): i16; 0 -> u32 free refreshes, u32 menu type, u16 n, n * (coded u32
      item, u8 index, obool sold, coded u16 count); a success shorter than 10 bytes crashes.
  C2S 0x154e SendPacket_ReqBuy (0x140633690): u8 index, u32 menu type, u32 NPC id.
  S2C 0x154f Process_ResBuy (0x140633e20): i16; 0 -> the entry (8 bytes, sold set); 0x447 text 7623, 0x643b failed.
  C2S 0x1550 free refresh (0x140632f70): u32 menu type.   S2C 0x1551: i16; 0 -> the client asks 0x154c again;
      0x643a -> refreshing off.
  C2S 0x1552 paid refresh ("CubicRefresh" 0x140631882, after box 0xd0a7; the client priced it at item_currency
      Randomshop_refresh Index 0 = 580 Cubic, currency type 4, and pre-checked the balance, text 0xd01b): u32 menu
      type.   S2C 0x1553 (0x140634290): i16; 0 -> the client asks 0x154c and shows 0xd0db "Product List has been
      refreshed."; 0x643a -> 0xd0a6, refreshing off; others only an assert log (rules census F8)."""
import random
import struct

from . import items, obf, tables
from .net import log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_LIST, S2C_LIST = 0x154c, 0x154d
C2S_BUY, S2C_BUY = 0x154e, 0x154f
C2S_REFRESH, S2C_REFRESH = 0x1550, 0x1551
C2S_PAID_REFRESH, S2C_PAID_REFRESH = 0x1552, 0x1553
BUY_FAILED = 0x643b
NO_REFRESH = 0x643a
BAG_FULL = 0x447                    # its text is 7623, the item-lock line; the handler names no bag-full code (ours)
MENUS = {18: "STORE_PVP", 19: "STORE_COIN", 55: "STORE_COIN2", 59: "STORE_RARE_TROOP_COIN", 65: "STORE_COIN3"}


def roll_goods(menu, roll=random.randrange):
    rows = [r for r in tables.sections("npcrandomshop")["NPCRandomShop_Default"] if r["ID"] == MENUS.get(menu)]
    out = []
    for slot in sorted({int(r["SLOT_ID"]) for r in rows}):
        opts = [r for r in rows if int(r["SLOT_ID"]) == slot and items.row(r["ItemID"])]
        total = sum(int(r["Weight"]) for r in opts)
        if not total:
            continue
        x = roll(total)
        for r in opts:
            x -= int(r["Weight"])
            if x < 0:
                out.append([int(r["ItemID"]), int(r["ItemCount"]), False])
                break
    return out


def paid_refresh_cost():
    """item_currency Randomshop_refresh Index 0 (one row: 580 Cubic)."""
    return next(int(r["Cubic_Count"]) for r in tables.sections("item_currency")["Base"]
                if r["ItemCurrencyType"] == "Randomshop_refresh" and r["Index"] == "0")


def free_refreshes(menu):
    return next((int(r["FreeRefreshNum"]) for r in tables.sections("npcrandomshop")["FreeRefresh"]
                 if r["ID"] == MENUS.get(menu)), 0)


def shop(c, menu, now=None):
    """The menu's goods of the game day (rules.game_day, 07:00 UTC; the stock period is daily, census F6 / E11)."""
    from . import rules
    today = rules.game_day(now)
    shops = c.setdefault("coin_shop", {})
    sh = shops.get(str(menu))
    if sh is None or sh.get("day") != today:
        sh = shops[str(menu)] = {"items": roll_goods(menu), "free": free_refreshes(menu), "day": today}
    return sh


def entry(i, e):
    code, count, sold = e
    return obf.u32(code) + bytes([i, OBOOL_TRUE if sold else OBOOL_FALSE]) + obf.u16(count)


def make(role, state):
    from . import world

    @role.on(C2S_LIST)
    def sale_list(s, pkt):
        menu = pkt.u32()
        if menu not in MENUS:
            s.send(Writer(S2C_LIST).u16(BUY_FAILED))
            return
        sh = shop(s.data["char"], menu)
        state.save()
        w = Writer(S2C_LIST).u16(0).u32(sh["free"]).u32(menu).u16(len(sh["items"]))
        for i, e in enumerate(sh["items"]):
            w.raw(entry(i, e))
        s.send(w)

    @role.on(C2S_BUY)
    def buy(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        index, menu = b[0], struct.unpack_from("<I", b, 1)[0]
        c = s.data["char"]
        sh = shop(c, menu) if menu in MENUS else {"items": []}
        e = sh["items"][index] if index < len(sh["items"]) else None
        row = items.row(e[0]) if e else None
        price = int(row.get("BuyPrice", "0")) if row and row.get("BuyPrice", "").isdigit() else 0
        money = int(row.get("MoneyType", "0")) if row and row.get("MoneyType", "").isdigit() else 0
        have = c.get("gold", 0) if money == 0 else sum(i["count"] for i in c.get("bag", []) if i["code"] == money)
        if e is None or e[2] or have < price:
            log.warning("coin shop %s slot %d refused (price %d of %d, have %d)", menu, index, price, money, have)
            s.send(Writer(S2C_BUY).u16(BUY_FAILED))
            return
        bag = c.get("bag", [])
        if not world.fits(c, [(e[0], e[1])]):
            s.send(Writer(S2C_BUY).u16(BAG_FULL))
            return
        world.add_item(s, state, e[0], e[1])
        if money == 0:
            world.add_gold(s, state, -price)
        else:
            world.remove_item(s, state, money, price)
        e[2] = True
        state.save()
        s.send(Writer(S2C_BUY).u16(0).raw(entry(index, e)))
        from . import quest
        quest.count(s, state, "PurchaseStoreCoin", "ID1", {"", "-"})
        log.info("coin shop %d: bought %d x%d for %d of %d", menu, e[0], e[1], price, money)

    @role.on(C2S_REFRESH)
    def refresh(s, pkt):
        menu = pkt.u32()
        sh = shop(s.data["char"], menu) if menu in MENUS else {"free": 0}
        if sh["free"] <= 0:
            s.send(Writer(S2C_REFRESH).u16(NO_REFRESH))
            return
        sh["free"] -= 1
        sh["items"] = roll_goods(menu)
        state.save()
        s.send(Writer(S2C_REFRESH).u16(0))

    @role.on(C2S_PAID_REFRESH)
    def paid_refresh(s, pkt):
        menu = pkt.u32()
        if menu not in MENUS:
            s.send(Writer(S2C_PAID_REFRESH).u16(NO_REFRESH))
            return
        sh = shop(s.data["char"], menu)
        cost = paid_refresh_cost()
        if not world.spend_cubic(s, state, cost):
            s.send(Writer(S2C_PAID_REFRESH).u16(world.CUBIC_SHORT))
            return
        sh["items"] = roll_goods(menu)                  # the free refreshes left stay as they were ([I])
        state.save()
        log.info("coin shop %d: paid refresh for %d Cubic", menu, cost)
        s.send(Writer(S2C_PAID_REFRESH).u16(0))

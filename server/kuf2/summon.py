"""The troop summon board (NPC menu GACHA_NORMAL: NPCs 207, 652, 7104; CommonSubGacha, scene 0x3f). Owner decision B5
(2026-09-30): Cubic content allowed, priced from its tables; rules census O12, ITEMS-WIRING I15. Read 2026-09-30.

The board: for each gacha %NormalSummon_Setting row (GroupID 66..78), the %Base row whose BbokyID is that GroupID names
a %Group (50..62); PickCount cards are drawn from it by Prob (relative to the group's sum; with replacement: [I]). The
PickCounts make 25 cards; every row of groups 50..62 is an ITEM card in this build (Visionstones, skill books, chests,
Troop Coins; the TROOP rows sit in groups only the dead 0x110d path used). The client derives each card's rare flag and
effect from (item, count) itself (0x14189e0e0 / 0x14189e220), so the cards carry %Group's exact ItemCount. The board is
the character's (c["summon_board"] = {"day", "used", "cards": [[kind, troop, count, opened, item]]}), drawn again on a
new game day (07:00 UTC: the window's timer counts down to 07:00 of the server clock, 0x1405caf50) at the town entry.

  S2C 0x1113 (0x1405cbbf0): u8 refreshes used (+0x7c; the client's 3 free at +0x80), u8 n, n * 13: u8 level (troop
      cards only), u8 kind 0 troop / 1 item, obf.u16 count, obf.u32 troop, obool opened, obf.u32 item; a card's index
      is its id. It replaces the list without a redraw: pushed at the town entry and before 0x1112, never right after
      0x1110 (the results the Flash "openCard" reads would go).
  C2S 0x110f (builder 0x1405ce600, after box 0x2005): u8 pay 1 Cubic / 0 coupons, u32 n (plain; the client asks
      min(unopened, 5)). The client pre-checks: Cubic >= its price (0x1405cd8a0: int(GachaCost_Rate[n] x
      Gacha_non[min(used, 7)] x n x 1e-5 + 0.5) = 136 x n), or a COUPON_TROOP item held.
  S2C 0x1110 (0x1405cc420): i16; 0 -> u8 n, n * u32 card index (plain); the Flash reveals them.
  C2S 0x1111: one coded bool (T1[b] & 1: 1 free, 0 paid). 3 free a day, then item_currency Gacha_refresh[min(used, 7)]
      (250, 400, 900, 1,950, 4,000 Cubic; box 0x1ff5 "The cost increases every time you refresh it").
  S2C 0x1112: i16 (0 redraws the board 0x1113 put).
Codes (mapper 0x1405ce560): 0x6430 "Not enough Cubics.", 0x6436 "Not enough items.", 0x411 bag full, 0x2c38 "Cannot use
it.", other 7268.
"""
import random
import struct

from . import items, obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_PICK, S2C_PICK = 0x110f, 0x1110
C2S_REFRESH, S2C_REFRESH = 0x1111, 0x1112
S2C_BOARD = 0x1113
PICK_MAX = 5                    # the client's constant (0x1420b37a4)
FREE_REFRESHES = 3              # the client's own +0x80
PAY_CUBIC, PAY_COUPON = 1, 0
COUPON_TROOP = 351500500        # "Use instead of Cubics" (one a card: [I])
ITEMS_SHORT, BAG_FULL, CANNOT_USE = 0x6436, 0x411, 0x2c38
KIND_TROOP, KIND_ITEM = 0, 1


def draw(roll=random.randrange):
    """A new board: [[kind, troop, count, opened, item]] per card, in the setting rows' order."""
    g = tables.sections("gacha")
    base = {r["BbokyID"]: r["GroupID"] for r in g["Base"]}
    cards = []
    for s in g["NormalSummon_Setting"]:
        rows = [r for r in g["Group"] if r["GroupID"] == base.get(s["GroupID"]) and r["Prob"].isdigit()
                and r["REWARD_TYPE"] == "ITEM"]         # all of groups 50..62 (a troop card would need its grant)
        total = sum(int(r["Prob"]) for r in rows)
        for _ in range(int(s["PickCount"]) if total else 0):
            x = roll(total)
            for r in rows:
                x -= int(r["Prob"])
                if x < 0:
                    cards.append([KIND_ITEM, 0, int(r["ItemCount"]) if r["ItemCount"].isdigit() else 1, False,
                                  int(r["REWARD_Item"])])
                    break
    return cards


def _currency(kind):
    return {int(r["Index"]): int(r["Cubic_Count"]) for r in tables.sections("item_currency")["Base"]
            if r["ItemCurrencyType"] == kind and r["Cubic_Count"].isdigit()}


def pick_cost(n, used=0):
    """The client's price of n cards (0x1405cd8a0): int(GachaCost_Rate[n] x Gacha_non[min(used, 7)] x n / 100000 +
    0.5); every rate is 100000 and every Gacha_non row 136."""
    rate = next((int(r["CostRate"]) for r in tables.sections("item_currency")["GachaCost_Rate"]
                 if r["ItemCurrencyType"] == "Gacha_non" and r["Index"] == str(n)), 100000)
    return int(rate * _currency("Gacha_non").get(min(used, 7), 0) * n * 1e-5 + 0.5)


def refresh_cost(used):
    """0 while a free refresh is left, else item_currency Gacha_refresh[min(used, 7)]."""
    return 0 if used < FREE_REFRESHES else _currency("Gacha_refresh").get(min(used, 7), 0)


def board(c, now=None):
    """The character's board of the game day, drawn anew on a new day with its refreshes back."""
    from . import rules
    day = rules.game_day(now)
    b = c.get("summon_board")
    if b is None or b.get("day") != day:
        b = c["summon_board"] = {"day": day, "used": 0, "cards": draw()}
    return b


def board_packet(c):
    b = board(c)
    w = Writer(S2C_BOARD).u8(min(b["used"], 255)).u8(len(b["cards"]))
    for kind, troop, count, opened, item in b["cards"]:
        w.u8(0).u8(kind).raw(obf.u16(count)).raw(obf.u32(troop)).u8(OBOOL_TRUE if opened else OBOOL_FALSE)
        w.raw(obf.u32(item))
    return w


def make(role, state):
    from . import world

    @role.on(C2S_PICK)
    def pick(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        pay, n = b[0], struct.unpack_from("<I", b, 1)[0]
        c = s.data["char"]
        from . import rules
        if (c.get("summon_board") or {}).get("day") != rules.game_day():
            s.send(board_packet(c))                     # the day turned with the window open: the new board first,
                                                        # so the picked indices name the cards the client holds
        bd = board(c)
        shut = [i for i, card in enumerate(bd["cards"]) if not card[3]]
        if not 1 <= n <= min(PICK_MAX, len(shut)):
            s.send(Writer(S2C_PICK).u16(CANNOT_USE))
            return
        chosen = random.sample(shut, n)                 # which closed cards open is ours (uniform)
        grant = [(bd["cards"][i][4], bd["cards"][i][2]) for i in chosen]
        if not world.fits(c, grant):
            s.send(Writer(S2C_PICK).u16(BAG_FULL))
            return
        if pay == PAY_CUBIC:
            cost = pick_cost(n, bd["used"])
            if not world.spend_cubic(s, state, cost):
                s.send(Writer(S2C_PICK).u16(world.CUBIC_SHORT))
                return
        elif sum(i["count"] for i in c.get("bag", []) if i["code"] == COUPON_TROOP) >= n:
            cost = 0
            world.remove_item(s, state, COUPON_TROOP, n, why="troop summon")
        else:
            s.send(Writer(S2C_PICK).u16(ITEMS_SHORT))
            return
        for i in chosen:
            card = bd["cards"][i]
            card[3] = True
            world.add_item(s, state, card[4], card[2], why="troop summon")
        state.save()
        journal("summon", ev="pick", cards=[bd["cards"][i] for i in chosen], cubic=cost)
        s.send(Writer(S2C_PICK).u16(0).u8(n).raw(b"".join(struct.pack("<I", i) for i in chosen)))
        log.info("summon board: %d cards %s for %s", n, chosen, f"{cost} Cubic" if pay == PAY_CUBIC else "coupons")

    @role.on(C2S_REFRESH)
    def refresh(s, pkt):
        c = s.data["char"]
        bd = board(c)
        cost = refresh_cost(bd["used"])
        if cost and not world.spend_cubic(s, state, cost):
            s.send(Writer(S2C_REFRESH).u16(world.CUBIC_SHORT))
            return
        bd["used"] += 1
        bd["cards"] = draw()
        state.save()
        journal("summon", ev="refresh", used=bd["used"], cubic=cost)
        s.send(board_packet(c))
        s.send(Writer(S2C_REFRESH).u16(0))

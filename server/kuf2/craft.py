"""Crafting (NPC menus MAKING_*, craft window 0x40, CraftInfoManager = common[0x14]). Recipes are item_makeproduct %Make
rows (ItemCode = the recipe id and the product; CraftGroup; Quantity; Gold; ReqCraftLevel; ReqHeroLevel; CraftExp;
Material_1..5 / MaterialNum_1..5; every row has one product at Weight 100000), craft levels %CraftLevelUP (the exp
each level needs per group; Gold_Rate per mille). The character keeps c["craft"] = {"level": [4], "exp": [4],
"favorites": [recipe], "running": {group: {recipe, count, uid, done}}, "uid": n}. Specs:
specs/session_account_worldmap.md 0x10d7-0x10df (2026-09-27); the order start -> finish -> receive follows the
window's callbacks (the finish is sent when the craft bar ends, inferred).

  C2S 0x10d7 'ReqSetFavorItem' (0x1405b4370): byte T2[flag + 2 * b1] (flag = T1[b0] & 1), coded u32 recipe.
  S2C 0x10d8 (0x1406688b0): i16; 0 -> obool on, coded u32 recipe.
  C2S 0x10d9 (after the confirm 0x1d62, 0x1405b4730): u32 count (inferred), u32 station (window +0x50), coded u32 recipe.
  S2C 0x10da Process_CraftStart (0x1406689f0): i16; 0 -> i32 (the count, inferred), coded u32 recipe.
  C2S 0x10db 'RequestItemCraftFinal' (0x1405b3b60): u32 station, coded u32 recipe.
  S2C 0x10dc (0x140668f20, reader 0x140669f60): i16; 0 -> u64 result uid, u8 craft level, i32 group, coded u32 recipe,
      u64 group exp (low 32 bits kept), u16 m, m * (coded u32 item, coded u16 count); a level change prints 0x1d98+g.
  C2S 0x10dd 'ReqCraftItemRecv': u64 result uid, u32 station.     S2C 0x10de (0x140668da0): i16; 0 -> u64 uid.
  C2S 0x10df 'CancelItemCraft' (also on closing the window mid-craft): coded u32 recipe.   S2C 0x10e0: i16.
  S2C 0x10e1 (0x140669690) at start: 36 bytes, group g's u64 exp / u8 level at STATE_AT[g] (the manager's +0x28+8g /
      +0x2c+8g, as the 0x10dc handler indexes them), then u16 n, n * coded u32 favourite.
Results other than 0 go through 0x140669d20 (0x40a -> text 0x1c64)."""
import struct

from . import items, obf, settings, tables
from .net import log
from .packet import Writer

C2S_FAVORITE, S2C_FAVORITE = 0x10d7, 0x10d8
C2S_START, S2C_START = 0x10d9, 0x10da
C2S_FINISH, S2C_FINISH = 0x10db, 0x10dc
C2S_RECEIVE, S2C_RECEIVE = 0x10dd, 0x10de
C2S_CANCEL, S2C_CANCEL = 0x10df, 0x10e0
S2C_STATE = 0x10e1
S2C_RUNNING = 0x10e2
REFUSED = 0x40a
GROUPS = ("M_WEAPON", "M_DEFENSE", "M_ACC", "M_ALCHEMY")    # the client's enum order (name table 0x1434ab250)
STATE_AT = ((0x1a, 0x23), (0x11, 0x22), (1, 0x19), (9, 0))
MATERIALS = 5


def recipe(code):
    return next((r for r in tables.sections("item_makeproduct")["Make"] if r["ItemCode"] == str(code)), None)


def level_rows():
    return tables.sections("item_makeproduct")["CraftLevelUP"]


def record(c):
    cr = c.setdefault("craft", {})
    cr.setdefault("level", [1] * len(GROUPS))
    cr.setdefault("exp", [0] * len(GROUPS))
    cr.setdefault("favorites", [])
    cr.setdefault("running", {})
    return cr


def materials(r, count):
    return [(int(r[f"Material_{k}"]), int(r[f"MaterialNum_{k}"]) * count) for k in range(1, MATERIALS + 1)
            if r[f"Material_{k}"].isdigit()]


def cost(r, level, count, off=0):
    """The craft's gold: ceil(Gold x count x %CraftLevelUP Gold_Rate / 1000), the price the recipe menu shows and checks
    the bag's gold against (ContentDetail SetItemDetailInfo_Req / SetCraftCountInfo: Math.ceil(cost *
    g_nCraftGoldDecRate / DEFAULT_CRAFT_RATE 1000); rules census ECONOMY G2). `off` is what the guild's
    MakeCost_Discount takes off the rate, per mille (guild.make_rate_off: the window is handed Gold_Rate - 10 x the
    skill's percent as g_nCraftGoldDecRate, 0x1405b1c49)."""
    rate = next((int(x["Gold_Rate"]) for x in level_rows() if x["Level"] == str(level)), 1000) - off
    return -(-int(r["Gold"]) * count * rate // 1000)


def penalty_level(level):
    """%CraftLevelUP Penalty_Level of a craft level (1 at 1-3, 2 at 4-6, 3 at 7-9, 4 at 10-12, 5 at 13-15)."""
    return next((int(x["Penalty_Level"]) for x in level_rows() if x["Level"] == str(level)), 1)


def craft_exp(r, level, count):
    """The craft exp of `count` of recipe r at the player's craft level in its group, as the recipe menu previews it
    (ContentDetail.UpdateExp, rules census ECONOMY G4): the full CraftExp while the player's penalty level is not above
    the recipe's (the band of its ReqCraftLevel), floor(CraftExp / 2) one band above, floor(CraftExp / 10) two above,
    0 beyond; times the count."""
    exp, over = int(r["CraftExp"]), penalty_level(level) - penalty_level(int(r["ReqCraftLevel"]))
    return (exp if over <= 0 else exp // 2 if over == 1 else exp // 10 if over == 2 else 0) * count


def state_packet(c):
    cr = record(c)
    head = bytearray(0x24)
    for g, (exp_at, level_at) in enumerate(STATE_AT):
        struct.pack_into("<Q", head, exp_at, cr["exp"][g])
        head[level_at] = cr["level"][g]
    w = Writer(S2C_STATE).raw(bytes(head)).u16(len(cr["favorites"]))
    for f in cr["favorites"]:
        w.raw(obf.u32(f))
    return w


def running_packet(c):
    """0x10e2 (0x140669800) at start: u16 n, n * (u64 result uid or 0, coded u32 recipe, u32 count, u16 m, m * (coded
    u32 item, coded u16 count)); the client clears its craft map first."""
    cr = record(c)
    runs = list(cr["running"].values())
    w = Writer(S2C_RUNNING).u16(len(runs))
    for run in runs:
        products = run.get("products") or [] if run.get("uid") else []
        w.u64(run.get("uid") or 0).raw(obf.u32(run["recipe"])).u32(run["count"]).u16(len(products))
        for item, n in products:
            w.raw(obf.u32(item)).raw(obf.u16(n))
    return w


def gain_exp(cr, g, exp):
    """Add craft exp to group g; a level needs %CraftLevelUP's group column at that level. The cap is the MaxCraftLevel
    setting (GAMEFORGE 9; the client's settings +0x3db, read at 0x1405b2af5 beside the craft window's builders) within
    the table's 15 rows. No recipe needs more than level 4."""
    rows = {int(x["Level"]): int(x[GROUPS[g]]) for x in level_rows()}
    top = min(settings.get("MaxCraftLevel"), max(rows))
    cr["exp"][g] += exp
    while cr["level"][g] in rows and cr["level"][g] < top and cr["exp"][g] >= rows[cr["level"][g]]:
        cr["exp"][g] -= rows[cr["level"][g]]
        cr["level"][g] += 1


def make(role, state):
    from . import world

    @role.on(C2S_FAVORITE)
    def favorite(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        on, code = bool(obf.T1[b[0]] & 1), obf.dec_u32(b[1:5])
        favs = record(s.data["char"])["favorites"]
        if on and code not in favs:
            favs.append(code)
        elif not on and code in favs:
            favs.remove(code)
        state.save()
        s.send(Writer(S2C_FAVORITE).u16(0).obool(on).raw(obf.u32(code)))

    @role.on(C2S_START)
    def start(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            log.warning("craft start not understood: %s", b.hex())
            return
        count, code = struct.unpack_from("<I", b, 0)[0], obf.dec_u32(b[8:12])
        c = s.data["char"]
        cr = record(c)
        r = recipe(code)
        g = GROUPS.index(r["CraftGroup"]) if r and r["CraftGroup"] in GROUPS else None
        need = materials(r, count) if r else []
        from . import guild
        off = guild.make_rate_off(c)                # the guild's MakeCost_Discount, off the level's Gold_Rate
        why = ("no recipe" if g is None else "a craft is running" if str(g) in cr["running"] else
               "count" if not 1 <= count <= 999 else
               "hero level" if c.get("level", 1) < int(r["ReqHeroLevel"]) else
               "craft level" if cr["level"][g] < int(r["ReqCraftLevel"]) else
               "gold" if c.get("gold", 0) < cost(r, cr["level"][g], count, off) else
               "materials" if any(sum(i["count"] for i in c.get("bag", []) if i["code"] == m) < n for m, n in need)
               else None)
        if why:
            log.warning("craft %d x%d refused: %s", code, count, why)
            s.send(Writer(S2C_START).u16(REFUSED))
            return
        for m, n in need:
            world.remove_item(s, state, m, n)
        paid = cost(r, cr["level"][g], count, off)
        world.add_gold(s, state, -paid)
        cr["running"][str(g)] = {"recipe": code, "count": count, "uid": None, "gold": paid}  # what a cancel returns
        state.save()
        s.send(Writer(S2C_START).u16(0).i32(count).raw(obf.u32(code)))
        log.info("craft %d x%d started (group %s)", code, count, GROUPS[g])

    @role.on(C2S_FINISH)
    def finish(s, pkt):
        b = pkt.rest()
        if len(b) < 8:
            return
        code = obf.dec_u32(b[4:8])
        c = s.data["char"]
        cr = record(c)
        g, run = next(((int(k), v) for k, v in cr["running"].items() if v["recipe"] == code), (None, None))
        if run is None or run["uid"] is not None:
            log.warning("craft finish without a running craft of %d", code)
            s.send(Writer(S2C_FINISH).u16(REFUSED))
            return
        r = recipe(code)
        cr["uid"] = cr.get("uid", 0) + 1
        run["uid"] = (c["id"] << 32) | cr["uid"]
        run["products"] = [[int(r["ItemCode"]), int(r["Quantity"]) * run["count"]]]
        gain_exp(cr, g, craft_exp(r, cr["level"][g], run["count"]))
        from . import titles
        titles.achieve(s, state, "ItemMakeTypeLv", value=cr["level"][g], cond={1: GROUPS[g]})
        state.save()
        w = Writer(S2C_FINISH).u16(0).u64(run["uid"]).u8(cr["level"][g]).i32(g).raw(obf.u32(code)).u64(cr["exp"][g])
        w.u16(len(run["products"]))
        for item, n in run["products"]:
            w.raw(obf.u32(item)).raw(obf.u16(n))
        s.send(w)

    @role.on(C2S_RECEIVE)
    def receive(s, pkt):
        b = pkt.rest()
        if len(b) < 8:
            return
        uid = struct.unpack_from("<Q", b, 0)[0]
        cr = record(s.data["char"])
        key = next((k for k, v in cr["running"].items() if v["uid"] == uid), None)
        if key is None:
            s.send(Writer(S2C_RECEIVE).u16(REFUSED))
            return
        run = cr["running"].pop(key)
        for item, n in run["products"]:
            world.add_item(s, state, item, n)
        state.save()
        s.send(Writer(S2C_RECEIVE).u16(0).u64(uid))
        from . import quest
        quest.count(s, state, "AnyMakeProduct", "ID1", {"", "-"})
        log.info("craft %d received: %s", run["recipe"], run["products"])

    @role.on(C2S_CANCEL)
    def cancel(s, pkt):
        b = pkt.rest()
        if len(b) < 4:
            return
        code = obf.dec_u32(b[0:4])
        c = s.data["char"]
        cr = record(c)
        key = next((k for k, v in cr["running"].items() if v["recipe"] == code and v["uid"] is None), None)
        if key is not None:
            run = cr["running"].pop(key)
            r = recipe(code)
            for m, n in materials(r, run["count"]):           # the client shows no loss: refunded (inferred)
                world.add_item(s, state, m, n, capped=False)
            world.add_gold(s, state, run.get("gold", cost(r, cr["level"][int(key)], run["count"])))   # as paid
            state.save()
        s.send(Writer(S2C_CANCEL).u16(0))

"""The economy rules hunt (planning/rules/ECONOMY.md, 2026-10-01): the rows the hunt settled as DIFFERS / MISSING, built
test-first from the original's evidence (the tape's frames, the client's code, the tables). Reads the game tables from
the installed game. Run: py -m pytest -q server/tests"""
import random
import struct

import pytest

from kuf2 import game, zone
from test_rewards import Session, State, char


# B7: a repeated mission's kill gold is scaled by the %Repeat_Penalty ExpRate of the clears before the room (the entry
# window's "EXP, Gold Bonus 300% / 200%"). Tape: Kedington Castle Wall 10320 (Repeat_Penalty_Control True), its ogre
# troop 120270 (item_drop_money 543-664): 193 + 177 + 186 = 556 on the first clear (part 12 f_00495) and
# 133 + 134 + 116 = 383 = 0.66 x 580 on the second (part 13 f_00199-f_00201, the window "200%"); its 2-3 gold
# soldiers (120030) 2 on the first, 1 on the second.

def kedington_troop(table_id, cleared):
    s = Session(char(level=22), spot=10320)
    s.data["char"]["cleared"] = {"10320": [cleared, 0, 0]}
    t = next(t for t in zone.for_spot(10320)["NPCTroopInfoData"] if t["TroopTableID"] == table_id)
    assert game.spawn_zone_troop(s, t)
    return s, t


@pytest.mark.parametrize("table_id, cleared, gold", [
    (120270, 0, 664),                   # first clear: the row's most (x1)
    (120270, 1, 438),                   # second clear: floor(664 x 0.66)
    (120270, 2, 332),                   # third: x0.5
    (120270, 3, 219),                   # fourth and on: x0.33
    (120030, 0, 3), (120030, 1, 1),     # the 2-3 soldiers: 3, then floor(3 x 0.66) = 1 as the tape's "1 (+1) Gold"
])
def test_a_repeated_missions_kill_gold_takes_the_repeat_rate(monkeypatch, table_id, cleared, gold):
    from test_loot import hit_to_wipe
    monkeypatch.setattr(random, "randrange", lambda n: n - 1)
    s, t = kedington_troop(table_id, cleared)
    hit_to_wipe(game.make(State(), 0), s, t["TroopID"])
    assert sum(s.data["gold_drops"].values()) == gold


def test_the_repeat_rate_leaves_gold_alone_where_the_penalty_is_off():
    c = {"cleared": {"10349": [5, 0, 0], "10320": [5, 0, 0]}}
    assert game.repeat_gold(c, 10349, 0, 100) == 100          # the spear camp: Repeat_Penalty_Control False
    assert game.repeat_gold(c, 10320, 0, 100) == 33           # Kedington: the last row, 0.33
    assert game.repeat_gold(c, 10001, 0, 100) == 100          # a field: no clears, no control


# G2: the craft window prices a craft as ceil(Gold x count x Gold_Rate / 1000) (the recipe menu's ContentDetail
# SetItemDetailInfo_Req / SetCraftCountInfo: Math.ceil(cost * g_nCraftGoldDecRate / DEFAULT_CRAFT_RATE 1000)), what
# the player sees and the bag's gold is checked against.

def test_the_craft_price_rounds_up_as_the_window_shows_it():
    from kuf2 import craft
    r = craft.recipe(350000030)                                 # 500 gold, Gold_Rate 990 at craft level 2
    assert craft.cost(r, 1, 1) == 500
    assert craft.cost(r, 2, 1) == 495 and craft.cost(r, 2, 3) == 1485
    fake = dict(r, Gold="7")
    assert craft.cost(fake, 2, 1) == 7                          # 6.93 -> 7 (floor gave 6)
    assert craft.cost(fake, 9, 3) == 20                         # 21 x 0.92 = 19.32 -> 20


# G4: %CraftLevelUP Penalty_Level: the recipe menu's exp preview (ContentDetail.UpdateExp) gives the full CraftExp while
# the player's penalty level (at his craft level in the group) is not above the recipe's (at its ReqCraftLevel), half
# (floored) one band above, a tenth (floored) two above, nothing beyond, times the count.

@pytest.mark.parametrize("player_level, exp", [(1, 10), (3, 10), (4, 5), (6, 5), (7, 1), (9, 1), (10, 0), (15, 0)])
def test_craft_exp_falls_with_the_penalty_bands_above_the_recipe(player_level, exp):
    from kuf2 import craft
    r = dict(craft.recipe(350000030), CraftExp="10", ReqCraftLevel="1")      # a level-1 recipe (penalty band 1)
    assert craft.craft_exp(r, player_level, 1) == exp
    assert craft.craft_exp(r, player_level, 4) == exp * 4


def test_a_finished_craft_pays_the_penalised_exp():
    from kuf2 import craft, obf
    from kuf2.net import Role
    from test_rewards import pkt
    role = Role("world", 0, State())
    craft.make(role, State())
    c = char(level=30)
    s = Session(c)
    cr = craft.record(c)
    code = 101117217                                            # a level-2 weapon recipe, CraftExp 25 (band 1)
    cr["level"][0] = 7                                          # weapon craft 7: band 3, two above -> a tenth
    cr["running"]["0"] = {"recipe": code, "count": 2, "uid": None}
    role.handlers[craft.C2S_FINISH](s, pkt(craft.C2S_FINISH, struct.pack("<I", 0) + obf.u32(code)))
    assert cr["exp"][0] == (25 // 10) * 2 and cr["level"][0] == 7


# I3: the repair coupon 351500400 "Universal Repair: Repairs all equipped items when used." (textitem Explain): the
# worn items only; the bag's worn-down items stay as they are.

def test_the_repair_coupon_mends_the_worn_items_only():
    from kuf2 import hero, items, world
    from test_quest import use_body, world_role as _wr     # noqa: F401 (the fixture's helpers)
    from test_rewards import pkt
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    c = char(level=30)
    c.update(gold=0, spot=10001, bag=[{"code": 351500400, "slot": 0, "count": 1, "serial": 3, "bound": False}])
    s = Session(c)
    main = next(e for e in hero.equipment(c) if items.full_durability(e["code"]) > 0)
    main["dur"] = 10
    spare = {"code": main["code"], "slot": 1, "count": 1, "serial": 9, "bound": False, "dur": 20}
    c["bag"].append(spare)
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use_body(351500400, 3)))
    assert "dur" not in main and spare["dur"] == 20


# I4: "If the item's durability drops to 0, the item stats will be no longer valid." (texttutorial Item_Durability):
# a worn item at durability 0 adds nothing (its traits, enchant, sockets and set count), until it is repaired.

def test_a_worn_item_at_durability_zero_adds_no_stats():
    from kuf2 import hero, items
    c = char(level=10)
    top = next(e for e in hero.equipment(c) if items.row(e["code"]).get("Parts") == "UPPERBODY")
    whole = hero.char_stats(c, abilities={})["HP_MAX"]
    top["dur"] = 0
    broken = hero.char_stats(c, abilities={})["HP_MAX"]
    hp = sum(v for n, v, pct in items.traits(top["code"]) if n == "HP_MAX" and not pct)
    assert hp > 0 and whole - broken == hp                      # the kit's top (371 HP on Glen's)
    top["dur"] = 1
    assert hero.char_stats(c, abilities={})["HP_MAX"] == whole


# M2: titletable %AchievementInfo StateMissionClear (31 / 32 / 96 / 114: Complete_Condition1 = spottable State 10 / 11 /
# 90 / 13, "Clear Eastern Settlement Mission %1% times" 61112, "Clear Hexter Mission" 61114): every won mission counts
# for its spot's State; titles 60112 (7), 60113 (15), 60198 (50) ... follow.

def test_a_won_mission_counts_for_its_regions_clear_titles():
    from kuf2 import titles
    s = Session(char(level=30))
    st = State()
    c = s.data["char"]
    game.count_state_clear(s, st, 10233)                     # Tower of Moonlight: State 20, no such achievement
    assert "31" not in c.get("achievements", {}) and "32" not in c.get("achievements", {})
    for _ in range(7):
        game.count_state_clear(s, st, 10306)                 # Fort Valley: State 10
    game.count_state_clear(s, st, 20304)                     # State 11
    assert c["achievements"]["31"] == 7 and c["achievements"]["32"] == 1
    assert 60112 in c["titles"] and 60113 not in c["titles"]
    assert any(w.proto == titles.S2C_TITLE_EARNED for w in s.sent)


def test_the_win_counts_the_region_clear():
    from test_rewards import win
    s = Session(char(level=8), spot=10235)                   # New Hampton Castle: State 10
    win(s, State(), seconds_ago=600)
    assert s.data["char"]["achievements"]["31"] == 1


# A5: the tokens' daily gain caps. item_token DayLimit on the six TOKEN_ITEMs (Crack Shard 200, Crack Crystal 100, Time
# Fragment 10, Coliseum Silver Coin 40, Clash Coin 50, Easter Egg 40) is what the official notes call the "Daily and
# weekly limits" (crack shards 200 / day, crystals 100 / day); the client counts only uses against an item's DayLimit
# (the counter 0x140dce120 is written by the use reply alone, 0x1408eeb70), and a token is never used, so the cap on
# gains is the server's: past it the day's gains are not given (textsystem 5763 "[%1%] You've reached the max.
# acquirable amount per day."), again from the next game day (07:00 UTC, rules.game_day).

def token_session():
    s = Session(char(level=30))
    s.data["char"].update(bag=[], spot=10001, gold=0)
    return s


def held(c, code):
    return sum(i["count"] for i in c["bag"] if i["code"] == code)


def test_a_token_stops_at_its_daily_gain_cap():
    from kuf2 import world
    s, st, day = token_session(), State(), 1_760_000_000          # 2025-10-09 08:53 UTC
    c = s.data["char"]
    world.add_item(s, st, 760000050, 150, now=day)                # Crack Shard, DayLimit 200
    world.add_item(s, st, 760000050, 100, now=day + 60)
    assert held(c, 760000050) == 200
    world.add_item(s, st, 760000050, 5, now=day + 120)
    assert held(c, 760000050) == 200
    world.add_item(s, st, 760000050, 30, now=day + 86400)         # the next game day
    assert held(c, 760000050) == 230
    world.add_item(s, st, 760000140, 12, now=day)                 # Time Fragment, 10 a day
    assert held(c, 760000140) == 10
    world.add_item(s, st, 760000030, 5000, now=day)               # Troop Coin: no DayLimit
    assert held(c, 760000030) == 5000


def test_the_cap_counts_gains_not_moves():
    from kuf2 import world
    s, st, day = token_session(), State(), 1_760_000_000
    c = s.data["char"]
    world.add_item(s, st, 760000090, 100, now=day)                # Crack Crystal, 100 a day
    world.add_item(s, st, 760000090, 20, now=day, capped=False)   # a move back into the bag (a mail's attachment)
    assert held(c, 760000090) == 120


# L9: make-up attendance for Cubic (C2S 0x10c3). The calendar prices the selected days itself (0x1405beec0): for the
# k-th day, item_currency Diary at index min(this month's make-ups + k, 8) (20, 40, 70, 120, 180, 250, 350, 460, 580
# Cubic), and sends only when the Cubic covers it (0x1405be0e0: u8 n + n x (u8 day, u16 year, u8 month)). The reply
# 0x10c4 (0x1405bd430): i16 0, u8 accrue group, u16 days attended this month, u8 make-ups this month, u8 n + n x (u8
# day, u8 month); then the client prints 71011 "Completed attendance check.<br>The reward will be sent via mail." The
# make-up count is the diary's header +2 (0x10c0, "This Month's Replenishment Count").

from kuf2 import diary as _diary                                # noqa: E402

MAKEUP_DAY = __import__("datetime").date(2026, 9, 27)          # a Sunday


def makeup(s, st, days):
    from kuf2 import world
    from test_rewards import pkt
    role = world.make(st, 0, "127.0.0.1", 0)
    body = bytes([len(days)]) + b"".join(struct.pack("<BHB", d.day, d.year, d.month) for d in days)
    role.handlers[_diary.C2S_MAKEUP](s, pkt(_diary.C2S_MAKEUP, body))
    return bytes(next(w for w in reversed(s.sent) if w.proto == _diary.S2C_MAKEUP).buf)


def test_the_makeup_price_climbs_the_diary_row():
    assert [_diary.makeup_price(0, n) for n in (1, 2, 3)] == [20, 60, 130]
    assert _diary.makeup_price(7, 3) == 460 + 580 + 580
    assert _diary.makeup_price(9, 1) == 580


def test_making_up_past_days_charges_cubic_records_them_and_mails_the_rewards(monkeypatch):
    import datetime
    monkeypatch.setattr(_diary, "today", lambda: MAKEUP_DAY)
    s, st = Session(char(level=30)), State()
    c = s.data["char"]
    c.update(name="A", cubic=100, attended=["2026-09-27"], bag=[])
    days = [datetime.date(2026, 9, 25), datetime.date(2026, 9, 26)]
    out = makeup(s, st, days)
    assert out[:2] == b"\0\0" and c["cubic"] == 100 - 20 - 40
    assert sorted(c["attended"]) == ["2026-09-25", "2026-09-26", "2026-09-27"]
    group, count, made = out[2], struct.unpack_from("<H", out, 3)[0], out[5]
    assert (group, count, made) == (_diary.ACCRUE_GROUP, 3, 2)
    assert out[6] == 2 and out[7:] == bytes([25, 9, 26, 9])
    mails = c.get("mail", [])
    assert len(mails) == 2 and all(m["items"] for m in mails)
    fri = _diary.week_row(days[0])["ItemReward_Fri"]
    assert mails[0]["items"][0]["code"] == _diary._group_items(fri)[0]
    s.sent.clear()
    _diary.send_diary(s)
    assert bytes(s.sent[-1].buf)[2] == 2                         # the header's make-up count


@pytest.mark.parametrize("day, cubic", [((2026, 9, 27), 100),   # today: attended the normal way
                                        ((2026, 9, 28), 100),   # a future day
                                        ((2026, 8, 30), 100),   # last month
                                        ((2026, 9, 20), 10)])   # Cubic short
def test_a_makeup_is_refused_outside_this_months_past_open_days(monkeypatch, day, cubic):
    import datetime
    monkeypatch.setattr(_diary, "today", lambda: MAKEUP_DAY)
    s, st = Session(char(level=30)), State()
    c = s.data["char"]
    c.update(name="A", cubic=cubic, attended=["2026-09-27"], bag=[])
    out = makeup(s, st, [datetime.date(*day)])
    assert out[:2] != b"\0\0" and c["cubic"] == cubic and c["attended"] == ["2026-09-27"] and not c.get("mail")
    if cubic == 10:
        assert struct.unpack_from("<H", out)[0] == 0x6430


# H11: random options. Every RandomOptionID_n of an item row (Prob_n 100000 on 9,468 of 9,469) gives the item one
# option: one TraitType of its randomoption row by Weight, its value in Min..Max ("%" a fraction, else a whole number).
# The record's tail carries them (u8 k + k x 10: i8 E_TraitTypes, u8 E_TraitTarget, f32 fraction, i32 whole; read by
# 0x140d66d40, shown by the tooltip 0x1406a0ba0: byte 0 the trait, byte 1 the target, the f32 x 100 as a percent); the
# tape's card tooltip counts them before the pick ("2 Random Options" on Senior Centurion Ring B, part 17 f_01436,
# whose row holds two 812441 slots). The reroll (C2S 0x10d2) takes Purification Stones (item_randomoptionini %ReqCost
# by level and rarity) and, per locked option, item_currency Random_option_init[ReqLevel] x Random_Option_init
# [Rarity] Cubic (the client's lock price 0x14060e400 -> 0x14188dc40); 0x10d3 previews the unlocked slots (u8 slot +
# 10 bytes each, 0x14060f540), 0x10d4 applies them (0x10d5).

from kuf2 import items as _items                                # noqa: E402

RING = 201124412                                                # Senior Centurion Ring B: HERO, Lv 24, 812441 x2


def test_the_trait_enum_is_the_clients():
    assert _items.TRAIT_TYPES.index("HP_MAX") == 0 and _items.TRAIT_TYPES.index("ATTACK_PHYSICAL") == 15
    assert _items.TRAIT_TYPES.index("ABILITY_ADD_DAMAGE_RATE_01") == 66
    assert _items.TRAIT_TYPES.index("M_DEFENCE_PHYSICAL") == 104 and _items.TRAIT_TYPES[-1] == "M_IMMUNE_ATTACK"
    assert all(_items.TRAIT_TYPES[i] == name for name, i in game.STAT_IDS.items())


def test_a_ring_rolls_one_option_per_slot_from_its_row():
    opts = _items.roll_options(RING, lambda n: n - 1)           # the last weighted trait, the top value
    assert len(opts) == 2
    for t, target, pct, flat, source in opts:
        assert _items.TRAIT_TYPES[t] == "ABILITY_ADD_DAMAGE_RATE_08" and target == _items.TARGET_LEADER
        assert (pct, flat, source) == (0.0, 47, 812441)
    low = _items.roll_options(RING, lambda n: 0)
    assert [(_items.TRAIT_TYPES[o[0]], o[3]) for o in low] == [("ABILITY_ADD_DAMAGE_RATE_01", 24)] * 2
    assert _items.roll_options(151101119, lambda n: 0) == [] or all(len(o) == 5 for o in
                                                                     _items.roll_options(151101119, lambda n: 0))


def test_a_percent_option_is_a_fraction():
    row = next(r for r in __import__("kuf2.tables", fromlist=["x"]).sections("randomoption")["RandomOption"]
               if r["RandomOptionID"] == "7000110")
    assert _items.option_from_row(row, lambda n: 0) == (_items.TRAIT_TYPES.index("ATTACK_PHYSICAL"), 1, 0.06, 0, 7000110)


def test_the_record_carries_the_options():
    opts = [[_items.TRAIT_TYPES.index("ATTACK_PHYSICAL"), 1, 0.09, 0, 7000110], [66, 1, 0.0, 47, 812441]]
    rec = _items.record(RING, 3, 77, options=opts)
    tail = rec[-21:]
    assert tail[0] == 2
    assert struct.unpack_from("<bBfi", tail, 1) == (15, 1, pytest.approx(0.09), 0)
    assert struct.unpack_from("<bBfi", tail, 11) == (66, 1, 0.0, 47)
    assert _items.record(RING, 3, 77)[-1:] == b"\0"


def test_a_gained_ring_has_its_options_in_the_bag():
    from kuf2 import world
    s, st = Session(char(level=30)), State()
    s.data["char"].update(bag=[], spot=10001, gold=0)
    world.add_item(s, st, RING, 1)
    it = s.data["char"]["bag"][0]
    assert len(it["options"]) == 2 and all(o[4] == 812441 for o in it["options"])
    assert "options" in _items.extras(it)
    cargo = bytes(next(w for w in reversed(s.sent) if w.proto == world.S2C_CARGO).buf)
    assert cargo.endswith(_items.option_tail(it["options"]))


def reroll_body(slot, serial, source=0, locks=()):
    from kuf2 import obf
    body = bytearray(obf.u16(slot) + obf.u64(serial) + bytes([source, 0]))
    body[0xb] = obf.T2[(2 * body[2] + (1 if locks else 0)) & 0xff]
    if locks:
        body += bytes([len(locks)]) + bytes(locks)
    return bytes(body)


def reroll_session(stones=3, cubic=100, options=None):
    from kuf2 import world
    s, st = Session(char(level=30)), State()
    c = s.data["char"]
    opts = options or [[66, 1, 0.0, 30, 812441], [67, 1, 0.0, 31, 812441]]
    c.update(spot=10001, gold=0, cubic=cubic, bag=[
        {"code": RING, "slot": 0, "count": 1, "serial": 77, "bound": False, "options": [list(o) for o in opts]}])
    if stones:
        c["bag"].append({"code": 351200010, "slot": 1, "count": stones, "serial": 78, "bound": False})
    role = world.make(st, 0, "127.0.0.1", 0)
    return s, st, role


def send(role, s, proto, body):
    from test_rewards import pkt
    role.handlers[proto](s, pkt(proto, body))
    return bytes(next(w for w in reversed(s.sent) if w.proto == proto + 1).buf)


def test_the_reroll_previews_the_unlocked_slots_and_the_apply_writes_them(monkeypatch):
    from kuf2 import world
    monkeypatch.setattr(random, "randrange", lambda n: n - 1)
    s, st, role = reroll_session()
    c = s.data["char"]
    assert _items.option_lock_cost(RING) == 24 * 3              # Random_option_init[24] 24 x HERO 3
    out = send(role, s, world.C2S_OPTION_REROLL, reroll_body(0, 77, locks=[0]))
    assert out[:2] == b"\0\0" and out[2] == 1 and out[3] == 1    # one entry: slot 1
    assert struct.unpack_from("<bBfi", out, 4) == (73, 1, 0.0, 47)
    assert c["cubic"] == 100 - 72 and not any(i["code"] == 351200010 for i in c["bag"])   # 3 stones (HERO)
    ring = c["bag"][0]
    assert ring["options"][1][3] == 31                          # nothing changes before the apply
    assert send(role, s, world.C2S_OPTION_APPLY, b"\x01")[:2] == b"\0\0"
    assert ring["options"][0][3] == 30 and ring["options"][1][:4] == [73, 1, 0.0, 47]
    assert send(role, s, world.C2S_OPTION_APPLY, b"\x01")[:2] != b"\0\0"     # nothing pending


@pytest.mark.parametrize("stones, cubic, locks", [(2, 100, []),          # HERO needs 3 stones
                                                  (3, 10, [0]),          # a lock's 72 Cubic short
                                                  (3, 999, [0, 1])])     # every option locked
def test_a_reroll_is_refused_without_its_price(stones, cubic, locks):
    from kuf2 import world
    s, st, role = reroll_session(stones=stones, cubic=cubic)
    c = s.data["char"]
    before = [list(o) for o in c["bag"][0]["options"]]
    out = send(role, s, world.C2S_OPTION_REROLL, reroll_body(0, 77, locks=locks))
    assert out[:2] != b"\0\0" and c["cubic"] == cubic and c["bag"][0]["options"] == before
    assert sum(i["count"] for i in c["bag"] if i["code"] == 351200010) == stones


def test_existing_gear_gets_its_options_once():
    c = char(level=30)
    c.update(bag=[{"code": RING, "slot": 0, "count": 1, "serial": 5, "bound": False},
                  {"code": 351200010, "slot": 1, "count": 2, "serial": 6, "bound": False}],
             warehouse=[{"code": RING, "slot": 0, "count": 1, "serial": 7, "bound": False}])
    assert _items.roll_missing_options(c, lambda n: 0) == 2
    assert len(c["bag"][0]["options"]) == 2 and "options" not in c["bag"][1]
    assert len(c["warehouse"][0]["options"]) == 2
    assert _items.roll_missing_options(c, lambda n: 0) == 0


# J5: three free resurrections a day ("You can resurrect for free 3 times a day, and the count will be reset the next
# day. The Free Resurrection count is not accumulative." texttutorial Basic_FreeRevival), shared by the hero and the
# deck troops: the tape's New Hampton (part 3 f_01166, 38:50) shows "Free Resurrection (x3)" over both fallen troops and
# "(x1)" after two were raised (f_01191). The client keeps the count at common+0x15c4 (S2C 0x1089, u16, 0x140d6ec80) and
# confirms a free one without a price; after them the Cubic price (70 the hero, the troop's by grade x rarity).

def test_the_first_three_revives_of_a_day_are_free(monkeypatch):
    from kuf2 import rules
    from test_mission_rules import dead_hero, revive_here
    monkeypatch.setattr(rules, "game_day", lambda now=None: "2026-10-01")
    s = dead_hero(10233, cubic=100)
    c = s.data["char"]
    c.pop("free_revives")                                           # (the helper spends them for the price tests)
    for n in (2, 1, 0):
        assert revive_here(s) == 0 and c["cubic"] == 100
        free = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_FREE_REVIVES]
        assert free[-1] == struct.pack("<H", n)
        s.data["battle"].troops[0]["hp"] = 0
    assert revive_here(s) == 0 and c["cubic"] == 30                 # the fourth: 70 Cubic
    monkeypatch.setattr(rules, "game_day", lambda now=None: "2026-10-02")
    s.data["battle"].troops[0]["hp"] = 0
    assert revive_here(s) == 0 and c["cubic"] == 30                 # a new day: three again
    assert game.free_revives(c) == 2


def test_the_free_count_goes_to_the_client_at_login():
    assert bytes(game.free_revives_packet({"id": 1}).buf) == struct.pack("<H", 3)

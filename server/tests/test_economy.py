"""The economy rules census (planning/rules/ECONOMY.md), build batch 2026-09-30: its CHECKABLE rows recomputed from the
tables, and the rules built from its decisions (README A11, B4, B5). Reads the game tables from the installed game.
Run: py -m pytest -q server/tests"""
import calendar
import datetime
import struct

import pytest

from kuf2 import coinshop, daily, diary, game, hero, items, mail, obf, quest, rules, tables, troops, world
from kuf2.packet import Reader

DAY = 86400


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0, "level": 30, "gold": 0, "bag": []}}
        self.data["account"] = {"id": 1, "characters": [self.data["char"]]}
        self.sent = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.data.setdefault("timers", []).append((delay, fn))


class State:
    saves = 0

    def save(self):
        self.saves += 1


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


@pytest.fixture
def role():
    st = State()
    return world.make(st, 0, "127.0.0.1", 0), st


@pytest.fixture
def troop_role():
    from kuf2.net import Role
    st = State()
    r = Role("world", 0, st)
    troops.make(r, st)
    return r, st


def call(role, s, proto, body=b""):
    role[0].handlers[proto](s, pkt(proto, body))


def last(s, proto):
    return bytes(next(w for w in reversed(s.sent) if w.proto == proto).buf)


def utc(y, mo, d, h=0, mi=0, sec=0):
    return calendar.timegm((y, mo, d, h, mi, sec))


# C5 / README A9: collected quest items leave the bag at the hand-in, per questtable Collect_Reward_Finish. The tape
# shows they go (part 8 RVJnrq3zPlo f_00459: the Quest tab "1 / 64" at Lv 15 after seven "All" hand-ins; quest items
# cannot be destroyed by the player); All = every held unit, Complete / PARTIAL = the condition's count, NONE = none
# (the count reading is inferred from the data: exchange quests over tokens are Complete / PARTIAL)

def quest_session(qid, extra=2):
    s = Session()
    c = s.data["char"]
    c.update(spot=10001, pos=[0, 0, 0])
    q = tables.by_id("questtable")[str(qid)]
    r = quest.record(c)
    r["active"][str(qid)] = {"counts": [need for _, _, need in quest.conditions(q)], "time": 0, "tracked": True}
    gains = [(int(id1), need) for kind, id1, need in quest.conditions(q) if kind == "ItemGain"]
    for code, need in gains:
        c["bag"].append({"code": code, "slot": world.bag_range(c, code)[0], "count": need + extra, "serial": code,
                         "bound": False})
    return s, gains


@pytest.mark.parametrize("qid, value, left", [
    (1150203, "All", lambda need, extra: 0),                     # Kobold Fire Powder x2
    (9900360, "Complete", lambda need, extra: extra),            # Mission Certificates x5 exchanged
    (2240038, "PARTIAL", lambda need, extra: extra),             # a daily's powder x1
    (1130407, "NONE", lambda need, extra: need + extra),         # Coliseum Silver Coins x10 kept
])
def test_collected_quest_items_leave_at_the_hand_in(qid, value, left):
    assert tables.by_id("questtable")[str(qid)]["Collect_Reward_Finish"] == value
    s, gains = quest_session(qid)
    st = State()
    assert quest.collected(tables.by_id("questtable")[str(qid)], {code: need + 2 for code, need in gains}) == \
        [(code, need + 2 - left(need, 2)) for code, need in gains if need + 2 - left(need, 2)]
    assert quest.hand_in(s, st, qid)
    for code, need in gains:
        assert sum(i["count"] for i in s.data["char"]["bag"] if i["code"] == code) == left(need, 2)


def test_collect_reward_finish_values_in_use():
    from collections import Counter
    used = Counter(r["Collect_Reward_Finish"] for r in tables.load("questtable") if r.get("Use_Quest") == "Yes")
    assert used["All"] == 764 and used["PARTIAL"] == 11 and used["Complete"] == 9 and used["NONE"] == 7
    assert set(quest.COLLECT) >= {"All", "PARTIAL", "Complete", "NONE"}


ALDRIC_LEFTOVERS = [(451000231, 2, 1150203), (451000374, 1, 1150305), (451000207, 5, 1150403),
                    (451000206, 3, 1150306), (451000371, 1, 1150803), (451000371, 1, 1150803),
                    (451000372, 1, 1150804)]


def test_login_migration_takes_finished_quests_leftover_items_once():
    c = {"id": 1, "class": 0, "bag": [], "quests": {"active": {"1150808": {"counts": [0] * 5}},
                                                     "done": sorted({q for _, _, q in ALDRIC_LEFTOVERS})}}
    for k, (code, n, _) in enumerate(ALDRIC_LEFTOVERS):
        c["bag"].append({"code": code, "slot": 0x80 + k, "count": n, "serial": 900 + k})
    kept = [{"code": 451000208, "slot": 0x8a, "count": 10, "serial": 990},     # 1150602: neither finished nor held
            {"code": 350000010, "slot": 3, "count": 4, "serial": 991}]
    c["bag"] += [dict(k) for k in kept]
    taken = quest.collect_leftovers(c)
    assert sorted(taken) == sorted([(451000231, 2), (451000374, 1), (451000207, 5), (451000206, 3), (451000371, 2),
                                    (451000372, 1)])
    assert c["bag"] == kept
    assert quest.collect_leftovers(c) == []                        # idempotent
    assert quest.LEFTOVERS_MIGRATION in c["migrations"]


def test_start_game_runs_the_save_migrations(role):
    s = Session()
    t0 = utc(2026, 10, 1)
    c = {"id": 4, "name": "A", "class": 0, "level": 20, "tutorial_done": True, "spot": world.START_SPOT,
         "pos": list(world.START_POS), "bag_slots": world.CARGO_SLOTS,
         "bag": [{"code": 451000231, "slot": 0x80, "count": 2, "serial": 5},
                 {"code": COSTUME, "slot": 0x100, "count": 1, "serial": 6},
                 {"code": COSTUME, "slot": 0x101, "count": 1, "serial": 7, "expires": 100}],   # ran out offline
         "quests": {"active": {}, "done": [1150203]}}
    s.data = {"account": {"id": 4, "characters": [c]}}
    call(role, s, world.C2S_START_GAME, struct.pack("<IB", 4, 0))
    assert [i["serial"] for i in c["bag"]] == [6] and c["bag"][0]["expires"] > t0
    assert quest.LEFTOVERS_MIGRATION in c["migrations"]
    assert not any(w.proto == world.S2C_ITEM_EXPIRED for w in s.sent)       # at login the lists carry it
    assert s.data["timers"]                                                  # the period's end is watched


def test_login_migration_keeps_an_item_an_active_quest_still_needs():
    c = {"id": 1, "class": 0, "bag": [{"code": 451000231, "slot": 0x80, "count": 2, "serial": 5}],
         "quests": {"active": {"1150203": {"counts": [0] * 5}}, "done": [1150203]}}
    assert quest.collect_leftovers(c) == [] and c["bag"][0]["count"] == 2


# A2 / B5: Cubic comes only from the original's in-game sources: CUBIC bundles (ChargeValue each) that quests, daily
# tasks and containers pay, used from the bag

def use_body(code, serial, count=1):
    return bytes(6) + obf.u32(code) + bytes(2) + obf.u64(serial) + obf.u16(count) + bytes(5)


def test_every_cubic_bundle_fills_the_balance_by_its_charge_value(role):
    bundles = [r for r in tables.load("item_consume") if r.get("ConsumeItemType") == "CUBIC"]
    assert len(bundles) > 100
    for r in bundles:
        s = Session()
        c = s.data["char"]
        code = int(r["ItemCode"])
        c.update(cubic=7, bag=[{"code": code, "slot": 0, "count": 2, "serial": 1, "bound": False}])
        call(role, s, world.C2S_USE_ITEM, use_body(code, 1, 2))
        assert c["cubic"] == 7 + 2 * int(r["ChargeValue"]), code


def test_quests_daily_tasks_and_containers_pay_cubic_bundles():
    bundles = {r["ItemCode"] for r in tables.load("item_consume") if r.get("ConsumeItemType") == "CUBIC"}
    quests = [r for r in tables.load("questtable") if r.get("Use_Quest") == "Yes"
              and any(r.get(f"Item{k}_Type") == "Normal" and r.get(f"Item{k}_ID") in bundles for k in range(1, 6))]
    assert len(quests) > 150
    assert all(any(str(code) in bundles for code, _ in quest.reward_items(q, 0)) for q in quests)
    daily_rows = [r for r in tables.sections("dailytask")["DailyTask"]
                  if any(r.get(f"Item{k}_ID") in bundles for k in range(1, 5))]
    assert daily_rows
    assert [r for r in tables.sections("item_container")["Group"] if r["ItemCode"] in bundles]


# F7 / B5: the Cubic shop, the cash shop window's Cubic tab: item_cash's COMMON goods, all Currency 2 (Cubic), listed
# by 0x3756 (0x51-byte entries, parser 0x1405a2200) and bought by 0x1128 (answered 0x1129); price = CashPrice, the same
# as item_currency Buy_Cubic_Shop[SellID] on all 80 item_cubic goods

def test_cubic_goods_are_item_cash_common_priced_as_the_cubic_table():
    from kuf2 import cubicshop
    goods = cubicshop.goods()
    cubic = {r["SellID"] for r in tables.sections("item_cubic")["Base"]}
    shop = {r["Index"]: int(r["Cubic_Count"]) for r in tables.sections("item_currency")["Base"]
            if r["ItemCurrencyType"] == "Buy_Cubic_Shop"}
    assert all(r["Currency"] == "2" and r["MainCategory"] == "COMMON" for r in goods)
    for r in goods:
        if r["SellID"] in cubic:
            assert int(r["CashPrice"]) == shop[r["SellID"]]
    ids = {r["SellID"] for r in goods}
    assert {"8111000", "8129000", "8133000", "8800700", "8801800"} <= ids          # ticket, resets, hero troops
    assert not ids & set(cubicshop.HIDDEN) and "8122000" not in ids               # item_cubic Availability False
    assert len(goods) == 97 - len(cubicshop.HIDDEN)
    assert sum(1 for r in goods if items.row(r["ItemCode"]).get("ConsumeItemType") == "TROOP_SUMMON") == 12


def test_the_cubic_tab_lists_its_goods_in_chunks(role):
    from kuf2 import cubicshop
    s = Session()
    call(role, s, cubicshop.C2S_LIST)
    lists = [bytes(w.buf) for w in s.sent if w.proto == cubicshop.S2C_LIST]
    assert len(lists) == -(-len(cubicshop.goods()) // cubicshop.CHUNK)
    n_total = 0
    for k, b in enumerate(lists):
        finalize, reset = b[0] == 0, b[1] == 0                      # obool: byte 0 is true
        assert (finalize, reset) == (k == len(lists) - 1, k == 0) and b[2] == 0
        n = struct.unpack_from("<h", b, 3)[0]
        assert len(b) == 5 + n * cubicshop.ENTRY
        n_total += n
    assert n_total == len(cubicshop.goods())
    first = cubicshop.goods()[0]
    e = lists[0][5:5 + cubicshop.ENTRY]
    assert struct.unpack_from("<i", e, 0x04)[0] == int(first["CashPrice"])
    assert e[0x17] == 1 and struct.unpack_from("<I", e, 0x18)[0] == int(first["Array"])
    assert struct.unpack_from("<i", e, 0x35)[0] == int(first["SellID"])
    assert obf.dec_u32(e[0x41:0x45]) == int(first["ItemCode"]) and struct.unpack_from("<I", e, 0x45)[0] == 2
    assert struct.unpack_from("<i", e, 0x3d)[0] == -1 and obf.dec_u16(e[0x11:0x13]) == 1


def test_a_cubic_good_is_bought_for_its_price(role):
    from kuf2 import cubicshop
    s = Session()
    c = s.data["char"]
    ticket = next(r for r in cubicshop.goods() if r["SellID"] == "8111000")        # Resurrection Ticket, 50
    c["cubic"] = 120
    call(role, s, cubicshop.C2S_BUY, bytes([2]) + struct.pack("<I", 8111000))
    assert last(s, cubicshop.S2C_BUY) == bytes(2) + bytes([2]) + struct.pack("<I", 8111000)
    assert c["cubic"] == 20 and last(s, world.S2C_CUBIC) == obf.u32(20)
    assert sum(i["count"] for i in c["bag"] if i["code"] == int(ticket["ItemCode"])) == 2
    call(role, s, cubicshop.C2S_BUY, bytes([1]) + struct.pack("<I", 8111000))
    assert last(s, cubicshop.S2C_BUY) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 20
    call(role, s, cubicshop.C2S_BUY, bytes([1]) + struct.pack("<I", 8106000))      # hidden: Guild Point Potion
    assert last(s, cubicshop.S2C_BUY) == struct.pack("<H", cubicshop.UNKNOWN_GOOD) and c["cubic"] == 20
    call(role, s, cubicshop.C2S_BUY, bytes([0]) + struct.pack("<I", 8111000))
    assert last(s, cubicshop.S2C_BUY) == struct.pack("<H", cubicshop.UNKNOWN_GOOD)


def test_a_reset_entry_ticket_clears_its_day_limit_group(role):
    s = Session()
    c = s.data["char"]
    code = 351511000                                            # [Extreme] Thunder Valley: EnterCount_Init 100
    c["bag"] = [{"code": code, "slot": 0, "count": 1, "serial": 1, "bound": True}]
    call(role, s, world.C2S_USE_ITEM, use_body(code, 1))
    assert last(s, world.S2C_USE_ITEM) == struct.pack("<H", world.ITEM_USE_REFUSED) and c["bag"][0]["count"] == 1
    rules.day_counts(c)["100"] = 1
    call(role, s, world.C2S_USE_ITEM, use_body(code, 1))
    assert rules.day_counts(c).get("100", 0) == 0 and c["bag"] == []
    assert last(s, world.S2C_USE_ITEM)[:2] == bytes(2) and last(s, rules.S2C_DAY_LIMITS)


# O12 / B5: the troop summon board (NPC menu GACHA_NORMAL, CommonSubGacha): 25 cards drawn from gacha %Group by the
# %NormalSummon_Setting rows, pushed as 0x1113; a pick of n (0x110f) costs int(CostRate x Gacha_non x n / 100000 +
# 0.5) = 136 x n Cubic (the client's 0x1405cd8a0); 3 free refreshes (0x1111), then Gacha_refresh 250 .. 4000

def test_the_board_is_drawn_from_its_setting_rows():
    from kuf2 import summon
    board = summon.draw(roll=lambda n: 0)
    assert len(board) == 25 == sum(int(r["PickCount"]) for r in tables.sections("gacha")["NormalSummon_Setting"])
    first = next(r for r in tables.sections("gacha")["Group"] if r["GroupID"] == "50")
    assert board[0] == [1, 0, int(first["ItemCount"]), False, int(first["REWARD_Item"])]
    assert all(card[0] == 1 for card in board)                    # every card an item in this build
    assert [summon.pick_cost(n) for n in (1, 5)] == [136, 680]
    assert [summon.refresh_cost(u) for u in range(9)] == [0, 0, 0, 250, 400, 900, 1950, 4000, 4000]


def test_the_board_is_pushed_at_town_entry_and_a_pick_pays_and_grants(role, monkeypatch):
    from kuf2 import summon
    monkeypatch.setattr(summon.random, "randrange", lambda n: 0)
    s = Session()
    c = s.data["char"]
    c.update(cubic=1000, spot=10001)
    call(role, s, world.C2S_ENTER_TOWN, obf.u32(10001))
    b = last(s, summon.S2C_BOARD)
    assert b[0] == 0 and b[1] == 25 and len(b) == 2 + 25 * 13
    card = c["summon_board"]["cards"][0]
    assert b[2 + 1] == 1 and obf.dec_u16(b[4:6]) == card[2] and obf.dec_u32(b[2 + 9:2 + 13]) == card[4]
    call(role, s, summon.C2S_PICK, bytes([1]) + struct.pack("<I", 2))
    out = last(s, summon.S2C_PICK)
    assert out[:3] == bytes(2) + bytes([2]) and c["cubic"] == 1000 - 272
    picked = struct.unpack_from("<2I", out, 3)
    assert all(c["summon_board"]["cards"][i][3] for i in picked)
    got = sum(i["count"] for i in c["bag"] if i["code"] == c["summon_board"]["cards"][picked[0]][4])
    assert got >= c["summon_board"]["cards"][picked[0]][2]
    call(role, s, summon.C2S_PICK, bytes([1]) + struct.pack("<I", 6))                   # more than 5
    assert last(s, summon.S2C_PICK) == struct.pack("<H", summon.CANNOT_USE)
    c["cubic"] = 100
    call(role, s, summon.C2S_PICK, bytes([1]) + struct.pack("<I", 1))
    assert last(s, summon.S2C_PICK) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 100


def test_a_pick_after_the_day_turned_sends_the_new_board_first(role):
    from kuf2 import summon
    s = Session()
    c = s.data["char"]
    c.update(cubic=500, summon_board={"day": "2000-01-01", "used": 3, "cards": [[1, 0, 1, False, 350000010]]})
    call(role, s, summon.C2S_PICK, bytes([1]) + struct.pack("<I", 1))
    protos = [w.proto for w in s.sent if w.proto in (summon.S2C_BOARD, summon.S2C_PICK)]
    assert protos == [summon.S2C_BOARD, summon.S2C_PICK] and last(s, summon.S2C_PICK)[:2] == bytes(2)
    assert c["summon_board"]["used"] == 0 and len(c["summon_board"]["cards"]) == 25 and c["cubic"] == 500 - 136


def test_three_free_refreshes_then_cubic(role):
    from kuf2 import summon
    s = Session()
    c = s.data["char"]
    c["cubic"] = 300
    for k in range(3):
        call(role, s, summon.C2S_REFRESH, bytes([obf.T1.index(1)]))
        assert [w.proto for w in s.sent[-2:]] == [summon.S2C_BOARD, summon.S2C_REFRESH]
        assert last(s, summon.S2C_REFRESH) == bytes(2) and last(s, summon.S2C_BOARD)[0] == k + 1
    assert c["cubic"] == 300
    call(role, s, summon.C2S_REFRESH, bytes([obf.T1.index(0)]))
    assert last(s, summon.S2C_REFRESH) == bytes(2) and c["cubic"] == 50                  # the fourth: 250
    call(role, s, summon.C2S_REFRESH, bytes([obf.T1.index(0)]))
    assert last(s, summon.S2C_REFRESH) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 50


# F8: the coin shop's paid refresh (0x1552): item_currency Randomshop_refresh Index 0 = 580 Cubic (the client's
# "CubicRefresh" 0x140631882 reads that row and pre-checks the balance)

def test_the_coin_shop_paid_refresh_costs_580_cubic(role):
    s = Session()
    c = s.data["char"]
    c["cubic"] = 600
    menu = 55
    before = coinshop.shop(c, menu)
    before["items"] = [[1, 1, True]]
    call(role, s, coinshop.C2S_PAID_REFRESH, struct.pack("<I", menu))
    assert last(s, coinshop.S2C_PAID_REFRESH) == bytes(2) and c["cubic"] == 20
    assert coinshop.shop(c, menu)["items"] != [[1, 1, True]]
    call(role, s, coinshop.C2S_PAID_REFRESH, struct.pack("<I", menu))
    assert last(s, coinshop.S2C_PAID_REFRESH) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 20


# A1: gold is capped at 999,999,999 on every gain (the client's cap, texts 0x1bd0 / 0x1bdf)

@pytest.mark.parametrize("have, delta, after", [
    (0, 500, 500),
    (999_999_000, 5_000, 999_999_999),
    (999_999_999, 1, 999_999_999),
    (999_999_999, -1_000, 999_998_999),         # a spend is not clamped
    (2_000, -500, 1_500),
])
def test_gold_is_capped_on_gains(have, delta, after):
    s, st = Session(), State()
    s.data["char"]["gold"] = have
    world.add_gold(s, st, delta)
    assert s.data["char"]["gold"] == after


# H10: stone removal priced by the client's grid 0x14184a630 (products); the Cubic payment accepted

def test_stone_removal_grid_is_a_product_in_gold_and_cubic():
    rows = tables.sections("item_consume_sub")["ExtractCompose"]
    num = lambda v: int(v) if str(v).isdigit() else 0
    for stone in (560010001,):                                  # RARE, ReqLevel 10
        r = items.row(stone)
        a = next(x for x in rows if x["ReqHeroLv"] == r["ReqLevel"])
        b = next(x for x in rows if x["ItemRarity"] == r["Rarity"])
        assert items.compose_cost(stone) == num(a["UseGoldCount1"]) * num(b["UseGoldCount2"]) == 1000
        assert items.compose_cubic(stone) == num(a["UseCubicCount1"]) * num(b["UseCubicCount2"]) == 1


def test_a_stone_comes_out_for_cubic(role):
    s = Session()
    c = s.data["char"]
    stone = 560010001
    main = next(e for e in hero.equipment(c) if e["index"] == 0)
    main["sockets"] = [stone]
    body = bytes([0]) + obf.u16(0) + bytes([1]) + obf.u64(main["serial"]) + bytes([1])     # payment 1: Cubic
    c["cubic"] = 0
    call(role, s, world.C2S_DISARM, body)
    assert last(s, world.S2C_DISARM) == struct.pack("<H", world.COMPOSE_REFUSED) and main["sockets"] == [stone]
    c["cubic"] = 5
    call(role, s, world.C2S_DISARM, body)
    assert last(s, world.S2C_DISARM) == bytes(2) and main["sockets"] == [-1] and c["cubic"] == 4 and c["gold"] == 0
    assert last(s, world.S2C_CUBIC) == obf.u32(4)


# O10: badge removal priced by the client's grid 0x14184a3f0 (UseGoldCount1(rarity) x UseGoldCount2(star rating), and
# the Cubic columns the same way; the confirm box 0x140653160 compares the grid's u64 with gold, its i32 with Cubic)

def test_badge_removal_grid_is_a_product_in_gold_and_cubic():
    rows = tables.sections("item_consume_sub")["ExtractBadge"]
    badges = [r for r in tables.sections("item_troop")["Base"] if r["ItemKind"] == "TROOP_ITEM"]
    num = lambda v: int(v) if str(v).isdigit() else 0
    checked = 0
    for r in badges:
        a = next((x for x in rows if x["ItemRarity"] == r["Rarity"]), None)
        b = next((x for x in rows if x["StarRating"] == r["StarRating"]), None)
        if a is None or b is None:
            continue
        code = int(r["ItemCode"])
        assert troops.badge_price(code) == num(a["UseGoldCount1"]) * num(b["UseGoldCount2"])
        assert troops.badge_cubic(code) == num(a["UseCubicCount1"]) * num(b["UseCubicCount2"])
        checked += 1
    assert checked > 200


def test_a_badge_comes_off_for_cubic(troop_role):
    s = Session()
    c = s.data["char"]
    badge = int(next(r["ItemCode"] for r in tables.sections("item_troop")["Base"] if r["ItemKind"] == "TROOP_ITEM"))
    t, _ = troops.grant(c, 1)
    t["badges"] = [{"slot": 0, "code": badge, "serial": 95, "bound": True, "enchant": 0}]
    price = troops.badge_cubic(badge)
    c["cubic"] = price - 1
    call(troop_role, s, troops.C2S_BADGE_OFF, struct.pack("<QHB", t["uid"], 0, 1))
    assert last(s, troops.S2C_BADGE_OFF) == struct.pack("<H", 0x6430) and t["badges"]
    c["cubic"] = price + 7
    call(troop_role, s, troops.C2S_BADGE_OFF, struct.pack("<QHB", t["uid"], 0, 1))
    assert last(s, troops.S2C_BADGE_OFF) == bytes(2) and t["badges"] == [] and c["cubic"] == 7 and c["gold"] == 0
    assert c["bag"][0]["serial"] == 95


# O8: the academy's Cubic level-ups (item_currency TroopSkill_Levelup rows whose CurrencyType is Cubic)

def test_an_academy_level_priced_in_cubic_takes_cubic(troop_role):
    s = Session()
    c = s.data["char"]
    ability = 81062                              # AbilityMinLevel 0; level 1 is priced Cubic 6 (CostGroup -> Index 15)
    assert troops.tactics_price(ability, 1) == ("Cubic", 6)
    c.update(cubic=5, gold=10**6)
    call(troop_role, s, troops.C2S_TACTICS_UP, obf.u32(ability))
    assert last(s, troops.S2C_TACTICS_UP) == struct.pack("<H", 0x6430) and troops.skill_level(c, ability) == 0
    c["cubic"] = 10
    call(troop_role, s, troops.C2S_TACTICS_UP, obf.u32(ability))
    assert last(s, troops.S2C_TACTICS_UP) == bytes(2) + obf.u32(ability) + bytes([1])
    assert troops.skill_level(c, ability) == 1 and c["cubic"] == 4 and c["gold"] == 10**6


# L6 / E7 (a): the original's day boundaries: dailies, repeat quests, item day limits, coin shop at 07:00 UTC;
# attendance at 00:00 UTC

@pytest.mark.parametrize("now, game, attendance", [
    (utc(2026, 9, 30, 6, 59, 59), "2026-09-29", "2026-09-30"),
    (utc(2026, 9, 30, 7, 0, 0), "2026-09-30", "2026-09-30"),
    (utc(2026, 9, 30, 23, 59, 59), "2026-09-30", "2026-09-30"),
    (utc(2026, 10, 1, 0, 0, 0), "2026-09-30", "2026-10-01"),
])
def test_day_boundaries(now, game, attendance):
    assert rules.game_day(now) == game
    assert rules.attendance_day(now).isoformat() == attendance
    assert diary.today(now).isoformat() == attendance


def test_daily_tasks_roll_again_at_seven_utc():
    c = {"level": 30}
    first = daily.record(c, now=utc(2026, 9, 30, 6, 0))
    assert first["date"] == "2026-09-29"
    first["tasks"] = [{"id": -1, "progress": 0, "state": daily.OPEN}]         # marked: the same list stays
    assert daily.record(c, now=utc(2026, 9, 30, 6, 59))["tasks"][0]["id"] == -1
    assert daily.record(c, now=utc(2026, 9, 30, 7, 0))["date"] == "2026-09-30"


def test_item_day_uses_and_the_coin_shop_turn_at_seven_utc():
    c = {}
    world.day_uses(c, now=utc(2026, 9, 30, 6, 0))[123] = 2
    assert world.day_uses(c, now=utc(2026, 9, 30, 6, 59)) == {123: 2}
    assert world.day_uses(c, now=utc(2026, 9, 30, 7, 0)) == {}
    menu = next(iter(coinshop.MENUS))
    sh = coinshop.shop(c, menu, now=utc(2026, 9, 30, 6, 0))
    assert sh["day"] == "2026-09-29" and coinshop.shop(c, menu, now=utc(2026, 9, 30, 6, 59)) is sh
    assert coinshop.shop(c, menu, now=utc(2026, 9, 30, 7, 0))["day"] == "2026-09-30"


def test_repeat_quests_reopen_on_the_game_day():
    rows = tables.load("questtable")
    day = next(int(r["ID"]) for r in rows if r.get("Retry_Type") == "Day" and r.get("Use_Quest") == "Yes")
    assert rules.game_day(utc(2026, 9, 30, 6, 0)) == "2026-09-29"       # a hand-in at 06:00 UTC counts for 09-29
    r = {"active": {}, "done": [day], "handed": {str(day): "2026-09-29"}}
    assert quest.reopen(r, now=utc(2026, 9, 30, 6, 59)) == [] and r["done"] == [day]
    assert quest.reopen(r, now=utc(2026, 9, 30, 7, 0)) == [day] and r["done"] == []


# N1: system mail expires after 28 days (textui 7509 "After 28 days, which is the expiration date, the mail will be
# automatically deleted.")

def test_mail_older_than_28_days_is_deleted():
    s, st = Session(), State()
    c = s.data["char"]
    mail.deliver(None, st, c, "old", "x", gold=10, grant=[(350000010, 1)])
    mail.deliver(None, st, c, "new", "y")
    now = c["mail"][0]["sent"] + 28 * DAY
    c["mail"][0]["sent"] -= 1                                  # 28 days and a second
    old = c["mail"][0]["id"]
    assert mail.expire(c, now) == [old]
    assert [m["title"] for m in c["mail"]] == ["new"]
    assert mail.expire(c, now) == []


def test_the_mail_list_drops_expired_mail(role):
    s = Session()
    c = s.data["char"]
    mail.deliver(None, role[1], c, "old", "x")
    c["mail"][0]["sent"] -= mail.KEEP_DAYS * DAY + 1
    call(role, s, mail.C2S_LIST, bytes([0]))
    assert last(s, mail.S2C_LIST) == bytes([0]) + struct.pack("<H", 0) and c["mail"] == []


# H13 / B4: timed costumes expire as the original: ValidDate minutes from the gain, the record's head 0x09 = seconds
# left (the client counts down from it, 0x140d66ad0), 0x1075 when it runs out (worn: undressed)

COSTUME = 950000640                                     # LOOK_UPPER, REAL_TIME, ValidDate 43200 (30 days)


def test_a_timed_costume_carries_its_seconds_left():
    assert items.valid_seconds(COSTUME) == 43200 * 60
    assert items.valid_seconds(101001300) == 0                  # a weapon: PERMANENT
    rec = items.record(COSTUME, 0x100, 5, expiry=2_592_000)
    assert struct.unpack_from("<i", rec, 0x09)[0] == 2_592_000
    assert struct.unpack_from("<i", items.record(COSTUME, 0x100, 5), 0x09)[0] == 0


def test_a_timed_costume_is_stamped_at_gain_and_removed_at_expiry(role):
    s = Session()
    c = s.data["char"]
    t0 = utc(2026, 9, 30, 12)
    world.add_item(s, role[1], COSTUME, 1, now=t0)
    it = next(i for i in c["bag"] if i["code"] == COSTUME)
    assert it["expires"] == t0 + 30 * DAY
    assert items.seconds_left(it, t0 + DAY) == 29 * DAY
    s.sent.clear()
    assert world.expire_items(s, role[1], now=t0 + 30 * DAY - 1) == []
    gone = world.expire_items(s, role[1], now=t0 + 31 * DAY)
    assert gone == [COSTUME] and not any(i["code"] == COSTUME for i in c["bag"])
    assert last(s, world.S2C_ITEM_EXPIRED) == obf.u16(it["slot"]) + bytes([1])
    assert s.sent[-1].proto == world.S2C_CARGO


def test_a_worn_timed_costume_is_undressed_at_expiry(role):
    s = Session()
    c = s.data["char"]
    eq = hero.equipment(c)
    t0 = utc(2026, 9, 30, 12)
    eq.append({"code": COSTUME, "index": 13, "serial": 4242, "expires": t0 + 10})
    gone = world.expire_items(s, role[1], now=t0 + 10)
    assert gone == [COSTUME] and not any(e["code"] == COSTUME for e in eq)
    assert last(s, world.S2C_ITEM_EXPIRED) == obf.u16(13) + bytes([0])


def test_timed_items_from_before_start_their_clock_at_login():
    c = {"bag": [{"code": COSTUME, "slot": 0x100, "count": 1, "serial": 7}], "warehouse": [], "equip": []}
    t0 = utc(2026, 10, 1)
    assert world.stamp_timed(c, t0) == 1 and c["bag"][0]["expires"] == t0 + 30 * DAY
    assert world.stamp_timed(c, t0 + 5) == 0 and c["bag"][0]["expires"] == t0 + 30 * DAY    # once


def test_the_expiry_timer_is_armed_for_the_first_timed_item(role):
    s = Session()
    t0 = utc(2026, 9, 30, 12)
    world.add_item(s, role[1], COSTUME, 1, now=t0)
    world.arm_expiry(s, role[1], now=t0)
    delay, fn = s.data["timers"][-1]
    assert delay == pytest.approx(30 * DAY + 1)


# B10 / D6 / P8 (README A11): base rates, events off: kill gold is its table's Min..Max with no multiplier; quest gold
# and exp are the columns; no leadership rate is applied

def test_kill_gold_is_the_tables_range_with_no_boost():
    rows = [r for r in tables.sections("item_drop_money")["Troop"] if r["DropGold_Max"].isdigit()]
    assert len(rows) > 1500
    for r in rows:
        lo, hi = int(r["DropGold_Min"]), int(r["DropGold_Max"])
        assert game.roll_gold(int(r["NPTroopID"]), roll=lambda n: n - 1) == hi
        assert game.roll_gold(int(r["NPTroopID"]), roll=lambda n: 0) == lo

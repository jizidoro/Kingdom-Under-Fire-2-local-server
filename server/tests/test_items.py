"""The Cubic services (planning/wiring/ITEMS-WIRING.md batch 2: I2-I6) and the UI rows U4 / U3 / U23 / the barracks
expansion of planning/wiring/UI-WIRING.md. Reads the game tables from the installed game.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import hero, items, obf, troops, world
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE, Reader

WEAPON_A, WEAPON_B = 101001300, 101001400      # GLEN main weapons, ReqLevel 29, NORMAL / MAGIC (max +10)
BOUND_WEAPON = 101001500                        # ReqLevel 29 RARE, BIND_EQUIP_TIME: unbind 29 x 2 x 2 = 116 Cubic
STONE = 550000100                               # the enchant stone (and the transfer's material)


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0, "level": 30, "gold": 0, "bag": []}}
        self.data["account"] = {"id": 1, "characters": [self.data["char"]]}
        self.sent = []

    def send(self, w):
        self.sent.append(w)


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


def call(role, s, proto, body=b""):
    role[0].handlers[proto](s, pkt(proto, body))


def last(s, proto):
    return bytes(next(w for w in reversed(s.sent) if w.proto == proto).buf)


def test_cubic_is_spent_once_and_the_balance_is_pushed():
    s, st = Session(), State()
    s.data["char"]["cubic"] = 100
    assert world.spend_cubic(s, st, 60) and not world.spend_cubic(s, st, 60)
    assert s.data["char"]["cubic"] == 40
    assert [bytes(w.buf) for w in s.sent if w.proto == world.S2C_CUBIC] == [obf.u32(40)]


def test_expansions_are_priced_by_open_slots_as_the_client_walks_them():
    assert [items.expansion("inven", n) for n in (32, 48, 56, 64)] == [(50, 8), (250, 8), (750, 8), (1200, 8)]
    assert items.expansion("inven", 128) is None
    assert [items.expansion("warehouse", n) for n in (16, 24, 56, 64)] == [(50, 8), (100, 8), (2500, 8), None]
    assert [items.expansion("barrack", n) for n in (24, 27, 57, 60)] == [(25, 3), (110, 3), (1000, 3), None]


def test_bag_expansion_spends_cubic_and_opens_slots(role):
    s = Session()
    c = s.data["char"]
    c.update(cubic=300, bag=[{"code": 350000010, "slot": k, "count": 1, "serial": 100 + k, "bound": False}
                             for k in range(world.CARGO_SLOTS)])
    assert world.add_item(s, role[1], 100000113, 1, mail=False) == 1          # full at the client's 32
    call(role, s, world.C2S_BAG_EXPAND)
    assert last(s, world.S2C_BAG_EXPAND) == bytes(2) and c["cubic"] == 250 and c["bag_slots"] == 40   # Index 1: 50
    assert struct.unpack_from("<h", last(s, world.S2C_CARGO), 5)[0] == 40
    assert last(s, world.S2C_CUBIC) == obf.u32(250)
    assert world.add_item(s, role[1], 100000113, 1, mail=False) == 0          # into slot 32 now
    assert next(i for i in c["bag"] if i["code"] == 100000113)["slot"] == 32
    call(role, s, world.C2S_BAG_EXPAND)
    assert last(s, world.S2C_BAG_EXPAND) == bytes(2) and c["cubic"] == 150 and c["bag_slots"] == 48   # Index 2: 100
    call(role, s, world.C2S_BAG_EXPAND)
    assert last(s, world.S2C_BAG_EXPAND) == struct.pack("<H", world.CUBIC_SHORT) and c["bag_slots"] == 48  # 150 < 250
    c.update(bag_slots=64, cubic=5000)
    call(role, s, world.C2S_BAG_EXPAND)
    assert last(s, world.S2C_BAG_EXPAND) == bytes([1, 0]) and c["cubic"] == 5000     # the window's 0x40 limit


def test_warehouse_expansion_spends_cubic_and_opens_slots(role):
    s = Session()
    c = s.data["char"]
    c.update(cubic=100, bag=[{"code": 350000010, "slot": 0, "count": 5, "serial": 11, "bound": False}])
    move = obf.u64(11) + obf.u16(20) + obf.u64(0) + obf.u16(1) + obf.u16(0)
    call(role, s, world.C2S_BAG_TO_WAREHOUSE, move)
    assert last(s, world.S2C_BAG_TO_WAREHOUSE) == struct.pack("<H", world.WAREHOUSE_REFUSED)     # slot 20 of 16
    call(role, s, world.C2S_WAREHOUSE_EXPAND)
    assert last(s, world.S2C_WAREHOUSE_EXPAND) == bytes(2) and c["cubic"] == 50
    assert struct.unpack_from("<h", last(s, world.S2C_WAREHOUSE_LIST), 1)[0] == 24
    call(role, s, world.C2S_WAREHOUSE_EXPAND)
    assert last(s, world.S2C_WAREHOUSE_EXPAND) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 50
    call(role, s, world.C2S_BAG_TO_WAREHOUSE, move)
    assert last(s, world.S2C_BAG_TO_WAREHOUSE) == bytes(2) and c["warehouse"][0]["slot"] == 20


def test_barracks_expansion_spends_cubic_and_raises_the_cap(role):
    s = Session()
    c = s.data["char"]
    c["cubic"] = 30
    call(role, s, troops.C2S_EXPAND)
    assert last(s, troops.S2C_EXPAND) == bytes(2) and c["barrack_cap"] == 27 and c["cubic"] == 5
    assert last(s, troops.S2C_CAPACITY) == bytes([27]) + bytes(8)
    call(role, s, troops.C2S_EXPAND)
    assert last(s, troops.S2C_EXPAND) == struct.pack("<H", world.CUBIC_SHORT) and c["barrack_cap"] == 27
    c.update(barrack_cap=60, cubic=10000)
    call(role, s, troops.C2S_EXPAND)
    assert last(s, troops.S2C_EXPAND) == bytes([1, 0]) and c["cubic"] == 10000


def test_unbinding_a_bound_bag_item_costs_its_grid_price(role):
    s = Session()
    c = s.data["char"]
    c.update(cubic=200, bag=[{"code": BOUND_WEAPON, "slot": 3, "count": 1, "serial": 31, "bound": True},
                             {"code": 109900100, "slot": 4, "count": 1, "serial": 32, "bound": True}])  # GAIN_TIME
    assert items.unbind_cost(BOUND_WEAPON) == 116
    call(role, s, world.C2S_UNBIND, struct.pack("<HI", 4, 109900100))
    assert last(s, world.S2C_UNBIND) == bytes([1, 0]) and c["cubic"] == 200
    call(role, s, world.C2S_UNBIND, struct.pack("<HI", 3, BOUND_WEAPON))
    assert last(s, world.S2C_UNBIND) == bytes(2) and c["cubic"] == 84 and c["bag"][0]["bound"] is False
    rec = next(r for r in s.sent if r.proto == world.S2C_CARGO).buf
    assert bytes(rec)[9] == OBOOL_FALSE                                 # the first record's bound flag
    call(role, s, world.C2S_UNBIND, struct.pack("<HI", 3, BOUND_WEAPON))
    assert last(s, world.S2C_UNBIND) == bytes([1, 0])                   # not bound any more
    c["bag"][0]["bound"], c["cubic"] = True, 100
    call(role, s, world.C2S_UNBIND, struct.pack("<HI", 3, BOUND_WEAPON))
    assert last(s, world.S2C_UNBIND) == struct.pack("<H", world.CUBIC_SHORT) and c["bag"][0]["bound"] is True


def transfer_body(to_slot, to_serial, from_slot, from_serial, material=STONE, to_worn=0, from_worn=0):
    return (bytes([to_worn]) + struct.pack("<HQ", to_slot, to_serial) + struct.pack("<HI", from_slot, material)
            + bytes([from_worn]) + struct.pack("<Q", from_serial))


def test_enchant_transfer_moves_the_level_for_cubic_and_stones(role):
    s = Session()
    c = s.data["char"]
    c.update(cubic=400, bag=[{"code": WEAPON_A, "slot": 1, "count": 1, "serial": 41, "bound": False, "enchant": 5},
                             {"code": WEAPON_B, "slot": 2, "count": 1, "serial": 42, "bound": False},
                             {"code": STONE, "slot": 3, "count": 25, "serial": 43, "bound": False}])
    rule = items.enchant_transfer(WEAPON_A, 5, WEAPON_B)
    assert (rule["cubic"], rule["material"], rule["count"]) == (384, STONE, 25)
    c["cubic"] = 383
    call(role, s, world.C2S_ENCHANT_TRANSFER, transfer_body(2, 42, 1, 41))
    assert last(s, world.S2C_ENCHANT_TRANSFER) == struct.pack("<H", world.CUBIC_SHORT)
    assert c["bag"][0]["enchant"] == 5 and c["bag"][2]["count"] == 25
    c["cubic"] = 400
    call(role, s, world.C2S_ENCHANT_TRANSFER, transfer_body(2, 42, 1, 41))
    assert last(s, world.S2C_ENCHANT_TRANSFER) == bytes([0, 0, OBOOL_TRUE])
    bag = {i["serial"]: i for i in c["bag"]}
    assert bag[42]["enchant"] == 5 and bag[41]["enchant"] == 0 and 43 not in bag and c["cubic"] == 16
    assert s.sent[-2].proto == world.S2C_CARGO                          # the bag, then the reply


def test_enchant_transfer_is_refused_past_five_levels_apart_and_onto_worn_gear_refreshes_the_hero(role):
    s = Session()
    c = s.data["char"]
    far = 101001000                                                     # ReqLevel 23: 6 levels from 29
    c.update(cubic=1000, bag=[{"code": far, "slot": 1, "count": 1, "serial": 51, "bound": False, "enchant": 3},
                              {"code": WEAPON_A, "slot": 2, "count": 1, "serial": 52, "bound": False, "enchant": 3},
                              {"code": STONE, "slot": 3, "count": 30, "serial": 53, "bound": False}])
    main = next(e for e in hero.equipment(c) if e["index"] == 0)
    main.update(code=WEAPON_B, enchant=0)
    call(role, s, world.C2S_ENCHANT_TRANSFER, transfer_body(0, main["serial"], 1, 51, to_worn=1))
    assert last(s, world.S2C_ENCHANT_TRANSFER) == struct.pack("<H", world.TRANSFER_REFUSED) and c["cubic"] == 1000
    s.sent.clear()
    call(role, s, world.C2S_ENCHANT_TRANSFER, transfer_body(0, main["serial"], 2, 52, to_worn=1))
    assert last(s, world.S2C_ENCHANT_TRANSFER) == bytes([0, 0, OBOOL_TRUE]) and main["enchant"] == 3
    assert c["cubic"] == 1000 - 48 and any(w.proto == world.S2C_HERO_DETAIL for w in s.sent)


def enchant_body(add, slot, serial, material=STONE):
    return bytes([add]) + obf.u16(slot) + obf.u32(material) + obf.u64(serial) + bytes([0])


def test_enchant_add_types_cost_cubic_at_their_steps_and_change_the_roll(role, monkeypatch):
    s = Session()
    c = s.data["char"]
    rule = items.enchant_rule(WEAPON_A, 5)                              # +5: 400 up, 300 stay, 300 down to +4
    c.update(cubic=1000, gold=10 ** 6, bag=[
        {"code": WEAPON_A, "slot": 1, "count": 1, "serial": 61, "bound": False, "enchant": 5},
        {"code": STONE, "slot": 2, "count": 50, "serial": 62, "bound": False}])
    assert items.enchant_add_cost(WEAPON_A, 5, 2) == 16 * 1 * 30 and items.enchant_add_cost(WEAPON_A, 5, 1) == 0
    monkeypatch.setattr(world.random, "randrange", lambda n: n - 1)    # the last outcome: Fail2, down to +4
    call(role, s, world.C2S_ENCHANT, enchant_body(2, 1, 61))
    assert last(s, world.S2C_ENCHANT) == struct.pack("<HhB", 0, 5, world.ENCHANT_STAY)
    assert c["bag"][0]["enchant"] == 5 and c["cubic"] == 1000 - 480 and c["gold"] == 10 ** 6 - rule["cost"]
    call(role, s, world.C2S_ENCHANT, enchant_body(1, 1, 61))            # success-up is not offered at +5
    assert last(s, world.S2C_ENCHANT) == struct.pack("<H", world.ENCHANT_CASH) and c["cubic"] == 520
    c["bag"][0]["enchant"] = 2
    call(role, s, world.C2S_ENCHANT, enchant_body(2, 1, 61))            # nor prevent-down at +2
    assert last(s, world.S2C_ENCHANT) == struct.pack("<H", world.ENCHANT_CASH) and c["cubic"] == 520
    c["bag"][0]["enchant"] = 5
    call(role, s, world.C2S_ENCHANT, enchant_body(0, 1, 61))            # without it the fall happens
    assert last(s, world.S2C_ENCHANT) == struct.pack("<HhB", 0, 4, 2) and c["cubic"] == 520


def test_success_up_adds_the_lucky_stone_weight(role, monkeypatch):
    s = Session()
    c = s.data["char"]
    code = 103000100                                                    # ReqLevel 30, max +15; +10: 100 up of 1000
    c.update(cubic=1280, gold=10 ** 6, bag=[
        {"code": code, "slot": 1, "count": 1, "serial": 71, "bound": False, "enchant": 10},
        {"code": STONE, "slot": 2, "count": 50, "serial": 72, "bound": False}])
    assert items.lucky_bonus() == 150 and items.enchant_add_cost(code, 10, 1) == 1280
    monkeypatch.setattr(world.random, "randrange", lambda n: 200)      # past 100: a failure without the stone
    call(role, s, world.C2S_ENCHANT, enchant_body(1, 1, 71))
    assert last(s, world.S2C_ENCHANT) == struct.pack("<HhB", 0, 11, 0) and c["cubic"] == 0
    call(role, s, world.C2S_ENCHANT, enchant_body(1, 1, 71))            # no Cubic left
    assert last(s, world.S2C_ENCHANT) == struct.pack("<H", world.ENCHANT_CASH)


def test_quick_bar_expansion_spends_cubic_and_comes_back_at_login(role):
    s = Session()
    c = s.data["char"]
    c["cubic"] = 299
    call(role, s, world.C2S_QUICK_BAR_EXPAND, bytes([4, 2]))
    assert last(s, world.S2C_QUICK_BAR_EXPAND) == struct.pack("<H", world.CUBIC_SHORT)
    c["cubic"] = 800
    call(role, s, world.C2S_QUICK_BAR_EXPAND, bytes([4, 2]))
    assert last(s, world.S2C_QUICK_BAR_EXPAND) == bytes([0, 0, 5, 0]) and c["cubic"] == 500
    assert last(s, world.S2C_CUBIC) == obf.u32(500)
    call(role, s, world.C2S_QUICK_BAR_EXPAND, bytes([5, 2]))
    assert last(s, world.S2C_QUICK_BAR_EXPAND) == bytes([0, 0, 6, 0]) and c["cubic"] == 0
    c["cubic"] = 5000
    call(role, s, world.C2S_QUICK_BAR_EXPAND, bytes([6, 2]))
    assert last(s, world.S2C_QUICK_BAR_EXPAND) == bytes([1, 0]) and c["cubic"] == 5000
    s.sent.clear()
    call(role, s, world.C2S_QUICK_SLOT_PAGE, bytes([0]))               # a relog: the count rides the first page
    assert [w.proto for w in s.sent] == [world.S2C_QUICK_BAR_EXPAND, world.S2C_COOLDOWNS, world.S2C_QUICK_SLOT_PAGE]
    assert bytes(s.sent[0].buf) == bytes([0, 0, 6, 0])


def test_cooldowns_and_day_uses_survive_a_relog(role, monkeypatch):
    from types import SimpleNamespace
    from kuf2 import combat
    clock = [1_800_000_000.0]
    monkeypatch.setattr(world.time, "time", lambda: clock[0])
    s = Session()
    c = s.data["char"]
    room = Session()
    room.data["battle"] = combat.Battle()
    room.data["battle"].add_hero(0, 1000)
    room.w = SimpleNamespace(is_closing=lambda: False)
    room.later = lambda *args: None
    role[1].game_sessions = {1: room}
    c["bag"] = [{"code": 350000010, "slot": 0, "count": 5, "serial": 81, "bound": False},     # HP potion, group 1, 30 s
                {"code": 358270000, "slot": 1, "count": 5, "serial": 82, "bound": False}]     # Cubic bundle, 3 a day
    use = lambda code, serial: call(role, s, world.C2S_USE_ITEM,
                                    bytes(6) + obf.u32(code) + bytes(2) + obf.u64(serial) + obf.u16(1) + bytes(5))
    use(350000010, 81)
    clock[0] += 10
    call(role, s, world.C2S_QUICK_SLOT_PAGE, bytes([0]))
    assert last(s, world.S2C_COOLDOWNS) == struct.pack("<H", 1) + obf.u32(350000010) + struct.pack("<i", 20) + bytes(2)
    for _ in range(3):
        clock[0] += 1  # Cubic bundles also share a one-second cooldown.
        use(358270000, 82)
    assert last(s, world.S2C_USE_ITEM)[:2] == bytes(2) and c["bag"][1]["count"] == 2
    clock[0] += 1  # This refusal must be the daily quota, not the one-second cooldown.
    use(358270000, 82)
    assert last(s, world.S2C_USE_ITEM) == struct.pack("<H", world.ITEM_USE_REFUSED) and c["bag"][1]["count"] == 2
    s.data.pop("cooldowns_sent")                                        # the next session
    call(role, s, world.C2S_QUICK_SLOT_PAGE, bytes([0]))
    out = last(s, world.S2C_COOLDOWNS)
    n = struct.unpack_from("<H", out)[0]
    assert out[2 + 8 * n:] == bytes(2)  # NumberOfUse, not DayLimit: native +0x268 on this item is zero.
    assert c["day_uses"]["counts"]["358270000"] == 3
    clock[0] += 86400
    assert bytes(world.cooldown_packet(c).buf) == bytes(4)             # the next day: nothing running, nothing used


def test_the_character_list_shows_worn_gear_and_costumes():
    c = {"id": 7, "class": 0, "level": 30, "name": "Glen", "look": bytes(0x38).hex()}
    hero.equipment(c).append({"code": 950009600, "index": 11, "serial": (7 << 32) | 0x10001, "bound": False})
    w = world.Writer(world.S2C_CHAR_LIST)
    world.write_char_entry(w, c)
    out = bytes(w.buf)
    tail = out[0x58 + len("Glen") + 2:]
    worn = world.equipped_items(c)
    assert tail == bytes([len(worn)]) + b"".join(worn) and len(worn) == len(c["equip"]) > 1
    assert 11 in {items.decode_head(r)[1] for r in worn}


# planning/client/items_troops_skills.md, the gaps a test can hold: 0x1543 per 0x1542 (Gap 6), the moves' lists
# (Gap 8), a stack of containers (Gap 9), 0x136a's detail (Gap 12)
POTION, BOX = 350000010, 602001403              # SellPrice 8; the gift box: 351100030 x1 + 605002205 x1, both sure


def sell_results(s):
    return [bytes(w.buf) for w in s.sent if w.proto == world.S2C_STORE_SELL]


def test_every_sale_is_answered_with_one_seven_byte_result_in_town_on_a_refusal_and_in_a_room(role):
    s = Session()
    c = s.data["char"]
    c.update(gold=10, bag=[{"code": POTION, "slot": 2, "count": 5, "serial": 21, "bound": False}])
    sell = obf.u16(3) + obf.u16(2) + obf.u64(21)
    call(role, s, world.C2S_STORE_SELL, sell)
    assert sell_results(s) == [obf.u40(34) + bytes(2)]
    call(role, s, world.C2S_STORE_SELL, sell)                       # only 2 left: refused, still one result
    assert len(sell_results(s)) == 2 and sell_results(s)[-1][:5] == obf.u40(34)
    assert len(sell_results(s)[-1]) == 7 and sell_results(s)[-1][5:] != bytes(2)   # non-zero: text 7090
    assert [w.proto for w in s.sent[-2:]] == [world.S2C_STORE_SELL, world.S2C_CARGO]
    s.data["battle_spot"] = 10233                                    # in a battle room (live world_20260927_183336:227)
    call(role, s, world.C2S_STORE_SELL, obf.u16(2) + obf.u16(2) + obf.u64(21))
    assert sell_results(s)[-1] == obf.u40(50) + bytes(2) and len(sell_results(s)) == 3 and c["bag"] == []


def test_a_stack_of_containers_opens_the_count_the_dialog_chose(role):
    s = Session()
    c = s.data["char"]
    c["bag"] = [{"code": BOX, "slot": 2, "count": 5, "serial": 41, "bound": True}]
    call(role, s, world.C2S_OPEN_CONTAINER, obf.u64(41) + obf.u16(3) + bytes([1]) + obf.u16(2))
    b = last(s, world.S2C_OPEN_CONTAINER)
    assert b[:2] == bytes(2) and struct.unpack_from("<H", b, 7)[0] == 2
    shown = sorted((obf.dec_u32(b[11 + 8 * i:15 + 8 * i]), obf.dec_u16(b[9 + 8 * i:11 + 8 * i])) for i in range(2))
    assert shown == [(351100030, 3), (605002205, 3)]
    call(role, s, world.C2S_TAKE_CONTAINER, obf.u64(41) + obf.u16(3) + bytes([1]) + obf.u16(2) + bytes(2))
    assert last(s, world.S2C_TAKE_CONTAINER) == bytes(2)
    held = {i["code"]: i["count"] for i in c["bag"]}
    assert held == {BOX: 2, 351100030: 3, 605002205: 3}
    call(role, s, world.C2S_OPEN_CONTAINER, obf.u64(41) + obf.u16(9) + bytes([1]) + obf.u16(2))   # 9 of 2: both
    call(role, s, world.C2S_TAKE_CONTAINER, obf.u64(41) + obf.u16(9) + bytes([1]) + obf.u16(2) + bytes(2))
    assert {i["code"]: i["count"] for i in c["bag"]} == {351100030: 5, 605002205: 5}


def test_bag_and_warehouse_moves_resend_their_list(role):
    s = Session()
    c = s.data["char"]
    c.update(bag=[{"code": POTION, "slot": 0, "count": 5, "serial": 11, "bound": False}],
             warehouse=[{"code": POTION, "slot": 3, "count": 2, "serial": 12, "bound": False}])
    call(role, s, world.C2S_BAG_MOVE, obf.u16(0) + obf.u16(7) + obf.u64(11) + obf.u64(0))
    assert last(s, world.S2C_BAG_MOVE) == bytes(2) and s.sent[-1].proto == world.S2C_CARGO    # 0x1647 moves nothing
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf), 7)[0] == 1
    call(role, s, world.C2S_WAREHOUSE_MOVE, obf.u16(3) + obf.u16(9) + obf.u64(12) + obf.u64(0))
    assert last(s, world.S2C_WAREHOUSE_MOVE) == bytes(2) and s.sent[-1].proto == world.S2C_WAREHOUSE_LIST
    assert c["warehouse"][0]["slot"] == 9


def test_unequipping_a_troop_skill_resends_the_troop_detail_without_it(role):
    from kuf2 import tables
    s = Session()
    c = s.data["char"]
    t, _ = troops.grant(c, 1)
    t["id"] = 1100113                                               # RARITY3 permits the second group's SkillGrade3
    group = {g["SkillGroupID"]: g for g in tables.sections("trooptable")["SkillGroup"]}
    first, second = int(group["11001111"]["SkillId_1"]), int(group["11001112"]["SkillId_1"])
    c["tactics"] = {str(second): {"level": 1, "exp": 0}}             # 70146 is AbilityMinLevel 0: learned first
    for ability in (first, second):
        call(role, s, troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], ability))
    call(role, s, troops.C2S_DETAIL, struct.pack("<Q", t["uid"]))
    out = last(s, troops.S2C_DETAIL)                                # i16, u64 uid, u8 n, n * (u8 slot, u8 level, u32)
    assert out[10] == 2 and sorted(struct.unpack_from("<BBI", out, 11 + 6 * i) for i in range(2)) == [
        (0, 1, first), (1, 1, second)]
    s.sent.clear()
    call(role, s, troops.C2S_UNEQUIP_SKILL, struct.pack("<QI", t["uid"], first))
    assert [w.proto for w in s.sent] == [troops.S2C_DETAIL]         # no 0x136b: the detail clears the client's slots
    out = bytes(s.sent[0].buf)
    assert out[:2] == bytes(2) and struct.unpack_from("<Q", out, 2)[0] == t["uid"]
    assert out[10] == 1 and struct.unpack_from("<BBI", out, 11) == (1, 1, second)


def test_a_new_character_opens_the_clients_32_bag_slots_and_an_older_save_keeps_its_48():
    # owner 2026-09-30: "there is the mechanism to extend the inventory size": the bag opens the client's own base
    # (0x14188db50: 32) and grows by the Cubic expansions (Expand_inven 50 / 100 / 250 / 750 / 1,200 for 8 each); saves
    # from when 48 opened (ITEMS-WIRING D3 (a)) keep 48, as two expansions bought, so no item sits in a shut slot
    assert world.CARGO_SLOTS == 32
    new = {"id": 3, "class": 3, "level": 1, "bag_slots": world.CARGO_SLOTS}      # as char_create writes it
    old = {"id": 2, "class": 3, "level": 6, "bag": [{"code": 350000010, "slot": 47, "count": 1, "serial": 9}]}
    assert world.keep_old_bag(new) is False and world.bag_slots(new) == 32
    assert world.keep_old_bag(old) is True and world.bag_slots(old) == 48
    assert world.keep_old_bag(old) is False                                         # once
    assert items.expansion("inven", 32) == (50, 8) and items.expansion("inven", 48) == (250, 8)

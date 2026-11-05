"""Original table/client gates: real handlers, rejected requests spend nothing, save/reload preserves limits.

Evidence and remaining unknowns: planning/quality/VANILLA-ITEMS.md. These tests do not prove unknown enchant odds.
"""
from copy import deepcopy
import json
import struct
from types import SimpleNamespace

import pytest

from kuf2 import combat, game, hero, items, obf, quest, rules, tables, world
from kuf2.packet import Reader


class Session:
    def __init__(self, c):
        self.data = {"char": c, "account": {"id": 7, "characters": [c]}}
        self.sent = []
        self.w = SimpleNamespace(is_closing=lambda: False)

    def send(self, w):
        self.sent.append(w)

    def later(self, *args):
        pass


@pytest.fixture
def rig(monkeypatch):
    clock = [1_800_000_000.0]
    monkeypatch.setattr(world.time, "time", lambda: clock[0])
    c = {"id": 2, "name": "qwe123", "class": 3, "level": 6, "gold": 1000000, "bag": [], "bag_slots": 48}
    s, g = Session(c), Session(c)
    g.data["battle"] = combat.Battle()
    g.data["battle"].add_hero(0, 10000)
    g.data["battle"].troops[0]["hp"] = 100
    g.data["pools"] = {"sp": 0, "sp_max": 200, "ammo": 0, "fp": 0}
    st = SimpleNamespace(game_sessions={7: g}, saved=None, saves=0)
    def save():
        st.saved = json.loads(json.dumps(c))
        st.saves += 1
    st.save = save
    role = world.make(st, 0, "127.0.0.1", 0)
    def call(proto, body=b""):
        role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return SimpleNamespace(c=c, s=s, g=g, st=st, call=call, clock=clock)


def put(r, code, count=1, slot=None):
    it = {"code": code, "slot": len(r.c["bag"]) if slot is None else slot,
          "serial": (2 << 32) | (0x50000 + len(r.c["bag"])), "count": count, "bound": False}
    r.c["bag"].append(it)
    return it


def reply(r, proto):
    return bytes(next(w.buf for w in reversed(r.s.sent) if w.proto == proto))


def use(r, it, count=1):
    r.call(world.C2S_USE_ITEM, bytes(6) + obf.u32(it["code"]) + bytes(2) + obf.u64(it["serial"])
           + obf.u16(count) + bytes(5))


@pytest.mark.parametrize("code,count", [(350000010, 2), (350000010, 1), (355000000, 3), (355000000, 1)])
def test_item_use_refreshes_the_native_count_or_clears_the_last_item(rig, code, count):
    r = rig
    it = put(r, code, count, slot=36)
    use(r, it)
    assert reply(r, world.S2C_USE_ITEM)[:2] == bytes(2)
    changes = [w for w in r.s.sent if w.proto == world.S2C_CARGO_CHANGE]
    assert len(changes) == 1
    expected = (items.record(code, 36, it["serial"], count - 1, bound=False) if count > 1
                else items.record(0xffffffff, 36, 0, count=0))
    assert bytes(changes[0].buf) == struct.pack("<H", 1) + expected
    assert r.s.sent.index(changes[0]) < next(i for i, w in enumerate(r.s.sent) if w.proto == world.S2C_CARGO)
    # The cooldown/refusal path must not send another change or spend another item.
    r.s.sent.clear()
    before = deepcopy(r.c)
    use(r, it)
    assert r.c == before and reply(r, world.S2C_USE_ITEM)[:2] != bytes(2)
    assert not any(w.proto == world.S2C_CARGO_CHANGE for w in r.s.sent)


def test_potion_group_cooldown_survives_reload_and_expires_at_boundary(rig):
    r = rig
    low, higher, sp = put(r, 350000010, 3), put(r, 350000020, 3), put(r, 350100010, 3)
    use(r, low)
    assert r.g.data["battle"].troops[0]["hp"] == 700
    before = deepcopy(r.c)
    use(r, higher)
    assert reply(r, world.S2C_USE_ITEM)[:2] != bytes(2) and r.c == before
    use(r, sp)  # SP has its own group, independent of HP.
    assert reply(r, world.S2C_USE_ITEM)[:2] == bytes(2) and r.g.data["pools"]["sp"] > 0
    r.c.clear()
    r.c.update(deepcopy(r.st.saved))
    higher = next(i for i in r.c["bag"] if i["code"] == 350000020)
    r.clock[0] += 29.999
    before = deepcopy(r.c)
    use(r, higher)
    assert reply(r, world.S2C_USE_ITEM)[:2] != bytes(2) and r.c == before
    r.clock[0] += .001
    use(r, higher)
    assert reply(r, world.S2C_USE_ITEM)[:2] == bytes(2) and higher["count"] == 2


@pytest.mark.parametrize("gate", ["town", "dead", "down", "level_min", "level_max", "closed"])
def test_potion_refusals_do_not_consume_or_start_cooldowns(rig, gate):
    r = rig
    it = put(r, 350000020, 2)
    if gate == "town":
        r.st.game_sessions.clear()
    elif gate in ("dead", "down"):
        r.g.data["battle"].troops[0].update({"hp": 0} if gate == "dead" else {"down": True})
    elif gate == "closed":
        r.g.w.is_closing = lambda: True
    else:
        r.c["level"] = 4 if gate == "level_min" else 101
    before = deepcopy(r.c)
    use(r, it)
    assert reply(r, world.S2C_USE_ITEM)[:2] != bytes(2)
    assert r.c == before and r.st.saves == 0


def test_contract_records_cooldown_in_the_same_save_as_the_troop(rig):
    r = rig
    it = put(r, 355000000, 3)
    use(r, it)
    assert len(r.c["troops"]) == 1
    assert r.st.saved.get("cooldowns") == r.c.get("cooldowns")
    before = deepcopy(r.c)
    use(r, it)
    assert r.c == before and reply(r, world.S2C_USE_ITEM)[:2] != bytes(2)
    r.clock[0] += 1
    use(r, it)
    assert len(r.c["troops"]) == 2 and it["count"] == 1


def test_daily_gacha_limit_and_reset_are_saved(rig, monkeypatch):
    r = rig
    r.c["level"] = 30  # These daily reward boxes explicitly require 30; this is a disposable test fixture.
    monkeypatch.setattr(world.random, "randrange", lambda n: 0)
    it = put(r, 707010050, 3)
    r.call(world.C2S_OPEN_GACHA, struct.pack("<H", it["slot"]))
    assert reply(r, world.S2C_OPEN_GACHA)[:2] == bytes(2)
    assert r.st.saved.get("day_uses", {}).get("counts", {}).get(str(it["code"])) == 1
    before = deepcopy(r.c)
    r.call(world.C2S_OPEN_GACHA, struct.pack("<H", it["slot"]))
    assert reply(r, world.S2C_OPEN_GACHA)[:2] != bytes(2) and r.c == before
    r.clock[0] += 86400
    r.call(world.C2S_OPEN_GACHA, struct.pack("<H", it["slot"]))
    assert reply(r, world.S2C_OPEN_GACHA)[:2] == bytes(2) and it["count"] == 1
    assert r.c["day_uses"]["counts"][str(it["code"])] == 1


def test_level_six_cannot_open_a_level_thirty_gacha(rig):
    it = put(rig, 707010050, 2)
    before = deepcopy(rig.c)
    rig.call(world.C2S_OPEN_GACHA, struct.pack("<H", it["slot"]))
    assert reply(rig, world.S2C_OPEN_GACHA)[:2] != bytes(2) and rig.c == before


@pytest.mark.parametrize("choice", [False, True])
def test_box_preview_does_not_spend_daily_quota_and_claim_rechecks_it(rig, choice):
    r = rig
    if not choice:
        r.c["class"] = 0  # The only daily-limited normal container in this build requires GLEN.
    it = put(r, 613100206 if choice else 609990010, 5)
    opening = world.C2S_OPEN_CHOICE if choice else world.C2S_OPEN_CONTAINER
    taking = world.C2S_TAKE_CHOICE if choice else world.C2S_TAKE_CONTAINER
    response = world.S2C_TAKE_CHOICE if choice else world.S2C_TAKE_CONTAINER
    r.call(opening, obf.u64(it["serial"]) + (b"" if choice else obf.u16(1)))
    assert reply(r, world.S2C_OPEN_CHOICE if choice else world.S2C_OPEN_CONTAINER)[:2] == bytes(2)
    assert r.c.get("day_uses", {}).get("counts", {}).get(str(it["code"]), 0) == 0
    r.c["day_uses"] = {"day": rules.game_day(r.clock[0]), "counts": {str(it["code"]): 3}}
    before = deepcopy(r.c)
    r.call(taking, (b"\0" if choice else b"") + obf.u64(it["serial"]) + (obf.u16(0) if choice else b""))
    assert reply(r, response)[:2] != bytes(2) and r.c == before


def test_container_claim_rechecks_space_and_keeps_the_box(rig):
    r = rig
    it = put(r, 602001403, 1)
    r.call(world.C2S_OPEN_CONTAINER, obf.u64(it["serial"]) + obf.u16(1))
    for slot in range(1, 48):
        put(r, 350100010, items.max_stack(350100010), slot)
    before = deepcopy(r.c)
    r.call(world.C2S_TAKE_CONTAINER, obf.u64(it["serial"]))
    assert reply(r, world.S2C_TAKE_CONTAINER)[:2] != bytes(2) and r.c == before


def test_daylimit_is_not_the_numberofuse_list_on_125a(rig):
    it = put(rig, 358270000, 2)
    use(rig, it)
    body = bytes(world.cooldown_packet(rig.c).buf)
    n = struct.unpack_from("<H", body)[0]
    assert body[2 + 8 * n:] == bytes(2)  # native +0x268 = NumberOfUse, zero on this Cubic bundle
    assert rig.c["day_uses"]["counts"][str(it["code"])] == 1


@pytest.mark.parametrize("add,source", [(3, 0), (255, 0), (0, 2), (0, 255)])
def test_invalid_refining_modes_spend_no_gold_stones_or_cubic(rig, add, source):
    r = rig
    it = put(r, 101001300)
    it["enchant"] = 5
    put(r, 550000100, 100)
    r.c["cubic"] = 100000
    before = deepcopy(r.c)
    r.call(world.C2S_ENCHANT, bytes([add]) + obf.u16(it["slot"]) + obf.u32(550000100)
           + obf.u64(it["serial"]) + bytes([source]))
    assert reply(r, world.S2C_ENCHANT)[:2] != bytes(2) and r.c == before


@pytest.mark.parametrize("coupon", [False, True])
def test_repair_restores_the_battle_stats_of_broken_worn_gear(rig, coupon):
    r = rig
    gear = hero.equipment(r.c)
    weapon = next(e for e in gear if e["index"] == 0)
    weapon["dur"] = 0
    game.room_stats(r.g, r.c)
    before = deepcopy(r.g.data["battle"].troops[0]["c"])
    if coupon:
        use(r, put(r, 351500400))
    else:
        r.call(world.C2S_REPAIR, struct.pack("<H", 1) + b"\1" + obf.u64(weapon["serial"]) + obf.u16(weapon["index"]))
    assert "dur" not in weapon
    assert r.g.data["battle"].troops[0]["c"] == game.hero_combatant(r.c)
    assert r.g.data["battle"].troops[0]["c"] != before


def buy(r, shop, slot=0, count=1):
    r.call(world.C2S_STORE_BUY, obf.u16(0) + bytes(4) + struct.pack("<I", shop) + obf.u16(count) + bytes([slot]))


@pytest.mark.parametrize("tokens", [False, True])
def test_full_bag_purchase_refuses_without_charging_or_mailing(rig, tokens):
    r = rig
    r.c["bag_slots"] = 2
    if tokens:
        put(r, 760000030, 1001)  # A 1000-coin purchase leaves this stack occupying its slot.
    else:
        put(r, 350100010, 1)
    put(r, 350100010, 1)
    before = deepcopy(r.c)
    buy(r, 216 if tokens else 103)
    result = reply(r, world.S2C_STORE_BUY)
    assert len(result) == 15 and result[:2] != bytes(2)
    assert r.c == before and r.st.saves == 0


def test_coin_purchase_uses_split_stacks_and_space_freed_by_payment(rig):
    r = rig
    r.c["bag_slots"] = 2
    put(r, 760000030, 600)
    put(r, 760000030, 401)
    gold = r.c["gold"]
    buy(r, 216)
    assert reply(r, world.S2C_STORE_BUY)[:2] == bytes(2)
    assert sum(i["count"] for i in r.c["bag"] if i["code"] == 760000030) == 1
    assert any(i["code"] == 613700310 for i in r.c["bag"]) and not r.c.get("mail")
    assert r.c["gold"] == gold and r.st.saved == r.c


def test_short_coin_balance_never_falls_back_to_gold(rig):
    put(rig, 760000030, 999)
    before = deepcopy(rig.c)
    buy(rig, 216)
    assert reply(rig, world.S2C_STORE_BUY)[:2] != bytes(2) and rig.c == before


def test_mission_certificates_exchange_five_for_the_shipped_supply_crate(rig):
    r = rig
    r.c.update(level=17, spot=10001, pos=[0, 0, 0])  # Exchange quest's AcquireLevel/PerformLevel, disposable fixture.
    put(r, 760000130, 2)
    put(r, 760000130, 4)
    row = tables.by_id("questtable")["9900360"]
    assert row["Use_Quest"] == "Yes" and quest.reward_items(row, 3) == [(704014000, 1)]
    q = quest.record(r.c)
    q["active"]["9900360"] = {"counts": [n for _, _, n in quest.conditions(row)], "time": 0, "tracked": True}
    assert quest.hand_in(r.s, r.st, 9900360)
    assert sum(i["count"] for i in r.c["bag"] if i["code"] == 760000130) == 1
    assert sum(i["count"] for i in r.c["bag"] if i["code"] == 704014000) == 1
    before = deepcopy(r.c)
    assert not quest.hand_in(r.s, r.st, 9900360) and r.c == before


@pytest.mark.parametrize("choice", [False, True])
def test_successful_box_claim_counts_once_and_survives_reload(rig, choice):
    r = rig
    if not choice:
        r.c["class"] = 0
    it = put(r, 613100206 if choice else 609990010, 5)
    opening = world.C2S_OPEN_CHOICE if choice else world.C2S_OPEN_CONTAINER
    taking = world.C2S_TAKE_CHOICE if choice else world.C2S_TAKE_CONTAINER
    response = world.S2C_TAKE_CHOICE if choice else world.S2C_TAKE_CONTAINER
    r.call(opening, obf.u64(it["serial"]) + (b"" if choice else obf.u16(2)))
    body = (b"\0" if choice else b"") + obf.u64(it["serial"]) + (obf.u16(0) if choice else b"")
    r.call(taking, body)
    assert reply(r, response)[:2] == bytes(2)
    assert r.st.saved["day_uses"]["counts"][str(it["code"])] == (1 if choice else 2)
    before = deepcopy(r.c)
    r.call(taking, body)
    assert reply(r, response)[:2] != bytes(2) and r.c == before

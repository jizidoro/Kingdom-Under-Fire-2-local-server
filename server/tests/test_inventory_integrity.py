"""Item conservation across the real bag, storage, shop and mail requests.

These are server regressions, not claims about unobserved original-server policy.
"""
from copy import deepcopy
import json
import struct

import pytest

from kuf2 import items, mail, obf, serials, troops, world
from test_economy import Session, State, call, last, role  # noqa: F401

POTION, COSTUME, WEAPON = 350000010, 950000640, 101001300


def item(code=POTION, slot=0, serial=11, count=5, **extra):
    return dict(code=code, slot=slot, serial=serial, count=count, bound=items.bound_on_gain(code), **extra)


def transfer(serial, src, dst, other=0, count=1):
    return obf.u64(serial) + obf.u16(dst) + obf.u64(other) + obf.u16(count) + obf.u16(src)


def assert_shop_delta(s, c, slots, reply):
    # The purchase result must update the shop's gold before1656 overwrites
    # the common total; otherwise140dcbdb0 treats the new total as unchanged.
    protos = [w.proto for w in s.sent]
    assert protos.index(reply) < protos.index(world.S2C_CARGO_CHANGE) < protos.index(world.S2C_CARGO)
    changes = last(s, world.S2C_CARGO_CHANGE)
    expected = bytearray(struct.pack("<H", len(slots)))
    for slot in slots:
        it = next((i for i in c["bag"] if i["slot"] == slot), None)
        expected.extend(items.record(it["code"], slot, it["serial"], it["count"], items.durability(it),
                                     bound=it.get("bound", False), enchant=it.get("enchant", 0),
                                     sockets=items.sockets(it), expiry=items.seconds_left(it),
                                     options=it.get("options", ())) if it else items.record(0xffffffff, slot, 0, count=0))
    assert changes == bytes(expected)


@pytest.mark.parametrize("pending", [False, True])
def test_field_entry_restores_buyback_list_without_requiring_another_sale(role, pending):
    s = Session()
    c = s.data["char"]
    entry = item(401000200, 0, 55, 7)
    entry.update(price=8, enchant=0)
    c.update(spot=10001, pos=[0, 0, 0], buyback=[entry] if pending else [])
    call(role, s, world.C2S_ENTER_TOWN, obf.u32(10001))
    expected = b"\1" + items.record(401000200, 0, 55, 7, items.durability(entry), bound=False) if pending else b"\0"
    assert last(s, world.S2C_REBUY_LIST) == expected
    # The same contract serves subsequent list requests.
    call(role, s, world.C2S_REBUY_LIST)
    assert last(s, world.S2C_REBUY_LIST) == expected


@pytest.mark.parametrize("existing", [0, 3, 99])
def test_shop_purchase_updates_gold_then_every_changed_slot(role, existing):
    s = Session()
    c = s.data["char"]
    c.update(gold=1000, bag=[item(count=existing)] if existing else [])
    call(role, s, world.C2S_STORE_BUY, obf.u16(1) + struct.pack("<II", 0, 103) + obf.u16(2) + b"\0")
    assert c["gold"] == 840 and sum(i["count"] for i in c["bag"]) == existing + 2
    assert_shop_delta(s, c, [1] if not existing else [0, 1] if existing == 99 else [0], world.S2C_STORE_BUY)
    assert sum(w.proto == world.S2C_CARGO for w in s.sent) == 1


def test_a_full_bag_gets_the_code_whose_text_says_so(role):
    s = Session()
    c = s.data["char"]
    c.update(gold=1000, bag_slots=1, bag=[item(760000030, 0, 11, 1)])      # another item holds the only slot
    call(role, s, world.C2S_STORE_BUY, obf.u16(1) + struct.pack("<II", 0, 103) + obf.u16(2) + b"\0")
    assert struct.unpack_from("<H", last(s, world.S2C_STORE_BUY))[0] == 0x6403 and c["gold"] == 1000


def test_token_purchase_refreshes_payment_slots_and_reward_before_snapshot(role):
    s = Session()
    c = s.data["char"]
    c.update(bag_slots=3, bag=[item(760000030, 0, 11, 600), item(760000030, 1, 12, 400)])
    call(role, s, world.C2S_STORE_BUY, obf.u16(2) + struct.pack("<II", 0, 216) + obf.u16(1) + b"\0")
    assert [(i["code"], i["slot"]) for i in c["bag"]] == [(613700310, 2)]
    assert_shop_delta(s, c, [0, 1, 2], world.S2C_STORE_BUY)


@pytest.mark.parametrize("count", [1, 5])
def test_sale_redraws_partial_or_empty_slot_after_ack(role, count):
    s = Session()
    c = s.data["char"]
    c["bag"] = [item()]
    call(role, s, world.C2S_STORE_SELL, obf.u16(count) + obf.u16(0) + obf.u64(11))
    assert c["gold"] == items.sell_price(POTION) * count
    assert_shop_delta(s, c, [0], world.S2C_STORE_SELL)


@pytest.mark.parametrize("target", ["empty", "compatible", "different", "full"])
def test_buyback_merges_only_compatible_stacks_and_redraws(role, target):
    s = Session()
    c = s.data["char"]
    entry = item(count=2)
    entry["price"] = items.sell_price(POTION)
    c.update(gold=1000, buyback=[entry], bag=[] if target == "empty" else [item(serial=22)])
    if target == "different":
        c["bag"][0]["bound"] = True
    if target == "full":
        c["bag"][0]["count"] = 99
    before = deepcopy(c)
    call(role, s, world.C2S_REBUY, obf.u16(0) + struct.pack("<H", 0))
    if target in ("different", "full"):
        assert c == before and last(s, world.S2C_REBUY)[-2:] != bytes(2)
        assert not any(w.proto == world.S2C_CARGO_CHANGE for w in s.sent)
    else:
        assert c["gold"] == 1000 - entry["price"] * 2 and not c["buyback"]
        assert (c["bag"][0]["count"], c["bag"][0]["serial"]) == ((2, 11) if target == "empty" else (7, 22))
        assert_shop_delta(s, c, [0], world.S2C_REBUY)


@pytest.mark.parametrize("operation,target,count", [
    ("split", None, 2), ("split", "same", 2), ("split", "same", 5),
    ("split", None, 5), ("move", None, 5), ("move", "different", 5),
])
def test_bag_changes_redraw_both_native_slots_before_the_snapshot(role, operation, target, count):
    # Native2026-10-09: splitting7 iron ore into6+1 changed the save but left
    # the open bag showing7 and an empty destination. Full snapshots do not redraw.
    s = Session()
    c = s.data["char"]
    c["bag"] = [item()]
    if target:
        c["bag"].append(item(code=POTION if target == "same" else 401000200, slot=1, serial=12))
    if operation == "split":
        proto = world.C2S_BAG_SPLIT
        body = obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u16(count)
    else:
        proto = world.C2S_BAG_MOVE
        body = obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u64(12 if target else 0)
    call(role, s, proto, body)
    changes = [w for w in s.sent if w.proto == world.S2C_CARGO_CHANGE]
    assert len(changes) == 1
    expected = bytearray(struct.pack("<H", 2))
    for slot in (0, 1):
        it = next((it for it in c["bag"] if it["slot"] == slot), None)
        expected.extend(items.record(it["code"], slot, it["serial"], it["count"], items.durability(it),
                                     bound=it["bound"]) if it else items.record(0xffffffff, slot, 0, count=0))
    assert bytes(changes[0].buf) == bytes(expected)
    assert s.sent.index(changes[0]) < next(i for i, w in enumerate(s.sent) if w.proto == world.S2C_CARGO)


@pytest.mark.parametrize("box,proto,reply", [
    ("bag", world.C2S_BAG_SPLIT, world.S2C_BAG_SPLIT),
    ("warehouse", world.C2S_WAREHOUSE_SPLIT, world.S2C_WAREHOUSE_SPLIT),
])
def test_split_preserves_attributes_without_aliasing(role, box, proto, reply):
    s = Session()
    original = item(enchant=2, dur=7, expires=2_000_000_000, sockets=[-1, 123], options=[[1, 1, 0.0, 7, 42]])
    s.data["char"][box] = [deepcopy(original)]
    call(role, s, proto, obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u16(2))
    assert last(s, reply) == bytes(2)
    a, b = sorted(s.data["char"][box], key=lambda i: i["slot"])
    assert (a["count"], b["count"]) == (3, 2)
    assert a["serial"] != b["serial"]
    for key in ("bound", "enchant", "dur", "expires", "sockets", "options"):
        assert a[key] == b[key] == original[key]
    b["sockets"][0] = 456
    assert a["sockets"] == original["sockets"]


@pytest.mark.parametrize("different", [{"bound": True}, {"enchant": 1}, {"dur": 1},
                                       {"expires": 2_000_000_000}, {"sockets": [123]},
                                       {"options": [[1, 1, 0.0, 7, 42]]}])
def test_split_does_not_erase_distinct_attributes_by_merging(role, different):
    s = Session()
    c = s.data["char"]
    a, b = item(), item(slot=1, serial=12)
    b.update(different)
    c["bag"] = [a, b]
    before = deepcopy(c)
    call(role, s, world.C2S_BAG_SPLIT, obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u16(2))
    assert last(s, world.S2C_BAG_SPLIT) != bytes(2)
    assert c == before
    assert not any(w.proto == world.S2C_CARGO_CHANGE for w in s.sent)


def test_storage_roundtrip_uses_costume_tab_and_keeps_expiry(role):
    s = Session()
    c = s.data["char"]
    c["bag"] = [item(COSTUME, 0x100, count=1, expires=2_000_000_000)]
    original = deepcopy(c["bag"])
    call(role, s, world.C2S_BAG_TO_WAREHOUSE, transfer(11, 0x100, 0))
    assert last(s, world.S2C_BAG_TO_WAREHOUSE) == bytes(2)
    call(role, s, world.C2S_WAREHOUSE_TO_BAG, transfer(11, 0, 0x100))
    assert last(s, world.S2C_WAREHOUSE_TO_BAG) == bytes(2)
    assert c["bag"] == original and c["warehouse"] == []


def test_storage_moves_redraw_the_open_bag_slot(role):
    # live 2026-11-07 (d8_wh4): the potions dragged into storage showed there, and the open bag kept drawing them at
    # slot 23 until it was reopened; 0x1656 does not redraw an open bag, 0x1657 does (defect 9).
    s = Session()
    c = s.data["char"]
    c["bag"] = [item(slot=23, count=9)]
    call(role, s, world.C2S_BAG_TO_WAREHOUSE, transfer(11, 23, 0, count=9))
    ids = [w.proto for w in s.sent]
    assert ids.index(world.S2C_BAG_TO_WAREHOUSE) < ids.index(world.S2C_CARGO_CHANGE) < ids.index(world.S2C_CARGO)
    assert struct.unpack_from("<H", last(s, world.S2C_CARGO_CHANGE))[0] == 1
    s.sent.clear()
    call(role, s, world.C2S_WAREHOUSE_TO_BAG, transfer(11, 0, 4, count=9))
    ids = [w.proto for w in s.sent]
    assert ids.index(world.S2C_WAREHOUSE_TO_BAG) < ids.index(world.S2C_CARGO_CHANGE) < ids.index(world.S2C_CARGO)
    assert c["bag"][0]["slot"] == 4


@pytest.mark.parametrize("bad_target", [0, 32, 0x80, 0xc0, 0x500])
def test_storage_rejects_wrong_bag_tab_without_mutation(role, bad_target):
    s = Session()
    c = s.data["char"]
    c["warehouse"] = [item(COSTUME, count=1)]
    before = deepcopy(c)
    call(role, s, world.C2S_WAREHOUSE_TO_BAG, transfer(11, 0, bad_target))
    assert last(s, world.S2C_WAREHOUSE_TO_BAG) != bytes(2)
    assert c == before


def test_storage_swap_validates_the_item_returning_to_bag(role):
    s = Session()
    c = s.data["char"]
    c.update(bag=[item(COSTUME, 0x100, count=1)], warehouse=[item(serial=12)])
    before = deepcopy(c)
    call(role, s, world.C2S_BAG_TO_WAREHOUSE, transfer(11, 0x100, 0, 12))
    assert last(s, world.S2C_BAG_TO_WAREHOUSE) != bytes(2)
    assert c == before


@pytest.mark.parametrize("proto,reply,body", [
    (world.C2S_BAG_MOVE, world.S2C_BAG_MOVE, obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u64(99)),
    (world.C2S_BAG_TO_WAREHOUSE, world.S2C_BAG_TO_WAREHOUSE, transfer(11, 0, 0, 99)),
])
def test_stale_destination_is_refused_even_when_now_empty(role, proto, reply, body):
    s = Session()
    c = s.data["char"]
    c.update(bag=[item(count=1)], warehouse=[])
    before = deepcopy(c)
    call(role, s, proto, body)
    assert last(s, reply) != bytes(2)
    assert c == before
    assert not any(w.proto == world.S2C_CARGO_CHANGE for w in s.sent)


def test_loot_does_not_inherit_binding_from_an_existing_stack(role):
    s = Session()
    c = s.data["char"]
    c["bag"] = [item(count=2)]
    c["bag"][0]["bound"] = True
    world.add_item(s, role[1], POTION, 3)
    assert sorted((i["bound"], i["count"]) for i in c["bag"]) == [(False, 3), (True, 2)]


def test_mail_multi_stack_attachment_cannot_be_partly_lost(role):
    s = Session()
    c = s.data["char"]
    cap = items.max_stack(POTION)
    c["bag"] = [item(WEAPON, slot=k, serial=k + 100, count=1) for k in range(world.bag_slots(c) - 1)]
    mail.deliver(s, role[1], c, "Overflow", "Test", grant=[(POTION, cap + 1)])
    before = deepcopy(c)
    call(role, s, mail.C2S_TAKE_ITEM, struct.pack("<QBH", c["mail"][0]["id"], 0, 31))
    assert last(s, mail.S2C_TAKE_ITEM) == struct.pack("<H", mail.BAG_FULL)
    assert c == before
    c["bag"].pop()
    call(role, s, mail.C2S_TAKE_ITEM, struct.pack("<QBH", c["mail"][0]["id"], 0, 31))
    assert last(s, mail.S2C_TAKE_ITEM) == bytes(2)
    assert sum(i["count"] for i in c["bag"] if i["code"] == POTION) == cap + 1
    assert c["mail"][0]["items"][0]["taken"]


def test_capacity_combines_partial_stacks_and_duplicate_reward_rows():
    cap = items.max_stack(POTION)
    c = dict(id=2, bag_slots=2, bag=[item(count=cap - 1), item(slot=1, serial=12, count=cap - 1)])
    assert world.fits(c, [(POTION, 2)])
    assert not world.fits(c, [(POTION, 2), (POTION, 1)])
    assert not world.fits(dict(id=2, bag_slots=1, bag=[]), [(POTION, cap + 1)])


def test_allocated_ids_do_not_repeat_at_legacy_boundary_or_after_reload(role):
    s = Session()
    c = s.data["char"]
    world.add_item(s, role[1], WEAPON, 1)
    first = c["bag"][0]["serial"]
    c["next_serial"] = 0x10000
    world.add_item(s, role[1], WEAPON, 1)
    assert len({i["serial"] for i in c["bag"]}) == 2, hex(first)
    c["next_serial"] = 0x20000
    t, result = troops.grant(c, 1)
    assert result == 0 and t["uid"] not in {i["serial"] for i in c["bag"]}
    s.data["char"] = c = json.loads(json.dumps(c))
    previous = {i["serial"] for i in c["bag"]} | {t["uid"]}
    world.add_item(s, role[1], WEAPON, 1)
    assert c["bag"][-1]["serial"] not in previous


def test_sell_and_buyback_preserve_equipment_and_money(role):
    s = Session()
    c = s.data["char"]
    c["bag"] = [item(WEAPON, count=1, enchant=3, dur=7, sockets=[123], options=[[1, 1, 0.0, 7, 42]])]
    before = deepcopy(c["bag"][0])
    call(role, s, world.C2S_STORE_SELL, obf.u16(1) + obf.u16(0) + obf.u64(11))
    assert not c["bag"] and c["gold"] == items.sell_price(WEAPON)
    call(role, s, world.C2S_REBUY, obf.u16(0) + struct.pack("<H", 0))
    assert last(s, world.S2C_REBUY)[-2:] == bytes(2)
    assert c["bag"] == [before] and c["gold"] == 0 and c["buyback"] == []


@pytest.mark.parametrize("box", ["bag", "warehouse", "equip", "buyback", "troops", "troop_gear"])
def test_allocator_respects_every_persistent_owner(box):
    old = (2 << 32) | 0x71234
    c = {"id": 2, "next_serial": 1}
    if box == "troops":
        c[box] = [{"uid": old}]
    elif box == "troop_gear":
        c["troops"] = [{"uid": (2 << 32) | 0x20001, "gear": [{"serial": old}]}]
    else:
        c[box] = [{"serial": old}]
    assert serials.allocate(c) > old
    saved = json.loads(json.dumps(c))
    assert serials.allocate(saved) > (2 << 32) | c["next_serial"]


def test_allocator_never_carries_into_another_character():
    c = {"id": 2, "next_serial": 0xffffffff}
    before = deepcopy(c)
    with pytest.raises(OverflowError):
        serials.allocate(c)
    assert c == before


@pytest.mark.parametrize("box,proto,reply", [
    ("bag", world.C2S_BAG_SPLIT, world.S2C_BAG_SPLIT),
    ("warehouse", world.C2S_WAREHOUSE_SPLIT, world.S2C_WAREHOUSE_SPLIT),
])
def test_compatible_split_then_merge_conserves_count(role, box, proto, reply):
    s = Session()
    c = s.data["char"]
    c[box] = [item(count=10)]
    call(role, s, proto, obf.u16(0) + obf.u16(1) + obf.u64(11) + obf.u16(4))
    new = next(i for i in c[box] if i["slot"] == 1)
    call(role, s, proto, obf.u16(1) + obf.u16(0) + obf.u64(new["serial"]) + obf.u16(4))
    assert last(s, reply) == bytes(2)
    assert c[box] == [item(count=10)]


def test_freed_container_slot_is_not_counted_as_both_space_and_stack_capacity():
    cap = items.max_stack(POTION)
    c = dict(id=2, bag_slots=1, bag=[item(count=1)])
    assert world.fits(c, [(POTION, cap)], freed=0)
    assert not world.fits(c, [(POTION, cap + 1)], freed=0)


def test_capacity_prediction_matches_actual_multi_reward_delivery(role):
    """Exercise independent request outcomes across fullness, binding and duplicate rows."""
    cap = items.max_stack(POTION)
    for count in (1, cap - 1, cap):
        for bound in (False, True):
            for slots in (1, 2, 3):
                for reward in (1, 2, cap, cap + 1):
                    s = Session()
                    c = s.data["char"]
                    c.update(bag_slots=slots, bag=[item(count=count)])
                    c["bag"][0]["bound"] = bound
                    got = [(POTION, reward), (POTION, 1)]
                    expected = world.fits(c, got)
                    left = sum(world.add_item(s, role[1], code, n, mail=False) for code, n in got)
                    assert expected == (left == 0), (count, bound, slots, reward)
                    assert sum(i["count"] for i in c["bag"]) + left == count + reward + 1

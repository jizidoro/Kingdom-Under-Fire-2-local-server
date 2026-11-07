"""The requests whose handlers no test or smoke had ever run, though the coverage page counted them as tested (the
reply recorder of tools/recon/answers.py found them, 2026-11-05): each through its registered handler, read as the
client's reply function reads it (planning/client/ANSWERS.md).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import daily, game, obf, tables, troops, world
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE
from test_army import army, entered, pkt
from test_economy import Session, call, last, role, troop_role  # noqa: F401

ITEM = 8128000                  # a real row: the warehouse and the bag read it


def session(*sets):
    s = Session()
    s.data["char"], ts = army(*sets)
    s.data["char"].update(gold=0, bag=[])
    s.data["account"] = {"id": 1, "characters": [s.data["char"]]}
    return s, s.data["char"], ts


def worn(c):
    c["equip"] = [{"code": ITEM, "index": 7, "serial": 5, "bound": False},
                  {"code": ITEM, "index": 8, "serial": 6, "bound": False}]
    return c["equip"]


def test_the_bag_tab_answers_and_resends_the_cargo(role):
    s, _, _ = session()
    call(role, s, world.C2S_BAG_TAB, b"\x01")
    assert last(s, world.S2C_BAG_TAB) == bytes(3)       # one 3-byte read (0x140dd1570): u8, i16 result
    assert world.S2C_CARGO in {w.proto for w in s.sent}


def test_favorites_are_saved_and_answered_by_nothing(troop_role):
    s, _, (t,) = session(1)
    call(troop_role, s, troops.C2S_FAVORITES, struct.pack("<HQ", 1, t["uid"]) + bytes([OBOOL_TRUE]))
    assert t["favorite"] is True
    call(troop_role, s, troops.C2S_FAVORITES, struct.pack("<HQ", 1, t["uid"]) + bytes([OBOOL_FALSE]))
    assert t["favorite"] is False
    call(troop_role, s, troops.C2S_FAVORITES, struct.pack("<HQ", 1, 999) + bytes([OBOOL_TRUE]))     # no such troop
    call(troop_role, s, troops.C2S_FAVORITES, b"\x01")                                              # short
    assert s.sent == []                                 # 0x1345's handler 0x140da5b70 is a bare ret: nothing to answer


def test_cheering_every_troop_refills_their_ap_for_gold(troop_role):
    s, c, (t,) = session(1)
    t["ap"] = 0
    cost, top = troops.cheer_cost(t)
    assert cost > 0
    c["gold"] = cost - 1
    call(troop_role, s, 0x135c)
    assert last(s, 0x135d) == struct.pack("<H", 0x6401) and t["ap"] == 0        # short of gold: nothing taken
    c["gold"] = cost
    call(troop_role, s, 0x135c)
    assert last(s, 0x135d) == struct.pack("<HBHQ", 0, 1, top, t["uid"])
    assert t["ap"] == top and c["gold"] == 0


def test_destroying_a_kept_item_takes_it_from_the_warehouse(role):
    s, c, _ = session()
    c["warehouse"] = [{"code": ITEM, "count": 3, "slot": 2, "serial": 77, "bound": False}]
    ask = lambda slot, n: call(role, s, world.C2S_DESTROY_KEPT, obf.u16(slot) + obf.u16(n) + obf.u64(77))
    ask(2, 4)                                           # more than the stack
    assert last(s, world.S2C_DESTROY_KEPT) == struct.pack("<H", world.WAREHOUSE_REFUSED)
    ask(5, 1)                                           # another slot
    assert last(s, world.S2C_DESTROY_KEPT) == struct.pack("<H", world.WAREHOUSE_REFUSED)
    assert c["warehouse"][0]["count"] == 3
    ask(2, 1)
    assert last(s, world.S2C_DESTROY_KEPT) == bytes(2) and c["warehouse"][0]["count"] == 2
    ask(2, 2)
    assert c["warehouse"] == []


def test_a_ring_pair_swaps_and_a_wrong_serial_or_slot_is_refused(role):
    s, c, _ = session()
    eq = worn(c)
    call(role, s, world.C2S_SWAP_PAIR, obf.u64(99) + obf.u16(7))
    assert last(s, world.S2C_SWAP_PAIR) == struct.pack("<H", 1)
    call(role, s, world.C2S_SWAP_PAIR, obf.u64(5) + obf.u16(3))             # not a pair's slot
    assert last(s, world.S2C_SWAP_PAIR) == struct.pack("<H", 1) and eq[0]["index"] == 7
    call(role, s, world.C2S_SWAP_PAIR, obf.u64(5) + obf.u16(7))
    assert last(s, world.S2C_SWAP_PAIR) == bytes(2)
    assert (eq[0]["index"], eq[1]["index"]) == (8, 7)


def test_destroying_a_worn_item_answers_its_slot_and_resends_the_hero(role):
    s, c, _ = session()
    worn(c)
    call(role, s, world.C2S_DESTROY_WORN, obf.u64(99) + obf.u16(7))
    assert last(s, world.S2C_DESTROY_WORN) == struct.pack("<H", 1) and len(c["equip"]) == 2
    call(role, s, world.C2S_DESTROY_WORN, obf.u64(5) + obf.u16(7))
    assert last(s, world.S2C_DESTROY_WORN) == bytes(2) + obf.u16(7)
    assert [e["serial"] for e in c["equip"]] == [6]


def test_quick_slots_swap_and_the_request_is_echoed(role):
    s, c, _ = session()
    first, second = {"code": 1}, {"code": 2}
    c["quick_slots"] = {"0:0:1": first, "0:0:2": second}
    body = bytes([1, 0, 0, 2])                          # bar slot 1, mode 0 (both item lists), group 0, slot 2
    call(role, s, world.C2S_QUICK_SLOT_SWAP, body)
    assert c["quick_slots"] == {"0:0:1": second, "0:0:2": first}
    assert last(s, world.S2C_QUICK_SLOT_SWAP) == bytes(2) + body        # the client swaps the two itself (0x1408ece40)


def test_a_daily_refresh_costs_its_price_and_resends_the_tasks(role):
    s, c, _ = session()
    price = next(int(r["Gold_Count"]) for r in tables.sections("item_currency")["Base"]
                 if r["ItemCurrencyType"] == "DAILYTASK_REFRESH")
    assert price > 0
    c["gold"] = price - 1
    call(role, s, daily.C2S_REFRESH)
    assert last(s, daily.S2C_REFRESH) == struct.pack("<H", 0x5c14) and c["gold"] == price - 1
    c["gold"] = price
    call(role, s, daily.C2S_REFRESH)
    assert last(s, daily.S2C_REFRESH) == bytes(2) and c["gold"] == 0


@pytest.fixture
def room():
    c, _ = army(1)
    return entered(10235, c)


def ask(room, proto, body):
    role, s = room
    before = len(s.sent)
    role.handlers[proto](s, pkt(proto, body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def test_an_ended_ground_effect_is_echoed_by_its_id(room):
    assert ask(room, game.C2S_AREA_END, struct.pack("<HH", 7, 0)) == [(game.S2C_AREA_END, struct.pack("<H", 7))]


def test_only_a_skipped_cutscene_waits_for_the_rooms_answer(room):
    scene = struct.pack("<I", 1234)
    assert ask(room, game.C2S_CUTSCENE, scene + bytes([OBOOL_FALSE])) == []
    assert ask(room, game.C2S_CUTSCENE, scene + bytes([OBOOL_TRUE])) == [(game.S2C_CUTSCENE, scene)]


def test_a_box_carries_no_gold_so_its_gold_entry_is_refused(room):
    body = obf.u40(0) + struct.pack("<H", 0) + obf.u32(42)
    assert ask(room, game.C2S_BOX_GOLD, body) == [(game.S2C_BOX_GOLD, obf.u32(42) + struct.pack("<H", game.PROP_REFUSED))]


def test_a_loot_owners_name_is_refused_with_the_object_echoed(room):
    assert ask(room, game.C2S_LOOT_OWNER, obf.u32(42)) == [(game.S2C_LOOT_OWNER, struct.pack("<H", 1) + obf.u32(42))]

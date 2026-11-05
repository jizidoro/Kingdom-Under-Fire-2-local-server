"""Equipping on a second character in a battle room (live 2026-09-30 13:57:49-13:58:21, field 10350): the owner's new
hero 'qwe123' (character 2 of account 1, class 3 ISABELLA) reported "we can't equip items from inventory to our hero";
the server log showed each swap followed by its reverse.

The requests below are the fifteen C2S 0x164e bodies of that span as captured (captures/world_20260930_135025_413671.log,
the bytes after the 5-byte header); the bag is the 0x1656 the server sent at 13:55:36 and the equipment the 0x134b of
13:54:27 (the class kit), both decoded from the same capture. The recorder (captures/logs/client_20260930_135027.log)
shows a MouseRClick (or, at 13:58:12, a drag) before every one of them: the reverses are the owner's own clicks on the
same bag slot, not the client undoing the server's swap."""
import struct
from copy import deepcopy

import pytest

from kuf2 import game, hero, items, obf, world
from test_battle import Session, pkt

LIVE_REQUESTS = [                                  # time, body (bag serial, worn serial, equipment index, bag slot)
    ("13:57:49.626", "1098c7c3ccc3c3c3109810c3c7c3c3c310c31033"),
    ("13:57:50.633", "1098c7c387c3c3c3109810c398c3c3c31012102a"),
    ("13:57:52.112", "1098c7c378c3c3c3109810c33ec3c3c310fd1035"),
    ("13:57:55.759", "109810c33ec3c3c31098c7c378c3c3c310fd1035"),
    ("13:57:55.918", "1098c7c378c3c3c3109810c33ec3c3c310fd1035"),
    ("13:57:56.083", "109810c33ec3c3c31098c7c378c3c3c310fd1035"),
    ("13:57:56.624", "1098c7c378c3c3c3109810c33ec3c3c310fd1035"),
    ("13:58:02.147", "109810c3c7c3c3c31098c7c3ccc3c3c310c31033"),
    ("13:58:02.660", "109810c398c3c3c31098c7c387c3c3c31012102a"),
    ("13:58:07.713", "1098c7c3ccc3c3c3109810c3c7c3c3c310c31033"),
    ("13:58:07.862", "109810c3c7c3c3c31098c7c3ccc3c3c310c31033"),
    ("13:58:08.037", "1098c7c3ccc3c3c3109810c3c7c3c3c310c31033"),
    ("13:58:12.869", "109810c3c7c3c3c31098c7c3ccc3c3c310c31033"),
    ("13:58:20.693", "1098c7c33ec3c3c3109810c3ccc3c3c3103310d2"),
    ("13:58:21.782", "1098c7c387c3c3c3109810c398c3c3c31012102a"),
]
BAG_1355 = [(0, 760000030, 0x200010001, 100, True), (1, 350000010, 0x200010002, 2, False),
            (2, 101201110, 0x200010003, 1, True), (3, 102201110, 0x200010004, 1, True),
            (0x80, 451000231, 0x200010005, 2, False), (4, 151201110, 0x200010006, 1, True),
            (5, 358200030, 0x200010007, 2, True), (6, 154204113, 0x200010008, 1, False),
            (7, 154201110, 0x200010009, 1, True)]


# the 0x134b of 13:54:27: the kit she was made with then (ours, before hero.starter_kit), serials 0x200000001..
EQUIP_1354 = [100000003, 100000004, 150000006, 150000007, 150000008, 150000009, 150000010]


def qwe123():
    c = {"id": 2, "name": "qwe123", "class": 3, "level": 2, "look": bytes(56).hex(),
         "bag": [{"slot": s, "code": code, "serial": serial, "count": n, "bound": b}
                 for s, code, serial, n, b in BAG_1355],
         "equip": [{"code": code, "index": i, "serial": (2 << 32) | (i + 1), "bound": True}
                   for i, code in enumerate(EQUIP_1354)]}
    hero.equipment(c)
    return c


class St:
    saves = 0

    def save(self):
        self.saves += 1


def test_the_owners_equip_clicks_replay_as_she_made_them():
    role, s, c = world.make(St(), 0, "127.0.0.1", 0), Session(), qwe123()
    s.data["char"] = c
    for when, body in LIVE_REQUESTS:
        b = bytes.fromhex(body)
        bag_serial, slot = obf.dec_u64(b[0:8]), obf.dec_u16(b[18:20])
        assert next(i["serial"] for i in c["bag"] if i["slot"] == slot) == bag_serial, when   # what the server left there
        s.sent.clear()
        role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, b))
        assert bytes(s.sent[0].buf) == b"\0\0", when                                          # 0x164f: done
    worn = {e["index"]: (e["code"], e["serial"]) for e in c["equip"]}
    assert worn[0] == (100000003, 0x200000001)         # the last touch on the main weapon (13:58:12) put the kit's back
    assert (worn[1], worn[2], worn[5]) == ((102201110, 0x200010004), (151201110, 0x200010006), (154201110, 0x200010009))
    assert next(i["code"] for i in c["bag"] if i["slot"] == 2) == 101201110          # the save the owner was left with


def worn_look(p):
    return [obf.dec_u32(p[0x29 + 4 * i:0x2d + 4 * i]) for i in range(21)]


def test_the_room_look_lists_each_worn_item_at_its_equipment_index_and_shows_it():
    """The 0x3f4f player struct's 21 codes are the troop's look array by equipment index (SetPlayerInfoData
    0x140cf9d70 -> player +0xb4; 0x140b40ab0 -> 0x140a4fdb0 copies them to troop +0x1140: [0] / [1] the main / sub
    weapon (0x140a4f580, -1 = the class's default), [2..6] the armour with a costume at index + 11 over it
    (0x140a52110), 7..10 the rings (no mesh)); +0x88 is the mask of parts shown (troop +0x1194). An equip in a room
    changes the model only where that flag is 1 (0x164f -> 0x140d6b1e0 -> 0x140a504e0). Ours listed the codes by
    E_ItemParts (the main weapon at [1], the sub weapon read as the upper body, the boots as a ring) and a mask of 0."""
    c = qwe123()
    c["equip"].append({"code": 200900001, "index": 8, "serial": 0x20001000a})            # a ring in its second place
    p = game.player_struct(c, 10350)
    assert worn_look(p) == ([100000003, 100000004, 150000006, 150000007, 150000008, 150000009, 150000010, 0xffffffff,
                             200900001] + [0xffffffff] * 12)
    assert struct.unpack_from("<I", p, 0x88)[0] == (1 << 21) - 1


def test_an_equip_moves_the_room_look_with_it():
    c = qwe123()
    assert world.change_equip(c, 0x200010003, 0x200000001, 0, 2) is None
    assert worn_look(game.player_struct(c))[0] == 101201110           # the next room starts him with it


@pytest.mark.parametrize("swap", [False, True])
def test_equipment_returned_to_the_bag_refreshes_the_open_native_slot(swap):
    # Native2026-10-09:164f/134b/1656 left slot34 blank until reopening I,
    # although both the saved and native bag contained the unequipped weapon.
    # AssignItemInfos1656 does not redraw the open slot. InvenItemChange1657
    # updates that slot through140dca560, before the authoritative bag snapshot.
    c = qwe123()
    c["bag_slots"] = 48
    worn = deepcopy(c["equip"][0])
    c["equip"][0].update(enchant=2, sockets=[-1], options=[[0, 23, 0.0, 2]])
    target = 2 if swap else 34
    bag_serial = next(i["serial"] for i in c["bag"] if i["slot"] == target) if swap else 0
    s = Session()
    s.data["char"] = c
    role = world.make(St(), 0, "127.0.0.1", 0)
    body = obf.u64(bag_serial) + obf.u64(worn["serial"]) + obf.u16(0) + obf.u16(target)
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    returned = next(i for i in c["bag"] if i["slot"] == target)
    assert returned["serial"] == worn["serial"] and returned["count"] == 1
    assert returned["sockets"] == [-1] and returned["options"] == [[0, 23, 0.0, 2]]
    changes = [w for w in s.sent if w.proto == 0x1657]
    assert len(changes) == 1
    b = bytes(changes[0].buf)
    assert struct.unpack_from("<H", b)[0] == 1
    assert items.decode_head(b[2:]) == (worn["code"], target, 1, worn["serial"])
    assert b[2:] == items.record(returned["code"], target, returned["serial"], 1,
                                items.durability(returned), bound=returned["bound"],
                                enchant=2, sockets=[-1], options=[[0, 23, 0.0, 2]])
    assert s.sent.index(changes[0]) < next(i for i, w in enumerate(s.sent) if w.proto == world.S2C_CARGO)


def test_equipping_into_an_empty_slot_clears_the_bag_icon_before_the_snapshot():
    c = qwe123()
    c["equip"] = [it for it in c["equip"] if it["index"] != 0]
    weapon = deepcopy(next(it for it in c["bag"] if it["slot"] == 2))
    s = Session()
    s.data["char"] = c
    role = world.make(St(), 0, "127.0.0.1", 0)
    body = obf.u64(weapon["serial"]) + obf.u64(0) + obf.u16(0) + obf.u16(2)
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    assert not any(it["slot"] == 2 for it in c["bag"])
    assert next(it for it in c["equip"] if it["index"] == 0)["serial"] == weapon["serial"]
    changes = [w for w in s.sent if w.proto == world.S2C_CARGO_CHANGE]
    assert len(changes) == 1
    assert bytes(changes[0].buf) == struct.pack("<H", 1) + items.record(0xffffffff, 2, 0, count=0)
    # The removal handler reads the old item. A prior full snapshot would erase it.
    assert s.sent.index(changes[0]) < next(i for i, w in enumerate(s.sent) if w.proto == world.S2C_CARGO)


def test_refused_equip_does_not_publish_an_inventory_change():
    c = qwe123()
    before = deepcopy(c)
    s = Session()
    s.data["char"] = c
    role = world.make(St(), 0, "127.0.0.1", 0)
    body = obf.u64(0) + obf.u64(999999) + obf.u16(0) + obf.u16(34)
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    assert c == before
    assert [w.proto for w in s.sent] == [world.S2C_EQUIP]
    assert bytes(s.sent[0].buf) != bytes(2)

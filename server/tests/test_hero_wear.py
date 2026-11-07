"""What the hero may wear and show (planning/rules/HERO.md G14, V3).

G14: an item's Use Conditions (ReqHero, ReqLevel, ReqLevelMax) as its tooltip prints them, "Use Conditions: Berserker, Lv 16
or higher" (part 9 9NwV8ikwLYk f_01062, the Corps Flag Bearer Greatsword): a drag that breaks them is refused (0x164f 1,
the client's fail sound). V3: the hero window's "Look item" boxes (0x107f, LookItemCheckBoxToggle 0x1405f5b50) hide a
part; the client applies it at once, and a room's player struct (+0x88 -> player +0x108, 0x140b41500) must carry the
same mask or the room shows every part again."""
import copy
import struct

import pytest

from kuf2 import game, hero, obf, world
from test_battle import Session, pkt

FLAG_BEARER_GREATSWORD = 101316213   # REGNIER, Lv 16
SOLDIER_GREATSWORD = 101313213       # REGNIER, Lv 13
GLEN_TOP = 151111210                 # Supplied Corps Soldier Top, GLEN, Lv 11
ANY_RING = 203000010                 # Mana Guide's Accuracy Ring, ALL, Lv 28


def berserker(level, code):
    c = {"id": 1, "class": 4, "level": level, "look": bytes(56).hex(),
         "bag": [{"code": code, "slot": 0, "count": 1, "serial": 0x100010001, "bound": False}]}
    hero.equipment(c)
    return c


@pytest.mark.parametrize("level, code, index, ok", [
    (17, FLAG_BEARER_GREATSWORD, 0, True),     # the tape's Lv.17 Berserker put it on (35:34)
    (15, FLAG_BEARER_GREATSWORD, 0, False),    # below its Lv 16
    (13, SOLDIER_GREATSWORD, 0, True),
    (17, GLEN_TOP, 2, False),                  # another class's top
    (27, ANY_RING, 7, False), (28, ANY_RING, 7, True),   # ALL: any class, from its level
])
def test_an_item_goes_on_only_within_its_use_conditions(level, code, index, ok):
    c = berserker(level, code)
    worn = next((e["serial"] for e in c["equip"] if e["index"] == index), 0)
    before = copy.deepcopy(c)
    why = world.change_equip(c, 0x100010001, worn, index, 0)
    assert (why is None) == ok
    if not ok:
        assert c == before and why == hero.wear_refusal(c, code)


def test_a_refused_drag_answers_the_clients_fail_code():
    class St:
        def save(self):
            pass
    role, s = world.make(St(), 0, "127.0.0.1", 0), Session()
    c = s.data["char"] = berserker(15, FLAG_BEARER_GREATSWORD)
    worn = next(e["serial"] for e in c["equip"] if e["index"] == 0)
    body = obf.u64(0x100010001) + obf.u64(worn) + bytes([obf.via_t1(0), obf.via_t2(0), obf.via_t1(0), obf.via_t2(0)])
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    assert [bytes(w.buf) for w in s.sent] == [struct.pack("<H", world.EQUIP_FAIL)]


def test_the_look_item_boxes_are_kept_and_reach_the_rooms_player_struct():
    class St:
        saves = 0

        def save(self):
            self.saves += 1
    st = St()
    role, s = world.make(st, 0, "127.0.0.1", 0), Session()
    c = s.data["char"] = berserker(17, SOLDIER_GREATSWORD)
    assert hero.look_shown(c) == hero.LOOK_SHOWN                       # every part until a box is cleared
    hidden = hero.LOOK_SHOWN & ~(1 << 11) & ~(1 << 13)                 # two costume parts hidden
    role.handlers[world.C2S_LOOK_SHOWN](s, pkt(world.C2S_LOOK_SHOWN, struct.pack("<I", (hidden - 0x200000) & 0xffffffff)))
    assert c["look_shown"] == hidden and st.saves == 1 and s.sent == []
    p = game.player_struct(c, 10234, [])
    assert struct.unpack_from("<I", p, 0x88)[0] == hidden


def test_a_look_box_cannot_clear_the_parts_the_client_has_no_box_for():
    # live 2026-11-07 (d8_look2): with no box ticked the client sends 0000e0ff (mask 0: its 21 flags common+0xbb0 are
    # 0, nothing fills them at login), and ticking the Appearance tab's first box sent 0020e0ff (flag 13). The client
    # toggles only parts 11..20 (0x140cdf5ff); stored raw, the mask cleared the room's +0x88 bits of the worn gear.
    st = type("St", (), {"save": lambda self: None})()
    role, s = world.make(st, 0, "127.0.0.1", 0), Session()
    c = s.data["char"] = berserker(17, SOLDIER_GREATSWORD)
    for body, kept in ((bytes.fromhex("0000e0ff"), 0), (bytes.fromhex("0020e0ff"), 1 << 13)):
        role.handlers[world.C2S_LOOK_SHOWN](s, pkt(world.C2S_LOOK_SHOWN, body))
        assert c["look_shown"] == hero.NO_LOOK_BOX | kept
    assert hero.NO_LOOK_BOX == (1 << 11) - 1


# --- G20: a broken piece's stats no longer count ("If the item's durability drops to 0, the item stats will be no
# longer valid", texttutorial Item_Durability) -------------------------------------------------------------------------

def test_a_broken_piece_counts_for_nothing_until_repaired():
    c = {"id": 1, "class": 4, "level": 17, "look": bytes(56).hex(),
         "equip": [{"code": 151311210, "index": 2, "serial": 1}, {"code": SOLDIER_GREATSWORD, "index": 0, "serial": 2}]}
    whole = hero.char_stats(c)
    c["equip"][0]["dur"] = 0                                         # the Supplied Corps Soldier Top (+5,866 HP)
    worn_out = hero.char_stats(c)
    assert whole["HP_MAX"] - worn_out["HP_MAX"] == 5866
    assert hero.worn_codes(c) == [SOLDIER_GREATSWORD] and hero.look_codes(c)[2] == 151311210   # it stays on
    c["equip"][0]["dur"] = 1
    assert hero.char_stats(c)["HP_MAX"] == whole["HP_MAX"]


def test_a_death_that_breaks_a_piece_updates_the_rooms_numbers(monkeypatch):
    from kuf2 import combat
    s = Session()
    c = s.data["char"] = {"id": 1, "class": 4, "level": 17, "look": bytes(56).hex(),
                          "equip": [{"code": 151311210, "index": 2, "serial": 1, "dur": 4}]}
    s.data["battle"].add_hero(0, 0)
    s.data["battle"].troops[0]["max"] = round(hero.char_stats(c)["HP_MAX"])

    class St:
        def save(self):
            pass
    monkeypatch.setattr(world.random, "randrange", lambda n: 0)
    world.wear_down(s, St(), "DIE")
    assert c["equip"][0]["dur"] == 0 and hero.broken(c["equip"][0])
    assert s.data["battle"].troops[0]["max"] == round(hero.char_stats(c)["HP_MAX"])
    assert any(w.proto == combat.S2C_STATS for w in s.sent)


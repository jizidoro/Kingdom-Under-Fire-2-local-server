"""Saves made before hero.starter_kit wear the kit ours made up (the removed game.STARTER_EQUIP: nameless weapons
100000001.., 'Supplied Top / Trousers / Pauldrons / Gloves / Sandals' 150000001..; no quest, drop or shop in the tables
gives any of them). Owner 2026-09-30 ~18:3x: "Replace them". At login each such piece, worn or in the bag, becomes the
original set's piece for its part and class (herotable %Inventory, the Old Novice set); the original set has no sub
weapon (and Helena nothing), so those go. The saves below are server/data/db.json as of 16:50 (Aldric, qwe123)."""
import copy
import json
import logging
import pathlib
import struct

import pytest

from kuf2 import hero, net, skills, timeline, world
from test_battle import Session, pkt


def aldric():
    return {"id": 1, "name": "Aldric", "class": 0, "level": 30,
            "equip": [{"code": 150000003, "index": 4, "serial": 4294967301, "bound": True},
                      {"code": 150000004, "index": 5, "serial": 4294967302, "bound": True},
                      {"code": 150000005, "index": 6, "serial": 4294967303, "bound": True},
                      {"code": 100000002, "index": 1, "serial": 4294967298, "enchant": 0, "bound": True},
                      {"code": 107000099, "index": 0, "serial": 4295032847, "enchant": 0, "bound": True},
                      {"code": 151104113, "index": 2, "serial": 4295032859, "enchant": 0, "bound": False},
                      {"code": 152104113, "index": 3, "serial": 4295032858, "enchant": 0, "bound": False}],
            "bag": [{"code": 100000001, "slot": 1, "count": 1, "serial": 4294967297, "enchant": 0, "bound": True},
                    {"code": 151101110, "slot": 0, "count": 1, "serial": 4295032842, "bound": True},
                    {"code": 150000001, "slot": 12, "count": 1, "serial": 4294967299, "enchant": 0, "bound": True},
                    {"code": 150000002, "slot": 11, "count": 1, "serial": 4294967300, "enchant": 0, "bound": True},
                    {"code": 151106110, "slot": 10, "count": 1, "serial": 4295032868, "bound": True}]}


def qwe123():
    return {"id": 2, "name": "qwe123", "class": 3, "level": 6,
            "equip": [{"code": 150000007, "index": 3, "serial": 8589934596, "bound": True},
                      {"code": 150000008, "index": 4, "serial": 8589934597, "bound": True},
                      {"code": 150000010, "index": 6, "serial": 8589934599, "bound": True},
                      {"code": 100000004, "index": 1, "serial": 8589934594, "enchant": 0, "bound": True},
                      {"code": 101201110, "index": 0, "serial": 8590000131, "enchant": 0, "bound": True},
                      {"code": 150000006, "index": 2, "serial": 8589934595, "enchant": 0, "bound": True},
                      {"code": 154204113, "index": 5, "serial": 8590000136, "enchant": 0, "bound": False}],
            "bag": [{"code": 150000009, "slot": 7, "count": 1, "serial": 8589934598, "enchant": 0, "bound": True},
                    {"code": 100000003, "slot": 8, "count": 1, "serial": 8589934593, "enchant": 0, "bound": True},
                    {"code": 151201110, "slot": 4, "count": 1, "serial": 8590000134, "enchant": 0, "bound": True},
                    {"code": 151206110, "slot": 19, "count": 1, "serial": 8590000155, "bound": True}]}


def max_hp(c):
    return hero.stats(c["class"], c["level"], hero.worn_codes(c), hero.worn_enchants(c),
                      skills.battle_abilities(c))["HP_MAX"]


def worn(c):
    return {e["index"]: (e["code"], e["serial"]) for e in c["equip"]}


def bag(c):
    return {b["slot"]: (b["code"], b["serial"]) for b in c["bag"]}


def test_qwe123s_made_up_pieces_become_the_old_novice_set():
    c = qwe123()
    assert max_hp(c) == 459
    changes = hero.replace_made_up_kit(c)
    assert worn(c) == {0: (101201110, 8590000131),                    # the quest's Supplied Adventurer Rapier: kept
                       2: (151201119, 8589934595), 3: (152201119, 8589934596), 4: (153201119, 8589934597),
                       5: (154204113, 8590000136),                    # the Adventurer Gloves she picked up: kept
                       6: (155201119, 8589934599)}                    # index 1, the made-up sub weapon: gone
    assert bag(c) == {7: (154201119, 8589934598), 8: (101201119, 8589934593),
                      4: (151201110, 8590000134), 19: (151206110, 8590000155)}    # the quest tops: kept
    assert all(not e["bound"] and e.get("enchant", 0) == 0 for e in c["equip"] + c["bag"]
               if e["code"] in (151201119, 152201119, 153201119, 155201119, 154201119, 101201119))   # BIND_NONE
    assert max_hp(c) == 84 + 330 + 200 == 614                         # the Old Novice Top instead of 44 + 44 + 87
    assert sorted(changes) == sorted([("equip", 1, 100000004, None), ("equip", 2, 150000006, 151201119),
                                      ("equip", 3, 150000007, 152201119), ("equip", 4, 150000008, 153201119),
                                      ("equip", 6, 150000010, 155201119), ("bag", 7, 150000009, 154201119),
                                      ("bag", 8, 100000003, 101201119)])


def test_aldrics_made_up_pieces_become_the_old_novice_set():
    c = aldric()
    assert max_hp(c) == 6133                                          # 69 Survival at level 6 (+3,000) at level 30
    hero.replace_made_up_kit(c)
    assert worn(c) == {0: (107000099, 4295032847), 2: (151104113, 4295032859), 3: (152104113, 4295032858),
                       4: (153101119, 4294967301), 5: (154101119, 4294967302), 6: (155101119, 4294967303)}
    assert bag(c) == {1: (101101119, 4294967297), 0: (151101110, 4295032842), 12: (151101119, 4294967299),
                      11: (152101119, 4294967300), 10: (151106110, 4295032868)}
    assert max_hp(c) == 1376 + 1648 + 3000 == 6024                   # the made-up Pauldrons' 109 HP went with them


def test_a_second_run_changes_nothing_and_a_new_hero_has_nothing_to_replace():
    for c in (qwe123(), aldric()):
        hero.replace_made_up_kit(c)
        after = copy.deepcopy(c)
        assert hero.replace_made_up_kit(c) == [] and c == after
    c = {"id": 3, "name": "new", "class": 4, "level": 1, "bag": []}
    hero.equipment(c)
    before = copy.deepcopy(c)
    assert hero.replace_made_up_kit(c) == [] and c == before


def test_worn_down_or_socketed_state_does_not_carry_over():
    c = qwe123()
    top = next(e for e in c["equip"] if e["index"] == 2)
    top.update(dur=40, sockets=[-1, 404000100])
    hero.replace_made_up_kit(c)
    assert "dur" not in top and "sockets" not in top and top["code"] == 151201119


@pytest.fixture
def journal(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(net, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(net, "LOG_DIR", tmp_path)
    path = net.open_journal()
    yield path
    net.close_journal()


class St:
    saves = 0

    def save(self):
        self.saves += 1


def test_login_replaces_them_logs_journals_and_saves_once(journal, caplog):
    st = St()
    role = world.make(st, 0, "127.0.0.1", 0)
    c = qwe123()
    c.update(tutorial_done=True, spot=world.START_SPOT, pos=list(world.START_POS))
    s = Session()
    s.data["account"] = {"characters": [c]}
    with caplog.at_level(logging.INFO, logger=net.log.name):
        role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 2, 0)))
    assert worn(c)[2] == (151201119, 8589934595) and st.saves >= 1
    assert any("qwe123" in r.getMessage() and "151201119" in r.getMessage() for r in caplog.records)
    events = [json.loads(x) for x in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
    gear = [e for e in events if e["k"] == "gear"]
    assert len(gear) == 1 and gear[0]["id"] == 2 and gear[0]["name"] == "qwe123"
    assert ["equip", 2, 150000006, 151201119] in gear[0]["replaced"] and gear[0]["hp"] == [459, 614]
    text = timeline.server_text(gear[0])
    assert text.startswith("character 2 'qwe123': made-up kit replaced (") and text.endswith("; HP 459 -> 614")
    assert "equip 1 100000004 -> removed" in text and "bag 8 100000003 -> 101201119" in text
    saves = st.saves
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 2, 0)))
    events = [json.loads(x) for x in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
    assert len([e for e in events if e["k"] == "gear"]) == 1 and st.saves == saves     # the second login: nothing

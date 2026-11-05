"""Observed level-6 field failure: surviving hits, active AI, empty TroopAggro.

Pin 0x50b4's native reader layout and the solo hero target's lifetime. These do not
establish the original server's multi-attacker threat ranking or decay formula.
"""
import struct

import pytest

from kuf2 import combat, game
from test_battle import FieldSession, NoSave, enc_uid, pkt


NPC = 10359


def room(spot=10359, team=1):
    s = FieldSession({"active": {}, "done": []})
    s.data.update(spot=spot, bound={0, NPC},
                  zone_troops={NPC: {"TeamNum": team, "TroopTableID": 163040}})
    s.data["battle"].add_hero(0, 614)
    s.data["battle"].add_np(NPC, 123, 1)
    return s


def hit(s, source=0, target=NPC, amount=11):
    combat.apply_hits(s, [(target, [0])], lambda *args: None, attacker=source,
                      attack={"damage": amount})


def lists(s):
    return [bytes(w.buf) for w in s.sent if w.proto == 0x50b4]


@pytest.fixture(autouse=True)
def fixed_damage(monkeypatch):
    monkeypatch.setattr(combat, "resolve_hit", lambda a, b, attack, *args, **kwargs:
                        (attack["damage"], 0))


@pytest.mark.parametrize("spot", [10359, 20906])
def test_surviving_field_hit_supplies_hero_target_without_resetting_it_each_hit(spot):
    s = room(spot)
    hit(s)
    assert s.data["battle"].troops[NPC]["units"] == [112]
    assert lists(s) == [struct.pack("<BHBH", 1, NPC, 1, 0)]
    hit(s)
    assert len(lists(s)) == 1


@pytest.mark.parametrize("spot,team,source,amount", [
    (10233, 1, 0, 11), (999999, 1, 0, 11), (10359, 0, 0, 11),
    (10359, 250, 0, 11), (10359, 255, 0, 11), (10359, 1, NPC, 11),
    (10359, 1, 0, 0), (10359, 1, 0, 123),
])
def test_no_target_for_mission_unknown_room_allies_neutrals_nonhero_no_damage_or_kill(spot, team, source, amount):
    s = room(spot, team)
    hit(s, source=source, amount=amount)
    assert lists(s) == []


@pytest.mark.parametrize("missing", [0, NPC])
def test_unbound_object_does_not_get_a_target(missing):
    s = room()
    s.data["bound"].remove(missing)
    hit(s)
    assert lists(s) == []


def test_forced_return_clears_target_without_healing_and_new_hit_can_rearm():
    s = room()
    hit(s)
    role = game.make(NoSave(), 0)
    role.handlers[0x50e8](s, pkt(0x50e8, enc_uid(NPC) + b"\0"))
    assert lists(s)[-1] == struct.pack("<BHB", 1, NPC, 0)
    assert s.data["battle"].troops[NPC]["units"] == [112]
    count = len(lists(s))
    role.handlers[0x50e8](s, pkt(0x50e8, enc_uid(NPC) + b"\0"))
    assert len(lists(s)) == count
    hit(s)
    assert lists(s)[-1] == struct.pack("<BHBH", 1, NPC, 1, 0)


@pytest.mark.parametrize("body", [b"", b"\0", b"\0\0", enc_uid(65535)+b"\0", enc_uid(NPC)+b"\1"])
def test_bad_or_other_return_notice_does_not_clear(body):
    s = room()
    hit(s)
    before = lists(s)
    game.make(NoSave(), 0).handlers[0x50e8](s, pkt(0x50e8, body))
    assert lists(s) == before


@pytest.mark.parametrize("victim", [NPC, 0])
def test_npc_or_hero_death_clears_the_live_target(victim):
    s = room()
    hit(s)
    hit(s, source=NPC if victim == 0 else 0, target=victim, amount=1000)
    assert lists(s)[-1] == struct.pack("<BHB", 1, NPC, 0)


def test_reused_uid_gets_fresh_target_after_new_bind():
    s = room()
    hit(s)
    hit(s, amount=1000)
    s.data["battle"].add_np(NPC, 123, 1)
    s.data["bound"].discard(NPC)
    hit(s)
    assert lists(s)[-1] == struct.pack("<BHB", 1, NPC, 0)
    s.data["bound"].add(NPC)
    hit(s)
    assert lists(s)[-1] == struct.pack("<BHBH", 1, NPC, 1, 0)


def test_dead_hero_cannot_be_reintroduced_by_a_late_hit():
    s = room()
    s.data["battle"].troops[0]["hp"] = 0
    hit(s)
    assert lists(s) == []


def test_clearing_one_target_does_not_forget_another_enemy():
    s = room()
    other = NPC + 1
    s.data["battle"].add_np(other, 123, 1)
    s.data["zone_troops"][other] = dict(s.data["zone_troops"][NPC])
    s.data["bound"].add(other)
    hit(s)
    hit(s, target=other)
    combat.clear_field_retaliation(s, NPC)
    before = len(lists(s))
    hit(s, target=other)
    assert len(lists(s)) == before
    combat.clear_field_retaliation(s, 0)
    assert lists(s)[-1] == struct.pack("<BHB", 1, other, 0)

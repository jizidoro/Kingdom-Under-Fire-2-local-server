"""Evolution must keep identity/progress and produce skills that the resulting troop can actually use."""
from copy import deepcopy
import struct

import pytest

from kuf2 import quest, troops
from test_vanilla_items import rig, put, reply
from test_army import entered, troop_entries


def test_training_advances_active_quest_by_levels_without_throwing(rig):
    r = rig
    t, _ = troops.grant(r.c, 1)
    cost = troops.troop_need(100, 6) + troops.troop_need(100, 7)
    r.c["barrack_exp"] = cost
    quest.record(r.c)["active"]["9900332"] = {"counts": [0] * quest.CONDITIONS}
    gold = r.c["gold"]
    r.call(troops.C2S_TRAIN, struct.pack("<QQQ", 0, cost, t["uid"]))
    assert reply(r, troops.S2C_TRAIN)[:2] == bytes(2)
    assert (t["level"], t["exp"], r.c["barrack_exp"]) == (8, 0, 0)
    assert r.c["gold"] == gold - troops.training_gold(100, [6, 7])
    assert r.c["quests"]["active"]["9900332"]["counts"][0] == 2
    assert r.st.saved == r.c


@pytest.mark.parametrize("proto", [troops.C2S_EQUIP_SKILL, troops.C2S_LEARN_SKILL])
def test_academy_unlock_does_not_bypass_troop_rarity_requirement(rig, proto):
    r = rig
    t, _ = troops.grant(r.c, 1)
    t["id"] = 1100111  # Rarity-1 Long Swordsman; group includes a SkillGrade-5 variant.
    r.c["tactics"] = {"70144": {"level": 1, "exp": 0}}
    before = deepcopy(r.c)
    body = struct.pack("<QI", t["uid"], 70144) if proto == troops.C2S_EQUIP_SKILL else struct.pack("<IQ", 70144, t["uid"])
    r.call(proto, body)
    assert reply(r, troops.S2C_EQUIP_SKILL if proto == troops.C2S_EQUIP_SKILL else troops.S2C_LEARN_SKILL)[:2] != bytes(2)
    assert r.c == before and r.st.saves == 0


def test_promotion_replaces_incompatible_skill_before_the_next_battle(rig):
    r = rig
    t, _ = troops.grant(r.c, 1)
    t.update(exp=77, ap=20)
    put(r, 354000000, 10)
    put(r, 354100000, 10)
    troops.lineup(r.c)["slots"][1] = t["uid"]
    uid = t["uid"]
    r.call(troops.C2S_PROMOTE, struct.pack("<QQIQ", uid, 0, 1000000, 0))
    assert reply(r, troops.S2C_PROMOTE)[:2] == bytes(2)
    assert (t["uid"], t["id"], t["level"], t["exp"], t["ap"]) == (uid, 1100111, 6, 77, 100)
    assert troops.equipped(r.c, t) == [(0, 70142, 1)]  # Shield Use 81001 belongs only to the former troop's groups.
    assert troops.lineup(r.c)["slots"][1] == uid
    r.c["look"] = "00" * 0x38
    _, room = entered(10234, r.c)
    _, deck = troop_entries(room)
    assert deck["abilities"] == [(1, 70142)]
    assert r.st.saved["troops"][0]["skills"] == t["skills"]


def test_old_promoted_save_is_repaired_once_without_reequipping_valid_removed_skills(rig):
    r = rig
    t, _ = troops.grant(r.c, 1)
    t["id"] = 1100111
    assert troops.give_default_skills(r.c) == 1
    assert troops.equipped(r.c, t) == [(0, 70142, 1)]
    assert troops.give_default_skills(r.c) == 0
    t["skills"][0]["slot"] = troops.UNEQUIPPED
    before = deepcopy(t)
    assert troops.give_default_skills(r.c) == 0 and t == before


def test_rarity_locked_academy_skill_is_not_auto_equipped_on_new_troops(rig):
    r = rig
    r.c["tactics"] = {"70144": {"level": 1, "exp": 0}, "70146": {"level": 1, "exp": 0}}
    assert troops.default_skills(r.c, 1100111) == [{"slot": 0, "id": 70142}]


def test_skill_requirement_uses_rarity_not_tech_grade(rig):
    r = rig
    t, _ = troops.grant(r.c, 1)
    t["id"] = 1100112  # GRADE1, RARITY2: a SkillGrade-2 passive is allowed.
    r.c["tactics"] = {"70148": {"level": 1, "exp": 0}}
    assert troops.skill_allowed(t["id"], 70148)
    r.call(troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], 70148))
    assert reply(r, troops.S2C_EQUIP_SKILL)[:2] == bytes(2)
    assert (4, 70148, 1) in troops.equipped(r.c, t, troops.PASSIVE_SLOTS)

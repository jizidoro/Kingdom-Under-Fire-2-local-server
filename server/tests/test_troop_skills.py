"""Troop skills on the troop bar (C1-C4 / CQ-CR under a troop's HUD panel), owner live 2026-09-30 15:13 in Grey Rock:
"trops skills are not been loaded to the bar". The client builds a troop's four slots in 0x1408ead40: a troop with a
barracks record (0x3f50 T+9 -> troop +0x7e0, record found by 0x140d979c0) takes the record's skill list (+0x250, the
0x1749 troop block) entries whose first byte is below 4, that byte the slot; any other troop (a zone troop handed to
the player) takes its ability manager's slots 0-3 (troop +0x1088, 0x140840970), which a 0x50cb troop gets only from
its entry's first ability list, the place in the list the slot (MakeTroopGenInfoForBuild 0x140cf7080). The original
(playthrough part 2, 36:22, f_01092): Grey Rock's F1 (troop 100) shows Shield Use I 81001 in C1, the handed archers
134060 their Fire Arrow 500045 in CQ; Tower (12:22, f_00372) the archers 133120 their ACTIVESKILL08 200147 in the
first slot and 10100 (133270, passives only) nothing.
Run: py -m pytest -q server/tests"""
import struct

from kuf2 import game, obf, skills, troops, world
from test_army import NoSave, army, entered, pkt, troop_entries, troops_role


def ability_lists(s):
    """{uid: [(level, ability)]} of the first ability list (0x140d0e060) of every 0x50cb entry sent."""
    out = {}
    for w in s.sent:
        if w.proto != game.S2C_ENTER_CELL_TROOP:
            continue
        b = bytes(w.buf)
        st = b[3:3 + 0x3d]
        i = 3 + 0x3d
        np = obf.T1[b[i]] & 1
        i += 1 + (22 if np else 0)
        n = struct.unpack_from("<H", b, i)[0]
        out[struct.unpack_from("<H", st, 0x11)[0]] = [struct.unpack_from("<BI", b, i + 2 + 5 * k) for k in range(n)]
    return out


def detail_skills(t, c=None):
    """(slot, level, ability) of a troop's 0x1349 detail (c: its character, the academy's levels)."""
    c = c or {}
    b = bytes(troops.detail_packet(c, t).buf)
    n = b[10]
    return [struct.unpack_from("<BBI", b, 11 + 6 * k) for k in range(n)]


def info_block(c, t):
    """(first byte, ability, level) of the troop block of the 0x1749 a 0x1748 for troop t gets."""
    from kuf2.net import Role
    role = Role("world", 0, None)
    skills.make(role, NoSave())

    class S:
        data = {"char": c}
        sent = []

        def send(self, w):
            self.sent.append(w)
    s = S()
    role.handlers[skills.C2S_INFO](s, pkt(skills.C2S_INFO, struct.pack("<QQ", t["uid"], 0)))
    b = bytes(s.sent[-1].buf)
    assert struct.unpack_from("<Q", b)[0] == t["uid"]
    n = b[10]
    return [struct.unpack_from("<BIB", b, 11 + 6 * k) for k in range(n)]


def test_a_new_troop_comes_with_its_first_held_skill_in_each_active_slot():
    # troop 100 (the first contract, set 1): MaxActiveSkill 1, %NewSkill A_1 = group 100 (81001, 81014), both
    # tacticsacademy AbilityMinLevel 1: 81001 in slot 0 at level 1, as the original's Grey Rock HUD shows it
    c, (t,) = army(1)
    assert t["skills"] == [{"slot": 0, "id": 81001}] and troops.skill_level(c, 81001) == 1
    # the Greywood archers 2202311: MaxActiveSkill 2; A_1 (70192 min level 1, 70193 min 0) -> 70192; A_2's only skill
    # 70194 is AbilityMinLevel 0 (not held until learned at the academy): no second skill
    c, (t,) = army(2202311)
    assert t["skills"] == [{"slot": 0, "id": 70192}]
    # a skill learned at the tactics academy is held at its level there (the level is read where it is sent)
    c["tactics"] = {"70194": {"level": 3, "exp": 0}}
    assert troops.default_skills(c, 2202311) == [{"slot": 0, "id": 70192}]  # SkillGrade 3 needs RARITY3.
    assert troops.default_skills(c, 2202313) == [{"slot": 0, "id": 70192}, {"slot": 1, "id": 70194}]
    assert troops.skill_level(c, 70194) == 3


def test_the_detail_and_the_skill_list_carry_the_equipped_skill_in_its_slot():
    c, (t,) = army(1)
    assert detail_skills(t) == [(0, 1, 81001)]                     # 0x1349: the troop windows' 4 slots (+0x288)
    assert info_block(c, t) == [(0, 81001, 1)]                     # 0x1749: the list the room's C1-C4 read (+0x250)
    # the first byte is the slot, not the place in the list (a skill in slot 2 alone showed in C1 before)
    t["skills"] = [{"slot": 2, "id": 81014}, {"slot": troops.UNEQUIPPED, "id": 81001}]
    assert info_block(c, t) == [(2, 81014, 1)]      # one in no slot is not listed: 4..7 are the passive slots, and
    assert detail_skills(t) == [(2, 1, 81014)]      # the equip window marks every listed id equipped (0x1409b2a30)


def test_a_deck_troop_takes_its_equipped_skill_into_the_room():
    # Grey Rock 10234: the deck troop's 0x3f50 ability list (u8 level, u32 ability) carries 81001, so the troop can
    # use what its C1 shows
    c, _ = army(1)
    _, s = entered(10234, c)
    hero, deck = troop_entries(s)
    assert deck["uid"] == 1 and deck["abilities"] == [(1, 81001)]


def test_the_handed_troops_carry_their_table_skills_in_their_cell_entry():
    # Grey Rock hands 10073 (134060, ACTIVESKILL01 500045 Lv 1): its 0x50cb list; Glen's 10072 (134070: 81001 in its
    # row) carries its own too since every NP troop does (tests/test_np_skills.py; owner 2026-09-30: vanilla)
    c, _ = army(1)
    _, s = entered(10234, c)
    lists = ability_lists(s)
    assert lists[10073] == [(1, 500045)]
    assert lists[10072] == [(1, 81001)]
    # Tower 10233: 11006 (133120, handed later at the wyrms) holds ACTIVESKILL08 200147 Lv 8, first in its list (the
    # original showed it in the first slot); 10100 (133270) has passives only: an empty list, an empty bar
    c, _ = army()
    _, s = entered(10233, c)
    lists = ability_lists(s)
    assert lists[11006] == [(8, 200147)] and lists[10100] == []
    # the archers' camp 10345: the mock battle's three (held force F12500, HAND_LATER) come later by a step, and
    # carry their row's six actives in column order (C1-C4 the first four)
    c, _ = army()
    _, s = entered(10345, c)
    assert 10153 not in ability_lists(s)
    game.spawn_troops(s, [10153])
    assert ability_lists(s)[10153] == [(4, 200117), (5, 70104), (5, 70100), (5, 70096), (5, 10089), (5, 60030)]


def test_troops_saved_without_skills_get_their_defaults_at_login():
    # qwe123's troop 100 (db.json 2026-09-30: "skills": []) was granted before troops came with skills
    c, (t,) = army(1)
    t["skills"] = []
    role = world.make(Saves(), 0, "127.0.0.1", 0)
    s = WorldSession(c)
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))
    assert t["skills"] == [{"slot": 0, "id": 81001}] and Saves.n >= 1


def test_an_unequipped_skill_stays_learned_and_is_not_given_again():
    c, (t,) = army(1)
    role = troops_role()
    s = WorldSession(c)
    role.handlers[troops.C2S_UNEQUIP_SKILL](s, pkt(troops.C2S_UNEQUIP_SKILL, struct.pack("<QI", t["uid"], 81001)))
    assert t["skills"] == [{"slot": troops.UNEQUIPPED, "id": 81001}]
    out = bytes(s.sent[-1].buf)                                    # the resent detail (0x1349) clears the slot
    assert s.sent[-1].proto == troops.S2C_DETAIL and out[10] == 0 and detail_skills(t) == []
    assert troops.give_default_skills(c) == 0                       # the next login leaves the choice alone
    # equipping the other skill of the group into the slot keeps the first learned
    role.handlers[troops.C2S_EQUIP_SKILL](s, pkt(troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], 81001)))
    role.handlers[troops.C2S_EQUIP_SKILL](s, pkt(troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], 81014)))
    assert sorted((k["id"], k["slot"]) for k in t["skills"]) == [(81001, troops.UNEQUIPPED), (81014, 0)]


class Saves:
    n = 0

    def save(self):
        Saves.n += 1


class WorldSession:
    def __init__(self, c):
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}}
        self.sent = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        pass

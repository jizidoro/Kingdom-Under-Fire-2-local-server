"""God's Blessing, the gear score (planning/rules/HERO.md S14, S15, B6; COMBAT H18).

The Info panel's first row, "Blessing Stats / God's Blessing" (text 52346), is the block's MDP (0x134b +0x10): the tape's
panels read 0 (part 9 9NwV8ikwLYk f_01059 and f_01069, Lv.17, every piece named in its tooltips) with gear whose MDP
column is 0 (the panels at Lv.5, 10, 11 and 22 read 0 too, their gear not all named), and an item's tooltip prints its
column as a stat line: aMS5MxRFmSU f_01436, the Senior Centurion Ring B, "[Hero] God's Blessing : +34"
(its MDP 34). The mission's band (spottable %Mdp, 28 spots) puts 1027 MDP_DOWN below the recommended value (text 52347
"Hero's power decreases when there's not enough God's Blessing": ATTACK -20 / -30 / -40 %, heals cut 50 / 75 / 90 %) or
1029 MDP_UP above it (OFFICIAL-NOTES: "the 30% damage buff for high gear score")."""
import struct

import pytest

from kuf2 import combat, game, hero, items, status, world
from test_battle import Session
from test_hero_panel import PANELS

BERSERKER = 4
RING = 201324412                   # Senior Centurion Ring B (REGNIER), MDP 34
TOP = 153000103                    # Relentless Royal Top (GLEN), MDP 780


def test_the_tapes_panels_read_no_blessing_with_their_gear():
    """S14 / S15: the Lv.17 panels' gear sums to 0, as their God's Blessing row."""
    for frame, at, worn, *_ in PANELS:
        assert hero.mdp(worn) == 0
        assert hero.stats(BERSERKER, 17, worn)["MDP"] == 0


def test_the_blessing_is_the_worn_items_mdp_summed_and_reaches_the_block():
    c = {"id": 1, "class": BERSERKER, "level": 24, "equip": [{"code": RING, "index": 7, "serial": 1}]}
    assert items.row(RING)["MDP"] == "34" and items.name(RING) == "Senior Centurion Ring B"
    block = world.hero_block(c)
    assert struct.unpack_from("<i", block, world.HERO_STAT_AT["MDP"])[0] == 34
    c["equip"].append({"code": RING, "index": 8, "serial": 2})          # two rings, both counted
    assert struct.unpack_from("<i", world.hero_block(c), world.HERO_STAT_AT["MDP"])[0] == 68


BANDS = [   # (spot, difficulty, God's Blessing, (status, level) or None): spottable %Mdp rows
    (20950, 0, 0, (1027, 2)), (20950, 0, 700, (1027, 2)), (20950, 0, 701, (1027, 1)), (20950, 0, 959, (1027, 1)),
    (20950, 0, 960, None), (20950, 0, 1199, None), (20950, 0, 1200, (1029, 1)), (20950, 0, 1400, (1029, 2)),
    (10546, 1, 500, (1027, 1)), (10546, 2, 1850, (1029, 2)), (10546, 2, 1000, None),
    (10234, 0, 0, None),                                                 # Grey Rock: no row, nothing
]


@pytest.mark.parametrize("spot, difficulty, mdp, want", BANDS)
def test_the_missions_band_picks_its_status(spot, difficulty, mdp, want):
    assert status.blessing_status(spot, difficulty, mdp) == want


def room(spot, worn, difficulty=0):
    s = Session()
    c = s.data["char"] = {"id": 1, "class": 0, "level": 30,
                          "equip": [{"code": code, "index": i, "serial": i + 1} for i, code in enumerate(worn)]}
    s.data["account"] = {"id": 9, "characters": [c]}
    s.data.update(spot=spot, difficulty=difficulty)
    s.data["battle"].add_hero(0, 10000)
    return s


def test_a_room_start_puts_the_band_on_the_hero_and_his_attack_follows():
    """B6: 20950 Normal, 780 blessing (a Relentless Royal Top): 1027 at level 1 (701-959), ATTACK -20 % on his hits."""
    s = room(20950, [TOP])
    status.room_start(s)
    assert status.holding(s, 0)[1027]["level"] == 1
    assert combat.status_bonus({1027: 1}, "ATTACK_PHYSICAL", leader=True) == (-20.0, 0.0)
    assert combat.status_bonus({1029: 2}, "ATTACK_MAGICAL", leader=True) == (30.0, 0.0)


def test_a_story_room_puts_nothing():
    s = room(10234, [TOP])
    status.room_start(s)
    assert 1027 not in status.holding(s, 0) and 1029 not in status.holding(s, 0)


def test_the_band_comes_back_after_a_revive():
    s = room(20950, [TOP])
    status.room_start(s)
    status.revived(s)
    assert 1027 in status.holding(s, 0)


def test_the_debuff_cuts_a_potions_heal_by_its_share():
    """1027 level 1: HP_HEAL_REDUCE 50 %: a 600 potion heals 300."""
    s = room(20950, [TOP])
    t = s.data["battle"].troops[0]
    t["hp"], t["max"] = 1000, 10000
    status.room_start(s)
    game.heal_hero(s, 600)
    assert t["hp"] == 1300
    assert combat.regen_share(s, 0) == 1.0                              # its function is the heals', not regeneration's

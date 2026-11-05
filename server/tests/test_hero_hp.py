"""The hero's max HP against the original's HUD. Owner 2026-09-30 ~17:2x: "the hp for that stage is too low" (qwe123,
ISABELLA level 6, 459 HP in Grey Rock).

The tape: Sorrowh's Berserker (REGNIER, class 4) in playthrough parts 1 (tiouWoPSPks) and 2 (qeeQjhgO8ss), frames
cached in captures/video/<video>_0_<length>_frames_0.5 (f_<n> is (n - 1) * 2 s in). Every
full-bar HP the hero HUD shows is lvuptypetable %Hero_HP LV_<level> + the worn items' HP_MAX + the held passives'
(REGNIER's +400 from level 4), exactly: the rule hero.stats already had. The item swaps are on screen too: at part 2
27:35 (qeeQjhgO8ss_1655_1661_frames_2 f_00004) the tooltips read Supplied Adventurer Top "Max HP +469" and Supplied
Trainee Top "+2815", the tables' values, and the HUD drops from 994 to 525 (994 - 469) on the swap.

What was not the original's: the class kit a new hero wears. The level-1 HUD reads 450 = LV_1 38 + the Old Novice
Top's 412 (herotable %Inventory, the class's creation kit); ours was a made-up kit (item codes 1500000xx, 'Supplied
Top / Trousers / Pauldrons' 66 / 66 / 131 HP for REGNIER, 44 / 44 / 87 for ISABELLA, and 1000000xx weapons with no
attack), 301 HP at level 1. qwe123's 459 is her gear:
she wears that kit's Supplied Top (her own swap back at 14:21:31) and the Supplied Trainee Top (2,252 HP, quest
'Sorting Rubbish' 15:11:05) sits in her bag; worn, she has 2,667 at level 6, as the original's Berserker had 3,340."""
import pytest

from kuf2 import hero, skills, tables

OLD_NOVICE_TOP, SUPPLIED_ADVENTURER_TOP, SUPPLIED_TRAINEE_TOP = 151301119, 151301110, 151306110   # REGNIER's
TAPE = [   # (video, frame, time, hero level, upper body worn, the HUD's HP with the bar full)
    ("tiouWoPSPks", "f_00241", "8:00", 1, OLD_NOVICE_TOP, 450),              # Azilia, the creation kit
    ("tiouWoPSPks", "f_00616", "20:30", 2, OLD_NOVICE_TOP, 467),
    ("tiouWoPSPks", "f_00781", "26:00", 2, SUPPLIED_ADVENTURER_TOP, 524),
    ("tiouWoPSPks", "f_01036", "34:30", 3, SUPPLIED_ADVENTURER_TOP, 541),
    ("qeeQjhgO8ss", "f_00166", "5:30", 4, SUPPLIED_ADVENTURER_TOP, 958),     # the passive's +400 from level 4
    ("qeeQjhgO8ss", "f_00200", "6:38", 4, SUPPLIED_ADVENTURER_TOP, 958),     # Tower of Moonlight
    ("qeeQjhgO8ss", "f_00796", "26:30", 6, SUPPLIED_ADVENTURER_TOP, 994),    # Mist Field village
    ("qeeQjhgO8ss", "f_01066", "35:30", 6, SUPPLIED_TRAINEE_TOP, 3340),      # Grey Rock
    ("qeeQjhgO8ss", "f_01186", "39:30", 6, SUPPLIED_TRAINEE_TOP, 3340),
    ("6uClEdAS__k", "f_00301", "10:00", 7, SUPPLIED_TRAINEE_TOP, 3388),      # part 3: + LV_7 - LV_6 = 48
]
SUPPLIED_TRAINEE_SET = [101306110, 102306110, 151306110, 152306110, 153306110, 154306110, 155306110]


def new_hero(cls, level):
    return {"id": 1, "class": cls, "level": level}


def max_hp(c):
    return hero.stats(c["class"], c["level"], hero.worn_codes(c), hero.worn_enchants(c),
                      skills.battle_abilities(c))["HP_MAX"]


@pytest.mark.parametrize("video, frame, at, level, top, hp", TAPE)
def test_the_berserkers_hp_is_the_originals_hud(video, frame, at, level, top, hp):
    c = new_hero(4, level)
    for e in hero.equipment(c):                        # the class kit, the upper body as worn on the tape
        if e["index"] == 2:
            e["code"] = top
    assert max_hp(c) == hp


def test_the_full_supplied_trainee_set_adds_its_seven_piece_bonus():
    """Part 3 f_00481 (16:00), Lv.8: 3,802 = LV_8 221 + the top's 2815 + the passive's 400 + the set's "7 set Effect
    [Hero] Max HP : +366" (its tooltip, part 2 27:35). Later, f_01301 (43:20) Lv.9: 4,250 = 269 + 2815 + 366 + 800,
    the passive 715 at its level 2 (RequireHeroLevelUpCycle 5: from hero level 9, skills.auto_level; the level-up
    itself is off tape, the rule is pinned at Lv.17: tests/test_hero_rules.py)."""
    c = {"id": 1, "class": 4, "level": 8,
         "equip": [{"code": code, "index": i, "serial": i + 1} for i, code in enumerate(SUPPLIED_TRAINEE_SET)]}
    assert max_hp(c) == 3802
    c.update(level=9)
    assert max_hp(c) == 4250


def test_a_new_hero_wears_the_class_kit_of_herotable_inventory():
    rows = tables.sections("herotable")["Inventory"]
    for cls, code in enumerate(hero.HERO_CODE):
        kit = {r["InventoryId"]: int(r["ItemCode"]) for r in rows if r["CHARACTER_TYPE"] == code}
        worn = {e["index"]: e["code"] for e in hero.equipment(new_hero(cls, 1))}
        assert worn == {i: kit[part] for i, part in enumerate(("MAIN_WEAPON", "SUB_WEAPON", "UPPERBODY", "LOWERBODY",
                                                                "SHOULDER", "GAUNTLET", "BOOTS")) if kit[part] != -1}
    assert hero.equipment(new_hero(4, 1))[0]["code"] == 101301119            # Old Novice Greatsword
    assert hero.equipment(new_hero(5, 1)) == []                               # Helena's rows are all -1


# HP_MAX = Hero_HP LV_<level> + the kit's Old Novice Top + the class's HP passive at the level it holds then (it levels
# with the hero, skills.auto_level: GLEN 69 300 / 600 / 3,000 at levels 6 / 10 / 30; OLIVIA 975, ISABELLA 369 and
# DRUID 1291 200 / 500 / 2,300; REGNIER 715 400 / 800 / 3,600; from level 4, DRUID's from 3; HELENA none); HELENA's HP
# row is her own curve, no kit
KIT_HP = {  # class: {level: HP_MAX}
    0: {1: 31 + 371, 6: 104 + 371 + 300, 10: 264 + 371 + 600, 30: 1376 + 371 + 3000},
    1: {1: 25 + 309, 6: 84 + 309 + 200, 10: 212 + 309 + 500, 30: 1096 + 309 + 2300},
    2: {1: 20 + 288, 6: 68 + 288 + 200, 10: 172 + 288 + 500, 30: 894 + 288 + 2300},
    3: {1: 25 + 330, 6: 84 + 330 + 200, 10: 212 + 330 + 500, 30: 1096 + 330 + 2300},
    4: {1: 38 + 412, 6: 125 + 412 + 400, 10: 317 + 412 + 800, 30: 1651 + 412 + 3600},
    5: {1: 397, 6: 651, 10: 854, 30: 1868},
}


@pytest.mark.parametrize("cls", range(6))
def test_every_class_in_its_kit_has_the_tables_hp(cls):
    assert {level: max_hp(new_hero(cls, level)) for level in (1, 6, 10, 30)} == KIT_HP[cls]


def test_qwe123s_hp_is_her_gear():
    """Her save of 2026-09-30 17:2x: 459 in the kit's pieces; the Supplied Trainee Top from her bag makes 2,667."""
    worn = [150000007, 150000008, 150000010, 100000004, 101201110, 150000006, 154204113]
    abilities = skills.battle_abilities({"id": 2, "class": 3, "level": 6})
    assert hero.stats(3, 6, worn, abilities=abilities)["HP_MAX"] == 84 + 44 + 87 + 44 + 200 == 459
    worn[worn.index(150000006)] = 151206110                                    # Supplied Trainee Top, 2,252
    assert hero.stats(3, 6, worn, abilities=abilities)["HP_MAX"] == 84 + 44 + 87 + 2252 + 200 == 2667


def test_the_heros_damage_record_counts_his_kit_passives_like_his_info_window():
    # rules census HERO gap 4 / the troop-skills builder 2026-09-30: the Info window (world.hero_block) passes the kit
    # passives (skills.battle_abilities) to hero.stats, the damage record (game.hero_combatant) did not, so a passive's
    # attack / crit / penetration showed in the window and never reached a hit
    from kuf2 import combat, game, hero, skills
    for c in (new_hero(4, 6), new_hero(3, 6), new_hero(0, 30)):   # Regnier's +400 HP passive from level 4
        named = hero.stats(c["class"], c.get("level", 1), hero.worn_codes(c), hero.worn_enchants(c),
                           skills.battle_abilities(c))
        named.setdefault("GUARD_REDUCE", game.HERO_STATS.get(c["class"], {}).get(42, 0))
        want = combat.combatant_hero(named, c.get("level", 1), c["class"], game.PLAYER_TEAM)
        assert game.hero_combatant(c) == want

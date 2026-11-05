"""The hero's Info panel rebuilt from the tables against the original's (planning/rules/HERO.md S3, S8, N1).

Part 9 (9NwV8ikwLYk, captures/video/9NwV8ikwLYk_0_2168_frames_0.5, f_<n> = (n - 1) x 2 s),
Sorrowh's Lv.17 Berserker (REGNIER, class 4) in Accolade, the Info window open with every worn piece's tooltip nearby:
  f_01058 35:14  the main weapon: Corps Soldier Greatsword (101313213) "Physical Attack 134 ~ 149, Magic 68 ~ 76,
                 Physical Critical Attack +820, Magic +581, Phys. Def. Penetration +522, Enchantment 0 / 3"
  f_01059 35:16  the panel: Physical Attack 345 ~ 360, Magic 233 ~ 241, Attack Speed 100, Phys. Def. Penetration 522,
                 Magic 779, Physical Critical Rate 274, Attack 1320, Magic 225 / 1081, Hit 585, Melee / Ranged Physical
                 Defence 1683; HUD HP 8,527 (the bar full)
  f_01064 35:26  the gauntlets worn: Supplied Corps Flag Bearer Gauntlets (102316210; set 3 / 7 with the shoulders and
                 gloves: the 3-set tier "Movement Speed +0.60, HP Recovery +14")
  f_01065 35:28  the top worn at 35:16: Supplied Corps Soldier Top +1 (151311210, "+371 / +164 / Max HP +5866",
                 enchant 1 / 3); after the swap to Supplied Corps Flag Bearer Top (151316210) the HUD reads 11,193
  f_01066 35:30  Supplied Corps Flag Bearer Shoulders (153316210, "+270 / +179 / Critical Rate Resistance +116")
  f_01067 35:32  Corps Soldier Bottoms (152313213, "+278 / +278 / HP Recovery +56"); the set lists name Supplied Corps
                 Soldier Shoes (155311210, "+1" on its icon) and the gloves are the Flag Bearer set's (154316210: its
                 ACCURACY 585 is the panel's Hit)
  f_01069 35:36  after the weapon (Corps Flag Bearer Greatsword 101316213, "165 ~ 183 / 85 ~ 94 / +642") and the top
                 swaps: 376 ~ 394, 250 ~ 259, 642, Melee / Ranged 2019
The blue ACC2 piece (right column, 4th) is a bracelet: of every REGNIER accessory at his level only the Mercenary
Bracelet A / C / E (202310311 / 13 / 15, RARE, identical: HP_MAX 839, CRITICAL_REDUCE 167) closes the HUD's HP
(8,527 = Hero_HP LV_17 622 + the top's 5,866 + 715 at level 3's 1,200 + 839).

Every number is reproduced: base %Contents + lvuptypetable %Hero growth x (level - 1) (S3: x 17 would read 346 ~ 361)
+ the gear's traits + the weapon's Base*_Min / _Max (S8) + the sets + the enchant + the held passives (715 L3 / 716 L4
/ 717 L3, L9), rounded as the server sends them (2,018.72 shows 2019: a truncation would read 2018)."""
import struct

import pytest

from kuf2 import hero, items, skills, world

BERSERKER = 4
BRACELET = 202310311                 # Mercenary Bracelet A (C / E identical)
PASSIVES = {715: 3, 716: 4, 717: 3}  # skills.auto_level at 17 (tests/test_hero_rules.py TAPE_LEVELS)

PANELS = [   # (frame, time, worn codes, enchants, the panel's numbers, the HUD's HP)
    ("f_01059", "35:16",
     (101313213, 151311210, 152313213, 155311210, 102316210, 153316210, 154316210, BRACELET),
     ((151311210, 1), (155311210, 1)),
     {"Physical Attack": (345, 360), "Magic Attack": (233, 241), "Attack Speed (%)": 100,
      "Physical Defence Penetration": 522, "Magic Defence Penetration": 779, "Physical Critical Rate": 274,
      "Physical Critical Attack": 1320, "Magic Critical Rate": 225, "Magic Critical Attack": 1081, "Hit": 585,
      "Melee Physical Defence": 1683, "Ranged Physical Defence": 1683}, 8527),
    ("f_01069", "35:36",
     (101316213, 151316210, 152313213, 155311210, 102316210, 153316210, 154316210, BRACELET),
     ((155311210, 1),),
     {"Physical Attack": (376, 394), "Magic Attack": (250, 259), "Physical Defence Penetration": 642,
      "Magic Defence Penetration": 779, "Physical Critical Rate": 274, "Physical Critical Attack": 1320,
      "Magic Critical Rate": 225, "Magic Critical Attack": 1081, "Hit": 585, "Melee Physical Defence": 2019,
      "Ranged Physical Defence": 2019}, 11193),
]

ROWS = {"Attack Speed (%)": "ATTACK_SPEED", "Physical Defence Penetration": "PHYSICAL_PENETRATE",
        "Magic Defence Penetration": "MAGICAL_PENETRATE", "Physical Critical Rate": "CRITICALPROB_PHYSICAL",
        "Magic Critical Rate": "CRITICALPROB_MAGICAL", "Hit": "ACCURACY",
        "Melee Physical Defence": "DEFENCE_PHYSICAL_CLOSE", "Ranged Physical Defence": "DEFENCE_PHYSICAL_RANGE"}
F32_ROWS = {"Physical Critical Attack": "CRITICAL_PHYSICAL", "Magic Critical Attack": "CRITICAL_MAGICAL"}
RANGES = {"Physical Attack": "PHYSICAL", "Magic Attack": "MAGICAL"}


def panel(block):
    """The panel's numbers as the Info window prints them from the 0x134b block (0x140984f00; the attack range is
    min / 10 " ~ " max / 10, 0x14098d7d0)."""
    out = {row: struct.unpack_from("<i", block, world.HERO_STAT_AT[name])[0] for row, name in ROWS.items()}
    out.update({row: round(struct.unpack_from("<f", block, world.HERO_STAT_F32_AT[name])[0])
                for row, name in F32_ROWS.items()})
    for row, kind in RANGES.items():
        lo, hi = (struct.unpack_from("<i", block, world.HERO_ATTACK_AT[f"ATTACK_{kind}_{end}"])[0] // 10
                  for end in ("MIN", "MAX"))
        out[row] = (lo, hi)
    return out


@pytest.mark.parametrize("frame, at, worn, enchants, want, hp", PANELS, ids=[p[0] for p in PANELS])
def test_the_lv17_berserkers_panel_is_rebuilt_from_the_tables(frame, at, worn, enchants, want, hp, monkeypatch):
    """CHECKABLE S3 / S8 (N1): every number the tape's panel shows, from the tables through the block the client
    prints."""
    c = {"id": 1, "class": BERSERKER, "level": 17, "title": 60418,
         "equip": [{"code": code, "index": i, "serial": i + 1} for i, code in enumerate(worn)]}
    monkeypatch.setattr(hero, "worn_codes", lambda _c: list(worn))
    monkeypatch.setattr(hero, "worn_enchants", lambda _c: list(enchants))
    monkeypatch.setattr(skills, "battle_abilities", lambda _c: dict(PASSIVES))
    got = panel(world.hero_block(c))
    assert {row: got[row] for row in want} == want
    assert round(hero.char_stats(c)["HP_MAX"]) == hp


def test_the_growth_is_per_level_above_the_first():
    """S3: lvuptypetable %Hero LvPhysicalAttack 1.159 x 16 at 17 is what closes 345; x 17 would show 346."""
    worn, ench = PANELS[0][2], PANELS[0][3]
    at17 = hero.stats(BERSERKER, 17, worn, ench, PASSIVES)["ATTACK_PHYSICAL_MIN"]
    growth = float(hero._row("lvuptypetable", "Hero", "ID", "REGNIER")["LvPhysicalAttack"])
    assert int(at17) == 345 and int(at17 + growth) == 346


def test_the_attack_range_is_the_attack_plus_the_weapons_base_range():
    """S8: the swap from the Corps Soldier Greatsword (134 ~ 149) to the Flag Bearer's (165 ~ 183) moves the panel by
    exactly the weapons' difference (+31 ~ +34, magic +17 ~ +18)."""
    a = hero.stats(BERSERKER, 17, PANELS[0][2], (), PASSIVES)
    b = hero.stats(BERSERKER, 17, PANELS[1][2], (), PASSIVES)
    assert (b["ATTACK_PHYSICAL_MIN"] - a["ATTACK_PHYSICAL_MIN"], b["ATTACK_PHYSICAL_MAX"] - a["ATTACK_PHYSICAL_MAX"]) \
        == (31, 34)
    assert round(b["ATTACK_MAGICAL_MIN"] - a["ATTACK_MAGICAL_MIN"]) == 17
    assert items.name(BRACELET) == "Mercenary Bracelet A"

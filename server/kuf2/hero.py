"""The hero's stats, as the server computes them from the game tables. The client computes none of them: it shows what
0x134b sends (Info window 0x140983050 / 0x140984f00). Stat names are the client's stat enum (name table 0x1434a74e0),
which the item trait columns use too. Sources (Info.pkg):
  herotable %Contents, %ApSp   the class's base values (row CHARACTER_TYPE / Hero = the E_HeroCode name)
  herotable %System HITRESIST  HIT_RESIST, the hit-reaction threshold (SYSTEM); the client reads the column too
                               (0x14191ca80 -> TroopGenConfig::BuildLeader_New +0x268), but the resist it tests is
                               stat 40 of the stat block, 0 until we sent it
  herotable %Inventory         the class kit a new hero wears (starter_kit) and carries (starter_bag)
  lvuptypetable %Hero_HP       HP_MAX at each level (LV_<n>)
  lvuptypetable %Hero          growth per level, applied x (level - 1). Inferred: the table is server-only (the
                               client never reads it), so its operand is not in the client; level 1 shows the same
                               either way
  item BASE_TRAIT_* with ADD   the equipped items (every weapon and armour trait targets LEADER), and their second
  and TraitType / Value        block (items.traits); a value written "N%" is a percent of the stat before it, after
                               every number (the Hero's Ring's "10%", the 77 set tiers' "15%.": items.trait_value)
  item_set %Info               the sets the worn pieces complete (items.set_traits)
  titletable %Base Ability0_ID the worn title's ability at Skill0_Level (title_ability): its SELF traits as a passive's
  weapon BasePhysical_Min/Max  the weapon's attack range (the client's item tooltip shows it as "[Hero] Physical
  and BaseMagical_Min/Max      Attack: min ~ max"); added to the hero's attack for ATTACK_*_MIN / _MAX (inferred sum)
  abilitycastinfo %Improvement the held passives' SELF traits (passive_traits); the client applies a status's traits
                               itself once the status exists, but no ability's (planning/wiring/HERO-CONTROLS-WIRING.md
                               R7)
"""
import functools

from . import items, tables

HERO_CODE = ("GLEN", "OLIVIA", "DRUID", "ISABELLA", "REGNIER", "HELENA")  # E_HeroCode = class id (names 0x1434a70c0)

PHYSICAL_DEFENCES = ("DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE")
MAGICAL_DEFENCES = ("DEFENCE_MAGICAL_FIRE", "DEFENCE_MAGICAL_ICE", "DEFENCE_MAGICAL_LIGHTNING", "DEFENCE_MAGICAL_NATURE",
                    "DEFENCE_MAGICAL_HOLY", "DEFENCE_MAGICAL_DARK")
# table names that stand for several stats (M_DEFENCE_* are stat enum 104/105; the herotable columns have no range split)
GROUPS = {"M_DEFENCE_PHYSICAL": PHYSICAL_DEFENCES, "DEFENCE_PHYSICAL": PHYSICAL_DEFENCES,
          "M_DEFENCE_MAGICAL": MAGICAL_DEFENCES, "DEFENCE_MAGICAL": MAGICAL_DEFENCES,
          "M_CRITICAL_PROB": ("CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL"),
          "M_CRITICAL": ("CRITICAL_PHYSICAL", "CRITICAL_MAGICAL")}
BASE = ("ATTACK_PHYSICAL", "ATTACK_MAGICAL", "DEFENCE_PHYSICAL", "DEFENCE_MAGICAL", "CRITICALPROB_PHYSICAL",
        "CRITICAL_PHYSICAL", "CRITICALPROB_MAGICAL", "CRITICAL_MAGICAL", "CRITICALPROB_RESIST", "CRITICAL_REDUCE",
        "PHYSICAL_PENETRATE", "MAGICAL_PENETRATE", "ACCURACY", "MISS", "HP_RECOVERY", "MAX_MOVE_SPEED", "RANGE_SIGHT",
        "ATTACK_SPEED")
APSP = {"SP_MAX": "SP_MAX", "SP_RECOVERY": "SP_RECOVERY"}
INIT = {"SP_INIT": "SP_CURRENT"}
SYSTEM = {"HITRESIST": "HIT_RESIST"}   # herotable %System: 15 for every hero. The client re-reads stat 40 into the
                                       # unit (+0x710, 0x140a14980) on every action and plays a hit reaction only when
                                       # the blow's AttackResistValue reaches it (0x140a2bde0; a kobold's blows 10)
GROWTH = {"LvPhysicalAttack": "ATTACK_PHYSICAL", "LvMagicalAttack": "ATTACK_MAGICAL",
          "LvPhysicalDefence": "DEFENCE_PHYSICAL", "LvMagicalDefence": "DEFENCE_MAGICAL",
          "LvPCriticalProbability": "CRITICALPROB_PHYSICAL", "LvPCriticalMag": "CRITICAL_PHYSICAL",
          "LvMCriticalProbability": "CRITICALPROB_MAGICAL", "LvMCriticalMag": "CRITICAL_MAGICAL",
          "LV_ACCURACY": "ACCURACY", "LV_MISS": "MISS", "LvSPMax": "SP_MAX"}


@functools.cache
def starter_kit(cls):
    """((E_ItemParts number, item code), ...) a new hero of class `cls` wears: herotable %Inventory's equipment rows
    (InventoryId = the part; ItemCode -1 = nothing there: every class's sub weapon, all of Helena's), the Old Novice
    set. The original's HUD pins it: a level-1 Berserker shows 450 HP = Hero_HP LV_1 38 + the Old Novice Top's 412
    (tests/test_hero_hp.py). The kit before it was made up (codes 1000000xx, weapons with no attack, and 1500000xx:
    a Berserker had 301 HP at level 1)."""
    return tuple((items.PARTS[r["InventoryId"]], int(r["ItemCode"])) for r in tables.sections("herotable")["Inventory"]
                 if r["CHARACTER_TYPE"] == HERO_CODE[cls] and r["InventoryId"] in items.PARTS and r["ItemCode"] != "-1")


def starter_bag(cls):
    """((item code, count), ...) a new hero of class `cls` carries: herotable %Inventory's INVENTORY01..08 rows
    (ItemCode -1 = nothing; OLIVIA's 02 / 03 say count 1 of -1): the class's Level-up Celebration Chest [Lv 5]
    (600000101 GLEN .. 600000501 DRUID; item_container: potions and the [Lv 10] chest), nothing for Helena."""
    return tuple((int(r["ItemCode"]), int(r["ItemCodeNum"])) for r in tables.sections("herotable")["Inventory"]
                 if r["CHARACTER_TYPE"] == HERO_CODE[cls] and r["InventoryId"].startswith("INVENTORY")
                 and r["ItemCode"] != "-1")


# The kit ours made up before starter_kit (the removed game.STARTER_EQUIP: nameless weapons 100000001.., 'Supplied Top /
# Trousers / Pauldrons / Gloves / Sandals' 150000001..; no quest, drop or shop in the tables gives one): saves made
# before 2026-09-30 still carry them (replace_made_up_kit)
MADE_UP_KIT = frozenset(range(100000001, 100000013)) | frozenset(range(150000001, 150000026))


def replace_made_up_kit(c):
    """Every made-up kit piece the character wears or carries becomes the original set's piece for its part and class
    (starter_kit; the owner's word 2026-09-30 ~18:3x, "Replace them"); a piece the original set has none for (the sub
    weapons, all of Helena's) goes: the client draws the class's default weapon on an empty weapon index. The serial,
    place and count stay; enchant, durability and sockets start fresh; the bound flag is the new item's. A save
    migration run at login (world.start_game); a second run changes nothing. Returns [(where "equip" / "bag", its index
    or slot, old code, new code or None)]."""
    out = []

    def keep(e, where, at):
        if e["code"] not in MADE_UP_KIT:
            return True
        r = items.row(e["code"]) or {}
        cls = HERO_CODE.index(r["ReqHero"]) if r.get("ReqHero") in HERO_CODE else c["class"]
        new = dict(starter_kit(cls)).get(items.PARTS.get(r.get("Parts")))
        out.append((where, e[at], e["code"], new))
        if new is None:
            return False
        e.update(code=new, bound=items.bound_on_gain(new))
        for k in ("dur", "sockets"):
            e.pop(k, None)
        if "enchant" in e:
            e["enchant"] = 0
        return True

    if "equip" in c:
        c["equip"] = [e for e in equipment(c) if keep(e, "equip", "index")]
    if "bag" in c:
        c["bag"] = [b for b in c["bag"] if keep(b, "bag", "slot")]
    return out


def equipment(c):
    """The character's worn items [{code, index (equipment index, items.index_part), serial, bound}], kept in the
    save; the class kit (starter_kit) the first time. Entries saved before accessories were mapped carry "part"
    (E_ItemParts) instead: index = part - 1."""
    if "equip" not in c:
        c["equip"] = [{"code": code, "index": part - 1, "serial": (c["id"] << 32) | part,
                       "bound": items.bound_on_gain(code)} for part, code in starter_kit(c["class"])]
    for e in c["equip"]:
        if "index" not in e:
            e["index"] = e.pop("part") - 1
    return c["equip"]


def wear_refusal(c, code):
    """Why the hero of character c cannot put item `code` on, or None (rules census G14): its Use Conditions, as the
    tooltip prints them ("Use Conditions: Berserker, Lv 16 or higher", tape part 9 f_01062): ReqHero (a class's
    E_HeroCode name, or ALL on 441 accessories and 3 costumes), ReqLevel at least, ReqLevelMax at most (100 on every
    wearable). The client greys the row and the original's server refused such a drag [I]; ours used to take it."""
    r = items.row(code) or {}
    req, level = r.get("ReqHero", "ALL"), c.get("level", 1)
    if req not in ("ALL", "-", "", HERO_CODE[c["class"]]):
        return f"item {code} is for {req}, not {HERO_CODE[c['class']]}"
    if level < _num(r.get("ReqLevel")):
        return f"item {code} needs level {r.get('ReqLevel')}"
    if _num(r.get("ReqLevelMax")) and level > _num(r.get("ReqLevelMax")):
        return f"item {code} is for level {r.get('ReqLevelMax')} or lower"
    return None


LOOK_PARTS = 21                    # the client's look array: one item code per equipment index (troop +0x1140)
LOOK_NONE = 0xffffffff             # -1, nothing worn there (the troop's constructor 0x140bf363c; 0x140a4f580 puts the
                                   # class's default weapon on a -1 main / sub weapon)
LOOK_SHOWN = (1 << LOOK_PARTS) - 1  # every part shown (troop +0x1194), what the rooms draw right with
NO_LOOK_BOX = (1 << 11) - 1        # parts 0..10: the client toggles only 11..20 (0x140cdf5ff), so 0x107f always has 0 here


def decode_look_shown(v):
    """The mask a 0x107f carries (u32 plain = mask - 0x200000, builder 0x1405f6c60; requests
    session_account_worldmap.md): bit i = the client's flag common+0xbb0+i, 1 when its Appearance box is ticked (live
    2026-11-07: 0000e0ff with none, 0020e0ff with the first). Parts 0..10 have no box and stay as the rooms draw them
    right; whether a ticked costume box shows or hides its part is not known (no costume was worn)."""
    return ((v + 0x200000) & LOOK_SHOWN) | NO_LOOK_BOX


def look_shown(c):
    """The parts the hero shows (bit i = equipment index i): the hero window's "Look item" boxes as 0x107f last set
    them, every part until then."""
    return c.get("look_shown", LOOK_SHOWN) & LOOK_SHOWN


def look_codes(c):
    """The hero's look as the room's player struct carries it (0x3f4f +0x29, SetPlayerInfoData 0x140cf9d70 -> player
    +0xb4 -> troop +0x1140 by 0x140a4fdb0): the worn item codes by equipment index (0 the main weapon, 2..6 the
    armour, 7..10 the rings, 11..20 the costumes, items.PART_INDEXES), LOOK_NONE where nothing is worn."""
    codes = [LOOK_NONE] * LOOK_PARTS
    for e in equipment(c):
        if 0 <= e["index"] < LOOK_PARTS:
            codes[e["index"]] = e["code"]
    return codes


def broken(e):
    """A worn piece worn down to durability 0 (of a DurabilityValue above 0): it counts for nothing (working; rules
    census HERO G20 / ECONOMY I4)."""
    return items.full_durability(e["code"]) > 0 and items.durability(e) <= 0


def working(c):
    """The worn items that count: a piece worn down to durability 0 adds nothing until it is repaired ("If the item's
    durability drops to 0, the item stats will be no longer valid.", texttutorial Item_Durability; rules census
    ECONOMY I4): its traits, its enchant, its sockets' stones and its place in a set."""
    return [e for e in equipment(c) if items.full_durability(e["code"]) <= 0 or items.durability(e) > 0]


def worn_codes(c):
    """The item codes whose traits the hero wears: the equipment (working) and the magic stones in its sockets."""
    eq = working(c)
    return [e["code"] for e in eq] + [v for e in eq for v in items.sockets(e) if v != -1]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _row(table, section, key, code):
    return next(r for r in tables.sections(table)[section] if r[key] == code)


def _add(stats, name, value):
    for n in GROUPS.get(name, (name,)):
        stats[n] = stats.get(n, 0.0) + value


def worn_enchants(c):
    """[(item code, enchant level)] of the equipment that counts (working; items.enchant_traits)."""
    return [(e["code"], e.get("enchant", 0)) for e in working(c)]


def passive_traits(abilities):
    """[(stat name, value, percent)] of the held passives ({ability id: level}; abilitytypeinfo %Basic Category
    AUTOMATIC: 68 M_CRITICAL / M_CRITICAL_PROB, 69 HP_MAX +300 / M_DEFENCE_PHYSICAL +100, 70 PHYSICAL_PENETRATE /
    ATTACK_PHYSICAL, 7003 CRITICAL_REDUCE, 7020 ATTACK "x%", 7022 M_CRITICAL): the SELF traits of their abilitycastinfo
    %Improvement row (COMMON, the held level), ADD a number, ASSIGN "x%" (percent True: ours, x % of the value computed
    before it)."""
    from .status import automatic, cast_row
    out = []
    for ability, level in sorted((abilities or {}).items()):
        row = cast_row(ability, level) if ability in automatic() else None
        for i in (1, 2) if row else ():
            name, op = row.get(f"TraitType{i}", "-"), row.get(f"TraitOperation{i}")
            value = str(row.get(f"TraitValue{i}"))
            if row.get(f"TraitObject{i}") != "SELF" or name in ("", "-"):
                continue
            if op in ("ADD", "ASSIGN") and value.endswith("%"):     # 7020 ASSIGN "10%", the title 500061 ADD "2%"
                out.append((name, _num(value[:-1]), True))
            elif op == "ADD":
                out.append((name, _num(value), False))
    return out


@functools.cache
def _titles():
    return {r["Reward_Title_ID"]: r for r in tables.sections("titletable")["Base"]}


def title_ability(title):
    """{ability id: level} of a title's effect: titletable %Base Ability0_ID at Skill0_Level (180 of the 215 titles; 20
    AUTOMATIC abilities: 5103 HP_RECOVERY +3 at level 1, 5102 HP_MAX +300 .. +1,500, 5085 ATTACK +10 / +10, 5112
    SP_RECOVERY +2, 7033-7038 an element's defence, 500061 ATTACK "+2%" ..; Ability1 / Ability2 are empty on every
    row). Part 9 35:08 (9NwV8ikwLYk f_01055): "Current Title: Traveller  HP Recovery +3", "In use"."""
    r = _titles().get(str(title)) if title else None
    a, lv = (r or {}).get("Ability0_ID", "-"), (r or {}).get("Skill0_Level", "-")
    return {int(a): int(lv)} if a.isdigit() and lv.isdigit() else {}


def char_stats(c, abilities=None):
    """stats of character c: its class, level, worn gear and enchants, the held abilities (skills.battle_abilities, or
    `abilities`), the worn title's (title_ability of c["title"]) and his guild's learned hero skills
    (guild.hero_abilities: 350001-350004, passives whose SELF traits count as the title's do)."""
    from . import guild, skills
    held = skills.battle_abilities(c) if abilities is None else abilities
    return stats(c["class"], c.get("level", 1), worn_codes(c), worn_enchants(c), held,
                 {**title_ability(c.get("title")), **guild.hero_abilities(c)}, worn_options(c))


def worn_options(c):
    """[(stat name, value, percent)] the random options of the working pieces (rules census HERO G10; items.roll_options'
    entries [trait id, target, fraction, whole, RandomOptionID]): a whole value adds to its stat as the gear's traits
    do, a fraction is a percent of the stat before it (ITEMS-WIRING D4 (a), the reading of the sets' "15%." HP, G5);
    a slot the data could not fill (NO_OPTION, both 0) adds nothing."""
    out = []
    for e in working(c):
        for trait, _target, fraction, whole, *_ in e.get("options") or ():
            if fraction:
                out.append((items.TRAIT_TYPES[trait], fraction * 100, True))
            elif whole:
                out.append((items.TRAIT_TYPES[trait], float(whole), False))
    return out


HP_REGEN_OUT_OF_COMBAT = 5     # the tape: 5 x the combat tick out of combat, in villages, fields and rooms alike


def regen_tick(c):
    """The hero's HP regeneration a 3 s tick in combat (rules census HERO P7): floor(S + lvuptypetable %Hero LvHPRestore
    (0.05, every class) x %Hero_HP LV_<level>), S = his HP_RECOVERY from gear, passives, sets and titles, the herotable
    %Contents base left out; out of combat HP_REGEN_OUT_OF_COMBAT times it (combat.start_regen). The tape (hunt agent
    2026-10-01, 17 reads at Lv.1-29): Lv.6 (Adventurer Bottoms +15, 715 L1 +3: 18 + 6.25) +24 a tick at Grey Rock between
    hits (qeeQjhgO8ss 2 fps 2205_2217, 36:47.5 / 50.5 / 53.5) and +120 in the Mist Field village and after the fight
    (f_00853, f_01112); Lv.1 +4 / +20, Lv.2 +5 / +25 (Old Novice Bottoms +3: the base 4 in would read 8 / 9); Lv.14 +94 /
    +470, Lv.23 +206 / +1,030; the level-ups step by the 0.05 x Hero_HP term (Lv.14 -> 15 -> 16: 94, 96, 98 with S 70)."""
    code = HERO_CODE[c["class"]]
    level = c.get("level", 1)
    base = _num(_row("herotable", "Contents", "CHARACTER_TYPE", code)["HP_RECOVERY"])
    restore = _num(_row("lvuptypetable", "Hero", "ID", code).get("LvHPRestore"))
    hp = _num(_row("lvuptypetable", "Hero_HP", "ID", code).get(f"LV_{level}"))
    return max(0, int(char_stats(c).get("HP_RECOVERY", 0.0) - base + restore * hp))


def mdp(item_codes):
    """The hero's God's Blessing (the gear score): the worn items' MDP column summed (item_weapon / _defence /
    _accessory MDP, 1,907 rows, levels 1-30). The Info panel's first row, "Blessing Stats / God's Blessing" (text 52346),
    reads block 0x134b +0x10 (HERO_STAT_AT "MDP"); an item's tooltip prints its column as "[Hero] God's Blessing : +34"
    (tape aMS5MxRFmSU f_01436, the Senior Centurion Ring B's MDP 34), and the tape's five panels (Lv.5, 10, 11, 17, 22)
    read 0 with gear whose MDP is 0. No enchant, random option or set row names MDP; the sum is ours [I] (the client
    only shows and compares what it is sent: spottable %Mdp Recom_MDP, text 61201 "Level of God's Blessing too
    low")."""
    total = 0
    for code in item_codes:
        v = str((items.row(code) or {}).get("MDP", ""))
        total += int(v) if v.isdigit() else 0
    return total


def stats(cls, level, item_codes, enchants=(), abilities=None, title=None, options=()):
    """{stat name: value} for a hero of class `cls` at `level` wearing `item_codes`, enchanted as `enchants`, holding
    `abilities` ({ability id: level}: the passives count), wearing a title whose ability is `title` ({ability id:
    level}, title_ability: its SELF traits count as a passive's) and the gear's random `options` ([(stat, value,
    percent)], worn_options: numbers with the gear's, percents after)."""
    code = HERO_CODE[cls]
    out = {}
    base = _row("herotable", "Contents", "CHARACTER_TYPE", code)
    for name in BASE:
        _add(out, name, _num(base[name]))
    for col, name in INIT.items():
        _add(out, name, _num(base[col]))
    apsp = _row("herotable", "ApSp", "Hero", code)
    for col, name in APSP.items():
        _add(out, name, _num(apsp[col]))
    system = _row("herotable", "System", "CHARACTER_TYPE", code)
    for col, name in SYSTEM.items():
        _add(out, name, _num(system[col]))
    growth = _row("lvuptypetable", "Hero", "ID", code)
    for col, name in GROWTH.items():
        _add(out, name, _num(growth[col]) * (level - 1))
    _add(out, "HP_MAX", _num(_row("lvuptypetable", "Hero_HP", "ID", code).get(f"LV_{level}")))
    out["MDP"] = float(mdp(item_codes))
    later = []                                         # the gear's and sets' "x%" (items.trait_value): after the numbers
    for name, value, percent in ([t for item in item_codes for t in items.traits(item)] + items.set_traits(item_codes)
                                 + list(options)):
        if percent:
            later.append((name, value, True))
        else:
            _add(out, name, value)
    for kind, col in (("PHYSICAL", "BasePhysical"), ("MAGICAL", "BaseMagical")):
        for end in ("Min", "Max"):
            out[f"ATTACK_{kind}_{end.upper()}"] = out.get(f"ATTACK_{kind}", 0.0) + sum(
                _num((items.row(i) or {}).get(f"{col}_{end}")) for i in item_codes)
    for code, enchant in enchants:                     # after the attack min / max block, which sets them
        for name, value in items.enchant_traits(code, enchant):
            _add(out, name, value)
    attack = {kind: out.get(f"ATTACK_{kind}", 0.0) for kind in ("PHYSICAL", "MAGICAL")}
    for name, value, percent in sorted(passive_traits(abilities) + passive_traits(title) + later,
                                       key=lambda t: t[2]):     # the numbers, then the "x%"
        for n in GROUPS.get(name, (name,)):
            out[n] = out.get(n, 0.0) + (out.get(n, 0.0) * value / 100 if percent else value)
    for kind, before in attack.items():                # the attack range moves with the attack
        for end in ("MIN", "MAX"):
            out[f"ATTACK_{kind}_{end}"] += out.get(f"ATTACK_{kind}", 0.0) - before
    return out

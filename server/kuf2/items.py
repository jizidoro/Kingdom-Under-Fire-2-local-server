"""Item records as the client reads them: the bag (S2C 0x1656) and the hero's equipped list (S2C 0x134b) use the same
record (reader 0x140619ae0 -> 0x140619170; field meaning from the conversion 0x140d66ad0).

Record: a 31-byte head, 8 bytes, u8 m + m * 4, u8 k + k * 10. Head:
  0x00 obool (item +6)          0x01..0x08 coded u64 serial   0x09 i32 seconds left of a timed item (0 = none)
  0x0d coded u16 count          0x0f u16 durability (plain)   0x11 coded u16 slot (bag slot, or equipment part)
  0x13..0x1a coded u64          0x1b coded u32 item code (obf.u32)
"""
import functools
import re
import struct

from . import obf
from .obf import via_t1, via_t2
from .packet import OBOOL_FALSE, OBOOL_TRUE

HEAD = 31
# E_ItemParts: the equipment slot of an item (item_* tables, column Parts)
PARTS = {"MAIN_WEAPON": 1, "SUB_WEAPON": 2, "UPPERBODY": 3, "LOWERBODY": 4, "SHOULDER": 5, "GAUNTLET": 6, "BOOTS": 7,
         "ACC1": 8, "ACC2": 9, "LOOK_HEAD": 10, "LOOK_FACE": 11, "LOOK_UPPER": 12, "LOOK_LOWER": 13, "LOOK_SHOULDER": 14,
         "LOOK_GAUNTLET": 15, "LOOK_BOOTS": 16, "LOOK_TATTOO": 17, "LOOK_ACC1": 18, "LOOK_ACC2": 19, "LOOK_SET": 20}
                                                   # E_ItemParts (name table 0x14353c670, read 2026-09-27)
PART_NAMES = {v: k for k, v in PARTS.items()}
# The equipment indexes a part may take (0x140e486e0 -> 0x140cdfae0, planning/features/ITEMS.md §3): costumes from 11,
# a full costume set (LOOK_SET) shares LOOK_UPPER's 13
PART_INDEXES = {"MAIN_WEAPON": {0}, "SUB_WEAPON": {1}, "UPPERBODY": {2}, "LOWERBODY": {3}, "SHOULDER": {4},
                "GAUNTLET": {5}, "BOOTS": {6}, "ACC1": {7, 8}, "ACC2": {9, 10}, "LOOK_HEAD": {11}, "LOOK_FACE": {12},
                "LOOK_UPPER": {13}, "LOOK_SET": {13}, "LOOK_LOWER": {14}, "LOOK_SHOULDER": {15}, "LOOK_GAUNTLET": {16},
                "LOOK_BOOTS": {17}, "LOOK_TATTOO": {18}, "LOOK_ACC1": {19}, "LOOK_ACC2": {20}}


def index_part(index):
    """The (first) part an equipment index takes (the equip drag 0x140e4a270)."""
    return next((p for p, idx in PART_INDEXES.items() if index in idx), None)


def fits_index(code, index):
    return index in PART_INDEXES.get((row(code) or {}).get("Parts"), set())


def bag_range(code, main_slots):
    """(first, end) of the bag slots an item lives in: the client finds items only in their kind's range (the tab rule
    0x140dc86c0, ITEMS.md §2): quest items 0x80..0xbf, troop stones 0xc0..0xff, costumes 0x100..0x4ff, the rest the
    main bag 0..main_slots-1."""
    r = row(code) or {}
    if r.get("ItemKind") == "QUEST_ITEM":
        return 0x80, 0xc0
    if r.get("ItemKind") == "CONSUME_ITEM" and r.get("ConsumeItemType") == "TROOP_STONE":
        return 0xc0, 0x100
    if r.get("ItemKind") == "LOOK_ITEM":
        return 0x100, 0x500
    return 0, main_slots
# byte positions of the coded u64s, most significant byte first, and the table that decodes each (client 0x140d66ad0)
_SERIAL = [(8, 2), (1, 1), (7, 2), (2, 1), (4, 2), (3, 1), (6, 2), (5, 1)]
_OTHER = [(0x1a, 2), (0x13, 1), (0x19, 2), (0x14, 1), (0x16, 2), (0x15, 1), (0x18, 2), (0x17, 1)]


def _coded_u64(head, layout, v):
    for (pos, table), byte in zip(layout, v.to_bytes(8, "big")):
        head[pos] = via_t2(byte) if table == 2 else via_t1(byte)


ITEM_TABLES = ("item_weapon", "item_defence", "item_consume", "item_quest", "item_material",
               "item_enchant", "item_gacha", "item_container", "item_accessory", "item_troop", "item_bboky_troop",
               "item_choice_container", "item_token", "item_look", "item_compose",
               "item_cash")   # last: a shop catalog (SellID, no ItemKind) that shadowed 421 real rows when read earlier
                              # (containers refused 0x447 live, costumes in the wrong bag range; items_troops_skills.md)


@functools.cache
def _index():
    from . import tables
    out = {}
    for name in ITEM_TABLES:
        for r in tables.load(name):
            out.setdefault(r["ItemCode"], r)
    return out


def row(code):
    """The item's table row (first section of the item_* tables, keyed by ItemCode), or None."""
    return _index().get(str(code))


@functools.cache
def _names():
    from . import tables
    try:
        rows = tables.sections("text\\eng\\textitem_eng")["TextTable"]
    except KeyError:
        return {}
    parts = {}
    for r in rows:
        code, _, field = r["TextID"].partition("/")
        if field in ("Name", "Name2") and r["Text"]:
            parts.setdefault(code, {})[field] = r["Text"]
    return {code: " ".join(p[f] for f in ("Name", "Name2") if f in p) for code, p in parts.items()}


def name(code):
    """An item's English name: textitem_eng <code>/Name (a prefix where /Name2 is set too: "Otherworldly") and /Name2
    ("[Lv 1] HP Recovery Potion"), '' without either: the journal's item lines name it."""
    return _names().get(str(code), "")


def max_stack(code):
    r = row(code)
    v = r.get("MaxStack", "") if r else ""
    return int(v) if v.isdigit() and int(v) > 0 else 1


def full_durability(code):
    r = row(code)
    v = r.get("DurabilityValue", "") if r else ""
    return int(v) if v.isdigit() else 0


def sockets(it):
    """The item's magic-stone sockets: its saved list, else ComposeSlotMax empty ones (-1; the compose window reads
    any other value as a stone code and looks its row up unchecked, 0x14072f300)."""
    if "sockets" in it:
        return list(it["sockets"])
    v = (row(it["code"]) or {}).get("ComposeSlotMax", "")
    return [-1] * (int(v) if v.isdigit() else 0)


def extras(it):
    """The per-item state that travels with an item when it moves between bag, equipment and rebuy list."""
    return {k: it[k] for k in ("dur", "sockets", "expires", "options") if k in it}


def can_stack(a, b):
    """Merging must not discard either item's saved attributes."""
    return (a["code"] == b["code"] and a.get("bound", False) == b.get("bound", False)
            and a.get("enchant", 0) == b.get("enchant", 0) and durability(a) == durability(b)
            and sockets(a) == sockets(b) and a.get("expires", 0) == b.get("expires", 0)
            and [list(o) for o in a.get("options", ())] == [list(o) for o in b.get("options", ())])


# E_TraitTypes, the client's stat enum (name table 0x1434a74e0 from its 5th entry; the first four are E_TraitTarget
# NONE, LEADER, TROOP, ALL): a random option's trait byte (rules census ECONOMY H11)
TRAIT_TYPES = ("HP_MAX", "HP_BASEUNIT", "HP_RECOVERY", "STAMINA_MAX", "STAMINA_RECOVERY", "STAMINA_REDUCE",
               "SP_CURRENT", "SP_MAX", "SP_RECOVERY", "SP_ENGAGE_GAIN", "RANGE_ATTACK_MAX", "RANGE_ATTACK_MIN",
               "RANGE_ACQUISITION", "RANGE_SIGHT", "MAX_MOVE_SPEED", "ATTACK_PHYSICAL", "ATTACK_MAGICAL",
               "DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE", "DEFENCE_MAGICAL_FIRE", "DEFENCE_MAGICAL_ICE",
               "DEFENCE_MAGICAL_LIGHTNING", "DEFENCE_MAGICAL_NATURE", "DEFENCE_MAGICAL_HOLY", "DEFENCE_MAGICAL_DARK",
               "CRITICAL_PHYSICAL", "CRITICAL_MAGICAL", "CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL",
               "PHYSICAL_PENETRATE", "DISPERSION", "ACCURACY", "MISS", "PROBABILITY_COUNTER", "PROBABILITY_GUARD",
               "STACK1_CURRENT", "STACK2_CURRENT", "STACK1_MAX", "STACK2_MAX", "ATTACK_SPEED", "HIT_RESIST",
               "EVADE_REDUCE", "GUARD_REDUCE", "CRITICAL_REDUCE", "IMMUNE_CAPTURE", "IMMUNE_FREEZE", "IMMUNE_STUN",
               "IMMUNE_ATTACK_DOWN", "IMMUNE_DEFENCE_DOWN", "IMMUNE_ATTACK_SPEED_DOWN", "IMMUNE_MOVE_SPEED_DOWN",
               "IMMUNE_PHYSICAL_DOT", "IMMUNE_FIRE_DOT", "IMMUNE_ICE_DOT", "IMMUNE_LIGHTNING_DOT",
               "IMMUNE_NATURE_DOT", "IMMUNE_HOLY_DOT", "IMMUNE_DARK_DOT", "IMMUNE_PHYSICAL", "IMMUNE_FIRE",
               "IMMUNE_ICE", "IMMUNE_LIGHTNING", "IMMUNE_NATURE", "IMMUNE_HOLY", "IMMUNE_DARK", "IMMUNE_DEBUFF",
               "ABILITY_ADD_DAMAGE_RATE_01", "ABILITY_ADD_DAMAGE_RATE_02", "ABILITY_ADD_DAMAGE_RATE_03",
               "ABILITY_ADD_DAMAGE_RATE_04", "ABILITY_ADD_DAMAGE_RATE_05", "ABILITY_ADD_DAMAGE_RATE_06",
               "ABILITY_ADD_DAMAGE_RATE_07", "ABILITY_ADD_DAMAGE_RATE_08", "ABILITY_ADD_DAMAGE_RATE_09",
               "ABILITY_ADD_DAMAGE_RATE_10", "CRITICALPROB_RESIST", "DEFENCE_PVP", "IMMUNE_HP_MAX",
               "CURRENT_STAMINA", "FINISH_RATE", "STAMINA_RATE", "FP_CURRENT", "MAGICAL_PENETRATE", "IMMUNE_BUFF",
               "MAINWEAPON_ATTACKRANGE", "SUBWEAPON_ATTACKRANGE", "ELVEN_ATTACK_RATE", "ORCISH_ATTACK_RATE",
               "GIANT_ATTACK_RATE", "DEMONIC_ATTACK_RATE", "MANKIND_ATTACK_RATE", "ELVEN_DEFENCE_RATE",
               "ORCISH_DEFENCE_RATE", "GIANT_DEFENCE_RATE", "DEMONIC_DEFENCE_RATE", "MANKIND_DEFENCE_RATE",
               "HERO_DEFENCE_RATE", "PROBABILITY_DODGE", "FSP_CURRENT", "MDP", "DAMAGE_ABSORB", "DAMAGE_ABSORB_RATE",
               "MAXCOUNT", "M_DEFENCE_PHYSICAL", "M_DEFENCE_MAGICAL", "M_IMMUNE_NON_CONTROLLABLE",
               "M_IMMUNE_ATTACK_DEFENCE_DOWN", "M_IMMUNE_SPEED_DOWN", "M_IMMUNE_DOT", "M_CRITICAL",
               "M_CRITICAL_PROB", "M_PENETRATE", "M_IMMUNE_STATUSEFFECT", "M_IMMUNE_DEBUFF", "M_IMMUNE_ATTACK")
TARGET_LEADER = 1                # E_TraitTarget LEADER: the hero (the tooltip's "[Hero]")
OPTION_SLOTS = 5                 # RandomOptionID_1..5 / Prob_1..5
NO_OPTION = (0, 0, 0.0, 0, 0)    # a slot the data cannot fill: zero values, which the tooltip skips (0x1406a0ba0)


@functools.lru_cache(maxsize=None)
def _option_rows():
    from . import tables
    return {r["RandomOptionID"]: r for r in tables.sections("randomoption")["RandomOption"]}


def option_from_row(r, roll):
    """One option of randomoption row r: a TraitType<n> picked by Weight<n> (relative), its value uniform in
    Value<n>_Min..Max; a value written "N%" is the fraction N / 100 (the tooltip shows the f32 x 100), any other the
    whole number. (trait id, target, fraction, whole, RandomOptionID)."""
    picks = [(n, int(r[f"Weight{n}"])) for n in range(1, 21) if r.get(f"TraitType{n}", "-") in TRAIT_TYPES
             and str(r.get(f"Weight{n}", "0")).isdigit() and int(r[f"Weight{n}"]) > 0]
    total = sum(w for _, w in picks)
    if not total:
        return NO_OPTION
    x = roll(total)
    for n, w in picks:
        if x < w:
            break
        x -= w
    lo, hi = (_leading_number(r.get(f"Value{n}_{end}", "0")) for end in ("Min", "Max"))
    lo, hi = int(min(lo, hi)), int(max(lo, hi))
    value = lo + roll(hi - lo + 1) if hi > lo else lo
    percent = "%" in str(r.get(f"Value{n}_Max", "")) + str(r.get(f"Value{n}_Min", ""))
    return (TRAIT_TYPES.index(r[f"TraitType{n}"]), TARGET_LEADER, round(value / 100, 4) if percent else 0.0,
            0 if percent else value, int(r["RandomOptionID"]))


def option_slots(code):
    """The item's option slots: its RandomOptionID_1..5 with an id, each (RandomOptionID, Prob of 100000) (all but one
    Prob in the data are 100000); the client sizes the reroll preview to their count (0x14060f540)."""
    r = row(code) or {}
    return [(r[f"RandomOptionID_{k}"], int(r.get(f"Prob_{k}", "0") or 0) if str(r.get(f"Prob_{k}", "")).isdigit()
             else 0) for k in range(1, OPTION_SLOTS + 1) if str(r.get(f"RandomOptionID_{k}", "-")).isdigit()]


def roll_options(code, roll):
    """The random options a newly gained item `code` gets (rules census ECONOMY H11): one per option slot that hits
    its Prob of 100000, from its randomoption row (option_from_row); a slot the data cannot fill (no randomoption row,
    Prob 0) keeps its place as NO_OPTION."""
    out = []
    for oid, prob in option_slots(code):
        r = _option_rows().get(oid)
        out.append(list(option_from_row(r, roll) if r and roll(100000) < prob else NO_OPTION))
    return out


def option_tail(options):
    """The record's tail: u8 k + k x (i8 trait, u8 target, f32 fraction, i32 whole) (0x140d66d40)."""
    return bytes([len(options)]) + b"".join(struct.pack("<bBfi", o[0], o[1], o[2], o[3]) for o in options)


def roll_missing_options(c, roll):
    """A save migration (rules census ECONOMY H11): the gear held from before random options (bag, equipment,
    warehouse) gets its options once, as a gain would have given them. Returns the items rolled."""
    from . import hero
    migrations = c.setdefault("migrations", [])
    if OPTIONS_MIGRATION in migrations:
        return 0
    n = 0
    for it in c.get("bag", []) + c.get("warehouse", []) + hero.equipment(c):
        if "options" not in it and option_slots(it["code"]):
            it["options"] = roll_options(it["code"], roll)
            n += 1
    migrations.append(OPTIONS_MIGRATION)
    return n


OPTIONS_MIGRATION = "random_options_rolled"     # c["migrations"]: roll_missing_options ran for this character


def reroll_stones(code):
    """(stone item, count) a reroll of item `code` takes: item_randomoptionini %ReqCost at its ReqLevel, the rarity's
    Req_Number (Purification Stone 351200010: 1 / 1 / 2 / 3 / 5); the client checks the bag first (0x14060e3b0)."""
    from . import tables
    r = row(code) or {}
    x = next((x for x in tables.sections("item_randomoptionini")["ReqCost"] if x["Item_ReqLevel"] == r.get("ReqLevel")),
             None)
    col = RARITY_COLUMN.get(r.get("Rarity"))
    if x is None or col is None or not str(x.get(f"{col}_Req_Number", "")).isdigit():
        return None, 0
    return int(x["Req_Item"]), int(x[f"{col}_Req_Number"])


def option_lock_cost(code):
    """The Cubic one locked option costs in a reroll (the client's price 0x14060e400 -> 0x14188dc40): item_currency
    Random_option_init at Index = the item's ReqLevel x the Random_Option_init row of its Rarity (1 / 1 / 1 / 3 / 6)."""
    from . import tables
    r = row(code) or {}
    per_rarity = next((int(x["Cubic_Count"]) for x in tables.sections("item_currency")["Random_Option_init"]
                       if x["ItemCurrencyType"] == r.get("Rarity") and x["Cubic_Count"].isdigit()), 0)
    return currency("Random_option_init", r.get("ReqLevel")) * per_rarity


def option_locks_allowed(code):
    """item_randomoptionini %FixAvailable of the item's Rarity: how many options a reroll may keep (0, 0, 1, 2, 3)."""
    from . import tables
    r = row(code) or {}
    x = next((x for x in tables.sections("item_randomoptionini")["FixAvailable"] if x["Item_Rarity"] == r.get("Rarity")),
             {})
    return int(x["FixAvailable"]) if str(x.get("FixAvailable", "")).isdigit() else 0


def valid_seconds(code):
    """A timed item's life from its gain: ValidDate minutes x 60 for ItemPeriod REAL_TIME (4,020 costumes, 2 NOBLE,
    1 accessory; the reachable costumes 43,200 = 30 days), else 0 (PERMANENT, or a REAL_TIME row with ValidDate 0)."""
    r = row(code) or {}
    v = r.get("ValidDate", "")
    return int(v) * 60 if r.get("ItemPeriod") == "REAL_TIME" and v.isdigit() else 0


def seconds_left(it, now=None):
    """What the record's head 0x09 carries for item entry `it`: the seconds to its "expires" stamp (at least 1, as 0
    is "no period"), or 0 for an item with none. The client counts down from it: the conversion 0x140d66ad0 stores
    it at item +0x40 and its receive time at +0x38 (ITEMS-WIRING I8)."""
    import time
    if "expires" not in it:
        return 0
    return max(1, int(it["expires"] - (time.time() if now is None else now)))


def compose_cost(stone, pay="Gold"):
    """The price to take a stone out of its socket (the cost grid 0x14184a630 from item_consume_sub %ExtractCompose,
    products at load: an i64 gold and an i32 Cubic cell, imul at 0x14184a884..0x14184a91b): Use<pay>Count1 of the row
    whose ReqHeroLv is the stone's ReqLevel x Use<pay>Count2 of the row for its Rarity (pay "Gold" or "Cubic")."""
    from . import tables
    r = row(stone) or {}
    rows = tables.sections("item_consume_sub")["ExtractCompose"]
    a = next((x for x in rows if x["ReqHeroLv"] == r.get("ReqLevel")), {})
    b = next((x for x in rows if x["ItemRarity"] == r.get("Rarity")), {})
    num = lambda v: int(v) if str(v).isdigit() else 0
    return num(a.get(f"Use{pay}Count1")) * num(b.get(f"Use{pay}Count2"))


def compose_cubic(stone):
    """compose_cost in Cubic (1 x 1 on every row of the data)."""
    return compose_cost(stone, "Cubic")


def durability(it):
    """An item's current durability: its saved "dur" once it has worn down, else full."""
    return it.get("dur", full_durability(it["code"]))


def wear(entries, kind, roll):
    """item_durability %DurabilityReduce for an event (DIE, KILL): each entry whose ItemKind has a row loses Value when
    roll(100000) < Prob (Prob read as out of 100000, the DIE rows' 100000 being certain; inferred). Items without
    durability (DurabilityValue -1) are skipped. Returns the entries changed."""
    from . import tables
    rules = {r["ItemKind"]: r for r in tables.sections("item_durability")["DurabilityReduce"] if r["Type"] == kind}
    changed = []
    for e in entries:
        rule = rules.get((row(e["code"]) or {}).get("ItemKind"))
        cur = durability(e)
        if rule and full_durability(e["code"]) > 0 and cur > 0 and roll(100000) < int(rule["Prob"]):
            e["dur"] = max(0, cur - int(rule["Value"]))
            changed.append(e)
    return changed


def repair_cost(it):
    """CommonSubShop::GetItemRepairCost 0x140e2a8c0: the item_durability %RepairCost row for the item's ItemKind and
    Rarity with the smallest ReqLevelMax >= its ReqLevel; int(ItemKindValue x RarityValue x Gold x durability missing)."""
    from . import tables
    missing = full_durability(it["code"]) - durability(it)
    if missing <= 0:
        return 0
    r = row(it["code"]) or {}
    level = int(r["ReqLevel"]) if str(r.get("ReqLevel", "")).isdigit() else 0
    rows = sorted((x for x in tables.sections("item_durability")["RepairCost"] if x["ItemKind"] == r.get("ItemKind")
                   and x["Rarity"] == r.get("Rarity") and int(x["ReqLevelMax"]) >= level), key=lambda x: int(x["ReqLevelMax"]))
    if not rows:
        return 0
    x = rows[0]
    return int(float(x["ItemKindValue"]) * float(x["RarityValue"]) * float(x["Gold"]) * missing)


def trait_value(text):
    """(number, percent) of a trait value column: "15%." (77 item_set HP_MAX tiers) and "10%" (the Hero's Ring
    (Limited-time) 200900027's HP_MAX) are percents (owner 2026-09-30, rules census HERO G5: a percent of the value
    before it, hero.stats' "x%" pass), any other text its leading number."""
    return _leading_number(text), "%" in str(text)


def traits(code):
    """[(stat name, value, percent)] the item adds to its wearer: its BASE_TRAIT_TYPE<i> / BASE_VALUE<i> columns with
    operation ADD (NOOP rows carry no effect), and its second block TraitType<i> / Value<i> with Target LEADER and
    Operation ADD: a magic stone's traits, and on gear (owner 2026-09-30, rules census HERO G2) 275 weapons', 590
    armour pieces' and 34 accessories' further stats (ACCURACY 5-36, CRITICAL_REDUCE, HP_MAX, MISS, HERO_DEFENCE_RATE,
    GIANT_DEFENCE_RATE, RANGE_SIGHT 25-70, DEFENCE_MAGICAL_FIRE 125 ..., all LEADER ADD in the data)."""
    r = row(code) or {}
    out = []
    for i in range(5):
        name, op, value = r.get(f"BASE_TRAIT_TYPE{i}", "-"), r.get(f"BASE_OPERATION{i}"), r.get(f"BASE_VALUE{i}", "0")
        if name != "-" and op == "ADD":
            out.append((name, *trait_value(value)))
        name = r.get(f"TraitType{i}", "-")
        if name not in ("-", "", None) and r.get(f"Target{i}") == "LEADER" and r.get(f"Operation{i}") == "ADD":
            out.append((name, *trait_value(r.get(f"Value{i}", "0"))))
    return out


@functools.lru_cache(maxsize=None)
def _set_rows():
    from . import tables
    out = {}
    for r in tables.sections("item_set")["Info"]:
        out.setdefault(r["SetCode"], []).append(r)
    return out


def set_traits(codes):
    """[(stat name, value, percent)] of the sets the worn codes complete (ITEMS.md set bonuses): per item SetCode, every
    item_set %Info tier whose SetNumber is at most the pieces worn adds its traits (all LEADER ADD in the data; the 77
    HP_MAX tiers written "15%." are percents, trait_value)."""
    worn = {}
    for code in codes:
        sc = str((row(code) or {}).get("SetCode", "-1"))
        if sc.isdigit() and int(sc) > 0:
            worn[sc] = worn.get(sc, 0) + 1
    out = []
    for sc, n in worn.items():
        for r in _set_rows().get(sc, []):
            if str(r.get("SetNumber", "")).isdigit() and n >= int(r["SetNumber"]):
                out += [(r[f"TraitType{i}"], *trait_value(r.get(f"Value{i}", "0"))) for i in range(1, 6)
                        if r.get(f"TraitType{i}", "-") != "-" and r.get(f"Target{i}") == "LEADER"
                        and r.get(f"Operation{i}") == "ADD"]
    return out


def enchant_traits(code, level):
    """[(stat name, value)] an item's enchant level adds (planning/wiring/ITEMS-WIRING.md I1): item_enchant %Enchant
    (ReqHero x Parts) or %EnchantDouble (the main weapon), COMMON rows, column Enchant<level> (the client reads 1..15),
    a percent of the item's own value for that trait as the client's tooltip computes it (0x1406a6a30): ATTACK_PHYSICAL
    / ATTACK_MAGICAL on the weapon's Base*_Min / _Max, any other type on the item's BASE_TRAIT of that type."""
    from . import tables
    r = row(code) or {}
    if level <= 0 or not r:
        return []
    section = "EnchantDouble" if r.get("Parts") == "MAIN_WEAPON" else "Enchant"
    out = []
    for e in tables.sections("item_enchant")[section]:
        if (e.get("ReqHero") != r.get("ReqHero") or e.get("SpotFilter") != "COMMON" or e.get("Target") != "LEADER"
                or e.get("Operation") != "ADD" or (section == "Enchant" and e.get("Parts") != r.get("Parts"))):
            continue
        pct, trait = _leading_number(e.get(f"Enchant{min(level, 15)}", "0")), e.get("TraitType")
        if trait in ("ATTACK_PHYSICAL", "ATTACK_MAGICAL"):
            col = "BasePhysical" if trait == "ATTACK_PHYSICAL" else "BaseMagical"
            out += [(f"{trait}_{end.upper()}", _leading_number(r.get(f"{col}_{end}", "0")) * pct / 100)
                    for end in ("Min", "Max")]
        else:
            base = next((_leading_number(r.get(f"BASE_VALUE{i}", "0")) for i in range(5)
                         if r.get(f"BASE_TRAIT_TYPE{i}") == trait), 0.0)
            if base:
                out.append((trait, base * pct / 100))
    return [(n, v) for n, v in out if v]


def _leading_number(text):
    """A String value column read as C's atof would: its leading number ("15%." -> 15, trait_value marks it a percent),
    0 when none."""
    m = re.match(r"\s*-?\d+(?:\.\d+)?", str(text))
    return float(m.group()) if m else 0.0


def sale_slot(shop, slot):
    """(item code, bundle) at slot (0-based) of an itemsaletable shop (the NPC's MENU_VALUE), or (None, 0)."""
    from . import tables
    r = next((r for r in tables.sections("itemsaletable")["ItemSaleTable"] if r["ID"] == str(shop)), None)
    code = r and r.get(f"SLOT{slot + 1}_ID", "-")
    if not code or not code.isdigit():
        return None, 0
    bundle = r.get(f"SLOT{slot + 1}_BUNDLE", "1")
    return int(code), int(bundle) if bundle.isdigit() else 1


def sell_price(code):
    r = row(code) or {}
    v = r.get("SellPrice", "0")
    return int(v) if v.isdigit() else 0


def buy_price(code):
    r = row(code) or {}
    v = r.get("BuyPrice", "0")
    return int(v) if v.isdigit() else 0


def heal(code):
    """HP a consumable gives the hero: its LEADER HP_BASEUNIT ADD traits (350000010 HP potion: 600)."""
    r = row(code) or {}
    return sum(int(float(r.get(f"BASE_VALUE{i}", "0"))) for i in range(5)
               if r.get(f"BASE_TARGET{i}") == "LEADER" and r.get(f"BASE_TRAIT_TYPE{i}") == "HP_BASEUNIT"
               and r.get(f"BASE_OPERATION{i}") == "ADD")


def sp_gain(code):
    """SP a consumable gives the hero: its LEADER SP_CURRENT ADD traits (350100010 SP potion: 50; all-in-one potions
    carry both this and HP)."""
    r = row(code) or {}
    return sum(int(float(r.get(f"BASE_VALUE{i}", "0"))) for i in range(5)
               if r.get(f"BASE_TARGET{i}") == "LEADER" and r.get(f"BASE_TRAIT_TYPE{i}") == "SP_CURRENT"
               and r.get(f"BASE_OPERATION{i}") == "ADD")


def container(code, kind="CONTAINER", table="item_container"):
    """An item_container box: (DropGold_Min, DropGold_Max, [(item, Min, Max, Prob of 100000)] of its GroupID), or
    None when the item is not a container."""
    from . import tables
    r = row(code)
    if not r or r.get("ItemKind") != kind or not r.get("GroupID", "").isdigit():
        return None
    num = lambda v, d=0: int(v) if v.lstrip("-").isdigit() else d
    group = [(int(g["ItemCode"]), num(g["Min"], 1), num(g["Max"], 1), num(g["Prob"]))
             for g in tables.sections(table)["Group"] if g["GroupID"] == r["GroupID"]]
    return num(r.get("DropGold_Min", "0")), num(r.get("DropGold_Max", "0")), group


def choice_container(code):
    """An item_choice_container box (the player picks one entry), in container()'s shape."""
    return container(code, "CHOICE_CONTAINER", "item_choice_container")


def open_container(code, roll, box=container):
    """What one box gives: (gold, [(item, count)]), each group row by its Prob (of 100000), count Min..Max."""
    box = box(code)
    if box is None:
        return 0, []
    lo, hi, group = box
    gold = lo + roll(hi - lo + 1) if hi > lo else lo
    got = [(item, a + roll(b - a + 1) if b > a else a) for item, a, b, prob in group if roll(100000) < prob]
    return gold, got


def open_gacha(code, roll):
    """What one GACHA_ITEM gives: (item, count) or None. item_gacha %Base ChangeId -> %ChangeType (GroupID1/Prob1,
    GroupID2/Prob2 of 100000) -> one %ChangeGroup row of the group by its Prob as a weight (inferred: not every
    group sums to 100000), count Min..Max. Rows naming items this build does not have are skipped."""
    from . import tables
    r = row(code)
    if not r or r.get("ItemKind") != "GACHA_ITEM":
        return None
    sec = tables.sections("item_gacha")
    kind = next((t for t in sec["ChangeType"] if t["ChangeID"] == r.get("ChangeId")), None)
    if kind is None:
        return None
    x, group = roll(100000), None
    for k in (1, 2):
        p = int(kind.get(f"Prob{k}", "0") or 0) if kind.get(f"Prob{k}", "").isdigit() else 0
        if x < p:
            group = kind.get(f"GroupID{k}")
            break
        x -= p
    rows = [g for g in sec["ChangeGroup"] if g["GroupID"] == group and row(g["ItemCode"]) and g["Prob"].isdigit()]
    total = sum(int(g["Prob"]) for g in rows)
    if not total:
        return None
    x = roll(total)
    for g in rows:
        x -= int(g["Prob"])
        if x < 0:
            lo, hi = int(g["Min"]), int(g["Max"])
            return int(g["ItemCode"]), lo + roll(hi - lo + 1) if hi > lo else lo
    return None


def dismantle(code, enchant, count, roll):
    """What dismantling `count` of item `code` gives: [(item, n)], or None when it cannot be dismantled. item_dismantle
    %Dismantle rows of the item's DismantleId are independent rolls of GroupProb of 100000 (their sums pass 100000,
    inferred), each picking one of its ItemCode_k (repeats act as weights) with Min_k..Max_k; an enchanted item adds
    %Compensation[CompensationId] ItemCode x Step<level>_Min..Max (inferred)."""
    from . import tables
    r = row(code)
    sec = tables.sections("item_dismantle")
    rows = [x for x in sec["Dismantle"] if r and x["DismantleId"] == r.get("DismantleId")]
    if not rows:
        return None
    span = lambda lo, hi: lo + roll(hi - lo + 1) if hi > lo else lo
    got = {}
    for _ in range(count):
        for x in rows:
            if roll(100000) >= int(x["GroupProb"]):
                continue
            picks = [k for k in range(1, 11) if x[f"ItemCode_{k}"].isdigit()]
            if picks:
                k = picks[roll(len(picks))]
                n = span(int(x[f"ItemCodeMin_{k}"]), int(x[f"ItemCodeMax_{k}"]))
                got[int(x[f"ItemCode_{k}"])] = got.get(int(x[f"ItemCode_{k}"]), 0) + n
        comp = next((x for x in sec["Compensation"] if enchant and x["CompensationId"] == r.get("CompensationId")), None)
        if comp and comp.get(f"Step{enchant}_Min", "").isdigit():
            n = span(int(comp[f"Step{enchant}_Min"]), int(comp[f"Step{enchant}_Max"]))
            got[int(comp["ItemCode"])] = got.get(int(comp["ItemCode"]), 0) + n
    return [(item, n) for item, n in got.items() if n > 0]


RARITY_COLUMN = {"NORMAL": "Normal", "MAGIC": "Magic", "RARE": "Rare", "HERO": "Hero", "UNIQUE": "Unique"}


def enchant_rule(code, level):
    """What enchanting item `code` at `level` needs (item_enchant): {max, material, count, cost, outcomes} or None
    when it cannot be enchanted. max = %EnchantMax by the item's ReqLevel (the last row at or below it); material and
    count = %ReqEnchantItem for its Parts and level band, the Rarity's Req_Number; cost = Base_Gold x Level_Revision
    of %ReqCost at `level` (what the client shows; it ignores the rarity revisions); outcomes = %Probability at
    `level`: [(new level, weight of 1000, outcome 0 success / 1..4 FailN)]."""
    from . import tables
    r = row(code)
    if not r or r.get("EnchantAble") != "True" or not r.get("ReqLevel", "").isdigit():
        return None
    sec = tables.sections("item_enchant")
    req = int(r["ReqLevel"])
    maxes = [(int(x["ReqLevel"]), int(x["Enchant_Max"])) for x in sec["EnchantMax"]]
    top = next((m for lv, m in sorted(maxes, reverse=True) if lv <= req), 0)
    need = next((x for x in sec["ReqEnchantItem"] if x["Parts"] == r.get("Parts")
                 and int(x["Level_Min"]) <= req <= int(x["Level_Max"])), None)
    cost = next((x for x in sec["ReqCost"] if x["Current_Enchant_Step"] == str(level)), None)
    prob = next((x for x in sec["Probability"] if x["Current_Enchant_Step"] == str(level)), None)
    if need is None or cost is None or prob is None:
        return None
    outcomes = [(int(prob["Success"]), int(prob["Success_Weight"]), 0)]
    outcomes += [(int(prob[f"Fail{k}"]), int(prob[f"Fail{k}_Weight"]), k) for k in range(1, 5)
                 if prob[f"Fail{k}_Weight"].isdigit() and int(prob[f"Fail{k}_Weight"])]
    return {"max": top, "material": int(need["Req_Item"]),
            "count": int(need[RARITY_COLUMN.get(r.get("Rarity"), "Normal") + "_Req_Number"]),
            "cost": int(float(cost["Base_Gold"]) * float(cost["Level_Revision"])), "outcomes": outcomes}


def currency(kind, index):
    """item_currency %Base Cubic_Count of an ItemCurrencyType at an Index (0 when there is no such row)."""
    from . import tables
    r = next((r for r in tables.sections("item_currency")["Base"]
              if r["ItemCurrencyType"] == kind and r["Index"] == str(index)), None)
    return int(r["Cubic_Count"]) if r and r["Cubic_Count"].isdigit() else 0


# The Cubic expansions the client prices itself (0x14188db50: item_currency type 5 / 6 / 7): the ItemCurrencyType, the
# open slots before any purchase and the count past which nothing is sold
EXPANSIONS = {"inven": ("Expand_inven", 32, 128), "warehouse": ("Expand_warehouse", 16, 64),
              "barrack": ("Expand_barrack", 24, 60)}


def expansion(kind, open_slots):
    """(Cubic cost, slots added) of the next bag / warehouse / barracks expansion at `open_slots`, as the client prices
    it (0x14188db50, planning/wiring/ITEMS-WIRING.md I2): the kind's rows in Index order, their %OpenSlot summed until
    the running sum passes open_slots - base; that row's %Base Cubic_Count. None at the cap or past the last row. The
    windows' own limits (the bag and the warehouse refuse at 0x40 open slots) are the callers'."""
    from . import tables
    name, base, cap = EXPANSIONS[kind]
    if open_slots >= cap:
        return None
    total = 0
    for r in sorted((r for r in tables.sections("item_currency")["OpenSlot"] if r["ItemCurrencyType"] == name),
                    key=lambda r: int(r["Index"])):
        total += int(r["OpenSlot"])
        if total > open_slots - base:
            return currency(name, r["Index"]), int(r["OpenSlot"])
    return None


def unbind_cost(code):
    """The Cubic to unbind an item (the client's grid 0x14184d7a0 over item_consume_sub %ItemBind): ReqHeroLvValue of
    its ReqLevel x ItemPartsValue of its Parts x ItemRarityValue of its Rarity; 0 when a factor is missing."""
    from . import tables
    r = row(code) or {}
    rows = tables.sections("item_consume_sub")["ItemBind"]
    value = lambda key, col, want: next((int(x[col]) for x in rows if x[key] == want and x[col].isdigit()), 0)
    return (value("ReqHeroLv", "ReqHeroLvValue", r.get("ReqLevel")) * value("ItemParts", "ItemPartsValue",
                                                                             r.get("Parts"))
            * value("ItemRarity", "ItemRarityValue", r.get("Rarity")))


ENCHANT_ADD = {1: "Enchant_success_up", 2: "Enchant_prevent_down"}    # 0x1670's add-type -> item_currency type 13 / 14


def enchant_add_cost(code, level, add):
    """The Cubic an enchant add-type costs at `level` (the enchant window's price, 0x1405f9d90 -> 0x14188dd30): the
    type's %Base Cubic_Count at Index = the item's ReqLevel x %Enchant_Parts Use_Count of its Parts x %Enchant_Step
    Use_Count of the level. 0 = not offered (the client then forces add-type 0): success-up only at levels 10..14,
    prevent-down at 5..9."""
    from . import tables
    kind, r = ENCHANT_ADD.get(add), row(code) or {}
    if kind is None:
        return 0
    sec = tables.sections("item_currency")
    num = lambda rows, key, want: next((int(x["Use_Count"]) for x in rows if x["ItemCurrencyType"] == kind
                                        and x[key] == str(want) and x["Use_Count"].isdigit()), 0)
    return (currency(kind, r.get("ReqLevel")) * num(sec["Enchant_Parts"], "ItemParts", r.get("Parts"))
            * num(sec["Enchant_Step"], "Current_Enchant_Step", level))


def lucky_bonus():
    """item_enchant %LuckyStone Value (150 of the 1000 outcome weight): what success-up adds to the success weight
    (ours, ITEMS-WIRING.md D1 (a): the only non-zero number the data gives; %Increase is 0 at every step)."""
    from . import tables
    v = tables.sections("item_enchant")["LuckyStone"][0].get("Value", "")
    return int(v) if v.isdigit() else 0


def enchant_transfer(code, level, target):
    """What moving enchant `level` from item `code` onto item `target` needs, as the ENCHANT_TRANS window previews it
    (items_troops_skills.md 0x1679): {cubic, material, count, chance}. cubic = item_currency Enchant_Trans_Cubic at
    Index level; material / count = item_enchant %ReqTransItem for the target's Rarity and ReqLevel band, Req_Item and
    EnchantLevel_<level>; chance (of 100000000) = %Rarity_TransProbability(source -> target) x
    %Level_TransProbability(|ReqLevel difference|), every shipped pair 10000 x 10000 or 0. None when the target has
    no %ReqTransItem row (only levels 25..30 do)."""
    from . import tables
    a, b = row(code) or {}, row(target) or {}
    if not (a.get("ReqLevel", "").isdigit() and b.get("ReqLevel", "").isdigit()) or level <= 0:
        return None
    sec = tables.sections("item_enchant")
    lv = int(b["ReqLevel"])
    need = next((x for x in sec["ReqTransItem"] if x["Rarity"] == b.get("Rarity")
                 and int(x["Level_Min"]) <= lv <= int(x["Level_Max"])), None)
    count = need.get(f"EnchantLevel_{level}", "") if need else ""
    if not count.isdigit():
        return None
    rarity = next((int(x["Rarity_Probability"]) for x in sec["Rarity_TransProbability"]
                   if x["Rarity_From"] == a.get("Rarity") and x["Rarity_To"] == b.get("Rarity")), 0)
    distance = next((int(x["Level_Probability"]) for x in sec["Level_TransProbability"]
                     if x["Level_Distance"] == str(abs(int(a["ReqLevel"]) - lv))), 0)
    return {"cubic": currency("Enchant_Trans_Cubic", level), "material": int(need["Req_Item"]), "count": int(count),
            "chance": rarity * distance}


def bound_on_gain(code):
    r = row(code)
    return bool(r) and r.get("BindType") == "BIND_GAIN_TIME"


def bound_on_equip(code):
    r = row(code)
    return bool(r) and r.get("BindType") in ("BIND_GAIN_TIME", "BIND_EQUIP_TIME")


def record(code, slot, serial, count=1, durability=0, bound=False, enchant=0, sockets=(), expiry=0, options=()):
    """head[0] is the bound flag (item +6): the client asks "bind on equip?" for an unbound item. The 8 bytes after
    the head: +0 plain i16 enchant level (0x140d66d40 -> item +8, salted in memory), +2 u32 and +6 u16 not pinned.
    Then u8 m + m x i32 sockets (copied raw into item +0x10: -1 empty, else the stone's code), and the random options
    (option_tail: u8 k + k x 10)."""
    head = bytearray(HEAD)
    head[0] = OBOOL_TRUE if bound else OBOOL_FALSE
    _coded_u64(head, _SERIAL, serial)
    struct.pack_into("<i", head, 0x09, expiry)
    head[0x0d], head[0x0e] = via_t1(count >> 8), via_t2(count)
    struct.pack_into("<H", head, 0x0f, durability)
    head[0x11], head[0x12] = via_t1(slot >> 8), via_t2(slot)
    _coded_u64(head, _OTHER, 0)
    head[0x1b:0x1f] = obf.u32(code)
    return (bytes(head) + struct.pack("<hIH", enchant, 0, 0) + bytes([len(sockets)])
            + b"".join(struct.pack("<i", v) for v in sockets) + option_tail(options))


def decode_head(b):
    """(code, slot, count, serial) of a record head, the client's way (for tests)."""
    T1, T2 = obf.T1, obf.T2
    serial = 0
    for pos, table in _SERIAL:
        serial = (serial << 8) | (T2[b[pos]] if table == 2 else T1[b[pos]])
    return (obf.dec_u32(b[0x1b:0x1f]), (T1[b[0x11]] << 8) | T2[b[0x12]], (T1[b[0x0d]] << 8) | T2[b[0x0e]], serial)

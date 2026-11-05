"""Loot, reward items and the mission grade from the original's own tables (ROADMAP D2, C5-C7, Q3; owner Q21
2026-09-29: "roll from the tables"; planning/todo/ORIGINAL-RULES-PLAN.md part C). Four Info.pkg tables no name list
has, read by package hash (tables.by_hash; INVENTORY "Unnamed tables found by a content crawl"):

- DROPS 0xf37598e0f7787b33: %Troop (1,812 NP troops) and %Leader (245 NP leaders): DropRepeat, Common_Drop,
  Drop_Category1..30 with _Prob.
- CATEGORIES 0x23593bf19b78f161: %Table (10,471 drop categories): ItemCode1..20 with _Weight, _Min, _Max. An ItemCode
  that is itself a category nests (903121 `1-33_노말_B1N` -> 8006040 `E급_040` -> 8016040..8056040, one per class ->
  7 pieces each; at most 3 deep).
- SMART 0x328cb123ac378dff: %SmartDrop (96 spots): PerPlayerDropProb, CommonDropProb.
- GRADES 0xeef9690fef45f7be: %Mission_Grade (95 missions x Normal / Hard / Hell).

The scales, read from the data (ORIGINAL-RULES falsifier F4 did not fire):
- A slot's _Prob is a chance in 100,000 (PROB, the scale item_drop_quest's _Rate uses): 793 troop slots hold 100000
  (bosses' and reward dummies' sure drops), the rest are fractions of it such as 12766 = 6/47 (Tower's troops) or
  7317 = 3/41, and none is above 100000. Every filled slot rolls on its own. The slot follows the category's letter
  (1 E normal, 2 D mid-boss, 3-4 C special, 5-10 and 30 B boss: DESIGNER-NOTES F2).
- %SmartDrop scales that chance per spot, in 100,000 too: PerPlayerDropProb for the rows with Common_Drop False and
  CommonDropProb for the 28 with Common_Drop True (the climax and raid bosses, whose loot stayed a party roll after
  the 17.12.19 patch made general mission loot personal: OFFICIAL-NOTES). Which column goes with which rows is read
  from the names (inferred); for one player both are one roll. A spot with no row (10237 the Goblin Nest, the 1-52
  and 2-50..2-52 fields): unscaled (ours).
- A category gives one of its entries, picked by _Weight (an entry of weight 0 never; 1,588 categories weigh 0 in all
  and give nothing); a nested category is picked the same way, and the count is the item entry's Min..Max. A
  category entry's own Min / Max is not a count: 15023013 writes x5 both on its entries and on their items, and
  12070215's entries hold -1 / -1.
- DropRepeat is False on every row: one roll per wiped troop (game.troop_down, where quest drops roll too).
- On Hard / Hell the rows are the room's variants (%NP_Troop_Change / %NP_Leader_Change): the troop's is the row it
  spawned as (game.difficulty_troop), its leader's is mapped for the roll (game.difficulty_leader: 80 Hard and 41 Hell
  %Leader rows, e.g. Fort Valley's 106030 -> 20106030, 903641 -> 903741; some variants hold rows with no slot filled,
  30106030: nothing drops).
Ours: an item of Rarity EVENT does not drop, events being off (ROADMAP Q9). Slot 30 of 92 bosses (B7N) is the Easter
2020 egg 760000044 x3 at 100000 (OFFICIAL-NOTES: "3 eggs per mission from bosses of any level as personal loot"), and
760000041..43 are the football event's balls.
"""
import functools
import random
import struct
from decimal import Decimal

from . import items, tables

DROPS = 0xf37598e0f7787b33
CATEGORIES = 0x23593bf19b78f161
SMART = 0x328cb123ac378dff
GRADES = 0xeef9690fef45f7be

PROB = 100000                    # the tables' chance scale
SLOTS = 30                       # Drop_Category1..30
ENTRIES = 20                     # ItemCode1..20
MAX_NEST = 4                     # %Table nests 3 deep at most; a guard, not a rule
EVENT = "EVENT"                  # item Rarity of the event tokens (ours: they do not drop, Q9)
RATES = ("SRate", "ARate", "BRate", "CRate")      # grade index 0..3; under CRate is D (4)


def _int(v):
    v = str(v).strip()
    return int(v) if v.lstrip("-").isdigit() else 0


@functools.cache
def _drop_rows(section):
    key = "NPTroopID" if section == "Troop" else "NPLeaderID"
    return {r[key]: r for r in tables.by_hash(DROPS)[section]}


@functools.cache
def categories():
    """{category: ((code, weight, min, max), ...)} of %Table, the entries of weight above 0 only."""
    out = {}
    for r in tables.by_hash(CATEGORIES)["Table"]:
        out[_int(r["Category_Name"])] = tuple(
            (_int(r[f"ItemCode{k}"]), _int(r[f"ItemCode{k}_Weight"]), _int(r[f"ItemCode{k}_Min"]),
             _int(r[f"ItemCode{k}_Max"]))
            for k in range(1, ENTRIES + 1) if _int(r[f"ItemCode{k}"]) > 0 and _int(r[f"ItemCode{k}_Weight"]) > 0)
    return out


@functools.cache
def _smart():
    return {r["SpotID"]: r for r in tables.by_hash(SMART)["SmartDrop"]}


def spot_scale(spot, common=False):
    """%SmartDrop's chance scale of `spot` in PROB: CommonDropProb for a Common_Drop row, else PerPlayerDropProb;
    PROB where the spot has no row (ours)."""
    row = _smart().get(str(spot))
    return _int(row["CommonDropProb" if common else "PerPlayerDropProb"]) if row else PROB


@functools.lru_cache(maxsize=None)
def fits(code, hero):
    """Whether a %Table entry can give hero class `hero` (E_HeroCode, "REGNIER") an item: an item row whose ReqHero is
    NONE or the hero and whose Rarity is not EVENT, or a category holding such an entry."""
    cats = categories()
    if code in cats:
        return any(fits(c, hero) for c, _, _, _ in cats[code])
    row = items.row(code)
    return bool(row) and row.get("ReqHero", "NONE") in ("NONE", hero) and row.get("Rarity") != EVENT


def roll_category(cat, roll=None, hero=None):
    """[(item, count)] one pick of drop category `cat` (nested categories picked in turn), or [] when it weighs nothing
    or the pick is not an item that drops. With `hero`, only the entries that fit that class (fits) are in the draw:
    the result cards (patch notes 17.12.19: "the 4 random cards no longer hide loot for classes other than the
    player's"); the ground loot draws from every class, as the tables weigh them (1 each). `roll(n)`: 0..n-1
    (random.randrange by default)."""
    roll = roll or random.randrange
    cats = categories()
    code, lo, hi, depth = cat, 1, 1, 0
    while code in cats:
        entries = [e for e in cats[code] if hero is None or fits(e[0], hero)]
        total = sum(w for _, w, _, _ in entries)
        if not total or depth == MAX_NEST:
            return []
        x = roll(total)
        for code, w, lo, hi in entries:
            if x < w:
                break
            x -= w
        depth += 1
    row = items.row(code)
    if not row or row.get("Rarity") == EVENT:
        return []
    lo = max(1, lo)
    return [(code, lo + roll(hi - lo + 1) if hi > lo else lo)]


def roll_drops(spot, np_troop_id, leader_id=None, roll=None):
    """[(item, count)] the normal loot of an NP troop wiped in `spot`: each filled slot of its %Troop row, and of its
    leader's %Leader row, hits at Drop_Category<k>_Prob x the spot's scale (spot_scale) / PROB in PROB and then gives
    one pick of its category (roll_category)."""
    roll = roll or random.randrange
    got = []
    for section, key in (("Troop", np_troop_id), ("Leader", leader_id)):
        row = _drop_rows(section).get(str(key)) if key not in (None, -100, 0) else None
        if row is None:
            continue
        scale = spot_scale(spot, row["Common_Drop"] == "True")
        for k in range(1, SLOTS + 1):
            cat, prob = _int(row[f"Drop_Category{k}"]), _int(row[f"Drop_Category{k}_Prob"])
            if cat > 0 and prob > 0 and roll(PROB) < prob * scale // PROB:
                got += roll_category(cat, roll)
    return got


def reward_category(row, roll=None):
    """The drop category a mission_reward %DATA row pays its card from: one of Category1..10 picked by _Weight (every
    shipped row holds one category or none: 703 / 285), or None."""
    roll = roll or random.randrange
    cats = [(_int(row.get(f"Category{k}")), _int(row.get(f"Category{k}_Weight"))) for k in range(1, 11)]
    cats = [(c, w) for c, w in cats if c > 0 and w > 0]
    total = sum(w for _, w in cats)
    if not total:
        return None
    x = roll(total)
    for c, w in cats:
        if x < w:
            return c
        x -= w


@functools.cache
def _grades():
    return {(r["ID"], r["Level"]): r for r in tables.by_hash(GRADES)["Mission_Grade"]}


def grade_row(spot, level):
    """The %Mission_Grade row of `spot` at `level` (Normal / Hard / Hell), or None (10358, 10361, 10362 and the other
    spots the original did not grade)."""
    return _grades().get((str(spot), level))


def float32(text):
    """A table's decimal as the original read it, a 32-bit float (0.02 -> 0.0199999995529651...)."""
    return struct.unpack("<f", struct.pack("<f", float(text)))[0]


def _band(top, value, best, worst):
    """`top` at `best` or better, 0 at `worst` or beyond, straight between (rounded down)."""
    if value <= best:
        return top
    if value >= worst:
        return 0
    return top * (worst - value) // (worst - best)


def grade_points(row, seconds, damage=0, deaths=0, recom_party=1, players=1):
    """The result window's points and grade of a clear in `seconds` (whole seconds) on a %Mission_Grade row:
    Clear Points TimeMaxPoint at MinTime or less, 0 at MaxTime, straight between; Damage Points the same over
    MinDmg..MaxDmg with DmgMaxPoint; Participants Points PartyMaxRate x (clear + damage) x `players` / `recom_party`
    (spottable Recom_Party_<difficulty>, game.recom_party; at most the full rate); Death Penalty DeathPenaltyRate x
    deaths x (clear + damage), the rate read as a 32-bit float; Total = clear + damage + participants - penalty; the
    grade is the first of SRate / ARate / BRate / CRate that Total / ((TimeMaxPoint + DmgMaxPoint) x (1 +
    PartyMaxRate)) reaches, else D. Every product is rounded down. The tape's windows pin the divisor and the float
    (planning/rules/MISSIONS.md X2): 20305 (Recom_Party_1 4) paid 2,500 participants and -61,999 = int(float32(0.02) x
    31 x 100,000) for 31 deaths; 10306 Hard (Recom_Party_2 2) 5,000; every Recom_Party 1 window the full 10 %.

    Pinned by the footage's result windows (planning/playthrough, the frames of 15 of them, 2026-09-29): Tower 10233
    14:13 -> 100000 / 100000 / 20000 / 0 = 220000 S; Stalker Forest 10305 10:44 -> 95222 (= 100000 x (943 - 644) /
    (943 - 629)) / 100000 / 19522 = 214744 S; Deathwood 10323 8:57 -> 75732 / 100000 / 17573 = 193305 A (0.879 of
    220000, under its SRate 0.9); the spear camp 10349 4:27 -> 100000 / 48800 / 14880 = 163680 C (0.744, under its
    BRate 0.75); 10212 5:22 -> 120000 / 80000 (its TimeMaxPoint and DmgMaxPoint) / 20000. The Participants Points
    are those of one player (the only case seen). Inferred: `damage` is a count the footage shows as 0, 1 (New
    Hampton), 18 (Field of Veterans 20304, MaxDmg 779) and 192 (the spear camp, MaxDmg 375), what it counts is not
    known; the penalty per hero death (New Hampton's -19968 = 10 % of 199687 is 5 deaths at DeathPenaltyRate 0.02,
    or another count)."""
    tmax, dmax = _int(row["TimeMaxPoint"]), _int(row["DmgMaxPoint"])
    clear = _band(tmax, int(seconds), _int(row["MinTime"]), _int(row["MaxTime"]))
    dmg = _band(dmax, damage, _int(row["MinDmg"]), _int(row["MaxDmg"]))
    party_rate = Decimal(row["PartyMaxRate"] or "0")
    party = int(party_rate * (clear + dmg) * min(players, max(1, recom_party)) / max(1, recom_party))
    death = int(float32(row["DeathPenaltyRate"] or "0") * max(0, deaths) * (clear + dmg))
    total = clear + dmg + party - death
    top = (tmax + dmax) * (1 + party_rate)
    ratio = Decimal(total) / top if top else Decimal(0)
    grade = next((i for i, col in enumerate(RATES) if ratio >= Decimal(row[col] or "0")), len(RATES))
    return {"clear": clear, "damage": dmg, "party": party, "death": death, "total": total, "grade": grade}

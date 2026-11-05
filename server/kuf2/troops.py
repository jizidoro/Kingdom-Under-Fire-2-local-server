"""Troops in the barracks (WorldMapTroopListMgr = common[0xc], troop window scene 0x16). Spec: the troop map of
2026-09-27 (planning/requests/troops.md) and items_troops_skills.md G5. Troops come from contracts: TROOP_SUMMON items
(e.g. 355000000, the accept reward of tutorial 9900103) whose GainSetId names a troopsaletable %Set row (TroopID, Lv);
using one (0x4042, world.use_item) grants the troop and pushes 0x135e. The character keeps c["troops"] (dicts below),
c["lineups"] {key: {"slots": [9 uids], "set": 0}} (key "-1" = the main deck; slot 0 is the hero), c["barrack_exp"],
c["troop_pedia"]. A troop's stats at its level (level_row): its trooptable row plus each Lv column (and its LV_UP_TYPE's
lvuptypetable %Troop row) x (level - 1), as hero.stats grows the hero (the operand is not in the client: the client
asks the server, 0x1548 / 0x1348); HP = the unit's HP (HP_BASEUNIT + HPRevision per level) x UNIT_COUNT. They fill the
0x88-byte stat block of 0x1549 / 0x1349 / 0x1367 (stat_block: the troop record's +0x1c0, laid out as the hero's) and a
deck troop's combatant record in battle (combat.combatant_troop). The deck in battle: room_deck (main-deck slots 1..3,
the first spottable Limit_Troop_<difficulty> of them), game.send_start_header; AP (ap_packet) and mission exp
(gain_exp) follow the room.

  C2S 0x1346 (on entering a town, world map or room while the capacity is 0) -> S2C 0x1347 (0x140da0f30), 9 bytes
      (shorter crashes): u8 barracks capacity, u64 barracks exp pool. With 0 every contract is refused (text 7115).
  C2S 0x1342 (once a session) -> S2C 0x1343 (0x140da13f0): u16 n, n * (u32 troop id, obool favorite, compact hp,
      compact hp max, u64 uid, i16 action power, u8 level, u8 m, m * gear (u8 slot, u16 enchant, u8 rarity)); an
      unknown troop id asserts. Later changes arrive as their own packets (0x135e, ...).
  C2S 0x1340 -> S2C 0x1341 (0x140da1040): u64 hero uid, u8 n, n * (u8 0, coded u32 key, u32 set, u8 m, m * (u8 slot,
      u64 uid)).
  S2C 0x135e NotifyNewTroopInfo (0x140da3d50), 0x16 bytes (+0x14 with an officer; shorter crashes): u8 level, u64
      uid, compact hp, u32 troop id, compact hp max, obool officer. The client then asks 0x1348 and 0x1748.
  C2S 0x1348: u64 uid -> S2C 0x1349 (0x140da1e50): i16; 0 -> u64 uid, u8 n * (u8 slot, u8 level, u32 ability), the
      0xaa detail block, u8 k * badge record, obool officer (+0x90 block); a short success crashes.
  C2S 0x134c barracks -> deck (u8 slot, u8 1, u64 uid, coded u32 key), 0x134e deck -> barracks (same layout), 0x1350
      deck swap (u8 1, u8 from, u8 to, coded u32 key) -> 0x134d / 0x134f: i16; 0 -> 0x12 bytes (u8 slot, u64 uid, u32
      -> hero record +0x24 = SP_MAX here, u8 0, coded key); 0x1351: i16; 0 -> u32 (the same). 0xA403 = reload.
  C2S 0x1344 favorites: u16 n, n * (u64 uid, byte T2[flag + 2 * prev]) -> state only (0x1345 reads nothing).
  C2S 0x554f tutorial counter (every TutorialQuest* type's, 0x14082ce50): u16 count, coded u32 quest, u8 -> no reply;
      the quests of quest.TUTORIALS_COUNTED wait for it."""
import functools
import struct

from . import hero, obf, serials, tables
from .net import journal, log
from .packet import Writer

C2S_CAPACITY, S2C_CAPACITY = 0x1346, 0x1347
C2S_BARRACKS, S2C_BARRACKS = 0x1342, 0x1343
C2S_LINEUPS, S2C_LINEUPS = 0x1340, 0x1341
S2C_NEW_TROOP = 0x135e
C2S_DETAIL, S2C_DETAIL = 0x1348, 0x1349
C2S_TO_DECK, S2C_TO_DECK = 0x134c, 0x134d
C2S_TO_BARRACKS, S2C_TO_BARRACKS = 0x134e, 0x134f
C2S_DECK_SWAP, S2C_DECK_SWAP = 0x1350, 0x1351
C2S_FAVORITES = 0x1344
C2S_TRAIN, S2C_TRAIN = 0x1361, 0x1362       # training (BARRACKS_TRAINING, 0x140d9ffc0): u64 officer uid, u64 exp cost,
                                            # u64 troop uid -> 0x140da4380: i16; 0 -> 0x29 bytes (u64 pool, u64 uid, u8
                                            # level, u64 exp, u64 X (0: no officer block), u64 need)
C2S_PROMOTE, S2C_PROMOTE = 0x135f, 0x1360   # promotion (0x140e40280): u64 troop uid, u64, u32 trooptechtree ID, u64 ->
                                            # 0x140e40800: i16; 0 -> u8 level, obool officer, u64 uid, u32 new troop id
S2C_POOL = 0x1363                           # 0x140da45e0: u64 barracks exp pool (after an exp item, training, offer)
PROMOTE_REFUSED = 0x2c30                    # "E_TECH_WRONG_CONDITION"
C2S_BATTLE_DETAIL, S2C_BATTLE_DETAIL = 0x1366, 0x1367   # the deck's troops in a room: u64 uid -> i16; 0 -> u64 uid, the
                                                        # 0xaa block, obool officer
C2S_SET_EFFECT, S2C_SET_EFFECT = 0x1372, 0x1373     # useTroopSet: u32 set id, coded u32 lineup key, 1 unwritten byte ->
                                                    # i16 (0 stores it; it comes back in 0x1341 +5)
C2S_OFFER, S2C_OFFER = 0x1354, 0x1355       # BARRACKS_OFFER (at least 4 troops): u64 uid -> i16 (0 removes the troop and
                                            # shows the %TroopOffer items); 0x2c2a "Cannot use it now."
OFFER_REFUSED = 0x2c2a
C2S_EQUIP_SKILL, S2C_EQUIP_SKILL = 0x1368, 0x1369   # u64 troop uid, u32 ability -> 0x1406388d0: i16; 0 -> u8 slot,
                                                    # u32 ability, u64 uid, u8 level (short success crashes)
C2S_LEARN_SKILL, S2C_LEARN_SKILL = 0x136d, 0x136e   # LearnSkill: u32 ability, u64 troop uid -> i16 (the client keeps
                                                    # the pending entry); price learn_price (never sent in this build)
C2S_TEMPLATE, S2C_TEMPLATE = 0x1548, 0x1549         # a troop type's stats at a key: u32 troop id, u8 key -> 0x140da4670:
                                                    # 0x95-byte block (0x88 stats, coded u32 id at +0x88, u8 key, u32,
                                                    # compact hp) + obool (TRUE: a 0x8c next-grade block); 0x96 at least
TEMPLATE_BLOCK = 0x95
C2S_BADGE_ON, S2C_BADGE_ON = 0x1650, 0x1651     # a badge (TROOP_ITEM) dragged onto a troop: coded u16 bag slot, u64
                                                # troop uid, u8 troop item slot -> i16 (0 copies it from the bag view;
                                                # the bag resend must follow the reply)
C2S_BADGE_OFF, S2C_BADGE_OFF = 0x165a, 0x165b   # recover a badge: u64 uid, u16 slot, u8 kind (1 Cubic) -> i16; 0x6401
                                                # gold, 0x6430 Cubic
C2S_TACTICS_LIST, S2C_TACTICS_LIST = 0x10bb, 0x10bc   # the tactics academy's learned skills: u16 n, n * (coded u32
                                                      # ability, u32 exp, u8 level)
C2S_TACTICS_UP, S2C_TACTICS_UP = 0x1750, 0x1751       # "clickSkillLevelUP": coded u32 ability -> i16; 0 -> 5 bytes
                                                      # (unused by the client); 0x2c18 at the max, 0x6401 gold
C2S_UNEQUIP_SKILL = 0x136a                  # a troop skill dragged off (u64 troop uid, u32 ability): no reply id;
                                            # the troop's 0x1349 follows
CHEER_UP = {0x1358: 0x1359, 0x135a: 0x135b, 0x135c: 0x135d}   # AP back for gold: one troop (u64 uid) / the main deck /
                                                              # all -> ResTroopCheerUp 0x140da3950: i16; 0 -> u8 n, n *
                                                              # (u16 AP, u64 uid); 0x6401 not enough gold
C2S_TUTORIAL_COUNT = 0x554f
C2S_GEAR_ENCHANT, S2C_GEAR_ENCHANT = 0x1148, 0x1149   # CommonSubTroopEquipEnchant clickEnchant, mode 0 (0x14064dfd0): i8
                                                      # levels, u8 slot, u64 troop -> 0x14064e670: i16; 0 -> i8 levels,
                                                      # u8 slot, u64 troop (troop +0x2b4 + slot x 8 += levels);
                                                      # 0x6401 gold (0x1b94), 0x2c5d material, else 0x1c64
C2S_GEAR_UPGRADE, S2C_GEAR_UPGRADE = 0x114a, 0x114b   # mode 1 (the piece at its MaxEnchant): u8 slot, u64 troop ->
                                                      # 0x14064e820: i16; 0 -> u8 slot, u64 troop; the client takes
                                                      # the next rarity itself (0x1418ac110) at +0
GEAR_MATERIAL_SHORT = 0x2c5d
EQUIP_TYPES = ("WEAPON", "ARMOR", "ACCESSORIES")      # E TroopEquipType 0..2: the gear slots (troop +0x2b0 + slot x 8)
ITEM_RARITY = ("NONE", "NORMAL", "MAGIC", "RARE", "HERO", "UNIQUE", "CASH", "EVENT")   # E ItemRarity (the 0x1343
                                                      # gear byte; 8 = "the lowest", 0x1418ac040)
GEAR_FROM_GRADE = 3                                   # 0x140d97150: a troop above GRADE2 carries gear,
GEAR_SLOT_RARITY = (3, 4, 5)                          # slot k from TroopRarity 3 + k (0x1422b2a08)
SET_LEVEL = 1       # a set status's level: the set window's (UISceneTroopSetEffect 0x1409dd6c0 buckets the average
                    # TroopGrade of the components it finds in the lineup, 0x140d98f20 comparing troop ids with the
                    # component ids; the shipped components are TroopGroupIDs, so it finds none: level 1)
C2S_PEDIA, S2C_PEDIA = 0x136f, 0x1370       # the troop book (T12.6): 0x136f on every entry (0x140d9b2c0), no body ->
                                            # 0x140da5900: u16 n, n coded u32 troop ids (it keeps those > 999999, the
                                            # %TroopPedia ids, grouped: 0x140d9bd50); the Troop Setting window's counts
S2C_PEDIA_ONE = 0x1371                      # 0x140da5a20: one coded u32, a troop type new to the book (not -1)
PEDIA_MIN = 1000000                         # the book's ids (0x140da5900 skips the rest)
BARRACK_BASE = 24               # the client's own base before expansions (item_currency walk 0x14188db50); Cubic
                                # expansions add 3 each up to 60 (c["barrack_cap"])
C2S_EXPAND, S2C_EXPAND = 0x10aa, 0x10ab     # SlotExpand, message 0xd018 answered Yes (0x14063e9e0; the client
                                            # priced it with 0x14188db50 type 7 at the capacity mgr+0x10 and checked
                                            # its Cubic): no payload -> 0x140da5ad0: i16; 0 -> text 0xd036, 0x6430 ->
                                            # 0xd01b, other -> 0xd01d; the new capacity comes with 0x1347 (0x140da0f30
                                            # sets mgr+0x10 and refreshes windows 0x16 / 0x15 / 0x4b)
TROOP_CAP_REACHED = 0x2c03      # 0x4043 code: text 7115
DECK_RELOAD = 0xA403            # 0x134d: the client drops its list and asks 0x1340 again
MAIN_DECK = "-1"
UNEQUIPPED = 0xff               # a troop skill's slot while it is learned but in none of the four (t["skills"] entries)
DETAIL_BLOCK = 0xaa
STAT_BLOCK = 0x88               # the stat block of 0x1549 +0 and 0x1349 / 0x1367 detail +0x12: copied to the troop record
DETAIL_STATS_AT = 0x12          # +0x1c0..0x247 (0x140da4670, 0x140da1e50), the record the hero's 0x134b block fills from
                                # its bytes 0x04..0x8b (world.HERO_STAT_AT) and UpdateDetailInfo 0x140d9ce40 writes by
                                # stat id (base record +0x20): the same offsets, less 4
S2C_AP = 0x1365                 # ProcessPacket_NotifyActionPower 0x140da3b90 (0x1364 has the same handler): i16 0, u8 n,
                                # n x (i16 AP, u64 uid) -> troop record +0x50, then the windows refresh (0x140d9e030)
DECK_SLOTS = (1, 2, 3)          # the mission slots of the main deck: 0x140d6b3f0 walks slots 1..3 (0x140d97870(mgr, slot,
                                # -1)) and stops after Limit_Troop_<difficulty> filled ones; the entry window shows three
# trooptable per-level growth columns and the stat each grows (x (level - 1)); HPRevision is the unit HP's (its rows keep
# the same ratio to HP_BASEUNIT as LvPhysicalAttack to ATTACK_PHYSICAL: 6015's 0.572 on every pair)
GROWTH = {"LvPhysicalAttack": "ATTACK_PHYSICAL", "LvMagicalAttack": "ATTACK_MAGICAL",
          "LvPhysicalDefence": "DEFENCE_PHYSICAL", "LvMagicalDefence": "DEFENCE_MAGICAL",
          "LvFireDefence": "DEFENCE_MAGICAL_FIRE", "LvIceDefence": "DEFENCE_MAGICAL_ICE",
          "LvLightningDefence": "DEFENCE_MAGICAL_LIGHTNING", "LvNatureDefence": "DEFENCE_MAGICAL_NATURE",
          "LvHolyDefence": "DEFENCE_MAGICAL_HOLY", "LvDarkDefence": "DEFENCE_MAGICAL_DARK",
          "LvPCriticalProbability": "CRITICALPROB_PHYSICAL", "LvMCriticalProbability": "CRITICALPROB_MAGICAL",
          "LV_ACCURACY": "ACCURACY", "LV_MISS": "MISS", "LV_PHYSICAL_PENETRATE": "PHYSICAL_PENETRATE",
          "LV_MAGICAL_PENETRATE": "MAGICAL_PENETRATE", "LvHPRecovery": "HP_RECOVERY", "HPRevision": "HP_BASEUNIT"}
# lvuptypetable %Troop (the row LV_UP_TYPE names), the same way; 0 on every stat of the 14 types trooptable uses but
# HERO_PROG_TEMP_TROOP (its LvCount / LvCountStep, 10 / 11 on troop 100's type 449, are not read: their meaning is open)
TYPE_GROWTH = {"LvPhysicalDefence": "DEFENCE_PHYSICAL", "LvMagicalDefence": "DEFENCE_MAGICAL",
               "LvHPRecovery": "HP_RECOVERY", "LvPCriticalProbability": "CRITICALPROB_PHYSICAL",
               "LvPCriticalMag": "CRITICAL_PHYSICAL", "LvMCriticalProbability": "CRITICALPROB_MAGICAL",
               "LvMCriticalMag": "CRITICAL_MAGICAL", "LV_ACCURACY": "ACCURACY", "LV_MISS": "MISS",
               "LvUnitHP": "HP_BASEUNIT"}
ELEMENTS = ("FIRE", "ICE", "LIGHTNING", "NATURE", "HOLY", "DARK")
STATS = ("HP_BASEUNIT", "HP_RECOVERY", "ATTACK_PHYSICAL", "ATTACK_MAGICAL", "DEFENCE_PHYSICAL", "DEFENCE_MAGICAL",
         "MAX_MOVE_SPEED", "PHYSICAL_PENETRATE", "MAGICAL_PENETRATE", "CRITICALPROB_PHYSICAL", "CRITICAL_PHYSICAL",
         "CRITICALPROB_RESIST", "CRITICAL_REDUCE", "CRITICALPROB_MAGICAL", "CRITICAL_MAGICAL", "ACCURACY", "MISS",
         "GUARD_REDUCE", "RANGE_SIGHT", "ENGAGE_ATTACK_REVISION", "MAIN_ATTACK_REVISION", "SP_RECOVERY") + tuple(
         "DEFENCE_MAGICAL_" + e for e in ELEMENTS)
# a badge's trait names (item_troop BASE_TRAIT_*, target ALL) that stand for several of the row's stats; HP_MAX adds to
# each unit (ours: the badge's value is read per unit, as the troop's own HP columns)
BADGE_STATS = {"M_DEFENCE_PHYSICAL": ("DEFENCE_PHYSICAL",), "M_DEFENCE_MAGICAL": ("DEFENCE_MAGICAL",),
               "HP_MAX": ("HP_BASEUNIT",)}


def troop_row(troop_id):
    return _troop_rows().get(str(troop_id))


@functools.cache
def _troop_rows():
    return {r["TROOP_ID"]: r for r in tables.sections("trooptable")["Contents"]}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def level_row(troop_id, level=1, badges=(), traits=()):
    """A troop's stats at `level` as an nptrooptable-like row (the columns combat's records read), or None: every
    STATS column of its trooptable row plus GROWTH / TYPE_GROWTH x (level - 1) (level clamped to 1..MAX_LEVEL); the
    element defences as DEFENCE_MAGICAL plus the element column (trooptable's element columns are offsets: 0 on 2,340
    of 5,760, 103 / -53 on the rest, where nptrooptable's equal the generic one on 68,399 of 76,236); UNIT_COUNT (one
    trooptable row per star: the stars add soldiers); the attack range RANGE_ATTACK_MIN / _MAX of its trooptype
    (TroopType) MAINATTACK_RANGE_MIN / _MAX; ATTACK_SPEED = GENERAL_ATTACK_SPEED; then each badge's ADD traits
    (badge_traits, BADGE_STATS; the "N%" ones after the numbers); then `traits` [(stat, value, percent)] (a room's
    passives: room_row) as combat.add_traits adds them. The troop gear (troopequipment) is not added: no troop carries
    any here."""
    r = troop_row(troop_id)
    if r is None:
        return None
    top = int(_num(r.get("MAX_LEVEL"))) or 1
    level = max(1, min(int(level or 1), top))
    out = {k: _num(r.get(k)) for k in STATS}             # the element columns are offsets until the end
    kind = next((x for x in tables.sections("lvuptypetable")["Troop"] if x["ID"] == r.get("LV_UP_TYPE")), {})
    for table, growth in ((r, GROWTH), (kind, TYPE_GROWTH)):
        for col, name in growth.items():
            out[name] += _num(table.get(col)) * (level - 1)
    system = next((x for x in tables.sections("trooptype")["System"] if x["TroopType"] == r.get("TroopType")), {})
    out.update(RANGE_ATTACK_MIN=_num(system.get("MAINATTACK_RANGE_MIN")),
               RANGE_ATTACK_MAX=_num(system.get("MAINATTACK_RANGE_MAX")), ATTACK_SPEED=_num(r.get("GENERAL_ATTACK_SPEED")))
    worn = [t for code in badges for t in badge_traits(code)]
    for name, value, percent in sorted(worn, key=lambda t: t[2]):       # the numbers, then the "x%" (hero.stats' order)
        for n in BADGE_STATS.get(name, (name,)):
            out[n] = out.get(n, 0.0) + (out.get(n, 0.0) * value / 100 if percent else value)
    for e in ELEMENTS:
        out["DEFENCE_MAGICAL_" + e] += out["DEFENCE_MAGICAL"]
    out.update(TROOP_ID=r["TROOP_ID"], TroopType=r.get("TroopType"), LEVEL_CURRENT=level,
               UNIT_COUNT=max(1, int(_num(r.get("UNIT_COUNT")))))
    if traits:
        from .combat import add_traits
        out = add_traits(out, traits)
    return out


def badge_traits(code):
    """[(stat name, value, percent)] a badge adds (item_troop BASE_TRAIT_TYPE<i> / BASE_VALUE<i>, operation ADD, target
    ALL): 111 plain numbers and 79 "N%" values (301110100: ATTACK_PHYSICAL 1%), a share of the stat."""
    from . import items
    r = items.row(code) or {}
    out = []
    for i in range(5):
        name, value = r.get(f"BASE_TRAIT_TYPE{i}", "-"), str(r.get(f"BASE_VALUE{i}", "0"))
        if name not in ("-", "") and r.get(f"BASE_OPERATION{i}") == "ADD":
            out.append((name, _num(value.rstrip("%")), value.endswith("%")))
    return out


def _enum(v, prefix):
    """GRADE3 -> 3, RARITY5 -> 5 (the client's TroopGrade / TroopRarity enums: NONE 0, then 1..)."""
    v = str(v or "")
    return int(v[len(prefix):]) if v.startswith(prefix) and v[len(prefix):].isdigit() else 0


@functools.cache
def _gear_rows():
    """{(TroopGroupID, slot): {ItemRarity index: troopequipment %Basic row}} (the client's registry: per slot, by
    group, by rarity, 0x1418ac040)."""
    out = {}
    for r in tables.sections("troopequipment")["Basic"]:
        if r["Equip_Type"] in EQUIP_TYPES and r["Rarity"] in ITEM_RARITY:
            out.setdefault((r["TroopGroupID"], EQUIP_TYPES.index(r["Equip_Type"])), {})[
                ITEM_RARITY.index(r["Rarity"])] = r
    return out


def gear_row(troop_id, slot, rarity=None):
    """The troopequipment %Basic row of troop_id's group in `slot` at ItemRarity index `rarity` (None: the lowest the
    group has, as the client's default 0x1418ac040(.., 8)), or None."""
    group = (troop_row(troop_id) or {}).get("TroopGroupID")
    by = _gear_rows().get((group, slot)) or {}
    return by.get(min(by) if rarity is None and by else rarity)


def gear(t):
    """[(slot, %Basic row, enchant)] troop t wears (T13.1): its stored pieces (t["gear"]: slot, enchant, rarity; what
    an enchant or upgrade made, sent in 0x1343), else the default the client gives it (0x140d97150): a troop above
    GRADE2 has, in slot k from TroopRarity 3 + k, its group's lowest-rarity piece at +0."""
    r = troop_row(t["id"]) or {}
    kept = {g["slot"]: g for g in t.get("gear", [])}
    out = []
    for slot in range(len(EQUIP_TYPES)):
        if slot in kept:
            row = gear_row(t["id"], slot, kept[slot].get("rarity"))
            if row is not None:
                out.append((slot, row, kept[slot].get("enchant", 0)))
        elif (_enum(r.get("TroopGrade"), "GRADE") >= GEAR_FROM_GRADE
              and _enum(r.get("TroopRarity"), "RARITY") >= GEAR_SLOT_RARITY[slot]):
            row = gear_row(t["id"], slot)
            if row is not None:
                out.append((slot, row, 0))
    return out


@functools.cache
def _gear_traits():
    out = {}
    for r in tables.sections("troopequipment")["EnchantTrait"]:
        out.setdefault(r["Equip_Id"], []).append(r)
    return out


def gear_traits(t):
    """[(stat, value, False)] troop t's gear adds (T1.9): each piece's troopequipment %EnchantTrait rows (FunctionType
    ADD on all 2,775), Base + ENCHANT<its level>; HP_MAX per unit, as a badge's (ours [I])."""
    out = []
    for _, row, enchant in gear(t):
        for x in _gear_traits().get(row["Equip_Id"], []):
            v = _num(x.get("Base")) + (_num(x.get(f"ENCHANT{enchant}")) if enchant else 0)
            if x.get("FunctionType") == "ADD" and v:
                out.append((x["TraitType"], v, False))
    return out


def enchant_cost_row(t, slot, row):
    """The troopequipment %EnchantCost row of a piece: (the troop's TroopGrade, the slot's Equip_Type, the piece's
    Rarity), as the window's 0x1418ac240 looks it up."""
    grade = (troop_row(t["id"]) or {}).get("TroopGrade")
    return next((r for r in tables.sections("troopequipment")["EnchantCost"] if r["TroopGrade"] == grade
                 and r["Equip_Type"] == EQUIP_TYPES[slot] and r["Equip_Rarity"] == row["Rarity"]), None)


def enchant_price(cost, current, target):
    """(gold, material, count) of enchanting a piece from `current` to `target` (0x14064d980: Enchant<k>_Gold x
    BaseGold summed over the levels passed, the loader 0x1418acc10 multiplying; 0x14064d810: Enchant_Count a level)."""
    num = lambda v: int(v) if str(v).isdigit() else 0
    gold = sum(num(cost.get(f"Enchant{k}_Gold")) * num(cost.get("BaseGold")) for k in range(current + 1, target + 1))
    return gold, num(cost.get("Enchant_Material")), num(cost.get("Enchant_Count")) * (target - current)


def held(c, code):
    return sum(i["count"] for i in c.get("bag", []) if i["code"] == code)


def troop_level_row(t):
    """level_row of a barracks troop dict: its id, level, badges and gear (gear_traits)."""
    return level_row(t["id"], t.get("level", 1), [b["code"] for b in t.get("badges", [])], gear_traits(t))


def set_row(set_id):
    return next((r for r in tables.sections("troopsaletable")["Set"] if r["SetID"] == str(set_id)), None)


def troop_need(troop_id, level):
    r = troop_row(troop_id) or {}
    row = next((x for x in tables.sections("lvexptable")["TroopExp"] if x["ID"] == r.get("TROOP_EXP_GRADE")), {})
    v = row.get(str(level), "0")
    return int(v) if v.isdigit() else 0


def unit_hp(r):
    """One unit's HP of a level_row, the fraction dropped (T1.3: the tape's Drafted Infantry Lv 6 shows 8,830 =
    floor(211 + 134.5 x 5) x 10, part 2 f_00920; the battle keeps unit HP in whole points)."""
    return max(1, int(r["HP_BASEUNIT"] + 1e-6))


def troop_hp(troop_id, level=1):
    """A troop's HP at `level`: its unit HP there x its units (level 1: HP_BASEUNIT x UNIT_COUNT, troop 100's 2110)."""
    r = level_row(troop_id, level)
    return unit_hp(r) * r["UNIT_COUNT"] if r else 0


def stat_values(r):
    """{stat name: value} of a level_row for the stat block, named as hero.stats names the hero's (world.HERO_STAT_AT):
    one attack value is both ends of the ATTACK_*_MIN / _MAX range, DEFENCE_PHYSICAL both the close and ranged one."""
    out = dict(r)
    for side in ("PHYSICAL", "MAGICAL"):
        out[f"ATTACK_{side}_MIN"] = out[f"ATTACK_{side}_MAX"] = r[f"ATTACK_{side}"]
    out["DEFENCE_PHYSICAL_CLOSE"] = r.get("DEFENCE_PHYSICAL_ENGAGE", r["DEFENCE_PHYSICAL"])   # split by a passive
    out["DEFENCE_PHYSICAL_RANGE"] = r.get("DEFENCE_PHYSICAL_RANGE", r["DEFENCE_PHYSICAL"])    # (add_traits)
    return out


def stat_block(r):
    """The 0x88-byte stat block of a level_row (or zeros for None): the hero block's bytes 0x04..0x8b as
    world.write_hero_stats lays them out (i32 / f32 crit damage / attack in tenths / the compact HP recovery)."""
    from . import world
    b = bytearray(world.HERO_BLOCK)
    if r is not None:
        world.write_hero_stats(b, stat_values(r))
    return bytes(b[4:4 + STAT_BLOCK])


def lineup(c, key=MAIN_DECK):
    return c.setdefault("lineups", {}).setdefault(key, {"slots": [0] * 9, "set": 0})


def find(c, uid):
    return next((t for t in c.get("troops", []) if t["uid"] == uid), None)


def grant(c, set_id):
    """A contract's troop (troopsaletable %Set: TroopID at Lv) into the barracks: (troop, 0) or (None, refusal)."""
    from . import world
    row = set_row(set_id)
    tr = troop_row(row["TroopID"]) if row else None
    if tr is None:
        return None, 1
    if len(c.get("troops", [])) >= c.get("barrack_cap", BARRACK_BASE):
        return None, TROOP_CAP_REACHED
    t = {"uid": serials.troop_uid(c), "id": int(row["TroopID"]), "level": int(row["Lv"]),
         "exp": 0, "ap": int(tr["ActingPower"]) if tr["ActingPower"].isdigit() else 100, "favorite": False,
         "gear": [], "skills": default_skills(c, int(row["TroopID"])), "sp": 0, "leader": None}
    c.setdefault("troops", []).append(t)
    pedia_add(c, t["id"])
    log.info("troop %d level %d joined (set %s)", t["id"], t["level"], set_id)
    journal("troop", ev="contract", troop=t["id"], level=t["level"], set=set_id)
    return t, 0


def pedia_add(c, troop_id):
    """Troop type troop_id into the character's troop book (c["troop_pedia"], sorted); True when it is new there."""
    pedia = c.setdefault("troop_pedia", [])
    if troop_id in pedia:
        return False
    pedia.append(troop_id)
    pedia.sort()
    return True


def pedia_packet(c):
    """0x1370, the troop book: every troop type the character has held."""
    ids = c.get("troop_pedia", [])
    w = Writer(S2C_PEDIA).u16(len(ids))
    for tid in ids:
        w.raw(obf.u32(tid))
    return w


def pedia_one_packet(troop_id):
    """0x1371 for a type new to the book, or None for an id the book does not keep (PEDIA_MIN)."""
    return Writer(S2C_PEDIA_ONE).raw(obf.u32(troop_id)) if troop_id >= PEDIA_MIN else None


def troop_set_row(set_id):
    return next((r for r in tables.sections("trooptechtree")["TroopSet"] if r["TroopSetID"] == str(set_id)), None)


def set_effect(c, key=MAIN_DECK):
    """(status, level) of lineup key's chosen troop set (0x1372 -> c["lineups"][key]["set"]; T1.10) while the lineup
    holds a troop of every ComponentTroop<n>ID group in its slots 1..8 (the deck window's check 0x140d9c860: each
    component a TroopGroupID, 0x1418bbbc0 its troops), else None: trooptechtree %TroopSet StatusEffectID (Target
    TROOP) at SET_LEVEL."""
    lu = (c.get("lineups") or {}).get(key) or {}
    row = troop_set_row(lu.get("set", 0)) if lu.get("set") else None
    if row is None or not str(row.get("StatusEffectID", "")).isdigit():
        return None
    groups = {(troop_row(t["id"]) or {}).get("TroopGroupID") for t in (find(c, u) for u in lu.get("slots", [])[1:9]
                                                                          if u) if t}
    comps = [row[f"ComponentTroop{k}ID"] for k in range(1, 9) if row.get(f"ComponentTroop{k}ID", "-") not in ("-", "")]
    return (int(row["StatusEffectID"]), SET_LEVEL) if comps and all(g in groups for g in comps) else None


def journal_deck(c, key):
    """The journal's line for a deck change: the troop (table id) in each of deck key's slots 1..8, 0 empty."""
    journal("troop", ev="deck", deck=int(key), slots=[(find(c, u) or {}).get("id", 0) if u else 0
                                                     for u in lineup(c, key)["slots"][1:]])


def pool_cap(level):
    """barrack %BarrackLimitExp LV_<hero level>: the most exp the barracks pool holds."""
    row = tables.sections("barrack")["BarrackLimitExp"][0]
    v = row.get(f"LV_{level}", "0")
    return int(v) if v.isdigit() else 0


def add_pool(c, amount):
    c["barrack_exp"] = min(c.get("barrack_exp", 0) + amount, pool_cap(c.get("level", 1)))
    return c["barrack_exp"]


def pool_packet(c):
    return Writer(S2C_POOL).u64(c.get("barrack_exp", 0))


def training_gold(troop_id, levels):
    """barrack %TrainingGold [TroopGrade] LV_l summed over the levels passed (the client checks it; charging it is
    inferred: the request carries only the exp)."""
    r = troop_row(troop_id) or {}
    row = next((x for x in tables.sections("barrack")["TrainingGold"] if x["TroopGrade"] == r.get("TroopGrade")), {})
    return sum(int(row.get(f"LV_{l}", "0")) if str(row.get(f"LV_{l}", "0")).isdigit() else 0 for l in levels)


def train(c, t, cost):
    """Spend `cost` pool exp on troop t, levelling through %TroopExp up to MAX_LEVEL: (levels passed) or None."""
    r = troop_row(t["id"]) or {}
    top = int(r.get("MAX_LEVEL", "1")) if str(r.get("MAX_LEVEL", "")).isdigit() else 1
    if cost <= 0 or cost > c.get("barrack_exp", 0) or t["level"] >= top:
        return None
    exp, level, passed = t["exp"] + cost, t["level"], []
    while level < top and exp >= troop_need(t["id"], level) > 0:
        exp -= troop_need(t["id"], level)
        passed.append(level)
        level += 1
    return passed, level, exp


LEVEL_TREATMENT_ROW = 1        # the barrack loader's LevelTreatment parser 0x14192f910 seeks row index 1 (ID 2: 0.7 at
                               # Lv 1 .. 35 at Lv 30) before it reads LV_1..LV_50 into holder +0x30 (the BarrackLimitExp
                               # parser 0x14192fdc0 seeks row 0); the tape pins it: part 4 f_00745, 50 gold for a Lv 7
                               # troop 100 at 45 / 100 AP (row 0 would ask 38)


def f32(x):
    """x rounded to a float32, as an SSE mulss leaves it."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def cheer_cost(t):
    """(gold, AP max) of encouraging troop t: GetTroopCheerUpMoney 0x140d99f20 in float32 as it runs, xmm7 =
    LevelTreatment[level] x the AP missing, then x TreatmentConstant(TroopRarity), then x
    TreatmentConstant_Grade(TroopGrade), truncated (cvttss2si); LevelTreatment row LEVEL_TREATMENT_ROW, 0 outside
    levels 1..50 (0x14192f740); the discount term is x 0.0 (0x140d9a399). Modes 1 / 2 (the lineup, all troops) sum these
    per troop, as cheer_up does."""
    b = tables.sections("barrack")
    r = troop_row(t["id"]) or {}
    level = t["level"]
    lt = f32(float(b["LevelTreatment"][LEVEL_TREATMENT_ROW].get(f"LV_{level}", "0") or 0)) if 1 <= level <= 50 else 0.0
    tc = {x["TroopRarity"]: f32(float(x["TreatmentConstant"])) for x in b["TreatmentConstant"]}
    tg = {x["TroopGrade"]: f32(float(x["TreatmentConstant_Grade"])) for x in b["TreatmentConstant"]}
    top = int(r.get("ActingPower", "100")) if str(r.get("ActingPower", "")).isdigit() else 100
    missing = max(0, top - t["ap"])
    return int(f32(tg.get(r.get("TroopGrade"), 0.0) * f32(tc.get(r.get("TroopRarity"), 0.0) * f32(lt * missing)))), top


def badge_price(code, pay="Gold"):
    """item_consume_sub %ExtractBadge: Use<pay>Count1 of the badge's Rarity row x Use<pay>Count2 of its StarRating row
    (pay "Gold" or "Cubic"). The client's grid (built at load 0x14184a550..0x14184a605: imul of the two columns, an
    i64 gold and an i32 Cubic cell per rarity x star; looked up by 0x14184dbf0) is what its confirm box 0x140653160
    checks against the gold (+0x108) or the Cubic (+0x118) before sending 0x165a (read 2026-09-30; rules census O10)."""
    from . import items
    r = items.row(code) or {}
    rows = tables.sections("item_consume_sub")["ExtractBadge"]
    a = next((x for x in rows if x["ItemRarity"] == r.get("Rarity")), {})
    b = next((x for x in rows if x["StarRating"] == r.get("StarRating")), {})
    num = lambda v: int(v) if str(v).isdigit() else 0
    return num(a.get(f"Use{pay}Count1")) * num(b.get(f"Use{pay}Count2"))


def badge_cubic(code):
    return badge_price(code, "Cubic")


@functools.cache
def _academy_rows():
    return {r["AbilityID"]: r for r in tables.sections("tacticsacademy")["Basic"]}


def academy(c):
    """{ability (str): {"level", "exp"}} the tactics academy holds for character c: every tacticsacademy row with
    AbilityMinLevel 1 at that level from the start (116 rows: the %NewSkill groups' first skills, 81001 among them),
    then what was learned or levelled there (c["tactics"]: 0x1750, skill books). The original's list held them: the
    troop skill window (0x1409b2a30) reads a skill's level only from this map (WorldMapTroopListMgr +0x690, 0x140d9b610;
    absent = level 0, "Can be equipped after learning the skill", text 60073), and troop 100 carried 81001 into Grey
    Rock without an academy visit (the tape, part 2 f_01092)."""
    out = {aid: {"level": int(r["AbilityMinLevel"]), "exp": 0} for aid, r in _academy_rows().items()
           if r["AbilityMinLevel"].isdigit() and int(r["AbilityMinLevel"]) > 0}
    out.update({str(aid): t for aid, t in c.get("tactics", {}).items()})
    return out


def skill_level(c, ability):
    """A troop skill's level: the tactics academy's (academy; 0 = not held). The client keeps it so too: 0x10bd
    (0x140da5310) sets the new level in the academy map and in every barracks troop's skill list (+0x250) holding the
    ability, and the equip window shows the academy's level (T5.3). A skill the academy has no row for (the NP
    troops' 500045, 200147) is never a player troop's own."""
    return academy(c).get(str(ability), {}).get("level", 0)


def tactics_packet(c):
    """0x10bc, the academy's list (academy: the held-from-the-start skills too)."""
    learned = academy(c)
    w = Writer(S2C_TACTICS_LIST).u16(len(learned))
    for aid, t in sorted(learned.items(), key=lambda kv: int(kv[0])):
        w.raw(obf.u32(int(aid))).u32(t.get("exp", 0)).u8(t["level"])
    return w


def tactics_price(ability, level):
    """tacticsacademy %Basic Levelup_CostGroup -> item_currency %TroopSkill_Levelup (CostGroup, Level) Index -> %Base
    (TroopSkill_Levelup, Index): (currency, count)."""
    row = next((r for r in tables.sections("tacticsacademy")["Basic"] if r["AbilityID"] == str(ability)), None)
    if row is None:
        return None
    ic = tables.sections("item_currency")
    idx = next((r["Index"] for r in ic["TroopSkill_Levelup"]
                if r["CostGroup"] == row["Levelup_CostGroup"] and r["Level"] == str(level)), None)
    base = next((r for r in ic["Base"] if r["ItemCurrencyType"] == "TroopSkill_Levelup" and r["Index"] == idx), None)
    if base is None:
        return None
    count = base["Gold_Count"] if base["CurrencyType"] == "Gold" else base.get("Cubic_Count", "0")
    return base["CurrencyType"], int(count) if str(count).isdigit() else 0


PASSIVE_SLOTS = range(4, 8)     # the client's troop skill slots: 0..3 = %NewSkill SkillGroupID_A_1..4, 4..7 = _P_1..4
                                # (the %NewSkill reader 0x1418bcbe3 fills the troop row +0x2dc + slot x 4 from the
                                # suffix table 0x1434e0c40 "A_1".."P_4"; the equip window 0x1409b2a30 takes a slot's
                                # group from there, and the 0x1369 / 0x136e replies store the skill under that slot byte)


def skill_slot(troop_id, ability):
    """The slot of an ability on a troop (PASSIVE_SLOTS): the index of the trooptable %NewSkill SkillGroupID_A_n
    (0..3) or _P_n (4..7) whose %SkillGroup lists it, or None."""
    t = tables.sections("trooptable")
    row = next((r for r in t["NewSkill"] if r["TROOP_ID"] == str(troop_id)), None)
    if row is None:
        return None
    groups = {g["SkillGroupID"]: g for g in t["SkillGroup"]}
    for base, kind in ((0, "A"), (PASSIVE_SLOTS.start, "P")):
        for n in range(1, 5):
            g = groups.get(row.get(f"SkillGroupID_{kind}_{n}", "-"))
            if g and str(ability) in [g.get(f"SkillId_{k}") for k in range(1, 6)]:
                return base + n - 1
    return None


def skill_allowed(troop_id, ability):
    """Client skill-window gate: SkillGrade <= TroopRarity (0x1409b2a30, row +0x380), within its own groups.

    TroopGrade is a different field (+0x434); the old census called this the troop's grade incorrectly.
    """
    row = _academy_rows().get(str(ability))
    rarity = _enum((troop_row(troop_id) or {}).get("TroopRarity"), "RARITY")
    return row is not None and _num(row.get("SkillGrade")) <= rarity and skill_slot(troop_id, ability) is not None


def default_skills(c, troop_id):
    """The skills a troop comes with, one per active slot up to its trooptable MaxActiveSkill: the first skill of
    %NewSkill SkillGroupID_A_<slot + 1> the tactics academy holds (skill_level above 0: tacticsacademy AbilityMinLevel
    1, or learned there). Inferred from the original: Grey Rock's F1, troop 100 from the first contract, shows 81001
    Shield Use I (group 100's first) in C1 (playthrough part 2 36:22, f_01092, its icon Impregnable_Discipline_I). The
    passive slots start empty: every passive group's skill is AbilityMinLevel 0 (learned at the academy first) but
    ten TACTICS ones, and no tape frame shows a new troop's passive. The level is the academy's (skill_level), read
    where it is sent, not kept here."""
    t = tables.sections("trooptable")
    new = next((r for r in t["NewSkill"] if r["TROOP_ID"] == str(troop_id)), None)
    top = _num((troop_row(troop_id) or {}).get("MaxActiveSkill"))
    if new is None:
        return []
    groups = {g["SkillGroupID"]: g for g in t["SkillGroup"]}
    out = []
    for slot in range(min(4, int(top))):
        g = groups.get(new.get(f"SkillGroupID_A_{slot + 1}", "-")) or {}
        for aid in (g.get(f"SkillId_{k}", "-") for k in range(1, 6)):
            if aid.isdigit() and skill_level(c, aid) > 0 and skill_allowed(troop_id, int(aid)):
                out.append({"slot": slot, "id": int(aid)})
                break
    return out


def equipped(c, t, slots=range(4)):
    """[(slot, ability, level)] of troop t's skills in `slots` (the actives by default; PASSIVE_SLOTS the passive
    ones), by slot, each at the academy's level (skill_level); a skill the academy no longer holds is left out (the
    client builds no ability at level 0)."""
    out = [(k["slot"], k["id"], skill_level(c, k["id"])) for k in t.get("skills", []) if k.get("slot") in slots]
    return sorted(x for x in out if x[2] > 0)


def passives(c, t):
    """{ability: level} of troop t's passives (T1.11): its skills in PASSIVE_SLOTS whose abilitytypeinfo Category is
    AUTOMATIC (the passive groups also hold TACTICS AUTOCASTING skills, which the client auto-casts), at the academy's
    level."""
    from .status import automatic
    return {a: lv for _, a, lv in equipped(c, t, PASSIVE_SLOTS) if a in automatic()}


def room_row(c, t, live=True):
    """Troop t's stats inside a room: troop_level_row with its passives' traits (status.passive_traits at the troop's
    level; a community note has "Sharp Insight" apply only inside a mission, so the barracks windows keep the plain
    row). live False leaves out the traits the resolver reads from the held statuses itself (the combat record's
    row: combat.status_bonus on ATTACK_*), True shows them all (the room's troop window, 0x1367)."""
    from . import status
    level = t.get("level", 1)
    traits = gear_traits(t) + status.passive_traits(passives(c, t), level, live=live)
    worn = set_effect(c)                        # the main deck's set status: its non-speed traits (T1.10)
    if worn and any(u == t.get("uid") for u in lineup(c)["slots"][1:]):
        traits += status.status_traits([worn], level, live=live)
    return level_row(t["id"], level, [b["code"] for b in t.get("badges", [])], traits)


def reconcile_skills(c, t):
    """Keep valid choices after evolution; replace obsolete skills using the new troop's default groups.

    Existing valid UNEQUIPPED entries preserve the player's choice. Filling obsolete slots uses the same default
    selection as recruitment; exact original promotion slot selection remains inferred (VANILLA-ITEMS.md).
    """
    before = t.get("skills", [])
    kept = [dict(k, slot=skill_slot(t["id"], k["id"]) if k.get("slot") != UNEQUIPPED else UNEQUIPPED)
            for k in before if skill_allowed(t["id"], k["id"])]
    if before and kept == before:
        return False
    for k in default_skills(c, t["id"]):
        if not any(x["slot"] == k["slot"] or x["id"] == k["id"] for x in kept):
            kept.append(k)
    if kept == before:
        return False
    t["skills"] = kept
    return True


def give_default_skills(c):
    """Repair missing/obsolete troop skills at login, preserving valid unequipped entries. Number changed."""
    n = 0
    for t in c.get("troops", []):
        n += reconcile_skills(c, t)
    return n


def seat(t, slot, ability):
    """Ability into slot (equip 0x1368, learn 0x136d, whose reply the client applies to the slot); the skill that sat
    there stays with the troop out of the slots (UNEQUIPPED), so the login migration does not give it back."""
    for k in t.get("skills", []):
        if k.get("slot") == slot and k["id"] != ability:
            k["slot"] = UNEQUIPPED
    t["skills"] = [k for k in t.get("skills", []) if k["id"] != ability] + [{"slot": slot, "id": ability}]


def learn_price(ability):
    """(gold, Cubic) the troop skill window asks to learn a skill: tacticsacademy SkillOpenGold / SkillOpenCash (the
    window's g_aSkillLearnGold / g_aSkillLearnCubic, filled from the academy row +0x20 / +0x1c by 0x1409b2a30 for a
    skill at academy level 0). Both are 0 on all 506 rows of this build, and LearnSkill (0x140636b40) returns at once
    when both are 0: the client never asks to learn (0x136d); the window shows 60073 "Can be equipped after learning
    the skill" and the academy teaches it (0x1750, TroopSkill_Levelup level 1)."""
    r = _academy_rows().get(str(ability)) or {}
    num = lambda v: int(v) if str(v).isdigit() else 0
    return num(r.get("SkillOpenGold")), num(r.get("SkillOpenCash"))


def barracks_packet(c):
    """0x1343, the barracks list (the reply to 0x1342, resent after a change the client does not apply itself)."""
    from . import world
    known = [t for t in c.get("troops", []) if troop_row(t["id"])]
    w = Writer(S2C_BARRACKS).u16(len(known))
    for t in known:
        hp = world.stat_code(hp_of(t))
        w.u32(t["id"]).obool(t.get("favorite", False)).raw(hp).raw(hp).u64(t["uid"]).raw(struct.pack("<h", t["ap"]))
        w.u8(t["level"]).u8(len(t.get("gear", [])))
        for g in t.get("gear", []):
            w.u8(g["slot"]).u16(g.get("enchant", 0)).u8(g["rarity"])
    return w


S2C_TACTICS_ONE = 0x10bd        # one tactics skill (WorldMapTroopListMgr 0x140da5310), 9 bytes: coded u32 ability, u32
                                # exp (inferred), u8 level; updates the tactics map and the troops' skill vectors


def tactics_book(c, ability, exp):
    """A troop skill book (TROOP_SKILL_BOOK: SkillBookAbilityID, SkillBookExp) read into the tactics academy: learned at
    tacticsacademy AbilityMinLevel, exp added and levelled through lvexptable %TroopSkillExp (the row of the skill's
    TroopSkillExpType, column = the current level: the exp to the next) up to AbilityMaxLevel. Returns the entry, or
    None when the skill is unknown or already at its max (the client refuses that itself, 0x11944)."""
    row = next((r for r in tables.sections("tacticsacademy")["Basic"] if r["AbilityID"] == str(ability)), None)
    if row is None:
        return None
    top = int(row["AbilityMaxLevel"]) if row["AbilityMaxLevel"].isdigit() else 1
    learned = c.setdefault("tactics", {})
    t = learned.setdefault(str(ability), {"level": int(row["AbilityMinLevel"] or 0), "exp": 0})
    if t["level"] >= top:
        return None
    need_row = next((r for r in tables.sections("lvexptable")["TroopSkillExp"] if r["ID"] == row["TroopSkillExpType"]), {})
    t["exp"] += exp
    while t["level"] < top:
        need = int(need_row.get(str(t["level"]), "0") or 0)
        if need <= 0 or t["exp"] < need:
            break
        t["exp"] -= need
        t["level"] += 1
    if t["level"] >= top:
        t["exp"] = 0
    return t


def tactics_one_packet(ability, t):
    return Writer(S2C_TACTICS_ONE).raw(obf.u32(ability)).u32(t.get("exp", 0)).u8(t["level"])


def new_troop_packet(t):
    from . import world
    hp = world.stat_code(hp_of(t))
    return Writer(S2C_NEW_TROOP).u8(t["level"]).u64(t["uid"]).raw(hp).u32(t["id"]).raw(hp).obool(False)


def hp_of(t):
    """A barracks troop's HP: its unit HP at its level (with its badges) x its units."""
    r = troop_level_row(t)
    return unit_hp(r) * r["UNIT_COUNT"] if r else 0


def detail_block(t, r=None):
    """The 0xaa detail block of 0x1349 / 0x1367 (reader 0x140da6180, applied by 0x140da1e50): +0 u64 exp (record
    +0x38), +0x0c i16 AP (+0x50, in the states 0x140d66220 allows), +0x0e / +0x9a compact HP / max (+0x28 / +0x30),
    +0x12 the stat block (+0x1c0), +0xa2 u64 exp the level needs (+0x40); +0x08 / +0x9e (u32 -> +0x48 / +0x4c) are not
    pinned and stay 0. r: the stat row (troop_level_row, or room_row for the room's 0x1367)."""
    from . import world
    r = r or troop_level_row(t)
    b = bytearray(DETAIL_BLOCK)
    struct.pack_into("<Q", b, 0x00, t["exp"])
    struct.pack_into("<h", b, 0x0c, t["ap"])
    hp = world.stat_code(unit_hp(r) * r["UNIT_COUNT"] if r else 0)
    b[0x0e:0x12] = hp
    b[0x9a:0x9e] = hp
    b[DETAIL_STATS_AT:DETAIL_STATS_AT + STAT_BLOCK] = stat_block(r)
    struct.pack_into("<Q", b, 0xa2, troop_need(t["id"], t["level"]))
    return bytes(b)


def detail_packet(c, t):
    """0x1349 for a troop: its skills (the handler 0x140da1e50 clears the troop's 4 skill slots, then sets each listed
    one: u8 slot, u8 level (the academy's, skill_level), u32 ability), the detail block, its badges, no officer."""
    from . import items
    skills = equipped(c, t)
    w = Writer(S2C_DETAIL).u16(0).u64(t["uid"]).u8(len(skills))
    for slot, ability, level in skills:
        w.u8(slot).u8(level).u32(ability)
    w.raw(detail_block(t))
    badges = [b for b in t.get("badges", []) if 0 <= b["slot"] < 3]
    w.u8(len(badges))
    for b in badges:
        w.raw(items.record(b["code"], b["slot"], b["serial"], 1, items.durability(b),
                           bound=b.get("bound", False), enchant=b.get("enchant", 0), sockets=items.sockets(b),
                           options=b.get("options", ())))
    return w.obool(False)


def deck_levels(c):
    """[(level, exp, need)] of the main deck's slots 0..8 for 0x124a (slot 0, the hero's own troop slot, stays 0)."""
    slots = lineup(c)["slots"]
    out = []
    for i in range(9):
        t = find(c, slots[i]) if i else None
        out.append((t["level"], t["exp"], troop_need(t["id"], t["level"])) if t else (0, 0, 0))
    return out


def deck_limit(spot, difficulty=0):
    """How many deck troops a spot takes on a difficulty: spottable Limit_Troop_<difficulty + 1> ("-" is 0). The client
    reads only these three (the spot loader 0x141864800.. puts them at SpotInfo +0x1b4 / +0x224 / +0x294, Min_Limit_Troop
    at +0x1a0, Limit_SubTroop at +0x1a4; no code names the plain Limit_Troop column: its string is only the tail of
    "Min_Limit_Troop" and nothing loads it), and uses them as the deck's participants: 0x140d6b3f0 checks the first
    Limit_Troop_<d> filled main-deck slots against the spot's BranchId (refusal 0x2c34), the entry window
    (0x1406606f0 / 0x140662267) asks "The number of organised troops is lower than that of the participatory troops"
    (text 61200) when fewer are organised (Q34)."""
    row = tables.by_id("spottable").get(str(spot)) or {}
    v = str(row.get(f"Limit_Troop_{difficulty + 1}", "-"))
    return int(v) if v.isdigit() else 0


def room_deck(c, spot, difficulty=0):
    """[(deck slot, troop)] a room takes: the filled main-deck slots of DECK_SLOTS in order, the first deck_limit of
    them (a uid the barracks lacks is skipped). Min_Limit_Troop, the original server's own entry minimum (its refusal
    0x1c21 prints text 7475 "At least %1% troops must be organised in order to continue." with it: 0x140d6834b in
    the Common error switch 0x140d673d0, and 0x5641's error case 0x140cbfbf9), is not enforced here (an owner call)."""
    slots = ((c.get("lineups") or {}).get(MAIN_DECK) or {}).get("slots") or []
    out = []
    for k in DECK_SLOTS:
        t = find(c, slots[k]) if k < len(slots) and slots[k] else None
        if t is not None and troop_row(t["id"]) is not None:
            out.append((k, t))
    return out[:deck_limit(spot, difficulty)]


def spot_cost(spot, column):
    """A spot's AP cost (spottable Troop_Mission_Enter 15 / Troop_Mission_Clear 5 / Troop_Death 5 /
    Troop_Mission_aborted 15 on the story missions: the official notes' "20 AP per mission")."""
    v = str((tables.by_id("spottable").get(str(spot)) or {}).get(column, "0"))
    return int(v) if v.isdigit() else 0


def spend_ap(ts, cost):
    """Take `cost` AP from each troop (never below 0: "A troop with 0 AP cannot fight", text 5740; the client's own
    entry check asks to restore it, text 53436)."""
    for t in ts:
        t["ap"] = max(0, t.get("ap", 0) - cost)


def ap_packet(ts):
    """S2C_AP for troops ts: their AP now."""
    w = Writer(S2C_AP).u16(0).u8(len(ts))
    for t in ts:
        w.raw(struct.pack("<h", t["ap"])).u64(t["uid"])
    return w


def exp_type_rate(kind):
    """lvexptable %ExpTypeRate ExpRate of HERO / TROOP / BARRACK (1 / 1 / 0.25)."""
    row = next((r for r in tables.sections("lvexptable")["ExpTypeRate"] if r["ExpType"] == kind), {})
    return _num(row.get("ExpRate", 1))


def gain_exp(c, t, amount):
    """A mission's exp for troop t (every deployed troop the same, dead ones too: DATAMINE-ROUND2 §4.1): at most one
    level a mission, the exp then held at the new level's need - 1 (OFFICIAL-NOTES "Level up restriction", 99/100);
    the rest is lost. A troop at its MAX_LEVEL keeps nothing (the window's "Max XP"): the barracks pool gets one share
    a win whoever is at the max (barracks_share; the tape's 20304 / 20305 windows, two Lv 30 troops, one share). The
    hero's level does not cap it (the barracks' does). Returns (level before, the exp it kept): the window's troop
    line (T2.3: 369 / 53 at New Hampton, not the 375 paid; record slot +0x3b)."""
    before, had = t["level"], t["exp"]
    top = int(_num((troop_row(t["id"]) or {}).get("MAX_LEVEL"))) or 1
    if amount <= 0:
        return before, 0
    if t["level"] >= top:
        t["exp"] = 0
        return before, 0
    exp, need = t["exp"] + amount, troop_need(t["id"], t["level"])
    if need > 0 and exp >= need:
        t["level"] += 1
        exp = 0 if t["level"] >= top else min(exp - need, max(0, troop_need(t["id"], t["level"]) - 1))
    t["exp"] = exp
    gained = t["exp"] - had + (need if t["level"] > before else 0)
    journal("troop", ev="exp", troop=t["id"], uid=t["uid"], add=amount, level=t["level"], up=t["level"] - before,
            exp=t["exp"], need=troop_need(t["id"], t["level"]))
    return before, gained


def exp_percent(t):
    """Troop t's exp as a whole percent of its level's need (0 at its max): the result window's gauge ends (record
    troop slot +0x51 before / +0x52 after; PlayExp 0x14085d650 sends AddExp = (after - before) x 100 - start + end,
    the gauge's units; the flooring is ours)."""
    need = troop_need(t["id"], t["level"])
    top = int(_num((troop_row(t["id"]) or {}).get("MAX_LEVEL"))) or 1
    return 0 if need <= 0 or t["level"] >= top else min(100, t["exp"] * 100 // need)


def barracks_share(amount):
    """The barracks pool's share of a won mission whose troops get `amount` (T2.4): floor(amount x lvexptable
    %ExpTypeRate BARRACK 0.25), once a win. Every result window of the tape: 93 of 375 (10235), 120 of 480 (10306),
    144 of 576 (10212), 170 / 180 / 196 / 127 / 122 / 135, and 2 x 256 / 422 / 435 under the x2 event (the share
    floored first)."""
    return int(amount * exp_type_rate("BARRACK") + 1e-9)


def mission_pool(c, amount):
    """Put a won mission's barracks share of `amount` into the pool (add_pool: up to %BarrackLimitExp); returns what
    went in: the result record's +0x297, "Barracks Saved EXP" (T2.5)."""
    was = c.get("barrack_exp", 0)
    if amount <= 0 or was >= pool_cap(c.get("level", 1)):
        return 0
    return add_pool(c, barracks_share(amount)) - was


def sp_max(c):
    st = hero.stats(c["class"], c.get("level", 1), hero.worn_codes(c), hero.worn_enchants(c))
    return round(st.get("SP_MAX", 0))


def capacity_packet(c):
    return Writer(S2C_CAPACITY).u8(c.get("barrack_cap", BARRACK_BASE)).u64(c.get("barrack_exp", 0))


def make(role, state):
    @role.on(C2S_CAPACITY)
    def capacity(s, pkt):
        s.send(capacity_packet(s.data["char"]))

    @role.on(C2S_EXPAND)
    def expand(s, pkt):
        from . import world
        c = s.data["char"]
        result = world.expand(s, state, "barrack", "barrack_cap", c.get("barrack_cap", BARRACK_BASE))
        s.send(Writer(S2C_EXPAND).u16(result))
        if not result:
            s.send(capacity_packet(c))          # 0x1347 at any time: the capacity and the open windows follow

    @role.on(C2S_BARRACKS)
    def barracks(s, pkt):
        s.send(barracks_packet(s.data["char"]))

    @role.on(C2S_LINEUPS)
    def lineups(s, pkt):
        c = s.data["char"]
        lineup(c)                                           # the main deck always exists
        w = Writer(S2C_LINEUPS).u64(c["id"]).u8(len(c["lineups"]))
        for key, lu in sorted(c["lineups"].items()):
            slots = [(i, uid) for i, uid in enumerate(lu["slots"]) if i and uid]
            w.u8(0).raw(obf.u32(int(key) & 0xFFFFFFFF)).u32(lu.get("set", 0)).u8(len(slots))
            for i, uid in slots:
                w.u8(i).u64(uid)
        s.send(w)

    @role.on(C2S_DETAIL)
    def detail(s, pkt):
        uid = pkt.u64()
        t = find(s.data["char"], uid)
        if t is None:
            s.send(Writer(S2C_DETAIL).u16(1))
            return
        s.send(detail_packet(s.data["char"], t))

    def deck_reply(proto, c, slot, uid, key):
        return (Writer(proto).u16(0).u8(slot).u64(uid).u32(sp_max(c)).u8(0).raw(obf.u32(int(key) & 0xFFFFFFFF)))

    @role.on(C2S_TO_DECK)
    def to_deck(s, pkt):
        b = pkt.rest()
        if len(b) < 14:
            return
        slot, uid, key = b[0], struct.unpack_from("<Q", b, 2)[0], str(struct.unpack("<i", struct.pack("<I", obf.dec_u32(b[10:14])))[0])
        c = s.data["char"]
        if find(c, uid) is None or not 1 <= slot <= 8:
            s.send(Writer(S2C_TO_DECK).u16(DECK_RELOAD))
            return
        slots = lineup(c, key)["slots"]
        slots[:] = [0 if x == uid else x for x in slots]
        slots[slot] = uid
        state.save()
        s.send(deck_reply(S2C_TO_DECK, c, slot, uid, key))
        log.info("troop %#x into deck %s slot %d", uid, key, slot)
        journal_deck(c, key)

    @role.on(C2S_TO_BARRACKS)
    def to_barracks(s, pkt):
        b = pkt.rest()
        if len(b) < 14:
            return
        slot, uid, key = b[0], struct.unpack_from("<Q", b, 2)[0], str(struct.unpack("<i", struct.pack("<I", obf.dec_u32(b[10:14])))[0])
        c = s.data["char"]
        slots = lineup(c, key)["slots"]
        if 1 <= slot <= 8 and slots[slot] == uid:
            slots[slot] = 0
            state.save()
            journal_deck(c, key)
        s.send(deck_reply(S2C_TO_BARRACKS, c, slot, uid, key))

    @role.on(C2S_DECK_SWAP)
    def deck_swap(s, pkt):
        b = pkt.rest()
        if len(b) < 7:
            return
        a, z, key = b[1], b[2], str(struct.unpack("<i", struct.pack("<I", obf.dec_u32(b[3:7])))[0])
        c = s.data["char"]
        slots = lineup(c, key)["slots"]
        if 1 <= a <= 8 and 1 <= z <= 8:
            slots[a], slots[z] = slots[z], slots[a]
            state.save()
            journal_deck(c, key)
        s.send(Writer(S2C_DECK_SWAP).u16(0).u32(sp_max(c)))

    @role.on(C2S_TRAIN)
    def training(s, pkt):
        from . import world
        b = pkt.rest()
        if len(b) < 0x18:
            return
        cost, uid = struct.unpack_from("<QQ", b, 8)
        c = s.data["char"]
        t = find(c, uid)
        got = train(c, t, cost) if t else None
        gold = training_gold(t["id"], got[0]) if got else 0
        if got is None or c.get("gold", 0) < gold:
            s.send(Writer(S2C_TRAIN).u16(0x6401 if got else 1))
            return
        passed, t["level"], t["exp"] = got
        c["barrack_exp"] -= cost
        if gold:
            world.add_gold(s, state, -gold)
        state.save()
        s.send(Writer(S2C_TRAIN).u16(0).u64(c["barrack_exp"]).u64(uid).u8(t["level"]).u64(t["exp"]).u64(0)
               .u64(troop_need(t["id"], t["level"])))
        from . import quest, titles
        titles.achieve(s, state, "TroopDedicate", add=1)
        if passed:                                  # a troop level-up: TroopLvUpgrade quests and daily tasks
            quest.count(s, state, "TroopLvUpgrade", "ID1", {"", "-"}, by=len(passed))
        log.info("troop %#x trained: level %d, exp %d (%d pool exp, %d gold)", uid, t["level"], t["exp"], cost, gold)

    @role.on(C2S_PROMOTE)
    def promote(s, pkt):
        from . import quest, world
        b = pkt.rest()
        if len(b) < 0x14:
            return
        uid, row_id = struct.unpack_from("<Q", b, 0)[0], struct.unpack_from("<I", b, 0x10)[0]
        c = s.data["char"]
        t = find(c, uid)
        row = next((r for r in tables.sections("trooptechtree")["TroopTechtree"]
                    if r["ID"] == str(row_id) and t and r["BaseTroopID"] == str(t["id"])), None)
        num = lambda v: int(v) if str(v).isdigit() else 0
        need = [(num(row[f"RepuireItemID_{k}"]), num(row[f"RepuireItemNumber_{k}"])) for k in range(1, 6)
                if num(row.get(f"RepuireItemID_{k}"))] if row else []
        held = lambda code: sum(i["count"] for i in c.get("bag", []) if i["code"] == code)
        done = quest.record(c)["done"]
        ok = (row is not None and troop_row(row["ChangeTroopID"]) is not None
              and t["level"] >= num(row["RequireBaseTroopLevel"]) and c.get("level", 1) >= num(row["HeroLevel"])
              and all(held(code) >= n for code, n in need) and c.get("gold", 0) >= num(row.get("CostGold"))
              and all(num(row.get(f"RequireCompletedQuestID_{k}")) in done
                      for k in range(1, 6) if num(row.get(f"RequireCompletedQuestID_{k}"))))
        if not ok:
            log.warning("promotion of %#x by row %d refused", uid, row_id)
            s.send(Writer(S2C_PROMOTE).u16(PROMOTE_REFUSED))
            return
        for code, n in need:
            world.remove_item(s, state, code, n)
        if num(row.get("CostGold")):
            world.add_gold(s, state, -num(row["CostGold"]))
        old = t["id"]
        t["id"] = int(row["ChangeTroopID"])
        reconcile_skills(c, t)
        new = troop_row(t["id"])                    # the reply 0x140e40800 rebuilds the troop at AP = the new row's
        t["ap"] = int(new["ActingPower"]) if str(new.get("ActingPower", "")).isdigit() else t["ap"]   # ActingPower
        fresh = pedia_add(c, t["id"])
        state.save()
        s.send(Writer(S2C_PROMOTE).u16(0).u8(t["level"]).obool(False).u64(uid).u32(t["id"]))
        if fresh and pedia_one_packet(t["id"]):
            s.send(pedia_one_packet(t["id"]))       # a type new to the book (0x1371; that a promotion sends it: [I])
        from . import titles
        titles.achieve(s, state, "TroopAdvance", add=1)
        quest.count(s, state, "TroopUpgrade", "ID1", {"", "-", str(old)})
        log.info("troop %#x promoted %d -> %d", uid, old, t["id"])

    @role.on(C2S_BATTLE_DETAIL)
    def battle_detail(s, pkt):
        uid = pkt.u64()
        c = s.data.get("char") or s.data["account"]["characters"][0]
        t = find(c, uid)
        if t is None:
            s.send(Writer(S2C_BATTLE_DETAIL).u16(1))
            return
        s.send(Writer(S2C_BATTLE_DETAIL).u16(0).u64(uid).raw(detail_block(t, room_row(c, t))).obool(False))

    @role.on(C2S_SET_EFFECT)
    def set_effect(s, pkt):
        b = pkt.rest()
        if len(b) < 8:
            return
        set_id, key = struct.unpack_from("<I", b, 0)[0], str(struct.unpack("<i", struct.pack("<I", obf.dec_u32(b[4:8])))[0])
        known = any(r["TroopSetID"] == str(set_id) for r in tables.sections("trooptechtree")["TroopSet"])
        if not known and set_id:
            s.send(Writer(S2C_SET_EFFECT).u16(1))
            return
        lineup(s.data["char"], key)["set"] = set_id
        state.save()
        s.send(Writer(S2C_SET_EFFECT).u16(0))

    @role.on(C2S_OFFER)
    def offer(s, pkt):
        from . import world
        uid = pkt.u64()
        c = s.data["char"]
        t = find(c, uid)
        in_deck = any(uid in lu["slots"] for lu in c.get("lineups", {}).values())
        if t is None or in_deck or len(c.get("troops", [])) < 4:
            s.send(Writer(S2C_OFFER).u16(OFFER_REFUSED))
            return
        r = troop_row(t["id"]) or {}
        row = next((x for x in tables.sections("barrack")["TroopOffer"] if x["Dedication_ID"] == r.get("Dedication_ID")), {})
        exp = t["exp"] + sum(troop_need(t["id"], l) for l in range(1, t["level"]))
        c["troops"].remove(t)
        add_pool(c, exp * (int(row.get("ExpGainRate", "0")) if str(row.get("ExpGainRate", "")).isdigit() else 0) // 1000)
        state.save()
        s.send(Writer(S2C_OFFER).u16(0))
        for k in range(1, 6):
            item = row.get(f"ItemID_{k}", "-")
            if item.isdigit():
                world.add_item(s, state, int(item), int(row.get(f"Value_{k}", "1") or 1))
        s.send(pool_packet(c))
        log.info("troop %#x (%d) offered: pool %d", uid, t["id"], c["barrack_exp"])

    @role.on(C2S_EQUIP_SKILL)
    def equip_skill(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            return
        uid, ability = struct.unpack_from("<QI", b, 0)
        c = s.data["char"]
        t = find(c, uid)
        slot = skill_slot(t["id"], ability) if t else None
        level = skill_level(c, ability)
        if slot is None or not level or not skill_allowed(t["id"], ability):
            s.send(Writer(S2C_EQUIP_SKILL).u16(1))      # (level above 0; else LearnSkill), 0x1409b2a30
            return
        seat(t, slot, ability)
        state.save()
        s.send(Writer(S2C_EQUIP_SKILL).u16(0).u8(slot).u32(ability).u64(uid).u8(level))

    @role.on(C2S_LEARN_SKILL)
    def learn_skill(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            return
        ability, uid = struct.unpack_from("<IQ", b, 0)
        from . import world
        c = s.data["char"]
        t = find(c, uid)
        slot = skill_slot(t["id"], ability) if t else None
        gold, cubic = learn_price(ability)
        if slot is None or not skill_level(c, ability) or not skill_allowed(t["id"], ability):
            s.send(Writer(S2C_LEARN_SKILL).u16(1))
            return
        if cubic:                                           # no row asks Cubic (SkillOpenCash 0 on all 506)
            s.send(Writer(S2C_LEARN_SKILL).u16(0x6430))
            return
        if c.get("gold", 0) < gold:
            s.send(Writer(S2C_LEARN_SKILL).u16(0x6401))
            return
        if not any(k["id"] == ability for k in t.setdefault("skills", [])):
            seat(t, slot, ability)
        if gold:
            world.add_gold(s, state, -gold)
        state.save()
        s.send(Writer(S2C_LEARN_SKILL).u16(0))

    @role.on(C2S_TEMPLATE)
    def template(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        troop_id, key = struct.unpack_from("<IB", b, 0)
        from . import world
        a = bytearray(TEMPLATE_BLOCK)                    # the key is the level (the training window asks its troop's
        r = level_row(troop_id, key)                     # level + 1 after each 0x1362, live 09-28 02:58)
        a[0:STAT_BLOCK] = stat_block(r)
        a[0x88:0x8c] = obf.u32(troop_id)
        a[0x8c] = key
        a[0x91:0x95] = world.stat_code(unit_hp(r) * r["UNIT_COUNT"] if r else 0)
        s.send(Writer(S2C_TEMPLATE).raw(bytes(a)).obool(False))

    @role.on(C2S_BADGE_ON)
    def badge_on(s, pkt):
        from . import items, world
        b = pkt.rest()
        if len(b) < 11:
            return
        bag_slot, uid, slot = obf.dec_u16(b[0:2]), struct.unpack_from("<Q", b, 2)[0], b[10]
        c = s.data["char"]
        t = find(c, uid)
        it = next((i for i in c.get("bag", []) if i["slot"] == bag_slot), None)
        if t is None or it is None or slot >= 3 or (items.row(it["code"]) or {}).get("ItemKind") != "TROOP_ITEM":
            s.send(Writer(S2C_BADGE_ON).u16(1))
            return
        world.take_serial(c, it["serial"], 1)
        t["badges"] = [x for x in t.get("badges", []) if x["slot"] != slot] + [
            {"slot": slot, "code": it["code"], "serial": it["serial"], "bound": True, "enchant": it.get("enchant", 0)}]
        state.save()
        s.send(Writer(S2C_BADGE_ON).u16(0))              # before the bag: the client copies the badge from its bag view
        world.send_cargo(s)

    @role.on(C2S_BADGE_OFF)
    def badge_off(s, pkt):
        from . import world
        b = pkt.rest()
        if len(b) < 11:
            return
        uid, slot, kind = struct.unpack_from("<QHB", b, 0)
        c = s.data["char"]
        t = find(c, uid)
        badge = next((x for x in t.get("badges", []) if x["slot"] == slot), None) if t else None
        if badge is None:
            s.send(Writer(S2C_BADGE_OFF).u16(1))
            return
        price = badge_cubic(badge["code"]) if kind == 1 else badge_price(badge["code"])
        if c.get("cubic" if kind == 1 else "gold", 0) < price:
            s.send(Writer(S2C_BADGE_OFF).u16(0x6430 if kind == 1 else 0x6401))
            return
        t["badges"].remove(badge)
        c.setdefault("bag", [])
        used = {i["slot"] for i in c["bag"]}
        lo, hi = world.bag_range(c, badge["code"])
        free = next(k for k in range(lo, hi) if k not in used)                   # the client checked a slot is free
        c["bag"].append({"code": badge["code"], "slot": free, "count": 1, "serial": badge["serial"],
                         "bound": badge.get("bound", False), "enchant": badge.get("enchant", 0)})
        if kind == 1:
            world.spend_cubic(s, state, price)
        else:
            world.change_gold(c, -price)
        state.save()
        s.send(Writer(S2C_BADGE_OFF).u16(0))
        world.send_cargo(s)

    @role.on(C2S_TACTICS_LIST)
    def tactics_list(s, pkt):
        s.send(tactics_packet(s.data["char"]))

    @role.on(C2S_TACTICS_UP)
    def tactics_up(s, pkt):
        from . import world
        b = pkt.rest()
        if len(b) < 4:
            return
        ability = obf.dec_u32(b[0:4])
        c = s.data["char"]
        row = _academy_rows().get(str(ability))
        learned = c.setdefault("tactics", {})
        cur = skill_level(c, ability)                   # a skill held from the start (AbilityMinLevel 1) is at 1
        top = int(row["AbilityMaxLevel"]) if row and row["AbilityMaxLevel"].isdigit() else 0
        price = tactics_price(ability, cur + 1) if row and cur < top else None
        if price is None:
            s.send(Writer(S2C_TACTICS_UP).u16(0x2c18))
            return
        currency, count = price                         # Gold, or Cubic (CostGroups 3 / 4 / 5 = SkillGrade 3..5, 256
        if currency not in ("Gold", "Cubic"):           # abilities, at every level from 1: 6..1,230; rules census O8;
                                                        # the client pre-checks either, texts 7060 / 0xd01b)
            s.send(Writer(S2C_TACTICS_UP).u16(0x2c18))
            return
        if c.get("gold" if currency == "Gold" else "cubic", 0) < count:
            s.send(Writer(S2C_TACTICS_UP).u16(0x6401 if currency == "Gold" else 0x6430))
            return
        learned[str(ability)] = {"level": cur + 1, "exp": 0}
        if currency == "Cubic":
            world.spend_cubic(s, state, count)
        else:
            world.add_gold(s, state, -count)
        state.save()
        s.send(Writer(S2C_TACTICS_UP).u16(0).raw(obf.u32(ability)).u8(cur + 1))
        s.send(tactics_one_packet(ability, learned[str(ability)]))     # 0x10bd: the academy map and every troop's
                                                        # skill list (+0x250) and deck quick slot take the new level
                                                        # (0x140da5310); the full list 0x10bc refreshes the map only

    @role.on(C2S_UNEQUIP_SKILL)
    def unequip_skill(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            return
        uid, ability = struct.unpack_from("<QI", b, 0)
        t = find(s.data["char"], uid)
        if t is not None:
            for k in t.get("skills", []):
                if k.get("id") == ability:
                    k["slot"] = UNEQUIPPED              # still learned (give_default_skills leaves the troop alone)
            state.save()
            s.send(detail_packet(s.data["char"], t))    # no 0x136b exists and the builder 0x140e4f930 changes nothing: the
                                                # detail's skill list clears the slot (items_troops_skills.md 0x136a)

    def cheer_up(s, pkt):
        from . import world
        c = s.data["char"]
        reply = CHEER_UP[pkt.proto]
        if pkt.proto == 0x1358:
            chosen = [t for t in [find(c, pkt.u64())] if t]
        elif pkt.proto == 0x135a:
            chosen = [t for t in (find(c, u) for u in lineup(c)["slots"][1:]) if t]
        else:
            chosen = list(c.get("troops", []))
        costs = [(t, *cheer_cost(t)) for t in chosen]
        total = sum(cost for _, cost, _ in costs)
        if c.get("gold", 0) < total:
            s.send(Writer(reply).u16(0x6401))
            return
        for t, _, top in costs:
            t["ap"] = top
        if total:
            world.add_gold(s, state, -total)
        state.save()
        w = Writer(reply).u16(0).u8(len(costs))
        for t, _, top in costs:
            w.u16(top).u64(t["uid"])
        s.send(w)

    for req in CHEER_UP:
        role.on(req)(cheer_up)

    @role.on(C2S_FAVORITES)
    def favorites(s, pkt):
        b = pkt.rest()
        n = struct.unpack_from("<H", b, 0)[0] if len(b) >= 2 else 0
        c = s.data["char"]
        for i in range(min(n, (len(b) - 2) // 9)):
            uid = struct.unpack_from("<Q", b, 2 + 9 * i)[0]
            t = find(c, uid)
            if t is not None:
                t["favorite"] = bool(obf.T1[b[2 + 9 * i + 8]] & 1)
        state.save()

    def store_gear(t, slot, rarity, enchant):
        t["gear"] = sorted([g for g in t.get("gear", []) if g["slot"] != slot]
                           + [{"slot": slot, "enchant": enchant, "rarity": rarity}], key=lambda g: g["slot"])

    def worn_piece(c, uid, slot):
        """(troop, (%Basic row, enchant), its %EnchantCost row, MaxEnchant) of a troop's gear slot, Nones if absent."""
        t = find(c, uid)
        piece = next(((row, e) for k, row, e in gear(t) if k == slot), None) if t else None
        cost = enchant_cost_row(t, slot, piece[0]) if piece else None
        top = int(cost["MaxEnchant"]) if cost and str(cost["MaxEnchant"]).isdigit() else 0
        return t, piece, cost, top

    def pay(s, c, gold, material, count, why):
        """Take the gold and materials, or the refusal code (0x6401 gold, GEAR_MATERIAL_SHORT)."""
        from . import world
        if c.get("gold", 0) < gold:
            return 0x6401
        if held(c, material) < count:
            return GEAR_MATERIAL_SHORT
        if count:
            world.remove_item(s, state, material, count, why=why)
        if gold:
            world.add_gold(s, state, -gold)
        return 0

    @role.on(C2S_GEAR_ENCHANT)
    def gear_enchant(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            return
        levels, slot, uid = struct.unpack_from("<bBQ", b, 0)
        c = s.data["char"]
        t, piece, cost, top = worn_piece(c, uid, slot)
        if cost is None or levels <= 0 or piece[1] + levels > top:
            s.send(Writer(S2C_GEAR_ENCHANT).u16(1))
            return
        gold, material, count = enchant_price(cost, piece[1], piece[1] + levels)
        refused = pay(s, c, gold, material, count, f"troop gear enchant {uid:#x}")
        if refused:
            s.send(Writer(S2C_GEAR_ENCHANT).u16(refused))
            return
        store_gear(t, slot, ITEM_RARITY.index(piece[0]["Rarity"]), piece[1] + levels)
        state.save()
        s.send(Writer(S2C_GEAR_ENCHANT).u16(0).raw(struct.pack("<bBQ", levels, slot, uid)))
        log.info("troop %#x gear %d (%s) +%d -> +%d: %d gold, %d x%d", uid, slot, piece[0]["Equip_Id"], piece[1],
                 piece[1] + levels, gold, material, count)

    @role.on(C2S_GEAR_UPGRADE)
    def gear_upgrade(s, pkt):
        b = pkt.rest()
        if len(b) < 9:
            return
        slot, uid = struct.unpack_from("<BQ", b, 0)
        c = s.data["char"]
        t, piece, cost, top = worn_piece(c, uid, slot)
        rarity = ITEM_RARITY.index(piece[0]["Rarity"]) if piece else 0
        better = sorted(k for k in _gear_rows().get((piece[0]["TroopGroupID"], slot), {}) if k > rarity) if piece else []
        if cost is None or not better or piece[1] < top:    # the window upgrades a piece at its MaxEnchant only
            s.send(Writer(S2C_GEAR_UPGRADE).u16(1))          # (0x1409d1fc0 -> mode 1)
            return
        num = lambda v: int(v) if str(v).isdigit() else 0
        gold, material, count = (num(piece[0]["Upgrade_Gold"]), num(piece[0]["Upgrade_Material"]),
                                 num(piece[0]["Upgrade_Count"]))
        refused = pay(s, c, gold, material, count, f"troop gear upgrade {uid:#x}")
        if refused:
            s.send(Writer(S2C_GEAR_UPGRADE).u16(refused))
            return
        store_gear(t, slot, better[0], 0)           # the next rarity of the group's slot (0x1418ac110), +0
        state.save()
        s.send(Writer(S2C_GEAR_UPGRADE).u16(0).raw(struct.pack("<BQ", slot, uid)))
        log.info("troop %#x gear %d upgraded %s -> rarity %d: %d gold, %d x%d", uid, slot, piece[0]["Equip_Id"],
                 better[0], gold, material, count)

    @role.on(C2S_PEDIA)
    def pedia(s, pkt):
        s.send(pedia_packet(s.data["char"]))

    @role.on(C2S_TUTORIAL_COUNT)
    def tutorial_count(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            return
        count, qid = struct.unpack_from("<H", b, 0)[0], obf.dec_u32(b[2:6])
        from . import quest
        q = quest.record(s.data["char"])["active"].get(str(qid))
        if q is not None:
            q["counts"][0] = max(q["counts"][0], min(count, 1))
            state.save()
            if q.get("tutorial") and q["counts"][0]:        # the hand-in waited for this (quest.tutorial_waits)
                quest.journal_quest("done", qid, q)
        log.info("tutorial quest %d counter %d", qid, count)

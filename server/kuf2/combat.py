"""Battle damage, server side. The host client simulates movement and AI and reports every hit (C2S 0x5053,
UnitHitSystem::DoHitUnit) without a damage amount; the original server computed damage and broadcast the results.
Each hit's amount comes from `resolve` (planning/wiring/BATTLE-WIRING.md §3 candidate A, owner Q6 2026-09-27): the
attacker's and the target's combatant records (`combatant_hero` / `combatant_np` / `combatant_leader`, from the tables)
and the attack (the hit's %Combat slot, or the cast ability's %Improvement row).

Messages (client build 4766023):
- C2S 0x5132 combat mode request (builder 0x14053c130, sent when the hero starts a combat-enter action): encoded troop
  uid (T2[hi], T1[lo]), then T2[(on + 2 * byte0) & 0xff]. S2C 0x5133 (0x140d18110): u8 n, n * (u16 uid, byte b with
  T1[b] & 1 = on) -> the troop's hero vt+0xdb8 SetCombatMode (hero+0x1030). Out of combat mode the hero keeps the
  town action set (COMMON_NORMAL_*) and does not attack.
- C2S 0x5058 engage report (builder 0x1405407b0, troop AI): troop A uid, a flag byte (raw 0 = disengage), troop B uid,
  uids encoded (T2[hi], T1[lo]). The server echoes it as S2C 0x5059 (0x140d16fb0, same 5 bytes), which is what
  actually adds/removes the engagement on troop B (troop+0x370).
- C2S 0x5053 hit report (builder 0x140544710): 15-byte header (+8 coded u16 attacker troop, +0xa u16 >> 7 attacker
  unit, +0xd u16 the attacker's E_ActionEnum; hit_source), then u16 n targets, each: u16 encoded troop uid, u16 m hits,
  m * 6 bytes (+4 u8 and +5 bit0 = unit index + 3; -1 = leader).
- S2C 0x505d troop hp (0x140d17a30), S2C 0x505b unit live/dead (Packet_TroopMemberLiveInfo 0x140d17100):
  u16 uid, u16 n, n * (obool alive, i16 unit index).
"""
import functools, math, random, struct, time

from .net import log
from . import net, obf
from .obf import T1, T2
from .packet import Writer
from . import status as statuses       # the status engine (status.py): statuses, removals, i-frames, the execution

C2S_COMBAT_MODE = 0x5132
S2C_COMBAT_MODE = 0x5133
C2S_ENGAGE = 0x5058
S2C_ENGAGE = 0x5059
C2S_ABILITY_EXECUTE = 0x5066   # AbilityProcessor::ExecuteAbility (builder 0x1404faf10), one per hit of a cast
S2C_ABILITY_EXECUTE = 0x5067   # 0x140d1a550: u16 serial, flag, u16 caster, target list (hate / unit effects)
C2S_CAST_DONE = 0x506a         # u16 cast serial (builder 0x1404fb5b0, sent by the cast result handlers)
S2C_CAST_DONE = 0x506b         # 0x140d1aae0: i16 result, u16, u16 serial -> releases the cast record
C2S_ENGAGE_CLEAR = 0x506d      # u16 troop uid (0x140541080, the troop's engage list emptied)
S2C_ENGAGE_CLEAR = 0x506e      # 0x140d18630: same u16 -> troop reset
C2S_USE_ABILITY = 0x5117   # AbilityFacade::UseAbilityLeaderToPos (builder 0x1404fa650): the hero's combo/skill use
S2C_USE_ABILITY = 0x5118   # 0x140d19720: the confirmation; until it arrives the ability stays busy in troop+0x1080
C2S_HIT = 0x5053
S2C_AGGRO = 0x50b4            # 0x140d1bc60: u8 records, each u16 troop, u8 count, count * u16 target
C2S_HERO_HIT = 0x504f          # hero variant (builder 0x140545210, UnitHero::DoHitUnit): 14-byte header, same target list
S2C_UNIT_LIVE = 0x505b
HIT_HEADER = {C2S_HIT: 15, C2S_HERO_HIT: 14}
LEADER = -1                    # the leader's unit index in hit reports (0x5053 / 0x504f: unit index + 3 = 2)
S2C_DAMAGE_NUMBERS = 0x507b    # numbers over enemy units (0x140c54a40, engage mode): u8, u16 n, n x (u16 troop, u16 m,
                               # m x (u16 unit, u8, u8 flags, i32 damage)); entries with damage > 0 show
S2C_HERO_DAMAGE = 0x507d       # the number over the controlled hero (0x140c61890): i32 damage, u16 troop, u8 flags, u8
# The damage words: flag bits of 0x507b's record +3 and 0x507d's +6 (the one bit order in both readers). 0x507d
# (0x140c54aa0): bit 0 -> TextNumMgr type 4, bit 1 -> 2, bit 2 -> 1, bit 3 -> 0, none -> 3, damage < 0 -> 10. 0x507b:
# the reader 0x140c61610 queues a record when damage > 0 or bit 3, its bits at +0x18..+0x1b; the queue's consumer
# 0x140c63760 picks the same order + 5 (bit 0 -> 9, 1 -> 7, 2 -> 6, 3 -> 5, none -> 8; damage < 0 -> 10). DAMAGE_TYPE
# (re/ui/.../TextNumMgr.as:8) = [0 @회피, 1 @방어, 2 @빗맞음, 3 "", 4 @치명타, 5..9 the same over units, 12 @무적]; English
# "Evasion", "Defence", "Miss", "Critical" (textflashui_eng). The tape shows the words over enemies (white) and over the
# hero (red): Critical 185 reads, Miss 94, Defence 8 (playthrough CATALOGUE; captures/video OCR, 2026-09-30).
FLAG_CRITICAL, FLAG_MISS, FLAG_GUARD, FLAG_DODGE = 1, 2, 4, 8
NUMBERS_RANGE = 6000           # ours: how near the hero another troop's hit shows its number. 0x507b's consumer
                               # (0x140c63760) keeps the 50 nearest records and draws each where its unit projects,
                               # however far, so a multiplayer server's sight range must have bounded them (not shipped,
                               # so the figure is ours: game.WAKE_RANGE's). The crash site, 2026-11-05 08:18.
S2C_DAMAGE_TALLY = 0x507c      # UiInGame::PlayTroopDamage (0x140d1c930): u16 n, n x (split HP value damage, u16 victim,
                               # u16 attacker): the tactical view's troop-icon tally (pushes_battle.md; BATTLE B15)
C2S_AREA_DAMAGE = 0x505a       # EventDamageRange / RangeDirect / Charge (builder 0x1405423d0): coded u16 source troop,
                               # u16 n, n x (coded u16 target troop, u8 (int)(ratio x 127) x 2 + flag); no reply, the
                               # result is 0x505d / 0x505b (requests/battle.md; BATTLE B12)


def dec_uid(b):
    """Troop uid as the client writes it in hit reports: bytes (T2[hi], T1[lo])."""
    return (T1[b[0]] << 8) | T2[b[1]]


def parse_hit(body, header):
    """-> (attacker unit id, [(troop uid, [unit index, ...]), ...])."""
    attacker, targets, _ = parse_hit_props(body, header)
    return attacker, targets


def parse_hit_props(body, header):
    """-> (attacker, targets, [smart prop id]): 0x5053 carries u16 k + k * coded u32 prop ids after the target list
    (0x14054f600); 0x504f carries none (the list is then absent)."""
    attacker, targets, _, props = parse_hit_kinds(body, header)
    return attacker, targets, props


def parse_hit_kinds(body, header):
    """-> (attacker, targets, kinds, [smart prop id]): kinds[k] the client's hit kind (hit_kind) of each unit of
    targets[k]."""
    attacker = struct.unpack_from("<H", body, 0)[0]
    i = header
    n = struct.unpack_from("<H", body, i)[0]
    i += 2
    targets, kinds = [], []
    for _ in range(n):
        uid = dec_uid(body[i:i + 2])
        m = struct.unpack_from("<H", body, i + 2)[0]
        i += 4
        units, ks = [], []
        for _ in range(m):
            r = body[i:i + 6]
            if len(r) < 6:
                raise IndexError("hit record past the end")
            units.append((r[4] | ((r[5] & 1) << 8)) - 3)
            ks.append(hit_kind(r))
            i += 6
        targets.append((uid, units))
        kinds.append(ks)
    props = []
    if len(body) >= i + 2:
        k = struct.unpack_from("<H", body, i)[0]
        props = [obf.dec_u32(body[i + 2 + 4 * j:i + 6 + 4 * j]) for j in range(k) if len(body) >= i + 6 + 4 * j]
    return attacker, targets, kinds, props


def hit_source(body, proto):
    """(attacker troop, attacker unit, E_ActionEnum) of a hit report. 0x5053's header (builder 0x140544710,
    re/hit.c:136-170; all 10,115 captured bodies decode so, BATTLE-WIRING finding 1): +8 coded u16 troop, +0xa u16
    (((flags & 3) + unit * 4) << 5) | 29 -> unit = >> 7, +0xd u16 the action (72 / 73 ATTACK_NORMAL_COMMON_1 / 2).
    0x504f: a swing that struck two or more units (a single-unit one comes as 0x5056 in a solo room): +0 u16 the
    E_ActionEnum (72 / 73 / 69 / 70 ...; 0xffff on the hero's, which his 0x5066 repeats), +2 u16 attack id, +5 bit 7
    the troop's leader struck, +12 coded u16 the attacker troop (`10c3` = our hero, troop 0) (planning/client/
    combat.md: census of 161 traces; the old reading "+0 the unit" was wrong). Live 2026-09-27 23:56 in Grey Fog, idle
    hero: 535 0x504f from troops 21002, 30002, 13000 ... (the enemy, staging and ally leaders), none from 0. The
    returned unit is LEADER for a leader's swing, else None. 0x5053's unit field is signed: a leader's blow is unit -1
    ((flags & 3) - 4) << 5 | 29, read unsigned it was 511 and struck with the troop's unit record (census E4: 4 live)."""
    if proto != C2S_HIT:
        action = struct.unpack_from("<H", body, 0)[0]
        return dec_uid(body[12:14]), LEADER if body[5] & 0x80 else None, None if action == 0xffff else action
    return dec_uid(body[8:10]), struct.unpack_from("<h", body, 0xa)[0] >> 7, struct.unpack_from("<H", body, 0xd)[0]


def reaction_copy(body, proto):
    """A 0x504f whose action (+0) is 0xffff: ExecuteSkill's copy of a cast's hit reaction, its damage in the 0x5066
    (planning/client/combat.md: 1,150 of 1,182 live hero copies had their 0x5066 within 50 ms; no NP record carries
    0xffff). 0x5056's copies are the same field at +3 (on_hit_sync)."""
    return proto == C2S_HERO_HIT and struct.unpack_from("<H", body, 0)[0] == 0xffff


class Battle:
    """Hp of the troops in one battle session. Troops with a leader (the hero) track one hp; NP troops track units,
    and those with an NP leader (zone NPLeaderID: Thompson, Glen, the kobold commanders) his hp too: hits on unit
    index LEADER, and every hit once the units are down, land on him; the troop falls when units and leader are all
    down. Each troop keeps its combatant record ("c", combatant_hero / combatant_np; "leader_c" combatant_leader),
    what resolve reads."""

    def __init__(self):
        self.troops = {}

    def add_hero(self, uid, hp, c=None):
        self.troops[uid] = {"hero": True, "hp": hp, "max": hp, "combat": False, "c": c}

    def add_np(self, uid, unit_hp, units, c=None, leader_hp=0, leader_c=None, leader_floor=0):
        self.troops[uid] = {"hero": False, "units": [unit_hp] * units, "unit_max": unit_hp,
                            "max": unit_hp * units + leader_hp, "c": c}
        if leader_hp:
            self.troops[uid].update(leader=leader_hp, leader_max=leader_hp, leader_c=leader_c or c,
                                    leader_floor=leader_floor)
        lead = leader_c if leader_hp else None          # the vitality: the commander's own (npleadertable
        for rec, unit in ((lead, LEADER), (c, 0)):      # STAMINA_MAX, his unit -1), else the troop's (the troll
            top = _f((rec or {}).get("stamina_max"))    # 134080's 3274, unit 0) (census I5)
            if top > 0:
                self.troops[uid]["vit"] = {"cur": top, "max": top, "unit": unit, "rec": rec}
                break

    @staticmethod
    def total(t):
        """A troop's whole hp: the hero's, or its units' plus its leader's."""
        return t["hp"] if t["hero"] else sum(t["units"]) + t.get("leader", 0)

    def hit(self, uid, unit_indexes, amounts, floor=0):
        """Apply hits, amounts[k] on unit_indexes[k]; returns (troop hp, leader hp or None, [dead unit indexes]) or
        None for unknown troops. A hit on a dead or unknown unit lands on a random living one (ours). floor: the hp no
        living unit, leader or hero drops below (1 under an IMMORTAL status, held_functions)."""
        t = self.troops.get(uid)
        if t is None:
            return None
        if t["hero"]:                                   # "floor": the hp a hero cannot drop below (game.UNDYING_MISSIONS)
            low = max(t.get("floor", 0), floor if t["hp"] > 0 else 0)
            t["hp"] = max(min(low, t["hp"]), t["hp"] - sum(amounts))
            return t["hp"], t["hp"], []
        dead = []
        units = t["units"]
        for idx, amount in zip(unit_indexes, amounts):
            alive = [i for i, hp in enumerate(units) if hp > 0]
            if t.get("leader", 0) > 0 and (idx == LEADER or not alive):
                if amount > 0:                          # "leader_floor": an ally leader who cannot fall (UNDYING)
                    t["leader"] = max(max(t.get("leader_floor", 0), floor), t["leader"] - amount)
                continue
            if not (0 <= idx < len(units)) or units[idx] <= 0:
                if not alive:
                    break
                idx = random.choice(alive)
            if amount <= 0:
                continue
            units[idx] = max(min(floor, units[idx]), units[idx] - amount)
            if units[idx] == 0:
                dead.append(idx)
        return sum(units), t.get("leader"), dead

    def heal(self, uid, unit_indexes, amount, revive=0.0):
        """Raise the listed units (the hero: his hp) by amount, capped at their max; with revive > 0 every dead unit
        of the troop comes back with min(amount, revive x unit max) (abilitytypeinfo %Heal Revival, MaxHealUnitHp; the
        cap is ours). Returns (troop hp, leader hp or None, [revived unit indexes]) or None (unknown, or a fallen
        hero: he comes back by the revive buttons only)."""
        t = self.troops.get(uid)
        if t is None or (t["hero"] and (t.get("down") or t["hp"] <= 0)):
            return None
        if t["hero"]:
            t["hp"] = min(t.get("max", t["hp"]), t["hp"] + amount)
            return t["hp"], t["hp"], []
        units, top = t["units"], t.get("unit_max") or max(t["units"] or [1])
        for idx in set(unit_indexes):
            if 0 <= idx < len(units) and units[idx] > 0:
                units[idx] = min(top, units[idx] + amount)
            elif idx == LEADER and t.get("leader", 0) > 0:
                t["leader"] = min(t["leader_max"], t["leader"] + amount)
        revived = [i for i, hp in enumerate(units) if hp <= 0] if revive > 0 else []
        for i in revived:
            units[i] = max(1, min(amount, int(top * revive)))
        return sum(units), t.get("leader"), revived


# Damage: the resolver (BATTLE-WIRING B11, B53, B60, B12, B15; owner Q6 2026-09-27: §3 candidate A, per unit hit)
#   dmg = max(1, round(ATK x PR x AR x BR x (1 - D / (D + 500 x Lv_att)) x CRIT x V))
# Every input is a table's [T]; the formula, the type -> defence mapping, crit, the spread and these constants are ours.
DEF_K_PER_LEVEL = 500          # ours (Q6): defence D costs D / (D + 500 x attacker level); fits W71 (Thompson "deals
                               # 25-50": 24.9-45.9) and W1079 (the cold zone's "about 20 %" resistance at level 40)
DAMAGE_SPREAD = 0.1            # ours: V = uniform(0.9, 1.1)
HERO_SCALE = 1.0               # ours: the hero's damage x this, until one number from the owner's footage pins it
INSTANT_KILL = 9999999         # abilitycastinfo AttributeValue at or above this (110 + 37 rows) = the target's hp [T]
KILL_AMOUNT = 1 << 30          # what resolve returns for such a hit: more than any hp (Battle.hit floors at 0)
GUARD_GROUP = 10               # statuseffectinfo %Group COMMON_GUARD: 341 (Glen's guard 62), 3040, 6040, 7200 ... [T]
PHYSICAL, MAGICAL = "PHYSICAL", "MAGICAL"
ELEMENTS = ("FIRE", "ICE", "LIGHTNING", "NATURE", "HOLY", "DARK")
# E_SynastryAttackType -> the magical defence it meets (ours: FIREBLAST is fire); every other type is physical
MAGICAL_TYPES = {"FIRE": "FIRE", "ICE": "ICE", "LIGHTNING": "LIGHTNING", "NATURE": "NATURE", "HOLY": "HOLY",
                 "DARK": "DARK", "FIREBLAST": "FIRE"}
# physical types that meet DEFENCE_PHYSICAL_RANGE (ours, from the names and the troops that use them as their main
# attack: RANGE archers, RANGEDENSE axe throwers, MUSKET musketeers, BLAST mortars, SIEGE ballistae); the rest meet
# DEFENCE_PHYSICAL_ENGAGE (NP) / _CLOSE (hero)
RANGED_TYPES = frozenset(("RANGE", "RANGEDENSE", "MUSKET", "BLAST", "SIEGE"))
RANGED_SLOTS = ("RANGEATTACK", "SUBATTACK", "TROOP_ATTACK")   # %Combat slots that use a ranged troop's main attack
HERO_BRANCH = ("GUNSLINGER_HERO", "RANGER_HERO", "Druid_HERO", "SPELLSWORD_HERO", "BERSERKER_HERO", "Helena_HERO")


def _f(v, default=0.0):
    try:
        return float(str(v).rstrip("%"))
    except (TypeError, ValueError):
        return default


@functools.cache
def _rows_by(table, section, key):
    from . import tables
    return {r[key]: r for r in tables.sections(table)[section]}


@functools.cache
def _action_names():
    """actioninfo %ActionAttr ActionEnum by row: the row index is the E_ActionEnum value (72 ATTACK_NORMAL_COMMON_1)."""
    from . import tables
    return [r["ActionEnum"] for r in tables.sections("actioninfo")["ActionAttr"]]


def action_name(action):
    names = _action_names()
    return names[action] if action is not None and 0 <= action < len(names) else None


@functools.cache
def _improvements():
    """{ability: {level: row}} of abilitycastinfo %Improvement, SpotFilter COMMON."""
    from . import tables
    out = {}
    for r in tables.sections("abilitycastinfo")["Improvement"]:
        if r.get("SpotFilter") == "COMMON" and r["AbilityId"].isdigit():
            out.setdefault(int(r["AbilityId"]), {}).setdefault(r.get("Level"), r)
    return out


def improvement(ability, level=1):
    """The %Improvement row of an ability at a level (else its first row), or None."""
    rows = _improvements().get(ability) or {}
    return rows.get(str(level)) or next(iter(rows.values()), None)


@functools.cache
def _functions():
    """{(ability, level): [abilitytypeinfo %Function rows]}."""
    from . import tables
    out = {}
    for r in tables.sections("abilitytypeinfo")["Function"]:
        if r["AbilityId"].isdigit():
            out.setdefault((int(r["AbilityId"]), r.get("Level")), []).append(r)
    return out


@functools.cache
def invincible_statuses():
    """Statuses whose holder takes no damage: statuseffectinfo %Function TROOP_INVINCIBLE_DPS (272 rows; 6321 the
    escape / get-up status of evade 14 and 94) and %Forbidden Invincibility True (41) [T]; the client runs neither
    (empty case of _ProcessFuncForTroop 0x140ca3570, BATTLE B47)."""
    from . import tables
    sec = tables.sections("statuseffectinfo")
    ids = {r["Id"] for r in sec["Function"] if r.get("FunctionType") == "TROOP_INVINCIBLE_DPS"}
    ids |= {r["Id"] for r in sec["Forbidden"] if r.get("Invincibility") == "True"}
    return frozenset(int(i) for i in ids if i.isdigit())


@functools.cache
def _status_groups():
    """{status: {group ids}} from statuseffectinfo %Basic Group_1..3."""
    from . import tables
    return {int(r["Id"]): {int(r[g]) for g in ("Group_1", "Group_2", "Group_3") if str(r.get(g, "")).isdigit()}
            for r in tables.sections("statuseffectinfo")["Basic"] if r["Id"].isdigit()}


def held_statuses(s, uid, now=None):
    """The status ids troop uid holds (held_levels)."""
    return set(held_levels(s, uid, now))


class Level(int):
    """A held status's level that carries its stack count (census H5: statuseffectinfo %Basic Count, status.apply);
    status_bonus multiplies the status's traits by it, dot_hit its ticks."""
    def __new__(cls, level, stacks=1):
        obj = super().__new__(cls, level)
        obj.stacks = max(1, int(stacks or 1))
        return obj


def held_levels(s, uid, now=None):
    """{status: level} troop uid holds, from the live-status bookkeeping s.data["statuses"][uid] = {status: record}
    (BATTLE-WIRING B42, HERO-CONTROLS-WIRING K1: a dict record with "level" and "until", or (level, until, caster));
    empty until that bookkeeping fills it. Each level is a Level with the record's stack count."""
    now = time.monotonic() if now is None else now
    out = {}
    for sid, rec in ((s.data.get("statuses") or {}).get(uid) or {}).items():
        until = rec.get("until") if isinstance(rec, dict) else rec[1] if isinstance(rec, (tuple, list)) and \
            len(rec) > 1 else None
        if until is None or until > now:
            level = rec.get("level") if isinstance(rec, dict) else rec[0] if isinstance(rec, (tuple, list)) else 1
            out[int(sid)] = Level(int(level or 1), rec.get("stacks", 1) if isinstance(rec, dict) else 1)
    return out


LEVEL_FUNCTIONS = {"ADD_TARGET_LEVEL": 1, "ADD_CASTER_LEVEL": 1, "SUBTRACT_TARGET_LEVEL": -1,
                   "SUBTRACT_CASTER_LEVEL": -1}         # Traitvalue x the holder's level (ours [I]: no client code reads
                                                        # them; 3337 "Critical Rate equivalent to Lv x @stv@"; a passive
                                                        # is its holder's own, so caster = target; the KR community's
                                                        # "knockdown passive adds level x 100 defence")
ELEMENT_DEFENCES = tuple("DEFENCE_MAGICAL_" + e for e in ELEMENTS)
# a trait name that stands for several stats (hero.GROUPS, the stat enum's M_* 104 / 105; DEFENCE_PHYSICAL is NP naming)
TRAIT_GROUPS = {"M_CRITICAL_PROB": ("CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL"),
                "M_CRITICAL": ("CRITICAL_PHYSICAL", "CRITICAL_MAGICAL"),
                "M_DEFENCE_PHYSICAL": ("DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE"),
                "DEFENCE_PHYSICAL": ("DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE"),
                "M_DEFENCE_MAGICAL": ELEMENT_DEFENCES, "DEFENCE_MAGICAL": ELEMENT_DEFENCES,
                "M_PENETRATE": ("PHYSICAL_PENETRATE", "MAGICAL_PENETRATE")}
SPECIES = ("MANKIND", "DEMONIC", "ORCISH", "ELVEN", "GIANT")     # nptrooptype / npleadertype / trooptype SpeciesId
SKILL_RATES = tuple("ABILITY_ADD_DAMAGE_RATE_%02d" % n for n in range(1, 11))   # a skill group's damage rate (A16)
RACE_RATES = tuple(f"{r}_{k}_RATE" for r in SPECIES for k in ("ATTACK", "DEFENCE")) + ("HERO_DEFENCE_RATE",)
# Stats kept per mille whose trait percent (Traitvalue_1) is percentage points, x 10 per mille, not a share of the stat
# (ours [I], from the data's own words and the tape): the race rates' flat 80 reads "+8 %" (1500100 "@stv/10@%") and
# their percent 12 "+12 %" (850110 "Increases damage on the Monster type by +@stv@"); Speed Reload 57-59's
# CRITICALPROB_PHYSICAL percent 2 / 3 / 5 ("Critical Rate +@stv0@") would be a tenth of a per mille of a hero's 50 as a
# share; the Berserker's Burning Anger 6200 (M_CRITICAL_PROB percent 20, "Critical Rate +@stv@", on him in the Madness
# stance from passive 643) as +200 gives the tape's crit rate (part 2 Grey Rock: 55 yellow "Critical" of 134 non-miss
# hero numbers, 41 %; the kit alone, CRITICALPROB 50, 5 %)
POINT_STATS = frozenset(("CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL", "CRITICALPROB_RESIST", "DAMAGE_ABSORB_RATE")
                        + RACE_RATES)
# every trait the resolver reads from the held statuses itself (status_bonus); a held status's traits on these stay out
# of a record's row (status.status_traits with live False), so none counts twice
RESOLVER_TRAITS = frozenset(("ATTACK_PHYSICAL", "ATTACK_MAGICAL", "ACCURACY", "MISS", "GUARD_REDUCE",
                             "CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL", "CRITICAL_PHYSICAL", "CRITICAL_MAGICAL",
                             "CRITICALPROB_RESIST", "CRITICAL_REDUCE", "PHYSICAL_PENETRATE", "MAGICAL_PENETRATE",
                             "DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE", "DAMAGE_ABSORB", "DAMAGE_ABSORB_RATE")
                            + ELEMENT_DEFENCES + RACE_RATES + tuple(TRAIT_GROUPS))


def point_stat(name):
    """Whether a trait name's percent counts as points (POINT_STATS; a group name when its stats are)."""
    return name in POINT_STATS or any(m in POINT_STATS for m in TRAIT_GROUPS.get(name, ()))


@functools.cache
def _trait_names(stat):
    """The TraitType names that add to a stat: itself and the group names standing for it (TRAIT_GROUPS)."""
    return frozenset((stat,) + tuple(g for g, members in TRAIT_GROUPS.items() if stat in members))


@functools.cache
def _traits():
    """{(status, level): [(TraitTarget, TraitType, FunctionType, Traitvalue_1, Traitvalue_2)]} of statuseffectinfo
    %Improvement: the ADD / SUBTRACT traits and the level ones (LEVEL_FUNCTIONS); ADD_CASTER / SUBTRACT_CASTER (a share
    of the caster's own stat, 30-40 rows each) are not built."""
    from . import tables
    out = {}
    for r in tables.sections("statuseffectinfo")["Improvement"]:
        rows = out.setdefault((r["Id"], r.get("Level")), [])
        for i in ("01", "02"):
            if r.get(f"FunctionType{i}") in ("ADD", "SUBTRACT") or r.get(f"FunctionType{i}") in LEVEL_FUNCTIONS:
                rows.append((r.get(f"TraitTarget{i}"), r.get(f"TraitType{i}"), r[f"FunctionType{i}"],
                             _f(r.get(f"Traitvalue{i}1")), _f(r.get(f"Traitvalue{i}2"))))
    return out


def status_bonus(held, stat, leader=False, level=None):
    """(percent, flat) the held statuses ({status: level}) add to one stat of a holder: each ADD (SUBTRACT: minus)
    trait of that TraitType (or a group name standing for it, TRAIT_GROUPS: M_CRITICAL_PROB for CRITICALPROB_PHYSICAL)
    whose TraitTarget is ALL, LEADER for the hero or an NP leader, TROOP for a troop's units; Traitvalue_1 is a percent
    of the stat, Traitvalue_2 a flat amount; on a POINT_STATS stat the percent is points (x 10 per mille, flat). With
    the holder's level, the level functions too (LEVEL_FUNCTIONS: the values x the level). [R] the client's own trait
    code (0x1407bc0c0: TraitTarget 3 every unit, 1 the leader, 2 the others; FunctionType 1 ADD +, 2 SUBTRACT -) calls
    0x140a04c90(unit, type, flat = Traitvalue_2, rate = Traitvalue_1 x 0.01), which adds flat + base x rate. The client
    runs only the speed traits so; the others are the server's (it computes the damage)."""
    pct = flat = 0.0
    traits = _traits()
    names, points = _trait_names(stat), stat in POINT_STATS
    for status, lv in held.items():
        for target, kind, fn, p, v in traits.get((str(status), str(lv))) or traits.get((str(status), "1")) or ():
            if kind not in names or target not in ("ALL", "LEADER" if leader else "TROOP"):
                continue
            if fn in LEVEL_FUNCTIONS:
                if not level:
                    continue
                sign, times = LEVEL_FUNCTIONS[fn], level
            else:
                sign, times = (-1 if fn == "SUBTRACT" else 1), 1
            times *= getattr(lv, "stacks", 1)               # a stacked status counts once a stack (Level, H5)
            if points:
                flat += sign * (p * 10 + v) * times
            else:
                pct, flat = pct + sign * p * times, flat + sign * v * times
    return pct, flat


# Synastry (troop type x attack type), BATTLE-WIRING §3.1: a file shipped in Info.pkg under no name in any list (a content
# crawl found it; the client image names none of its sections, so only the server read it) [T]
SYNASTRY_ENTRY = 0x019e20b1c59402f5
SYNASTRY_SPOT = "COMMON"        # ours: the %Contents SpotFilter read (the 2 PVP rows are for PvP spots; none offline)
# The troop states (%StateMapper's columns, in order) and the client's report of them: 0x50b0's record flags & 0x7f is
# 0x14158e8a0(troop state +0x124, +0x451), which folds the TROOP_BEHAVIOR enum (its names: pointer table 0x1434a7120)
# into 0 READY / WANDER / DEAD ... (0-11), 1 MOVE / CHASE_MELEE / CHASE_RANGE ... (12-23), 2 MELEE* (25-38),
# 3 ATTACK_RANGE* (45-49), 4 ATTACK_CHARGE_TYPE1/2 / MOVE_CHARGE / CHASE_CHARGE (39-44) or +0x451 set, 5 the FRONTAL
# behaviours (7-9, 15, 20, 31-34: FRONTAL_READY, FRONTAL_MOVE, CHASE_FRONTAL, FRONTAL_PRESS / PUSH / DEFENSE),
# 7 FORCED_RETURN (24); 6 is never produced [R]. Class k = the k-th column: every class's behaviours are its column's
# name (the reading is ours; live 04:59 run: the archers 11004-11006 report 3, melee troops 2, the wyrms 1)
STATES = ("IDLE", "MOVE", "MELEE", "RANGE_ATTACK", "CHARGE", "FRONTAL", "ESCAPE", "RETURN")
IDLE, MELEE, CHARGE = STATES[0], STATES[2], STATES[4]


@functools.cache
def _synastry():
    """{section: rows} of the synastry file: %Contents (TypeName, SpotFilter, TroopRevision, one multiplier per
    E_SynastryAttackType column), %StateMapper (TypeName -> the %Contents row per troop state), %TypeName,
    %SynastryGroup, %SynastryGroupMatrix, %Line_Defence (cp949 text, the tables' '%Name' layout)."""
    import csv, io
    from . import tables
    p = tables.pkg.Pkg(tables.pkg.GAME / "Packages" / "Info.pkg")
    e = next(e for e in p.entries if e["hash"] == SYNASTRY_ENTRY)
    rows = list(csv.reader(io.StringIO(tables.pkg.text(p.read(e)))))
    out, i = {}, 0
    while i < len(rows):
        if rows[i] and rows[i][0].startswith("%"):
            name, cols, i = rows[i][0][1:], rows[i + 1], i + 3
            out[name] = []
            while i < len(rows) and not (rows[i] and rows[i][0].startswith("%")):
                if len(rows[i]) == len(cols):
                    out[name].append(dict(zip(cols, rows[i])))
                i += 1
        else:
            i += 1
    return out


@functools.cache
def _synastry_index():
    sec = _synastry()
    return ({r["TypeName"]: r for r in sec["Contents"] if r["SpotFilter"] == SYNASTRY_SPOT},
            {r["TypeName"]: r for r in sec["StateMapper"]},
            {r["Defender"]: r for r in sec["SynastryGroupMatrix"]},
            {r["Name"]: r["StringID"] for r in sec["SynastryGroup"]})


def synastry(att, tgt, kind, state=IDLE):
    """The synastry multiplier of an attack type on a target [T]: the %Contents row of the target's DEFENCE_TYPE
    (nptrooptype / npleadertype / herotable %System; every value is a TypeName there), through %StateMapper to the row of
    its state when the type has one (state_of: 162 human infantry MOVE 202 / MELEE 222, 230 spearmen FRONTAL 213, 205
    cavalry CHARGE 208), at the attack type's column (Tower's winged wyrm 278 takes RANGE x3; a spear square MOUNTED
    x0.1, a charging cavalry DENSE x6: the counter chart). Ours: a state row the file lacks (18 StateMapper targets, 246-256
    the spirits' moving / engaged rows ...) falls back to the type's own; the reading of TroopRevision (1 on 335 rows,
    0.5 LARGE / HUGE / COLOSSAL_WORM, 0 COLOSSAL_WORM_RAGE) as what a troop's units deal to that type (the hero and
    leaders are not a troop's units); x %SynastryGroupMatrix[target group][attacker group] when both have a
    SynastryGroup ("-" is 1: only 16 nptrooptypes carry one, colossal / bomber). Not built: %Line_Defence (the
    battle-line defence bonus needs formation positions) and OrganizeFactor (meaning unknown)."""
    if att is None or tgt is None or tgt.get("defence_type") in (None, "", "-"):
        return 1.0
    contents, states, matrix, names = _synastry_index()
    dtype = str(tgt["defence_type"])
    row = contents.get(states.get(dtype, {}).get(state)) or contents.get(dtype)
    if row is None:
        return 1.0
    mult = _f(row.get(kind), 1.0)
    if not att.get("hero") and not att.get("leader"):
        mult *= _f(row.get("TroopRevision"), 1.0)
    if tgt.get("group") and att.get("group"):
        mult *= _f(matrix.get(tgt["group"], {}).get(names.get(att["group"], "")), 1.0)
    return mult


def engaged(s, uid):
    """Whether troop uid is in melee (an engagement the client reported, on_engage, still open)."""
    return bool((s.data.get("engaged") or {}).get(uid))


def troop_states(s, flags):
    """Keep each troop's state class from a 0x50b0 ({uid: record flags}, game.sync_positions): the host reports every
    troop of a solo room (live: the hero, the allies and the enemies alike), a moving or fighting one every 1.5 s, one
    at rest once when it stops (room_troops §2.2)."""
    states = s.data.setdefault("troop_state", {})
    for uid, f in flags.items():
        states[uid] = STATES[f & 0x7f] if (f & 0x7f) < len(STATES) else IDLE


def state_of(s, uid):
    """Troop uid's synastry state: its last 0x50b0 class (troop_states), or its charge (on_area_damage); a troop never
    reported is IDLE. Ours: an engagement still open (on_engage) makes an IDLE troop MELEE, since a troop at rest is
    reported only once and the engagement report is the fresher news."""
    state = (s.data.get("troop_state") or {}).get(uid, IDLE)
    return MELEE if state == IDLE and engaged(s, uid) else state


def combatant(level, team=0, atk=(0.0, 0.0), matk=(0.0, 0.0), close=0.0, far=0.0, magical=None, pen=0.0, mpen=0.0,
              crit=(0.0, 0.0), mcrit=(0.0, 0.0), crit_resist=0.0, crit_reduce=0.0, guard=0.0, plain="LOOSE", acc=0.0,
              miss=0.0, evade_reduce=0.0, **more):
    """A combatant record, what resolve reads of an attacker or a target: level, team, attack ranges (physical,
    magical), defences (CLOSE / RANGE physical, one per element), penetrations, crit (probability, damage per mille)
    per side, crit resist / reduce, GUARD_REDUCE, ACCURACY / MISS and EVADE_REDUCE (the hit roll, miss_chance), the
    plain hit's attack type, the synastry DEFENCE_TYPE and
    SynastryGroup; the SpeciesId ("species": MANKIND / DEMONIC / ORCISH / ELVEN / GIANT, the race rates' key) and the
    race rates it carries itself ("rates": {RACE_RATES name: per mille}, the hero's gear sets); the hero's plain hit's
    hitsignalinfo CriticalRate ("plain_crit", per mille); NP troops add their %Combat power slots ("powers": {action
    name: (POWERRATE, slot)}),
    Default_PowerRate, the attack revisions, the main / engage attack types, the charge's power rate, BRANCH, RACE and
    their %Skill levels ("skills" the actives, "passives" the passives, each in column order); "leader" marks an NP
    leader's record."""
    rec = {"level": level, "team": team, "atk": {PHYSICAL: tuple(atk), MAGICAL: tuple(matk)},
           "def": dict({"CLOSE": close, "RANGE": far}, **(magical or dict.fromkeys(ELEMENTS, 0.0))),
           "pen": {PHYSICAL: pen, MAGICAL: mpen}, "crit": {PHYSICAL: tuple(crit), MAGICAL: tuple(mcrit)},
           "crit_resist": crit_resist, "crit_reduce": crit_reduce, "guard": guard, "acc": acc, "miss": miss,
           "evade_reduce": evade_reduce, "plain": plain, "main": plain,
           "engage": plain, "powers": {}, "default_pr": 1.0, "main_rev": 0.0, "engage_rev": 0.0, "charge_pr": 1.0,
           "branch": None, "race": None, "skills": {}, "passives": {}, "hero": False, "leader": False,
           "defence_type": None, "group": None, "species": None, "rates": {}, "plain_crit": 0.0}
    rec.update(more)
    return rec


@functools.cache
def _hero_plain(cls):
    """The attack type of the hero's plain hit: hitsignalinfo AttackAttribute of the class's ATTACK_NORMAL_COMMON_1
    (Glen HERO, Druid NATURE); HERO when the class has no row (Helena)."""
    from . import hero, tables
    code = hero.HERO_CODE[cls] if 0 <= cls < len(hero.HERO_CODE) else None
    return next((r["AttackAttribute"] for r in tables.sections("hitsignalinfo")["HitSignal"]
                 if r["CHARACTER_TYPE"] == code and r["ACTIONENUM"] == "ATTACK_NORMAL_COMMON_1"), "HERO")


CRIT_RATE_POINTS = 10           # hitsignalinfo CriticalRate is percentage points: 10 -> +100 per mille (ours [I])


@functools.cache
def _signal_crit():
    """{hero class code: [(DamageRate, CriticalRate)]} of hitsignalinfo (server-only: no "HitSignal" string in the
    client image, census A14): every class's ATTACK_NORMAL_COMMON_n and dash rows CriticalRate 10, FINISH_SKILL_5 0."""
    from . import tables
    out = {}
    for r in tables.sections("hitsignalinfo")["HitSignal"]:
        out.setdefault(r["CHARACTER_TYPE"], []).append((_f(r["DamageRate"]), _f(r["CriticalRate"]), r["ACTIONENUM"]))
    return out


@functools.cache
def basic_attack_crit(ability):
    """The crit bonus (per mille) of a hero's basic attack (census B4): the plain combo and dash abilities
    (heroskillbook KeyType SLOT_TYPE_4: Glen 164-167 / 32, the Berserker 803-806 / 623) take their class's hitsignalinfo
    CriticalRate x CRIT_RATE_POINTS, the row whose DamageRate is the ability's AttributeRate / 1000 (the rows restate
    it: 164-167 1000 / 1000 / 1250 / 1500 = 1 / 1 / 1.25 / 1.5), else the class's ATTACK_NORMAL_COMMON_1; any other
    ability 0. The reading of CriticalRate as points added to the crit chance is ours [I]; the tape's Berserker at Grey
    Rock crits 41 % of his non-miss hits (census B1), his kit and Burning Anger give 25 %, the combos' 10 more 35 %;
    [C] "the Gunslinger crits far more often than its stat suggests" (OFFICIAL-NOTES F144)."""
    from . import tables
    for r in tables.sections("heroskillbook")["AbilityBook"]:
        if r["AbilityId"] == str(ability) and r.get("KeyType") == "SLOT_TYPE_4":
            rows = _signal_crit().get(r["HeroID"], [])
            ar = _f((improvement(ability) or {}).get("AttributeRate")) / 1000
            row = next((x for x in rows if abs(x[0] - ar) < 1e-6 and x[2] != "FINISH_SKILL_5"), None) or next(
                (x for x in rows if x[2] == "ATTACK_NORMAL_COMMON_1"), None)
            return row[1] * CRIT_RATE_POINTS if row else 0.0
    return 0.0


def _species(value):
    return value if value in SPECIES else None


def combatant_hero(stats, level, cls=0, team=0):
    """The hero's record from hero.stats' named values (game.hero_combatant): attack = ATTACK_*_MIN..MAX (a uniform
    draw per hit), DEFENCE_PHYSICAL_CLOSE / _RANGE, DEFENCE_MAGICAL_*, the penetrations, crit, GUARD_REDUCE; the
    synastry DEFENCE_TYPE of herotable %System (0 HERO for every class); ACCURACY / MISS (the kit's gloves and shoes:
    the Berserker's Old Novice 132 / 88); GUARD_REDUCE and EVADE_REDUCE from the stats, else the class's herotable
    %Contents row (700 / 900 for every class)."""
    from . import hero
    g = lambda k: _f(stats.get(k))
    code = hero.HERO_CODE[cls] if 0 <= cls < len(hero.HERO_CODE) else None
    base = _rows_by("herotable", "Contents", "CHARACTER_TYPE").get(code, {})
    own = lambda k: g(k) if k in stats else _f(base.get(k))
    span = lambda side: (g(f"ATTACK_{side}_MIN") or g(f"ATTACK_{side}"), g(f"ATTACK_{side}_MAX") or g(f"ATTACK_{side}"))
    return combatant(level, team, atk=span(PHYSICAL), matk=span(MAGICAL), close=g("DEFENCE_PHYSICAL_CLOSE"),
                     far=g("DEFENCE_PHYSICAL_RANGE"), magical={e: g("DEFENCE_MAGICAL_" + e) for e in ELEMENTS},
                     pen=g("PHYSICAL_PENETRATE"), mpen=g("MAGICAL_PENETRATE"),
                     crit=(g("CRITICALPROB_PHYSICAL"), g("CRITICAL_PHYSICAL")),
                     mcrit=(g("CRITICALPROB_MAGICAL"), g("CRITICAL_MAGICAL")), crit_resist=g("CRITICALPROB_RESIST"),
                     crit_reduce=g("CRITICAL_REDUCE"), guard=own("GUARD_REDUCE"), acc=g("ACCURACY"), miss=g("MISS"),
                     evade_reduce=own("EVADE_REDUCE"), plain=_hero_plain(cls), hero=True,
                     branch=HERO_BRANCH[cls] if 0 <= cls < len(HERO_BRANCH) else None,
                     defence_type=_rows_by("herotable", "System", "CHARACTER_TYPE").get(code, {}).get("DEFENCE_TYPE"),
                     rates={k: g(k) for k in RACE_RATES + SKILL_RATES if g(k)},
                     plain_crit=next((c * CRIT_RATE_POINTS for _, c, a in _signal_crit().get(code, ())
                                      if a == "ATTACK_NORMAL_COMMON_1"), 0.0))


def _power_slots(*rows):
    """{E_ActionEnum name: (POWERRATE, slot)} of %Combat / %EncounterCombat rows: each slot column naming an action and
    its rate column (X_POWERRATE, SUBATTACK_x -> SUBATTACKPOWERRATE_x, SubAttackID -> SubAttackPowerRate); the first
    slot in column order wins an action two slots name (ours)."""
    out = {}
    for row in rows:
        for col, value in row.items():
            rate = (col + "_POWERRATE" if col + "_POWERRATE" in row else
                    "SUBATTACKPOWERRATE_" + col[10:] if col.startswith("SUBATTACK_") else
                    "SubAttackPowerRate" if col == "SubAttackID" else None)
            if rate in row and value not in ("", "-") and not value[:1].isdigit() and value not in out:
                out[value] = (_f(row[rate], 1.0), col)
    return out


def _skill_levels(row, kind="ACTIVESKILL", columns=16):
    """{ability: level} of an nptrooptable / npleadertable %Skill row in column order: its ACTIVESKILLnn / nnLV (16
    columns), or with kind "PASSIVESKILL" its 5 passive columns."""
    out = {}
    for k in range(1, columns + 1):
        a, lv = str(row.get("%s%02d" % (kind, k), "")), str(row.get("%s%02dLV" % (kind, k), ""))
        if a.isdigit() and int(a) > 0:
            out[int(a)] = int(lv) if lv.isdigit() and int(lv) > 0 else 1
    return out


def _on_hit_statuses(cmb):
    """{E_ActionEnum name: [(status, level, probability per mille)]} of a %Combat row's StatusEffectAddActionEnum_n /
    StatusEffectId_n / _Lv_n / _Probability_n (62 of 1,165 nptrooptypes; npleadertype and trooptype carry the columns
    too): the kobold sorcerer 134020's (type 1241) SKILL_SKILL_101 / 102 / 112 put its poison 102301 at 1000, the
    type 87 dash stuns (3), 40125 / 50001 burn (7) with every plain blow (census D10)."""
    out = {}
    for i in (1, 2, 3):
        action, sid = cmb.get(f"StatusEffectAddActionEnum_{i}"), str(cmb.get(f"StatusEffectId_{i}", "-"))
        if action not in (None, "", "-") and sid.isdigit() and int(sid) > 0:
            out.setdefault(action, []).append((int(sid), max(1, int(_f(cmb.get(f"StatusEffectLv_{i}"), 1))),
                                               _f(cmb.get(f"StatusEffectProbability_{i}"))))
    return out


def _np_record(row, system, combat_rows, skill_row, team, branch):
    g = lambda k, d=0.0: _f(row.get(k), d)
    cmb = combat_rows[0]
    charge = next((_f(cmb.get(c)) for c in ("ENGAGE_DASHATTACK_POWERRATE", "DASHATTACK1_POWERRATE")
                   if _f(cmb.get(c)) > 0), 1.0)
    return combatant(int(g("LEVEL_CURRENT", 1)), team, atk=(g("ATTACK_PHYSICAL"),) * 2, matk=(g("ATTACK_MAGICAL"),) * 2,
                     close=g("DEFENCE_PHYSICAL_ENGAGE", g("DEFENCE_PHYSICAL")),
                     far=g("DEFENCE_PHYSICAL_RANGE", g("DEFENCE_PHYSICAL")),
                     magical={e: g("DEFENCE_MAGICAL_" + e, g("DEFENCE_MAGICAL")) for e in ELEMENTS},
                     pen=g("PHYSICAL_PENETRATE"), mpen=g("MAGICAL_PENETRATE"),
                     crit=(g("CRITICALPROB_PHYSICAL"), g("CRITICAL_PHYSICAL")),
                     mcrit=(g("CRITICALPROB_MAGICAL"), g("CRITICAL_MAGICAL")), crit_resist=g("CRITICALPROB_RESIST"),
                     crit_reduce=g("CRITICAL_REDUCE"), guard=g("GUARD_REDUCE"), acc=g("ACCURACY"), miss=g("MISS"),
                     evade_reduce=g("EVADE_REDUCE"), plain=system.get("ENGAGEATTACK_TYPE") or "LOOSE",
                     main=system.get("MAINATTACK_TYPE") or system.get("ENGAGEATTACK_TYPE") or "LOOSE",
                     engage=system.get("ENGAGEATTACK_TYPE") or "LOOSE", powers=_power_slots(*combat_rows),
                     default_pr=_f(cmb.get("Default_PowerRate")) or 1.0, main_rev=g("MAIN_ATTACK_REVISION"),
                     engage_rev=g("ENGAGE_ATTACK_REVISION"), charge_pr=charge, branch=branch,
                     race=system.get("RACE"), skills=_skill_levels(skill_row),
                     passives=_skill_levels(skill_row, "PASSIVESKILL", 5),
                     defence_type=system.get("DEFENCE_TYPE"), species=_species(system.get("SpeciesId")),
                     rates={k: g(k) for k in RACE_RATES if g(k)}, onhit=_on_hit_statuses(cmb),
                     hp_rec=g("HP_RECOVERY"), stamina_max=g("STAMINA_MAX"), stamina_reduce=g("STAMINA_REDUCE"),
                     kdown=(int(g("KDOWN_STATUSEFFECT_ID")), max(1, int(g("KDOWN_STATUSEFFECT_LV", 1)))),
                     stamina_visible=system.get("STAMINA_VISIBLE") == "True",
                     group=system.get("SynastryGroup") if system.get("SynastryGroup") not in (None, "", "-") else None)


def combatant_np(row, team=1):
    """An NP troop's unit record: nptrooptable ATTACK_*, DEFENCE_PHYSICAL_ENGAGE / _RANGE, DEFENCE_MAGICAL_*, the
    penetrations, crit, LEVEL_CURRENT, the revisions (the room's difficulty row: game.difficulty_troop); its
    nptrooptype (NPTroopType) %System attack types, BRANCH and RACE, %Combat / %EncounterCombat power slots and
    Default_PowerRate (0 read as 1); its %Skill levels."""
    tid = row.get("NPTroopType")
    return _np_record(row, _rows_by("nptrooptype", "System", "NPTroopType").get(tid, {}),
                      (_rows_by("nptrooptype", "Combat", "NPTroopType").get(tid, {}),
                       _rows_by("nptrooptype", "EncounterCombat", "NPTroopType").get(tid, {})),
                      _rows_by("nptrooptable", "Skill", "NPTROOP_ID").get(row.get("NPTROOP_ID"), {}), team,
                      _rows_by("nptrooptype", "System", "NPTroopType").get(tid, {}).get("BRANCH"))


def combatant_leader(row, team=1):
    """An NP leader's record: npleadertable (the same stat columns) with its npleadertype (NPLeaderType) %System /
    %Combat (Thompson 162010: type 2007, Default_PowerRate 0.3); npleadertype has no BRANCH column (none)."""
    tid = row.get("NPLeaderType")
    return dict(_np_record(row, _rows_by("npleadertype", "System", "NPLeaderType").get(tid, {}),
                           (_rows_by("npleadertype", "Combat", "NPLeaderType").get(tid, {}),),
                           _rows_by("npleadertable", "Skill", "NPLEADER_ID").get(row.get("NPLEADER_ID"), {}), team,
                           None), leader=True)


def combatant_troop(row, team=0, skills=None, passives=None):
    """A player's deck troop's unit record (B4): troops.level_row (its trooptable row at its level, with its badges;
    in a room troops.room_row, its passives' stats too) read as an NP row is, with its trooptype (TroopType) %System
    attack types, DEFENCE_TYPE, SynastryGroup, BRANCH and RACE, and %Combat / %EncounterCombat power slots (trooptype
    has nptrooptype's columns); skills = {ability: level} of its equipped troop skills, passives those of its passive
    slots (troops.passives: status.immunity reads their IMMUNE traits), at the academy's levels. EVADE_REDUCE (not
    among troops.STATS) comes from the troop's trooptable row."""
    tid = row.get("TroopType")
    system = _rows_by("trooptype", "System", "TroopType").get(tid, {})
    if "EVADE_REDUCE" not in row and row.get("TROOP_ID") is not None:
        from . import troops
        row = dict(row, EVADE_REDUCE=(troops.troop_row(row["TROOP_ID"]) or {}).get("EVADE_REDUCE", 0))
    rec = _np_record(row, system, (_rows_by("trooptype", "Combat", "TroopType").get(tid, {}),
                                   _rows_by("trooptype", "EncounterCombat", "TroopType").get(tid, {})),
                     {}, team, system.get("BRANCH"))
    rec["skills"] = dict(skills or {})
    rec["passives"] = dict(passives or {})
    return rec


# a trait's stat name -> the stat row columns it adds to (troops.level_row / nptrooptable naming; the group names as
# hero.GROUPS reads them for the hero). Any other name adds to its own column.
TRAIT_COLUMNS = {"DEFENCE_PHYSICAL": ("DEFENCE_PHYSICAL", "DEFENCE_PHYSICAL_ENGAGE", "DEFENCE_PHYSICAL_RANGE"),
                 "M_DEFENCE_PHYSICAL": ("DEFENCE_PHYSICAL", "DEFENCE_PHYSICAL_ENGAGE", "DEFENCE_PHYSICAL_RANGE"),
                 "DEFENCE_PHYSICAL_CLOSE": ("DEFENCE_PHYSICAL_ENGAGE",),
                 "DEFENCE_MAGICAL": ("DEFENCE_MAGICAL",) + tuple("DEFENCE_MAGICAL_" + e for e in ELEMENTS),
                 "M_DEFENCE_MAGICAL": ("DEFENCE_MAGICAL",) + tuple("DEFENCE_MAGICAL_" + e for e in ELEMENTS),
                 "M_CRITICAL_PROB": ("CRITICALPROB_PHYSICAL", "CRITICALPROB_MAGICAL"),
                 "M_CRITICAL": ("CRITICAL_PHYSICAL", "CRITICAL_MAGICAL"),
                 "M_PENETRATE": ("PHYSICAL_PENETRATE", "MAGICAL_PENETRATE"),
                 "HP_MAX": ("HP_BASEUNIT",)}              # per unit, as a badge's HP_MAX (troops.BADGE_STATS)


def add_traits(row, traits):
    """A copy of a stat row (troops.level_row, an nptrooptable / npleadertable row) with traits [(stat, value,
    percent)] added (status.passive_traits: a troop's passives, T1.11): a number adds itself, a percent that share of
    the column before any trait, as the client's own trait code adds flat + base x rate (0x140a04c90) and
    status_bonus reads a status's Traitvalue_1 / _2; the close / ranged physical defences split from DEFENCE_PHYSICAL
    when the row has one only (the record reads DEFENCE_PHYSICAL_ENGAGE / _RANGE, _np_record)."""
    out = dict(row)
    for col in ("DEFENCE_PHYSICAL_ENGAGE", "DEFENCE_PHYSICAL_RANGE"):
        if str(out.get(col, "")) in ("", "-"):
            out[col] = out.get("DEFENCE_PHYSICAL", 0)
    base = {k: _f(v) for k, v in out.items()}
    for name, value, percent in traits:
        for col in TRAIT_COLUMNS.get(name, (name,)):
            out[col] = _f(out.get(col)) + (base.get(col, 0.0) * value / 100 if percent else value)
    return out


@functools.cache
def np_combatant(np_troop_id, team=1):
    """combatant_np of an nptrooptable id (cached: the tables do not change), or None without a row."""
    row = _rows_by("nptrooptable", "Contents", "NPTROOP_ID").get(str(np_troop_id))
    return combatant_np(row, team) if row else None


def ranged(kind):
    return kind in RANGED_TYPES or kind in MAGICAL_TYPES


def hit_attack(att, action=None):
    """The attack of a plain hit report, or None without an attacker record. The hero: his plain hit (AR 1,
    hitsignalinfo's attribute). An NP troop: the %Combat slot whose value is the hit's action (0x5053 +0xd,
    actioninfo %ActionAttr row = E_ActionEnum: finding 1), PR = Default_PowerRate x its POWERRATE (1 when no slot
    names it) x MAIN_ATTACK_REVISION for a RANGEATTACK* / SUBATTACK* / TROOP_ATTACK* slot of a troop whose main attack
    is ranged (then of MAINATTACK_TYPE), else x ENGAGE_ATTACK_REVISION (ENGAGEATTACK_TYPE); a revision <= 0 is 1."""
    if att is None:
        return None
    if att.get("hero"):
        return {"type": att["plain"], "pr": 1.0, "ar": 1.0, "crit_rate": att.get("plain_crit", 0.0)}
    name = action_name(action)
    pr, slot = att["powers"].get(name, (1.0, ""))
    far = slot.upper().startswith(RANGED_SLOTS) and ranged(att["main"])
    rev = att["main_rev"] if far else att["engage_rev"]
    return {"type": att["main"] if far else att["engage"], "pr": att["default_pr"] * pr * (rev if rev > 0 else 1.0),
            "ar": 1.0, "action": name}


def charge_attack(att):
    """A charge / area hit's attack (0x505a, B12): an NP troop's ENGAGE_DASHATTACK_POWERRATE (else DASHATTACK1's; ours)
    x Default_PowerRate with its engage type; the hero's plain hit."""
    if att is None or att.get("hero"):
        return hit_attack(att)
    rev = att["engage_rev"]
    return {"type": att["engage"], "pr": att["default_pr"] * att["charge_pr"] * (rev if rev > 0 else 1.0), "ar": 1.0}


@functools.cache
def _charge_rows():
    from . import tables
    return {(r["AbilityId"], r["Level"]): r for r in tables.sections("abilitytypeinfo")["Charge"]}


def charge_stage(ability, level, stage):
    """What a charged skill's stage changes (abilitytypeinfo %Charge: 39 hero skills, up to ChargeLevel stages a
    level): its own ProcessRate list, AttributeValue, AttributeOperation and status slots; None for a skill with no
    row or a cast released before its first stage (stage 0: the plain abilitycastinfo row). The stage is the count of
    0x5062 the cast sent (on_charge_step), capped at ChargeLevel. Its MaxTarget is the client's (it lists the targets).
    statuses: the stage's StatusEffect<n>, Level<n>, StatusEffectObject<n>, StatusEffectTimesType<n>, Probability<n> and
    their _2 columns, under the plain row's names: status.ability_statuses puts them in place of the plain row's slots,
    an empty one too (ours [I]: 266 of the 297 stages restate the plain row; the Rain of Arrows family rises, 956's 6413
    from level 1 to 3 and 5, and 1297's stage 1 has no 3391). Its ProcessStatusEffect<n> is not read: on every stage
    with a status it is the plain row's."""
    row = _charge_rows().get((str(ability), str(level))) or _charge_rows().get((str(ability), "1"))
    if row is None or stage < 1:
        return None
    n = min(int(stage), int(_f(row.get("ChargeLevel")) or 1))
    shares = [_f(x) for x in str(row.get(f"ProcessRate{n}", "")).split() if x.replace(".", "").isdigit()]
    value = row.get(f"AttributeValue{n}", "-")
    op = row.get(f"AttributeOperation{n}", "-")
    slots = {f"{column}{slot}": row.get(f"{column}{n}{tail}") for slot, tail in ((1, ""), (2, "_2"))
             for column in ("StatusEffect", "Level", "StatusEffectObject", "StatusEffectTimesType", "Probability")}
    return {"shares": shares, "value": None if value in ("", "-") else _f(value),
            "op": None if op in ("", "-", "NOOP") else op, "statuses": slots}


def ability_attack(att, ability, level=1, k=1, stage=0):
    """The k-th execute (0x5066) of a cast of `ability` at `level` by att: abilitycastinfo %Improvement AttributeRate /
    1000 x ProcessRate_k / 100 (ours: past the list the last one counts); when every ProcessRate x 10 restates
    AttributeRate (the basic combos 164-167: 1000 / "100 100") AttributeRate / 1000 alone. AttributeValue >=
    INSTANT_KILL kills; a smaller one adds that many (x the same share) before defence (ours: the cold zone's fixed
    2000 meets the defence term, §3). AttributeCircle is the attack type ("-": the caster's plain one); PR is 1 for
    the hero, Default_PowerRate for NP casters (ours); "op" SUBTRACT damages, ADD heals (B60), NOOP changes no hp;
    Add_Accuracy adds to the caster's ACCURACY in the hit roll (100000 on 224 rows: never misses) and Add_Panetrate
    to its penetration (100000 on 45: ignores defence). Without a row: the caster's plain hit."""
    row = improvement(ability, level) if ability is not None else None
    if att is None or row is None:
        return hit_attack(att)
    rate, value = _f(row.get("AttributeRate")), _f(row.get("AttributeValue"))
    shares = [_f(x) for x in str(row.get("ProcessRate", "")).split() if x.replace(".", "").isdigit()] or [100.0]
    op = row.get("AttributeOperation")
    charged = charge_stage(ability, level, stage)        # a charged skill past its first stage: that stage's own
    if charged:                                          # shares, value and operation (0x5062, on_charge_step)
        shares = charged["shares"] or shares
        value = value if charged["value"] is None else charged["value"]
        op = charged["op"] or op
    restated = rate > 0 and all(abs(x * 10 - rate) < 1e-6 for x in shares)
    share = 1.0 if restated else shares[min(k, len(shares)) - 1] / 100
    circle = row.get("AttributeCircle", "-")
    return {"type": att["plain"] if circle in ("", "-") else circle,
            "pr": 1.0 if att.get("hero") else att["default_pr"], "ar": rate / 1000 * share, "flat": 0.0 if value >= INSTANT_KILL else value * share,
            "kill": value >= INSTANT_KILL, "op": op, "ability": ability, "level": level,
            "add_prob": _f(row.get("Add_CriticalProb")), "add_dmg": _f(row.get("Add_CriticalDmg")),
            "add_acc": _f(row.get("Add_Accuracy")), "add_pen": _f(row.get("Add_Panetrate")),
            "crit_rate": basic_attack_crit(ability) if att.get("hero") else 0.0,
            "groups": [(row.get(f"Add_attributeType{i}"), _f(row.get(f"Add_attributeValue{i}")))
                       for i in (1, 2, 3) if row.get(f"Add_attributeType{i}") in SKILL_RATES]}


def _in_group(section, key, group, name):
    """Whether `name` (a branch or race) is marked "O" in the abilitytypeinfo %TroopBranch / %Race row named `group`
    (its StringId, else its id); "-" names no filter."""
    if group in ("", "-", None):
        return True
    row = (_rows_by("abilitytypeinfo", section, "StringId").get(group)
           or _rows_by("abilitytypeinfo", section, key).get(group))
    return bool(row and name and row.get(name) == "O")


def ability_modifiers(ability, level, tgt, held=(), hp_ratio=1.0, struck=1, stack2=0):
    """BR, the damage modifiers of an ability's abilitytypeinfo %Function rows at its level (else level 1) against a
    target (B53, the types the hero kits carry):
    - RACE_BRANCH_ADD_DAMGE: x ParamValue3 % when the target's BRANCH is marked in the %TroopBranch group ParamValue2
      names (and its RACE in the %Race row ParamValue1 names): 95 영웅용중형피해 100 %, 96 영웅용대형피해 200 % (finding 4).
      Reading the percent as a multiplier is the spec's (ours; B53).
    - STATUSEFFECT_ADD_DAMAGE: x (1 + ParamValue2 %) while the target holds status ParamValue1 (15: 86 -> +20 %).
    - STATUSEFFECTGROUP_ADD_DAMAGE: x (1 + ParamValue2 %) while it holds a status of group ParamValue1 (10 COMMON_GUARD
      -> +235 %).
    - HP_BACEUNIT_ADD_DAMAGE: x (1 + ParamValue1 %) while the unit's hp is below ParamValue3 % (151: +70 % under 30 %;
      the reading is the spec's [I]).
    - UNITCOUNT_ADD_DAMAGE (census A8; the bosses' 35020 / 35037 Pergos, 10620 / 10650 Behemoth): ParamValue1 the unit
      counts "1 2 3 4 5", ParamValue2 the adds per 100,000 ("0 -50000 -70000 ..." the Behemoth's explosion shared by
      the units it strikes, "100 25000 ..." the fireball growing): x (1 + the add of the highest count <= `struck`, the
      units the execute struck, / 100,000) [I].
    - STACK2_ADD_DAMAGE (A8; the Druid's spirit commands 1309 ["1", "100%", "True"], 1312-1322 "0%"): x (1 + the
      caster's Stack2 x ParamValue2) [I]."""
    fns = _functions()
    rows = fns.get((ability, str(level))) or fns.get((ability, "1")) or []
    br = 1.0
    for r in rows:
        kind, p = r["FunctionType"], [r.get(f"ParamValue{i}", "-") for i in range(1, 6)]
        if kind == "RACE_BRANCH_ADD_DAMGE":
            if tgt and _in_group("TroopBranch", "BranchId", p[1], tgt.get("branch")) and \
                    _in_group("Race", "RaceId", p[0], tgt.get("race")):
                br *= _f(p[2], 100.0) / 100
        elif kind == "STATUSEFFECT_ADD_DAMAGE":
            if p[0].isdigit() and int(p[0]) in held:
                br *= 1 + _f(p[1]) / 100
        elif kind == "STATUSEFFECTGROUP_ADD_DAMAGE":
            if p[0].isdigit() and any(int(p[0]) in _status_groups().get(st, ()) for st in held):
                br *= 1 + _f(p[1]) / 100
        elif kind == "HP_BACEUNIT_ADD_DAMAGE":
            if hp_ratio * 100 < _f(p[2]):
                br *= 1 + _f(p[0]) / 100
        elif kind == "UNITCOUNT_ADD_DAMAGE":
            steps = [(_f(n), _f(a)) for n, a in zip(str(p[0]).split(), str(p[1]).split())]
            add = next((a for n, a in sorted(steps, reverse=True) if n <= struck), 0.0)
            br *= max(0.0, 1 + add / 100000)
        elif kind == "STACK2_ADD_DAMAGE":
            br *= 1 + stack2 * _share(p[1])
    return br


def defence(tgt, kind):
    """The target's defence against an attack type: DEFENCE_MAGICAL_<element> for the magical types, else the
    physical defence against ranged (RANGED_TYPES) or close attacks."""
    if tgt is None:
        return 0.0
    element = MAGICAL_TYPES.get(kind)
    return tgt["def"].get(element or ("RANGE" if kind in RANGED_TYPES else "CLOSE"), 0.0)


def defence_stat(kind):
    """The stat name of the defence an attack type meets (defence): DEFENCE_MAGICAL_<element>,
    DEFENCE_PHYSICAL_RANGE or DEFENCE_PHYSICAL_CLOSE, as the statuses' traits name them."""
    element = MAGICAL_TYPES.get(kind)
    return "DEFENCE_MAGICAL_" + element if element else (
        "DEFENCE_PHYSICAL_RANGE" if kind in RANGED_TYPES else "DEFENCE_PHYSICAL_CLOSE")


def _stat(rec, name, key, held, value=None):
    """A record's stat (its `key`, or `value`) with its holder's statuses' traits on it (held {status: level}:
    status_bonus at the record's level, x (1 + percent / 100) + flat), e.g. MISS under the Berserker's Iron Body 6201
    (+400) or the escape 6321 (+3000), CRITICALPROB_PHYSICAL under his Burning Anger 6200 (+200 points)."""
    value = (rec or {}).get(key, 0.0) if value is None else value
    if held and rec is not None:
        pct, flat = status_bonus(held, name, rec.get("hero") or rec.get("leader"), max(1, rec.get("level") or 1))
        value = value * (1 + pct / 100) + flat
    return value


def race_factor(att, tgt, own=None, held=None):
    """The race rates' factor on a hit (census A15; stats 87-97): x (1 + the attacker's <target's SpeciesId>_ATTACK_RATE
    / 1000) x (1 - the target's <attacker's SpeciesId>_DEFENCE_RATE / 1000), and x (1 - the target's HERO_DEFENCE_RATE
    / 1000) when a hero strikes; each rate its record's own (the hero's gear sets: item_set 95 HERO_DEFENCE_RATE ...)
    plus its holder's statuses' (850110 "Increases damage on the Monster type by +12 %", 850120 "Reduces damage
    inflicted by the Monster type by 12 %"; the troops' 1500100 "Orc Hunter" flat 80 = "+8 %"). The species: nptrooptype
    / npleadertype / trooptype SpeciesId (MANKIND 180, DEMONIC 173, ORCISH 148, ELVEN 123, GIANT 50, NONE 491 of 1,165);
    a hero has none. The multiplication is ours [I]; the rates and whom they apply to are the data's words."""
    if att is None or tgt is None:
        return 1.0
    rate = lambda rec, name, h: _stat(rec, name, None, h, rec.get("rates", {}).get(name, 0.0))
    factor = 1.0
    if tgt.get("species"):
        factor *= max(0.0, 1 + rate(att, tgt["species"] + "_ATTACK_RATE", own) / 1000)
    if att.get("species"):
        factor *= max(0.0, 1 - rate(tgt, att["species"] + "_DEFENCE_RATE", held) / 1000)
    if att.get("hero"):
        factor *= max(0.0, 1 - rate(tgt, "HERO_DEFENCE_RATE", held) / 1000)
    return factor


def miss_chance(att, tgt, attack=None, own=None, held=None):
    """The chance a hit misses (glances): (the target's MISS - the attacker's ACCURACY - the ability's Add_Accuracy) /
    1000, within 0..1, each stat with its holder's statuses' traits (_stat). The rule is the server's (no GetTrait
    caller in the client reads 31 ACCURACY or 32 MISS: census D7) and the community's "1000 points = 100 %, hit vs
    evasion subtractive" (OFFICIAL-NOTES F144: vs 2,763 need 1,764 for 1 %, ~2,400 for ~75 %). Tape, 2026-09-30: 189 of
    the 192 "Miss" reads over the 18 parts are white (over enemies: the hero's hits, ACCURACY 132-265 in the class kits
    vs story foes' MISS 330-480 -> 5-35 %), 3 red (over the hero, one frame, part 5 f_00860: foes' ACCURACY 250-630 vs
    his MISS 88-321 -> none, unless a status raises it: Iron Body's +400 [I]); Grey Rock (part 2, 2 fps frames
    31:25-43:20): 23 Miss of 139 hero-sized hits (16.5 %; this formula: 23-25 % for the Berserker's 132-147 against
    the kobolds' 380; OCR drops words, so a rough agreement)."""
    if att is None or tgt is None:
        return 0.0
    acc = _stat(att, "ACCURACY", "acc", own) + (attack or {}).get("add_acc", 0.0)
    return max(0.0, min(1.0, (_stat(tgt, "MISS", "miss", held) - acc) / 1000))


def resolve(att, tgt, attack, held=(), hp_ratio=1.0, rng=None, state=IDLE, own=None, guard=None):
    """One unit hit's damage (resolve_hit without the flags)."""
    return resolve_hit(att, tgt, attack, held, hp_ratio, rng, state, own, guard)[0]


def resolve_hit(att, tgt, attack, held=(), hp_ratio=1.0, rng=None, state=IDLE, own=None, guard=None):
    """One unit hit: (damage, the damage-word flags FLAG_*) (BATTLE-WIRING §3 candidate A, owner Q6 2026-09-27; §3.1
    synastry): max(1, round(ATK x PR x AR x BR x (1 - D / (D + DEF_K_PER_LEVEL x Lv_att)) x S x HIT x CRIT x G x V)),
    where ATK is a draw from the attacker's physical or magical range (by the attack type) with its held statuses'
    traits on that stat (own = {status: level}: x (1 + percent / 100) + flat, status_bonus; + the ability's flat
    value), D the target's defence against that type minus the attacker's penetration and the ability's Add_Panetrate
    (floor 0), Lv_att the attacker's level (at least 1), S the synastry of the attack type on the target in its state
    (synastry), HIT the hit roll: with miss_chance the hit glances, x (1 - the target's EVADE_REDUCE / 1000) (900 on
    12,481 nptrooptable rows and every hero: a tenth) and FLAG_MISS, no crit roll (the tape: every "Miss" carries a
    tenth of its neighbours' numbers, 95 / 928, 145 / 1,457, 29 / 288, 50 / 493, 26 / 263, 133 / 1,299, 15 / 160, 16 /
    166, 12 / 125, 33 / 336 ...: a glancing hit, as @빗맞음 says, not a zero), CRIT x (1 + (CRITICAL_x +
    Add_CriticalDmg - CRITICAL_REDUCE) / 1000) with probability (CRITICALPROB_x + Add_CriticalProb -
    CRITICALPROB_RESIST) / 1000 (FLAG_CRITICAL), G x (1 - guard / 1000) when the hit is guarded (guard: the effective
    GUARD_REDUCE per mille, guard_reduce; None: not guarded) with FLAG_GUARD, V the spread; x HERO_SCALE for the hero.
    A target holding an invincible status takes 0 (B47's part in A); a synastry of 0 is immunity (walls against every
    type but SIEGE / BLAST): 0, not the floor's 1; an instant-kill ability takes the unit's hp (KILL_AMOUNT); no
    attacker record, no damage (a troop the server never spawned). held: the target's statuses ({status: level}, or
    their ids at level 1). Since the rules hunt (2026-10-01) every stat it reads carries its holder's statuses' traits
    (_stat: the defence, the penetration, crit chance and damage, CRITICALPROB_RESIST, CRITICAL_REDUCE), and the
    race rates (race_factor), a skill group's rate (skill_rate_factor) and the target's absorption (absorbed) join the
    product; a "dot" attack (a damage-over-time tick, a reflection) rolls neither the miss nor the crit; a "fixed" one
    (an ability's HP trait) is its amount."""
    if att is None or attack is None or att.get("harmless"):      # harmless: a force that fires for show (director.harmless)
        return 0, 0
    rng = rng or random
    levels = dict(held) if isinstance(held, dict) else dict.fromkeys(held, 1)
    held = set(levels)
    if held & invincible_statuses():
        return 0, 0
    if attack.get("kill"):
        return KILL_AMOUNT, 0
    if attack.get("fixed") is not None:                 # an ability's HP trait: a fixed amount, no roll (hp_traits)
        return max(0, round(attack["fixed"])), 0
    kind = attack.get("type") or att["plain"]
    side = MAGICAL if kind in MAGICAL_TYPES else PHYSICAL
    t, flags = tgt or {}, 0
    lo, hi = att["atk"][side]
    atk = rng.uniform(lo, hi) if hi > lo else lo
    if own:
        atk = max(0.0, _stat(att, "ATTACK_" + side, None, own, atk))
    base = atk * attack.get("pr", 1.0) * attack.get("ar", 1.0) + attack.get("flat", 0.0)
    if base <= 0:                   # an attack-0 troop (the designers' "attack x0" allies, 133010: DESIGNER-NOTES)
        return 0, 0                 # deals nothing: the floor of 1 below is for a real attack
    syn = synastry(att, tgt, kind, state)
    if syn <= 0:                      # immune (C5): the census's resolver run (2026-09-30) had the hero chip a New Hampton
        return 0, 0                 # wall (135200, DEFENCE_TYPE 92) for 1 a hit, 10,000 under the boost
    if attack.get("ability") is not None:
        base *= ability_modifiers(attack["ability"], attack.get("level", 1), tgt, held, hp_ratio,
                                  attack.get("struck", 1), attack.get("stack2", 0))
    base *= skill_rate_factor(att, attack, own)
    d = max(0.0, _stat(tgt, defence_stat(kind), None, levels, defence(tgt, kind))
            - _stat(att, side + "_PENETRATE", None, own, att["pen"][side]) - attack.get("add_pen", 0.0))
    dmg = base * (1 - d / (d + DEF_K_PER_LEVEL * max(1, att["level"]))) * syn * race_factor(att, tgt, own, levels)
    p = 0.0 if attack.get("dot") else miss_chance(att, tgt, attack, own, levels)
    if attack.get("dot"):
        pass                                            # a damage-over-time tick: no hit roll, no crit (start_dot)
    elif p > 0 and rng.random() < p:
        dmg *= max(0.0, 1 - t.get("evade_reduce", 0.0) / 1000)
        flags |= FLAG_MISS
    elif rng.random() < crit_chance(att, tgt, attack, side, own, levels):
        bonus = (_stat(att, "CRITICAL_" + side, None, own, att["crit"][side][1]) + attack.get("add_dmg", 0.0)
                 - _stat(tgt, "CRITICAL_REDUCE", "crit_reduce", levels))
        dmg *= 1 + max(0.0, bonus) / 1000
        flags |= FLAG_CRITICAL
    if guard is not None:
        dmg *= max(0.0, 1 - guard / 1000)
        flags |= FLAG_GUARD
    if att.get("hero"):
        dmg *= HERO_SCALE
    dmg *= rng.uniform(1 - DAMAGE_SPREAD, 1 + DAMAGE_SPREAD)
    return max(1, round(absorbed(tgt, dmg, levels))), flags


def skill_rate_factor(att, attack, own=None):
    """A skill group's damage rate (census A16): an ability's abilitycastinfo %Improvement Add_attributeType1-3 name its
    groups (ABILITY_ADD_DAMAGE_RATE_01..10, 746 rows, Add_attributeValue 1000), the caster's gear sets carry the rate
    (item_set: 11021's 3 pieces ABILITY_ADD_DAMAGE_RATE_03 / _07 +800, LEADER): x (1 + the caster's rate x the
    ability's value / 1000 / 1000), a sum over the groups. The per-mille readings (800 = +80 %, 1000 = the whole rate)
    are ours [I], as the race rates' and the crit damage's per mille."""
    groups = (attack or {}).get("groups") or ()
    if not groups or att is None:
        return 1.0
    return max(0.0, 1 + sum(_stat(att, name, None, own, att.get("rates", {}).get(name, 0.0)) * value / 1e6
                            for name, value in groups))


def crit_chance(att, tgt, attack=None, side=PHYSICAL, own=None, held=None):
    """The chance a hit that did not glance crits (census B1, B4): (the attacker's CRITICALPROB_x with its held
    statuses' traits (the percent as points: POINT_STATS; the Berserker's Burning Anger 6200 +200) + the ability's
    Add_CriticalProb + a basic attack's hitsignalinfo CriticalRate (basic_attack_crit: +100) - the target's
    CRITICALPROB_RESIST with its statuses') / 1000, within 0..1."""
    if att is None:
        return 0.0
    prob = (_stat(att, "CRITICALPROB_" + side, None, own, att["crit"][side][0]) + (attack or {}).get("add_prob", 0.0)
            + (attack or {}).get("crit_rate", 0.0) - _stat(tgt, "CRITICALPROB_RESIST", "crit_resist", held))
    return max(0.0, min(1.0, prob / 1000))


def absorbed(tgt, dmg, held=None):
    """A hit after the target's damage absorption (census A18; stats 101 / 102, statuses only: 54 rows, 703491 "Steely
    Stride" DAMAGE_ABSORB flat 500, 850840 "Reliable Supporter" 60 x the level, 812180 "Swift Ambush" 40 x the
    level): x (1 - DAMAGE_ABSORB_RATE / 1000), then - DAMAGE_ABSORB, not below 0 (the formula's floor of 1 follows).
    Reading ours [I]: "Increases Damage Absorption equivalent to target Lv x n" is an amount taken off each hit."""
    if not held or tgt is None:
        return dmg
    rate = _stat(tgt, "DAMAGE_ABSORB_RATE", None, held, 0.0)
    flat = _stat(tgt, "DAMAGE_ABSORB", None, held, 0.0)
    return max(0.0, dmg * max(0.0, 1 - rate / 1000) - max(0.0, flat))


GUARDED_KINDS = (1, 2, 3)       # the client's hit kinds (0x140a2ba40) that are a guard: 1 the target's guard stance
                                # (hero +0x10b1, UnitHero::EnterStance, from the front only) or its own guard roll
                                # (Unit::EvaluateGuard 0x140a161b0: rand % 1000 < PROBABILITY_GUARD), 2 that roll
                                # followed by its counter roll (< PROBABILITY_COUNTER; the NP unit plays 149
                                # DEFENSE_COUNTER, the counter blow comes as its own hit) or a counter armed by the
                                # motion signal ActionSignalHandlerCountAttack 0x140ad9fe0, 3 the target in 148
                                # DEFENSE_STANDING. 0 plain, 4-5 others take the full hit; 6 is a dodge (DODGE_KIND)
DODGE_KIND = 6                  # Unit::EvaluateDodge 0x140a162a0: rand % 1000 < the target's PROBABILITY_DODGE (stat 98,
                                # in no client table: only the server's stat block sets it, game.np_stat_block); the NP
                                # unit plays 59 COMBAT_CAUTION_MOVE_BACK_DASH half the time. No damage, the Dodge word
                                # (FLAG_DODGE: 0x507b queues a zero-damage record only with bit 3) (client digs 2026-10-01)


def hit_kind(record):
    """The client's hit kind in a 6-byte hit record (0x5053 / 0x504f / 0x5056): +5 bits 2-3 = kind & 3, bit 1 = kind
    bit 2 (builder 0x140544710; INVENTORY "Whether a blow staggers"). Captures 2026-09-28..30: hits on the hero 698
    kind 0, 1,137 kind 1 (guarding), 10 kind 4; on NP units 78,578 kind 0, 555 kind 4."""
    b = record[5]
    return ((b >> 2) & 3) | (((b >> 1) & 1) << 2)


@functools.cache
def _status_functions():
    """{(status, level): [statuseffectinfo %Function rows]}."""
    from . import tables
    out = {}
    for r in tables.sections("statuseffectinfo")["Function"]:
        out.setdefault((r["Id"], r.get("Level")), []).append(r)
    return out


def held_functions(s, uid, kind, now=None):
    """[(status, level, [ParamValue1..5])] of the statuseffectinfo %Function rows of type `kind` of the statuses troop
    uid holds (the held level's rows, else level 1's). The client runs none of the server-run functions (the empty
    cases of _ProcessFuncForTroop 0x140ca3570, BATTLE-WIRING B47)."""
    if uid is None:
        return []
    fns = _status_functions()
    out = []
    for sid, lv in held_levels(s, uid, now).items():
        for r in fns.get((str(sid), str(lv))) or fns.get((str(sid), "1")) or ():
            if r["FunctionType"] == kind:
                out.append((sid, lv, [r.get(f"ParamValue{i}", "-") for i in range(1, 6)]))
    return out


def _share(v, whole=1.0):
    """A %Function parameter: "30%" -> 0.3 x whole, a number itself, "-" 0."""
    v = str(v).strip()
    return _f(v[:-1]) / 100 * whole if v.endswith("%") else _f(v)


def _chance(v):
    """A per-mille chance parameter ("-": always)."""
    v = str(v).strip()
    return 1.0 if v in ("", "-") else _f(v) / 1000


def _rolls(chance):
    """A roll of a chance in 0..1 (1 and above: always, without drawing)."""
    return chance >= 1 or random.random() < chance


def heal_share(s, uid):
    """The share of a heal troop uid still receives (census H14): 1 - the held DEATHBLOW ("Reduces Received Healing
    Effect -40%", 1028; "Reduces Incoming Healing Amount -100%", 600451) and HP_HEAL_REDUCE ("Reduces Healing Amount
    of the recovery skill -30%", 1007) shares, not below 0. That HP_HEAL_REDUCE is the received healing is ours [I]."""
    cut = sum(_share(p[0]) for kind in ("DEATHBLOW", "HP_HEAL_REDUCE") for _, _, p in held_functions(s, uid, kind))
    return max(0.0, 1 - cut)


def regen_share(s, uid):
    """The share of its natural regeneration troop uid keeps: 1 - HP_REGEN_REDUCE ("Reduces naturally recovered HP
    -60%", 1009 Burn - Medium; 28 rows)."""
    return max(0.0, 1 - sum(_share(p[0]) for _, _, p in held_functions(s, uid, "HP_REGEN_REDUCE")))


def start_shield(s, uid, status, level):
    """A SHIELD status going on troop uid (census H14; 101 rows: 6090 Dark Ward ["20", "10", "10%"]: "Generates Shield
    with Max HP x 10% ... Receives enemy's attack x10 / Removed immediately after receiving an attack for removing the
    shield"): its record keeps the pool, ParamValue3 of the troop's max hp, and the attacks it takes, ParamValue2
    (absorb_shields). ParamValue1 (20 / 1) is unread [I]."""
    fns = _status_functions()
    rec = ((s.data.get("statuses") or {}).get(uid) or {}).get(status)
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    for r in fns.get((str(status), str(level))) or fns.get((str(status), "1")) or ():
        if r["FunctionType"] == "SHIELD" and isinstance(rec, dict) and t:
            rec["shield"] = [_share(r.get("ParamValue3"), t.get("max", 0)), int(_f(r.get("ParamValue2"), 1)) or 1]
            return True
    return False


def absorb_shields(s, uid, amounts):
    """The hits of one report on troop uid after its SHIELD statuses (start_shield): each takes what it can of the
    report's damage, hit by hit, and counts the report as one attack; a shield spent or out of attacks ends (0x5078).
    Returns the amounts left."""
    left = list(amounts)
    for sid, rec in list(((s.data.get("statuses") or {}).get(uid) or {}).items()):
        pool = rec.get("shield") if isinstance(rec, dict) else None
        if not pool:
            continue
        for k, a in enumerate(left):
            take = min(a, int(pool[0]))
            left[k], pool[0] = a - take, pool[0] - take
        pool[1] -= 1
        if pool[0] <= 0 or pool[1] <= 0:
            statuses.end(s, uid, sid)
    return left


def _progress(status, level, since, now):
    """The rate (%) of a status's %Function TRAITRATE_PROGRESS on GUARD_REDUCE (ParamValue2 the start, 3 the step, 4
    the end, 5 the step's period in seconds) after it has been held since `since`, or None: every guard of group 10
    (341 Glen, 3040 Isabella, 6040 Regnier, 7200 Helena, 6339, 6431) carries (GUARD_REDUCE, 90, 1, 70 / 75, 1); the
    reading "start, minus step every period, down to the end" is ours [I], the tape's two guarded blows fit it
    (guard_reduce)."""
    fns = _status_functions()
    for r in fns.get((str(status), str(level))) or fns.get((str(status), "1")) or ():
        p = [r.get(f"ParamValue{i}", "-") for i in range(1, 6)]
        if r["FunctionType"] != "TRAITRATE_PROGRESS" or p[0] != "GUARD_REDUCE":
            continue
        start, step, end, period = _f(p[1], 100.0), _f(p[2]), _f(p[3], 100.0), _f(p[4], 1.0) or 1.0
        return max(end, start - step * int(max(0.0, now - since) // period))
    return None


def guard_reduce(s, uid, rec, now=None):
    """The effective GUARD_REDUCE (per mille) of troop uid's guarded hit: its record's GUARD_REDUCE (heroes and nearly
    every NP row 700) plus its held statuses' GUARD_REDUCE traits (the guards' +300 flat), x the guard's
    TRAITRATE_PROGRESS rate (_progress: 90 % at first, falling 1 point a second to 70 %). A fresh guard so takes a
    tenth, a guard held 20 s three tenths, an NP unit (no guard status) three tenths. The tape: red "Defence 14" on the
    guarding Berserker against the Mountain Troll's 142 / 164 blows (part 2 f_00004 of 42:07-42:25, 2 fps), then
    "Defence 36" 10 s later (f_00024); white "Defence 23 / 21" on guarding units by the hero's "80" (part 5 f_00166 /
    f_00186), "757" among his ~2,500s (part 14 f_00095): 0.27-0.30."""
    now = time.monotonic() if now is None else now
    recs = ((s.data.get("statuses") or {}).get(uid) or {})
    held = held_levels(s, uid, now)
    pct, flat = status_bonus(held, "GUARD_REDUCE", (rec or {}).get("hero") or (rec or {}).get("leader"),
                             max(1, (rec or {}).get("level") or 1))
    value = (rec or {}).get("guard", 0.0) * (1 + pct / 100) + flat
    for sid, level in held.items():
        r = recs.get(sid)
        since = r.get("since", now) if isinstance(r, dict) else now
        rate = _progress(sid, level, since, now)
        if rate is not None:
            value *= rate / 100
            break
    return max(0.0, min(1000.0, value))


def guarding(s, uid):
    """Troop uid holds a COMMON_GUARD (group 10) status: the guard of a hit whose report carries no hit kind (an
    ability's execute, a volley, a charge)."""
    return any(GUARD_GROUP in _status_groups().get(st, ()) for st in held_statuses(s, uid))


PEACE_S = 10.0                 # the quiet spell after which the hero leaves combat mode (owner B1 2026-09-30: off after
                               # a quiet spell, reversing the 09-27 keep-on rule). No table or client string names the
                               # original's; chosen from the captures (174 runs, 2026-09-26..30): the hero's combat
                               # events (his 0x5132, 0x5117, hits on him, engagements with him) follow each other
                               # within 3 s 95.0 % of the time, 5 s 96.7 %, 10 s 98.1 %; the client's own re-requests
                               # while swinging come every 1-2 s (2,188 of 3,615 gaps), within 10 s 88 %. 10 s so a
                               # pause inside a fight (a run to the next group, a skill's cast) keeps the pose
S2C_STATUS_ADD = 0x5074        # status effects on troops (0x140d1b1b0): u16 n, n x (obool whole troop, u16 duration s,
                               # u16 troop uid [+ units]); u16 caster, u8 level, u32 status id, u16 event id (short crashes)
S2C_STATUS_END = 0x5078        # removal (0x140d1b3b0): u16 n, n x (obool whole troop, u16 uid); u8 kind, u32 status, u8
STATUS_HOLD_S = 600            # a status with no Duration row (guard 341) lasts until its chant ends


def hero_activity(s):
    """The hero fought (his combat-mode request, an ability, his hit or a hit on him, an engagement with him): the
    quiet spell starts again (PEACE_S); one timer runs at a time (_peace re-arms it for what is left)."""
    s.data["hero_active_at"] = time.monotonic()
    _arm_peace(s, PEACE_S)


def _arm_peace(s, delay):
    later = getattr(s, "later", None)
    if later is None or s.data.get("peace_armed"):
        return
    s.data["peace_armed"] = True
    later(delay, lambda: _peace(s))


def _peace(s):
    """The peace timer: after PEACE_S with no activity of the hero (hero_activity), no guard held (guarding) and no open
    engagement with a living troop (on_engage / on_engage_clear), his combat mode goes off (0x5133, set_stance): the
    client plays the town set again (601 COMMON_NORMAL_STAND / 602 MOVE_NORMAL_RUN; standing, the sheath 606). The
    client asks again (0x5132) when he next swings or guards, and a hit or an engagement puts it back on at once."""
    s.data["peace_armed"] = False
    battle = s.data.get("battle")
    t = battle and battle.troops.get(0)
    if not t or not t.get("hero") or not t.get("combat") or t.get("down") or t["hp"] <= 0:
        return
    quiet = time.monotonic() - s.data.get("hero_active_at", 0.0)
    if quiet < PEACE_S:
        _arm_peace(s, PEACE_S - quiet)
        return
    if guarding(s, 0) or any(statuses.alive(s, o) for o in (s.data.get("engaged") or {}).get(0, ())):
        _arm_peace(s, PEACE_S)                          # still guarding (a held guard sends no request), or in melee
        return                                          # with a living troop
    set_stance(s, False)


HERO_DAMAGE_SCALE = 1           # every hit of the hero (troop 0) on another troop, multiplied; 1 is the game's own damage.
                                # `py server/main.py --hero-damage N` sets it: the owner's exception is 10000 (2026-09-28,
                                # "can you incress our hero damage by 10000x?"), which tools/dev.py passes


def hero_moved(s, pos):
    """A hero position report (game.troop_sync): the mission reads where he is (game.on_hero_position)."""
    from . import game
    s.data["hero_prev"], s.data["hero_pos"] = s.data.get("hero_pos"), pos     # the way between two reports
    game.on_hero_position(s)


def set_stance(s, on):
    """The hero's combat mode (0x5133), on at once when a fight reaches him (the client's request 0x5132, an engagement
    with him, a hit on him); off after a quiet spell (_peace, PEACE_S; owner B1 2026-09-30). The client's setter 0x140bf9730 decides the look: standing (the
    action test 0x140bfa5c0: 1, 0x24, 0x32, 0x62, 0x259 or the stance's stand) it plays the draw 0x25f
    COMMON_NORMAL_TO_STAND, whose clip is the class's 비전투_무기빼기 "take the weapon out" (C_AHH_GL_0003,
    C_DEH_IS_0003 in data/unit/hero/*/c_*.uaf); otherwise it only sets hero+0x1030, and PlayAction 0x140bf5f80 turns the
    next run / stand request into the combat set (vt+0xe10 0x140bfc000: 0x26 MOVE_RUN, 0x32 COMBAT_CAUTION_STAND)
    instead of the town set (0x25a MOVE_NORMAL_RUN, 0x259 COMMON_NORMAL_STAND). Inferred: the clips place the weapon
    (the skeleton has weapon bones Dummy_WP_L / _R / _R01, named in the clip files too; in the original's footage the
    heroes hold their weapons in the Mist Field village, qeeQjhgO8ss frames 8-14), so a flip with no draw only skips
    the draw's flourish. Holding the push for a stand the server guessed (38dae01, 483c8fa: the draw gate and the off /
    on redraw) left her fighting in the town set for 16 s (live 2026-09-30 14:17:44-14:18:00, 0x50db 602 / 601 between
    her swings) and put her weapon away mid-fight (14:18:19.876 off, the sheath 606; the on at 14:18:21.377 landed
    while she ran)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(0)
    if t and t["hero"] and bool(t.get("combat")) != on:
        t["combat"] = on
        send_combat_mode(s, 0, on)
        log.info("hero combat mode %s", "on" if on else "off (peace)")


def status_duration(status, level):
    """statuseffectinfo %Improvement Duration (s) of a status level; STATUS_HOLD_S when it has none."""
    from . import tables
    imp = next((x for x in tables.sections("statuseffectinfo")["Improvement"]
                if x["Id"] == str(status) and x.get("Level") == str(level)), {})
    d = imp.get("Duration", "0")
    return int(float(d)) if d.replace(".", "").isdigit() and float(d) > 0 else STATUS_HOLD_S


def checkskill_statuses(ability, kit):
    """[(status, level, duration s)] from abilitytypeinfo %Function CHECKSKILL_ADD_STATUSEFFECT_NODMG (B55): the ability
    puts status ParamValue3 at level ParamValue4 on its caster when the caster holds skill ParamValue1 at level
    ParamValue2 (the Gunslinger's dash 2 with passive 7004 Lv n -> status 7000 Lv n; 30 rows)."""
    from . import tables
    out = []
    for r in tables.sections("abilitytypeinfo")["Function"]:
        if r["AbilityId"] == str(ability) and r["FunctionType"] == "CHECKSKILL_ADD_STATUSEFFECT_NODMG":
            p = [r.get(f"ParamValue{i}", "") for i in range(1, 5)]
            if all(v.isdigit() for v in p) and kit.get(int(p[0])) == int(p[1]):
                out.append((int(p[2]), int(p[3]), status_duration(p[2], int(p[3]))))
    return out


S2C_STATS = 0x5138             # the leader's stats (0x1406f6ba0): u8 n, n x (u32 value, i8 stat, u16 troop); HP ids <= 2
                               # use the packed value codec; the LeaderBase hook copies SP 6 / ammo 35 into the Player
STAT_SP, STAT_AMMO, STAT_FP = 6, 35, 82   # SP_CURRENT, STACK1_CURRENT, FP_CURRENT (the client's stat enum)
STAT_STACK2, STAT_FSP = 36, 99            # STACK2_CURRENT (Player +0x144), FSP_CURRENT (+0x160, Helena's gauge
                                          # 0x140690da0), both written from 0x5138 (HERO-CONTROLS-WIRING K5)
POOL_STATS = (("sp", "sp_max", STAT_SP, "SP", "SP_CURRENT"), ("ammo", "ammo_max", STAT_AMMO, "Stack1", "STACK1_CURRENT"),
              ("stack2", "stack2_max", STAT_STACK2, "Stack2", "STACK2_CURRENT"),
              ("fsp", "fsp_max", STAT_FSP, "FSP", "FSP_CURRENT"))   # pool, its max, stat, cost column, SELF trait


HP_SCALE_FREE = 0x3fffffff       # 0x5138 HP values: the top 2 bits pick a scale (x1, x2, x5, x10), so below 2^30 as is


def send_stats(s, stats, uid=0):
    """Every value a plain little-endian u32 (0x1406f6ba0; the HP ids, 0x14158ecb0 true, below 2^30 as is). The HP ids
    went out as pack_value's swapped u16 halves until 2026-09-28: after an equip the client read the hero's max HP 1,895
    as 124,190,720 (1,895 << 16), and at 0.0015% HP it played the low-HP blood screen (0x1408fac60: vt+0x298 / vt+0x288
    under 30%; owner live: "our hero entered in danget state like we are low hp")."""
    w = Writer(S2C_STATS).u8(len(stats))
    for sid, value in sorted(stats.items()):
        value = min(int(value), HP_SCALE_FREE) if sid <= 2 else int(value)
        w.u32(value & 0xffffffff).raw(struct.pack("<b", sid)).u16(uid)
    s.send(w)


def spend(s, ability, level=1):
    """The hero's SP, Stack1 (ammo, ice runes, fury), Stack2 (lightning runes, the Druid's summon slot), FSP (Helena's
    gauge) and finisher points for an ability use: abilitycastinfo %Improvement (COMMON, the level) SP, Stack1, Stack2,
    FSP and FP costs (the executions 90-93: FP 1000; 16 Stack2 rows, all Isabella's but 90000; Helena's 1522 FSP 1,
    1523 / 1524 FSP 6), and its SELF traits on SP_CURRENT / STACK1_CURRENT / STACK2_CURRENT / FSP_CURRENT (the R
    reloads: STACK1_CURRENT +10; the Druid's 1297 STACK2 +1; Helena's 1520 FSP +1, 1521 +6), capped at the pool's max;
    the client changes none itself (HERO-CONTROLS.md §3.3), so the new values go out as 0x5138 (POOL_STATS)."""
    from . import tables
    pools = s.data.get("pools")
    if not pools:
        return
    rows = [r for r in tables.sections("abilitycastinfo")["Improvement"]
            if r["AbilityId"] == str(ability) and r.get("SpotFilter") == "COMMON"]
    row = next((r for r in rows if r.get("Level") == str(level)), rows[0] if rows else None)
    if row is None:
        return
    num = lambda v: int(float(v)) if str(v).replace(".", "").lstrip("-").isdigit() else 0
    before = dict(pools)
    for pool, _, _, cost, _ in POOL_STATS:
        if pool in pools:
            pools[pool] = max(0, pools[pool] - num(row.get(cost)))
    if "fp" in pools:
        pools["fp"] = max(0, pools["fp"] - num(row.get("FP")))
    refill = {trait: (pool, top) for pool, top, _, _, trait in POOL_STATS}
    for i in (1, 2):
        if row.get(f"TraitObject{i}") == "SELF" and row.get(f"TraitOperation{i}") == "ADD":
            pool, top = refill.get(row.get(f"TraitType{i}"), (None, None))
            if pool in pools:
                pools[pool] = min(pools.get(top, 0), pools[pool] + num(row.get(f"TraitValue{i}")))
    changed = {sid: pools[pool] for pool, _, sid, _, _ in POOL_STATS if pool in pools and pools[pool] != before[pool]}
    if pools.get("fp") != before.get("fp"):
        changed[STAT_FP] = pools["fp"]
    if changed:
        send_stats(s, changed)
    start_regen(s)


SP_TICK_S = 3.0                # the regeneration period. SP: pools_for's SP_RECOVERY (%ApSp + the room troops') each
                               # tick, the original's HUD: Grey Rock +3 per 3 s, with the Grey Wood Bowmen +5, +10 or
                               # +15 in 8 s (tests/test_hero_pools.py). HP: HP_RECOVERY x this, shown as a green "+n"
                               # over the hero (0x507d, damage < 0 -> TextNumMgr type 10 HealingText): the tape's Lv 6
                               # Berserker mid-fight at Grey Rock shows "+24" at 38:42, 38:45 and 38:48 (part 2 2 fps
                               # frames 2321-2329): every 3 s, 8 x 3 (census M1)


@functools.cache
def _pool_ticks():
    """{(status, level): (period s, [(pool, amount)])} of the statuseffectinfo %Improvement rows with an OverTime whose
    traits raise or lower a hero pool (POOL_STATS' SELF traits: STACK1 / STACK2 / FSP / SP_CURRENT, the flat value
    Traitvalue_2, SUBTRACT negative): the Berserker's Dark Energy 6539 (passive 616, TYPE_PASSIVE, OverTime 3, STACK1
    +1), the Druid's 3365 (OverTime 3, +1), 6399 (OverTime 1, +2), the 700290-700340 items' (3 s). The client runs no
    status trait but speed (0x1407bc0c0), so these are the server's (rules census HERO P13)."""
    from . import tables
    pools = {trait: pool for pool, _, _, _, trait in POOL_STATS}
    out = {}
    for r in tables.sections("statuseffectinfo")["Improvement"]:
        period = _f(r.get("OverTime"))
        gains = []
        for i in range(1, 5):
            trait = r.get(f"TraitType0{i}")
            if period > 0 and trait in pools and r.get(f"FunctionType0{i}") in ("ADD", "SUBTRACT"):
                v = _f(r.get(f"Traitvalue0{i}2"))
                if v:
                    gains.append((pools[trait], -v if r[f"FunctionType0{i}"] == "SUBTRACT" else v))
        if gains:
            out[(int(r["Id"]), int(r["Level"]))] = (period, gains)
    return out


def pool_ticks(s, now=None):
    """The hero's held over-time pool statuses (_pool_ticks) credited for the time since their last credit (a status
    of period p gains floor(elapsed / p) times; the regeneration's 3 s tick calls this), capped at the pools' max and
    floored at 0; the new values sent (0x5138). The tape: the Dark Energy count rises +1 every 3 s in the village, the
    fields and the rooms (qeeQjhgO8ss 21:28 15 -> 21:58 24 -> 22:28 34; 2 fps 1555_1573 +1 at 25:58.0 / 26:01.5 /
    26:04.5 / 26:07.5), holds at 99 and starts from 0 in each new room. Returns {stat: value} sent."""
    pools = s.data.get("pools")
    if not pools:
        return {}
    now = time.monotonic() if now is None else now
    credited = s.data.setdefault("pool_ticks", {})
    before = dict(pools)
    ticks = _pool_ticks()
    for status, level in sorted(held_levels(s, 0).items()):
        tick = ticks.get((status, level)) or ticks.get((status, 1))
        if not tick:
            continue
        period, gains = tick
        since = ((s.data.get("statuses") or {}).get(0) or {}).get(status) or {}
        last = credited.setdefault(status, since.get("since", now) if isinstance(since, dict) else now)
        n = int((now - last + 1e-6) // period)
        if n <= 0:
            continue
        credited[status] = last + n * period
        for pool, amount in gains:
            if pool in pools:
                pools[pool] = max(0, min(pools.get(pool + "_max", 0), pools[pool] + int(amount) * n))
    for status in [k for k in credited if k not in held_levels(s, 0)]:
        credited.pop(status)
    changed = {sid: pools[pool] for pool, _, sid, _, _ in POOL_STATS if pool in pools and pools[pool] != before[pool]}
    if changed:
        send_stats(s, changed)
    return changed


def pool_ticks_due(s):
    """Whether a held over-time pool status can still move a pool (the regeneration keeps ticking for it)."""
    pools = s.data.get("pools") or {}
    ticks = _pool_ticks()
    for status, level in held_levels(s, 0).items():
        _, gains = ticks.get((status, level)) or ticks.get((status, 1)) or (0, ())
        for pool, amount in gains:
            if pool in pools and (pools[pool] < pools.get(pool + "_max", 0) if amount > 0 else pools[pool] > 0):
                return True
    return False


def start_regen(s):
    """Regenerate SP and the hero's HP (the pools' SP_RECOVERY a tick; the HP tick pools["hp_rec"] = hero.regen_tick,
    x HP_REGEN_OUT_OF_COMBAT unless his combat mode is on, census HERO P7; the client applies neither itself, BATTLE.md
    B22) and move the over-time pool statuses (pool_ticks, P13) while any can: one tick per SP_TICK_S, stopping when
    nothing is left to fill (a spend, a hit or a gear change restarts it). A fallen hero does not regenerate."""
    pools = s.data.get("pools")
    later = getattr(s, "later", None)
    battle = s.data.get("battle")
    hero = battle and battle.troops.get(0)
    hurt = bool(hero and hero.get("hero") and not hero.get("down") and 0 < hero["hp"] < hero.get("max", 0)
                and pools and pools.get("hp_rec"))
    if (not pools or later is None or s.data.get("regen")
            or (pools["sp"] >= pools["sp_max"] and not hurt and not pool_ticks_due(s))):
        return
    s.data["regen"] = True

    def tick():
        s.data["regen"] = False
        gain_sp(s, pools["sp_rec"])
        pool_ticks(s)                                   # Dark Energy and the other over-time pool statuses (P13)
        t = battle and battle.troops.get(0)
        if t and t.get("hero") and not t.get("down") and 0 < t["hp"] < t.get("max", 0) and pools.get("hp_rec"):
            from .game import send_troop_hp
            from .hero import HP_REGEN_OUT_OF_COMBAT      # the tick (hero.regen_tick), x5 out of combat (census P7)
            gain = pools["hp_rec"] * (1 if t.get("combat") else HP_REGEN_OUT_OF_COMBAT)
            gain = min(t["max"] - t["hp"], int(gain * regen_share(s, 0)))
            t["hp"] += gain
            send_troop_hp(s, 0, t["hp"], t["hp"])
            if gain > 0:                                # the green "+n" over the hero (census M1): 0x507d with a
                s.send(Writer(S2C_HERO_DAMAGE).u32(-gain & 0xffffffff).u16(0).u8(0).u8(0))    # negative amount
        start_regen(s)
    later(SP_TICK_S, tick)


def start_np_regen(s, uid):
    """An NP or deck troop's HP regeneration (census M2, TROOPS T1.14): its record's HP_RECOVERY (nptrooptable, 0 on
    12,363 rows; a deck troop's trooptable row at its level with its traits) back on every living unit (and its leader)
    each SP_TICK_S beat, floored as the unit HP is (T1.3), while it is hurt and alive; one timer a troop, restarted by
    the next hit. Sent as 0x505d. The tape: part 2 qeeQjhgO8ss 2 fps 2331-2356 s (Grey Rock), the F1 Drafted Infantry
    Lv 6 (HP_RECOVERY 1 + 0.9 x 5 = 5.5, 10 units) 6,282 -> 6,332 -> ... -> 6,661, +50 on the 3 s beat, while the handed
    archers (134060, HP_RECOVERY 0) stay at 913: 5 a unit a beat, not the hero's x SP_TICK_S (16.5, M1) (TROOPS hunt,
    2026-10-01)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    rate = _f(((t or {}).get("c") or {}).get("hp_rec"))
    later = getattr(s, "later", None)
    hurt = lambda t: any(0 < hp < t.get("unit_max", hp) for hp in t["units"]) or 0 < t.get("leader", 0) < t.get(
        "leader_max", 0)
    if not t or t["hero"] or int(rate) <= 0 or later is None or uid in s.data.setdefault("np_regen", set()) or             not hurt(t):                                # below 1 a unit a beat nothing comes back (the floor)
        return
    s.data["np_regen"].add(uid)

    def tick():
        s.data["np_regen"].discard(uid)
        if battle is not s.data.get("battle") or not statuses.alive(s, uid) or not hurt(t):
            return
        gain = int(int(rate) * regen_share(s, uid))
        if gain <= 0:                                   # a status took all of it: no beat until the next hit
            return
        top = t.get("unit_max") or max(t["units"] or [1])
        t["units"] = [min(top, hp + gain) if hp > 0 else 0 for hp in t["units"]]
        if t.get("leader", 0) > 0:
            t["leader"] = min(t["leader_max"], t["leader"] + gain)
        send_hp = (s.data.get("hit_callbacks") or (None,))[0]
        if send_hp is None:
            from .game import send_troop_hp as send_hp
        send_hp(s, uid, sum(t["units"]), t.get("leader"))
        start_np_regen(s, uid)
    later(SP_TICK_S, tick)


def gain_sp(s, amount):
    """SP back (regeneration, potions), capped at SP_MAX; sends the new value."""
    pools = s.data.get("pools")
    if pools and amount > 0 and pools["sp"] < pools["sp_max"]:
        pools["sp"] = min(pools["sp_max"], pools["sp"] + amount)
        send_stats(s, {STAT_SP: pools["sp"]})
        return True
    return False


@functools.cache
def _stack_gains():
    """{status: {level: (when, pool, amount, chance per mille, uses, used up)}} of the statuseffectinfo %Function rows
    that fill a hero's stack (the client runs neither function: empty cases of 0x140ca3570, BATTLE.md §6).
    ATTACK_GAIN_STACK1 / 2 (when "attack"): ParamValue1 the amount, 2 the chance out of 1000, 4 the landed hits it
    serves per application (100000: all), 5 True = it ends when they are used; 3 (1, or 0 on 6291) unread. Rows: the
    Spellsword's runes 3321 ICE / 3322 LIGHTNING (level n: n, 1000, 1, n, True), put on her by her skills (305, 314,
    336 ...), the Berserker's 6200 RAMPAGE (1, 1000, 1, 100000, False; his 643 passive and stance 738) and 620202
    (1, 100), 6202 (1, 500), 6291 DARKNESS_AURA (1, 1000, 0, 1, True), the Druid's affinity 3365 (2, 500), 3310
    (1, 5..21). HIT_ADD_STACK (when "hit": the hero took a hit): ParamValue1 the pool, 2 the amount, 3 the chance out
    of 1000; 4 (1) unread: 6201 IRON_BODY (stance 737) and the 6203 it adds, so each hit taken in that stance gives 2.
    The parameter roles are ours [I] (read from the values; no client code reads them)."""
    from . import tables
    out = {}
    for r in tables.sections("statuseffectinfo")["Function"]:
        kind, p = r["FunctionType"], [r.get(f"ParamValue{i}", "-") for i in range(1, 6)]
        if kind in ("ATTACK_GAIN_STACK1", "ATTACK_GAIN_STACK2"):
            gain = ("attack", "ammo" if kind.endswith("1") else "stack2", _f(p[0]), _f(p[1]), _f(p[3]), p[4] == "True")
        elif kind == "HIT_ADD_STACK":
            gain = ("hit", "ammo" if p[0] == "Stack1" else "stack2", _f(p[1]), _f(p[2]), 0, False)
        else:
            continue
        if r["Id"].isdigit() and r["Level"].isdigit():
            out.setdefault(int(r["Id"]), {})[int(r["Level"])] = gain
    return out


def gain_stacks(s, when):
    """The hero landed a hit ("attack") or took one ("hit"): each status he holds with a stack function for it
    (_stack_gains) adds its amount to Stack1 (stat 35) or Stack2 (stat 36), by its chance, capped at the pool's max; a
    status that serves a number of hits ends once they are used (0x5078). Returns {stat: value} sent."""
    pools = s.data.get("pools")
    held = ((s.data.get("statuses") or {}).get(0) or {})
    if not pools or not held:
        return {}
    gains = _stack_gains()
    before = dict(pools)
    for status, level in sorted(held_levels(s, 0).items()):
        gain = gains.get(status, {}).get(level) or gains.get(status, {}).get(1)
        if not gain or gain[0] != when or gain[1] not in pools:
            continue
        _, pool, amount, chance, uses, used_up = gain
        if chance < 1000 and random.random() * 1000 >= chance:
            continue
        pools[pool] = min(pools.get(pool + "_max", 0), pools[pool] + int(amount))
        rec = held.get(status)
        if isinstance(rec, dict) and uses:
            rec["used"] = rec.get("used", 0) + 1
            if used_up and rec["used"] >= uses:
                statuses.end(s, 0, status)
    changed = {sid: pools[pool] for pool, _, sid, _, _ in POOL_STATS if pool in pools and pools[pool] != before[pool]}
    if changed:
        send_stats(s, changed)
    return changed


def send_status(s, uid, status, level, duration, caster=None, event=0):
    """0x5074 for one troop uid or a list of them (whole-troop records, one duration); caster None = the troop itself
    (a self status), 0xffff = none; event = the area event that asked for it (0x5075), 0 for none."""
    uids = [uid] if isinstance(uid, int) else list(uid)
    w = Writer(S2C_STATUS_ADD).u16(len(uids))
    for u in uids:
        w.obool(True).u16(min(duration, 0xffff)).u16(u)
    s.send(w.u16(uids[0] if caster is None else caster).u8(level).u32(status).u16(event))


def start_dot(s, uid, status, level, caster):
    """Damage or healing over time (census H13, BATTLE-WIRING B48): a status whose statuseffectinfo %Improvement row
    carries an AttackType with AttackOperation SUBTRACT / ADD (304 statuses, 1,907 levels) strikes its holder every
    OverTime seconds while it lasts, Duration // OverTime times (held ones while held): the data's own words, 7 Burn
    "Inflicts Fire Damage equivalent to Magic Attack x @sar@ every @sot@ sec for @sdr@ sec" (AttackRate 500 = x 0.5,
    OverTime 2, Duration 10: five ticks), 11 Bleeding "... Physical Attack x ...", 610040 Warmth "Recovers HP equivalent
    to @sar@ of Magic Attack every @sot@ sec"; the flat AttackTypeValue beside it (the kobold sorcerer's poison 102301:
    100 a tick). Each tick is dot_hit. A re-application restarts the chain (the status's generation, status_gen); a
    removal, a cleanse or the holder's fall ends it. Returns whether a chain started."""
    imp = statuses.improvement(status, level)
    period = _f(imp.get("OverTime"))
    if imp.get("AttackType") in (None, "", "-") or imp.get("AttackOperation") not in ("SUBTRACT", "ADD") or period <= 0:
        return False
    later = getattr(s, "later", None)
    if later is None:
        return False
    duration = _f(imp.get("Duration"))
    n = int(duration // period) if duration > 0 else None
    gens = s.data.setdefault("status_gen", {})
    gen, box = gens.get((uid, status), 0), (s.data.get("statuses") or {}).get(uid)

    def tick(k):
        if gens.get((uid, status)) != gen or (s.data.get("statuses") or {}).get(uid) is not box or box is None:
            return                                      # applied again, removed, or its holder fell (forget)
        if n is None and status not in box:
            return
        dot_hit(s, uid, imp, caster)
        if n is None or k < n:
            later(period, lambda: tick(k + 1))
    later(period, lambda: tick(1))
    return True


def dot_hit(s, uid, imp, caster):
    """One tick of a damage / heal over time on troop uid (start_dot): SUBTRACT strikes every living unit (and a living
    leader; the hero once) through apply_hits with the attack {AttackType, AR = AttackRate / 1000, flat AttackTypeValue,
    "dot"} and the caster's record (its attack by the type's side, as resolve reads it; no caster: the flat part alone,
    at the holder's level), no hit roll, no crit and no guard (ours [I]); its numbers, kills and kill credit as any
    hit's. ADD heals them by the caster's magic attack x the rate + the flat value (apply_heals)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t or not statuses.alive(s, uid):
        return
    send_hp, on_down = s.data.get("hit_callbacks") or (None, None)
    if send_hp is None:
        from .game import send_troop_hp as send_hp
    src = battle.troops.get(caster) or {}
    att = src.get("c") or combatant(((t.get("c") or {}).get("level") or 1), None)
    rec = ((s.data.get("statuses") or {}).get(uid) or {}).get(int(imp["Id"])) if str(imp.get("Id", "")).isdigit() else None
    stacks = rec.get("stacks", 1) if isinstance(rec, dict) else 1   # a stacked status ticks once a stack (H5)
    attack = {"type": imp["AttackType"], "pr": 1.0, "ar": _f(imp.get("AttackRate")) / 1000 * stacks,
              "flat": _f(imp.get("AttackTypeValue")) * stacks, "dot": True}
    units = [LEADER] if t["hero"] else [i for i, hp in enumerate(t["units"]) if hp > 0] + (
        [LEADER] if t.get("leader", 0) > 0 else [])
    if imp.get("AttackOperation") == "ADD":
        apply_heals(s, [(uid, units)], attack, att, None, send_hp)
    else:
        apply_hits(s, [(uid, units)], send_hp, on_down, attacker=caster if caster in battle.troops else None,
                   attack=attack, record=att)


def expire_status(s, uid, status, duration):
    """A timed status ends after its Duration (B44; statuseffectinfo EndProcReason TIME_OUT 108): 0x5078 as end_statuses
    sends it. A newer application of the same status restarts the clock (only the latest timer removes it)."""
    later = getattr(s, "later", None)
    if later is None:
        return
    gens = s.data.setdefault("status_gen", {})
    gen = gens[(uid, status)] = gens.get((uid, status), 0) + 1

    def end():
        if gens.get((uid, status)) == gen:
            send_status_end(s, uid, status)
    later(duration, end)


def send_status_end(s, uid, status):
    s.data.get("statuses", {}).get(uid, {}).pop(status, None)      # the status engine's record goes too (status.py)
    s.send(Writer(S2C_STATUS_END).u16(1).obool(True).u16(uid).u8(1).u32(status).u8(0))


def chain_statuses(s, ability, uid=0, now=None):
    """[(status, level 1, duration s)] from abilitytypeinfo %Function STATUSEFFECT_CHAIN_NODAMAGE (B55): each cast moves
    the caster one step along statuseffectinfo %StatusEffectChain ParamValue1 (the Gunslinger's reloads 63-66, 71, 72:
    chain 1, fast-reload buffs 57 -> 58 -> 59, 30 s each); the step before is removed (0x5078); a cast after the last
    status ran out starts again at the first; at the top a Renewal True chain refreshes the last, a False one keeps it."""
    from . import tables
    now = time.monotonic() if now is None else now
    chains = _chains()
    ids = []
    for r in tables.sections("abilitytypeinfo")["Function"]:
        if r["AbilityId"] == str(ability) and r["FunctionType"] == "STATUSEFFECT_CHAIN_NODAMAGE" \
                and r["ParamValue1"] in chains and r["ParamValue1"] not in ids:
            ids.append(r["ParamValue1"])
    return [step for step in (chain_step(s, cid, uid, now) for cid in ids) if step]


@functools.cache
def _chains():
    from . import tables
    return {r["StatusEffectChainId"]: r for r in tables.sections("statuseffectinfo")["StatusEffectChain"]}


def chain_step(s, cid, uid, now=None):
    """(status, level 1, duration s) of the next step of statuseffectinfo %StatusEffectChain `cid` on troop uid, or
    None: a step after the last status ran out starts again at the first; the step before is removed (0x5078); at the
    top a Renewal True chain refreshes the last, a False one keeps it."""
    now = time.monotonic() if now is None else now
    c = _chains().get(str(cid))
    links = [int(c[f"Chain{i}"]) for i in range(1, 11) if str(c.get(f"Chain{i}", "")).isdigit()
             and int(c[f"Chain{i}"]) > 0] if c else []
    if not links:
        return None
    state = s.data.setdefault("chains", {})
    st = state.get((uid, str(cid)))
    live = st is not None and now < st["until"]
    if live and st["i"] == len(links) - 1 and c.get("Renewal") != "True":
        return None
    i = min(st["i"] + 1, len(links) - 1) if live else 0
    if live and links[st["i"]] != links[i]:
        send_status_end(s, uid, links[st["i"]])
    duration = status_duration(links[i], 1)
    state[(uid, str(cid))] = {"i": i, "until": now + duration}
    return links[i], 1, duration


def execute_chains(s, caster, ability, targets):
    """Every execute of a cast (census H12): abilitytypeinfo %Function STATUSEFFECT_CHAIN (177 rows: 54 / 119 the
    Gunslinger's bleed chain 3, 6453 -> 6454 -> 6455; 1020 the poison chain 2, 7100 -> 7104; ParamValue2 the chance
    per mille) steps each struck troop of the other side along the chain (chain_step), and
    STATUSEFFECT_ADD_STATUSEFFECT (4 rows: 628 Meteor ["LIVE_ENEMY", "6319", "LIVE_ENEMY", "6391", level]: 6391 on a
    struck enemy that holds 6319; 200107 / 200140 ["2001050", "1"]: that status on the struck enemies) adds its status.
    ParamValue3-5 of the chain rows (true / True / false) are unread [I]."""
    if ability is None or not targets:
        return
    level = statuses.cast_level(s, ability, caster)
    fns = _functions().get((ability, str(level))) or _functions().get((ability, "1")) or []
    mine = statuses.side(s, caster)
    struck = [uid for uid, _ in targets if uid != caster and statuses.side(s, uid) != mine and statuses.alive(s, uid)]
    for r in fns:
        p = [r.get(f"ParamValue{i}", "-") for i in range(1, 6)]
        if r["FunctionType"] == "STATUSEFFECT_CHAIN":
            for uid in struck:
                step = _rolls(_chance(p[1])) and chain_step(s, p[0], uid)
                if step:
                    statuses.apply(s, [uid], step[0], step[1], caster)
        elif r["FunctionType"] == "STATUSEFFECT_ADD_STATUSEFFECT":
            if p[0] == "LIVE_ENEMY" and p[1].isdigit() and p[3].isdigit():
                to = [uid for uid in struck if int(p[1]) in statuses.holding(s, uid)]
                sid, lv = int(p[3]), int(_f(p[4], 1)) or 1
            elif p[0].isdigit():
                to, sid, lv = struck, int(p[0]), int(_f(p[1], 1)) or 1
            else:
                continue
            if to:
                statuses.apply(s, to, sid, lv, caster)


def end_statuses(s, ability, uid):
    """An ability ended (0x5068): the statuses its cast put on the caster go (0x5078)."""
    for status in s.data.get("chant_statuses", {}).pop((ability, uid), []):
        send_status_end(s, uid, status)
        log.info("troop %d: status %d ended with ability %d", uid, status, ability)


def send_combat_mode(s, uid, on):
    s.send(Writer(S2C_COMBAT_MODE).u8(1).u16(uid).raw(bytes([T2[int(on)]])))


def on_combat_mode(s, pkt):
    """The client's request (0x5132, sent when a swing or a guard starts, at most once a second, always "on"): answered
    at once; its re-sends while he fights keep the peace timer off (hero_activity, _peace)."""
    b = pkt.rest()
    if len(b) < 3:
        log.warning("combat mode request too short: %s", b.hex())
        return
    uid = dec_uid(b[0:2])
    on = T2[(1 + 2 * b[0]) & 0xff] == b[2]
    t = s.data.get("battle") and s.data["battle"].troops.get(uid)
    if t and t["hero"]:
        t["combat"] = on
        if on:
            hero_activity(s)
    log.info("troop %d combat mode %s", uid, on)
    send_combat_mode(s, uid, on)


def on_engage(s, pkt):
    b = pkt.rest()
    if len(b) < 5:
        log.warning("engage report too short: %s", b.hex())
        return
    a, d = dec_uid(b[0:2]), dec_uid(b[3:5])
    log.info("engage %d -> %d %s", a, d, "on" if b[2] else "off")
    s.send(Writer(S2C_ENGAGE).raw(b[:5]))
    pairs = s.data.setdefault("engaged", {})           # who is in melee with whom (engaged: the synastry state)
    for x, y in ((a, d), (d, a)):
        if b[2]:
            pairs.setdefault(x, set()).add(y)
            if statuses.players(s, y):                  # it fought the player's side (status.fights_player)
                s.data.setdefault("fought_player", set()).add(x)
        else:
            pairs.get(x, set()).discard(y)
    if b[2]:
        from . import director
        director.on_engage(s, a, d)
    if 0 in (a, d) and b[2]:                           # a fight with the hero: his combat mode (set_stance)
        set_stance(s, True)
        hero_activity(s)


def on_use_ability(s, pkt):
    """Confirm an ability use. Request (0x1404fa650): +0 ability id (4 coded bytes), +4 caster pos (7, packed),
    +0xb u16, +0xd direction, +0xe target troop (coded u16), +0x10 caster troop u16, +0x12 target pos (7),
    +0x19 coded u16, +0x1b target kind + list. Confirmation (0x140d19720 reads 30 bytes, then the list with
    0x140d1fca0): +0 result, +1 target troop, +3 u16 cast serial, +5 caster troop, +7 the 3 bytes from +0xb,
    +0xa caster pos, +0x11 ability id, +0x15 target pos, +0x1c the u16 from +0x19, then the request's list."""
    b = pkt.rest()
    if len(b) < 0x1c:
        log.warning("ability use too short: %s", b.hex())
        return
    serial = s.data["cast_serial"] = s.data.get("cast_serial", 0) % 0xfffd + 1
    s.data.setdefault("casts", {})[serial] = b[0x10:0x12]      # caster troop (plain u16), for 0x5067
    ability = s.data.setdefault("cast_ability", {})[serial] = obf.dec_u32(b[0:4])
    caster = struct.unpack_from("<H", b, 0x10)[0]
    level = statuses.cast_level(s, ability, caster)
    if caster == 0:
        hero_activity(s)
    # HUD troop skills also use0x5117 (native F1 Shield Use I). Their owner pays
    # the same table cost as0x505f; the following commit/execute pays nothing.
    if caster == 0 or statuses.players(s, caster):
        spend(s, ability, level)
    pay_hp(s, caster, ability, level)
    body = (bytes([0]) + b[0xe:0x10] + struct.pack("<H", serial) + b[0x10:0x12] + b[0xb:0xe] + b[4:0xb]
            + b[0:4] + b[0x12:0x19] + b[0x19:0x1b] + b[0x1b:])
    s.send(Writer(S2C_USE_ABILITY).raw(body))
    target = dec_uid(b[0xe:0x10])
    journal_cast(s, caster, ability, target, serial)
    from . import director
    director.on_skill(s, caster, target, ability)


C2S_TROOP_CAST = 0x505f        # troop ability cast (troop-skill AI, scripts; builder 0x1404f9420), 15 bytes: coded u16
                               # target, u16 caster, coded u32 ability, packed position (7)
S2C_TROOP_CAST = 0x5060        # Packet_AbilityCastRes 0x140d18980, 17 bytes (shorter crashes): coded target, coded ability,
                               # position, u16 cast serial, u16 caster; the executes (0x5066) then carry the serial


C2S_COMMIT = 0x5064             # ability commit (AbilityCast::_DoCommit, builder 0x1404f9f90): u8 direction, u16 (cast
                               # +0x7a), u32 ability, packed target position (7), u16 cast serial, coded u16 target troop,
                               # then the target kind + list (the 0x5117 shape)
S2C_COMMIT = 0x5065            # Packet_AbilityCommitRes 0x140d190b0: 17 bytes (u16 target, position, u16 serial, u8, u16
                               # caster, u8, u16), then the kind + list (0x140d1fca0, as in 0x5118); it releases the
                               # executes (0x5066) queued behind the commit; under 17 bytes crashes


def on_commit(s, pkt):
    b = pkt.rest()
    if len(b) < 0x13:
        log.warning("ability commit too short: %s", b.hex())
        return
    serial = struct.unpack_from("<H", b, 0xe)[0]
    caster = s.data.get("casts", {}).get(serial, struct.pack("<H", 0xFFFE))
    body = (struct.pack("<H", obf.dec_u16(b[0x10:0x12])) + b[7:14] + b[0xe:0x10] + b"\0" + caster + b"\0" + b[1:3]
            + b[0x12:])
    s.send(Writer(S2C_COMMIT).raw(body))


def on_troop_cast(s, pkt):
    """A troop skill cast (0x505f: coded u16 target, u16 caster, coded u32 ability, packed position): the serial and
    0x5060, for any caster (the hero, the player's troops, and every NP troop's AI: the host client runs them all in a
    solo room, and an unanswered cast keeps the ability reserved); the journal's "cast" line; the mission table hears
    it (director.on_skill). A cast of the player's troops (a deck or handed troop, status.players) costs the hero's SP
    (T5.8: abilitycastinfo %Improvement SP at the cast's level, spend, pushed as 0x5138; the tape, part 2 f_01098 ->
    f_01099: 570 -> 533 as the handed archers' Fire Arrow 500045, SP 40, goes off, + 3 regeneration). The client
    checks the cost against the hero's SP before it sends (CanTargeting 0x140c23240, the usable flag 0x140840ac0) and
    spends nothing; 0x5060 has no refusal form (0x140d18980 reads no result) and an unanswered cast freezes the troop,
    so one that arrives unpaid anyway (a race with the SP push) is answered and takes the SP down to 0. An NP troop's
    casts are free (its owner's SP is 0, so its SP-cost skills never fire: the client's rule), and so are the hero's
    own 0x505f uses (the aimed-shot trigger 176): his 0x5117 uses pay (on_use_ability)."""
    b = pkt.rest()
    if len(b) < 15:
        log.warning("troop cast too short: %s", b.hex())
        return
    serial = s.data["cast_serial"] = s.data.get("cast_serial", 0) % 0xfffd + 1
    s.data.setdefault("casts", {})[serial] = b[2:4]
    ability = s.data.setdefault("cast_ability", {})[serial] = obf.dec_u32(b[4:8])   # for its executes (status.on_execute)
    s.send(Writer(S2C_TROOP_CAST).raw(b[0:2] + b[4:8] + b[8:15] + struct.pack("<H", serial) + b[2:4]))
    caster, target = struct.unpack_from("<H", b, 2)[0], dec_uid(b[0:2])
    log.info("troop %d casts %d on troop %d", caster, ability, target)
    if caster and statuses.players(s, caster):
        level = statuses.cast_level(s, ability, caster)
        cost = _f((improvement(ability, level) or {}).get("SP"))
        pools = s.data.get("pools") or {}
        if cost > pools.get("sp", cost):
            log.warning("troop %d cast %d (SP %d) with the hero's SP at %d: answered, SP to 0", caster, ability, cost,
                        pools.get("sp", 0))
        spend(s, ability, level)
    pay_hp(s, caster, ability, statuses.cast_level(s, ability, caster))
    journal_cast(s, caster, ability, target, serial)
    from . import director
    director.on_skill(s, caster, target, ability)


def pay_hp(s, caster, ability, level=1):
    """An ability's HP cost (census F12): abilitycastinfo %Improvement HP at the cast's level, "20%" (54 rows), "10%"
    (18), "5%" (18), "40%" (9) a share of the caster's max HP, a number that many hp (80020 the tower's 13000): the
    troop skills that "sacrifice HP" (60019 Stimulant, 70152 Blood Contract, 75015 Self-sacrifice, 70162 Critical
    Sacrifice ...). Each living unit (and a living leader; the hero his pool) pays the share of its own max, never below
    1 hp (ours [I]: "You sacrifice HP to cast", no row that kills its caster); the new hp goes out as 0x505d. The client
    changes none itself. Returns what was paid."""
    row = improvement(ability, level) if ability is not None else None
    cost = str((row or {}).get("HP", "0")).strip()
    battle = s.data.get("battle")
    t = battle and battle.troops.get(caster)
    if not t or cost in ("", "-", "0") or not statuses.alive(s, caster):
        return 0
    share = _f(cost) / 100 if cost.endswith("%") else None
    take = lambda hp, top: min(hp - 1, round(top * share) if share is not None else int(_f(cost))) if hp > 1 else 0
    paid = 0
    if t["hero"]:
        paid = take(t["hp"], t.get("max", t["hp"]))
        t["hp"] -= paid
        troop_hp, leader_hp = t["hp"], t["hp"]
    else:
        top = t.get("unit_max") or max(t["units"] or [1])
        for i, hp in enumerate(t["units"]):
            if hp > 0:
                n = take(hp, top)
                t["units"][i], paid = hp - n, paid + n
        if t.get("leader", 0) > 0:
            n = take(t["leader"], t.get("leader_max", t["leader"]))
            t["leader"], paid = t["leader"] - n, paid + n
        troop_hp, leader_hp = sum(t["units"]), t.get("leader")
    if paid > 0:
        send_hp = (s.data.get("hit_callbacks") or (None,))[0]
        if send_hp is None:
            from .game import send_troop_hp as send_hp
        send_hp(s, caster, troop_hp, leader_hp)
        log.info("troop %d paid %d hp for ability %s (%s)", caster, paid, ability, cost)
        if t["hero"]:
            start_regen(s)
    return paid


def journal_cast(s, caster, ability, target, serial):
    """The journal's "cast" line of a0x505f or0x5117: the caster's side ("player's": the hero, a deck or handed troop; "ally":
    the player's team; "neutral": zone team 255; else "enemy"), the ability's abilitytypeinfo StringId and the level it
    runs at (status.cast_level). Its hits follow in the "hits" summary under the caster."""
    if net.journal_out is None:
        return
    team = (s.data.get("zone_troops", {}).get(caster) or {}).get("TeamNum")
    side = ("player's" if statuses.players(s, caster) else "ally" if statuses.side(s, caster) == 0
            else "neutral" if team == 255 else "enemy")
    name = _rows_by("abilitytypeinfo", "Basic", "AbilityId").get(str(ability), {}).get("StringId")
    net.journal("cast", spot=s.data.get("spot"), troop=caster, ability=ability, name=name, target=target,
                level=statuses.cast_level(s, ability, caster), side=side, serial=serial)


def target_list_len(b, i):
    """Length of an ability target list at b[i:] (0x140d20060 / 0x140d208d0): u16 n, n * (u8 flag, u16 troop uid,
    then only when the flag byte is 0: u16 m, m * u16 unit index << 5; writer 0x1404fdc90 -> 0x1404fdc00). Raises
    struct.error / IndexError on a short list."""
    start = i
    n = struct.unpack_from("<H", b, i)[0]
    i += 2
    for _ in range(n):
        if b[i] != 0:
            i += 3                          # the whole troop: no unit list
            continue
        m = struct.unpack_from("<H", b, i + 3)[0]
        i += 5 + 2 * m
    if i > len(b):
        raise IndexError("target list past the end")
    return i - start


class WholeTroop(list):
    """A target list record with a nonzero flag (census E6): the whole troop, its share of the ability = flag / 255
    (the writer 0x140820870: share x 255, at least 1; AffectType TROOP gives every troop in the area 1.0, TROOP_FACTOR
    shares; the client applies the hit to every living unit and the leader, 0x140820200). It reads as [0] where only the
    troop matters (the statuses); apply_ability strikes every living unit and the leader, x the share [I: the scaling]."""
    def __init__(self, flag):
        super().__init__([0])
        self.share = max(1, flag) / 255


def ability_targets(b, i):
    """[(troop uid, [unit index, ...])] of an ability target list at b[i:] (see target_list_len); a whole-troop record
    gives a WholeTroop."""
    n = struct.unpack_from("<H", b, i)[0]
    i += 2
    out = []
    for _ in range(n):
        uid = struct.unpack_from("<H", b, i + 1)[0]
        if b[i] != 0:
            out.append((uid, WholeTroop(b[i])))
            i += 3
            continue
        m = struct.unpack_from("<H", b, i + 3)[0]
        out.append((uid, [struct.unpack_from("<H", b, i + 5 + 2 * k)[0] >> 5 for k in range(m)]))
        i += 5 + 2 * m
    return out


def ability_props(b, i):
    """The smart prop ids after an ability target list at b[i:]: u8 k, k * coded u32 (0x1404fdc90)."""
    if len(b) <= i:
        return []
    k = b[i]
    return [obf.dec_u32(b[i + 1 + 4 * j:i + 5 + 4 * j]) for j in range(k) if len(b) >= i + 5 + 4 * j]


def on_ability_execute(s, pkt, send_troop_hp=None, on_down=None, on_props=None):
    """A hit of a confirmed cast. Request: 7-byte packed position, u16 cast serial, target list, 1 byte.
    Reply 0x5067: u16 serial, flag (T1-coded, false: the summon/select path is for special abilities), u16 caster
    troop (remembered from the 0x5117 that got this serial), the request's target list. On a hero-only field the
    hero's hits arrive only this way (no 0x504f), so the targets take the hit here; a cast's own troop is skipped."""
    b = pkt.rest()
    try:
        serial = struct.unpack_from("<H", b, 7)[0]
        n = target_list_len(b, 9)
        targets = ability_targets(b, 9)
    except (struct.error, IndexError):
        log.warning("ability execute not understood: %s", b.hex())
        return
    caster = s.data.get("casts", {}).get(serial, b"\0\0")
    s.send(Writer(S2C_ABILITY_EXECUTE).u16(serial).obool(False).raw(caster).raw(b[9:9 + n]))
    ability = s.data.get("cast_ability", {}).get(serial)   # kept for every execute of the cast (a multi-hit skill's
    executes = s.data.setdefault("executes", {})           # later hits need it; dropped at its 0x506a, on_cast_done)
    k = executes[serial] = executes.get(serial, 0) + 1     # the k-th execute: ProcessRate_k (ability_attack)
    own = struct.unpack("<H", caster)[0]
    finishing = ability is not None and bool(statuses.functions(
        ability, statuses.cast_level(s, ability, own), "FINISH_KILL"))
    # A lethal finisher's ordinary damage otherwise clears status31 before its
    # execution function can grant the lesson/proc. Resolve that function first;
    # it owns the death once. Other casts keep their damage-before-status order.
    if finishing:
        statuses.on_execute(s, serial, ability, own, targets, send_troop_hp, on_down)
    if send_troop_hp is not None:                       # the hit first: a status the cast puts on (86, the aimed
        apply_ability(s, own, ability, k, targets, send_troop_hp, on_down,  # shot's mark) counts from its next hit
                      stage=s.data.get("charge", {}).get(serial, 0))        # a charged skill's stage (on_charge_step)
    if not finishing:
        statuses.on_execute(s, serial, ability, own, targets, send_troop_hp, on_down)   # the statuses by the execute's
                                                        # ProcessStatusEffect; removals and the execution once a cast
    execute_chains(s, own, ability, targets)           # the damage chains: every execute (H12)
    props = ability_props(b, 9 + n)
    if props and on_props is not None:
        on_props(s, props)


def caster_record(battle, uid, ability):
    """The combatant record a cast of `ability` by troop uid strikes with: its NP leader's when the ability is the
    leader's (npleadertable %Skill) and not the troop's own (Grey Rock's Glen 134010 / Thompson 134020: 200137 on troop
    rows that hold 81001), else the troop's. A troop's casts all arrive under its uid (0x505f +2)."""
    t = battle.troops.get(uid) or {}
    own, lead = t.get("c"), t.get("leader_c")
    if lead is not None and ability in lead.get("skills", {}) and ability not in (own or {}).get("skills", {}):
        return lead
    return own


def apply_ability(s, caster, ability, k, targets, send_troop_hp, on_down=None, stage=0):
    """The k-th execute of caster's cast of ability on [(troop uid, [unit index])] (ability_attack with the caster's
    record, caster_record: a leader's skill strikes with the leader's; the hero's level from the kit, an NP caster's
    from its record's %Skill list, else 1). A SUBTRACT ability (or an unknown one: the plain hit) damages the listed
    troops that are not on the caster's team, never its own troop (friendly fire off, BATTLE F12; ours); an ADD ability
    heals those on its team (B60); NOOP changes no hp (ours)."""
    battle = s.data.get("battle")
    if battle is None:
        return
    targets = [_whole(battle, uid, units) for uid, units in targets]
    att = caster_record(battle, caster, ability)
    level = s.data.get("kit", {}).get(ability, 1) if caster == 0 else (att or {}).get("skills", {}).get(ability, 1)
    attack = ability_attack(att, ability, level, k, stage)
    if attack is not None and attack.get("ability") is not None:          # the units the execute struck, the hero's
        attack = dict(attack, struck=sum(len(e[1]) for e in targets),              # Stack2 (A8)
                      stack2=(s.data.get("pools") or {}).get("stack2", 0) if caster == 0 else 0)
    op = (attack or {}).get("op", "SUBTRACT")
    team = (att or {}).get("team")
    mate = lambda uid: team is not None and ((battle.troops.get(uid) or {}).get("c") or {}).get("team") == team
    if op == "ADD":
        apply_heals(s, [(e[0], e[1]) for e in targets if mate(e[0])], attack, att, ability, send_troop_hp)
    elif op in ("SUBTRACT", None):
        took = apply_hits(s, [e for e in targets if e[0] != caster and not mate(e[0])], send_troop_hp,
                          on_down, attacker=caster, attack=attack, record=att) or {}
        if ability is not None:
            for uid, dealt in took.items():
                drain_vitality(s, uid, ability, level, dealt)
    if ability is not None and att is not None:
        hp_traits(s, caster, ability, level, k, [e[0] for e in targets], mate, att, send_troop_hp, on_down)
        if k == 1:
            reinforce(s, ability, level, [e[0] for e in targets if mate(e[0])], send_troop_hp)
    from . import director
    for e in targets:                                   # a cast on a place names no target (0xffff), its executes do:
        director.on_skill(s, caster, e[0], ability)     # Flamegrass' Blizzard on the column


def _unit_parts(t, target):
    """The unit indexes a trait's TraitTarget reaches in troop t: TROOP its living units, LEADER its leader (the hero
    himself), ALL both."""
    if t["hero"]:
        return [LEADER]
    units = [i for i, hp in enumerate(t["units"]) if hp > 0] if target in ("TROOP", "ALL") else []
    return units + ([LEADER] if target in ("LEADER", "ALL") and t.get("leader", 0) > 0 else [])


def hp_traits(s, caster, ability, level, k, uids, mate, att, send_troop_hp, on_down=None):
    """An ability's HP traits (census F6 / F14; abilitycastinfo %Improvement TraitObject ALLY / ENEMY, TraitType
    HP_BASEUNIT, 390 rows): ADD heals, SUBTRACT takes, each reached unit (TraitTarget TROOP its units, LEADER its leader,
    ALL both) of each listed troop of that side, the value a share of the unit's max hp ("15%") or a number; the data's
    words: 5012 Supplement "Restores target ally Troops by 15% of Max HP", 312 "Instantly restores Max HP x 10%",
    60036 "Inflicts 5000 damage on a selected enemy. Ignores its Defence" (a fixed amount, no roll). TraitTimesType ONCE
    on the first execute only; TraitProbability per mille. Heals are cut by the target's DEATHBLOW / HP_HEAL_REDUCE."""
    row = improvement(ability, level) or {}
    battle = s.data.get("battle")
    for i in (1, 2):
        obj, kind, op = row.get(f"TraitObject{i}"), row.get(f"TraitType{i}"), row.get(f"TraitOperation{i}")
        if kind != "HP_BASEUNIT" or obj not in ("ALLY", "ENEMY") or op not in ("ADD", "SUBTRACT"):
            continue
        if row.get(f"TraitTimesType{i}") == "ONCE" and k != 1:
            continue
        if not _rolls(_f(row.get(f"TraitProbability{i}"), 1000) / 1000):
            continue
        value, target = str(row.get(f"TraitValue{i}", "0")), row.get(f"TraitTarget{i}")
        for uid in uids:
            t = battle.troops.get(uid)
            if not t or uid == caster and obj == "ENEMY" or (obj == "ALLY") != mate(uid):
                continue
            parts = _unit_parts(t, target)
            top = lambda i_: (t.get("max", 0) if t["hero"] else t.get("leader_max", 0) if i_ == LEADER
                              else t.get("unit_max", 0))
            amounts = [round(_share(value, top(i_)) if value.endswith("%") else _f(value)) for i_ in parts]
            if not parts or not any(amounts):
                continue
            if op == "ADD":
                heal_units(s, uid, parts, amounts, send_troop_hp, ability)
                continue
            for part, amount in zip(parts, amounts):
                apply_hits(s, [(uid, [part])], send_troop_hp, on_down, attacker=caster, record=att,
                           attack={"type": att.get("plain"), "fixed": amount, "ability": ability})


def heal_units(s, uid, parts, amounts, send_troop_hp, ability=None):
    """Raise the listed units of troop uid (LEADER: its leader, or the hero) by their amounts, cut by the received-
    healing statuses (heal_share), capped at their max; 0x505d and the heal line 0x505e. Returns the restored total."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t or not statuses.alive(s, uid):
        return 0
    cut = heal_share(s, uid)
    before = Battle.total(t)
    for i, a in zip(parts, amounts):
        a = round(a * cut)
        if t["hero"]:
            t["hp"] = min(t.get("max", t["hp"]), t["hp"] + a)
        elif i == LEADER:
            t["leader"] = min(t["leader_max"], t["leader"] + a) if t.get("leader", 0) > 0 else t.get("leader", 0)
        elif 0 <= i < len(t["units"]) and t["units"][i] > 0:
            t["units"][i] = min(t.get("unit_max") or t["units"][i], t["units"][i] + a)
    restored = Battle.total(t) - before
    send_troop_hp(s, uid, t["hp"] if t["hero"] else sum(t["units"]), t["hp"] if t["hero"] else t.get("leader"))
    if restored > 0:
        from .game import S2C_HEAL, HEAL_NO_SOURCE, pack_value
        b = bytearray(4)
        pack_value(b, 0, restored)
        s.send(Writer(S2C_HEAL).u32(HEAL_NO_SOURCE).u16(uid).u32(0).raw(bytes(b)))
        log.info("troop %d restored by %d (ability %s)", uid, restored, ability)
    return restored


def reinforce(s, ability, level, uids, send_troop_hp):
    """REINFORCE_TROOP (census F14; abilitytypeinfo %Function, 37 rows: 5012 Supplement "30, 0, 100, 1" "Replaces some
    fallen Troop Members", 81090 "-, 10, 20, 1" "Resurrects 10 fallen soldiers with 20% HP", 4098 "10, 5, 100, 1"):
    each listed allied troop gets back ParamValue1 % of its fallen units (rounded up), or ParamValue2 of them when that
    is more, with ParamValue3 % of a unit's hp: 0x505b alive TRUE for each (the heal revival's path), then 0x505d.
    ParamValue4 (1) unread; the readings of 1 and 2 are ours [I] from 81090's text."""
    battle = s.data.get("battle")
    for p in statuses.functions(ability, level, "REINFORCE_TROOP"):
        for uid in uids:
            t = battle and battle.troops.get(uid)
            if not t or t["hero"] or not any(t["units"]):
                continue
            dead = [i for i, hp in enumerate(t["units"]) if hp <= 0]
            n = max(-(-len(dead) * int(_f(p[0])) // 100) if str(p[0]).replace(".", "").isdigit() else 0,
                    int(_f(p[1])))
            back = dead[:n]
            if not back:
                continue
            top = t.get("unit_max") or max(t["units"])
            for i in back:
                t["units"][i] = max(1, round(top * _f(p[2], 100) / 100))
            send_unit_live(s, uid, [], back)
            send_troop_hp(s, uid, sum(t["units"]), t.get("leader"))
            log.info("troop %d: %d fallen units back (ability %s)", uid, len(back), ability)


S2C_STAMINA = 0x5131             # Packet_TroopStamina (0x140d17f30, reader 0x140d20c80): u8 n, n x (u16 troop, u16 m, m x
                                 # (i16 unit, -1 the leader unit +0x838; u32 vitality)) -> unit +0x140, the yellow bar =
                                 # unit +0x140 x 100 / troop +0x74c (BATTLE-WIRING §3.2)


def send_stamina(s, uid, shown_only=False):
    """0x5131 with troop uid's vitality (its pool's unit: the commander -1, else 0); shown_only: only when its type
    shows the bar (nptrooptype / npleadertype STAMINA_VISIBLE: 364 of 1,165 troop types, 266 of 280 leader types)."""
    t = (s.data.get("battle") and s.data["battle"].troops.get(uid)) or {}
    vit = t.get("vit")
    if vit and (not shown_only or (vit.get("rec") or {}).get("stamina_visible")):
        s.send(Writer(S2C_STAMINA).u8(1).u16(uid).u16(1).raw(struct.pack("<h", vit["unit"])).u32(int(vit["cur"])))


def drain_vitality(s, uid, ability, level, dealt):
    """A skill's execute that dealt `dealt` to troop uid drains its vitality (census I5): min(dealt x Add_StaminaProb /
    1000, STAMINA_MAX x GROGGY_RATE / 200) whole points, x (1 - STAMINA_REDUCE / 100) (abilitycastinfo %Improvement;
    npleadertable / nptrooptable), pushed as 0x5131; at 0 the row's KDOWN_STATUSEFFECT_ID at its _LV goes on (3000208
    STAMINA_OUT_STUN "Exhausted after consuming all vitality", 3 s + 1 s a level; the troll's 3000210) and the bar is full
    again when it ends [I]; nothing recovers it otherwise (STAMINA_RECOVERY 0). The tape (part 2 Grey Rock, the
    commanders' 41-point bars measured at 10 fps; tape dig 2026-10-01): only skills drain ("Only skills consume
    Vitality", text 6021; the combos 803-806 have GROGGY_RATE and Add_StaminaProb 0); Dark Impact 633 (GROGGY_RATE 50,
    Add_StaminaProb 2000) takes 10 of 41 (the cap) 17 times for 7-200 damage, Charging Slash 608 (50, 100) 6 for 61,
    Capture 710 (10, 100) 2; on the troll (3274) Dark Impact takes ~1.8 x its damage (the cap 818 never reached). The
    formula is ours [I], fitted to those; the damage share of the Add_StaminaProb 100 skills is pinned to about x 2. The
    weight's meaning is the game's words: the 64 abilities whose text says "Significantly decreases enemy Vitality on
    hit." carry Add_StaminaProb 2000 (textability_eng), 3 carry 100."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    vit = (t or {}).get("vit")
    row = improvement(ability, level) or {}
    rate, prob = _f(row.get("GROGGY_RATE")), _f(row.get("Add_StaminaProb"))
    if not vit or vit["cur"] <= 0 or dealt <= 0 or (rate <= 0 and prob <= 0) or not statuses.alive(s, uid):
        return 0
    rec = vit.get("rec") or {}
    cap = vit["max"] * rate / 200
    drain = int(min(dealt * prob / 1000, cap) * max(0.0, 1 - _f(rec.get("stamina_reduce")) / 100))
    if drain <= 0:
        return 0
    vit["cur"] = max(0, vit["cur"] - drain)
    send_stamina(s, uid)
    if vit["cur"] == 0:
        sid, lv = rec.get("kdown") or (0, 1)
        if sid > 0:
            statuses.apply(s, [uid], sid, lv, statuses.NO_CASTER)
        later = getattr(s, "later", None)
        dur = _f(statuses.improvement(sid, lv).get("Duration")) if sid > 0 else 0

        def refill():
            if (s.data.get("battle") or Battle()).troops.get(uid) is t and statuses.alive(s, uid):
                vit["cur"] = vit["max"]
                send_stamina(s, uid)
        if later is not None and dur > 0:
            later(dur, refill)
        log.info("troop %d: vitality out, status %d (level %d)", uid, sid, lv)
    return drain


def _whole(battle, uid, units):
    """A WholeTroop record's units: every living unit and a living leader (the hero: himself), with its share as the
    hit's scale (apply_hits' third field); any other record as it is."""
    if not isinstance(units, WholeTroop):
        return uid, units
    t = battle.troops.get(uid) or {}
    if t.get("hero"):
        return uid, [LEADER], units.share
    every = [i for i, hp in enumerate(t.get("units", ())) if hp > 0] + ([LEADER] if t.get("leader", 0) > 0 else [])
    return uid, every or [0], units.share


def apply_heals(s, targets, attack, att, ability, send_troop_hp):
    """A heal ability's execute (B60): each listed troop gains ATTACK_MAGICAL x AR + the flat value (ours: the caster's
    magical attack, AttributeRate and AttributeValue of abilitycastinfo) on its listed units, 0x505d, the heal line
    0x505e (the restored total); with abilitytypeinfo %Heal Revival True its dead units come back (0x505b alive TRUE)
    with up to MaxHealUnitHp % of a unit ("-": 100)."""
    battle = s.data.get("battle")
    if battle is None or att is None or not targets:
        return
    from .game import S2C_HEAL, HEAL_NO_SOURCE, pack_value
    lo, hi = att["atk"][MAGICAL]
    matk = random.uniform(lo, hi) if hi > lo else lo
    amount = max(0, round(matk * attack.get("ar", 0.0) + attack.get("flat", 0.0)))
    row = _rows_by("abilitytypeinfo", "Heal", "AbilityId").get(str(ability), {})
    revive = _f(row.get("MaxHealUnitHp"), 100.0) / 100 if row.get("Revival") == "True" else 0.0
    for uid, units in targets:
        t = battle.troops.get(uid)
        before = t and (t["hp"] if t["hero"] else sum(t["units"]))
        r = battle.heal(uid, units, round(amount * heal_share(s, uid)), revive)
        if r is None:
            continue
        troop_hp, leader_hp, revived = r
        send_troop_hp(s, uid, troop_hp, leader_hp)
        if revived:
            send_unit_live(s, uid, [], revived)
        if troop_hp > before:
            restored = bytearray(4)
            pack_value(restored, 0, troop_hp - before)
            s.send(Writer(S2C_HEAL).u32(HEAL_NO_SOURCE).u16(uid).u32(0).raw(bytes(restored)))
            log.info("troop %d healed by %d (ability %s)", uid, troop_hp - before, ability)


def heal_troop(s, uid):
    """A troop's living units back to full (director "heal" with a troop: Glen's "I'll restore it for now"), sent as a
    heal ability's result is (0x505d, the heal line 0x505e); False when it is not in the battle or has fallen."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t or t["hero"] or not any(t["units"]):
        return False
    from .game import S2C_HEAL, HEAL_NO_SOURCE, pack_value, send_troop_hp
    before = sum(t["units"])
    top = t.get("unit_max") or max(t["units"])
    r = battle.heal(uid, [i for i, hp in enumerate(t["units"]) if hp > 0], top, 0.0)
    if r is None:
        return False
    troop_hp, leader_hp, _ = r
    send_troop_hp(s, uid, troop_hp, leader_hp)
    if troop_hp > before:
        restored = bytearray(4)
        pack_value(restored, 0, troop_hp - before)
        s.send(Writer(S2C_HEAL).u32(HEAL_NO_SOURCE).u16(uid).u32(0).raw(bytes(restored)))
    log.info("troop %d restored by %d (the script)", uid, troop_hp - before)
    return True


C2S_CHARGE_STEP = 0x5062       # AbilityCast::_IncreaseChargeStep 0x140c20740 (builder 0x1404fb9a0): u16 cast serial, one
                               # per charge stage reached; no other request of the cast names the stage


def on_charge_step(s, pkt):
    """A charged skill reached its next stage: counted per cast serial for the cast's executes (charge_stage). No
    reply: 0x5063 does nothing for the caster's own troop. Never seen live (no cast has passed stage 0)."""
    b = pkt.rest()
    if len(b) < 2:
        return
    serial = struct.unpack_from("<H", b, 0)[0]
    steps = s.data.setdefault("charge", {})
    steps[serial] = steps.get(serial, 0) + 1


def on_cast_done(s, pkt):
    b = pkt.rest()
    if len(b) < 2:
        log.warning("cast done too short: %s", b.hex())
        return
    serial = struct.unpack_from("<H", b, 0)[0]
    for key in ("casts", "cast_ability", "executes", "cast_runs", "charge"):  # the cast's record, ability, executes go
        s.data.get(key, {}).pop(serial, None)
    s.send(Writer(S2C_CAST_DONE).u16(0).u16(0).u16(serial))


def on_engage_clear(s, pkt):
    b = pkt.rest()
    if len(b) < 2:
        log.warning("engage clear too short: %s", b.hex())
        return
    s.send(Writer(S2C_ENGAGE_CLEAR).raw(b[:2]))
    pairs = s.data.get("engaged") or {}                # its engage list emptied: out of melee
    uid = struct.unpack_from("<H", b, 0)[0]
    for other in pairs.pop(uid, ()):
        pairs.get(other, set()).discard(uid)


def send_unit_live(s, uid, dead, alive=()):
    w = Writer(S2C_UNIT_LIVE).u16(uid).u16(len(dead) + len(alive))
    for idx in dead:
        w.obool(False).raw(struct.pack("<h", idx))
    for idx in alive:                                  # alive TRUE: a revived unit (0x140d17100 revives it)
        w.obool(True).raw(struct.pack("<h", idx))
    s.send(w)


def on_hit(s, pkt, send_troop_hp, on_down=None, on_props=None):
    """A hit report (0x5053 an NP troop's, 0x504f the hero's swing): the attacker named by its header (hit_source)
    hits with its table attack (hit_attack), each unit's hit kind (a guard) as the client reports it. A cast's reaction
    copy (reaction_copy) is skipped: its 0x5066 applies it. Until 2026-09-30 the hero's 0x504f were skipped for 2 s
    after his last 0x5117 (CAST_SWING_S), which let 13 of 1,182 live copies strike twice (census E2)."""
    try:
        body = pkt.rest()
        _, targets, kinds, props = parse_hit_kinds(body, HIT_HEADER[pkt.proto])
        troop, unit, action = hit_source(body, pkt.proto)
    except (struct.error, IndexError):
        log.warning("hit report 0x%04x not understood: %s", pkt.proto, pkt.rest().hex())
        return
    if reaction_copy(body, pkt.proto):
        return
    battle = s.data.get("battle")
    att = battle and striker(battle, troop, unit == LEADER)
    apply_hits(s, targets, send_troop_hp, on_down, attacker=troop, attack=hit_attack(att, action), record=att,
               kinds=kinds)
    if props and on_props is not None:
        on_props(s, props)


C2S_HIT_SYNC = 0x5056            # the solo hit-reaction sync (0x140530990): 15-byte records (on_hit_sync)
HIT_SYNC_RECORD = 15


def on_hit_sync(s, pkt, send_troop_hp, on_down=None):
    """C2S 0x5056, the solo room's hit-reaction sync: records of 15 bytes, +0 bit 7 the troop's leader struck, +1 u16
    attack id, +3 u16 the E_ActionEnum (0xffff on the hero's), +5 coded attacker troop, +7 coded target troop, +9 the
    6-byte hit record (+4 unit + 3) (planning/client/combat.md; the old map read +3 as the attacker unit). A swing
    that struck one unit comes here, two or more as 0x504f.
    In a solo room it is the only report of an NP troop's melee blow on a troop not the player's, and of most blows on
    the CPU allies (live 2026-09-29 01:55-02:00, Tower: 1,387 blows of the allies on the Encablossians, 1,163 of them
    the player's troop 10100, and 907 of theirs on the allies, none in 0x5053; the server ignored it and the allies
    fought for minutes without a kill, owner: "they keep there fighting for ever but they neveer kill"). A 0x5053 never
    had a twin here (Grey Rock 2026-09-28: 0 of 336 within 50 ms). The hero's records repeat his 0x5066 (applied
    there): skipped. A ranged troop's records are its melee blows (actions 72 / 73: 12,284 live), not its arrows
    (0x505a); they were skipped until the contract showed it. The attack is the record's action (hit_attack), a
    leader's with the leader's record."""
    battle = s.data.get("battle")
    if battle is None:
        return
    b = pkt.rest()
    blows = {}                                        # (attacker, action) -> [(target, [unit], [kind])]
    for i in range(0, len(b) - HIT_SYNC_RECORD + 1, HIT_SYNC_RECORD):
        r = b[i:i + HIT_SYNC_RECORD]
        attacker, target = dec_uid(r[5:7]), dec_uid(r[7:9])
        action = struct.unpack_from("<H", r, 3)[0]
        att = (battle.troops.get(attacker) or {}).get("c")
        if attacker == 0 or action == 0xffff or att is None or att.get("hero"):
            continue
        unit = (r[13] | ((r[14] & 1) << 8)) - 3
        blows.setdefault((attacker, action, bool(r[0] & 0x80)), []).append((target, [unit], [hit_kind(r[9:15])]))
    for (attacker, action, leader), hits in blows.items():
        att = striker(battle, attacker, leader)
        apply_hits(s, [(uid, units) for uid, units, _ in hits], send_troop_hp, on_down, attacker=attacker,
                   attack=hit_attack(att, action), record=att, kinds=[k for _, _, k in hits])


def striker(battle, uid, leader=False):
    """The combatant record a blow of troop uid strikes with: its leader's when the report says the leader struck
    (0x504f +5 / 0x5056 +0 bit 7: 1,157 live blows), else the troop's."""
    t = battle.troops.get(uid) or {}
    return (t.get("leader_c") if leader else None) or t.get("c")


VOLLEY_ACTION = 80               # ATTACK_LIGHT_RANGE: the %Combat slot of a ranged troop's volley (hit_attack)
VOLLEY_UNSHARE = 1.25            # the client sends each target's share of the arrows as share ** 0.8 (0x142935110)


def on_area_damage(s, pkt, send_troop_hp, on_down=None):
    """C2S 0x505a (B12): a ranged volley, a charge or an area hit of the source troop on each listed troop, with the
    client's ratio ((b >> 1) / 127). A ranged NP troop's volley (EventDamageRange::Execute 0x1408c0700: the impact
    area's troops weighted into shares summing to 1, each sent as share ** 0.8; 37 live packets sum to 0.979-1.000):
    its living units' arrows split by share (at least one per target), each a hit of its ranged attack on the
    target's front unit (a dead one passes the hit on: Battle.hit). Until 2026-09-28 a volley was one charge hit:
    Tower of Moonlight's handed archers 11006 (133120, 42 units) did 1 damage per target in 115 of 115 hits (owner:
    "our trops are not dealing damage there"). Other sources (charges, areas): ours, one hit on the troop's front
    living unit, the charge's power rate (charge_attack) scaled by the ratio."""
    b = pkt.rest()
    try:
        source, n = dec_uid(b[0:2]), struct.unpack_from("<H", b, 2)[0]
        records = [(dec_uid(b[4 + 3 * i:6 + 3 * i]), b[6 + 3 * i]) for i in range(n)]
    except (struct.error, IndexError):
        log.warning("area damage not understood: %s", b.hex())
        return
    battle = s.data.get("battle")
    if battle is None:
        return
    if not records:
        journal_empty_volley(s, source)
    targets = []
    for uid, code in records:
        t = battle.troops.get(uid)
        if t is None or uid == source:
            continue
        front = 0 if t["hero"] else next((i for i, hp in enumerate(t["units"]) if hp > 0), 0)
        targets.append((uid, [front], (code >> 1) / 127))
    src = battle.troops.get(source) or {}
    att = src.get("c")
    if att is not None and not att.get("hero") and ranged(att["main"]) and src.get("units"):
        able = sum(1 for hp in src["units"] if hp > 0) or 1
        volley = [(uid, units * max(1, round(able * share ** VOLLEY_UNSHARE))) for uid, units, share in targets]
        apply_hits(s, volley, send_troop_hp, on_down, attacker=source, attack=hit_attack(att, VOLLEY_ACTION))
        return
    if att is not None and not att.get("hero"):         # Charge::Execute's report: the source is charging (ours:
        s.data.setdefault("troop_state", {})[source] = CHARGE   # until its next 0x50b0 record)
    apply_hits(s, targets, send_troop_hp, on_down, attacker=source, attack=charge_attack(att))


def hit_add_statuses(s, attacker, uid):
    """The attacker's HIT_ADD_STATUSEFFECT statuses (census H14; 279 rows: 6349 Thunderbolt Upgrade ["6350", "6350",
    "6351", "100"], 700000 ["700012", "-", "-", "1000"]: "Applies X effect for n sec to the enemy you attacked") put
    ParamValue1 at level 1 on the troop it damaged, by ParamValue4 per mille ("-": always). ParamValue2 / 3 (700000's
    "additionally ... if the enemy is Ranged or Wizard") are not read [I]."""
    for _, _, p in held_functions(s, attacker, "HIT_ADD_STATUSEFFECT"):
        if str(p[0]).isdigit() and int(p[0]) > 0 and _rolls(_chance(p[3])):
            statuses.apply(s, [uid], int(p[0]), 1, attacker)


def reflect(s, uid, attacker, dealt, send_troop_hp, on_down=None):
    """The target's REFLECT_DAMAGE statuses (census H14; 14 rows: 6103 Lightning Shield ["LIGHTNING", "100%", "1000"],
    6210 Rage / 6214 Hell Cry ["FIRE", "30%", "1000"]: "Reflects 30% of the damage as Fire Damage") send ParamValue2 of
    what it took back to the attacker, by ParamValue3 per mille: a flat hit of the ParamValue1 type on the attacker's
    front unit (it meets that defence and synastry; no hit roll; a reflection is not reflected). Ours [I]: the flat
    through the resolver."""
    battle = s.data.get("battle")
    src = battle and battle.troops.get(attacker)
    t = battle and battle.troops.get(uid)
    if not src or not t:
        return
    for _, _, p in held_functions(s, uid, "REFLECT_DAMAGE"):
        if not _rolls(_chance(p[2])):
            continue
        amount = dealt * _share(p[1])
        front = LEADER if src["hero"] else next((i for i, hp in enumerate(src["units"]) if hp > 0), LEADER)
        rec = t.get("c") or combatant(1, None)
        apply_hits(s, [(attacker, [front])], send_troop_hp, on_down, attacker=uid, record=rec,
                   attack={"type": p[0], "pr": 1.0, "ar": 0.0, "flat": amount, "dot": True, "reflect": True})


def bloodsuck(s, attacker, dealt, send_troop_hp):
    """The attacker's BLOODSUCK statuses (census H14; 20 rows: 16 Vampirism ["30%", "1000", "5%", ...], 6210 Rage
    ["150%", "1000", "1%", ...]) heal it by ParamValue1 of the damage its report dealt, by ParamValue2 per mille, at
    most ParamValue3 (a share of its max hp, or a number). ParamValue4 / 5 (True / False) unread; the reading is ours
    [I] (16 has no text)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(attacker)
    if not t:
        return
    for _, _, p in held_functions(s, attacker, "BLOODSUCK"):
        if not _rolls(_chance(p[1])):
            continue
        cap = _share(p[2], t.get("max", 0)) if str(p[2]).strip() not in ("", "-") else float("inf")
        amount = round(min(dealt * _share(p[0]), cap) * heal_share(s, attacker))
        units = [i for i, hp in enumerate(t.get("units", [])) if hp > 0] if not t["hero"] else [LEADER]
        r = amount > 0 and battle.heal(attacker, units, amount)
        if r:
            send_troop_hp(s, attacker, r[0], r[1])


def on_hit_statuses(s, att, action, attacker, uid):
    """An NP blow of an action its %Combat row names in StatusEffectAddActionEnum_n (_on_hit_statuses) that dealt
    damage puts that status on the struck troop by its Probability per mille, the striker its caster (status.apply:
    immunity, overlap, damage over time); once a report per troop [I]."""
    for sid, level, prob in ((att or {}).get("onhit") or {}).get(action, ()):
        if prob >= 1000 or random.random() * 1000 < prob:
            statuses.apply(s, [uid], sid, level, attacker if attacker is not None else statuses.NO_CASTER)


S2C_KILL_COUNT = 0x50b9          # MainHUD C2A_playKillCount (0x140d1c170): i32 count (> 0 shown), u8 style 0 / 1 / 2 (the
                                 # Flash's frames 1 / 2 / 3); BATTLE-WIRING B17


@functools.cache
def _kill_rule(code):
    """herotable %ActionCount of a class (every class: CountType KILL, MaxCount 99, ActionCount / SkillCount True,
    InitializationNextAction True, InitializationTime 20, InitializationAttacked False): (max, seconds)."""
    from . import tables
    r = next((r for r in tables.sections("herotable")["ActionCount"] if r["HeroId"] == code), {})
    return int(_f(r.get("MaxCount"), 99)) or 99, _f(r.get("InitializationTime"), 20.0) or 20.0


def kill_count(s, n=1, now=None):
    """The hero's kill counter (census I9, B17): each unit (or leader) his hits and skills fell adds one, up to the
    class's %ActionCount MaxCount (99); a kill more than InitializationTime (20 s) after the last starts again at 1; each
    count goes out as 0x50b9 (the "15 KILL" / "26 KILL" / "39 KILL" popups of the tape, part 2 Grey Rock, all in the one
    look: style 0, ours [I]; the client picks nothing itself). Being hit does not reset it (InitializationAttacked
    False). Returns the count."""
    from . import hero
    now = time.monotonic() if now is None else now
    c = (s.data.get("char") or ((s.data.get("account") or {}).get("characters") or [{}])[0]) or {}
    cls = c.get("class", 0)
    top, window = _kill_rule(hero.HERO_CODE[cls] if 0 <= cls < len(hero.HERO_CODE) else "GLEN")
    count, last = s.data.get("kill_streak", (0, None))
    if last is None or now - last > window:
        count = 0
    count = min(top, count + n)
    s.data["kill_streak"] = (count, now)
    s.send(Writer(S2C_KILL_COUNT).u32(count).u8(0))
    return count


def _hp_ratio(t, idx):
    if t["hero"]:
        return t["hp"] / max(1, t.get("max", t["hp"]))
    if idx == LEADER and "leader" in t:
        return t["leader"] / max(1, t["leader_max"])
    units = t["units"]
    return units[idx] / max(1, t.get("unit_max") or 1) if 0 <= idx < len(units) else 1.0


HITS_S = 1.0                     # ours: the journal's hit summary, one line a second while hits land


def journal_hit(s, attacker, uid, dealt, hits=1):
    """Count `hits` unit hits (a blow, an arrow each) of troop attacker on troop uid, together dealing `dealt`, for the
    journal's summary (net.journal "hits"): per attacking troop its hits and damage, per target the damage it took;
    the line goes out HITS_S after the first hit counted, with each target's hp left. Until 2026-09-30 a target troop
    counted as one hit: a 16-arrow volley read "x1 = 171" (Grey Rock, the handed archers 10073)."""
    if net.journal_out is None:
        return
    tally = _journal_hit_tally(s)
    by = tally["by"].setdefault(-1 if attacker is None else attacker, [0, 0])
    by[0], by[1] = by[0] + hits, by[1] + max(0, dealt)
    tally["on"][uid] = tally["on"].get(uid, 0) + max(0, dealt)


def journal_empty_volley(s, source):
    """A volley report (0x505a) of troop source that named no troop: the client's impact list was empty (an NP volley
    at the player's hero always is: EventDamageRange::Execute 0x1408c0700 drops a hero-type leader's troop, INVENTORY
    "Enemy archers aimed at the lone hero"), so nothing is applied; counted for the journal's "volley" line, which
    goes out with the second's hit summary. Grey Rock 16:50 (2026-09-30): 20164 / 20166 fired 6 such volleys and the
    journal showed nothing ("foes archers ... do the motions but nothing happens")."""
    if net.journal_out is None:
        return
    empty = _journal_hit_tally(s)["empty"]
    empty[source] = empty.get(source, 0) + 1


def _journal_hit_tally(s):
    """The second's tally (hits by attacker, damage by target, empty volleys by source); the first entry of a second
    starts it and its HITS_S timer."""
    tally = s.data.get("hit_tally")
    if tally is None:
        tally = s.data["hit_tally"] = {"by": {}, "on": {}, "empty": {}}
        s.later(HITS_S, lambda: _journal_hits(s))
    return tally


def _journal_hits(s):
    tally, battle = s.data.pop("hit_tally", None), s.data.get("battle")
    if not tally or battle is None:
        return
    left = lambda u: (Battle.total(battle.troops[u]), battle.troops[u]["max"]) if u in battle.troops else (0, 0)
    if tally["by"] or tally["on"]:
        net.journal("hits", spot=s.data.get("spot"), secs=HITS_S, by=[[a, n, d] for a, (n, d) in tally["by"].items()],
                    on=[[u, d, *left(u)] for u, d in tally["on"].items()])
    if tally.get("empty"):
        net.journal("volley", spot=s.data.get("spot"), secs=HITS_S, empty=[[u, n] for u, n in tally["empty"].items()])


def field_retaliation(s, uid, attacker, dealt):
    """Supply the sole hero target for a surviving hostile field NPC after real damage.

    Native 2026-10-01: TAI50000 dispatches but its TroopAggro stays empty after hits;
    0x5067's under-attack list is a different store. 0x50b4 writes the AI's ranked
    list even on the simulating client. This deliberately covers the single hero
    case only: multi-attacker HateValue ranking/decay remain unproven (COMBAT E10).
    Keep the latch on the battle record so replacement/respawn cannot inherit it.
    """
    if attacker != 0 or uid == 0 or dealt <= 0:
        return
    from . import game
    if not game.is_field(s.data.get("spot")):
        return
    zone = s.data.get("zone_troops", {}).get(uid)
    if not zone or zone.get("TeamNum", game.NP_TEAM) in (game.PLAYER_TEAM, 250, 255):
        return
    battle = s.data.get("battle")
    t, hero = battle.troops.get(uid), battle.troops.get(0)
    bound = s.data.get("bound", set())
    if (not t or not hero or Battle.total(t) <= 0 or Battle.total(hero) <= 0 or
            t.get("field_retaliation") or uid not in bound or 0 not in bound):
        return
    s.send(Writer(S2C_AGGRO).u8(1).u16(uid).u8(1).u16(0))
    t["field_retaliation"] = True
    net.journal("field_retaliation", spot=s.data.get("spot"), troop=uid, targets=[0])


def clear_field_retaliation(s, uid):
    """Forget this NPC's target on return/death, or every hero target on hero death.

    Send the reader's empty list; this changes neither HP nor the native movement
    program. No generic threat-list policy is applied to missions or other owners.
    """
    battle = s.data.get("battle")
    if battle is None:
        return
    for other, t in battle.troops.items():
        if (uid == 0 or other == uid) and t.pop("field_retaliation", False):
            s.send(Writer(S2C_AGGRO).u8(1).u16(other).u8(0))
            net.journal("field_retaliation", spot=s.data.get("spot"), troop=other, targets=[])


def on_field_return(s, pkt):
    from . import game
    body = pkt.rest()
    if len(body) != 3 or body[2] != 0 or not game.is_field(s.data.get("spot")):
        return
    uid = dec_uid(body)
    if uid not in s.data.get("zone_troops", {}) or uid not in s.data.get("bound", set()):
        return
    clear_field_retaliation(s, uid)
    net.journal("forced_return", spot=s.data.get("spot"), troop=uid)


def in_sight(s, uid):
    """Whether troop `uid` is within NUMBERS_RANGE of the hero; a place not reported yet counts as near."""
    here, there = s.data.get("hero_pos"), s.data.get("last_pos", {}).get(uid)
    return not here or not there or math.hypot(here[0] - there[0], here[2] - there[2]) <= NUMBERS_RANGE


def apply_hits(s, targets, send_troop_hp, on_down=None, attacker=None, attack=None, record=None, kinds=None):
    """Hits on [(troop uid, [unit index][, scale])] by troop `attacker` with `attack` (hit_attack / ability_attack /
    charge_attack; scale multiplies its AR, 0x505a's ratio): each unit's amount and damage words from resolve_hit (the
    target's held statuses, the unit's hp ratio, the guard), hp, unit deaths (0x505b), the numbers with their words
    (0x507b over enemies, 0x507d over the hero: before - after, FLAG_* per unit), the troop-icon tally (0x507c: the sum
    dealt to each victim by the attacker, B15), and on_down(s, uid) when a troop is wiped, with
    s.data["killed_by"][uid] = the attacker (the kill feed's killer, B7). A hit of the player's own (status.players)
    marks its target as fighting him (status.fights_player). `record` is the combatant record the hits strike with (a
    leader's blow: his leader's, striker), else the attacker troop's: Glen's and Thompson's leader blows had struck with
    their attack-0 shells' (133010 / 133030), 0 each since b335664 (the 04:59 Tower capture replayed,
    test_replay_tower_0459). kinds[k]: the client's hit kind of each unit of targets[k] (hit_kind; a kind in
    GUARDED_KINDS is a guarded hit); without them a hit on a troop holding a guard status is guarded (guarding). The
    hero's peace timer hears only his own fight: his hits and the hits on him (hero_activity)."""
    battle = s.data.get("battle")
    if battle is None:
        return {}
    if targets and (attacker == 0 or any(entry[0] == 0 for entry in targets)):
        hero_activity(s)
    att = record or ((battle.troops.get(attacker) or {}).get("c") if attacker is not None else None)
    dot = bool((attack or {}).get("dot"))
    if not dot and (attack or {}).get("ability") is None and held_functions(s, attacker, "TROOP_NOATTACK_DPS"):
        return {}                                       # a stunned, frozen, escaping or reviving troop's blows land
                                                        # nothing (H14: TROOP_NOATTACK_DPS on 28 statuses, each with
                                                        # %Forbidden Controllability); an ability's execute still does
                                                        # (733, the get-up counter, puts the escape's 6321 on its first
                                                        # execute and strikes on the next four) [I]
    own = held_levels(s, attacker) if attacker is not None else {}     # its buffs (status_bonus)
    mine = attacker is not None and statuses.players(s, attacker)
    numbers, tally, drained = [], [], 0
    for k, entry in enumerate(targets):
        uid, units = entry[0], entry[1]
        if statuses.invincible(s, uid):                 # i-frames (the escape's 6321): no hit lands
            continue
        t = battle.troops.get(uid)
        if t is None or t.get("untouchable"):
            continue
        if mine and uid != attacker:
            s.data.setdefault("fought_player", set()).add(uid)
        before = t["hp"] if t["hero"] else list(t["units"])
        before_leader = t.get("leader", 0)
        if t["hero"] and not t["combat"]:           # a hero under attack: his combat mode (set_stance)
            set_stance(s, True)
        hit = dict(attack, ar=attack.get("ar", 1.0) * entry[2]) if attack and len(entry) > 2 else attack
        held = held_levels(s, uid)
        state = state_of(s, uid)                        # the synastry row of the target's state (0x50b0, engage)
        ks = (kinds[k] if kinds and k < len(kinds) else None) or [None] * len(units)
        guarded_by_status = guarding(s, uid)
        outcomes = []
        for i, kind in zip(units, list(ks) + [None] * (len(units) - len(ks))):
            rec = t.get("leader_c") if i == LEADER and "leader" in t else t.get("c")
            guarded = (kind in GUARDED_KINDS if kind is not None else guarded_by_status) and not (hit or {}).get("dot")
            if kind == DODGE_KIND and not (hit or {}).get("dot"):
                outcomes.append((0, FLAG_DODGE))
                continue
            outcomes.append(resolve_hit(att, rec, hit, held, _hp_ratio(t, i), state=state, own=own,
                                        guard=guard_reduce(s, uid, rec) if guarded else None))
        amounts = [a for a, _ in outcomes]
        if attacker == 0 and uid != 0:
            amounts = [round(a * HERO_DAMAGE_SCALE) for a in amounts]  # whole HP (a scale of 1.5 made floats)
        amounts = absorb_shields(s, uid, amounts)
        words = {}                                      # unit index -> its hits' damage words (FLAG_*)
        for i, (_, fl) in zip(units, outcomes):
            words[i] = words.get(i, 0) | fl
        troop_hp, leader_hp, dead = battle.hit(uid, units, amounts,
                                               floor=1 if held_functions(s, uid, "IMMORTAL") else 0)
        if t["hero"]:
            dealt = before - t["hp"]
            flags = functools.reduce(int.__or__, words.values(), 0)
            if dealt > 0 or flags & FLAG_DODGE:
                s.send(Writer(S2C_HERO_DAMAGE).u32(max(0, dealt)).u16(uid).u8(flags).u8(0))
        else:
            hits = [(i, b - a, words.get(i, 0)) for i, (b, a) in enumerate(zip(before, t["units"])) if b > a]
            dealt = sum(d for _, d, _ in hits) + before_leader - t.get("leader", 0)
            hits += [(i, 0, FLAG_DODGE) for i, fl in words.items()          # a dodge shows its word at 0
                     if fl & FLAG_DODGE and i >= 0 and all(j != i for j, _, _ in hits)]
            if hits:                                    # the leader's number: his unit index in 0x507b is not read
                numbers.append((uid, hits))
        if dealt > 0 and attacker is not None:
            tally.append((uid, dealt))
        journal_hit(s, attacker, uid, dealt, len(units))
        send_troop_hp(s, uid, troop_hp, leader_hp)
        if Battle.total(t) <= 0:
            clear_field_retaliation(s, uid)
        else:
            field_retaliation(s, uid, attacker, dealt)
        if dealt > 0 and troop_hp > 0 and attack and attack.get("action"):
            on_hit_statuses(s, att, attack["action"], attacker, uid)
        if dealt > 0 and not dot and attacker is not None and uid != attacker:
            drained += dealt
            if troop_hp > 0:
                hit_add_statuses(s, attacker, uid)
            reflect(s, uid, attacker, dealt, send_troop_hp, on_down)
        from . import director
        director.on_hp(s, uid, Battle.total(t), t["max"], attacker)
        leader_fell = before_leader > 0 and not leader_hp
        if dead:
            send_unit_live(s, uid, dead)
            log.info("troop %d: units %s down, hp %d", uid, dead, troop_hp)
        if attacker == 0 and uid != 0 and (dead or leader_fell):
            kill_count(s, len(dead) + bool(leader_fell))
        if leader_fell:
            log.info("troop %d: its leader is down", uid)
        if on_down is not None and troop_hp == 0 and (t["hero"] or ((dead or leader_fell) and not leader_hp)):
            s.data.setdefault("killed_by", {})[uid] = attacker     # this hit felled it
            on_down(s, uid)                             # wiped: units and leader (the hero: one hp for the troop)
        statuses.after_hit(s, uid, dead)                # finisher points, the finish status, a fallen troop's statuses
        if not t["hero"]:
            start_np_regen(s, uid)                      # its HP_RECOVERY, when its row has one (M2)
        if t["hero"]:
            if uid == 0 and dealt > 0:
                gain_stacks(s, "hit")                   # Iron Wall's fury for a hit taken
                from . import procs                     # gear / set procs (census HERO G11): a hit taken, and
                procs.roll(s, "WHEN_ATTACKED", attacker)      # a guarded one's
                if any(fl & FLAG_GUARD for fl in words.values()):
                    procs.roll(s, "BLOCK", attacker)
            start_regen(s)
    if drained:
        bloodsuck(s, attacker, drained, send_troop_hp)
    if attacker == 0 and any(uid != 0 for uid, _ in tally):
        gain_stacks(s, "attack")                        # the runes, rampage: once for a hit report that landed
        from . import procs
        procs.roll(s, "EACH_ATTACK", next(uid for uid, _ in tally if uid != 0))
    numbers = [n for n in numbers if mine or in_sight(s, n[0])]
    if numbers:
        w = Writer(S2C_DAMAGE_NUMBERS).u8(0).u16(len(numbers))
        for uid, hits in numbers:
            w.u16(uid).u16(len(hits))
            for idx, dmg, fl in hits:
                w.u16(idx).u8(0).u8(fl).u32(dmg)
        s.send(w)
    if tally:
        from .game import pack_value
        w = Writer(S2C_DAMAGE_TALLY).u16(len(tally))
        for uid, dealt in tally:
            b = bytearray(4)
            pack_value(b, 0, dealt)
            w.raw(bytes(b)).u16(uid).u16(attacker)
        s.send(w)
    return dict(tally)

"""The status engine (planning/wiring/HERO-CONTROLS-WIRING.md K1-K4, K7, K8, R7; BATTLE-WIRING.md B36, B42, B44, B54,
B55). Statuses exist only when the server sends them (0x5074, ended by 0x5078; BATTLE.md finding 1) and the client runs
no damage, so the server keeps what each troop holds and applies what the tables say:
  abilitycastinfo %Improvement   (COMMON, the cast's level) StatusEffectN with Object SELF / ENEMY / ALLY, TimesType,
                                 LevelN, ProbabilityN (per mille), TargetBranchN (a row of abilitytypeinfo %TroopBranch:
                                 the target's branch column holds "O"; row 39 생명체 = every living branch) and
                                 TargetRaceN (%Race likewise); RemoveStatusEffectGroupId1/2
  abilitytypeinfo %Function      REMOVE_STATUSEFFECTGROUP(_NODMG) (ParamValue2 = the group), ADD_FINISH_STATE (91:
                                 "31, 1") and FINISH_KILL (90, 92, 93: kill a target holding status 31)
  statuseffectinfo               %Basic Group_1..3; %Improvement Duration (none: held), AddStatusEffect1/2 (+ level),
                                 RemoveStatusEffectGroupId1/2 (on apply, from the holder); %Forbidden Invincibility and
                                 %Function TROOP_INVINCIBLE_DPS (6321, the escape's: the server's hits skip the troop)
  nptrooptable                   FINISH_HP_RATE, FINISH_STATUSEFFECT_ID / _LV (6 COMMON_FINISH, 32 on tutorial bosses),
                                 FINISH_DEAD_PROC (5075 / 5078: buffs for the executioner); %Skill ACTIVESKILLnnLV
The client's E key offers the execution on a unit holding a group-11 status and no group-12 one (HERO-CONTROLS-WIRING
F1), the groggy attack on one holding group 9. A whole-troop 0x5074 reaches every unit (F6).
Ours: the bookkeeping; a held status is sent with duration 0xffff (a CHANT ability's own status keeps
combat.STATUS_HOLD_S and ends with the chant); TimesType ONCE / TOTAL_ONCE / NODAMAGE_TOTAL_ONCE on the first execute of
a cast, EACH and "-" on every one (renewing the clock); the sides by the zone TeamNum; LEADER targets are the whole
troop (no NP leaders spawn yet, A3); group removal on the caster and the targets; FINISH_HP_RATE read as parts per ten
thousand of the troop's hp; the finisher points per kill (FP_PER_UNIT)."""
import functools, math, random, struct, time

from . import combat, net, tables
from .net import log
from .obf import T1
from .packet import Writer

NO_CASTER = 0xffff              # 0x5074's caster field for none (the finish status of a weakened troop)
HOLD = 0xffff                   # ours: the duration sent for a status held until removed (the client's reading of 0 is
                                # unknown)
ONCE = ("ONCE", "TOTAL_ONCE", "NODAMAGE_TOTAL_ONCE")   # TimesType applied on a cast's first execute only
GROUP_FINISH, GROUP_FINISH_STATE = 11, 12              # COMMON_FINISH (6, 32), COMMON_FINISH_STATE (31)
DEMORALIZE = 10202              # status ABILITY_NPT_LEADER_DEATH (ATTACK_PHYSICAL -30, 10 s; W155); its ability is on no
                                # list, so nothing casts it (commander_down, TROOPS T8.7); the tests use it as a status
# Finisher points: the client shows an FP orb flying from each non-leader unit that dies in a troop fighting the hero
# while FP is below its maximum (0x140d0b450 from the unit-death path 0x140a0af10) and holds the shown value back while
# orbs fly (SetFP 0x140b41160 -> 0x140d0b9c0): a gain per unit. No table gives the amount (W154 "kill troops /
# commanders ... at 1000 the finishing attack is available"); both amounts are ours.
FP_PER_UNIT = 25                # ours: a full bar (herotable %ApSp FP_Max 1000) after 40 units
FP_PER_COMMANDER = 250          # ours (BATTLE-WIRING B36): a commander's troop wiped (no leader unit spawns yet, A3)
C2S_STATUS_INFO = 0x10e3        # no body: GameStateTown::OnEnter 0x140e82780 (after 0x3746) and GameStateWorldMap::OnEnter
                                # 0x140d363d0 ask for the running statuses (planning/client/world_travel.md §2 0x10e3)
S2C_STATUS_INFO = 0x10e4        # CommonSubMainHUD::Packet_ResStatusEffectInfo 0x140e0fc80: u32 character id (the local
                                # player when it equals common+0xd4), then reader 0x140e145a0: u16 n, n x 9 plain bytes:
                                # u8 kind, u16 seconds left (0 removes), u8 level, u32 status, u8 flag. An unknown status
                                # asserts; one whose row +0x34 is 0 ends the list
HUD_KIND, HUD_FLAG = 0, 1       # the entry's list: of the eight (0x140e0e2f0 GetList(kind, flag)) the client reads only
                                # (0, 1), from 0x140767db9 and 0x14076d3fa (the hero's HUD)


def num(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


@functools.cache
def _cast_rows():
    out = {}
    for r in tables.sections("abilitycastinfo")["Improvement"]:
        if r.get("SpotFilter") == "COMMON" and r["AbilityId"].isdigit():
            out.setdefault(int(r["AbilityId"]), {}).setdefault(r.get("Level"), r)
    return out


def cast_row(ability, level=1):
    """abilitycastinfo %Improvement (COMMON) of an ability at a level; its first row when that level has none."""
    rows = _cast_rows().get(int(ability), {})
    return rows.get(str(level)) or next(iter(rows.values()), None)


@functools.cache
def _functions():
    out = {}
    for r in tables.sections("abilitytypeinfo")["Function"]:
        if r["AbilityId"].isdigit():
            out.setdefault(int(r["AbilityId"]), []).append(r)
    return out


def functions(ability, level, kind):
    """[[ParamValue1..5]] of an ability's abilitytypeinfo %Function rows of one type at a level (else level 1)."""
    rows = [r for r in _functions().get(int(ability), ()) if r["FunctionType"] == kind]
    at = [r for r in rows if r.get("Level") == str(level)] or [r for r in rows if r.get("Level") == "1"]
    return [[r.get(f"ParamValue{i}", "-") for i in range(1, 6)] for r in at]


@functools.cache
def _basic():
    return {int(r["AbilityId"]): r for r in tables.sections("abilitytypeinfo")["Basic"] if r["AbilityId"].isdigit()}


@functools.cache
def automatic():
    """The passives: abilities of abilitytypeinfo %Basic Category AUTOMATIC (68-70, 7000-7003, 7020-7023 ...)."""
    return frozenset(a for a, r in _basic().items() if r.get("Category") == "AUTOMATIC")


@functools.cache
def _improvements():
    return {(int(r["Id"]), int(r["Level"])): r for r in tables.sections("statuseffectinfo")["Improvement"]
            if r["Id"].isdigit() and r["Level"].isdigit()}


def improvement(status, level):
    """statuseffectinfo %Improvement of a status level (its level-1 row when that level has none)."""
    imp = _improvements()
    return imp.get((int(status), int(level))) or imp.get((int(status), 1)) or {}


@functools.cache
def _status_basic():
    return {r["Id"]: r for r in tables.sections("statuseffectinfo")["Basic"]}


@functools.cache
def groups(status):
    """statuseffectinfo %Basic Group_1..3 of a status."""
    row = _status_basic().get(str(status), {})
    return frozenset(int(row[k]) for k in ("Group_1", "Group_2", "Group_3") if str(row.get(k, "")).isdigit())


@functools.cache
def _overlaps():
    return {int(r["StatusEffectCategory"]): max(1, num(r.get("OverlapCount"), 1))
            for r in tables.sections("statuseffectinfo")["Category"] if r["StatusEffectCategory"].isdigit()}


@functools.cache
def category(status):
    """(Category, CategoryLevel) of a status's %Basic row, or None: 330 of 3,015 statuses carry one of the 107
    %Category rows (0 사용안함 "unused" and "-" are none). The "same effect" class of the stacking rule (A11): 57-61 the
    speed-reload buffs (7 INC_ATTACK, levels 1-5), 62-66 / 6220 / 6528 / 919990-2 ... (8 INC_ATTACK_PHYSICAL), 3 / 87 /
    94 the stuns (1), 70-74 the finish buffs (27, all level 5). %Group (Group_1..3) is not it: those are the removal
    and function handles (10 COMMON_GUARD, 11 COMMON_FINISH, 100-108 GROUP_TEST_xx shared by unlike buffs)."""
    row = _status_basic().get(str(status), {})
    cat = num(row.get("Category"))
    return (cat, num(row.get("CategoryLevel"))) if cat > 0 else None


def overlap(s, uid, status, level, spare=()):
    """The stacking rule for a status about to go on troop uid (A11; HANGAME-DEVNOTES §3.2 [O 2010]: a buff "does not
    stack with other abilities of the same effect; only the stronger one applies"): None when it may not go on (a
    stronger one of its effect is held), else the held statuses it replaces. Same effect = the same %Basic Category
    [T], up to its %Category OverlapCount at once [T] (1 on 106 of the 107 categories, 3 on 106 Test_cat_D); the
    stronger = the higher CategoryLevel [T column; the reading is ours], at an equal level the newer replaces the
    oldest (ours; BATTLE-WIRING B50's "replaces the oldest"). A status already held at a higher level keeps it (the
    same effect). spare: statuses the same cast just put, which it does not displace (ours: the fire elixir 110004
    puts SELF 1000038, the hero's version, and ALLY 1000039, the troops' version, both of category 146; on the hero
    his own stays). The client has no such rule (0x5074 / 0x5078 only, B50), so the server decides what it holds and
    shows."""
    held = holding(s, uid)
    if status in held and held[status]["level"] > level:
        return None
    cat = category(status)
    if cat is None:
        return []
    same = [(category(st)[1], i, st) for i, st in enumerate(held) if st != status and (category(st) or (0,))[0] == cat[0]]
    extra = len(same) + 1 - _overlaps().get(cat[0], 1)
    if extra <= 0:
        return []
    weakest = sorted(same)[:extra]
    if any(lv > cat[1] or st in spare for lv, _, st in weakest):
        return None
    return [st for _, _, st in weakest]


@functools.cache
def stack_count(status):
    """How many times a status stacks on its holder (census H5): statuseffectinfo %Basic Count (3 on 117 statuses, 4 on
    8, 2 on 4, 5 on 2: the raid's Demoralised 1027 / 1028, the tactics buffs 6294-6310, the Berserker's Dark Energy 6291
    and Fire Twister 6293); 1 elsewhere. A re-application at the same level adds a stack (the clock restarts), up to the
    count; each stack counts its traits (combat.status_bonus) and its ticks (combat.dot_hit). The client reads no Count
    (its %Basic reader 0x14197ad10 takes 15 columns) and shows one icon; the reading is ours [I]."""
    return max(1, num(_status_basic().get(str(status), {}).get("Count"), 1))


def ground(status):
    """A GROUND-target status (%Basic Target, 168; Isabella's 363 -> 3326 / 3327): an area on the ground whose events
    the client reports (0x5075, on_area_apply), no troop's status."""
    return _status_basic().get(str(status), {}).get("Target") == "GROUND"


@functools.cache
def _invincible():
    se = tables.sections("statuseffectinfo")
    ids = frozenset(num(r["Id"]) for r in se["Forbidden"] if r.get("Invincibility") == "True")
    levels = frozenset((num(r["Id"]), num(r["Level"])) for r in se["Function"]
                       if r["FunctionType"] == "TROOP_INVINCIBLE_DPS")
    return ids, levels


def removal(row, key="RemoveStatusEffectGroupId"):
    return frozenset(int(row[f"{key}{i}"]) for i in (1, 2) if str(row.get(f"{key}{i}", "")).isdigit())


# --- immunities (BATTLE-WIRING §3.4): only the original server decided them. The client's %Basic reader 0x14197ad10
# takes 15 of the 31 columns and never Immune_Type1..6, its 0x5074 path puts whatever it is sent, and a status's traits
# reach it only for speed (0x1407bc0c0 -> 0x140a04c90: ATTACK_SPEED, MAX_MOVE_SPEED) [R]. So the tables are the spec [T]

META_IMMUNITIES = (("M_IMMUNE_STATUSEFFECT", None), ("M_IMMUNE_DEBUFF", "IMMUNE_DEBUFF"))
# ours [I], by the names: two holder traits no Immune_Type names (M_IMMUNE_DEBUFF: none of 3,015 statuses;
# M_IMMUNE_STATUSEFFECT: one, 3000011) though the tables give them at 1000 (42029 on walls and towers, the petrify
# 70361, the escape 6321, the revive's 33 / 34): the first keeps off every status that names an immunity, the second
# every one that names IMMUNE_DEBUFF


@functools.cache
def immune_types(status):
    """The traits that keep a status off its target: statuseffectinfo %Basic Immune_Type1..6 (E_TraitTypes; the
    IMMUNE ones: the data's ATTACK_PHYSICAL on 6425 / 6531 / 102310 and M_DEFENCE_PHYSICAL on 946330 are none), then
    META_IMMUNITIES. The finish and K-down statuses (6, 31, 32, 3000209, 3000210) name none: an immune boss still gets
    them."""
    row = _status_basic().get(str(status), {})
    named = tuple(dict.fromkeys(t for t in (str(row.get(f"Immune_Type{i}", "-")) for i in range(1, 7)) if "IMMUNE" in t))
    return named + tuple(meta for meta, needs in META_IMMUNITIES
                         if named and meta not in named and (needs is None or needs in named))


def _passive_immunity(abilities, have):
    """Add the IMMUNE traits of held passives ({ability: level}; abilitytypeinfo Category AUTOMATIC) to have: their
    abilitycastinfo %Improvement row at the level, TraitObjectN SELF, TraitOperationN ADD, TraitValueN per mille
    (42000-42029: 200 / 400 / 600 / 800 / 1000 at levels 1-5, 500 at 6), TraitTargetN ALL or TROOP (an NP leader's
    42102 / 42108 are LEADER: him alone, and the engine keeps statuses by troop, so they keep nothing off it)."""
    for ability, level in (abilities or {}).items():
        row = cast_row(ability, level) if ability in automatic() else None
        for i in (1, 2) if row else ():
            name = row.get(f"TraitType{i}")
            if (name in have and row.get(f"TraitObject{i}") == "SELF" and row.get(f"TraitOperation{i}") == "ADD"
                    and row.get(f"TraitTarget{i}") in ("ALL", "TROOP")):
                have[name] += num(row.get(f"TraitValue{i}"))


def immunity(s, uid, names):
    """{trait: per mille} of the named traits troop uid holds, the zero ones left out. The hero: hero.stats (his gear's
    options and his kit's passives); an NP or deck troop: its record's passives and learned AUTOMATIC skills, and its NP
    leader's (_passive_immunity); either: its held statuses' ADD traits (statuseffectinfo %Improvement, combat.
    status_bonus: the guard 341 IMMUNE_DEBUFF 1000 on the hero, the escape 6321 M_IMMUNE_DEBUFF 1000)."""
    have = dict.fromkeys(names, 0)
    if uid == 0:
        c = _hero_char(s)
        if c is not None and "class" in c:
            from . import hero
            stats = hero.stats(c["class"], c.get("level", 1), hero.worn_codes(c), hero.worn_enchants(c),
                               s.data.get("kit"))
            for name in have:
                have[name] += stats.get(name, 0)
    else:
        battle = s.data.get("battle")
        t = (battle.troops.get(uid) if battle else None) or {}
        own, lead = t.get("c"), t.get("leader_c")
        for rec in (own, lead if lead is not own else None):     # Battle.add_np's leader_c falls back to the troop's
            if rec:
                _passive_immunity({**(rec.get("skills") or {}), **(rec.get("passives") or {})}, have)
    held = {st: r["level"] for st, r in holding(s, uid).items()}
    for name in have:
        have[name] += combat.status_bonus(held, name, leader=uid == 0)[1]
    return {name: round(v) for name, v in have.items() if v > 0}


def resisted(s, uid, status):
    """(trait, per mille) when troop uid keeps the status off, else None: for each of its immune_types the target
    holds, in the column order, a draw of 1000 below the value (1000 and above: always). The per mille reading is the
    client's own for its trait chances (PROBABILITY_COUNTER / _GUARD 0x14079b000, _DODGE 0x14079b060: rand % 1000 <
    value [R]) and the passives' steps to 1000 at level 5 [T]; a draw per trait is ours [I]."""
    names = immune_types(status)
    for name, value in immunity(s, uid, names).items() if names else ():
        if value >= 1000 or random.randrange(1000) < value:
            return name, value
    return None


# --- what a troop holds (K1) ---

def holding(s, uid):
    """{status: {level, until, groups, caster}} a troop holds; a record past its clock is dropped (a session without
    timers; with them, the expiry's 0x5078 drops it, combat.send_status_end)."""
    held = s.data.setdefault("statuses", {}).get(uid)
    if not held:
        return {}
    now = time.monotonic()
    for st in [st for st, r in held.items() if r["until"] is not None and r["until"] <= now]:
        held.pop(st)
    return held


def has_group(s, uid, group):
    return any(group in r["groups"] for r in holding(s, uid).values())


def forget(s, uid):
    """A fallen troop's statuses go with it (no packet: the client drops them itself, BATTLE-WIRING B44), and its
    fight with the player's side (fights_player): a troop that comes back under its uid (a field respawn) starts unfought."""
    s.data.get("statuses", {}).pop(uid, None)
    s.data.get("fought_player", set()).discard(uid)


def invincible(s, uid):
    """The troop holds an invincible status (statuseffectinfo %Forbidden Invincibility True, or TROOP_INVINCIBLE_DPS at
    its level: 6321 ABILITY_ESCAPE from the escapes 14, 1178, 310, 614, 914, 1253 and the get-up counter 94). The
    client has an empty case for the function (BATTLE.md §6): the server's hits skip such a troop (K4)."""
    ids, levels = _invincible()
    return any(st in ids or (st, r["level"]) in levels for st, r in holding(s, uid).items())


def alive(s, uid):
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t:
        return True                     # a troop the server does not track (the client knows it)
    return t["hp"] > 0 and not t.get("down") if t["hero"] else any(t["units"]) or t.get("leader", 0) > 0


def _bump(s, uid, status):
    """Stale the expiry clock of an earlier application (combat.expire_status keeps a generation per status)."""
    gens = s.data.setdefault("status_gen", {})
    gens[(uid, status)] = gens.get((uid, status), 0) + 1


def apply(s, uids, status, level, caster=0, chant=None, depth=0, event=0, spare=()):
    """Put a status on troops: one 0x5074 listing them all, kept in s.data["statuses"]. A timed one ends after its
    Duration (combat.expire_status) and restarts its clock when applied again; one with no Duration is held until a
    group removal or death (sent with HOLD, not sent again while held), or, for a CHANT ability's own status (the guards
    62, 304, 604, 909, 1201), until the chant ends (combat.STATUS_HOLD_S and a chant record, as before). On apply the
    status removes the groups its %Improvement names from its holder and adds its AddStatusEffect1/2. event: the area
    event that asked (0x5075), echoed in the 0x5074. A target immune to it (resisted, BATTLE-WIRING §3.4) does not get
    it: nothing is sent for it, the journal says "immune". A status of an effect the troop already holds stronger does
    not go on; one that is stronger replaces the weaker (0x5078 first; overlap, A11)."""
    status, level = int(status), max(1, int(level))
    imp = improvement(status, level)
    duration = num(imp.get("Duration"))
    gone = removal(imp)
    top = stack_count(status)
    to, stacks = [], {}
    for uid in dict.fromkeys(uids):
        held = holding(s, uid).get(status)
        more = held is not None and held["level"] == level and held.get("stacks", 1) < top
        if not alive(s, uid) or (not duration and held and held["level"] == level and not more):
            continue
        stacks[uid] = held.get("stacks", 1) + 1 if more else 1
        why = resisted(s, uid, status)
        if why is not None:
            log.info("troop %d: status %d (level %d) kept off: immune (%s %d)", uid, status, level, *why)
            net.journal("immune", spot=s.data.get("spot"), troop=uid, status=status, level=level,
                        name=_status_basic().get(str(status), {}).get("StringId"), trait=why[0], value=why[1],
                        caster=caster)
            continue
        weaker = overlap(s, uid, status, level, spare)
        if weaker is None:
            log.info("troop %d: status %d (level %d) kept out by a stronger one of its effect", uid, status, level)
            continue
        for st in weaker:
            end(s, uid, st)
            log.info("troop %d: status %d replaced by %d (same effect)", uid, st, status)
        if gone:
            remove_groups(s, uid, gone, keep=status)
        to.append(uid)
    if not to:
        return []
    combat.send_status(s, to, status, level, duration or (combat.STATUS_HOLD_S if chant is not None else HOLD), caster,
                       event)
    now = time.monotonic()
    until = now + duration if duration else None
    for uid in to:                                  # "since": when it went on (a guard's TRAITRATE_PROGRESS, combat)
        s.data.setdefault("statuses", {}).setdefault(uid, {})[status] = {
            "level": level, "until": until, "groups": groups(status), "caster": caster, "since": now,
            "stacks": stacks.get(uid, 1)}
        if duration:
            combat.expire_status(s, uid, status, duration)
            if uid == 0:
                keep(s, status, level, duration)
            continue
        _bump(s, uid, status)
        if chant is not None:
            chants = s.data.setdefault("chant_statuses", {}).setdefault((chant, uid), [])
            if status not in chants:
                chants.append(status)
    for uid in to:                                  # damage / healing over time (combat.start_dot, census H13), a
        combat.start_dot(s, uid, status, level, caster)     # shield's pool (combat.start_shield, H14)
        combat.start_shield(s, uid, status, level)
    log.info("troops %s: status %d (level %d, %s) from %d", to, status, level,
             f"{duration} s" if duration else "held", caster)
    for i in (1, 2):
        add = str(imp.get(f"AddStatusEffect{i}", "-"))
        if add.isdigit() and int(add) > 0 and depth < 3:          # 6201 -> 6203, 6200 -> 620202, 700010 -> 5
            apply(s, to, int(add), num(imp.get(f"AddStatusEffectLevel{i}"), 1), caster, chant, depth + 1,
                  spare=set(spare) | {status})
    return to


def end(s, uid, status):
    """End a held status now (0x5078; the record goes in combat.send_status_end)."""
    _bump(s, uid, status)
    if uid == 0:
        (_hero_char(s) or {}).get("timed_statuses", {}).pop(str(status), None)
    combat.send_status_end(s, uid, status)


def remove_groups(s, uid, gone, keep=None):
    """End every status of the troop that belongs to one of the groups (K3, BATTLE-WIRING B44 / B55)."""
    for st, r in list(holding(s, uid).items()):
        if st != keep and r["groups"] & gone:
            end(s, uid, st)
            log.info("troop %d: status %d removed (groups %s)", uid, st, sorted(r["groups"] & gone))


# --- what the client asks (planning/client/combat.md gaps 3 and 6; never seen live) ---

C2S_AREA_APPLY = 0x5075         # StatusEffectEventManager::Request 0x140c9f350 / ::RequestTroop 0x140c9f680 when the
                                # event's +0x26 != -1 (builder 0x1404fbda0): an aura or ground effect asks for its
                                # status on the troops in its area. u8 level (event +8; [I]: the byte beside the status
                                # +4, as the {status, level} pair 0x5074 / 0x5078 carry), u16 event id (+0x26), u32
                                # status (+4); u16 k x u16 (the event's id list, 0x1404fde50); u16 n targets (0x1408201e0)
C2S_REMOVE = 0x5077             # ClientStatusEffectRemover slot 5 0x140869200 (level 1, reason = remover +0x20) and
                                # 0x1407ba3b0 (reason 3) (builder 0x1404fc5e0): u8 level, u32 status, u8 reason; u16 n
                                # targets (0x14081ff90). Answered by 0x5078 (0x140d1b3b0): the records, the same 6 bytes


def _targets(b, off, whole):
    """The u16 n target records of 0x5075 / 0x5077 at b[off:]: a flag byte, u16 plain troop uid, then, when whole(flag)
    is false, u16 m + m x u16 units. [(uid, units, or None for the whole troop)]; None when the body is short."""
    if len(b) < off + 2:
        return None
    out = []
    n, off = struct.unpack_from("<H", b, off)[0], off + 2
    for _ in range(n):
        if len(b) < off + 3:
            return None
        flag, uid, off, units = b[off], struct.unpack_from("<H", b, off + 1)[0], off + 3, None
        if not whole(flag):
            m = struct.unpack_from("<H", b, off)[0] if len(b) >= off + 2 else None
            if m is None or len(b) < off + 2 + 2 * m:
                return None
            units, off = list(struct.unpack_from(f"<{m}H", b, off + 2)), off + 2 + 2 * m
        out.append((uid, units))
    return out


def on_area_apply(s, pkt):
    """0x5075: the event's status on each listed troop, through apply (one 0x5074, the status's Duration, the event id
    echoed, no caster). A record's flag is the troop's share of the area x 255 (at least 1), 0 when a unit list
    (unit << 5 | code) follows; ours: the status goes on the whole troop either way (the engine keeps troops)."""
    b = pkt.rest()
    head = struct.unpack_from("<BHIH", b) if len(b) >= 9 else None
    recs = head and _targets(b, 9 + 2 * head[3], lambda share: share != 0)
    if recs is None:
        log.warning("area status event not understood: %s", b.hex())
        return
    level, event, status, _ = head
    log.info("area event %d: status %d (level %d) asked for %s", event, status, level, [u for u, _ in recs])
    apply(s, [u for u, _ in recs], status, level, caster=NO_CASTER, event=event)


def on_remove(s, pkt):
    """0x5077: the status goes from the listed troops (a whole-troop record also from the engine's record and clock;
    a unit list leaves the rest of the troop holding it), answered by one 0x5078 with the request's records and its
    6 bytes. A record's flag is T2[whole + 2 x the byte before] (the client's writer), so T1[flag] & 1 = whole."""
    b = pkt.rest()
    recs = _targets(b, 6, lambda flag: T1[flag] & 1)
    if recs is None:
        log.warning("status removal not understood: %s", b.hex())
        return
    status = struct.unpack_from("<I", b, 1)[0]
    w = Writer(combat.S2C_STATUS_END).u16(len(recs))
    for uid, units in recs:
        w.obool(units is None).u16(uid)
        if units is None:
            _bump(s, uid, status)
            s.data.get("statuses", {}).get(uid, {}).pop(status, None)
        else:
            w.u16(len(units))
            for u in units:
                w.u16(u)
    s.send(w.raw(b[0:6]))
    log.info("troops %s: status %d removed (the client asked, reason %d)", [u for u, _ in recs], status, b[5])


# --- who is who ---

def side(s, uid):
    """0 on the hero's side (troop 0, his deck troops and zone troops of the player's team), 1 otherwise (ours: the zone
    TeamNum; the test enemy and quest spawns carry no player team)."""
    from .game import PLAYER_TEAM
    if uid == 0 or uid in (s.data.get("deck") or {}):
        return 0
    t = s.data.get("zone_troops", {}).get(uid)
    return 0 if t is not None and t.get("TeamNum") == PLAYER_TEAM else 1


def players(s, uid):
    """The player's own: the hero (troop 0), his deck troops (game.deploy) and the troops handed to him (the plan's
    hand: game.count_as_players, the director's "hand" and the client's 0x50e6), not the allies of his team (Glen's
    forces)."""
    return uid == 0 or uid in (s.data.get("deck") or {}) or uid in (s.data.get("plan") or {}).get("hand", ())


def fights_player(s, uid):
    """Whether troop uid fights the player's side, the client's own test for a finisher orb (the unit-death path
    0x140a0af10 -> 0x140d0b450 spawns one for each non-leader unit whose troop lists the local hero's troop or another
    of the player's: troop +0x470, INVENTORY "Finisher points" [R]). The server cannot read that list; it stands for
    it by what it is told (ours): an engagement with one of the player's troops (0x5059, combat.on_engage) or a hit of
    one of them on it (combat.apply_hits), kept in s.data["fought_player"] until the troop falls (forget): a hate
    list outlives the engagement that filled it. Kill exp, the commander's SP and finisher points follow it
    (game.troop_down, units_down, commander_down; B7): an ally's kill of a troop the player never fought is the
    ally's alone."""
    return uid in s.data.get("fought_player", ())


def troop_row(s, uid):
    """The nptrooptable row of a zone troop (its difficulty variant), or None."""
    from . import zone
    t = s.data.get("zone_troops", {}).get(uid)
    return zone.np_troop(t["TroopTableID"]) if t else None


@functools.cache
def _troop_types():
    return {r["NPTroopType"]: r for r in tables.sections("nptrooptype")["System"]}


def troop_kind(s, uid):
    """(branch, race) of a troop: the hero's herotable %System TROOPBRANCH / RACE, an NP troop's nptrooptype %System
    BRANCH / RACE (through nptrooptable NPTroopType); None when unknown."""
    if uid == 0:
        from .hero import HERO_CODE
        c = s.data.get("char") or (s.data.get("account") or {}).get("characters", [{}])[0]
        row = next((r for r in tables.sections("herotable")["System"]
                    if "class" in c and r["CHARACTER_TYPE"] == HERO_CODE[c["class"]]), None)
        return (row["TROOPBRANCH"], row["RACE"]) if row else None
    row = troop_row(s, uid)
    kind = row and _troop_types().get(row.get("NPTroopType"))
    return (kind.get("BRANCH", ""), kind.get("RACE", "")) if kind else None


@functools.cache
def _filter_rows(section, key):
    return {r[key]: {k.upper(): v for k, v in r.items()} for r in tables.sections("abilitytypeinfo")[section]}


def fits(s, uid, branch, race):
    """TargetBranch / TargetRace: the troop's branch (race) column of that abilitytypeinfo %TroopBranch (%Race) row
    holds "O" (column names matched without case: DRUID_HERO / Druid_HERO); "-" or a troop of unknown kind passes."""
    kind = troop_kind(s, uid)
    if kind is None:
        return True
    for rid, section, key, value in ((branch, "TroopBranch", "BranchId", kind[0]), (race, "Race", "RaceId", kind[1])):
        row = _filter_rows(section, key).get(str(rid)) if str(rid).isdigit() else None
        if row is not None and row.get(str(value).upper()) != "O":
            return False
    return True


@functools.cache
def _np_skills(table, key):
    return {r[key]: r for r in tables.sections(table)["Skill"]}


def cast_level(s, ability, caster):
    """The level a cast runs at: the hero's held level (the kit); a deck troop's the tactics academy's (troops.
    skill_level, T5.3); an NP troop's nptrooptable (then its leader's npleadertable) %Skill ACTIVESKILLnnLV for that
    ability (a handed troop's too: its skills are its row's, no academy row names them); else 1."""
    if caster == 0:                             # a proc's skill runs at its gear's ProcSkillLevel (procs.roll)
        return s.data.get("kit", {}).get(ability) or s.data.get("proc_levels", {}).get(ability, 1)
    if caster in (s.data.get("deck") or {}):
        from . import troops
        return max(1, troops.skill_level(_hero_char(s), ability))
    t = s.data.get("zone_troops", {}).get(caster) or {}
    for table, key, tid in (("nptrooptable", "NPTROOP_ID", t.get("TroopTableID")),
                            ("npleadertable", "NPLEADER_ID", t.get("NPLeaderID"))):
        row = _np_skills(table, key).get(str(tid)) or {}
        for n in range(1, 17):
            if row.get(f"ACTIVESKILL{n:02d}") == str(ability):
                return max(1, num(row.get(f"ACTIVESKILL{n:02d}LV"), 1))
    return 1


# --- an ability's execute (K2, K3, K8) ---

def ability_statuses(ability, level=1):
    """[(status, level, object, times type, probability, target branch, target race)] of an ability's two status slots
    at a level (abilitycastinfo %Improvement, COMMON)."""
    row = cast_row(ability, level) or {}
    out = []
    for i in (1, 2):
        sid = str(row.get(f"StatusEffect{i}", "-"))
        if sid.isdigit() and int(sid) > 0:
            out.append((int(sid), max(1, num(row.get(f"Level{i}"), 1)), row.get(f"StatusEffectObject{i}"),
                        row.get(f"StatusEffectTimesType{i}", "-"), num(row.get(f"Probability{i}")),
                        row.get(f"TargetBranch{i}", "-"), row.get(f"TargetRace{i}", "-")))
    return out


def cast_statuses(s, ability, level, caster, others, first=True):
    """The statuses one execute of a cast puts: SELF on the caster, ENEMY on the listed troops of the other side, ALLY
    on the caster and the listed troops of its side, each rolled by its Probability and filtered by its TargetBranch /
    TargetRace; ONCE-type slots only on the first execute. On the hero's first execute also the CHECKSKILL statuses and
    the reload chain step (combat.checkskill_statuses, combat.chain_statuses). One 0x5074 per status."""
    mine = side(s, caster)
    plan = {}
    for st, lv, obj, times, prob, branch, race in ability_statuses(ability, level):
        if (times in ONCE and not first) or ground(st):
            continue
        if obj == "SELF":
            to = [caster]
        elif obj == "ENEMY":
            to = [u for u in others if side(s, u) != mine]
        elif obj == "ALLY":
            to = [caster] + [u for u in others if side(s, u) == mine]
        else:
            continue
        plan.setdefault((st, lv), []).extend(u for u in to if fits(s, u, branch, race)
                                             and (prob >= 1000 or random.randrange(1000) < prob))
    if caster == 0 and first:
        for st, lv, _ in (combat.checkskill_statuses(ability, s.data.get("kit", {}))
                          + combat.chain_statuses(s, ability)):
            plan.setdefault((st, lv), []).append(0)
    chant = ability if _basic().get(int(ability), {}).get("Branch") == "CHANT" else None
    put = set()                                         # this execute's statuses do not displace each other (overlap)
    for (st, lv), to in plan.items():
        if to:
            apply(s, to, st, lv, caster, chant if set(to) == {caster} else None, spare=put)
            put.add(st)


def process_flag(row, k):
    """Whether the k-th execute (0-based) of a cast puts its statuses (census F3, H2): abilitycastinfo %Improvement
    ProcessStatusEffect, one 0 / 1 a ProcessRate share ("1 1 1" on 108 three-execute rows, "0 0 0 1 0" on 106: its
    status 55 on the fourth execute alone, "0 1" on 48 two-execute rows: the second); past the list its last value; "-"
    or empty: every execute. A single "0" (520 rows, 423 of them passives, whose statuses go on at room start) puts none
    from an execute. The reading as a per-execute switch is ours [I], from the lists' alignment with ProcessRate."""
    flags = [x for x in str(row.get("ProcessStatusEffect", "")).split() if x in ("0", "1")]
    if not flags:
        return True
    return flags[min(k, len(flags) - 1)] == "1"


def on_execute(s, serial, ability, caster, targets, send_troop_hp=None, on_down=None):
    """A hit of a cast (C2S 0x5066, combat.on_ability_execute): ability = the cast's (None after its first execute, the
    cast is then found by its serial), caster = its troop (0 the hero, an NP uid for a 0x505f cast), targets = the
    execute's [(uid, units)]. In order: the targets in the finish state for ADD_FINISH_STATE (read before the removal),
    the group removals (abilitycastinfo RemoveStatusEffectGroupId1/2 and %Function REMOVE_STATUSEFFECTGROUP(_NODMG):
    14 -> 2, 94 -> 141, 737 -> 117 / 505, 738 -> 118 / 506, 1029 -> 127, 91 / 90 -> 11, 4 -> 9) on the caster and the
    targets, the statuses, then ADD_FINISH_STATE (91: 31 on a target holding group 11) and FINISH_KILL (90 / 92 / 93)."""
    runs = s.data.setdefault("cast_runs", {})
    if ability is not None and (serial not in runs or runs[serial]["ability"] != ability):
        runs[serial] = {"ability": ability, "caster": caster, "level": cast_level(s, ability, caster), "n": 0}
    run = runs.get(serial)
    if run is None:
        return
    k, first = run["n"], run["n"] == 0
    run["n"] += 1
    ability, caster, level = run["ability"], run["caster"], run["level"]
    if caster == 0 and first:
        combat.hero_activity(s)
    others = list(dict.fromkeys(uid for uid, _ in targets if uid != caster))
    row = cast_row(ability, level) or {}
    adds = functions(ability, level, "ADD_FINISH_STATE") if first else []
    finishing = [u for u in others if has_group(s, u, GROUP_FINISH)] if adds else []
    gone = removal(row) | frozenset(num(p[1]) for kind in ("REMOVE_STATUSEFFECTGROUP",
                                                           "REMOVE_STATUSEFFECTGROUP_NODMG")
                                    for p in functions(ability, level, kind) if str(p[1]).isdigit()) if first else ()
    if gone:
        for uid in [caster] + others:
            remove_groups(s, uid, gone)
    if process_flag(row, k):                        # the statuses: the executes ProcessStatusEffect marks (F3)
        cast_statuses(s, ability, level, caster, others, not run.get("put"))
        run["put"] = True
    if not first:
        return
    for p in adds:
        if str(p[0]).isdigit():
            apply(s, finishing, int(p[0]), num(p[1], 1), caster)
    for p in functions(ability, level, "FINISH_KILL"):
        for uid in others:
            if str(p[0]).isdigit() and int(p[0]) in holding(s, uid):
                execution(s, uid, int(p[0]), send_troop_hp, on_down, killer=caster)


# --- the finish chain and finisher points (K7, K8) ---

def execution(s, uid, status, send_troop_hp=None, on_down=None, killer=0):
    """FINISH_KILL on a target in the finish state (status 31): every unit to 0 (0x505d, 0x505b for all), the troop's
    fall (on_down: kill feed, exp, quests, loot, waves as for any kill; killer = the executing caster), the finish
    state ends (0x5078), then its row's FINISH_DEAD_PROC ability runs as a cast of the hero (5075: ALLY 6410 / 6411
    attack buffs, 30 s). The kill by the function rather than by a damage number is ours (the function's name says
    so)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t or t["hero"]:
        return
    fell = [i for i, hp in enumerate(t["units"]) if hp > 0]
    if not fell and not t.get("leader"):
        return
    for i in fell:
        t["units"][i] = 0
    if t.get("leader"):
        t["leader"] = 0                                  # 0x505d without the leader's hp: he falls too
    row = troop_row(s, uid) or {}
    if send_troop_hp is not None:
        send_troop_hp(s, uid, 0)
    combat.send_unit_live(s, uid, fell)
    if players(s, killer):
        s.data.setdefault("fought_player", set()).add(uid)
    units_down(s, uid, len(fell))
    log.info("troop %d executed (%d units)", uid, len(fell))
    from . import director
    director.on_finish(s, uid)                           # the mission table's finisher lesson, before the fall
    if on_down is not None:
        s.data.setdefault("killed_by", {})[uid] = killer
        on_down(s, uid)
    end(s, uid, status)
    forget(s, uid)
    proc = str(row.get("FINISH_DEAD_PROC", "-"))
    if proc.isdigit():
        cast_statuses(s, int(proc), 1, 0, [])


def after_hit(s, uid, dead=()):
    """After hits on a troop (combat.apply_hits): finisher points for its units that fell, the finish status once its hp
    is at its row's FINISH_HP_RATE (weakened), and a fallen troop's statuses are forgotten."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    if not t:
        return
    if t["hero"]:
        if t["hp"] <= 0:
            forget(s, uid)
            caster_fell(s, uid)
        return
    if dead:
        units_down(s, uid, len(dead))
    hp = sum(t["units"]) + t.get("leader", 0)
    if hp <= 0:
        forget(s, uid)
        caster_fell(s, uid)
        return
    weakened(s, uid, t, hp)


@functools.cache
def _caster_bound():
    """statuseffectinfo %Basic RemoveWhenCasterDie True: 7 boss debuffs (the Behemoth's and the Colossus's fire fields,
    Pergos's fire-prison stun 30146, the Yeti's frostbite 35030 ...)."""
    return frozenset(num(r["Id"]) for r in tables.sections("statuseffectinfo")["Basic"]
                     if r.get("RemoveWhenCasterDie") == "True")


def caster_fell(s, uid):
    """Troop uid fell: the statuses it put on others that end with their caster (_caster_bound) end (0x5078; census
    H9)."""
    bound = _caster_bound()
    for other, recs in list((s.data.get("statuses") or {}).items()):
        for st, rec in list(recs.items()):
            if st in bound and isinstance(rec, dict) and rec.get("caster") == uid:
                end(s, other, st)


def weakened(s, uid, t, hp):
    """An enemy troop at hp <= max x FINISH_HP_RATE / 10000 (1000 on 12,177 nptrooptable rows: 10 %, the Troll's
    vitality tutorial, W152; 0 on 528: never) that holds no group-11 or group-12 status gets its FINISH_STATUSEFFECT_ID
    at FINISH_STATUSEFFECT_LV (6 COMMON_FINISH 6 s; 32 COMMON_FINISH_TU on tutorial bosses) on the whole troop: the E
    prompt's condition. Expired unused, the next hit puts it again. The rate's unit is ours."""
    row = troop_row(s, uid) or {}
    rate, sid, top = num(row.get("FINISH_HP_RATE")), str(row.get("FINISH_STATUSEFFECT_ID", "-")), t.get("max")
    if rate <= 0 or not sid.isdigit() or not top or hp * 10000 > top * rate or side(s, uid) == 0:
        return
    if has_group(s, uid, GROUP_FINISH) or has_group(s, uid, GROUP_FINISH_STATE):
        return
    apply(s, [uid], int(sid), num(row.get("FINISH_STATUSEFFECT_LV"), 1), NO_CASTER)


def units_down(s, uid, n):
    """Units of an enemy troop fell: FP_PER_UNIT each (the client's orbs, one per unit), when the troop fights the
    player's side (fights_player: the orbs' own condition)."""
    if n > 0 and side(s, uid) != 0 and fights_player(s, uid):
        gain_fp(s, FP_PER_UNIT * n)


def gain_fp(s, amount):
    """Finisher points up to herotable %ApSp FP_Max (1000); the value goes out as stat 82 FP_CURRENT (0x5138)."""
    pools = s.data.get("pools")
    if not pools or amount <= 0 or pools.get("fp", 0) >= pools.get("fp_max", 0):
        return False
    pools["fp"] = min(pools["fp_max"], pools.get("fp", 0) + amount)
    combat.send_stats(s, {combat.STAT_FP: pools["fp"]})
    return True


def commander_down(s, uid, t, credited=True):
    """A wiped enemy zone troop that carries an NPLeaderID is a commander's troop (ours until leaders spawn, A3;
    BATTLE-WIRING B36): SP by its npleadertype %System Death_Give_Sp (28 on all 280 rows; W156 "+28 SP per commander
    killed"), FP_PER_COMMANDER. Returns the SP (the 0x50da "Enemy Commander Defeated" banner's). credited False (an
    ally's kill of a troop the player never fought, fights_player): no SP and no FP. The leader's fall weakens his
    troop through its own list, not here (TROOPS T8.7): 300127 NP리더버프_제거스킬 (ACTIVESKILL of 2,191 nptrooptable
    rows, 103080's first) has the %AiCondition OneTimeEvent DEATH_SELF_LEADER, so the client's AI casts it when the
    leader dies (RunAutoSkill) and its execute takes off the leaders' buffs (REMOVE_STATUSEFFECTGROUP 137) and puts
    300110 (HP_MAX -50, ATTACK_PHYSICAL -50 x level, 30 s) on his allies (on_execute). 10202 NPT_LEADER_DEATH, which
    this cast on his force (with its HP_BASEUNIT -30 % trait, COMBAT H19) until the troop hunt of 2026-10-01, has the
    same event but sits on no nptrooptable or npleadertable list: nothing in the data casts it."""
    leader = t.get("NPLeaderID")
    if leader in (None, -100) or side(s, uid) == 0:
        return 0
    row = next((r for r in tables.sections("npleadertable")["Contents"] if r["NPLEADER_ID"] == str(leader)), None)
    if row is None:
        return 0
    kind = next((r for r in tables.sections("npleadertype")["System"] if r["NPLeaderType"] == row["NPLeaderType"]), {})
    sp = num(kind.get("Death_Give_Sp")) if credited else 0
    if credited:
        combat.gain_sp(s, sp)
        gain_fp(s, FP_PER_COMMANDER)
    log.info("commander %s of troop %d down: SP +%d", leader, uid, sp)
    return sp


# --- room start (R7) ---

def passive_statuses(abilities):
    """[(status, level)] the passives among abilities ({ability: level}; AUTOMATIC ones) put on their holder: the SELF
    statuses of their abilitycastinfo %Improvement row at the level (held: Duration 0 on all 114 of the player troops'
    passives, e.g. 70148 -> 701480 Sharp Insight, 70150 -> 701500, 70196 -> 701960)."""
    return [(st, lv) for ability, level in sorted((abilities or {}).items()) if ability in automatic()
            for st, lv, obj, *_ in ability_statuses(ability, level) if obj == "SELF"]


CLIENT_TRAITS = ("MAX_MOVE_SPEED", "ATTACK_SPEED")      # the client runs these once the status exists (0x1407bc0c0 ->
                                                        # 0x140a04c90, its only trait types): nothing for the server


def passive_traits(abilities, level, unit="TROOP", live=True):
    """[(stat, value, percent)] the passives among abilities ({ability: level}) add to a holder at `level` (T1.11), for
    its units (unit "TROOP") or its leader ("LEADER"): the traits of their SELF statuses (passive_statuses;
    statuseffectinfo %Improvement TraitTarget ALL or unit: ADD / SUBTRACT Traitvalue_1 percent, Traitvalue_2 flat as
    combat.status_bonus reads them; ADD_TARGET_LEVEL and the like Traitvalue_2 x level, combat.LEVEL_FUNCTIONS) and their own
    SELF ADD trait columns (abilitycastinfo TraitObject / TraitTarget / TraitType / TraitValue, the hero's kind,
    hero.passive_traits: an NP troop's DEFENCE_PHYSICAL_RANGE). Left out: the IMMUNE traits (status.resisted reads
    them), the speed traits (CLIENT_TRAITS), and with live False a held status's traits the resolver reads itself (combat.RESOLVER_TRAITS) (the combat record's
    row: the resolver counts those from the held status itself)."""
    keep = lambda name, target: (target in ("ALL", unit) and name not in (None, "", "-") and "IMMUNE" not in name
                                 and name not in CLIENT_TRAITS)
    out = []
    for ability, lv in sorted((abilities or {}).items()):
        row = cast_row(ability, lv) if ability in automatic() else None
        for i in (1, 2) if row else ():
            name, value = row.get(f"TraitType{i}"), str(row.get(f"TraitValue{i}", "0"))
            if (row.get(f"TraitObject{i}") == "SELF" and row.get(f"TraitOperation{i}") == "ADD"
                    and keep(name, row.get(f"TraitTarget{i}")) and combat._f(value)):
                out.append((name, combat._f(value), value.endswith("%")))    # 20061: DEFENCE_PHYSICAL_RANGE "200%"
    return out + status_traits(passive_statuses(abilities), level, unit, live)


def status_traits(pairs, level, unit="TROOP", live=True):
    """[(stat, value, percent)] held statuses [(status, level)] add to a holder at `level`: their statuseffectinfo
    %Improvement TraitTarget ALL or unit traits as passive_traits reads a passive's (the same exclusions)."""
    keep = lambda name, target: (target in ("ALL", unit) and name not in (None, "", "-") and "IMMUNE" not in name
                                 and name not in CLIENT_TRAITS)
    out = []
    for st, lv in pairs:
        imp = improvement(st, lv)
        for j in ("01", "02"):
            name, fn = imp.get(f"TraitType{j}"), imp.get(f"FunctionType{j}")
            if not keep(name, imp.get(f"TraitTarget{j}")):
                continue
            p, f = combat._f(imp.get(f"Traitvalue{j}1")), combat._f(imp.get(f"Traitvalue{j}2"))
            if not live and name in combat.RESOLVER_TRAITS and (fn in ("ADD", "SUBTRACT") or fn in combat.LEVEL_FUNCTIONS):
                continue
            if fn in ("ADD", "SUBTRACT"):
                sign, times = (-1 if fn == "SUBTRACT" else 1), 1
            elif fn in combat.LEVEL_FUNCTIONS:
                sign, times = combat.LEVEL_FUNCTIONS[fn], level
            else:
                continue
            if combat.point_stat(name):                  # a per-mille rate: its percent is points (combat.POINT_STATS)
                p, f = 0.0, p * 10 + f
            out += [(name, sign * p * times, True)] if p else []
            out += [(name, sign * f * times, False)] if f else []
    return out


def troop_passives(s, uid, abilities):
    """A troop's passives (abilities: {ability: level}) at its spawn or room start: their SELF statuses on it, held
    (0x5074 with the hold; the client then runs their speed traits), as passives does for the hero. Their other
    traits are its record's (passive_traits in game.deck_enters / game.np_records)."""
    for st, lv in passive_statuses(abilities):
        apply(s, [uid], st, lv, uid)


def passives(s):
    """The held passives' (AUTOMATIC abilities) SELF statuses on the hero at the held level, held (Duration 0): 7000 ->
    7010, 7001 -> 7012, 7002 -> 7011, 7021 -> 7014, 7023 -> 7013 (the client computes their ADD_CASTER_LEVEL traits
    once the status exists)."""
    for st, lv in passive_statuses(s.data.get("kit", {})):
        apply(s, [0], st, lv, 0)


@functools.cache
def _mdp_rows():
    out = {}
    for r in tables.sections("spottable")["Mdp"]:
        out.setdefault((num(r["ID"]), r["Mission_Diffi"]), []).append(r)
    return out


def blessing_status(spot, difficulty, mdp):
    """(status, level) spottable %Mdp puts on a hero of God's Blessing `mdp` (hero.mdp) in `spot` at `difficulty` (0
    Normal, 1 Hard, 2 Hell): the row whose Mdp_Min <= mdp <= Mdp_Max (153 rows on 28 spots, none a story mission):
    1027 MDP_DOWN (ATTACK_PHYSICAL / _MAGICAL -20 / -30 / -40 % by level, HP_HEAL_REDUCE 50 / 75 / 90 %) below the
    recommended value, 1029 MDP_UP (+20 / +30 %, levels 3-9 +3..+10 %) above it; None between the bands or elsewhere.
    Text 52347 "Hero's power decreases when there's not enough God's Blessing"; OFFICIAL-NOTES "the 30% damage buff
    for high gear score" (rules census HERO B6)."""
    from .quest import DIFFICULTIES
    name = DIFFICULTIES[difficulty] if 0 <= difficulty < len(DIFFICULTIES) else None
    for r in _mdp_rows().get((num(spot), name), ()):
        if num(r["Mdp_Min"]) <= mdp <= num(r["Mdp_Max"]):
            return num(r["Mdp_StatusEffect"]), num(r["Level"], 1)
    return None


def blessing(s):
    """The hero's God's Blessing status for this room (blessing_status), held on him (uid 0) from no caster: at the
    room start and again after a revive (which clears his statuses, revived)."""
    c = _hero_char(s)
    if c is None or s.data.get("spot") is None:
        return []
    from . import hero
    got = blessing_status(s.data["spot"], s.data.get("difficulty", 0), hero.mdp(hero.worn_codes(c)))
    return apply(s, [0], got[0], got[1], NO_CASTER) if got else []


def room_start(s):
    """Room start (game.load_progress, after the enter-cell): the FP gauge (0x5138 stat 82; the player struct carries
    no FP), the passive statuses (the hero's, then each deck troop's: troops.passives, T1.11), the God's Blessing band
    (blessing) and the kept timed ones (resume)."""
    pools = s.data.get("pools")
    if pools and "fp" in pools:
        combat.send_stats(s, {combat.STAT_FP: pools["fp"]})
    passives(s)
    blessing(s)
    c = _hero_char(s)
    if c is not None:
        from . import troops
        worn = troops.set_effect(c)             # the main deck's troop set status (T1.10), held
        for uid, t in sorted((s.data.get("deck") or {}).items()):
            troop_passives(s, uid, troops.passives(c, t))
            if worn:
                apply(s, [uid], worn[0], worn[1], uid)
    resume(s)


# --- statuses that outlive their room (planning/client/world_travel.md Gaps 2) ---

@functools.cache
def _maintained():
    """statuseffectinfo %Maintain: the 56 statuses kept across a map change (MAINTAIN in City / World / Field /
    Colosseum / Mission alike: the item and food buffs, e.g. the fire potion's 1000038 / 1000039 for 1800 s, and the
    title statuses); the other 1159 are DELETE."""
    return frozenset(num(r["Id"]) for r in tables.sections("statuseffectinfo")["Maintain"]
                     if r.get("City") == "MAINTAIN")


def _hero_char(s):
    return s.data.get("char") or ((s.data.get("account") or {}).get("characters") or [None])[0]


def keep(s, status, level, duration):
    """A timed status on the hero that the table keeps across maps: kept on the character with its end (wall clock:
    the record outlives the room and the session) for 0x10e4 and the next room (resume)."""
    c = _hero_char(s)
    if c is not None and status in _maintained():
        c.setdefault("timed_statuses", {})[str(status)] = {"level": level, "until": time.time() + duration}


def kept(c):
    """[(status, level, seconds left)] of the character's kept statuses still running; the ended ones are dropped."""
    now, rec = time.time(), c.get("timed_statuses", {})
    for k in [k for k, r in rec.items() if r["until"] <= now]:
        rec.pop(k)
    return [(int(k), r["level"], max(1, math.ceil(r["until"] - now))) for k, r in rec.items()]


def info_packet(c):
    """0x10e4, the answer to 0x10e3: the character's kept statuses on the hero's HUD after a map load."""
    held = kept(c) if c else []
    w = Writer(S2C_STATUS_INFO).u32(c["id"] if c else 0).u16(len(held))
    for st, lv, left in held:
        w.u8(HUD_KIND).u16(min(left, 0xffff)).u8(lv).u32(st).u8(HUD_FLAG)
    return w


def resume(s):
    """Room start: the kept statuses go on the hero again for the rest of their clock (the live service presumably
    re-sent them, world_travel.md Gaps 2 [I])."""
    c = _hero_char(s)
    for st, lv, left in kept(c) if c else []:
        combat.send_status(s, [0], st, lv, left, 0)
        s.data.setdefault("statuses", {}).setdefault(0, {})[st] = {
            "level": lv, "until": time.monotonic() + left, "groups": groups(st), "caster": 0}
        combat.expire_status(s, 0, st, left)
        log.info("hero: kept status %d (level %d) back for %d s", st, lv, left)


def revived(s):
    """The hero's revive (0x505c FALSE) clears his statuses on the client (0x140bed610): the records go, the passives
    come back, and the revive's invincibility goes on (revive_invincible)."""
    forget(s, 0)
    passives(s)
    blessing(s)
    revive_invincible(s, 0)


def troop_revived(s, uid):
    """A deck troop's revive in place (game.revive_troop, 0x505c FALSE: the client clears its statuses, 0x1407e3900 ->
    0x140bed610): its passives and the main deck's set status come back, as at the room start, then the revive's
    invincibility (34, 10 s)."""
    forget(s, uid)
    c = _hero_char(s)
    t = (s.data.get("deck") or {}).get(uid)
    if c is not None and t is not None:
        from . import troops
        troop_passives(s, uid, troops.passives(c, t))
        worn = troops.set_effect(c)
        if worn:
            apply(s, [uid], worn[0], worn[1], uid)
    revive_invincible(s, uid)


REVIVE_HERO, REVIVE_TROOP = 33, 34  # statuseffectinfo COMMON_INVINCIBLE_HERO (5 s) / _TROOP (10 s): TROOP_INVINCIBLE_DPS
                                    # + TROOP_NOATTACK_DPS, %Forbidden Invincibility True, M_IMMUNE_DEBUFF 1000,
                                    # MAX_MOVE_SPEED +500; no other row names them, their use on a revive is the names'
                                    # (census J2 [I], owner decision A8)


def revive_invincible(s, uid):
    """A revived troop's invincibility: 33 on a hero's troop (5 s), 34 on any other (10 s), from no caster. Hits skip
    it while it holds it (invincible: %Forbidden Invincibility); it ends on its Duration (0x5078). For every revive
    path (the camp / in-place revive of the hero, game.revive_hero; a troop's, when one is built)."""
    battle = s.data.get("battle")
    t = battle and battle.troops.get(uid)
    return apply(s, [uid], REVIVE_HERO if (t or {}).get("hero") or uid == 0 else REVIVE_TROOP, 1, NO_CASTER)

"""Hero skills and the skill tree (CommonSubSkillTree, window 0x2c; WorldMapTroopListMgr keeps the hero's list).
Tables: heroskillbook %AbilityBook (HeroID = hero.HERO_CODE, AbilityId, HeroLevel, AutoLearn, SkillType, RequireTP,
RequireSkillType, RequireTotalTP, CommonLogicCalc, RestrictedSkill_1/2, RequireAbilityId_1/2, RequireAbilityLevel_1/2,
AbilityMaxLevel, RequireHeroLevelUpCycle, RequireLevelTP, RequireTotalTPUpCycle), tpgain %TPGain (Level, HeroGainTP).
The character keeps c["skills"] = {ability id: level} for what the tree taught and the AutoLearn levels raised
(record_auto); the class's starter abilities are held at level 1, the AutoLearn rows at their auto_level (they level
with the hero, pushed at the level-up as the original did: level_up). Every hero-skill gold cost is 0 in this build (CostGold),
so skills cost TP only. Spec: specs/items_troops_skills.md 0x1748 / 0x1760.

  C2S 0x1748 (0x140f00110, on city entry with the hero detail): u64 troop uid 0, u64 leader uid.
  S2C 0x1749 ProcessPacket_ResTroopSkillInfo (0x140da3250), no result code, 20 bytes at least (shorter crashes):
      u64 key1 (troop; 0 = no block), u64 key2 = the hero uid + u32 unread; key2 != 0 -> u16 free TP (inferred), u8 n,
      n * (u8 0, u32 ability id, u8 level). The only way TP and the learned list reach the tree.
  C2S 0x1760 (0x140d9f130, 'SkillDecision' after message 7488): u16 n, n * (u32 ability id, u8 target level).
  S2C 0x1761 ProcessPacket_ResHeroSkillLearnLvUp (0x140da4a20): i16; 0 -> u16 n, n * (u8 0, u8 level, u32 id);
      0x2c10 gold, 0x2c11 cannot learn, 0x2c12 previous skill, 0x2c13; the client undoes its queue on a refusal.
The server repeats the client's gates (0x1409c1b40 first level, 0x1409c1960 level-ups), one level at a time."""
import struct

from . import hero, tables
from .net import journal, log
from .packet import Writer

C2S_INFO, S2C_INFO = 0x1748, 0x1749
C2S_LEARN, S2C_LEARN = 0x1760, 0x1761
S2C_ROOM_SKILL = 0x50a9        # a skill learned while in a room (0x140d1afb0): u16 troop uid, u32 ability id
C2S_RESET, S2C_RESET = 0x10ae, 0x10af   # reset the hero's skills (message 0xd019): no payload -> i16 (0 resets the tree;
                                        # the client then asks 0x1746 and 0x10b7)
S2C_RESET_COUNT = 0x1114                # 0x14063cde0 at start: u32 resets done, which prices the next (item_currency
                                        # Skill_Init Gold_Count by index; under 4 bytes crashes)
S2C_TP = 0x1057                         # NotifyUpdateTP 0x140da3820: i16 unspent skill points (hero record +0x284)
RESET_REFUSED = 1                       # "Skills can not be reset."
NOT_LEARNABLE, PREVIOUS_SKILL = 0x2c11, 0x2c12
TREES = ("SKILLTREE1", "SKILLTREE2", "GUILDTREE")    # the gated tree types (COMMON and "-" are not)


def num(v, d=0):
    return int(v) if str(v).lstrip("-").isdigit() else d


def book(cls):
    return {int(r["AbilityId"]): r for r in tables.sections("heroskillbook")["AbilityBook"]
            if r["HeroID"] == hero.HERO_CODE[cls]}


def auto_level(r, hero_level):
    """The level a heroskillbook AutoLearn row holds at `hero_level`: none below its HeroLevel, then 1 and one more every
    RequireHeroLevelUpCycle levels, up to AbilityMaxLevel: the highest level the tree's own gate allows (_refusal), at
    no TP (RequireLevelTP is 0 on every such row). The rows that grow: the class passives (68-70, 367-369, 715-717,
    973-975, 1290-1292: HeroLevel 2-4, cycle 5, max 6), the groggy chains (60, 342, 639, 954, 1244: 12, 6, 4) and the
    Druid's 1216 (1, 5, 6). The original raised them itself at the level-up (rules census HERO L9): part 9 34:44
    (9NwV8ikwLYk f_01043), "The hero levelled up." and "Hero Skill/Action Level-up success." (text 7126, which the
    client prints for a 0x1761 entry of level 2 or more, 0x140da4e79) in the same frame at Lv.17, where 716 alone lands
    (2 + 5 x 3), with no skill window opened; the new rows came the same way, "Learned %s skill." (7102): part 1 at
    Lv.2 "Learned Capture skill. Learned Exile's Power skill." (710, 716), Lv.3 Exile's Resistance (717), Lv.4 Exile's
    Will (715)."""
    start = max(num(r["HeroLevel"], 1), 1)
    if hero_level < start:
        return 0
    cycle = num(r["RequireHeroLevelUpCycle"])
    return min(max(num(r["AbilityMaxLevel"], 1), 1), 1 + (hero_level - start) // cycle) if cycle > 0 else 1


def hero_skills(c):
    """{ability id: level} the hero holds: starter abilities at 1, AutoLearn rows at their auto_level, then the tree
    (c["skills"], which also records the AutoLearn levels raised: record_auto)."""
    from .game import STARTER_ABILITIES
    level = c.get("level", 1)
    held = {a: 1 for a in STARTER_ABILITIES.get(c["class"], ())}
    for aid, r in book(c["class"]).items():
        if r["AutoLearn"] == "True" and auto_level(r, level):
            held[aid] = max(held.get(aid, 0), auto_level(r, level))
    for k, v in (c.get("skills") or {}).items():
        held[int(k)] = max(held.get(int(k), 0), v)
    return held


BAR_ROWS = {"SLOT_TYPE_1": 0, "SLOT_TYPE_7_SERIES1": 100}   # heroskillbook KeyType -> the hero bar row's first slot:
# the upper row = slots 0-7, the lower row = slots 100-107 (MainControlWidget slot_0..7 / slot_100..107, both
# SLOT_SET_MAIN; C2A_swapSlot makes either the row keys 1-8 drive)


def bar_skills(c, level=None):
    """[ability id] the hero bar gets as the hero learns them (world.seat_skills), up to HeroLevel `level` (the
    hero's), in the order they come (HeroLevel, then the class book's row order): the AutoLearn rows marked
    QuickSlotSituate that hang off no other skill (ParentsLinkId "-"), on the numbered skill keys (KeyType SLOT_TYPE_1,
    the upper row) or the tactics row (SLOT_TYPE_7_SERIES1, the lower row: bar_row). Two at level 1 for every class
    but the Sorceress (none): Glen 15 / 9, Isabella 305 / 336, Regnier 608 / 633, Olivia 908 / 945, the Druid
    1204 / 1206; one more at level 2 (82, 314, 710, 969, 1208); Supplement 5012 at 6 (lower row); then 95, 320, 745,
    1008, 1228 at 8; First Aid 5098 at 12 (lower row) and the upper row's 12, 15, 20.
    The original (the tape, the Berserker Sorrowh, every level 1-10 read on the bar; planning/agents/reports/
    2026-10-24_skillbar.md): keys 1 and 2 filled the moment the prologue's UseSkill lesson brings the bar up (part 1
    tiouWoPSPks 5:10.5, 293_319 f_00036); key 3 Capture (710) within 4 s of "Learned Capture skill." at Lv.2 (1199_1207
    f_00010 -> f_00016) with a dialogue open; at Lv.6 (part 2 qeeQjhgO8ss, exact grabs at video 1548 -> 1551.5)
    Supplement (5012) on the lower row's first slot as "Learned Supplement skill." comes, a dialogue open between;
    at Lv.8 (part 3 6uClEdAS__k, video 718 -> 727) Extinction (745) on key 4 under its "Learned the new Hero Skill."
    card, the quest windows open between; Lv.3, 4, 5, 7, 9, 10 change nothing. No drag at any of them. What a level
    opens under a held skill (Earth Cleaver 605 at 6, True Dark Impact 635 at 4, 739 / 691 at 10) is announced
    (announced) but never seated: QuickSlotSituate False. The client never puts a skill on the bar itself: its only
    0x1740 sender is the drag (0x140efce30: 0x1408ebaa0 / 0x1408ebca0 / 0x140dcdd00) and only 0x1747 (0x1408ebf50 ->
    0x1408eee00) and 0x1741 add entries; the 0x1761 handler only re-levels entries already there (0x1408e6f80,
    0x1408e6dd0). So the server kept the bar. Left out, open: the auto rows under a parent (Glen 74 under 82 at 20,
    Isabella 343 under 320 at 12; the Berserker has none, so the tape cannot say)."""
    level = c.get("level", 1) if level is None else level
    rows = [(max(num(r["HeroLevel"], 1), 1), aid) for aid, r in book(c["class"]).items()
            if r["AutoLearn"] == "True" and r["QuickSlotSituate"] == "True" and r["KeyType"] in BAR_ROWS
            and num(r["ParentsLinkId"], None) is None]
    return [aid for at, aid in sorted(rows, key=lambda e: e[0]) if at <= level]


def bar_row(c, ability):
    """The first slot of the hero bar row a skill of bar_skills goes to: 100 (the lower row) for a tactics skill
    (KeyType SLOT_TYPE_7_SERIES1: Supplement 5012, First Aid 5098), else 0 (keys 1-8)."""
    return BAR_ROWS.get((book(c["class"]).get(ability) or {}).get("KeyType"), 0)


def gained(c, before):
    """[(ability id, level)] the hero holds now above what he held at hero level `before`: the AutoLearn rows a
    level-up brings (new ones at 1) and raises (auto_level), in id order."""
    was = hero_skills(dict(c, level=before))
    return sorted((a, lv) for a, lv in hero_skills(c).items() if lv > was.get(a, 0))


def announced(c, before):
    """[(ability id, level)] a level-up from hero level `before` announces in its 0x1761, in the class book's row order
    (the order of the tape's lines): the AutoLearn rows it brings and raises (gained), and the linked follow-ups
    (battle_abilities: ParentsLinkId, 0 TP, no tree) its level opens under a parent held before it. The tape: Lv.6
    (part 2 26:16, qeeQjhgO8ss f_00789) "Learned Earth Cleaver skill." (605 under 608, row 65) then "Learned Supplement
    skill." (5012, row 82); Lv.10 (_0FD8aKDxto f_00296) "Learned Dark Impact - Wave skill." (739, row 66) then "Learned
    Land of Death skill." (691, row 67), both under 633; a follow-up whose parent the same level brings is not
    announced: Lv.2 (part 1 f_00603-00616) reads "Learned Capture skill." (710) and "Learned Exile's Power skill." (716)
    only, not 711 Suppression / 746 Dark Confinement (under 710); Lv.5 and Lv.11 announce nothing, Lv.7 one "Hero
    Skill/Action Level-up success." (716 to 2)."""
    was = battle_abilities(dict(c, level=before))
    rows, held = book(c["class"]), hero_skills(c)
    follow = [(a, lv) for a, lv in battle_abilities(c).items()
              if a not in was and a not in held and num(rows[a]["ParentsLinkId"], None) in was]
    order = {a: i for i, a in enumerate(rows)}
    return sorted(gained(c, before) + follow, key=lambda e: (order.get(e[0], len(order)), e[0]))


def record_auto(c):
    """Write the AutoLearn rows risen above level 1 into c["skills"], the save's record (hero_skills derives them
    anyway; the record makes the login migration run once and shows the levels in the save). Returns [(ability id,
    level held before, level now)]: before = the saved level, else 1 (what ours held a reached row at until 2026-09-30)."""
    saved = c.get("skills") or {}
    out = []
    for aid, r in sorted(book(c["class"]).items()):
        new = auto_level(r, c.get("level", 1)) if r["AutoLearn"] == "True" else 0
        old = saved.get(str(aid), 1)
        if new > 1 and new > old:
            out.append((aid, old, new))
    if out:
        c["skills"] = dict(saved, **{str(a): new for a, _, new in out})
    return out


def taught(c):
    """{ability id (str): level} of c["skills"] the tree taught (not an AutoLearn row's recorded level)."""
    rows = book(c["class"])
    return {k: v for k, v in (c.get("skills") or {}).items()
            if (rows.get(int(k)) or {}).get("AutoLearn") != "True"}


def learned_packet(c, entries):
    """0x1761 success for [(ability id, level)]: the client adds a new one to its list ("Learned %s skill.", 7102) and
    sets a known one's level ("Hero Skill/Action Level-up success.", 7126, for a level of 2 or more; 0x140da4a20)."""
    w = Writer(S2C_LEARN).u16(0).u16(len(entries))
    for aid, level in entries:
        w.u8(handle(c, aid)).u8(level).u32(aid)
    return w


def level_up(s, c, before, room=None):
    """A hero level gained from `before` (world.add_exp): what it brings (gained) goes to the client as the original's
    0x1761, is recorded (record_auto) and journaled ("skill"); inside a room the kit follows and the new abilities are
    usable at once (0x50a9). Returns the entries."""
    entries = announced(c, before)
    if not entries:
        return entries
    old = dict(hero_skills(dict(c, level=before)))
    record_auto(c)
    s.send(learned_packet(c, entries))
    journal("skill", ev="level", id=c["id"], name=c.get("name"), level=c.get("level", 1),
            levels=[[a, old.get(a, 0), lv] for a, lv in entries])
    if room is not None:                                # the room's session: the game connection, whoever paid the exp
        kit = room.data.get("kit") or {}
        room.data["kit"] = battle_abilities(c)
        for aid in sorted(set(room.data["kit"]) - set(kit)):
            room.send(Writer(S2C_ROOM_SKILL).u16(0).u32(aid))
    log.info("level %d: hero skills %s", c.get("level", 1), entries)
    return entries


def battle_abilities(c):
    """{ability id: level} the hero can use in a room (the 0x3f50 leader list; the client starts only abilities in it):
    the held skills (hero_skills) and every heroskillbook row linked to a held one (ParentsLinkId) that costs no TP, is
    no tree skill and is within the hero's level, at its parent's level, repeated until nothing is added. That is the
    class's whole kit: the Gunslinger's R reload stances (63-66, 71, 72 and their slashes 78-81, parent 15 aimed
    shot), dash 2, evade 14, counter 85, executions 91 hang off the auto-learned 15 / 62 / 9; tree follow-ups (e.g.
    56-61 under 8) come with the tree skill. Rows without an abilitytypeinfo row are left out (the client asserts). The
    guild's cores come last (guild.hero_kit; sorted, they follow every other id): without them the list is unchanged."""
    from . import guild
    rows = book(c["class"])
    known = {r["AbilityId"] for r in tables.sections("abilitytypeinfo")["Basic"]}
    level = c.get("level", 1)
    held = dict(hero_skills(c))
    grew = True
    while grew:
        grew = False
        for aid, r in rows.items():
            parent = num(r["ParentsLinkId"], None)
            if (aid not in held and parent in held and num(r["RequireTP"]) == 0 and r["SkillType"] in ("-", "COMMON")
                    and num(r["HeroLevel"], 1) <= level and str(aid) in known):
                held[aid] = held[parent]
                grew = True
    held.update(guild.hero_kit(c))
    return held


def cost(r, level):
    """TP a skill at `level` has taken: RequireTP for the first level, RequireLevelTP for each later one."""
    return num(r["RequireTP"]) + max(level - 1, 0) * num(r["RequireLevelTP"]) if level else 0


def tp_spent(c, held, tree=None):
    rows = book(c["class"])
    return sum(cost(rows[a], lv) for a, lv in held.items() if a in rows and (tree is None or rows[a]["SkillType"] == tree))


def tp_total(level):
    return sum(num(r["HeroGainTP"]) for r in tables.sections("tpgain")["TPGain"] if num(r["Level"]) <= level)


def handle(c, ability):
    """A skill entry's handle `a` (the first byte of 0x1749 / 0x1761 entries): the client drags a skill by it and finds
    it again by it (0x14063aaa0 -> 0x14063a1d0, 0x1408ec2e0); all zeros made every drag ability 1, which no bar takes
    (planning/features/UI.md). The skill's row index in the class's heroskillbook (stable as skills are learned);
    abilities outside the book follow it; never 0xff (the client's own entries)."""
    rows = list(book(c["class"]))
    if ability in rows:
        return rows.index(ability)
    extra = sorted(a for a in hero_skills(c) if a not in rows)
    return min(0xfe, len(rows) + (extra.index(ability) if ability in extra else len(extra)))


def info_packet(c):
    held = hero_skills(c)
    free = max(tp_total(c.get("level", 1)) - tp_spent(c, held), 0)
    w = Writer(S2C_INFO).u64(0).u64(c["id"]).u32(0).u16(free).u8(len(held))
    for aid, lv in sorted(held.items()):
        w.u8(handle(c, aid)).u32(aid).u8(lv)
    return w


def free_tp(c):
    return max(tp_total(c.get("level", 1)) - tp_spent(c, hero_skills(c)), 0)


def tp_packet(c):
    return Writer(S2C_TP).raw(struct.pack("<h", free_tp(c)))


def reset_count_packet(c):
    return Writer(S2C_RESET_COUNT).u32(c.get("skill_resets", 0))


def reset_price(count):
    rows = [r for r in tables.sections("item_currency")["Base"] if r["ItemCurrencyType"] == "Skill_Init"]
    row = rows[min(count, len(rows) - 1)] if rows else {}
    return num(row.get("Gold_Count"))


def _refusal(c, r, aid, lv, held, total):
    """Why skill aid cannot go to level lv now (0: it can), against the levels in held."""
    if lv > num(r["AbilityMaxLevel"], 1):
        return NOT_LEARNABLE
    if c.get("level", 1) < num(r["RequireHeroLevelUpCycle"]) * (lv - 1) + max(num(r["HeroLevel"], 1), 1):
        return NOT_LEARNABLE
    tree = r["RequireSkillType"]
    if tree in TREES and tp_spent(c, held, tree) < num(r["RequireTotalTP"]) + (lv - 1) * num(r["RequireTotalTPUpCycle"]):
        return NOT_LEARNABLE
    if lv == 1:
        reqs = [(num(r[f"RequireAbilityId_{k}"], None), num(r[f"RequireAbilityLevel_{k}"])) for k in (1, 2)]
        reqs = [(a, need) for a, need in reqs if a is not None]
        ok = [held.get(a, 0) >= max(need, 1) for a, need in reqs]
        if reqs and not (any(ok) if r["CommonLogicCalc"] == "OR" else all(ok)):
            return PREVIOUS_SKILL
        if any(num(r[f"RestrictedSkill_{k}"], None) in held for k in (1, 2)):
            return NOT_LEARNABLE
    if total - tp_spent(c, held) < (num(r["RequireTP"]) if lv == 1 else num(r["RequireLevelTP"])):
        return NOT_LEARNABLE
    return 0


def learn(c, wanted):
    """Check and apply [(ability id, target level)] as one batch; returns 0, or the refusal with nothing changed. The
    client checks the batch as a whole (a skill's prerequisite or its tree's spent TP may come from another entry of
    the same batch, in any order), so the levels are taken in passes until every target is reached or a pass gets
    nowhere (live world_20260928_025527:1997: the owner's nine skills, refused one by one in id order, go in four
    passes; planning/client/items_troops_skills.md)."""
    rows = book(c["class"])
    held = hero_skills(c)
    total = tp_total(c.get("level", 1))
    goals = {}
    for aid, target in wanted:
        if rows.get(aid) is None:
            return NOT_LEARNABLE
        goals[aid] = max(goals.get(aid, 0), target)
    while any(held.get(a, 0) < t for a, t in goals.items()):
        moved, why = False, 0
        for aid, target in goals.items():
            while held.get(aid, 0) < target:
                lv = held.get(aid, 0) + 1
                no = _refusal(c, rows[aid], aid, lv, held, total)
                if no:
                    why = why or no
                    break
                held[aid], moved = lv, True
        if not moved:
            return why or NOT_LEARNABLE
    learned = c.setdefault("skills", {})
    for aid, target in wanted:
        learned[str(aid)] = max(held[aid], learned.get(str(aid), 0))
    return 0


def make(role, state):
    @role.on(C2S_INFO)
    def info(s, pkt):
        b = pkt.rest()
        troop_uid, leader_uid = struct.unpack_from("<QQ", b, 0) if len(b) >= 16 else (0, 0)
        c = s.data["char"]
        if not troop_uid:
            s.send(info_packet(c))
            return
        # a troop's list, asked after its detail (0x140d9f0c0): its block under key1, then no leader block. It
        # replaces the troop record's list (+0x250, 0x140da3250), from which a room builds the troop's C1-C4
        # (0x1408ead40): an entry's first byte is its slot, 0..3 the actives (the bar), 4..7 the passives
        # (troops.PASSIVE_SLOTS); the level is the academy's (troops.skill_level, which 0x10bd updates in this list).
        # A skill in no slot is not listed: the equip window marks every listed id as equipped (0x1409b2a30)
        from . import troops
        t = troops.find(c, troop_uid)
        skills = troops.equipped(c, t, range(8)) if t else []
        w = Writer(S2C_INFO).u64(troop_uid).u16(t.get("sp", 0) if t else 0).u8(len(skills))
        for slot, ability, level in skills:
            w.u8(slot).u32(ability).u8(level)
        s.send(w.u64(0).u32(0))

    @role.on(C2S_RESET)
    def reset(s, pkt):
        from . import world
        c = s.data["char"]
        price = reset_price(c.get("skill_resets", 0))
        tree = taught(c)
        if not tree or c.get("gold", 0) < price:
            s.send(Writer(S2C_RESET).u16(RESET_REFUSED))
            return
        c["skills"] = {k: v for k, v in c["skills"].items() if k not in tree}    # the AutoLearn levels stay (0 TP)
        c["skill_resets"] = c.get("skill_resets", 0) + 1
        world.add_gold(s, state, -price)
        s.send(Writer(S2C_RESET).u16(0))
        s.send(info_packet(c))
        s.send(tp_packet(c))
        log.info("skills reset (%d gold)", price)

    @role.on(C2S_LEARN)
    def learn_skills(s, pkt):
        b = pkt.rest()
        n = struct.unpack_from("<H", b, 0)[0] if len(b) >= 2 else 0
        wanted = [struct.unpack_from("<IB", b, 2 + 5 * i) for i in range(min(n, (len(b) - 2) // 5))]
        c = s.data["char"]
        result = learn(c, wanted) if wanted else NOT_LEARNABLE
        if result:
            log.warning("skill learn %s refused: %#x", wanted, result)
            s.send(Writer(S2C_LEARN).u16(result))
            return
        state.save()
        from . import world                             # the hero window follows a learned passive (census S11: the
        s.send(Writer(world.S2C_HERO_BLOCK).raw(world.hero_block(c)))   # client shows only what 0x134b sends)
        s.send(learned_packet(c, wanted))
        s.send(info_packet(c))
        g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
        if g is not None and "battle" in g.data:        # inside a room: the hero can use it without leaving (0x50a9)
            for aid, _ in wanted:
                g.send(Writer(S2C_ROOM_SKILL).u16(0).u32(aid))
            if g.data.get("char") is c or g.data.get("char", {}).get("id") == c["id"]:
                from . import game                      # and the room's numbers (0x5138) and the damage record
                g.data["kit"] = battle_abilities(c)
                game.room_stats(g, c)
        log.info("skills learned: %s", wanted)

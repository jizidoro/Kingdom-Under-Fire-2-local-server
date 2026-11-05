"""Gear and set procs (planning/rules/HERO.md G11; planning/wiring/ITEMS-WIRING.md I13, BATTLE-WIRING B41).

The data: ProcCondition / ProcSkillId / ProcSkillLevel / ProcTarget / ProcProbability on 58 weapons and 10 costumes
(item_weapon, item_look) and on 164 item_set %Info tiers: EACH_ATTACK (the hero's hit landed), BLOCK (he guarded a hit),
WHEN_ATTACKED (he was hit), SELF or TARGET, a chance out of 1000 (10 / 50 / 70 / 75 / 100 / 1000; per mille read as
the item wiring did [I]). The skills are TACTICS abilities (110010-110017 "Fury", "Incision", "Holy Armour" ... their
statuses 60000-60005 and 60008 SELF, 1 s; 113060 "Fiery Bash" a meteor on the nearest enemy).
The client never rolls them: `AbilityFacade::CommitProcSkill 0x140c258e0` has one caller, the 0x50af handler
(`Packet_DoAbilityReq 0x140d1a1b0`, read 2026-10-01 from re/decomp/s2c/50af.c), 23 bytes:
  +0 u16 cast serial (passed to the cast's creation 0x140c266e0; ours: the next of combat's cast serials, so the
     client's executes (0x5066) of it find their caster and ability as a 0x505f cast's do)
  +2 obool: true = the target troop's own position, false = the position of its unit +0xd
  +3 u16 caster troop, +5 u8 level, +6..+12 packed position (x / z as obf.pos_xz: 6..9 its four bytes, 12 the
     nibbles; 10..11 i16 height), +0xd u16 unit, +0xf u16 target troop, +0x11 obf.u32 ability (the client asserts on
     an unknown one), +0x15 i16 -2 = aim at the target's position (else a troop uid whose position it looks up).
Ours: at most one proc while the hero holds 60008 (every proc skill puts it on him for 1 s) [I]."""
import random
import struct

from . import combat, hero, items, net, obf, status
from .net import log
from .packet import Writer

S2C_DO_ABILITY = 0x50af
PROC_MARK = 60008
AIM_AT_TARGET = -2
CONDITIONS = ("EACH_ATTACK", "BLOCK", "WHEN_ATTACKED")


def _proc(r):
    sid = str(r.get("ProcSkillId", "-"))
    if not sid.isdigit() or int(sid) <= 0 or r.get("ProcCondition") not in CONDITIONS:
        return None
    return (r["ProcCondition"], int(sid), max(1, status.num(r.get("ProcSkillLevel"), 1)), r.get("ProcTarget", "SELF"),
            status.num(r.get("ProcProbability")))


def worn(codes):
    """[(condition, ability, level, target SELF / TARGET, chance per mille)] of the worn items and of the set tiers
    their pieces complete (item_set %Info SetNumber <= pieces worn, as items.set_traits)."""
    out, sets = [], {}
    for code in codes:
        r = items.row(code) or {}
        p = _proc(r)
        if p:
            out.append(p)
        sc = str(r.get("SetCode", "-1"))
        if sc.isdigit() and int(sc) > 0:
            sets[sc] = sets.get(sc, 0) + 1
    for sc, n in sets.items():
        for r in items._set_rows().get(sc, []):
            if str(r.get("SetNumber", "")).isdigit() and n >= int(r["SetNumber"]):
                p = _proc(r)
                if p:
                    out.append(p)
    return out


def packet(serial, caster, ability, level, target):
    """0x50af: the client casts `ability` at `level` for troop `caster` on troop `target` (its own position)."""
    xz, nibbles = obf.pos_xz(0, 0)
    return (Writer(S2C_DO_ABILITY).u16(serial).obool(True).u16(caster).u8(level).raw(xz).raw(struct.pack("<h", 0))
            .u8(nibbles).u16(0).u16(target).raw(obf.u32(ability)).raw(struct.pack("<h", AIM_AT_TARGET)))


def roll(s, condition, target=None, rng=random):
    """The hero's procs of `condition` (EACH_ATTACK with the first troop the hit landed on, BLOCK / WHEN_ATTACKED with
    the attacker): each rolls its chance; a success is cast for him by 0x50af (TARGET on `target`, SELF on him) with a
    new cast serial kept as a 0x505f cast's (combat.casts / cast_ability), so the client's executes of it take the
    usual path (damage, statuses: status.on_execute). Returns the abilities cast."""
    c = s.data.get("char")
    if c is None or PROC_MARK in status.holding(s, 0):
        return []
    done = []
    for cond, ability, level, aim, chance in worn(hero.worn_codes(c)):
        if cond != condition or (aim == "TARGET" and target is None):
            continue
        if chance < 1000 and rng.randrange(1000) >= chance:
            continue
        serial = s.data["cast_serial"] = s.data.get("cast_serial", 0) % 0xfffd + 1
        s.data.setdefault("casts", {})[serial] = struct.pack("<H", 0)
        s.data.setdefault("cast_ability", {})[serial] = ability
        s.data.setdefault("proc_levels", {})[ability] = level
        on = target if aim == "TARGET" else 0
        s.send(packet(serial, 0, ability, level, on))
        net.journal("proc", condition=condition, ability=ability, level=level, target=on, serial=serial)
        log.info("proc: %s -> ability %d (level %d) on troop %d, serial %d", condition, ability, level, on, serial)
        done.append(ability)
        break                                           # one proc a time: the next waits for the mark to end [I]
    return done

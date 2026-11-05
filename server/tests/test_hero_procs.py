"""Gear and set procs (planning/rules/HERO.md G11): the server rolls them and has the client cast them (0x50af, the only
caller of AbilityFacade::CommitProcSkill 0x140c258e0); the layout is the handler's (0x140d1a1b0, re/decomp/s2c/50af.c)."""
import struct

import pytest

from kuf2 import combat, obf, procs, status
from test_battle import Session

ALWAYS_RUTHLESS = 100999001      # a GLEN test weapon: EACH_ATTACK, 110012 "Ruthlessness" level 1, SELF, 1000 of 1000
STARK_RUINS = 103000101          # Stark Ruins Longsword: EACH_ATTACK, 110014 "Incision" level 2, TARGET, 50
PASSIONATE = 103000102           # Passionate Imperial Longsword: 110011 "Fury" level 2, SELF, 75


class Roll:
    def __init__(self, v):
        self.v = v

    def randrange(self, n):
        return self.v


def room(worn):
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "level": 30,
                      "equip": [{"code": code, "index": i, "serial": i + 1} for i, code in enumerate(worn)]}
    s.data["battle"].add_hero(0, 10000)
    return s


def decode(b):
    """The fields as the client's handler reads them."""
    return {"serial": struct.unpack_from("<H", b, 0)[0], "own_position": obf.T1[b[2]] & 1,
            "caster": struct.unpack_from("<H", b, 3)[0], "level": b[5], "unit": struct.unpack_from("<H", b, 0xd)[0],
            "target": struct.unpack_from("<H", b, 0xf)[0], "ability": obf.dec_u32(b[0x11:0x15]),
            "aim": struct.unpack_from("<h", b, 0x15)[0], "position": obf.dec_pos_xz(b[6:10], b[12])}


def test_the_worn_procs_come_from_the_items_and_their_sets():
    assert procs.worn([STARK_RUINS]) == [("EACH_ATTACK", 110014, 2, "TARGET", 50)]
    assert procs.worn([ALWAYS_RUTHLESS]) == [("EACH_ATTACK", 110012, 1, "SELF", 1000)]
    assert procs.worn([]) == []
    pergos = [101130521, 102130521, 151130521, 152130521, 153130521, 154130521, 155130521]   # Enraged Pergos set
    assert procs.worn(pergos) == [("EACH_ATTACK", 110011, 1, "SELF", 50)]                   # its 7-piece tier
    assert procs.worn(pergos[:6]) == []


def test_a_landed_hit_casts_a_self_proc_through_0x50af():
    s = room([ALWAYS_RUTHLESS])
    assert procs.roll(s, "EACH_ATTACK", 7) == [110012]
    w = next(w for w in s.sent if w.proto == procs.S2C_DO_ABILITY)
    b = bytes(w.buf)
    assert len(b) == 0x17
    got = decode(b)
    assert got == {"serial": got["serial"], "own_position": 1, "caster": 0, "level": 1, "unit": 0, "target": 0,
                   "ability": 110012, "aim": -2, "position": (0, 0)}
    assert s.data["casts"][got["serial"]] == b"\0\0" and s.data["cast_ability"][got["serial"]] == 110012
    assert status.cast_level(s, 110012, 0) == 1


@pytest.mark.parametrize("roll, fires", [(49, True), (50, False)])
def test_a_target_proc_rolls_its_chance_per_mille_and_aims_at_the_hit_troop(roll, fires):
    s = room([STARK_RUINS])
    assert (procs.roll(s, "EACH_ATTACK", 7, rng=Roll(roll)) == [110014]) == fires
    sent = [decode(bytes(w.buf)) for w in s.sent if w.proto == procs.S2C_DO_ABILITY]
    assert [(d["target"], d["level"], d["ability"]) for d in sent] == ([(7, 2, 110014)] if fires else [])
    if fires:
        assert status.cast_level(s, 110014, 0) == 2


def test_no_proc_while_the_mark_of_the_last_is_held_or_for_another_condition():
    s = room([ALWAYS_RUTHLESS])
    assert procs.roll(s, "WHEN_ATTACKED", 7) == [] and procs.roll(s, "BLOCK", 7) == []
    s.data.setdefault("statuses", {}).setdefault(0, {})[procs.PROC_MARK] = {"level": 1, "until": None, "groups": ()}
    assert procs.roll(s, "EACH_ATTACK", 7) == []


def test_the_hit_path_rolls_the_heros_attack_procs_and_the_hits_on_him(monkeypatch):
    from kuf2 import game
    from test_battle import Even, FieldSession, record
    monkeypatch.setattr(combat, "random", Even())
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["char"] = {"id": 1, "class": 0, "level": 30, "equip": [{"code": ALWAYS_RUTHLESS, "index": 0, "serial": 1}]}
    s.data["battle"].add_hero(0, 10 ** 9, c=record(100, 1, team=0))
    s.data["battle"].add_np(1, 10 ** 9, 1, c=combat.combatant(1, 1, atk=(100, 100)))
    combat.apply_hits(s, [(1, [0])], game.send_troop_hp, attacker=0, attack={"pr": 1.0, "ar": 1.0})
    assert [decode(bytes(w.buf))["ability"] for w in s.sent if w.proto == procs.S2C_DO_ABILITY] == [110012]
    s.data["char"]["equip"] = [{"code": 103000101, "index": 0, "serial": 1}]      # no WHEN_ATTACKED proc on it
    s.sent.clear()
    combat.apply_hits(s, [(0, [0])], game.send_troop_hp, attacker=1, attack={"pr": 1.0, "ar": 1.0})
    assert not any(w.proto == procs.S2C_DO_ABILITY for w in s.sent)


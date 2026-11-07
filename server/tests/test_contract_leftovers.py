"""The single-player requests that had only a constant reply (planning/todo/CONTRACT-COMPLETE-PLAN.md, family 1),
each through its registered handler.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import game, world
from kuf2.packet import Reader
from test_mission_rules import dead_hero, revive_here
from test_rewards import State


def ask(role, s, proto, body=b""):
    """Send one request through the role's handler table; returns the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def test_the_battle_hud_is_told_the_revivals_used_in_this_room():
    # 0x513b -> 0x513c u32 (0x140e10110): the count the revive in place keeps (0x50f5's), so the HUD's confirm
    # (0x14068f0b0) refuses at the spot's limit; PVE_RIFT 10335 allows 5
    role = game.make(State(), 0)
    s = dead_hero(10335, cubic=1000)
    assert ask(role, s, game.C2S_REVIVE_COUNT) == [(game.S2C_REVIVE_COUNT, struct.pack("<I", 0))]
    for used in (1, 2):
        assert revive_here(s) == 0
        s.data["battle"].troops[0]["hp"] = 0
        assert ask(role, s, game.C2S_REVIVE_COUNT) == [(game.S2C_REVIVE_COUNT, struct.pack("<I", used))]
    assert revive_here(dead_hero(10540, cubic=1000)) == 0x7412          # a refused revive is not counted
    s = dead_hero(10540, cubic=1000)
    revive_here(s)
    assert ask(role, s, game.C2S_REVIVE_COUNT) == [(game.S2C_REVIVE_COUNT, struct.pack("<I", 0))]


def test_a_cutscenes_force_complete_finishes_only_a_marker_quest():
    # 0x5551, RTS.SetQuestForceComplete(id) of the shipped cutscene scripts (not a developer command: the silent
    # builder's report): 1002 is questtable %SpotEvent's marker for Sunstruck's opening room (Use_Quest No,
    # JustCompleted); the reply is the empty 0x5552 list, then the finished list with it (0x5541)
    from kuf2 import obf, quest
    from test_rewards import Session, char

    class Saves(State):
        saves = 0

        def save(self):
            self.saves += 1

    st = Saves()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session(char())
    got = ask(role, s, quest.C2S_FORCE_COMPLETE, obf.u32(1002))
    assert got[0] == (quest.S2C_FORCE_COMPLETE, bytes(2))
    assert [p for p, _ in got] == [quest.S2C_FORCE_COMPLETE, quest.S2C_FINISHED]
    assert got[1][1] == struct.pack("<H", 1) + bytes([got[1][1][2]]) + obf.u32(1002) + bytes(4)
    assert s.data["char"]["quests"]["done"] == [1002] and st.saves == 1
    # again, a real quest (1003), an id in no table (1006), a short body: answered, nothing finished
    for body in (obf.u32(1002), obf.u32(1003), obf.u32(1006)):
        assert ask(role, s, quest.C2S_FORCE_COMPLETE, body) == [(quest.S2C_FORCE_COMPLETE, bytes(2))]
    assert ask(role, s, quest.C2S_FORCE_COMPLETE, b"\x01") == []
    assert s.data["char"]["quests"]["done"] == [1002] and st.saves == 1


def test_a_charged_skills_stage_changes_its_executes():
    # 0x5062 (AbilityCast::_IncreaseChargeStep): one per charge stage reached, the only carrier of the stage.
    # abilitytypeinfo %Charge, the Gunslinger's aimed shot 176 level 1: ChargeLevel 2, ProcessRate1 "100 125 80",
    # ProcessRate2 "120 150 100"; uncharged it is abilitycastinfo's "70 100 50" at AttributeRate 2500
    from kuf2 import combat
    hero = game.hero_combatant({"id": 1, "class": 0, "level": 30})

    def shares(stage):
        return [combat.ability_attack(hero, 176, 1, k, stage)["ar"] for k in (1, 2, 3)]

    assert shares(0) == pytest.approx([2.5 * 0.70, 2.5 * 1.00, 2.5 * 0.50])
    assert shares(1) == pytest.approx([2.5 * 1.00, 2.5 * 1.25, 2.5 * 0.80])
    assert shares(2) == pytest.approx([2.5 * 1.20, 2.5 * 1.50, 2.5 * 1.00])
    assert shares(5) == shares(2)                                   # capped at ChargeLevel
    assert combat.charge_stage(164, 1, 3) is None                   # a skill with no %Charge row: its plain row
    assert combat.ability_attack(hero, 164, 1, 1, 3) == combat.ability_attack(hero, 164, 1, 1)
    # the request counts per cast serial, answers nothing, and the cast's end (0x506a) drops the count
    role, s = game.make(State(), 0), Bare()
    for _ in range(2):
        assert ask(role, s, combat.C2S_CHARGE_STEP, struct.pack("<H", 7)) == []
    assert ask(role, s, combat.C2S_CHARGE_STEP, b"\x07") == [] and s.data["charge"] == {7: 2}
    ask(role, s, combat.C2S_CAST_DONE, struct.pack("<H", 7))
    assert s.data["charge"] == {}


def test_a_boost_event_that_is_on_raises_exp_gold_and_drops_at_their_call_sites(monkeypatch):
    # events.ACTIVE_BOOST (the owner's switch, off): the anniversary boost adds gold 200 %, exp 100 %, drops 100 %.
    # The call sites: game.troop_down and the mission's end (hero exp, troop exp, gold), loot.roll_drops (the chance)
    from kuf2 import events, loot
    assert [events.boosted(k, 100) for k in ("hero_exp", "troop_exp", "gold", "drop")] == [100] * 4      # off
    troop = next(int(key) for key, r in loot._drop_rows("Troop").items()
                 if any(0 < loot._int(r[f"Drop_Category{k}_Prob"]) < loot.PROB // 4 for k in range(1, loot.SLOTS + 1)))

    def hits(rolls=4000):
        import random
        rng = random.Random(7)
        return sum(bool(loot.roll_drops(10233, troop, roll=rng.randrange)) for _ in range(rolls))

    plain = hits()
    monkeypatch.setattr(events, "ACTIVE_BOOST", "anniversary_2020_11")
    assert [events.boosted(k, 100) for k in ("hero_exp", "troop_exp", "gold", "drop")] == [200, 200, 300, 200]
    assert hits() > plain * 1.4                              # the same rolls, a doubled chance


NEW_MODULES = {"kuf2.market", "kuf2.party", "kuf2.social", "kuf2.events", "kuf2.realm", "kuf2.guild",
               "kuf2.changetroop"}
JUNK = (b"", b"\0", b"\xff", bytes(2), bytes(3), b"\xff" * 5, bytes(7), b"\xff" * 64)


@pytest.mark.parametrize("name", ["world", "game"])
def test_a_short_or_junk_request_never_raises_in_a_handler_added_for_the_contract(name):
    # a handler that raises closes the session (net.Session.run); the constants these handlers replaced read nothing.
    # Found by the wiring's attack, 2026-11-05: the letters' lists and take-gold read past a short body, and the
    # mail check wrote a junk id as an i32
    from kuf2 import combat
    role = world.make(State(), 0, "127.0.0.1", 0) if name == "world" else game.make(State(), 0)
    mine = [(p, fn) for p, fn in sorted(role.handlers.items())
            if fn.__module__ in NEW_MODULES or p in (0x5551, 0x5062, 0x513b)]
    assert len(mine) >= (60 if name == "world" else 17)   # (events' and realm's fixed replies are net's handlers)
    for proto, fn in mine:
        for body in JUNK:
            s = Bare()
            c = {"id": 1, "class": 0, "level": 30, "exp": 0, "name": "T", "spot": 10354, "pos": [0, 0, 0], "gold": 0,
                 "quests": {"active": {}, "done": []}, "bag": [], "troops": []}
            s.data.update(char=c, account={"id": 1, "characters": [c]})
            if name == "game":
                s.data.update(spot=10370, difficulty=0, battle=combat.Battle())
            s.pending = []
            s.later = lambda delay, f, s=s: s.pending.append((delay, f))
            fn(s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))       # must not raise


class Bare:
    """A session that only collects what is sent."""
    def __init__(self):
        self.data, self.sent = {}, []

    def send(self, w):
        self.sent.append(w)


# The fixed replies judged to be the whole behaviour on a one-player server (the specs' "CONSTANT" lines hold each
# proof): (role, request, reply, body). A change here is a change of the judged answer.
CONSTANTS = [
    ("world", 0x1031, 0x1032, ""),                # the ping: the handler reads nothing
    ("world", 0x10e9, 0x10ea, "00000000"),        # GM-event spot flags: result 0, no spot
    ("world", 0x112e, 0x112f, "0000000000"),      # day info: result 0, (minute, weekday, hour) = zeros
    ("world", 0x1078, 0x1079, "0000"),            # reputation: nothing in this build grants any
    ("world", 0x1049, 0x104a, "000001"),          # world-map entry: result 0, the one channel
    ("world", 0x1016, 0x1017, "0000"),            # survey answer: the client shows its own end text
    ("world", 0x1044, 0x1045, "e80301010001"),    # channel list: capacity 1000, one row (1 user, channel 1)
    ("world", 0x104d, 0x104e, "1504"),            # channel select: 0x415 "Wrong channel."
    ("world", 0x10ca, 0x10cb, "0000"),            # shout: result 0, the client prints it itself
    ("world", 0x112c, 0x112d, "00000000"),        # /escape: no cooldown left
    ("game", 0x112c, 0x112d, "00000000"),
    ("game", 0x513d, 0x513e, "00000000"),         # other players' revival counts, revive bans: none
    ("game", 0x5146, 0x5147, "0000"),             # the party's map pings: none
]


@pytest.mark.parametrize("name, request_id, reply, body", CONSTANTS, ids=[f"{c[0]}-{c[1]:04x}" for c in CONSTANTS])
def test_a_judged_constant_reply_keeps_its_bytes(name, request_id, reply, body):
    role = world.make(None, 0, "127.0.0.1", 0) if name == "world" else game.make(None, 0)
    assert ask(role, Bare(), request_id) == [(reply, bytes.fromhex(body))]

"""Field NPC simulation transfer, pinned to client 0x140d1c3f0's four-byte contract.

Packet checks prove server ordering/lifecycle only. Native +0x230, dispatch and behavior
remain the acceptance checks in planning/quality/FIELD-SIMULATION.md.
"""
import struct

import pytest

from kuf2 import game
from test_battle import FieldSession, NoSave, pkt, spawn_programs


TRANSFER = 0x50cf


def room(spot=10359):
    s = FieldSession({"active": {}, "done": []})
    s.data["spot"] = spot
    return s


def spawn(s, uid=20001, **extra):
    t = dict(TroopID=uid, TroopTableID=154340, PosX=100., PosZ=200.,
             TeamNum=1, ForceNum=10030, UnitNum=0, FirstAttack=1,
             WanderingDist=500, HoldMovement=0)
    t.update(extra)
    assert game.spawn_zone_troop(s, t)
    return t


def bind(s, uid):
    game.make(NoSave(), 0).handlers[0x50ab](s, pkt(0x50ab, struct.pack("<H", uid)))


def transfers(s):
    return [bytes(w.buf) for w in s.sent if w.proto == TRANSFER]


@pytest.mark.parametrize("team,force", [(1, 10030), (0, 20030), (255, 30030)])
@pytest.mark.parametrize("spot", [10359, 20906])  # Field and Field_PK, the client's two remote-spawn types
def test_field_transfer_waits_for_both_objects_and_keeps_faction_and_ai(team, force, spot):
    s = room(spot)
    spawn(s, TeamNum=team, ForceNum=force)
    assert transfers(s) == []
    enter = next(w for w in s.sent if w.proto == game.S2C_ENTER_CELL_TROOP)
    state = bytes(enter.buf)[3:]
    assert struct.unpack_from("<h", state)[0] == team
    assert struct.unpack_from("<H", state, 0x30)[0] == force
    assert spawn_programs(s)[20001] == (60000, 60000)
    bind(s, 20001)                            # NPC builds before hero: reference not ready
    assert transfers(s) == []
    bind(s, 0)
    assert transfers(s) == [struct.pack("<HH", 20001, 0)]  # troop UID 0, NOT player slot 1
    assert s.sent[-1].proto == TRANSFER        # no faction/AI overwrite after granting simulation
    bind(s, 20001)
    bind(s, 0)
    assert len(transfers(s)) == 1             # duplicate transfer would reset client behavior


def test_transfer_precedes_orders_even_when_hero_binds_last():
    s = room()
    spawn(s)
    order = [game.ACT_ENABLE_ALL_TROOPS, 1, 1]
    game.troop_order(s, 20001, order)
    bind(s, 20001)
    game.troop_order(s, 20001, order)           # bound, but simulation still awaits hero
    assert not any(w.proto == game.S2C_SCRIPT_ACTION for w in s.sent)
    bind(s, 0)
    assert [w.proto for w in s.sent[-3:]] == [TRANSFER, game.S2C_SCRIPT_ACTION, game.S2C_SCRIPT_ACTION]


def test_respawn_requires_new_bind_and_grants_once_again():
    s = room()
    bind(s, 0)
    t = spawn(s)
    bind(s, 20001)
    assert len(transfers(s)) == 1
    game.respawn_zone_troop(s, 20001, t)
    assert len(transfers(s)) == 1
    bind(s, 20001)
    bind(s, 20001)
    assert transfers(s) == [struct.pack("<HH", 20001, 0)] * 2


def test_unknown_early_bind_does_not_authorize_a_later_spawn():
    s = room()
    bind(s, 0)
    bind(s, 20001)
    bind(s, 1)                               # player/deck UID is not an NP spawn
    assert transfers(s) == []
    spawn(s)
    assert transfers(s) == []
    bind(s, 20001)
    assert transfers(s) == [struct.pack("<HH", 20001, 0)]


@pytest.mark.parametrize("hero_first", [False, True])
def test_expired_unbound_quest_spawn_cannot_be_transferred_by_late_ack(hero_first):
    s = room()
    if hero_first:
        bind(s, 0)
    spawn(s)
    if not hero_first:
        bind(s, 20001)                      # built target still waits for its reference
    game.quest_troop_gone(s, 20001)
    bind(s, 20001)
    bind(s, 0)
    assert transfers(s) == []
    # Reusing the UID is a new lifetime; no ForceNum is needed for a quest NPC.
    t = dict(TroopID=20001, TroopTableID=154340, PosX=100., PosZ=200., TeamNum=1, UnitNum=0)
    assert game.spawn_zone_troop(s, t)
    assert transfers(s) == []
    bind(s, 20001)
    assert transfers(s) == [struct.pack("<HH", 20001, 0)]


def test_failed_respawn_clears_the_old_pending_transfer():
    s = room()
    t = spawn(s)
    # Leave succeeds, replacement table row is invalid: a late bind must not grant it.
    game.respawn_zone_troop(s, 20001, dict(t, TroopTableID=99999999))
    bind(s, 0)
    bind(s, 20001)
    assert transfers(s) == []


@pytest.mark.parametrize("spot", [10233, 10234, 10358, 50116, 999999])
def test_missions_and_unknown_spots_keep_existing_host_simulation(spot):
    s = room(spot)
    bind(s, 0)
    spawn(s)
    bind(s, 20001)
    assert transfers(s) == []


def test_all_initial_field_npcs_receive_transfer_after_bind():
    s = room()
    bind(s, 0)
    game.spawn_zone_troops(s)
    uids = sorted(s.data["zone_troops"])
    assert len(uids) > 200 and transfers(s) == []  # real room 10359: hostiles and neutrals
    for uid in uids:
        bind(s, uid)
    assert transfers(s) == [struct.pack("<HH", uid, 0) for uid in uids]
    for uid in uids:
        bind(s, uid)
    assert len(transfers(s)) == len(uids)

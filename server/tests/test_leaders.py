"""NP troops with their leaders (zone NPLeaderID): the troop state's +0x32, the leader's hp in Battle and 0x505d."""
import struct

from kuf2 import combat, game, status
from test_battle import mission_room


def entered(s, uid):
    """The 61-byte troop state of the 0x50cb that brought troop uid in (u16 1, obool player block, the state)."""
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_ENTER_CELL_TROOP and struct.unpack_from("<H", b, 3 + 0x11)[0] == uid:
            return b[3:3 + 0x3d]
    return None


def test_thompson_and_the_mini_boss_come_with_their_leaders():
    # Grey Fog 10358: Thompson 10000 (troop 162010, 0 units, leader 162010 "톰슨", 6664 hp) and the Encablossian Leader's
    # formation 22003 (12 x 162120, leader 162020, 423 hp); the militia without one
    s = mission_room(10358)
    st = entered(s, 10000)
    assert struct.unpack_from("<I", st, 0x32)[0] == 162010
    b = s.data["battle"].troops
    assert b[10000]["units"] == [] and b[10000]["leader"] == 6664 and b[10000]["leader_floor"] == 1
    assert b[22003]["leader"] == 423 and b[22003]["leader_floor"] == 0 and len(b[22003]["units"]) == 12
    militia = next(u for u, t in s.data["zone_troops"].items() if game.np_leader(t.get("NPLeaderID")) is None)
    assert struct.unpack_from("<I", entered(s, militia), 0x32)[0] == 0 and "leader" not in b[militia]


def test_a_formation_falls_when_its_units_and_its_leader_are_down():
    s = mission_room(10358)
    t = s.data["battle"].troops[22003]
    s.data["battle"].add_np(1, 100, 1, c=combat.np_combatant(162010, 0))          # an ally hits them
    downs = []
    hit = lambda idx: combat.apply_hits(s, [(22003, [idx])], game.send_troop_hp, lambda s, uid: downs.append(uid),
                                        attacker=1, attack={"kill": True})
    for k in range(12):
        hit(k)
    assert not any(t["units"]) and t["leader"] == 423 and downs == [] and status.alive(s, 22003)
    hp = [w for w in s.sent if w.proto == game.S2C_TROOP_HP][-1]
    assert bytes(hp.buf)[0] & 0x30 == 0x10                               # every 0x505d carries the leader's hp
    hit(0)                                                               # a hit on a fallen unit lands on him
    assert t["leader"] == 0 and downs == [22003]


def test_an_ally_leader_holds_in_the_missions_where_nobody_dies():
    s = mission_room(10358)
    t = s.data["battle"].troops[10000]
    s.data["battle"].add_np(2, 100, 1, c=combat.np_combatant(162120, 1))
    for _ in range(3):
        combat.apply_hits(s, [(10000, [combat.LEADER])], game.send_troop_hp, attacker=2, attack={"kill": True})
    assert t["leader"] == 1 and status.alive(s, 10000)

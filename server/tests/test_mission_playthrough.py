"""The story missions up to New Hampton played through headless (adversarial run 2026-09-28 on the director and the
NP leaders: each test here broke the change once, or pins a boundary the suite lacked)."""
import struct

import pytest

from kuf2 import combat, director, game, obf
from test_battle import NoSave, mission_room, walk, pkt
from test_director import obey
from conftest import run_pending

SPOTS = (10358, 10233, 10234, 10361, 10362, 10235, 10331, 10345, 10347, 10349, 10303, 10306)


def windows(s):
    return sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)


def ends(s):
    """How the room ended: result windows, or for a windowless mission (decision B2) the leaves (0x4041)."""
    if game.windowless(s.data["spot"]):
        assert windows(s) == 0
        return sum(w.proto == game.S2C_MISSION_LEAVE for w in s.sent)
    return windows(s)


def play_through(s, visit_bounds=True, rounds=200):
    """Down every standing hostile and every troop of a force a story step waits on (Tower's wyrms: staging hp, no
    exp, and "uphill" and the tower wait for them); walk every bound the table names (in table order) and break the
    props it waits on (Flamegrass's barricade); do what the lessons ask (test_director.obey); let time pass."""
    steps = director.script(s.data["spot"])
    bounds = [director.bound(s.data["spot"], st["bound"]) for st in steps if st["on"] == "bound"]
    props = [p for st in steps if st["on"] == "broken" for p in (st["prop"] if isinstance(st["prop"], tuple)
                                                                 else (st["prop"],))]
    awaited = {st["force"] for st in steps if st["on"] == "down" and st.get("force") is not None}
    for _ in range(rounds):
        if s.data.get("mission_won"):
            return True
        if visit_bounds:
            for b in bounds:
                walk(s, b["BoundCenterX"], b["BoundCenterZ"])
            for p in props:
                director.on_broken(s, p)
        alive = [u for u, z in s.data.get("zone_troops", {}).items()
                 if (game.hostile(z) or z.get("ForceNum") in awaited) and u not in s.data.get("down", set())]
        for u in alive:
            game.mission_troop_down(s, NoSave(), u)
        # a troop downed outright still fires its hp steps (director.on_down: Vert summons and escapes)
        run_pending(s)
        obey(s)
    return s.data.get("mission_won")


@pytest.mark.parametrize("spot", SPOTS)
def test_each_mission_can_be_won_by_playing_it(spot):
    s = mission_room(spot)
    s.state = NoSave()
    assert play_through(s), "never won: %s waves held %s" % (
        spot, [w[0].get("ForceNum") for w in s.data.get("waves", ())])
    assert ends(s) == 1


@pytest.mark.parametrize("spot", SPOTS)
def test_with_nothing_left_to_fight_the_story_points_ahead(spot):
    # the table's held forces wait for their places (Tower: the door bound 10012); ActGuiShowDirectionToTargetArea
    # points at the next one (Lunawing waits on its own bound and is won at its destination)
    s = mission_room(spot)
    s.state = NoSave()
    won = play_through(s, visit_bounds=False, rounds=60)
    pointed = [struct.unpack_from("<3I", bytes(w.buf))[1] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
               and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_DIRECTION_TO_AREA]
    if not won:
        assert pointed


def test_the_win_command_during_the_ending_gives_one_window():
    s = mission_room(10234)
    s.state = NoSave()
    run_pending(s)
    game.mission_won(s, NoSave())                       # the ending starts playing
    assert windows(s) == 0
    director.skip_ending(s)                             # what world.force_win does now
    game.mission_won(s, NoSave())
    run_pending(s)                                      # the ending's own finish() then runs
    assert windows(s) == 1, windows(s)


def test_two_wins_during_the_ending_give_one_window():
    s = mission_room(10234)
    s.state = NoSave()
    run_pending(s)
    game.mission_won(s, NoSave())
    game.mission_troop_down(s, NoSave(), 20000)
    game.on_hero_position(s)
    run_pending(s)
    assert windows(s) == 1


def test_area_damage_reaches_a_leader_only_troop():
    s = mission_room(10233)
    game.spawn_zone_troop(s, next(t for t in __import__("kuf2.zone").zone.for_spot(10233)["NPCTroopInfoData"]
                                  if t["TroopID"] == 20014))
    t = s.data["battle"].troops[20014]
    assert t["units"] == [] and t["leader"] > 0
    src = 11006                                          # the handed archers (133120, ranged)
    before = t["leader"]
    body = obf.u16(src) + struct.pack("<H", 1) + obf.u16(20014) + bytes([127 * 2])
    role = game.make(NoSave(), 0)
    for _ in range(5):
        role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
    assert t["leader"] < before


def test_an_ability_index_past_the_units_reaches_the_leader():
    s = mission_room(10358)
    t = s.data["battle"].troops[22003]
    for i in range(len(t["units"])):
        t["units"][i] = 0
    s.data["battle"].add_np(1, 100, 1, c=combat.np_combatant(162010, 0))
    downs = []
    combat.apply_hits(s, [(22003, [2047])], game.send_troop_hp, lambda s, u: downs.append(u), attacker=1,
                      attack={"kill": True})
    assert t["leader"] == 0 and downs == [22003]


def test_a_heal_of_a_leader_troop_keeps_its_leader_hp_in_the_packet():
    s = mission_room(10358)
    s.sent.clear()
    r = s.data["battle"].heal(22003, [0], 10)
    game.send_troop_hp(s, 22003, r[0], r[1])
    b = bytes(s.sent[-1].buf)
    assert b[0] & 0x30, "leader hp left out: the client kills the leader"


def test_a_bound_step_waking_a_force_inside_the_proximity_loop():
    s = mission_room(10234)
    b = director.bound(10234, "P1_S2_코볼트 리더 등장")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])        # wakes 20024 in the step, 20024 also in WAKE_RANGE
    assert 20170 in s.data["zone_troops"]


def test_rapid_falls_queue_one_heal_line():
    s = mission_room(10234)
    run_pending(s)
    hero = s.data["battle"].troops[0]
    for _ in range(10):                                 # ten crossings in the same second
        director.on_hp(s, 0, 10, hero["max"])
        director.on_hp(s, 0, hero["max"], hero["max"])
    run_pending(s)
    from test_director import lines_shown
    heals = [x for x in lines_shown(s) if x[2] == 1000]
    assert len(heals) == 1


def test_grey_fog_villagers_are_not_enemies_to_kill():
    s = mission_room(10358)
    vill = [t for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 15000]
    assert vill and not any(game.hostile(t) for t in vill), [(t["TeamNum"], t["TroopTableID"]) for t in vill]

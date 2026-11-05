"""Lunawing Sortie I 10361: the director's table (kuf2/scenes/m10361.py)."""
from kuf2 import game
from test_battle import FieldSession, NoSave, mission_room, pkt, walk
from test_director import lines_shown, run_pending
import struct

from kuf2 import director
from kuf2 import combat
import pytest

GLEN, THOMPSON, GOLDEN_HAMMER, JADE = 10283, 10284, 10285, 10286      # force 10100, in the room from the start


@pytest.mark.parametrize('attack', [None, {'dot': True}, {'ability': 200195}])
def test_lunawing_does_not_lose_hp_to_enemy_hits(attack, monkeypatch):
    # Original part3 frames120/140: HP77610 under fire, separate blue shield.
    # Replay lethal damage through the shared hit pipeline, including ticks/skills.
    s = mission_room(10361)
    ship = s.data['battle'].troops[10000]
    before = combat.Battle.total(ship)
    monkeypatch.setattr(combat, 'resolve_hit', lambda *a, **kw: (10**9, 0))
    combat.apply_hits(s, [(10000, [0])], game.send_troop_hp,
                      lambda *a: pytest.fail('protected airship died'), attacker=11000, attack=attack)
    assert combat.Battle.total(ship) == before
    assert 10000 not in s.data.get('down', set())


def test_untouchable_does_not_protect_enemies_and_can_be_released(monkeypatch):
    s = mission_room(10361)
    battle = s.data['battle']
    assert {u for u, t in battle.troops.items() if t.get('untouchable')} == {10000}
    game.spawn_force(s, 20000)
    enemy = next(u for u,t in s.data['zone_troops'].items() if t.get('ForceNum') == 20000)
    monkeypatch.setattr(combat, 'resolve_hit', lambda *a, **kw: (1, 0))
    before = combat.Battle.total(battle.troops[enemy])
    combat.apply_hits(s, [(enemy, [0])], game.send_troop_hp, lambda *a: None, attacker=10000)
    assert combat.Battle.total(battle.troops[enemy]) == before - 1
    director.run(s, ('untouchable troop', 10000, 0))
    before = combat.Battle.total(battle.troops[10000])
    combat.apply_hits(s, [(10000, [0])], game.send_troop_hp, lambda *a: None, attacker=enemy)
    assert combat.Battle.total(battle.troops[10000]) == before - 1


def test_untouchable_only_queues_for_existing_troops():
    s = mission_room(10361)
    s.sent.clear()
    director.run(s, ('untouchable troop', 65000, 1))
    assert not s.sent


def test_airship_camera_attaches_before_the_opening_dialogue():
    s = mission_room(10361)
    actions = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    attach = struct.pack('<III', 0xe68c, 10000, 2)  # attachment channel 2 -> camera axis 5
    camera = struct.pack('<II', 0xe682, 30003)       # shipped Mist Field interactive camera
    assert attach in actions
    default = struct.pack('<IIII', 0xe6b9, 0xffffffff, 30003, 0xffffffff)
    tactical = struct.pack('<II', 0xe682, 10054)
    assert actions[actions.index(attach) + 1:actions.index(attach) + 4] == [tactical, default, camera]
    opening = next(i for i, b in enumerate(actions)
                   if struct.unpack_from('<I', b)[0] == director.ACT_HELP_TEXT_BY_TROOP)
    assert actions.index(camera) < opening


def test_camera_waits_for_ship_bind_after_startup_control_mode():
    # Native cold entry 2026-10-09 14:51 sent the camera before the ship bound;
    # the trailing control-mode initialization then left camera10054 selected.
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data.update(spot=10361, difficulty=0)
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    game.troop_bound(s, 0)
    next(fn for delay, fn in s.pending if delay == 1.0)()
    reset = struct.pack('<I', director.ACT_CAMERA_RESTORE_DEFAULT)
    assert reset in [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    next(fn for delay, fn in s.pending if delay == 3.0)()
    attach = struct.pack('<III', 0xe68c, 10000, 2)
    camera = struct.pack('<II', 0xe682, 30003)
    protected = struct.pack('<IIII', 0xea9c, 0, 10000, 1)
    actions = lambda: [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    assert attach not in actions() and camera not in actions() and protected not in actions()
    mode = struct.pack('<II', game.ACT_CONTROL_MODE, 0)
    assert actions().count(mode) == 1
    assert actions().index(reset) < actions().index(mode)
    bar = struct.pack('<7I', game.ACT_SITUATION_TROOPS_BAR, 0xff, 0, 8570, 0, 10000, 10000)
    assert bar not in actions()                      # the client builds the bar from the troop it finds then
    game.troop_bound(s, 10000)
    assert protected in actions() and actions().index(protected) < actions().index(attach)
    assert actions().count(bar) == 1
    default = struct.pack('<IIII', 0xe6b9, 0xffffffff, 30003, 0xffffffff)
    tactical = struct.pack('<II', 0xe682, 10054)
    assert actions()[-4:] == [attach, tactical, default, camera]
    assert actions().index(mode) < actions().index(attach)
    game.troop_bound(s, 10000)  # duplicate bind must not reset the player's camera
    assert actions().count(attach) == actions().count(default) == actions().count(camera) == 1

def test_camera_does_not_switch_to_an_absent_troop():
    s = mission_room(10361)
    s.sent.clear()
    director.run(s, ('camera troop', 65000, 30003))
    assert not s.sent


def test_camera_preset_cannot_accidentally_release_a_cutscene_wait():
    s = mission_room(10361)
    s.sent.clear()
    director.run(s, ('camera troop', 10000, -1))
    assert not s.sent


def test_the_sortie_opens_with_the_take_off_and_nothing_more():
    # 8100 "Our destination is New Hampton" (Glen), 8110 (Thompson), 8120 "This Lunawing can also attack!" (Golden
    # Hammer); the remnants' 8130 waits for the bound 시작
    s = mission_room(10361)
    assert lines_shown(s) == [(GLEN, 0, 8100)]
    run_pending(s)
    assert lines_shown(s) == [(GLEN, 0, 8100), (THOMPSON, 0, 8110), (GOLDEN_HAMMER, 0, 8120)]


def test_the_encablossians_follow_the_airship_at_their_bound_once():
    s = mission_room(10361)
    run_pending(s)
    walk(s, 214490, 172003)                                  # 엔카가이상하군요 "the Encablossians are strange"
    run_pending(s)
    walk(s, 214490, 172003)
    run_pending(s)
    scene = [(uid, line) for uid, _, line in lines_shown(s) if 8180 <= line <= 8290]
    # the tape (part 3, frames 3:18-3:52): Jager's 8180, Jade's 8190, Glen's 8250 "Let's just take care of the
    # surrounding Encablossians and get out of here." (3:44), Golden Hammer's 8270 "Let's attack them one more time
    # before we go!" (3:50); the draft 8200 / 8210 ("The longer we stay here ...", "Let's get out of here") never shows
    assert scene == [(0xFFFF, 8180), (JADE, 8190), (GLEN, 8250), (GOLDEN_HAMMER, 8270)]    # Jager: not in the room
    assert 8130 not in [line for _, _, line in lines_shown(s)]  # 시작 was never entered


def test_the_head_cannons_warning_comes_as_the_remnants_cannons_can_target_the_ship():
    # Thompson's 8240 "Ah, watch out! There are Head Cannons around here!": his box at 3:07.50, a head cannon walking
    # into view ahead of the ship, 10 s before Jager's 8180 at 엔카가이상하군요 (frames 3:05-3:10, build/order-b
    # captures/order-b/p3_luna_8240_zoom.jpg), the ship abreast of the remnants' head cannons 10308 / 10309. Ours:
    # within their acquisition range (165030 RANGE_ACQUISITION 6000), alone; force 21000's wake says nothing now
    s = mission_room(10361)
    run_pending(s)
    director.run(s, ("wake", 20000, 21000))
    run_pending(s)
    told = len(lines_shown(s))
    cannon = s.data["zone_troops"][10309]
    for dx in (7000, 6100):                                  # beyond its reach (10308 too)
        walk(s, cannon["PosX"] - dx, cannon["PosZ"])
        run_pending(s)
    assert lines_shown(s)[told:] == []
    walk(s, cannon["PosX"] - 5900, cannon["PosZ"])
    run_pending(s)
    walk(s, cannon["PosX"], cannon["PosZ"] - 1900)           # abreast: once
    run_pending(s)
    assert [(uid, line) for uid, _, line in lines_shown(s)[told:]] == [(THOMPSON, 8240)]


def test_the_head_cannons_reach_is_measured_from_where_they_were_last_seen():
    # the host's position reports (0x50b0, s.data["last_pos"]) move a walking head cannon; one never in the room
    # (its force held) warns of nothing
    s = mission_room(10361)
    run_pending(s)
    cannon = next(t for t in s.data["waves"][0] if t["TroopID"] == 10309)
    walk(s, cannon["PosX"] - 3000, cannon["PosZ"])             # its force not in yet: no warning (the walk wakes it)
    assert 8240 not in [line for _, _, line in lines_shown(s)]
    far = (cannon["PosX"] + 20000, 0, cannon["PosZ"])
    s.data.setdefault("last_pos", {}).update({10308: far, 10309: far})
    walk(s, cannon["PosX"] - 2000, cannon["PosZ"])
    run_pending(s)
    assert 8240 not in [line for _, _, line in lines_shown(s)]
    walk(s, far[0] - 4000, far[2])
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)].count(8240) == 1


def test_force_22000s_bound_brings_it_in_without_golden_hammers_line():
    s = mission_room(10361)
    run_pending(s)
    told = len(lines_shown(s))
    walk(s, 208991, 204153)                                  # 포스활성화_22000 "force 22000 activates"
    run_pending(s)
    assert any(t.get("ForceNum") == 22000 for t in s.data["zone_troops"].values())
    assert 8270 not in [line for _, _, line in lines_shown(s)[told:]]        # (F23000 nearby may wake: 8290)


def bars(s):
    return [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from('<I', bytes(w.buf))[0] == game.ACT_SITUATION_TROOPS_BAR]


def test_the_lunawing_shield_bar_follows_the_airship_from_the_take_off():
    # the original (part 3, frames 2:30, 3:40, 4:30): under the quest tracker a box with the airship's icon, "Lunawing
    # Shield" (8570) and a cyan bar, full throughout (the ship is untouchable); ActGuiAddTroopsBarToMissionSituation on
    # troop 10000, its portrait the bar's icon (a6)
    s = mission_room(10361)
    assert bars(s) == [struct.pack('<7I', game.ACT_SITUATION_TROOPS_BAR, 0xff, 0, 8570, 0, 10000, 10000)]


def test_the_destination_wins_at_once_after_the_scenes_on_the_way():
    # the map has no Sortie I ending (the story goes on in 10362's text): Jade's scene plays on the way, and 목적지
    # wins without waiting; no result window (decision B2: no reward or grade row), the room is left
    s = mission_room(10361)
    run_pending(s)
    walk(s, 205077, 222867)                                  # 제이드_대사
    run_pending(s)
    assert lines_shown(s)[-2:] == [(JADE, 0, 8220), (GOLDEN_HAMMER, 0, 8230)]
    walk(s, 191505, 272969)                                  # 목적지
    assert s.data.get("mission_won")
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 0
    assert sum(w.proto == game.S2C_MISSION_LEAVE for w in s.sent) == 1
    run_pending(s)
    assert lines_shown(s)[-1] == (GOLDEN_HAMMER, 0, 8230)

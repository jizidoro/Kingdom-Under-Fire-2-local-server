"""New Hampton Castle's director table (kuf2/scenes/m10235.py): the opening, the trebuchet's lessons, the siege of
the wall, Vert's summons, his escape as the win."""
import heapq
import itertools
import struct
import time
import types

import pytest

from kuf2 import combat, director, game, obf
from test_battle import NoSave, acts, mission_room, opened, walk
from test_director import (answer, cutscenes, lines_shown, obey, press, prompts, queries, rooms_at_cutscenes,
                           run_pending)
from test_scenes_10233 import closes, tutorials

GLEN, DURAN, THOMPSON = 40000, 40001, 40002       # force 40000's 글렌 / 듀란 / 톰슨
VERT = 49400
WALL, STAGING_WALL = 49444, 23504


def wake_force(s, force):
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == force), "test")


def done(s):
    return [a[2] for a in acts(s, game.ACT_SITUATION_DONE)]


def test_the_castle_opens_with_thompson_glen_and_duran_then_the_order_to_fire():
    s = mission_room(10235)
    assert cutscenes(s) == [0] and lines_shown(s) == []      # 0_Start voices 15000-15050
    run_pending(s)
    assert lines_shown(s) == [(GLEN, 1, 5000)]              # the troop skill lesson waits for the player
    obey(s)
    assert lines_shown(s) == [(GLEN, 1, 5000), (GLEN, 1, 5010)]     # the original: 5000, the lessons, 5010


def test_the_troop_skill_lesson_waits_for_ctrl_a():
    # the original (part 3 25:58-26:08, 1_TroopSkill_Tuto): 13502's two F pages (the client's), then "Ctrl + A: Use
    # the Trebuchet Troop's Fireball skill", which its cutscene waited on as KEY_UseAbilityC9 (the third troop's first
    # skill; the pop-up's text names Ctrl + 1 / Q / A for troops 1 / 2 / 3). No 135_Select_TroopSlot3_Enter: the
    # footage shows none (25:52-26:14), and no script of the map starts 13501
    s = mission_room(10235)
    run_pending(s)
    assert tutorials(s) == ["135_TroopSkill_Short_Cut9"]
    [(serial, cond, args)] = queries(s)
    assert cond == director.COND_TUTORIAL_PAST and args == b"135_TroopSkill_Short_Cut9\0" + struct.pack("<i", 1)
    answer(s, serial, False)                          # on its F pages: nothing prompted
    run_pending(s)
    assert 0x2b not in prompts(s).values()
    [(serial, _, _)] = [q for q in queries(s) if q[0] != serial]
    answer(s, serial, True)
    assert 0x2b in prompts(s).values()
    press(s, 0x23)                                    # Ctrl + 1: the first troop's skill, not the trebuchet's
    run_pending(s)
    assert closes(s) == [] and tutorials(s) == ["135_TroopSkill_Short_Cut9"] and 5010 not in [
        line for _, _, line in lines_shown(s)]
    press(s, 0x2b)
    assert closes(s) == [director.ACT_FINISH_TUTORIAL]          # three pages: closed (0xc898 would show page 2 again)
    run_pending(s)
    assert tutorials(s)[-1] == "135_TroopSkill_Use" and lines_shown(s)[-1] == (GLEN, 1, 5010)


def test_the_wall_lesson_shows_after_glens_order_and_closes_on_the_target_click():
    # "Select a castle wall." (13503, one page) after Glen's 5010: his box at 26:13.00, the pop-up at 26:14.00 (frames,
    # build/order-b captures/order-b/p3_nh_5010.jpg; the original's 1_TroopSkill_Tuto started 13503 once its server
    # released System_WaitState(-11)); it left only the target keys live for it (KEY_SelectTarget, KEY_Interaction) and
    # waited on its server (System_WaitState(-12)). The fireball (200139) is FocusType GROUND: the pick is the left
    # button while targeting, KEY_SelectTarget; a right button order (KEY_Interaction) moves troops too, so it does not
    # close it. "Use Trebuchet skill (Complete)" at 26:20, before the first hit
    s = mission_room(10235)
    obey(s, rounds=1)                                 # the Ctrl + A lesson's page: asked and shown
    press(s, 0x2b)
    run_pending(s)                                    # (the test's clock stands: 5000's time on screen is not over)
    sent = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    act = lambda b: struct.unpack_from("<I", b)[0]
    shown = next(i for i, b in enumerate(sent) if act(b) == director.ACT_START_TUTORIAL and b"135_TroopSkill_Use" in b)
    told = next(i for i, b in enumerate(sent) if act(b) == director.ACT_HELP_TEXT_BY_TROOP
                and struct.unpack_from("<6I", b)[4] == 5010)
    assert tutorials(s)[-1] == "135_TroopSkill_Use" and told < shown      # after Glen's line, not before it
    [(serial, cond, args)] = [q for q in queries(s) if q[0] not in s.answered]
    assert cond == director.COND_TUTORIAL_PAST and args == b"135_TroopSkill_Use\0" + struct.pack("<i", -1)
    shut = len(closes(s))
    press(s, 0x81)                                    # before the pop-up shows: no prompt yet
    s.answered.add(serial)
    answer(s, serial, True)
    assert 0x81 in prompts(s).values()
    press(s, 0x83)                                    # a right button order: not the pick
    run_pending(s)
    assert len(closes(s)) == shut and 430 not in done(s)
    press(s, 0x81)
    assert closes(s)[shut:] == [director.ACT_COMPLETE_TUTORIAL] and 430 in done(s)
    # the circle fills and the box goes: pick about 26:18, full 26:20, gone 26:21 (frames, part 3). 0xc898 alone only draws
    # the circle: live 2026-11-05 10:21 the box stayed for minutes
    run_pending(s, 3)
    assert closes(s)[shut:] == [director.ACT_COMPLETE_TUTORIAL, director.ACT_FINISH_TUTORIAL]


def test_the_panel_shows_under_its_title_as_the_opening_ends():
    # the original's panel under "New Hampton Castle" (100, the red bar) with "Mission Success / Enter New Hampton
    # Castle / Mission Failure / Let Hero and all ally Troops die" as the HUD returns after 0_Start (25:51.50), then
    # "Tutorial / Use Trebuchet skill" (25:52.25-25:52.50), before Glen's 5000 (25:53.50): frames, build/order-b
    # captures/order-b/p3_nh_panel_zoom.jpg. Ours sent it untitled with the scene, before its subtitles
    s = mission_room(10235)
    assert acts(s, game.ACT_SITUATION_TITLE) == [] and acts(s, game.ACT_SITUATION_LINE) == [] and cutscenes(s) == [0]
    run_pending(s)
    sent = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    act = lambda b: struct.unpack_from("<I", b)[0]
    title = next(i for i, b in enumerate(sent) if act(b) == game.ACT_SITUATION_TITLE)
    lines = [i for i, b in enumerate(sent) if act(b) == game.ACT_SITUATION_LINE]
    scene = next(i for i, b in enumerate(sent) if act(b) == director.ACT_CUTSCENE)
    order = next(i for i, b in enumerate(sent) if act(b) == director.ACT_HELP_TEXT_BY_TROOP)
    assert struct.unpack_from("<3I", sent[title])[2] == 100
    assert [struct.unpack_from("<4I", sent[i])[2:] for i in lines] == [(200, 210), (300, 310), (420, 430)]
    assert scene < title < lines[0] and lines[-1] < order and struct.unpack_from("<6I", sent[order])[4] == 5000


def test_the_first_objective_completes_with_durans_call_past_the_wall():
    # the tape: Glen's 5300 (28:33.50) with the notice 1020 / 1030 (28:34.50), Duran's 5310 (28:38); past the wall
    # "Enter New Hampton Castle (Complete)" and "Reach the entrance to the town with Duran" (28:55.25) as Duran's 5320
    # comes (28:55.75), then the notice 1050 / 1060 (29:02): frames, build/order-b captures/order-b/p3_nh_220_zoom.jpg.
    # Ours completed it and added 220 with 5300
    s = mission_room(10235)
    obey(s)
    del s.sent[:]
    director.run(s, ("wake", 20100))
    for u in [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 20100 and game.hostile(t)]:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    seen = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto != game.S2C_SCRIPT_ACTION:
            continue
        a = struct.unpack_from("<I", b)[0]
        if a == director.ACT_HELP_TEXT_BY_TROOP:
            seen.append(struct.unpack_from("<6I", b)[4])
        elif a == director.ACT_NOTICE_WINDOW:
            seen.append(struct.unpack_from("<6I", b)[2])
        elif a == game.ACT_SITUATION_DONE:
            seen.append(("done", struct.unpack_from("<4I", b)[2]))
        elif a == game.ACT_SITUATION_LINE:
            seen.append(struct.unpack_from("<4I", b)[3])
    assert seen[seen.index(5300):seen.index(1050) + 1] == [5300, 1020, 5310, ("done", 210), 220, 5320, 1050]


def test_the_fireball_ctrl_a_throws_at_the_wall():
    # 200140 (the lesson's Ctrl + A) only puts 2001100 on the trebuchet, whose function TROOP_PROCSKILL fires 200139 on its
    # ranged attack. Live 2026-11-05 10:20:59, 10:22:13: two casts, the bar stayed full; 200139 by hand took 1,010 hp
    from kuf2 import combat, procs, status
    s = mission_room(10235)
    obey(s)
    s.sent.clear()
    status.on_execute(s, 7, 200140, 40100, [(WALL, 0)])
    # 200139 is a TROOPACTION: 0x50af refuses it ("Server request ability must none action skill", live 11:00:01 and 11:10:07
    # no shot came), so the troop is told to use it (0xc3df), and its own 0x505f throws it (live 11:13:28)
    assert not [w for w in s.sent if w.proto == procs.S2C_DO_ABILITY]
    assert acts(s, game.ACT_TROOP_USE_SKILL) == [[game.ACT_TROOP_USE_SKILL, 40100, WALL, 0, 200139]]
    status.on_execute(s, 7, 200140, 40100, [(WALL, 0)])                         # a second execute of the cast: no second shot
    assert len(acts(s, game.ACT_TROOP_USE_SKILL)) == 1


def test_the_siege_is_fought_on_the_wall_the_player_can_select():
    # the frames of part 3 26:14-27:24: the target is "Lv.8 Castle Wall" with its own hp bar (a HUD-visible row:
    # 135200, troop 49444, 2,217 hp; the staging segments 135380 hide theirs), right ahead of the trebuchet 40100
    # (x 120,166 vs 119,892); "Castle Wall Durability" falls 100 -> 64 -> 14 -> 0 % in three shots (27:08, 27:24),
    # as 49444 does under the trebuchet's fireball here (100 -> 58 -> 17 -> 0); 23504 (17,739 hp) would take 11
    s = mission_room(10235)
    troops = s.data["zone_troops"]
    assert WALL in troops and game.hostile(troops[WALL])
    obey(s)
    top = s.data["battle"].troops[WALL]["max"]
    assert top == 2217
    director.on_hp(s, STAGING_WALL, 1, s.data["battle"].troops[STAGING_WALL]["max"])
    run_pending(s)
    assert 5020 not in [line for _, _, line in lines_shown(s)]
    s.data["battle"].troops[WALL]["units"] = [top * 58 // 100]      # the first shot (the frames: 64 %)
    director.on_hp(s, WALL, top * 58 // 100, top)
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)][-5:] == [5020, 5030, 5100, 5110, 5120]   # the original 26:28-27:04,
    bars = acts(s, game.ACT_SITUATION_GAUGE)                                                 # all at 64 %
    assert bars and bars[-1][2:5] == [400, 401, (top * 58 // 100) * 100 // top]
    assert not opened(s)
    game.mission_troop_down(s, NoSave(), WALL)
    run_pending(s)
    assert cutscenes(s)[-1] == 2 and any(t.get("ForceNum") == 20100 for t in troops.values())
    assert opened(s) == {19211}      # the breach: the vanishing collision prop (type 232) just behind 49444 (x
                                     # 120,008 vs 119,892), with the swarm F20100


def wall_breaks(s):
    return [bytes(w.buf) for w in s.sent if w.proto == game.S2C_PROP_SET_STATE]


def test_the_walls_fall_breaks_the_composite_it_is_linked_to():
    # the footage has a hole in the wall by 27:32, the troops cross it at 28:42. 49444 is a UnitProp standing on composite
    # 19214 (its zone row: LinkedComositeProp); live 2026-11-05 the fallen troop left the wall whole and solid, NO_PATH
    # through it, until 0x50a3 (the only way to 0x14091a0f0, which walks a composite's links) put 19214 in TYPE_DESTORY:
    # collision off, the breach drawn, the hero walked through
    s = mission_room(10235)
    obey(s)
    assert s.data["zone_troops"][WALL]["LinkedComositeProp"] == 19214
    assert not wall_breaks(s)
    game.mission_troop_down(s, NoSave(), WALL)
    assert wall_breaks(s) == [obf.u32(19214) + struct.pack("<i", 4)]


def test_a_troop_with_no_composite_breaks_nothing():
    # F20030 on the battlements links to no prop; 23513 links to 18004, which this zone does not place
    s = mission_room(10235)
    obey(s)
    troops = s.data["zone_troops"]
    archer = next(u for u, t in troops.items() if t.get("ForceNum") == 20030)
    game.mission_troop_down(s, NoSave(), archer)
    assert troops[23513]["LinkedComositeProp"] == 18004
    game.mission_troop_down(s, NoSave(), 23513)
    assert not wall_breaks(s)


def marched_to(s, area):
    return {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == area}


def test_the_army_advances_and_the_swarm_comes_out_of_the_breach():
    # the footage: the infantry out in the field by 27:10, its melee with the swarm in front of the wall at 27:38, the
    # line at the breach by 28:30, "Everyone, enter the castle!" 28:34, a marked ring past the wall at 28:46. Live
    # 2026-11-05 11:15 nobody moved: the army stood on its start line (z 111,000), F20100 behind the wall (z 132,000). The
    # map names the places: 11000 P1_보병방어이동 (a line across the field, "Advance in defensive formation!"; the frames
    # have one wide line at 27:14), P1_좌측보병돌격 10030, 12000 past the breach, P3_시가지시작_영웅 11213
    s = mission_room(10235)
    obey(s)
    troops = s.data["zone_troops"]
    mine = set(s.data["plan"]["hand"])
    force = lambda f: {u for u, t in troops.items() if t.get("ForceNum") == f} - mine
    top = s.data["battle"].troops[WALL]["max"]
    assert not marched_to(s, 11000)
    s.data["battle"].troops[WALL]["units"] = [top * 58 // 100]
    director.on_hp(s, WALL, top * 58 // 100, top)
    run_pending(s)
    assert marched_to(s, 11000) == force(10000) | force(10001)
    assert {a[4] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == 11000} == {director.MOVE_NEAREST}
    game.mission_troop_down(s, NoSave(), WALL)
    run_pending(s)
    assert force(20100) and force(20100) <= marched_to(s, 11000)       # to the line, not past it: live 12:24 two stood
                                                                       # idle behind it at 10030, the mission waiting on them
    assert not marched_to(s, 12000)
    fell(s, 20100)
    run_pending(s)
    assert force(10000) | force(10001) <= marched_to(s, 11211)
    assert force(10010) <= marched_to(s, 11212)
    assert force(40000) == marched_to(s, 11213)
    assert [a[1] for a in acts(s, director.ACT_HIGHLIGHT_AREA)][-1:] == [12000]


def test_the_call_to_enter_does_not_wait_for_the_stragglers(monkeypatch):
    # three live runs on 2026-11-05 ended on the same few of F20100 no one fought, one stuck at (115230, 130208) where the
    # hero cannot walk; the tape's 5300 (28:34) plays with reds still about
    s, clock, fell_at, rest = breach_on_seconds(monkeypatch, 5)
    clock.to(fell_at + 100)
    assert 5300 not in [l for _, l in clock.shown]
    game.mission_troop_down(s, NoSave(), rest[0])
    assert clock.at(5300) - fell_at < 110
    for u in rest[1:]:
        game.mission_troop_down(s, NoSave(), u)
    clock.to(clock.now + 600)
    assert [l for _, l in clock.shown].count(5300) == 1


def test_the_town_defenders_come_with_the_town_scene():
    # live 2026-11-05 12:22: the chase through the breach woke 51 of F21000 before 5300, the tape has them after the town
    # scene (5430 "Stop the dogs of Hironeiden!", 31:0x)
    s = mission_room(10235)
    obey(s)
    defenders = lambda: {u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 21000}
    assert 21000 in director.held(10235) and not defenders()
    walk(s, 115000, 131000)                             # past the breach, among them
    run_pending(s)
    assert not defenders()
    b = director.bound(10235, "P3_시가지시작_영웅")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert len(defenders()) == 54


def test_the_allies_take_the_maps_lanes_through_the_town():
    # the tape fights the town beside the orange infantry (33:20-35:00), and the map names their way: P3_시가지시작_보병 11211 /
    # 궁병 11212, P3_2_아군이동 13202, 아군이동2 13203, P3_3_아군이동 13330. Live 2026-11-05 14:02: 49 of 52 alive and still by the wall,
    # z 125,000, the hero alone at the last line, z 151,000: nothing marched them past the breach. A march is dropped once
    # they engage (troop 10002 chased the swarm and stopped at (115039, 140134)), so each stage orders them again. Moments
    # ours [I]: the map has the places, not when
    s = mission_room(10235)
    obey(s)
    troops = s.data["zone_troops"]
    mine = set(s.data["plan"]["hand"])
    force = lambda f: {u for u, t in troops.items() if t.get("ForceNum") == f} - mine
    army = lambda: force(10000) | force(10001)
    orders = lambda area: [a[2] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == area]
    game.mission_troop_down(s, NoSave(), WALL)
    run_pending(s)
    fell(s, 20100)
    before = len(orders(11211))
    assert army() <= set(orders(11211))
    b = director.bound(10235, "P3_시가지시작_영웅")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert len(orders(11211)) == before + len(army())   # after the scene, for those a fight stopped
    for lane, stage in ((13202, lambda: wake_force(s, 21310)), (13203, lambda: fell(s, 21310)),
                        (13330, lambda: wake_force(s, 21400))):
        assert not orders(lane)
        stage()
        run_pending(s)
        assert army() | force(40000) <= set(orders(lane)), lane


def test_the_march_through_the_breach_ignores_the_wall_top():
    # live 2026-11-05 14:52: F10000 stood at (112000-113000, 129000), its engages on 2025x, the wall-top shooters it can never reach,
    # and the archers stayed at z 115,000 shooting them: a march that fights what it meets stopped for them. Order type 3 goes
    # on past them (engage 0, 0xc3a0); in the town, where the fights are the point, they fight what they meet
    s = mission_room(10235)
    obey(s)
    troops = s.data["zone_troops"]
    mine = set(s.data["plan"]["hand"])
    force = lambda f: {u for u, t in troops.items() if t.get("ForceNum") == f} - mine
    engage = lambda area: {a[5] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == area}
    game.mission_troop_down(s, NoSave(), WALL)
    run_pending(s)
    fell(s, 20100)
    assert engage(11211) == {0} and engage(11212) == {0}
    assert force(10000) | force(10001) <= marched_to(s, 11211) and force(10010) <= marched_to(s, 11212)
    b = director.bound(10235, "P3_시가지시작_영웅")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert engage(11211) == {0}
    wake_force(s, 21310)
    run_pending(s)
    assert engage(13202) == {1}


def test_the_plaza_is_the_maps_own_line_and_the_army_stays_below():
    # the tape: the infantry fights at the last line at 36:40, the hero climbs almost alone (36:50-37:00), its minimap has the squads
    # still in the town at 37:00. The crowd on Vert at 38:30-38:40 is the map's F13000, 6 squads of 9 of the same infantry
    # (135040) in a line across the plaza at z 160,500, not the army. Live 2026-11-05 15:50 with F10000 / F10001 / F10010 sent
    # up (14201, 14300): four archer volleys, 13,900 each, took Vert from 84 % to 24 % in one second during cutscene 4
    s = mission_room(10235)
    obey(s)
    below = {u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") in (10000, 10001, 10010)}
    assert below
    fell(s, 21410)
    fell(s, 21400)
    wake_force(s, 49400)
    run_pending(s)
    assert not marched_to(s, 14201) and not below & marched_to(s, 14300)


def test_the_archers_go_to_their_own_lane_and_no_further():
    # live 2026-11-05: 5300's order took F10010 from z 109,000 to z 114,000-120,000 at 15:07, where they stopped to shoot the swarm
    # and stood until the end: a ranged troop drops its march to fire, engage 0 or not. The map names one lane for them, 11212
    # 궁병, so the order repeats with the town and the cannons, and goes no further: a volley is 35 arrows, 13,900 on a target
    s = mission_room(10235)
    obey(s)
    troops = s.data["zone_troops"]
    mine = set(s.data["plan"]["hand"])
    archers = {u for u, t in troops.items() if t.get("ForceNum") == 10010} - mine
    assert archers
    orders = lambda: len([a for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == 11212 and a[2] in archers])
    game.mission_troop_down(s, NoSave(), WALL)
    run_pending(s)
    fell(s, 20100)
    assert archers <= marched_to(s, 11212)
    once = orders()
    b = director.bound(10235, "P3_시가지시작_영웅")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert orders() == 2 * once
    wake_force(s, 21310)
    run_pending(s)
    assert orders() == 3 * once
    fell(s, 21310)
    wake_force(s, 21400)
    run_pending(s)
    assert not archers & (marched_to(s, 13202) | marched_to(s, 13203) | marched_to(s, 13330))


def test_all_clear_does_not_wait_for_the_four_behind_the_rubble():
    # four of the eight rabble stand at (128098-128545, 146432-148557), north of the fallen building 11002: closed from the
    # cannons, reached only round the west street past the last line. Live 2026-11-05 13:58: the near four down, the cannons
    # down, 5570 never came and the hero met 5600 first. The tape has 5570 eight seconds after 5560 (35:02), no red near
    # him, then 5600 at 35:14: ours [I], as 5300
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 21300)
    rabble = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 21300]
    said = lambda: [line for _, _, line in lines_shown(s) if line in (5560, 5570)]
    fell(s, 21310)
    assert said() == [5560]
    for u in rabble[:3]:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    assert said() == [5560]
    game.mission_troop_down(s, NoSave(), rabble[3])
    run_pending(s)
    assert said() == [5560, 5570]
    for u in rabble[4:]:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)
    assert said() == [5560, 5570]


def test_the_wall_top_shooters_fire_for_show():
    # live 2026-11-05 F20030's 64,879 hits dealt 697,750 in four minutes and wiped F10000 (the swarm dealt 40 k); the tape's
    # line stands whole under that fire at 27:18, no red number on it, the player's troops at full hp, the shooters still
    # on the wall at 28:34 (135620 / 135670: staging, range 20,000, EXP 0, no HUD)
    s = mission_room(10235)
    troops = s.data["battle"].troops
    shooters = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") in (20030, 49000)]
    assert len(shooters) == 45                             # with the opening's staging force (mages 49003 / 49004, 135270)
    infantry = troops[10002]["c"]
    for uid in shooters:
        c = troops[uid]["c"]
        assert combat.resolve(c, infantry, combat.hit_attack(c, 0)) == 0
    # the mages' purple meteor 200189 took a whole troop a cast (live 12:36: 18,132 of 18,132), whatever their attack
    assert combat.resolve(troops[49003]["c"], infantry, {"kill": True}) == 0
    assert combat.resolve(troops[49003]["c"], infantry, {"fixed": 500}) == 0
    c = troops[10002]["c"]
    assert combat.resolve(c, troops[shooters[0]]["c"], combat.hit_attack(c, 0)) > 0
    assert combat.np_combatant(135620)["atk"]["PHYSICAL"][0] > 0       # the shared record keeps its attack


def test_the_staging_bombardment_stays_off_the_field():
    # the 23 wall cannons F20070 (135280 "연출공격력20배": ATK x20 = 1,797.8, HUD hidden, EXP 0): live 2026-09-28
    # 03:10:56 (captures/game_20260928_030946) cannon 20088's first volley took the player's trebuchet 40100 from
    # 5,449 to 0; in the original the player's troops kept full hp through the shelling (part 3 26:16-29:52: F1 / F2 /
    # F3 bars at their max). The wall-top shooters F20030 stay (Glen's 5100 "Archers! Attack those on the
    # battlements!")
    s = mission_room(10235)
    obey(s)
    forces = {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    assert 20070 not in forces and 20030 in forces


def fell(s, force):
    """Every troop of force (woken first when it is still held) falls."""
    if not any(t.get("ForceNum") == force for t in s.data["zone_troops"].values()):
        wake_force(s, force)
    for u in [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == force]:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)


def test_all_clear_comes_after_the_cannons_whichever_falls_first():
    # the tape (part 3, frames 34:52-35:14): Duran's "Good job! Now, wipe out the rest of the rabble!" (5560, 34:54) as
    # the cannons F21310 fall, "All clear! Now, let's go after Vert!" (5570, 35:04) once the rabble F21300 is down too;
    # its words need both down, the cannons' line first. The rabble falling first (the headless run, a player who
    # clears the street before the cannons) waited for nothing and said "All clear!" before the cannons were seen
    s = mission_room(10235)
    run_pending(s)
    fell(s, 21300)
    assert 5570 not in [line for _, _, line in lines_shown(s)]
    fell(s, 21310)
    town = [line for _, _, line in lines_shown(s) if line in (5560, 5570)]
    assert town == [5560, 5570]


def test_the_staircase_waits_for_the_last_cannons_too():
    # the same for the last line of defence: "Good job! Come on, let's go up this staircase!" (5640) after "You took
    # care of the cannons!" (5630, 36:24), not before the cannons F21410 have come
    s = mission_room(10235)
    run_pending(s)
    fell(s, 21400)
    assert 5640 not in [line for _, _, line in lines_shown(s)]
    fell(s, 21410)
    assert [line for _, _, line in lines_shown(s) if line in (5630, 5640, 5650)] == [5630, 5640, 5650]


def until(s, line, limit=500):
    """Run what the room scheduled, in delay order, until line has been shown."""
    for _ in range(limit):
        if line in [l for _, _, l in lines_shown(s)]:
            return
        s.pending.sort(key=lambda p: p[0])
        s.pending.pop(0)[1]()
    raise AssertionError(f"line {line} never came")


def test_vert_summons_his_primitives_when_he_comes_and_the_juggernauts_on_the_clock():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    troops = s.data["zone_troops"]
    assert VERT in troops and 24100 not in troops     # the summons wait for 4_Enca_Sommon (15400-15430)
    until(s, 5810)
    assert cutscenes(s)[-1] == 4
    assert 24100 in troops and 24200 in troops and 24300 not in troops
    until(s, 5860)                                    # after his lines
    assert 24300 in troops and 24108 in troops        # the juggernaut 저거너트_좌 (force 24300), force 24400
    assert [line for _, _, line in lines_shown(s)][-3:] == [5840, 5850, 5860]


def test_the_fight_with_vert_keeps_the_tapes_clock():
    # the tape's bar (part 3, frames 2026-11-05): 91.2 % at 5840, 89.1 % at 5880, 88.0 % at 5900, 68.6 % at 5940, and he leaves at
    # 65.7 %; the guide has the summons at 70 % and the escape at 20 %. No hp rule gives both, a clock does: a player dealing a
    # steady 0.45 % a second is at 70 % and 20 % at the tape's two moments. Live 2026-11-05 on hp thresholds the fight took
    # 12 minutes against the tape's 3:14
    clock = {st["do"][-1][2] if st["do"][-1][0] == "say" else st["do"][0][2]: st["s"] for st in director.script(10235)
             if st["on"] == "after" and st.get("step") == "vert"}
    assert clock == {5830: 22, 5860: 52, 5890: 84, 5930: 124, 5940: 174}
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    run_pending(s)
    beats = [5800, 5810, 5820, 5830, 5840, 5850, 5860, 5880, 5890, 5900, 5920, 5930, 5940, 5950, 5960, 5970]
    assert [line for _, _, line in lines_shown(s) if line in beats] == beats


def test_the_reinforcements_come_with_glen():
    # 5900 "I'm here!", 5920 Vert "Bah! Reinforcements?! What a hassle!": they are the map's F46600, two squads of 12 and a leader at
    # (135,000, 166,800). On the tape the bar stands at 88-91 % for over a minute, then falls 22 % in the minute after Glen. Live
    # 2026-11-05 16:16 they came with Vert, on him from the scene's end, 93,428 of the damage
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    troops = s.data["zone_troops"]
    until(s, 5890)
    assert not any(t.get("ForceNum") == 46600 for t in troops.values())
    assert any(t.get("ForceNum") == 13000 for t in troops.values())       # the plaza's own line is there from the start
    until(s, 5900)
    held = {u for u, t in troops.items() if t.get("ForceNum") == 46600}
    assert held and held <= marched_to(s, 14300)


def test_vert_leaves_on_the_clock_whatever_his_hp_and_the_mission_is_won():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    run_pending(s)
    assert cutscenes(s)[-1] == 5                       # 5_End (16000-16080) after the escape's boxes
    assert [(uid, line) for uid, _, line in lines_shown(s)][-4:] == [(VERT, 5940), (VERT, 5950), (DURAN, 5960),
                                                                    (GLEN, 5970)]    # the original, part 3 40:48
    assert VERT in s.data["down"] and VERT not in s.data["battle"].troops                 # he left the field
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1 and s.data["mission_won"]


def test_vert_at_20_percent_escapes_before_the_clock_and_only_once():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    until(s, 5810)
    top = s.data["battle"].troops[VERT]["max"]
    director.on_hp(s, VERT, top * 21 // 100, top)
    assert not s.data.get("mission_won")
    director.on_hp(s, VERT, top * 19 // 100, top)
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")
    run_pending(s)
    lines = [line for _, _, line in lines_shown(s)]
    assert lines.count(5940) == 1 and lines.count(5970) == 1 and 5880 not in lines     # the ending stops the clock
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1 and s.data["mission_won"]


class Seconds:
    """The room on real seconds: run_pending takes each timer in the order of its own delay, so what comes due while lines
    are playing never meets them. Here s.later and the director's clock run on one timeline, line by line."""

    def __init__(self, s, monkeypatch):
        self.s, self.now, self.due, self.order, self.shown, self.seen = s, time.monotonic(), [], itertools.count(), [], 0
        monkeypatch.setattr(director, "time", types.SimpleNamespace(monotonic=lambda: self.now, time=lambda: self.now))

    def to(self, then):
        while True:
            while self.s.pending:
                delay, fn = self.s.pending.pop(0)
                heapq.heappush(self.due, (self.now + delay, next(self.order), fn))
            if not self.due or self.due[0][0] > then:
                self.now = then
                return
            self.now, _, fn = heapq.heappop(self.due)
            fn()
            shown = lines_shown(self.s)
            self.shown += [(self.now, line) for _, _, line in shown[self.seen:]]
            self.seen = len(shown)

    def at(self, line):
        while line not in [l for _, l in self.shown]:
            assert self.due or self.s.pending, f"line {line} never came"
            self.to(self.due[0][0] if self.due else self.now)
        return next(t for t, l in self.shown if l == line)


def vert_on_seconds(monkeypatch):
    s = mission_room(10235)
    clock = Seconds(s, monkeypatch)
    clock.to(clock.now + 3000)                         # the opening's lines, long done when he comes
    wake_force(s, 49400)
    return s, clock, clock.at(5810)


def test_the_beats_show_at_the_tapes_seconds(monkeypatch):
    # part 3, read from 5810 at 37:50; a read is good to 2-4 s, and a line after another comes when that one ends
    tape = {5830: 30, 5840: 56, 5850: 62, 5860: 70, 5880: 88, 5890: 94, 5900: 128, 5930: 142, 5940: 178, 5950: 184, 5960: 192,
            5970: 196}
    s, clock, start = vert_on_seconds(monkeypatch)
    clock.to(start + 600)
    ours = {line: t - start for t, line in clock.shown}
    assert {line: round(ours[line] - second) for line, second in tape.items() if abs(ours[line] - second) > 8} == {}


@pytest.mark.parametrize("after", [15, 21, 25, 50, 55, 80, 85, 120, 125])
@pytest.mark.parametrize("how", ["below 20", "killed"])
def test_no_beat_of_the_clock_comes_once_he_is_on_his_way_out(monkeypatch, after, how):
    # the ending starts after the escape's lines, so the clock's own beats have to close with it: a beat due in those seconds
    # had him taunt the hero (5880) and call his juggernauts with the field already left
    s, clock, start = vert_on_seconds(monkeypatch)
    clock.to(start + after)
    if how == "killed":
        game.mission_troop_down(s, NoSave(), VERT)
    else:
        top = s.data["battle"].troops[VERT]["max"]
        director.on_hp(s, VERT, top * 19 // 100, top)
    clock.to(clock.now + 600)
    lines = [l for _, l in clock.shown]
    assert lines.count(5940) == 1 and lines.count(5970) == 1
    assert not set(lines[lines.index(5940):]) & {5820, 5830, 5840, 5850, 5860, 5880, 5890, 5900, 5920, 5930}
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1


def test_vert_killed_outright_still_wins_once():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    until(s, 5810)
    game.mission_troop_down(s, NoSave(), VERT)
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)].count(5970) == 1
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1


def test_the_ending_gives_the_picture_back_before_the_results():
    # 5_End finishes on a fade to black (its last System_Fade at 80.475 s of 81.165). Live 2026-11-05 14:32 the cards closed onto a
    # black screen with the loading spinner, the Mission Complete button unseen under it; the tape has the plaza and the
    # button (42:05). As Grey Rock's 13_EndScene: the picture comes back after the whole scene, before the result
    ending = next(st for st in director.script(10235) if st["on"] == "won")
    assert next(a[2] for a in ending["do"] if a[:2] == ("cutscene", 5)) > 81.165
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    run_pending(s)
    window = [i for i, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_COMPLETE]
    scene = max(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
                and bytes(w.buf)[:4] == director.ACT_CUTSCENE.to_bytes(4, "little"))
    fades = [i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
             and bytes(w.buf) == struct.pack("<4I", game.ACT_FADE, 1, 0, 1)]
    assert len(window) == 1 and any(scene < i < window[0] for i in fades)


def breach_on_seconds(monkeypatch, standing):
    """The wall down on real seconds, with all but `standing` of F20100 fallen; the room, its clock and the rest."""
    s = mission_room(10235)
    obey(s)
    clock = Seconds(s, monkeypatch)
    clock.to(clock.now + 3000)
    fell_at = clock.now
    game.mission_troop_down(s, NoSave(), WALL)
    swarm = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 20100]
    for u in swarm[:-standing]:
        game.mission_troop_down(s, NoSave(), u)
    return s, clock, fell_at, swarm[-standing:]


def test_the_call_to_enter_comes_on_the_clock_when_the_last_of_the_swarm_stand_out_of_reach(monkeypatch):
    # live 2026-11-05 (20261105_180609): five of F20100 stood where neither the army (z 126,000) nor the hero met them,
    # and nothing else was left to do: 5300 came 1,944 s after the wall, when two runs of 450 s had shown the same thing
    s, clock, fell_at, _ = breach_on_seconds(monkeypatch, 5)
    clock.to(fell_at + 150)
    assert 5300 not in [l for _, l in clock.shown] and not marched_to(s, 11211)
    assert 200 < clock.at(5300) - fell_at < 280
    clock.at(5310)
    assert marched_to(s, 11211)                        # the army moves on with the call, as when the swarm brings it


def test_the_call_to_enter_comes_once_whichever_comes_first(monkeypatch):
    s, clock, _, rest = breach_on_seconds(monkeypatch, 5)
    game.mission_troop_down(s, NoSave(), rest[0])      # four left: the swarm's call, well before the clock
    called = clock.at(5300)
    clock.to(called + 600)
    assert [l for _, l in clock.shown].count(5300) == 1

    s, clock, _, rest = breach_on_seconds(monkeypatch, 5)
    clock.to(clock.at(5300) + 5)                       # the clock's call, then the fifth falls
    game.mission_troop_down(s, NoSave(), rest[0])
    clock.to(clock.now + 600)
    assert [l for _, l in clock.shown].count(5300) == 1


def test_each_scene_is_sent_with_the_troops_its_actor_tracks_bind(monkeypatch):
    # The client starts a scene only once every troop its ACTOR tracks name is in the room (0x1408b3360); a missing
    # one leaves it at black for ever (Grey Rock's 11_Kobold, live 2026-09-30). 3_Into_Castle binds Vert on the gate,
    # 49300 (staging force F49300), and enables him at 0 s. 4_Enca_Sommon binds the summoned Encablossians 49440-49443
    # (F49410), enables them at 28 s and disables them at 35.7 s. 5_End binds GLEN / THOMSON / DURAN, 19500 / 19510 /
    # 19520 of the staging force F19500, and enables that force at 0 s. Each step brings the cast in first
    s = mission_room(10235)
    run_pending(s)
    seen = rooms_at_cutscenes(monkeypatch)
    b = director.bound(10235, "P3_시가지시작_영웅")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    wake_force(s, 49400)
    run_pending(s)
    rooms = dict(seen)
    assert [slot for slot, _ in seen] == [3, 4, 5]
    assert 49300 in rooms[3] and {49440, 49441, 49442, 49443} <= rooms[4] and {19500, 19510, 19520} <= rooms[5]

"""New Hampton Castle's director table (kuf2/scenes/m10235.py): the opening, the trebuchet's lessons, the siege of
the wall, Vert's summons, his escape as the win."""
import struct

from kuf2 import director, game
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


def test_vert_summons_his_primitives_when_he_comes_and_the_juggernauts_below_70_percent():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    troops = s.data["zone_troops"]
    assert VERT in troops and 24100 not in troops     # the summons wait for 4_Enca_Sommon (15400-15430)
    run_pending(s)
    assert cutscenes(s)[-1] == 4
    assert 24100 in troops and 24200 in troops and 24300 not in troops
    top = s.data["battle"].troops[VERT]["max"]
    director.on_hp(s, VERT, top * 75 // 100, top)
    assert 24300 not in troops
    director.on_hp(s, VERT, top * 65 // 100, top)
    run_pending(s)                                    # after his lines
    assert 24300 in troops and 24108 in troops        # the juggernaut 저거너트_좌 (force 24300), force 24400
    assert [line for _, _, line in lines_shown(s)][-3:] == [5840, 5850, 5860]


def test_vert_escapes_at_20_percent_and_the_mission_is_won_after_his_lines_and_the_ending():
    s = mission_room(10235)
    run_pending(s)
    wake_force(s, 49400)
    run_pending(s)
    top = s.data["battle"].troops[VERT]["max"]
    director.on_hp(s, VERT, top * 21 // 100, top)
    assert not s.data.get("mission_won")
    director.on_hp(s, VERT, top * 19 // 100, top)
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")
    run_pending(s)
    assert cutscenes(s)[-1] == 5                       # 5_End (16000-16080) after the escape's boxes
    assert [(uid, line) for uid, _, line in lines_shown(s)][-4:] == [(VERT, 5940), (VERT, 5950), (DURAN, 5960),
                                                                    (GLEN, 5970)]    # the original, part 3 40:48
    assert VERT in s.data["down"] and VERT not in s.data["battle"].troops                 # he left the field
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1 and s.data["mission_won"]


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
    top = s.data["battle"].troops[VERT]["max"]
    director.on_hp(s, VERT, top * 19 // 100, top)
    run_pending(s)
    rooms = dict(seen)
    assert [slot for slot, _ in seen] == [3, 4, 5]
    assert 49300 in rooms[3] and {49440, 49441, 49442, 49443} <= rooms[4] and {19500, 19510, 19520} <= rooms[5]

"""Training Camp (Artilleryman) 10347: the director's table (kuf2/scenes/m10347.py) in a mission room, against the
original's run (playthrough part 9 13:16-16:16; the frames read in the table's docstring)."""
from kuf2 import director, game
from test_battle import NoSave, acts, mission_room
from test_director import lines_shown, press, prompts, run_pending
from test_scenes_10345 import down, handed, hit, left, notices, panel, said

JAGER, TUTOR, MOCK = 49001, 10000, (12000, 12001, 12002)
TOWERS, INFANTRY = (21003, 21004), (21000, 21001, 21002)
RIGHT = director.KEY_RIGHT_ORDER


def forces(s):
    return {t.get("ForceNum") for t in s.data["zone_troops"].values()}


def to_the_mock_battle(s):
    run_pending(s)
    hit(s, TOWERS[0], TUTOR)
    run_pending(s)
    down(s, *TOWERS, *INFANTRY)


def test_the_lesson_opens_on_one_mortar_the_watchtowers_and_the_melee():
    # 13:34-13:40: F1 alone, 36,048 hp (PC_TutoTroop: 16 x 2,253); two watchtowers among the enemy infantry, our
    # infantry (F11000, F21000's mirror) fighting them; Jager (49001, active in the zone) speaks
    s = mission_room(10347)
    assert handed(s) == [TUTOR] and s.data["battle"].troops[TUTOR]["max"] == 36048
    assert {*TOWERS, *INFANTRY, 11000, 11001, 11002, JAGER} <= set(s.data["zone_troops"])
    assert not forces(s) & {23000, 23100, 12000, 13000}
    run_pending(s)
    assert said(s) == [541000, 543070] and lines_shown(s)[0][0] == JAGER and notices(s) == [(546030, 546001)]
    assert director.start_panel(10347) == (540000, ((540100, (540110,)), (540200, (540210, 540220))))


def test_the_splash_waits_for_the_mortars_own_hit_on_a_watchtower():
    # 13:44 "See how its attacks splash damage": the lesson mortar's shell, not our infantry's blows; then "Eliminate
    # all the enemies" with its notice and the panel's next objective (13:56-14:04)
    s = mission_room(10347)
    run_pending(s)
    hit(s, TOWERS[1], 11000)
    run_pending(s)
    assert 543080 not in said(s)
    hit(s, TOWERS[1], TUTOR)
    run_pending(s)
    assert said(s)[-2:] == [543080, 543090] and notices(s)[-1] == (546040, 546041)
    assert panel(s) == ([(540100, 540112)], [540110])


def test_the_mock_battle_comes_when_the_lessons_enemies_are_all_down():
    # 14:24-14:46: the three mortars F1-F3 (36,048 hp each), the lesson one gone; Jager's army with our infantry
    # (F13000, F23000's mirror)
    s = mission_room(10347)
    run_pending(s)
    hit(s, TOWERS[0], TUTOR)
    run_pending(s)
    down(s, *TOWERS)
    assert 542000 not in said(s)                        # the infantry still stand
    down(s, *INFANTRY)                                  # (the test's clock runs every timer: the flank too, below)
    assert said(s)[said(s).index(542000):][:3] == [542000, 542020, 544040]
    assert (545060, 545061) in notices(s)
    assert handed(s) == [TUTOR, *MOCK] and left(s) == [TUTOR]
    assert all(s.data["battle"].troops[u]["max"] == 36048 for u in MOCK)
    assert {23000, 13000} <= forces(s)
    assert panel(s)[1][-1] == 540112 and (540100, 540120) in panel(s)[0]


def test_the_flank_comes_at_the_mortars_and_the_players_move_is_praised():
    # 15:04 "That's a good spot" as the player's mortars fire; 15:18 Jager's flank F23100 marched at them with
    # 544040 and "Enemy Infantrymen are coming from behind you. / Move to a place of safety."; 15:26 the player's move
    s = mission_room(10347)
    to_the_mock_battle(s)
    flank = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 23100]
    assert flank and set(flank) <= {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA)}      # 25 s on (ours)
    assert said(s)[-1] == 544040 and notices(s)[-1] == (546050, 546051)
    army = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 23000]
    hit(s, army[0], 13000)                              # our infantry's blow: not the mortars' good spot
    run_pending(s)
    assert 544030 not in said(s)
    hit(s, army[0], MOCK[1])
    run_pending(s)
    assert said(s)[-1] == 544030
    assert set(prompts(s).values()) >= set(RIGHT)
    press(s, RIGHT[0])
    run_pending(s)
    assert said(s)[-1] == 544070


def test_the_camp_is_won_after_drat_i_lost():
    s = mission_room(10347)
    s.state = NoSave()
    to_the_mock_battle(s)
    for _ in range(3):
        down(s, *[u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", ())])
    assert s.data.get("mission_won") and said(s)[-1] == 544090 and panel(s)[1][-1] == 540120
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1

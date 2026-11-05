"""Training Camp (Spearman) 10349: the director's table (kuf2/scenes/m10349.py) in a mission room, against the
original's run (playthrough part 12 2:50-7:48; the frames read in the table's docstring)."""
from kuf2 import director, game
from test_battle import NoSave, acts, mission_room
from test_director import lines_shown, press, prompts, run_pending
from test_scenes_10233 import closes, tutorials
from test_scenes_10345 import down, handed, hit, left, notices, panel, said

JAGER, SPEARMEN, MOCK = 10002, 10001, (10021, 10022, 10023)
CHARGE, REAR, MORTAR, CAVALRY = 10003, 10004, 10005, 10007
ONE, RIGHT = director.KEY_USE_ABILITY1, director.KEY_RIGHT_ORDER


def at(s, name):
    """The player's spearmen reported inside the bound (0x50b0: game.troop_sync's troop_pos, then the director)."""
    b = director.bound(10349, name)
    s.data["troop_pos"] = {SPEARMEN: (b["BoundCenterX"], 0, b["BoundCenterZ"])}
    game.on_hero_position(s)
    run_pending(s)


def to_cohesion(s):
    run_pending(s)
    at(s, "시작다리입구")
    press(s, ONE)
    run_pending(s)
    down(s, CHARGE)
    press(s, RIGHT[0])
    run_pending(s)
    at(s, "대열이동위치")


def test_the_lesson_opens_on_the_one_spearman_troop_and_jager():
    # 3:10-3:26: F1 alone, 98,720 hp (튜토창병, 20 x 4,936); Jager's name and face on every line; no enemy yet
    s = mission_room(10349)
    assert handed(s) == [SPEARMEN] and s.data["battle"].troops[SPEARMEN]["max"] == 98720
    assert not any(game.hostile(t) for t in s.data["zone_troops"].values())
    run_pending(s)
    assert lines_shown(s) == [(JAGER, 1, 559999), (JAGER, 1, 560000)]
    assert director.start_panel(10349) == (566000, ((566010, (566090,)), (566020, (566060,))))


def test_the_line_change_waits_for_the_bridge_then_its_key():
    # "Move them to the entrance into the bridge" (3:24), "Good job" at the entrance (3:40), "press 1" with its notice
    # (3:50), then 560030 and the charging infantryman (3:52-3:56)
    s = mission_room(10349)
    run_pending(s)
    assert ONE not in prompts(s).values()
    at(s, "시작다리입구")
    assert said(s)[2:] == [560010, 560020] and notices(s) == [(565000, 565001)] and ONE in prompts(s).values()
    assert CHARGE not in s.data["zone_troops"]
    press(s, ONE)
    run_pending(s)
    assert said(s)[-2:] == [560030, 560031] and CHARGE in s.data["zone_troops"]
    assert CHARGE in {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA)}       # at the line


def test_the_slow_march_and_the_attack_from_behind():
    # 4:08-4:48: "Move them over there" (the right button's order), "they move extremely slowly" as they go, the
    # infantry from behind once they reach the marker, 560060 as it strikes, 560061 once it is down
    s = mission_room(10349)
    run_pending(s)
    at(s, "시작다리입구")
    press(s, ONE)
    run_pending(s)
    down(s, CHARGE)
    assert said(s)[-1] == 560040 and notices(s)[-1] == (565010, 565011)
    press(s, RIGHT[1])
    run_pending(s)
    assert said(s)[-1] == 560050 and REAR not in s.data["zone_troops"]
    at(s, "대열이동위치")
    assert said(s)[-1] == 560051 and REAR in s.data["zone_troops"]
    hit(s, SPEARMEN, CHARGE)                            # (fallen) not the rear's: nothing
    run_pending(s)
    assert 560060 not in said(s)
    hit(s, SPEARMEN, REAR)
    run_pending(s)
    assert said(s)[-1] == 560060
    down(s, REAR)
    assert said(s)[-3:] == [560061, 560070, 560170] and tutorials(s) == ["Organizational_Power"]
    assert MORTAR in s.data["zone_troops"] and panel(s)[1] == [566090] and (566010, 566120) in panel(s)[0]


def test_the_cohesion_lesson_goes_on_if_the_mortar_falls_first():
    # the switch back to Normal Line is the player's key, whatever became of the mortar
    s = mission_room(10349)
    to_cohesion(s)
    down(s, REAR)
    down(s, MORTAR)
    press(s, ONE)
    run_pending(s)
    assert said(s)[-2:] == [560100, 560110] and CAVALRY in s.data["zone_troops"]


def test_cohesion_the_shells_the_normal_line_and_the_cavalry():
    # 5:10-5:34: the artillery's shells (560170, the panel's "Change to Normal Line"), the switch on its key (5:16:
    # 560100, both objectives complete), the banner closing with the cavalry (5:26-5:28), 560120 at its fall
    s = mission_room(10349)
    to_cohesion(s)
    down(s, REAR)
    assert said(s)[-1] == 560170 and (566010, 566130) in panel(s)[0] and MORTAR in s.data["zone_troops"]
    shut = len(closes(s))
    press(s, ONE)
    run_pending(s)
    assert said(s)[-2:] == [560100, 560110] and panel(s)[1][-2:] == [566130, 566120]
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL] and MORTAR in left(s)
    assert CAVALRY in s.data["zone_troops"] and notices(s)[-1] == (565030, 565031)
    down(s, CAVALRY)
    assert said(s)[-3:] == [560120, 20000, 560150] and panel(s)[1][-1] == 566140


def test_the_mock_battle_swaps_the_lesson_troop_for_the_three_on_the_dais():
    # 5:34-6:24: the three spearman troops F1-F3 of 49,360 hp, no lesson troop; the hero on the dais; the allies and
    # Jager's army; "Cavalrymen, attack the enemy Archers!" once half of it is down; won after "Geez, I lost."
    s = mission_room(10349)
    s.state = NoSave()
    to_cohesion(s)
    down(s, REAR)
    press(s, ONE)
    run_pending(s)
    down(s, CAVALRY)
    assert handed(s) == [SPEARMEN, *MOCK] and SPEARMEN in left(s)
    assert all(s.data["battle"].troops[u]["max"] == 49360 for u in MOCK)
    b = director.bound(10349, "모의전영웅이동")
    assert s.data["hero_pos"][0] == round(b["BoundCenterX"])
    forces = {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    assert {21000, 12000} <= forces and 21010 not in forces
    assert notices(s)[-1] == (565040, 565041) and {(566010, 566040), (566020, 566050)} <= set(panel(s)[0])
    army = [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 21000]
    down(s, *army[:5])
    assert said(s)[-1] == 560130 and 10026 in s.data["zone_troops"]
    assert not s.data.get("mission_won")
    down(s, *army[5:], 10026)
    assert s.data.get("mission_won") and said(s)[-1] == 560140 and panel(s)[1][-1] == 566040
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1

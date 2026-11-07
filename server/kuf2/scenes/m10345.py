"""Training Camp (Archer) 10345 (1_TrainingCamp zone2), the director's table.
The original's run of it: playthrough part 4 25:20-30:04 (planning/scripts/missions/10345.md, `py
tools/mission_scripts.py 10345`, its storyboard and panel under captures/scripts/10345/; until this table the tool
filed the run under 10331 and 10349, the camps sharing one missiontext; the frames between the tiles read 2026-09-29,
captures/video/_0FD8aKDxto frames 1520-1812 s). Won at 29:40 ("Uh-oh. I lost."), S at 4:19.

What the frames show: the hero stays on the dais (the zone's start, beside 모의전영웅이동) and commands one archer
troop, F1 "Elf Archer Unit" 13,700 hp (troop 10087 상성조작궁병 "the archer you control": 20 x 685), across a field
where four allied infantry and four enemy infantry are already locked in melee (25:38-25:44: four blue and four red
banners across the river, one red one highlighted, "Lv.10 Human Infantry"): 상성궁병아군보병1-4 (10118-10121) against
상성궁병적보병1-4 (10104, 10115, 10116 and the zone's only active enemy, the highlighted 10117). The panel reveals its
objectives one at a time (panel_1: "Basic Ranged Attack" 25:42, completed with "Bomber Wing Attacks" 26:12, then "Move
to a place of safety" 26:42, "Eliminate all enemies" 27:12, "Win a mock battle with Jager" 28:42; failure "Let your
Infantry Troop be eliminated" throughout). The frames at 4 fps (2026-10-24, build/order-c, video time) put the first
ones earlier: the start panel ("Archer Training Camp", "Basic Ranged Attack", "Let your Infantry Troop be eliminated")
fades in with the HUD at 25:32.9, after the opening camera that carries 20001 (25:24-25:31, no HUD) and before Jager's
20002 (25:33.4) and the notice (25:33.9); "Move to a place of safety" 26:34.4, a quarter second before 12418's box;
"Win a mock battle with Jager" and the "Your Infantry Troop" bar under the quest tracker in the first frame of the HUD
back after the mock battle's camera (28:37.4-28:37.6), with Jager's 20020 and the notice. The bar sinks slowly to
about 80 % by 29:12 and stays: the troops' hp summed, a force's bar. For the mock battle (28:44-29:40) the HUD shows
three fresh archer troops
F1-F3, 13,700 hp and three skills each (최종부여궁병1-3, "finally granted archers", 10153-10155) and no more the lesson
archer. The panel's title reads "Archer Training Camp" in the footage; this build's missiontext has 30000 "Bowman
Training Camp" at that row. Speaker: Jager (the box's name and face in every tile), troop 10148 최종전투예거 (leader
123010 `아군연출_예거`), who stands on the dais from the start (game.mission_plan G4).

Left out: the start's camera shot of the archers (25:24-25:30) and the mock battle's (28:32-28:36): the footage's
"cutscene archer" is named by its length only, and the map's `archer` cutscene has no index to play it by. So the
start panel waits for the opening's line instead ("panel start" after 20001: the HUD came back after it), and the mock
battle's panel line and bar go up as 20020 shows. Ours: which step each beat hangs on (below), the bar of the enemy
infantry's charge (all of F20009 standing), the lesson archer leaving the field for the three mock-battle troops (the
HUD shows only them from 28:44), the force the "Your Infantry Troop" bar follows (F12000, the only allied infantry of
the mock battle: six troops 123690; 0xc8b4 kind 2 sums a force, game.TROOPS_BAR_FORCE)."""
from ..director import KEY_RIGHT_ORDER

JAGER = 10148                    # 최종전투예거
ARCHER = 10087                   # 상성조작궁병: the player's archer through the lessons
MOCK = (10153, 10154, 10155)     # 최종부여궁병1-3: the player's three in the mock battle
TARGET = 10117                   # 상성궁병적보병4: "the highlighted enemy Troop" (the zone activates it alone)
MELEE = (10104, 10115, 10116)    # 상성궁병적보병1-3: the rest of the melee in front of the archer at the start
WING = 10123                     # 상성궁병버머윙: "Enemy Bomber Wing!" (one)
WINGS = 10135                    # 궁병도전과제용버머윙: "the enemy has dispatched another Bomber Wing!" (six)
HAND = (ARCHER, *MOCK)
HAND_LATER = set(MOCK)
# the lesson's enemies (F20009), the mock battle's (F30000 infantry and archers, F30010 support infantry, F30020 Bomber
# Wings), its allied infantry F12000 and the player's three F12500: only the steps bring them (the proximity wake had
# the archer's first move bring the whole lesson at once)
HOLD = {20009, 30000, 30010, 30020, 12000, 12500, 10013}   # 10013: 컷신용궁병 10113, the opening camera's archer (left
# out below): the tape's field has the player's archer alone, and live 2026-11-06 it shot the target and the Wing down
# The lesson's melee is staged, ours [I]: the allied infantry of F10014 hit for show. Tape 25:38-28:12: the four red troops
# stand in it for 2:34, one still at half its bar at 27:45, and they fall to the archer's volleys (1,534-1,775 each, 11
# for a troop's 18,350). Their row 123690 hits for real in the mock battle (14 troops down in 53 s, ours 48 s), so the
# lost script held them here; at their full 700-1,000 a second the four fell in 37 s (live 2026-11-06), before the
# player's first order. The archer is of the same force and hits for real (game: a handed troop is his).
HARMLESS = {10014}
PANEL = (30000, ((30010, (30090,)), (30020, (30050,))))

STEPS = [
    # the lesson's field: the allied infantry F10014 (with the player's archer) and the enemy infantry in melee
    # (25:38; HOLD keeps the zone's active 10117 out with its force until then); "Let's learn about the Archer"
    # (25:24, over the opening camera), the panel as the HUD comes back (25:32.9), "Try a Ranged attack." with its
    # notice (25:33.4-25:33.9)
    {"on": "start", "id": "start", "do": [
        ("wake", 10014), ("spawn", TARGET, *MELEE), ("say", JAGER, 20001), ("panel start",), ("say", JAGER, 20002),
        ("notice", 12080, 12081)]},
    # the archer's own hit on the highlighted troop, not the allied infantry's beside it (or its fall): "That's good"
    # (25:44), the Bomber Wing (25:50, the notice 25:52), the hint to move (25:58)
    {"on": "hp", "troop": TARGET, "below": 99, "by": ARCHER, "id": "ranged", "do": [
        ("done", 30090), ("say", JAGER, 12413), ("panel", 30010, 30100), ("spawn", WING), ("say", JAGER, 12414),
        ("notice", 12088, 12089), ("say", JAGER, 20004)]},
    # the Bomber Wing down (26:12 complete): what to avoid (26:14-26:42); one enemy troop leaves the melee for the archer
    # with 12417 "Here come the enemy Infantrymen!" (26:28-26:38: the archer in melee; at 26:37 three red banners stay at
    # the river and one stands by the archer's ring; which one the tape does not name, ours the first still standing,
    # past the melee: engage 0); "Move to a place of safety" joins the
    # panel with 12418 (frames every 4 s: absent at 26:32, there at 26:36; it came with 20005, 26:14)
    {"on": "down", "troop": WING, "needs": "ranged", "id": "wing", "do": [
        ("done", 30100), ("say", JAGER, 20005), ("say", JAGER, 12416), ("march one", 20009, "시작궁병가두기"),
        ("say", JAGER, 12417), ("panel", 30010, 30110), ("say", JAGER, 12418), ("say", JAGER, 12419)]},
    # "Move them over there." (26:42): the player's order to move them (the right button), then "Good! Now that
    # they're far away" (26:50) and the second Bomber Wing with "Defeat all the enemies" (26:58)
    {"on": "after", "step": "wing", "s": 0, "id": "move away"},
    {"on": "prompt", "keys": KEY_RIGHT_ORDER, "needs": "move away", "id": "safe", "do": [
        ("done", 30110), ("say", JAGER, 12420), ("panel", 30010, 30120), ("spawn", WINGS), ("say", JAGER, 12424),
        ("notice", 12020, 12022), ("say", JAGER, 20003)]},
    # every enemy of the lesson down (28:12): the mock battle. The lesson archer leaves, the three come (28:44), with
    # the allied infantry and Jager's army; "brace yourself" (28:32), then as the HUD comes back (28:37.6) "Win a mock
    # battle with Jager" in the panel, the "Your Infantry Troop" bar over the allied infantry F12000, "Now everyone,
    # attack!" and its notice
    {"on": "down", "force": 20009, "needs": "safe", "id": "mock", "do": [
        ("done", 30120), ("say", JAGER, 20011), ("say", JAGER, 20000), ("leave", ARCHER), ("wake", 12500),
        *(("hand", u) for u in MOCK), ("wake", 12000, 30000, 30010, 30020), ("say", JAGER, 20010),
        ("panel", 30010, 30040), ("force bar", 30070, 12000), ("say", JAGER, 20020), ("notice", 21000, 12022),
        ("say", JAGER, 20130)]},
    # the mock battle's last enemy down: "Uh-oh. I lost." (29:40), then the victory
    {"on": "won", "do": [("done", 30040), ("say", JAGER, 20050)]},
]

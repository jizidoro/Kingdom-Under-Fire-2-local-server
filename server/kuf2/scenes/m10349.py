"""Training Camp (Spearman) 10349 (1_TrainingCamp zone6), the director's table.
The original's run of it: playthrough part 12 2:50-7:48 (planning/scripts/missions/10349.md, `py
tools/mission_scripts.py 10349`, its storyboard and panel under captures/scripts/10349/; until this table the tool
filed the run under 10345, the camps sharing one missiontext; the frames between the tiles read 2026-09-29,
captures/video/TrE5TmRNJno frames 140-470 s). Won at 7:24 ("Geez, I lost."), C at 4:27 (loot.grade_points reproduces
that window).

What the frames show: through the lessons the player commands one spearman troop, F1 98,720 hp (troop 10001 튜토창병,
the zone's own active spearmen: 20 x 4,936), on the bridge; for the mock battle three spearman troops F1-F3 of 49,360
hp (지원창병1-3, 10021-10023: 20 x 2,468) and no more the lesson troop. The beats: 559999 in the opening shot (3:10);
"Move them to the entrance into the bridge." with a marker there (3:24-3:38, bound 시작다리입구); "Good job" (3:40);
"Now, press 1 and change their formation to Concentrated Line." with its notice (3:50: the Line change is the
troop's skill 1); 560030 (3:52); the lone infantryman charging the line (3:56-4:04, 대열튜토적보병 10003); 560040 with
"Move while in Concentrated Line mode" (4:08-4:10) and a marker ahead on the bridge (대열이동위치); "they move extremely
slowly" (4:20) while they crawl there; the infantry from behind (4:28-4:46, 대열튜토후방적보병 10004) and 560060 as
they strike (4:38); "This time, we'll learn about Cohesiveness" (4:48); the banner "Spearmen require Cohesiveness to
retain their formation" (5:02, mission tutorial Organizational_Power, 13000) with 560070 (5:04); the artillery's
shells on the line (5:10-5:16, 조직력포병 10005, attack x50) with 560170; the panel's "Change to Normal Line" done and
560100 (5:16); the banner gone with "Eliminate the Cavalry Troop" and 560110 (5:26-5:28, 조직력기병 10007); 560120
(5:34); the mock battle: Jager's army (5:56) with 20000, "Use your Spearmen and win the mock battle" and 560150
(6:04), 560130 "Cavalrymen, attack the enemy Archers!" (6:24), 560140 (7:24). The panel (panel_1): "Learn about
Spearman Line modes" from 3:40, completed with "Learn about Cohesiveness" by 5:10; "Learn about Cohesiveness", "Change
to Normal Line" and "Defeat Cavalrymen" complete by 5:40; "Win a mock battle with Jager" and the failure "Let your
Infantry Troop be eliminated" from 6:10. Speaker: Jager (name and face in every box), troop 10002 대사용예거
("Jager for the lines", leader 123010), which no step of the zone brings: the start does.

Left out: the opening shot and the mock battle's (the footage's "cutscene archer" by length only; the map's `archer`
cutscene has no index); the black at 4:58 and 5:46 (the script moved the view: which bound is not read); the "Your
Troop" bar of the mock battle (which troop it follows is not read). Ours: the steps' triggers where the footage shows
only the moment (below), the mortar leaving with the cavalry (no shell falls after 5:22), the lesson spearmen leaving
for the mock battle's three, "I think I'm in danger" at half of Jager's army down."""
from ..director import KEY_RIGHT_ORDER, KEY_USE_ABILITY1

JAGER = "대사용예거"             # 10002 (F11000)
SPEARMEN = 10001                 # 튜토창병: the player's troop through the lessons
MOCK = (10021, 10022, 10023)     # 지원창병1-3 (F12010): the player's three in the mock battle
CHARGE = 10003                   # 대열튜토적보병: the infantryman charging the line
REAR = 10004                     # 대열튜토후방적보병: the infantry from behind
MORTAR = 10005                   # 조직력포병: the shells that cost the line its Cohesiveness
CAVALRY = 10007                  # 조직력기병
HAND = (SPEARMEN, *MOCK)
HAND_LATER = set(MOCK)
# the lessons' enemies F20000 / F20010, the mock battle's F21000 and its cavalry F21010, the player's three F12010:
# only the steps bring them (10004 stands 2.3 k from the bridge's entrance: the proximity wake brought it at once)
HOLD = {20000, 20010, 21000, 21010, 12010}
PANEL = (566000, ((566010, (566090,)), (566020, (566060,))))

STEPS = [
    {"on": "start", "id": "start", "do": [("wake", 11000), ("say", JAGER, 559999), ("say", JAGER, 560000)]},
    # the spearmen at the bridge's entrance: the Line change, on its key (the notice's "@K_1")
    {"on": "bound", "bound": "시작다리입구", "needs": "start", "id": "bridge", "do": [
        ("say", JAGER, 560010), ("notice", 565000, 565001), ("say", JAGER, 560020)]},
    {"on": "prompt", "keys": (KEY_USE_ABILITY1,), "needs": "bridge", "id": "line", "do": [
        ("say", JAGER, 560030), ("spawn", CHARGE), ("march", "대열튜토적보병", "시작다리입구"), ("say", JAGER, 560031)]},
    # the charge broken on the line: "Move them over there." The player's order to move (the right button), then
    # the marker's place on the bridge, and the infantry from behind
    {"on": "down", "troop": CHARGE, "needs": "line", "id": "charged", "do": [
        ("say", JAGER, 560040), ("notice", 565010, 565011)]},
    {"on": "prompt", "keys": KEY_RIGHT_ORDER, "needs": "charged", "id": "crawl", "do": [("say", JAGER, 560050)]},
    {"on": "bound", "bound": "대열이동위치", "needs": "crawl", "id": "moved", "do": [
        ("spawn", REAR), ("march", "대열튜토후방적보병", "대열이동위치"), ("say", JAGER, 560051)]},
    {"on": "hp", "troop": SPEARMEN, "below": 99, "by": REAR, "needs": "moved", "do": [("say", JAGER, 560060)]},
    # Cohesiveness: the banner, the shells (the mortar comes with 560170, "Look, their Cohesiveness is decreasing
    # because of the Artillerymen's attacks!", 6 s after 560070: a line that waited for its first shell stalled the
    # lesson whenever the mortar fell first), the switch back to Normal Line (the panel's own objective)
    {"on": "down", "troop": REAR, "needs": "moved", "id": "cohesion", "do": [
        ("done", 566090), ("panel", 566010, 566120), ("say", JAGER, 560061), ("tutorial", "Organizational_Power"),
        ("say", JAGER, 560070), ("spawn", MORTAR), ("say", JAGER, 560170), ("panel", 566010, 566130)]},
    {"on": "prompt", "keys": (KEY_USE_ABILITY1,), "needs": "cohesion", "id": "normal", "do": [
        ("done", 566130), ("done", 566120), ("say", JAGER, 560100)]},
    # the cavalry (the banner closes as it comes, 5:26-5:28)
    {"on": "after", "step": "normal", "s": 0, "id": "cavalry", "do": [
        ("finish",), ("leave", MORTAR), ("spawn", CAVALRY), ("march", "조직력기병", "조직력튜토가두기"),
        ("say", JAGER, 560110), ("notice", 565030, 565031), ("panel", 566010, 566140)]},
    # the mock battle: the hero to the dais, the lesson troop leaves, the three come with the allies and Jager's army
    {"on": "down", "troop": CAVALRY, "needs": "cavalry", "id": "mock", "do": [
        ("done", 566140), ("say", JAGER, 560120), ("move", "hero", "모의전영웅이동"), ("leave", SPEARMEN),
        ("wake", 12010), *(("hand", u) for u in MOCK), ("wake", 12000, 21000), ("say", JAGER, 20000),
        ("notice", 565040, 565041), ("panel", 566010, 566040), ("panel", 566020, 566050), ("say", JAGER, 560150)]},
    {"on": "left", "force": 21000, "count": 5, "needs": "mock", "do": [
        ("wake", 21010), ("march", 21010, "기병도착"), ("say", JAGER, 560130)]},
    {"on": "won", "do": [("done", 566040), ("say", JAGER, 560140)]},
]

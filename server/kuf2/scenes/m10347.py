"""Training Camp (Artilleryman) 10347 (1_TrainingCamp zone4), the director's table.
The original's run of it: playthrough part 9 13:16-16:16 (planning/scripts/missions/10347.md, `py
tools/mission_scripts.py 10347`, its storyboard and panel under captures/scripts/10347/; until this table the tool
filed its 13:54-13:56 beats under 10349; the frames between the tiles read 2026-09-29, captures/video/9NwV8ikwLYk
frames 796-980 s). Won at 16:10 ("Drat, I lost!").

What the frames show: the hero on the dais (the zone's start, Start_Hero_Area) commands one mortar troop through the
lessons, F1 36,048 hp (PC_TutoTroop 10000: 16 x 2,253), and for the mock battle three, F1-F3 36,048 hp with three
skills each (PC_Troop1-3, 12000-12002), the lesson troop gone (14:46). The beats: 541000 in the opening shot (13:22);
"Attack the watchtower over there." with its notice (13:36; two watchtowers, 감시탑 F21100, among the enemy infantry
F21000 and our infantry F11000 in melee, 13:34-13:40); the splash (13:44, as the first shell lands); "Eliminate all
the enemies" with its notice and the panel's "Master the basic controls (Complete)", "Eliminate enemy Troops"
(13:56-14:04); every enemy down: 542000 (14:24); the mock battle (14:46: 542020 with "Use your Mortarmen and win the
mock battle"), "That's a good spot" as they fire (15:04), Jager's flank from behind (15:18: 544040, the notice
"Enemy Infantrymen are coming from behind you. / Move to a place of safety." 15:24), 544070 at the player's move
(15:26), 544090 (16:10). The panel (panel_1): "Master the basic controls of the Artilleryman" and the two failure
lines at 13:34; its completion and "Eliminate enemy Troops" by 14:04; that complete and "Win a mock battle with
Jager" with a "Your Infantry Troop" bar by 15:04. Speaker: Jager, troop 49001 예거 (active in the zone).

Left out: the opening and mock battle shots (13:22-13:28 Skip Video, 14:34-14:40: which cutscene is not read; the
map's cutscenes with an index are the Controls camp's lessons); the "Your Infantry Troop" bar (which troop it follows
is not read). Ours: the steps' triggers where the footage shows only the moment (below), the flank's time and its march
to the player's mortars (bound 11002 covers PC_Troop1-3's places), the lesson troop leaving for the three."""
from ..director import KEY_RIGHT_ORDER

JAGER = "예거"                   # 49001 (F49000)
TUTOR = 10000                    # PC_TutoTroop: the player's mortar through the lessons
MOCK = (12000, 12001, 12002)     # PC_Troop1-3: the player's three in the mock battle
HAND = (TUTOR, *MOCK)
HAND_LATER = set(MOCK)
# the lesson's infantry F21000 and watchtowers F21100, the mock battle's army F23000 and flank F23100, the player's
# three (force 12000): only the steps bring them (their allies F11000 / F13000 come with their mirrors F21000 / F23000)
HOLD = {21000, 21100, 23000, 23100, 12000}
PANEL = (540000, ((540100, (540110,)), (540200, (540210, 540220))))

STEPS = [
    {"on": "start", "id": "start", "do": [
        ("wake", 21000, 21100), ("say", JAGER, 541000), ("say", JAGER, 543070), ("notice", 546030, 546001)]},
    # the mortar's first hit on a watchtower: the splash (13:44), then the lesson's last order (13:56)
    {"on": "hp", "force": 21100, "below": 99, "by": TUTOR, "id": "tower hit", "do": [("say", JAGER, 543080)]},
    {"on": "after", "step": "tower hit", "s": 3, "id": "eliminate", "do": [
        ("done", 540110), ("panel", 540100, 540112), ("say", JAGER, 543090), ("notice", 546040, 546041)]},
    # every enemy of the lesson down (14:24): the mock battle, the three for the lesson troop (14:46)
    {"on": "down", "force": 21000, "needs": "eliminate", "id": "infantry down"},
    {"on": "down", "force": 21100, "needs": "infantry down", "id": "mock", "do": [
        ("done", 540112), ("say", JAGER, 542000), ("leave", TUTOR), ("wake", 12000), *(("hand", u) for u in MOCK),
        ("wake", 23000), ("panel", 540100, 540120), ("say", JAGER, 542020), ("notice", 545060, 545061)]},
    # the player's mortars firing from their places (15:04); Jager's flank (15:18, 32 s into the mock battle: its
    # time is ours, from the footage) at the player's mortars; the player's move to safety (15:26)
    {"on": "hp", "force": 23000, "below": 99, "by": "mine", "needs": "mock", "do": [("say", JAGER, 544030)]},
    {"on": "after", "step": "mock", "s": 25, "id": "flank", "do": [
        ("wake", 23100), ("march", 23100, 11002), ("say", JAGER, 544040), ("notice", 546050, 546051)]},
    {"on": "prompt", "keys": KEY_RIGHT_ORDER, "needs": "flank", "do": [("say", JAGER, 544070)]},
    {"on": "won", "do": [("done", 540120), ("say", JAGER, 544090)]},
]

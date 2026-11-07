"""Troop Training Camp (Controls) 10331 (1_TrainingCamp zone1), the director's table. No footage: the playlist never
enters this camp (planning/scripts/missions/10331.md, removed 2026-10-24: the script filed here was first the Archer
camp's run, 10345's, then Tower's look-alikes, none of them the camp's own; tools/playthrough.py own). Built from the
data alone.

The lessons are the original's own: the map's lesson cutscene 1_Tab (index 1, 66.7 s, planning/scripts/cutscenes.json;
waits on its server 19 times, System_WaitState(-1..-19)) starts eleven mission tutorials in this order and waits in
each for its F pages (CheckCompleteTutorialSub) and then one key (System_CheckInputEvent), then completes its last
page: Select_Mode_1 (Tab), Select_TroopSlot1_Enter_1 (F1), Command_X_1 (X), Command_C_1 (C), Command_Z_1 (Z),
Select_TroopSlot2_Enter_1 (F2), Select_TroopSlot1_Move_1 ("Attack the enemy Troop", the right button's orders free,
then a server wait), Select_TroopSlot3_Enter (F3), Test1 (1: "Use Troop skills"), TroopSkill_Short_Cut1 (Ctrl + 1),
Select_AllTroop (F4); then the move keys free and three more server waits. The cutscene itself is not played (its
waits are the server's to release, one ahead at most: director docstring): its pop-ups are ours, each closed on its
key (0xc897: every one has two pages or more), as Tower's.

Ours: the lines with each lesson, paired by their words from the missiontext's 510000-511100 set (the camp's
"Captain" lines are Sanchez's, the aide who calls the hero Captain; 511050, 511100 are Jager's: "Archers! Concentrate
fire", "I lost"); the panel, the 500700 block the same set belongs to ("Troop Control Tutorial", "Jager's Troop
eliminated"), not the 700 block game.mission_text picks by the title both share; the mock battle (the held forces
F21000 / F22000 and their allies, game.mission_plan G4) once the troops reach the map's strip 12100 (LINE below;
511062 "Move your Troops to the highlighted location"); the three troops the lessons command (F1-F3: PC_Troop_1-3,
11000 / 11107 / 11104; G5 took PC_Troop_4 too). The win is the rule's: every hostile down, Jager's F20000 on the
other side (511021) with the mock battle's."""
from ..director import (COND_TUTORIAL_PAST as TUTORIAL_PAST, KEY_AI_DEFENSIVE, KEY_AI_HERO_SUPPORT, KEY_AI_OFFENSIVE,
                        KEY_CHANGE_CONTROL_MODE, KEY_RIGHT_ORDER, KEY_SELECT_ALL_TROOP, KEY_SELECT_TROOP2,
                        KEY_SELECT_TROOP3, KEY_SELECT_TROOP4, KEY_TROOP1_SKILL1, KEY_USE_ABILITY1)

SANCHEZ, JAGER = "산체스", "예거"     # 14000, 14001 (both active in the zone)
HAND = (11000, 11107, 11104)         # PC_Troop_1, PC_Troop_2, PC_Troop_3
HOLD = {21000, 22000}                # the mock battle's two forces
# Where the troops regroup, ours [I]: the strip with the three stands 12000-12002 along it, across the field from the
# mock battle's lines at x 43,000. 유저이동지역 ("the user's move area"), by Sanchez's seat, is ground the client refuses
# a troop ("Cannot move to that area." three times, live 2026-11-06 10:53): sent there the camp could not go on.
LINE = "12100"
PANEL = (500700, ((500710, (500720, 500721)), (500730, (500740,))))

# (the step before, the lines, the pop-up, the page its key waits past, the keys, the id): 1_Tab's order
LESSONS = (
    ("start", (510000, 510010), "Select_Mode_1", 1, (KEY_CHANGE_CONTROL_MODE,), "tab"),
    ("tab", (510020, 511000), "Select_TroopSlot1_Enter_1", 2, (KEY_SELECT_TROOP2,), "f1"),
    ("f1", (511010,), "Command_X_1", 2, (KEY_AI_DEFENSIVE,), "stopped"),
    ("stopped", (511020,), "Command_C_1", 1, (KEY_AI_HERO_SUPPORT,), "support"),
    ("support", (511021, 511030), "Command_Z_1", 1, (KEY_AI_OFFENSIVE,), "attack"),
    ("attack", (511031, 511040), "Select_TroopSlot2_Enter_1", 0, (KEY_SELECT_TROOP3,), "f2"),
    ("f2", (), "Select_TroopSlot1_Move_1", 0, KEY_RIGHT_ORDER, "ordered"),
    ("ordered", (511041,), "Select_TroopSlot3_Enter", 0, (KEY_SELECT_TROOP4,), "f3"),
    ("f3", (511042,), "Test1", 1, (KEY_USE_ABILITY1,), "strike"),
    ("strike", (511050, 511051), "TroopSkill_Short_Cut1", 1, (KEY_TROOP1_SKILL1,), "shield"),
    ("shield", (511060, 511061), "Select_AllTroop", 1, (KEY_SELECT_ALL_TROOP,), "regroup"),
)
SPEAKERS = {511050: JAGER}


def lesson(before, lines, name, page, keys, sid):
    """A lesson of 1_Tab: its lines and pop-up when the one before is done (2 s on, ours), its F pages the client's,
    then its key, and the pop-up closed."""
    shown = {"on": "after", "step": before, "s": 2, "id": f"{sid} shown", "do": [
        *(("say", SPEAKERS.get(line, SANCHEZ), line) for line in lines), ("tutorial", name)]}
    if before == "start":
        shown = {"on": "start", "id": "start", "do": shown["do"]}
    return [shown,
            {"on": "cond", "cond": (TUTORIAL_PAST, name, page), "needs": shown["id"], "id": f"{sid} page"},
            {"on": "prompt", "keys": keys, "needs": f"{sid} page", "id": sid, "do": [("finish",)]}]


STEPS = [
    *(st for les in LESSONS for st in lesson(*les)),
    # W-17: the move keys free; the lessons are complete; the troops to the highlighted place
    {"on": "after", "step": "regroup", "s": 0, "id": "move", "do": [
        ("done", 500720), ("say", SANCHEZ, 511062), ("point", LINE)]},
    {"on": "bound", "bound": LINE, "needs": "move", "do": [
        ("wake", 21000, 22000), ("say", SANCHEZ, 511070), ("say", SANCHEZ, 511071)]},
    {"on": "won", "do": [("done", 500721), ("say", JAGER, 511100)]},
]

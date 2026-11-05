"""New Hampton Castle 10235 (1_NewHamptonCastle zone1), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10235.md
(`py tools/mission_scripts.py 10235`).

Sources: the map's missiontext (`py tools/recon/mission_sheet.py 10235`), the zone's bounds and forces, the walkthrough
(walkthrough_guide.txt L241-274: the trebuchet, Duran, Glen and Thompson along, "once you attack, Vert commands everyone
to fight back, after wall breaks encablossians start swarm", the heretic infantry and cannons before Vert, Vert's
summons at 100 % and 70 % and his escape at 20 %, then the celebration). The heroes are zone troops here: force 40000's
글렌 / 듀란 / 톰슨 (npleadertable 135040 Glen, 135060 the lord, 135050 Thompson) by the start. Vert before the boss
fight is the opening scene's staging Vert 49000 (135720 연출_베르트 on the wall), the boss is 49400 (135110).

Ours: the missiontext holds four drafts of the story. This table plays the 15000 set (the scenes: the opening, the
wall broken, Vert sighted, the boss, the escape) with the 16000 ending it leads into ("Vert got away") and the 5000 set
for the play between them (the siege, the breach, the town's heretics and cannons, the summons), whose ids follow the
zone's phases P1 siege, P2 inside the wall, P3_1-3 the town, P4 the boss. Left out: 17000-17430 (an older draft of
15000's opening, siege and escape), 6000-6900 (a field battle with heavy infantry, winged wyrms and a siege tower
defence: no such forces in zone1), 5010 / 5800-5950 (the same beats as 15050 / 15400-15530), 5230 / 5240 (the steam
siege tower's advance, which nothing offline moves), 4100-4200 (follow-me and trebuchet nags: only the hero's place is
known). Speakers from the lines' words: Thompson calls Glen "General", Glen calls the hero "Commander", Vert names
Duran and Glen, Duran goes through the town with the hero while Glen goes to the barracks (5420); heretic lines go to
a troop of the force that says them. Triggers and numbers are ours: the siege starts at the first hit on the wall and
the breach is its fall; the town begins at the bound P3_시가지시작_영웅 (the line across the town gate); the summons at
100 % are 24100 / 24200 (primitives) and at 70 % 24300 (its aliases 저거너트_좌 / 타일런트_우, "Juggernauts! Tyrants!")
with 24400 beside it.

The wall, from the footage (part 3 26:14-27:40, frames read 2026-09-29): the target the player selects is "Lv.8 Castle
Wall" with its own hp bar, and only one row can show that: 135200 (troop 49444, alias 성벽, 2,217 hp, HUD visible);
the staging segments 135380 (23501-23514, 49445, 21200-21202: 17,739 hp) hide their HUD. 49444 stands right ahead of
the player's trebuchet 40100 (x 119,892 vs 120,166). "Castle Wall Durability" falls 100 -> 64 -> 14 -> 0 % in three
shots (bar 26:50-27:06, 27:08-27:22, empty 27:24), as 49444 does under the trebuchet's fireball here (100 -> 58 -> 17
-> 0; 23504 would take 11). The breach's vanishing collision prop 19211 (type 232) stands just behind 49444 (x 120,008)
and opens with the swarm F20100 at its fall. Until then the table sieged 23504 (DESIGNER-NOTES F5).

The lessons, from the original's 1_TroopSkill_Tuto (planning/scripts/cutscenes.json) and the footage (25:52-26:20):
135_TroopSkill_Short_Cut9's two F pages (the client's), then Ctrl + A (KEY_UseAbilityC9, the third troop's first
skill), then "Select a castle wall." (135_TroopSkill_Use), which its cutscene left to the target keys and its server
(System_WaitState(-12)): here the target key (KEY_SelectTarget) closes it. No 135_Select_TroopSlot3_Enter:
the footage shows none and no script of the map starts it. The cutscene itself is not played (it waits on the server
three times, -10 / -11 / -12, and disables the heroes and troop slots 1 / 2 until 2_Destroy_Wall): its pop-ups are
ours, so the Ctrl + A one closes without its completion circle (0xc897; 0xc898 completes page 0 only)."""
from ..director import COND_TUTORIAL_PAST as TUTORIAL_PAST, KEY_SELECT_TARGET, KEY_TROOP3_SKILL1

GLEN, DURAN, THOMPSON = "글렌", "듀란", "톰슨"
# The panel reveals its objectives one at a time and completes them (frames of playthrough part 3: "Enter New Hampton
# Castle" and the lesson "Use Trebuchet skill" from 25:52, "Use Trebuchet skill (Complete)" at 26:20, "Reach the
# entrance to the town with Duran" at 28:56 as 210 completes, "Follow Vert" at 30:26 as 220 completes, "Fight Vert" at
# 37:40 as 230 completes). Under its title "New Hampton Castle" (100, the red bar; frames 25:51.50-28:56, build/order-b
# captures/order-b/p3_nh_panel_zoom.jpg; ours had none). Sent as the opening scene ends ("panel start"), where the tape
# first shows it (25:51.50 with the HUD's return, "Tutorial / Use Trebuchet skill" at 25:52.25-25:52.50, Glen's 5000
# at 25:53.50): sent at the start it would only show there too, behind the scene
PANEL = (100, ((200, (210,)), (300, (310,)), (420, (430,))))
VERT_ON_WALL = 49000             # the opening scene's staging Vert (force 49000 시작 컷신 연출용)
VERT = 49400                     # the boss (보스_베르트, 88,695 hp)
WALL = 49444                     # the castle wall the trebuchet breaks (F20010 성벽, 135200; see above)
ESCORT = {40000}                 # Glen, Duran, Thompson go through the town with the hero

HOLD = {20100, 24100, 24200, 24300, 24400,    # the wall's fall and Vert's summons bring these (the proximity
                                              # wake had them all in with Vert, the authoring run)
        20070}                   # the 23 wall cannons (135280 "연출공격력20배": staging, ATK x20 = 1,797.8, HUD hidden,
                                 # EXP 0) never come (ours): live 2026-09-28 03:10:56 (captures/game_20260928_030946)
                                 # cannon 20088's first volley took the trebuchet from 5,449 hp to 0, while in the
                                 # original the player's troops kept full hp through the shelling (part 3 26:16-29:52)

STEPS = [
    # the opening before the walls: 0_Start (42 s, voices 15000-15050), then the order to fire (5000). Cutscenes:
    # planning/scripts/cutscenes.md (tools/recon/cutscenes.py)
    {"on": "start", "id": "opening", "do": [("wake", 20010), ("cutscene", 0, 42)]},   # the wall 49444 (inactive in
                                                                                        # the zone: a wave otherwise)
    {"on": "after", "step": "opening", "s": 0, "do": [("panel start",)]},
    # the order to fire, then the troop skill lesson (the original 25:54, 25:58-26:08)
    {"on": "after", "step": "opening", "s": 2, "id": "fire", "do": [
        ("say", GLEN, 5000), ("tutorial", "135_TroopSkill_Short_Cut9")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "135_TroopSkill_Short_Cut9", 1), "needs": "fire", "id": "ctrl"},
    # "Select a castle wall." after Glen's order (frames 26:13.00 his box "Attack the castle wall with the trebuchet!",
    # 26:14.00 the pop-up: build/order-b captures/order-b/p3_nh_5010.jpg; the original's cutscene started 13503 after
    # its server released System_WaitState(-11), 8.7 s in), as the fireball's targeting is up from the Ctrl + A (the
    # original's cutscene locked the input through its camera on the trebuchet, which we do not play). Its key is
    # the one 1_TroopSkill_Tuto left live for it with the right button's orders: KEY_SelectTarget, the left button
    # picking the skill's ground (200139 is FocusType GROUND: no troop target to read in the cast). It completes the
    # lesson line (26:20, before the first hit)
    {"on": "prompt", "keys": (KEY_TROOP3_SKILL1,), "needs": "ctrl", "id": "fireball", "do": [
        ("finish",), ("say", GLEN, 5010), ("tutorial", "135_TroopSkill_Use")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "135_TroopSkill_Use", -1), "needs": "fireball", "id": "select wall"},
    {"on": "prompt", "keys": (KEY_SELECT_TARGET,), "needs": "select wall", "do": [("complete",), ("done", 430)]},
    # the siege: the first hit on the wall, Vert calls the defence, the trebuchet told to keep at it: one run of lines
    # in the original (26:28-27:04), all before its second shot (the bar at 64 % from 26:50 to 27:06)
    {"on": "hp", "troop": WALL, "below": 99, "do": [
        ("say", None, 5020), ("say", VERT_ON_WALL, 5030), ("say", GLEN, 5100), ("notice", 900),
        ("gauge", 400, 401, WALL),                      # 5020: an infantryman's; "Castle Wall Durability" is its own
        ("say", GLEN, 5110), ("say", GLEN, 5120)]},     # panel group with a red bar under it, after the Tutorial
                                                        # group (frames of part 3, 26:50-27:22)
    # the breach: Vert leaves the wall, the Encablossians inside the left wall swarm out (force 20100)
    {"on": "down", "troop": WALL, "do": [
        ("cutscene", 2, 12), ("say", VERT_ON_WALL, 5200), ("wake", 20100), ("notice", 1000, 1010),
        ("say", DURAN, 5210), ("say", GLEN, 5220)]},     # 2_Destroy_Wall voices 15100; the Offensive notice with
                                                         # 5200, before Duran's 5210 (the original 27:40-27:46)
    # "Enter New Hampton Castle (Complete)" and "Reach the entrance to the town with Duran" come with Duran's 5320, past
    # the wall (frames 28:55.25 the panel, 28:55.75 his box: p3_nh_220_zoom.jpg), not with Glen's 5300 (28:33.50, with
    # the notice 1020 / 1030 at 28:34.50; Duran's 5310 at 28:38); the tape's troop crosses to the highlighted area
    # between 5310 and 5320, a place no step of ours waits for yet
    {"on": "down", "force": 20100, "do": [("say", GLEN, 5300), ("notice", 1020, 1030), ("say", DURAN, 5310),
                                          ("done", 210), ("panel", 200, 220), ("say", DURAN, 5320),
                                          ("notice", 1050, 1060)]},
    # the town gate: Vert sighted, Glen to the barracks, Duran with the hero (15200-15203, 5400, 5420). Vert on the
    # gate, 49300 (the staging force F49300), comes in first. 3_Into_Castle's ACTOR track BERD binds him, and the
    # client starts no scene until every such troop is there (0x1408b3360; Grey Rock's 11_Kobold waited at black
    # without its troll, live 2026-09-30). The scene enables him itself at 0 s and disables F49300 at 15.7 s: the
    # original's room held him, disabled
    {"on": "bound", "bound": "P3_시가지시작_영웅", "id": "town", "do": [
        ("wake", 49300), ("cutscene", 3, 22), ("done", 220), ("panel", 200, 230), ("say", DURAN, 5400), ("say", DURAN, 5410), ("notice", 1100, 1110),
        ("say", GLEN, 5420)]},                                                   # 3_Into_Castle voices 15200-15203
    {"on": "after", "step": "town", "s": 2, "do": [
        ("say", DURAN, 5500), ("say", 21002, 5430), ("say", 21002, 5440), ("say", DURAN, 5510)]},
    # P3_2: the cannons (21310) and their rabble (21300)
    {"on": "wake", "force": 21310, "do": [("say", DURAN, 5530), ("say", DURAN, 5540)]},
    # "All clear!" once both are down, after the cannons' "wipe out the rest of the rabble" (the tape 34:54 -> 35:04):
    # the rabble down first waits for the cannons
    {"on": "down", "force": 21310, "id": "cannons down", "do": [("say", DURAN, 5560)]},
    {"on": "down", "force": 21300, "needs": "cannons down", "do": [("say", DURAN, 5570)]},
    # P3_3: the last line of defence (21400) and more cannons (21410), then the stairs up to Vert
    {"on": "wake", "force": 21400, "do": [("say", 21400, 5600)]},
    {"on": "wake", "force": 21410, "do": [("say", DURAN, 5610), ("say", DURAN, 5620)]},
    {"on": "down", "force": 21410, "id": "last cannons down", "do": [("say", DURAN, 5630)]},
    {"on": "down", "force": 21400, "needs": "last cannons down", "do": [("say", DURAN, 5640), ("say", DURAN, 5650)]},
    # Vert: 4_Enca_Sommon (40 s, voices 15400-15430: his words with Duran, the summoning), the first summons
    # (the original, playthrough part 3, 37:14-41:08: the cutscene, then the fight in boxes 5800-5970; the
    # hp thresholds between its beats are ours). The summoned Encablossians 49440-49443 (F49410) come in first:
    # the scene's ACTOR tracks Enca_0-3 bind them (0x1408b3360, as above). The scene enables them itself at 28 s and
    # disables F49410 at 35.7 s, when it enables the real summons F24100 / F24200
    {"on": "wake", "force": 49400, "id": "vert", "do": [
        ("wake", 49410), ("cutscene", 4, 40), ("wake", 24100), ("wake", 24200), ("done", 230), ("panel", 200, 240),
        ("say", DURAN, 5800), ("say", VERT, 5810)]},
    {"on": "hp", "troop": VERT, "below": 90, "do": [("say", DURAN, 5820), ("say", VERT, 5830)]},
    # the second summons at 70 %: the juggernaut and the tyrant
    {"on": "hp", "troop": VERT, "below": 70, "do": [
        ("say", VERT, 5840), ("say", VERT, 5850), ("wake", 24300), ("wake", 24400), ("say", None, 5860)]},
    # Duran falters, Glen comes back from the barracks
    {"on": "hp", "troop": VERT, "below": 45, "do": [("say", VERT, 5880), ("say", DURAN, 5890)]},
    {"on": "hp", "troop": VERT, "below": 35, "do": [("say", GLEN, 5900), ("say", VERT, 5920), ("say", GLEN, 5930)]},
    # the escape at 20 %: "We'll meet again", he leaves the field; that is the win
    {"on": "hp", "troop": VERT, "below": 20, "do": [
        ("say", VERT, 5940), ("say", VERT, 5950), ("leave", VERT), ("say", DURAN, 5960), ("say", GLEN, 5970),
        ("win",)]},
    # "you will not die": an ally restores the hero (4010)
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", GLEN, 4010), ("heal",)]},
    # the ending: 5_End (81 s, voices 16000-16080: the castle retaken, the refugees, the celebration). Its cast F19500
    # (19500 / 19510 / 19520 "마지막 실기 영웅들", staging) comes in first: the scene's ACTOR tracks GLEN, THOMSON and
    # DURAN bind them (0x1408b3360). The scene enables the force itself at 0 s
    {"on": "won", "do": [("wake", 19500), ("cutscene", 5, 81)]},
]

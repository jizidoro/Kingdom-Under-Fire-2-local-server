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
and opens with the swarm F20100 at its fall; the wall itself is composite 19214, 49444's LinkedComositeProp, which the
fall breaks (game.break_composite). Until then the table sieged 23504 (DESIGNER-NOTES F5).

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
LATE_ALLIES = {46600}            # the reinforcements Vert names (5920): they come with Glen's 5900, not with Vert

HOLD = {20100, 24100, 24200, 24300, 24400,    # the wall's fall and Vert's summons bring these (the proximity
                                              # wake had them all in with Vert, the authoring run)
        21000,                   # the town's defenders: the town scene brings them (5430, the tape 31:0x); live 2026-11-05
                                 # 12:22 the chase through the breach woke 51 of them before 5300
        20070}                   # the 23 wall cannons (135280 "연출공격력20배": staging, ATK x20 = 1,797.8, HUD hidden,
                                 # EXP 0) never come (ours): live 2026-09-28 03:10:56 (captures/game_20260928_030946)
                                 # cannon 20088's first volley took the trebuchet from 5,449 hp to 0, while in the
                                 # original the player's troops kept full hp through the shelling (part 3 26:16-29:52)

HARMLESS = {20030, 49000}        # the wall-top shooters (135620 / 135670 "연출공격력0.5배": staging, range 20,000, EXP 0, no
                                 # HUD) and the opening's staging force (mages 135270 "연출공격력0.3배") fire for show (ours
                                 # [I]): live 2026-11-05 F20030's 64,879 hits dealt 697,750 in four minutes and wiped F10000,
                                 # the swarm 40 k, then the mages' purple meteor 200189 took a troop a cast; the tape's
                                 # line stands whole under that fire at 27:18 (no red number on it), the player's troops
                                 # at full hp, the shooters still on the wall at 28:34

TOWN_INFANTRY = "P3_시가지시작_보병"   # they go past the wall-top shooters: a march that fights what it meets stops for them, unreachable


ENTER = [("say", GLEN, 5300), ("march past", 10000, TOWN_INFANTRY), ("march past", 10001, TOWN_INFANTRY),
         ("march past", 10010, "P3_시가지시작_궁병"),
         ("march", 40000, "P3_시가지시작_영웅"), ("highlight", 12000),
         ("notice", 1020, 1030), ("say", DURAN, 5310),
         ("done", 210), ("panel", 200, 220), ("say", DURAN, 5320),
         ("notice", 1050, 1060)]
ESCAPE = [("say", VERT, 5940), ("say", VERT, 5950), ("leave", VERT), ("say", DURAN, 5960), ("say", GLEN, 5970), ("win",)]


def army(bound):
    """The infantry and Duran's party on to the map's next lane. The map names the lanes (P3_2_아군이동, 아군이동2, P3_3_아군이동), the
    tape has them fighting the town beside the hero; the moments are ours [I]. Every stage orders them again: a march is
    dropped once they engage."""
    return [("march", 10000, bound), ("march", 10001, bound), ("march", 40000, bound)]


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
    # picking the skill's target (Ctrl+A casts 200140, whose status throws 200139, FocusType GROUND: procs.troop_shot). It completes the
    # lesson line (26:20, before the first hit)
    {"on": "prompt", "keys": (KEY_TROOP3_SKILL1,), "needs": "ctrl", "id": "fireball", "do": [
        ("finish",), ("say", GLEN, 5010), ("tutorial", "135_TroopSkill_Use")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "135_TroopSkill_Use", -1), "needs": "fireball", "id": "select wall"},
    {"on": "prompt", "keys": (KEY_SELECT_TARGET,), "needs": "select wall", "id": "wall picked",
     "do": [("complete",), ("done", 430)]},
    {"on": "after", "step": "wall picked", "s": 2, "do": [("finish",)]},    # the circle fills, the box goes (26:18-26:21)
    # the siege: the first hit on the wall, Vert calls the defence, the trebuchet told to keep at it: one run of lines
    # in the original (26:28-27:04), all before its second shot (the bar at 64 % from 26:50 to 27:06)
    {"on": "hp", "troop": WALL, "below": 99, "do": [
        ("say", None, 5020), ("say", VERT_ON_WALL, 5030), ("say", GLEN, 5100),
        ("march line", 10000, 11000), ("march line", 10001, 11000), ("notice", 900),     # P1_보병방어이동, across the
                                        # field; the frames have one wide line out by 27:14 (when: ours, from his order)
        ("gauge", 400, 401, WALL),                      # 5020: an infantryman's; "Castle Wall Durability" is its own
        ("say", GLEN, 5110), ("say", GLEN, 5120)]},     # panel group with a red bar under it, after the Tutorial
                                                        # group (frames of part 3, 26:50-27:22)
    # the breach: Vert leaves the wall, the Encablossians inside the left wall swarm out (force 20100)
    {"on": "down", "troop": WALL, "id": "wall down", "do": [
        ("wake", 20100), ("march line", 20100, 11000),   # out during the scene, to the line: in melee at 27:38, the fall 27:24
        ("cutscene", 2, 12), ("say", VERT_ON_WALL, 5200), ("notice", 1000, 1010),
        ("say", DURAN, 5210), ("say", GLEN, 5220)]},     # 2_Destroy_Wall voices 15100; the Offensive notice with
                                                         # 5200, before Duran's 5210 (the original 27:40-27:46)
    # "Enter New Hampton Castle (Complete)" and "Reach the entrance to the town with Duran" come with Duran's 5320, past
    # the wall (frames 28:55.25 the panel, 28:55.75 his box: p3_nh_220_zoom.jpg), not with Glen's 5300 (28:33.50, with
    # the notice 1020 / 1030 at 28:34.50; Duran's 5310 at 28:38); the tape's troop crosses to the highlighted area
    # between 5310 and 5320, a place no step of ours waits for yet. 12000 stands just past the breach (the ring at 28:46)
    # four left, not none: three live runs ended on stragglers no one fought, and the tape's 5300 plays with reds about
    # or on the clock: the wall's fall is the call's own cause on the tape (69 s), and the last of the swarm can stand where
    # neither the army nor the hero meets them (live 2026-11-05: 450 s twice, then 1,944 s). 200 s after the scene's lines
    # is about 240 s from the fall, past every run the swarm decided in 220 s or less (ours [I], as the four)
    {"on": "left", "force": 20100, "count": 4, "id": "enter at four", "unless": "enter on the clock", "do": ENTER},
    {"on": "after", "step": "wall down", "s": 200, "id": "enter on the clock", "unless": "enter at four", "do": ENTER},
    # the town gate: Vert sighted, Glen to the barracks, Duran with the hero (15200-15203, 5400, 5420). Vert on the
    # gate, 49300 (the staging force F49300), comes in first. 3_Into_Castle's ACTOR track BERD binds him, and the
    # client starts no scene until every such troop is there (0x1408b3360; Grey Rock's 11_Kobold waited at black
    # without its troll, live 2026-09-30). The scene enables him itself at 0 s and disables F49300 at 15.7 s: the
    # original's room held him, disabled
    {"on": "bound", "bound": "P3_시가지시작_영웅", "id": "town", "do": [
        ("wake", 49300), ("cutscene", 3, 22), ("march past", 10000, TOWN_INFANTRY), ("march past", 10001, TOWN_INFANTRY),
        ("march past", 10010, "P3_시가지시작_궁병"), ("done", 220), ("panel", 200, 230), ("say", DURAN, 5400), ("say", DURAN, 5410), ("notice", 1100, 1110),
        ("say", GLEN, 5420)]},                                                   # 3_Into_Castle voices 15200-15203
    {"on": "after", "step": "town", "s": 2, "do": [
        ("say", DURAN, 5500), ("wake", 21000), ("say", 21002, 5430), ("say", 21002, 5440), ("say", DURAN, 5510)]},
    # P3_2: the cannons (21310) and their rabble (21300)
    # the archers again: a ranged troop drops its march to fire. Their one lane is 11212, a volley takes 13,900 off a target
    {"on": "wake", "force": 21310, "do": [*army("P3_2_아군이동"), ("march past", 10010, "P3_시가지시작_궁병"), ("say", DURAN, 5530),
                                          ("say", DURAN, 5540)]},
    # "All clear!" after the cannons' "wipe out the rest of the rabble" (the tape 34:54 -> 35:02), the rabble down first
    # waiting for the cannons. Four of the eight (128098-128545, 146432-148557) stand north of the fallen building 11002,
    # closed from here, and the tape's hero has no red near him: it comes with those four left (ours [I], as 5300)
    {"on": "down", "force": 21310, "id": "cannons down", "do": [*army("P3_2_아군이동2"), ("say", DURAN, 5560)]},
    {"on": "left", "force": 21300, "count": 4, "needs": "cannons down", "do": [("say", DURAN, 5570)]},
    # P3_3: the last line of defence (21400) and more cannons (21410), then the stairs up to Vert
    {"on": "wake", "force": 21400, "do": [*army("P3_3_아군이동"), ("say", 21400, 5600)]},
    {"on": "wake", "force": 21410, "do": [("say", DURAN, 5610), ("say", DURAN, 5620)]},
    {"on": "down", "force": 21410, "id": "last cannons down", "do": [("say", DURAN, 5630)]},
    # the army stays down here: the tape's crowd on Vert (38:30) is the map's own line F13000 on the plaza, 54 of the same infantry
    {"on": "down", "force": 21400, "needs": "last cannons down", "do": [("say", DURAN, 5640), ("say", DURAN, 5650)]},
    # Vert: 4_Enca_Sommon (40 s, voices 15400-15430: his words with Duran, the summoning), the first summons
    # (the original, playthrough part 3, 37:14-41:08: the cutscene, then the fight in boxes 5800-5970; the
    # hp thresholds between its beats are ours). The summoned Encablossians 49440-49443 (F49410) come in first:
    # the scene's ACTOR tracks Enca_0-3 bind them (0x1408b3360, as above). The scene enables them itself at 28 s and
    # disables F49410 at 35.7 s, when it enables the real summons F24100 / F24200
    {"on": "wake", "force": 49400, "id": "vert", "do": [
        ("wake", 49410), ("cutscene", 4, 40), ("wake", 24100), ("wake", 24200), ("done", 230), ("panel", 200, 240),
        ("say", DURAN, 5800), ("say", VERT, 5810)]},
    # The fight runs on a clock from his taunt (ours [I], the one reading both sources allow). The tape's bar reads 91.2 % at 5840,
    # 89.1 % at 5880, 88.0 % at 5900, 68.6 % at 5940, and he leaves at 65.7 %: no hp rule gives that. The guide has the summons at
    # 70 % and the escape at 20 %: a steadier player, 0.45 % a second, is there at the tape's same two moments. The seconds
    # are the tape's, from 5810 at 37:50. Falsifier: footage of this fight with another pace and other times
    # (each beat closes with the early escape: the ending only starts after the escape's own lines)
    {"on": "after", "step": "vert", "s": 22, "unless": "escape at 20", "do": [("say", DURAN, 5820), ("say", VERT, 5830)]},
    # the second summons: the juggernaut and the tyrant
    {"on": "after", "step": "vert", "s": 52, "unless": "escape at 20", "do": [
        ("say", VERT, 5840), ("say", VERT, 5850), ("wake", 24300), ("wake", 24400), ("say", None, 5860)]},
    # Duran falters
    {"on": "after", "step": "vert", "s": 84, "unless": "escape at 20", "do": [("say", VERT, 5880), ("say", DURAN, 5890)]},
    # Glen comes back from the barracks with the reinforcements Vert names (5920): F46600, the east arm of the plaza
    {"on": "after", "step": "vert", "s": 124, "unless": "escape at 20", "do": [
        ("wake", 46600), ("march", 46600, "P4_Summon_move"), ("say", GLEN, 5900), ("say", VERT, 5920), ("say", GLEN, 5930)]},
    # the escape: "We'll meet again", he leaves the field; that is the win, at the clock or at the guide's 20 %, whichever is first
    {"on": "after", "step": "vert", "s": 174, "id": "escape on the clock", "unless": "escape at 20", "do": ESCAPE},
    {"on": "hp", "troop": VERT, "below": 20, "id": "escape at 20", "unless": "escape on the clock", "do": ESCAPE},
    # "you will not die": an ally restores the hero (4010)
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", GLEN, 4010), ("heal",)]},
    # the ending: 5_End (81 s, voices 16000-16080: the castle retaken, the refugees, the celebration). Its cast F19500
    # (19500 / 19510 / 19520 "마지막 실기 영웅들", staging) comes in first: the scene's ACTOR tracks GLEN, THOMSON and
    # DURAN bind them (0x1408b3360). The scene enables the force itself at 0 s
    # It finishes on a fade to black (80.475 s of 81.165): the picture comes back before the results, as Grey Rock's 13_EndScene,
    # or the loading spinner covers the world and the Mission Complete button (live 2026-11-05 14:32)
    {"on": "won", "do": [("wake", 19500), ("cutscene", 5, 82), ("fade", True, 1, 0)]},
]

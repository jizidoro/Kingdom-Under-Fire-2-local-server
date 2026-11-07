"""The mission director (MISSION-DIRECTOR-PLAN, option B): a mission's scripted scenes from an authored table, since
the original's mission scripts are not shipped (135,890 package entries scanned, 2026-09-28) and its line ids do not
follow the zone's bounds or forces (the census: 2 % of the story lines link to a bound). A table is
`server/kuf2/scenes/m<spot>.py`, STEPS = [step, ...], or the same in Lua, `scenes/m<spot>.lua` (lua_script: the
game's RTS.* names; it wins when there, `py tools/mission_lua.py <spot>` prints one); each step fires once, when its
trigger holds:

  {"on": "start"}                            the room's troops are in (game.spawn_zone_troops)
  {"on": "bound", "bound": name or id}       the hero enters that zone EventBound (EventBoundName / EventBoundID)
  {"on": "wake", "force": n}                 held force n comes in (game.wake)
  {"on": "down", "force": n}                 the last troop of force n falls ("troop": TroopID for one troop)
  {"on": "hp", "troop": id, "below": pct}    that troop's hp drops below pct % of its max (troop: as an actor)
  {"on": "hp", "force": n, "below": pct}      any troop of force n does (the first of a group hit); with "by": who
                                              (a TroopID or alias, or "mine": any troop of the player's), only a hit
                                              of that troop's counts, or the troop's fall (the training camps' "Attack
                                              the highlighted enemy Troop from a distance": the player's archer's hit,
                                              not the allied infantry beside it)
  {"on": "left", "force": n, "count": k}      only k of force n still stand (Tower's "Only one left!")
  {"on": "engage", "force": n}                a troop engages one of force n, or one of it engages (the client's
                                              engage report, combat.on_engage: melee contact; volleys and a
                                              flyer's passes report none, live 2026-10-24 Tower's wyrms); with
                                              "by": (who, ...), only a fight of one of those troops (TroopIDs or
                                              aliases) with force n (Tower: Glen's force reaching the ring)
  {"on": "won"}                              the mission is won: these play before the victory window
  {"on": "closed"}                           the victory window has closed (the client's own clock: game.RESULT_CLOSE_S
                                              after the record; Tower's "Mission Complete" notice, the tape 19:32.5)
  {"on": "after", "step": sid, "s": secs}    secs after step "id": sid has fired and its lines have played
  {"on": "skill", "troop": who, "force": n}  troop who (alias or TroopID) casts a troop skill on one of force n
                                              (the client's 0x505f)
  {"on": "cond", "cond": (id, arg, ...)}      the client says condition id holds (S2C 0x5086, answered by C2S 0x5089;
                                              planning/client/mission_script.md §5.1): asked once the step it needs
                                              has fired, and again POLL_S after each "no" (COND_TUTORIAL_PAST, name,
                                              n: that lesson pop-up shows a page past n)
  {"on": "prompt", "keys": (key, ...)}        the player presses one of the keys (InputEvent values, KEY_*): a key
                                              prompt each (S2C 0x50c1) once the step it needs has fired; the client
                                              answers the one pressed (C2S 0x50c2), the others come down (0x50c3)
  {"on": "finish", "troop": id}               the hero's finishing attack fells that troop (FINISH_KILL on a troop
                                              in the finish state, status.execution; Grey Rock's troll)
  {"on": "broken", "prop": id}                the hero breaks that attackable prop (game's props_hit; a tuple: the
                                              first of them; Flamegrass's barricade into the shortcut)
  {"on": "used", "prop": id}                  the hero finishes a cast on that prop (the client's 0x5096; a tuple: the first
                                              of them; Grey Rock's Crystal Stones)
  {"on": "arrive", "force": n, "bound": b}    a troop of force n (a tuple: of any of them) is inside bound b, by the
                                              host's position reports (0x50b0, game.troop_sync; Flamegrass's orc
                                              column reaching the ambush)
  {"on": "near", "troop": id}                 the hero (or a troop of his) comes within that troop's acquisition
                                              range (its troop row's RANGE_ACQUISITION: it can target him), the
                                              troop in the room, where it was last seen (ours; Lunawing Sortie I's
                                              head cannons 10308 / 10309, "Ah, watch out! There are Head Cannons
                                              around here!")
"troop" (hp, near) and "force" (skill, arrive) also take a tuple: any one of them. A "prompt" step with "in": bound counts
the key only while the hero stands in that bound; pressed elsewhere it is put up again (Flamegrass's F at the Ice or
the Fire wizard, both prompts up).

A step with "repeat": True fires every time its trigger comes true again (an hp step: each time the hp crosses
below). A step with "class": n is for a hero of that class only (createcharacter HeroId: 0 Gunslinger, 1 Ranger, 2
Elementalist, 3 Spellsword, 4 Berserker): for any other it never fires and is never waited on (the prologue's class
lessons, m50116; steps of different classes may share an id, the one that fires is the hero's). A step with
"difficulty": n (or a tuple) is likewise for a room entered on that difficulty only (0 Normal, 1 Hard, 2 Hell; Fort
Valley's Ukuron and right wall, on the Hard tape alone, in forces the zone does not mark). A step with "needs":
sid waits for step sid: its trigger coming first is remembered, and it fires right after
sid does (Tower's story places: the replay's hero walked into the first one, 18020, during the start scene, and the
table told the scouting lines and marched the escort in the middle of it; live 2026-09-28 23:52); a "cond" or
"prompt" step starts to wait when sid fires (at the start without one). A step with "unless": sid (or a tuple of sids)
never fires once step sid has: two branches of one choice (Flamegrass's Ice or Fire wizard), or two places that
start the same scene (the step whose trigger comes first wins; its prompts come down). It runs its "do" list in
order:

  ("say", speaker, line[, seconds])  a missiontext line of the room's map in the HUD's mission help box. Speaker:
                                     "hero", a zone TroopAlias, a TroopID, None (the text without a name), or a tuple
                                     of those: the first in the room and standing (the troop the player picked)
  ("wake", force, ...)               bring these forces in now: their held groups, and their troops not in yet
                                     (staging, inactive) of the room's difficulty (game.spawn_force)
  ("spawn", troop, ...)              bring these troops (TroopIDs) in now, one by one out of their held group
                                     (game.spawn_troops: the Archer camp's lesson brings its force's troops in turn)
  ("leave", troop)                   a troop leaves the battle (game.troop_leaves: Vert's escape)
  ("march straight", force, bound)   as "march", in a straight line with no pathfinding (ActTroopMoveToAreaIgnoringPolyline):
                                     for troops the navmesh gives no way out, like Grey Rock's caged wolves
  ("march line", force, bound)       as "march", each troop to the bound's point nearest it (goal 1): a line keeps its width
  ("march past", force, bound)       as "march", ignoring what it meets on the way (engage 0, order type 3): troops that would
                                     stop for enemies they cannot reach, like New Hampton's wall-top shooters
  ("march one", force, bound)        as "march straight", the first of the force still standing only (10345: one troop leaves the
                                     melee for the archer)
  ("march", force, bound)            the force's troops (not the player's) run to the bound's centre and fight what
                                     they meet (ActTroopMoveToArea goal 0); a str is one troop's alias. The escort's
                                     marches (ESCORT, below) go to the bound's point nearest each troop (goal 1): the
                                     place the hero crosses a strip; a march to a strip's nearest point left Tower's
                                     troop 20112 at the strip's far end, 9 k from the scouts (live 2026-09-29 03:59)
  ("route", troop, path[, bound])     a troop (alias or TroopID) runs its map's MissionPath `path` under its own program:
                                     0x5083 SetSpawnAI with path 1 (its TAI walks the path when not engaged and fights
                                     what it meets: COMPANIONS plan option A, its F1 the live check); with `bound`, it
                                     leaves the battle once the host reports it inside that bound (0x50b0, on_troops:
                                     Grey Fog's militiaman, gone at 도망 on the tape, part 1 23:41.5-23:42.5)
  ("move deck", uid, bound[, (dx, dz)])  place an owned room troop at a scene mark, only if that deck uid exists
  ("move", troop, bound[, (dx, dz)])  a troop (alias, TroopID or "hero") to a bound's centre (game.move_troop), or
                                     that far from it (a force placed together without stacking on one point)
  ("highlight", bound[, on])          mark a bound on the ground and the minimap (ActGuiSetHighlightArea), or with on 0
                                     take the mark down (Tower's "Let me mark your path on the Map")
  ("highlight troop", troop[, on[, seconds]])  mark a troop (alias or TroopID) with the client's troop marker, the
                                     pillar and glow over it and its minimap mark (ActGuiSetHighlightTroop): blue on an
                                     ally, until taken down (seconds 0) or for seconds; on 0 takes it down (Tower's
                                     Glen under "Follow Glen." and up the hill: the tape, part 2 10:38, 13:07)
  ("point", bound)                   show the direction to a bound (ActGuiShowDirectionToTargetArea, POINT_S; what
                                     point_ahead shows when nothing hostile stands): the Controls camp's "Move your
                                     Troops to the highlighted location"
  ("shoot", troop, target)           a troop not the player's shoots at target (TroopID, alias or "nearest": its
                                     nearest enemy), ActTroopRangeAttack; its AI goes on after (Tower's archers 11004 /
                                     11005 on the wyrms, the original part 2 12:03-12:46)
  ("open", prop_id)                  open a barrier prop (game.open_barriers)
  ("heal",)                          the hero back to full hp (game.heal_hero)
  ("heal", troop)                    a troop's living units back to full (combat.heal_troop)
  ("camera troop", troop, preset)    attach camera axis 5 to a present troop and select a shipped map camera
  ("cutscene", index, seconds)       one of the map's cutscenes (its name's number: Grey Rock "0_Start_CutScene" is 0),
                                     queued like a line for its length (the client reports no end; lengths read
                                     live, CutScene +0xd0 ms). A cutscene moves its actors (Grey Rock's 3_Mid_CutSCene
                                     puts the hero, Glen and Thompson in the fortress): the step moves the rest.
                                     The client starts it only once every troop its ACTOR tracks name is in the room
                                     (cutscenes.json "actors"; 0x1408b3360); a missing one leaves it at black for ever,
                                     so the step brings a held cast in first (Grey Rock's troll, 11_Kobold)
  ("notice", title[, text])          the left notice panel, red seal, a title and a line (ActGuiShowNoticeWindow,
                                     missiontext ids): "Destroy the Oak Barrel." / "Certain objects can be ..."
  ("banner", title[, text])          the same notice centred at the top of the screen (NoticeTable 6
                                     MISSION_EVENT_OPEN_MID, NOTICE_MID): Flamegrass's "Select either the Ice or Fire
                                     Troop." (the tape, part 4 35:36)
  ("untouchable troop", troop, on)    native troop hit protection plus room-local server damage flag
  ("gauge", group, text, troop)      a bar in the mission panel under its group, kept at the troop's hp % as it
                                     takes hits (New Hampton's "Castle Wall Durability")
  ("troops bar", text, troop)        a troop's hp bar below the quest tracker, labelled text, the troop's portrait
                                     its icon; the client keeps it at the troop's hp (0xc8b4, game.panel_troops_bar:
                                     Lunawing Sortie I's "Lunawing Shield" over the airship)
  ("force bar", text, force)         one hp bar below the quest tracker for a whole force, its troops' hp summed by the
                                     client (0xc8b4 ref kind 2, game.panel_force_bar; sent once every troop of the
                                     force in the room is bound): the Archer camp's "Your Infantry Troop"
  ("done", text)                     the panel's condition with that text shown "(Complete)" (0xc828)
  ("count", group, text, force)      a count in the panel, "fallen/all" of the force, kept as its troops fall
                                     (0xc800 kind 0: Tower's "Defeat Winged Wyrms 0/3")
  ("clock", group, text, seconds)    a clock in the panel under its group counting the seconds down, sent each second
                                     (ActGuiAddTimeObjectiveToMissionSituation 0xc80a, rules.panel_time; countdown):
                                     the prologue's "Protect the Castle Gate" 00:00:20 until the reinforcements come
                                     (the tape, part 1 9:14-9:36); what happens at 0 is the table's ("after" steps)
  ("panel", group, line)             a line added to the mission panel under its group (the group sent once):
                                     a lesson's checklist line (Tower's "Tutorial" 200 / 210-270)
  ("panel start",)                   the room's start panel now (the table's PANEL, else game.mission_text): a table
                                     whose steps send it gets no panel at the start, for an original that shows it
                                     only as the HUD comes back after its opening camera (the Archer camp, Flamegrass)
  ("tutorial", name)                 a mission tutorial pop-up (missiontutorial %MissionTutorialType, e.g.
                                     "134_GroggyFinish": its texts from the map's missiontext, images, highlights)
  ("finish",)                        close the lesson pop-up showing (ActGuiFinishTutorial 0xc897, what the original's
                                     cutscenes call as System_FinishTutorial): a pop-up the lesson cutscene would
                                     have completed stays up after its key otherwise (live 2026-09-29 01:55: Tower's
                                     Hero Support lesson a minute after the C, under the next notice)
  ("complete",)                      complete the lesson pop-up's first page (ActGuiCompleteTutorial 0xc898): a
                                     one-page pop-up is done, with its circle and sound; on a later page it would
                                     show page 2 again (0x140b5db70 passes page 0), so a longer one is closed with
                                     ("finish",) on its last page's key
  ("state", n)                       release a cutscene's System_WaitState(n) (n < 0; ActCameraSetCamera, below)
  ("fade", in, seconds, color)        restore or hide the picture (System_Fade); queued after a preceding scene
  ("escort", who, ...)               from now on these (ForceNum, or a troop's alias) march with the story too
  ("hand", troop)                    give a troop to the player now (ActTroopChangeForce; the table's HAND_LATER)
  ("win",)                           win the mission (its "won" steps play first)
  ("clock off", group)               the clock under group stops: shown 00:00:00, the group gone CLOCK_GONE_S later
                                     (0xc7ed; the tape's Flamegrass "Arrive later than the enemy", part 4
                                     41:07-41:08, as the hero reached the convoy's front)

Lesson pop-ups and notices take their turn on screen: while a line or a cutscene holds the queue they wait for it,
as an action listed after a step's line does (the replay of 2026-09-28 23:52 stacked lines, notices and lessons).
A cutscene's System_WaitState(n) holds its timeline (0x140b6d580 -> 0x1408b12a0, the hold CheckCompleteTutorialSub
also uses) until the client's wait state is n; the only writer of that state (0x1435ad9d4) is ActCameraSetCamera
0xe682 (0x140b3c210) given a negative argument (a positive one sets camera n): the original's server stepped its
lesson cutscenes with it. The client reports no lesson progress by itself (a completed mission tutorial logs
"MissionTutorialComplete" and plays a sound, 0x14094e510; nothing is sent), so the server can release one wait ahead
and no more: a cutscene with one wait value is released with its step (Tower's 10_Defense_Camp -10), and the ones with
several (Tower's 1_TroopTutorial -1..-8, 6_Tutorial_CX, 7_Tutorial_Range) are left for our pop-ups. Asked, it answers:
a "cond" step learns a pop-up's page, a "prompt" step the player's key, and our pop-ups close on those (Tower's
lessons: the keys the original's lesson cutscenes waited for).

A table may set PANEL = (title or None, ((group, (line, ...)), ...)): the mission panel it starts with, when the
original reveals its objectives one at a time (New Hampton; "panel" steps add the rest, "done" steps complete them).
A table may set WIN = "table": the room is won only by a ("win",) step, not when its last hostile troop falls (Grey
Fog's finale is fought after the boss, against staging troops the win rule does not count). A table may set ESCORT = {ForceNum or troop alias, ...}: the allies the CPU leads along the story (owner 2026-09-28, the original's
footage: "they move all commanders and all attack the enemies", "the cpu control them and kill enemies"): each time
a bound step fires, those forces march to that bound ("escort" steps add more). HAND_LATER = {TroopID, ...}: player's
troops a "hand" step gives, not the start (Tower's archers come at the winged wyrms); one of a HOLD force also comes
in only with a step then (the camps' mock-battle troops). HAND = (TroopID, ...): the player's troops, in slot order,
where the designers' marks pick others (game.mission_plan G5: the camps hand one lesson troop, then swap it for the
mock battle's three; their PC-grade marks pick all four, or an allied archer). A table may also set
HOLD = {ForceNum, ...}: forces only its steps bring in (not spawned at the start, active troops too, left by the
proximity wake and the fallback), and HOLD_PROPS = {prop id, ...}: barriers only an "open" step opens (not the hero's
approach). NEXT = warp id: the won room goes on into that warp's mission instead of leaving (a windowless win:
game.end_without_window -> world.continue_mission; Sortie I 10361 into Sortie II 10362 through warp 622). Lines play
one after another; an action listed after a step's lines waits for them (a door opens once
its scene is told, Vert's summons come after his taunt). "after" timers of the story stop once the ending plays.
The engine is ours; each table says where its steps come from.

The line action, read from code 2026-09-28: ActGuiShowMissionHelpTextByTroopId 0xc76f (handler 0x140b35cd0), args
(leader 0/1, troop uid, visible-only 0/1, text id, seconds) -> 0x140b5cf90 -> 0x140c51e50(hud, -1, ...) ->
0x140c5f230: a troop found by uid gives the name and face (leader 1: its leader's, 0x140c5a910 / 0x140c59d60; 0: the
troop's, 0x140c5a7a0 / 0x140c599e0); none found shows the text alone when leader and visible-only are 0 and nothing
at all when either is 1. 0x140c65600 looks the id up in the map's missiontext (Data/Info/MissionText/, loaded into
hud +0x16d8 by 0x140d67b70), plays `<mission>/Voice/<id>` and calls the Flash Show_MissionHelpText; an unknown id
shows "Error ShowMissionHelpText -- TextID <id>". A troop spawned with its NP leader (game.spawn_zone_troop: Glen,
Thompson, Duran) speaks as its leader, by his name and face; the hero as himself."""
import functools
import importlib
import logging
import math
import pathlib
import time

from . import net
from .rules import ACT_HIGHLIGHT_TROOP

log = logging.getLogger("director")

ACT_HELP_TEXT_BY_TROOP = 0xc76f
ACT_CUTSCENE = 0x10d92          # ActCutScenePlayCutScene (0x140b3d090 -> 0x140b6ce80): (index, mode 0): the index into
                                 # the map's loaded cutscenes, which is the number their names start with (live
                                 # 2026-09-28, Grey Rock: 0_Start_CutScene ... 13_EndScene; 0 played the hanged corpses)
ACT_MOVE_TO_AREA = 0xc3a0        # ActTroopMoveToArea (0x140b31a40 -> 0x140b2d4e0): (kind 0 troop / 1 force, id, area,
                                 # goal, engage, flag, mode 0..2): a move order to the area (0x1407e7240, a player's
                                 # order path); live 2026-09-28 Glen walked east on it. Kind 0 needs the troop enabled
                                 # and active (0x140709740: +0x94 bit 0x10, +0x7f4) and simulated here (+0x230)
ACT_MOVE_STRAIGHT = 0xc3a2       # ActTroopMoveToAreaIgnoringPolyline (0x140b31c20 -> 0x140b9dc80): (kind, id, area, goal,
                                 # mode): always to the centre; order bit 0x8 skips the navmesh, and the units follow
                                 # (live 2026-11-05: pinned wolves walked out of their cages on it)
MOVE_CENTRE = 0                  # goal 0 -> 0x140b9dc80 -> 0x140b9dce0: to the area's centre (area +0x30)
MOVE_NEAREST = 1                 # goal 1 -> 0x140b9ec40 -> 0x140b9eca0: to the area's point nearest the troop
                                 # (0x140b93380, area vt+0x70), one troop radius further on
MOVE_RUN, MOVE_WALK = 0, 1       # the order's last field, its mode (+0x1c; 2: the troop's own), is a walk flag
                                 # (read 2026-09-30): TroopCommand::Move (vtable 0x142098c10) slot 0 0x14094b120 makes
                                 # the move task (TaskTroopMovePosition, 0x1407cdd90) with +0x2c = 0 / 1 / the troop's
                                 # walk flag +0x910 (0x1407df0b0); BehaviorTroopSV_MovePosition's enter (0x140579560)
                                 # sets +0x910 from it (0x1407df0c0), its exit (0x140579800) restores it; and
                                 # BehaviorTroopMove::UpdateWalkMode (0x1407145c0) moves a troop whose +0x910 is set at
                                 # speed mode 2, its walk speed (Troop vt+0x2e0: +0xcf0), else at mode 1, its run speed
                                 # (vt+0x2d8: stat 14 MAX_MOVE_SPEED). The client's own RTS.Troop_RunToArea clears the
                                 # flag and sends 0 (0x140ba0520), Troop_WalkToArea sets it and sends 2 (0x140ba03d0)
MOVE_MODE = MOVE_RUN             # what the marches send. Live 2026-09-30 on 1 (walk) Glen went at 180 units/s, his
                                 # troop type's (nptrooptype 1091) MAX_WALK_SPEED, and Tower's column at ~255, while
                                 # the tape runs at ~790: running, a troop goes at its MAX_MOVE_SPEED (Glen's troop
                                 # 133010: 600), which the Tower lesson cutscenes' Troop_SetRunSpeed (vt+0x318: 850-950,
                                 # 650 in 6_Tutorial_CX) set for Glen and the column when they play. The original's
                                 # cutscenes move troops on 0 in 189 of their 219 RTS.Troop_MoveToArea calls
ACT_RANGE_ATTACK = 0xc3f0        # ActTroopRangeAttack (0x140b34430): (kind, id, target, engage, flag) -> kind 0:
                                 # ScriptTroop::RangeAttack 0x140ba1280(uid, target, engage, flag): both enabled and
                                 # active (0x140709740), other teams, the target alive, the caster ranged (0x140707b40);
                                 # an order to it through 0x1407e7240, type 2 with engage (as ActTroopMoveToArea)
NEAREST_ENEMY = 0xFFFFFF34       # -204 as a target: the caster's nearest enemy (0x140ba0dc0, the handler 0x140b345fa)
ACT_NOTICE_WINDOW = 0xc8f0       # ActGuiShowNoticeWindow (0x140b39780 -> 0x140b5d070 -> UI window 0x29,
                                 # CommonSub2DTopLayer::ShowNoticeWarSituation 0x140dbaa80): (NoticeTable id, 4
                                 # missiontext ids, a5); each id from the map's missiontext (0x140dba0f0; -1 ends the
                                 # list, a miss shows "<id> MissionText"), a5 handed to Flash CA_setNoticeWarSituation
                                 # as an int. Not seen live.
NOTICE_LEFT = 10003              # NoticeTable MISSION_EVENT_OPEN_LEFT, Notice_System.png, the open sound
NOTICE_MID = 6                   # NoticeTable 6 MISSION_EVENT_OPEN_MID, Notice_System.png: the centred notice. The row's
                                 # Notice_Type picks the swf (0x140dc42b0, the type by the enum table 0x1434e14d0):
                                 # OPEN_MID (5) ../Notice/NoticeWarSituation_default, as the occupation phases;
                                 # OPEN_LEFT (6) ..._misson_left (10003, live), OPEN_RIGHT (7) ..._misson_right
NO_TEXT = 0xFFFFFFFF             # -1: the end of the ids
NOTICE_S = 10                    # a5: the original held its notices 10-14 s (its unit is Flash's: to see live)
ACT_START_TUTORIAL = 0xc896      # ActGuiStartTutorial (0x140b389e0): a C string, the MissionTutorialType name, read
                                 # from the packet (0x1415835b0) -> 0x140b5db20: looked up by name, a showing one is
                                 # closed first; FinishTutorial 0xc897 / CompleteTutorial 0xc898 take no argument
ACT_HIGHLIGHT_AREA = 0xc7b0      # ActGuiSetHighlightArea (0x140b36980): (area id, seconds, on): the area marked on the
HIGHLIGHT_S = 600                # ground and the minimap (planning/client/mission_script.md); seconds ours, the mark
                                 # taken down by the table when the place is reached (the handler's use of it unread)
# ActGuiSetHighlightTroop 0xc7ba (rules.ACT_HIGHLIGHT_TROOP): (troop, seconds, on, leader), 0x140b36aa0 reads them in
# that order for 0x140b2e8d0; on 1 -> 0x140b5cb30 -> the HUD's highlight entry (0x140c569f0: seconds <= 0 kept until
# taken down) and UiFxMarker's troop marker (0x140c78f30 -> PlayTargetTroopMarker, ALLIANCE blue on an ally); on 0 ->
# 0x140b5cb50 takes it down
HIGHLIGHT_LEADER = 1             # its leader flag: the marker at the troop's leader (troop +0x838) when it has one,
                                 # else at the troop (0x140c78f30 -> 0x140c76b80, read 2026-09-30): the lone figure
                                 # the tape's pillar stands over (Glen, 10:36-10:46)
ACT_DIRECTION_TO_AREA = 0xc756  # ActGuiShowDirectionToTargetArea (0x140b35a70 -> 0x140b7d0d0): (area id, seconds);
                                 # the area from the client's zone areas by id (0x140b93310, a miss returns safely),
                                 # GenericCamera 0x140aa63d0 shows the direction effect toward it for seconds x 1000 ms
ACT_FINISH_TUTORIAL = 0xc897     # ActGuiFinishTutorial (0x140b38a90): no argument
ACT_COMPLETE_TUTORIAL = 0xc898   # ActGuiCompleteTutorial (0x140b38b30 -> 0x140b5db70 -> 0x14094e510(tutorial, 0)): no
                                 # argument; completes page 0 whatever page shows (mission_script.md §3.12)
COND_TUTORIAL_PAST = 0xcb2b      # condition (lesson name, n) -> 0x140b5dbb0: that mission tutorial shows (+8) and its
                                 # page (+4) is past n; n = -1: it shows (mission_script.md §5.1)
COND_TUTORIAL_COMPLETE = 0xc760  # no args; current tutorial +0 completed flag, not its visible/closed state
POLL_S = 0.5                     # ours: a condition answered "no" is asked again this much later
NO_KEY_PROMPT = 0x7f             # a key prompt with key 0: never checked, so it never times out, and first in the
                                 # client's list it stops the 30 s timeout of the ones after it (0x140b25a40, §5.2)
# The InputEvent values lesson prompts wait for, with their default keys (Data/Script/ControlSetting.lua, Script.pkg)
KEY_SELECT_ALL_TROOP = 0x33      # KEY_Select_AllTroop, F4: the hero and every troop (Grey Rock's 1_F4_Check)
KEY_SELECT_HERO = 0x34           # KEY_SelectTroop1, `: the hero
KEY_SELECT_TROOP3 = 0x36         # KEY_SelectTroop3, F2: the second troop slot
KEY_TROOP3_SKILL1 = 0x2b         # KEY_UseAbilityC9, Ctrl + A: the third troop's first skill (Ctrl + 1-4 / Q-R / A-F
                                 # are troops 1 / 2 / 3; New Hampton's 1_TroopSkill_Tuto, its trebuchet's Fireball)
KEY_SELECT_TARGET = 0x81         # KEY_SelectTarget: the left button picking a skill's target or ground while targeting
KEY_AI_HERO_SUPPORT = 0x3a       # KEY_AIHeroSupport, C
KEY_ZOOM = (0x3f, 0x40)          # KEY_SceneToggleDown / Up: the mouse wheel
KEY_CAMERA_ROTATED = 0x77        # KEY_MouseCameraRotEnd: the right button released after turning the camera
KEY_CAMERA_MOVE = (0x7c, 0x7d, 0x7e, 0x7f)   # KEY_CameraMoveForward / Back / Left / Right: W S A D
# the training camps' lessons (1_TrainingCamp's 1_Tab, planning/scripts/cutscenes.json; the camps' notices "@K_1")
KEY_CHANGE_CONTROL_MODE = 0x30   # KEY_ChangeControlMode, Tab: the strategy view
KEY_SELECT_TROOP2 = 0x35         # KEY_SelectTroop2, F1: the first troop slot
KEY_SELECT_TROOP4 = 0x37         # KEY_SelectTroop4, F3: the third
KEY_AI_OFFENSIVE = 0x38          # KEY_AIOffensive, Z
KEY_AI_DEFENSIVE = 0x39          # KEY_AIDefensive, X
KEY_USE_ABILITY1 = 0x15          # KEY_UseAbility1, 1: the selected troop's first skill (the Spearman's Line change)
KEY_TROOP1_SKILL1 = 0x23         # KEY_UseAbilityC1, Ctrl + 1: the first troop's first skill
# the prologue's lessons (1_AziliaCastle; planning/controls/HERO-CONTROLS.md §2): the hero's own keys
KEY_PAD_A = 0x06                 # KEY_Pad_A_Press, the left button: the basic attack chain ("Use Basic Attack")
KEY_PAD_X = 0x07                 # KEY_Pad_X_Press, the right button: the special attack chain ("Use Special Attack")
KEY_PAD_X_HOLD = 0x96            # KEY_Pad_X_Hold, the right button held: the Ranger's Aimed Shot (ChargeShot_Olivia)
KEY_GUARD = 0x08                 # KEY_UseAbilitySpecialKey1, Shift: guard ("Block enemy attacks", Defence)
KEY_DASH = 0x09                  # KEY_UseAbilitySpecialKey2, Space: Charge, and Escape while immobilised (Groggy)
KEY_SKILL_SLOTS = tuple(range(0x15, 0x1d))   # KEY_UseAbility1..8, 1-8: the quick bar's skills ("Use skills in the
                                             # Skill slots")
KEY_ACTION = 0x32                # KEY_ActionKey, F: the prompt's F icon ("Press F to check!", textui 9000 "Look far")
KEY_FRIEND_AND_FOE = 0x43        # KEY_FriendAndFoe, V: Enemy Identification (Command_V)
KEY_RUNE = 0x44                  # KEY_UseRuneAbilitySpecialKey, R: the class's rune key (the Rune_Skill_* lessons)
KEY_RIGHT_ORDER = (0x84, 0x83, 0x57)   # KEY_DefensiveMove, KEY_Interaction, KEY_MouseRClick: the right button's
                                       # order to the troops selected, a move or an attack (ControlSetting.lua binds
                                       # all three to VK_MOUSE_BTN_RIGHT; KEY_OffensiveMove is the left button)
KEY_NAMES = {v: k for k, vs in list(globals().items()) if k.startswith("KEY_")      # the journal's names for them
             for v in (vs if isinstance(vs, tuple) else (vs,))}
ACT_CAMERA_SET = 0xe682          # ActCameraSetCamera (0x140b3c210): (i32 n); n < 0 sets the cutscene wait state
                                 # System_WaitState(n) waits for (the "state" action), n >= 0 camera n (0x140b516d0)
ACT_CAMERA_ATTACH_TROOP = 0xe68c  # (troop uid, channel 2): 0x140b505d0 binds camera axis 5
ACT_CAMERA_SET_DEFAULT = 0xe6b9   # (-1, tactical preset, flying preset or -1): 0x140b52520
ACT_CAMERA_RESTORE_DEFAULT = 0xe6ba  # reset the common camera bindings on each room entry
ON_SCREEN = ("tutorial", "notice", "banner")   # actions that wait while a line or a cutscene holds the queue
NO_TROOP = 0xFFFF                # a uid no troop has: the text alone
CHARS_PER_S = 12                 # ours: reading time of a line with no voice length known
MIN_LINE_S = 3
ENDING_PAUSE = 1.0               # ours: after the last ending line, before the victory window


SCENES = pathlib.Path(__file__).parent / "scenes"     # where a mission's m<spot>.lua is looked for


@functools.lru_cache(maxsize=None)
def mission(spot):
    """The mission's table: scenes/m<spot>.lua when that file exists (lua_script.load: its steps and its Mission{}
    settings; a parse error raises, naming the file, line and column), else scenes/m<spot>.py (STEPS and the settings
    it sets: HOLD, ESCORT, HAND, ...); {} when it has neither."""
    from . import lua_script
    lua = SCENES / f"m{spot}.lua"
    if lua.is_file():
        return lua_script.load(lua.read_text(encoding="utf-8-sig"), str(lua))   # -sig: Notepad's BOM
    name = f"{__package__}.scenes.m{spot}"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as e:
        if e.name != name:
            raise
        return {}
    return {k: getattr(mod, k) for k in ("STEPS", *lua_script.SETTINGS) if hasattr(mod, k)}


@functools.lru_cache(maxsize=None)
def script(spot):
    """The mission's steps (its table's STEPS, mission), () when it has no table."""
    return tuple(mission(spot).get("STEPS", ()))


@functools.lru_cache(maxsize=None)
def _table(spot, name):
    return frozenset(mission(spot).get(name, ()))


def late_allies(spot):
    """The held allies that come with a step of the table, not with their group (scenes/m<spot>.py LATE_ALLIES: New Hampton's
    reinforcements, F46600, with Glen's 5900), frozenset() without one."""
    return _table(spot, "LATE_ALLIES")


def held(spot):
    """The forces the mission's table brings in itself (scenes/m<spot>.py HOLD), frozenset() without one."""
    return _table(spot, "HOLD")


def harmless(spot):
    """The forces whose hits are for show (scenes/m<spot>.py HARMLESS): their records carry "harmless", no hit of theirs
    lands; a troop of theirs the table hands the player (HAND) hits for real."""
    return _table(spot, "HARMLESS")


def escort(spot):
    """The ally forces (or troop aliases) the CPU leads along the table's story places (ESCORT)."""
    return _table(spot, "ESCORT")


def hand_later(spot):
    """The player's troops the table gives with a "hand" step, not at the start (HAND_LATER)."""
    return _table(spot, "HAND_LATER")


@functools.lru_cache(maxsize=None)
def hand(spot):
    """The player's troops the table names, in slot order (HAND), () without."""
    return tuple(mission(spot).get("HAND", ()))


def held_props(spot):
    """The barriers only the table's steps open (HOLD_PROPS)."""
    return _table(spot, "HOLD_PROPS")


@functools.lru_cache(maxsize=None)
def lines(spot):
    """{text id: text} of the spot's map (missiontext/eng/<Map_File>), the table the client shows them from."""
    from . import tables
    row = tables.by_id("spottable").get(str(spot)) or {}
    try:
        rows = tables.sections("missiontext\\eng\\" + str(row.get("Map_File", "")).lower())["TextTable"]
    except KeyError:
        return {}
    return {int(r["textID"]): r["text"] for r in rows if str(r["textID"]).isdigit()}


@functools.lru_cache(maxsize=None)
def bound(spot, key):
    """The zone EventBound named key (EventBoundName, or EventBoundID for an int); None when there is none."""
    from . import zone
    for b in zone.for_spot(spot).get("EventBound") or []:
        if (b.get("EventBoundID") == key) if isinstance(key, int) else (str(b.get("EventBoundName")) == key):
            return b
    return None


def _alias(t):
    return str(t.get("TroopAlias") or "").replace(" ", "")


def troop_uid(s, who):
    """A speaker or an actor: "hero" -> 0, a TroopID as is, a TroopAlias -> the spawned zone troop of that alias
    (spaces ignored), else the first zone troop of that alias; None when nothing matches."""
    from . import zone
    if who == "hero":
        return 0
    if isinstance(who, int):
        return who
    key = str(who).replace(" ", "")
    spawned = s.data.get("zone_troops", {})
    hit = next((u for u, t in spawned.items() if _alias(t) == key), None)
    if hit is not None:
        return hit
    return next((t["TroopID"] for t in zone.for_spot(s.data["spot"])["NPCTroopInfoData"] if _alias(t) == key), None)


def _state(s):
    return s.data.setdefault("director", {"fired": set(), "free_at": 0.0, "ending": None})


def line_seconds(text):
    return max(MIN_LINE_S, math.ceil(len(text) / CHARS_PER_S))


def say(s, speaker, line, seconds=None, before=()):
    """Queue one line: it shows when the lines before it are done, for `seconds` (by its length when not given);
    `before`, a step's actions listed ahead of it, run just before it shows (one moment, the table's order)."""
    text = lines(s.data["spot"]).get(line)
    if text is None:
        log.warning("mission %s: line %s is not in the map's missiontext", s.data.get("spot"), line)
        _after_lines(s, before)
        return
    seconds = seconds or line_seconds(text)
    before = _take_held(s) + list(before)
    if isinstance(speaker, tuple):                  # the first of them in the room and standing
        present = lambda w: troop_uid(s, w) in s.data.get("zone_troops", {}) and troop_uid(s, w) not in s.data.get(
            "down", set())
        speaker = next((w for w in speaker if present(w)), speaker[0] if speaker else None)
    uid = troop_uid(s, speaker) if speaker is not None else None
    here = uid == 0 or uid in s.data.get("zone_troops", {})
    battle = s.data.get("battle")
    lead = uid == 0 or (here and battle is not None and "leader" in battle.troops.get(uid, {}))
    act = [ACT_HELP_TEXT_BY_TROOP, int(lead), uid if here else NO_TROOP, 0, line, seconds]
    d = _state(s)
    now = time.monotonic()
    at = max(now, d["free_at"])
    d["free_at"] = at + seconds

    def show():
        from . import game
        for a in before:
            _run_live(s, a)
        game.send_actions(s, act)
        log.info("director: mission %s line %d (%s): %s", s.data.get("spot"), line, speaker, text[:60])
        net.journal("say", spot=s.data.get("spot"), line=line, speaker=speaker, text=text[:120])
    if at <= now:
        show()
    else:
        s.later(at - now, show)


def cutscene(s, index, seconds, before=()):
    """Queue a cutscene like a line: it plays when the lines before it are done and holds the queue for its length."""
    before = _take_held(s) + list(before)
    d = _state(s)
    now = time.monotonic()
    at = max(now, d["free_at"])
    d["free_at"] = at + seconds

    def play():
        from . import game
        for a in before:
            _run_live(s, a)
        game.send_actions(s, [ACT_CUTSCENE, index, 0])
        log.info("director: mission %s cutscene %d (%d s)", s.data.get("spot"), index, seconds)
        net.journal("cutscene", spot=s.data.get("spot"), index=index, secs=seconds)
    if at <= now:
        play()
    else:
        s.later(at - now, play)


def march(s, who, area, goal=MOVE_NEAREST, straight=False, engage=1, one=False):
    """Order a force's standing troops (or one troop, by alias) to area, as ActTroopMoveToArea: goal (MOVE_CENTRE /
    MOVE_NEAREST), engage 1, mode MOVE_MODE (the run); the player's own troops (game.mission_plan hand)
    take their orders from him. one: only the first of them still standing."""
    from . import game
    troops, down = s.data.get("zone_troops", {}), s.data.get("down", set())
    mine = set((s.data.get("plan") or {}).get("hand", ()))
    if isinstance(who, str):
        uids = [troop_uid(s, who)]
    else:
        uids = [u for u, t in troops.items() if t.get("ForceNum") == who]
    uids = [uid for uid in uids if uid in troops and uid not in down and uid not in mine]
    uids = uids[:1] if one else uids
    for uid in uids:
        game.troop_order(s, uid, [ACT_MOVE_STRAIGHT, 0, uid, area, goal, MOVE_MODE] if straight
                         else [ACT_MOVE_TO_AREA, 0, uid, area, goal, engage, 0, MOVE_MODE])
    log.info("director: mission %s: %s marches to area %s", s.data.get("spot"), who, area)
    net.journal("march", spot=s.data.get("spot"), who=who, area=area, goal=goal, troops=uids)


def route(s, who, path, exit=None):
    """A troop (alias or TroopID) onto zone MissionPath `path` (the "route" action): SetSpawnAI 0x5083 again with its
    own program (game.table_ai) and zone leash, path 1 set (the TAI's MoveThroughPaths branch, COMPANIONS-EVIDENCE §6);
    with `exit` (a bound), it leaves the battle when the host reports it there (on_troops)."""
    from . import game
    uid = troop_uid(s, who)
    t = s.data.get("zone_troops", {}).get(uid)
    if t is None or uid in s.data.get("down", set()):
        return
    game.send_spawn_ai(s, uid, game.table_ai(t["TroopTableID"]), zt={**t, "DefaultPath1ID": path})
    if exit is not None:
        _state(s).setdefault("exits", {})[uid] = exit
    log.info("director: mission %s: troop %s runs path %s%s", s.data.get("spot"), uid, path,
             f", leaving at bound {exit}" if exit is not None else "")
    net.journal("route", spot=s.data.get("spot"), troop=uid, path=path, exit=exit)


def on_troops(s, places):
    """The host's troop positions (game.troop_sync, C2S 0x50b0 {uid: (x, y, z)}): a routed troop inside its exit bound
    leaves the battle (game.troop_leaves), as the original's fleeing militiaman vanished at Grey Fog's 도망."""
    exits = (s.data.get("director") or {}).get("exits")
    if not exits:
        return
    from . import game
    for uid, exit in list(exits.items()):
        if uid in s.data.get("down", set()):            # fell on the way
            exits.pop(uid)
            continue
        b, p = bound(s.data["spot"], exit), places.get(uid)
        if b is not None and p is not None and game.inside_bound(b, p[0], p[2]):
            exits.pop(uid)
            game.troop_leaves(s, uid)


def run(s, action):
    from . import game
    kind, args = action[0], action[1:]
    if kind == "say":
        say(s, *args)
    elif kind == "wake":
        for force in args:
            game.spawn_force(s, force)
    elif kind == "spawn":
        game.spawn_troops(s, args)
    elif kind == "highlight":
        b = bound(s.data["spot"], args[0])
        if b is not None and b.get("EventBoundID") is not None:
            game.send_actions(s, [ACT_HIGHLIGHT_AREA, b["EventBoundID"], HIGHLIGHT_S, args[1] if len(args) > 1 else 1])
    elif kind == "highlight troop":
        uid = troop_uid(s, args[0])
        on, secs = (args[1] if len(args) > 1 else 1), (args[2] if len(args) > 2 else 0)
        if uid in s.data.get("zone_troops", {}):
            game.send_actions(s, [ACT_HIGHLIGHT_TROOP, uid, secs, on, HIGHLIGHT_LEADER])
            log.info("director: mission %s: troop %s marked %s", s.data.get("spot"), args[0], "on" if on else "off")
    elif kind == "point":
        b = bound(s.data["spot"], args[0])
        if b is not None and b.get("EventBoundID") is not None:
            game.send_actions(s, [ACT_DIRECTION_TO_AREA, b["EventBoundID"], POINT_S])
    elif kind in ("march", "march straight", "march line", "march past", "march one"):
        b = bound(s.data["spot"], args[1])
        if b is not None and b.get("EventBoundID") is not None:
            march(s, args[0], b["EventBoundID"], MOVE_NEAREST if kind == "march line" else MOVE_CENTRE,
                  straight=kind in ("march straight", "march one"), engage=0 if kind == "march past" else 1,
                  one=kind == "march one")
    elif kind == "route":
        route(s, *args)
    elif kind == "leave":
        uid = troop_uid(s, args[0])
        if uid is not None and uid != 0:
            game.troop_leaves(s, uid)
    elif kind == "shoot":
        uid = troop_uid(s, args[0])
        target = NEAREST_ENEMY if args[1] == "nearest" else troop_uid(s, args[1])
        mine = set((s.data.get("plan") or {}).get("hand", ()))
        if (uid in s.data.get("zone_troops", {}) and uid not in s.data.get("down", set()) and uid not in mine
                and target is not None):
            game.troop_order(s, uid, [ACT_RANGE_ATTACK, 0, uid, target, 1, 0])
            log.info("director: mission %s: %s shoots at %s", s.data.get("spot"), args[0], args[1])
    elif kind in ("move", "move deck"):
        # Optional player troop in a scene: an empty deck has no actor to place.
        if kind == "move deck" and args[0] not in s.data.get("deck", {}):
            return
        uid, b = troop_uid(s, args[0]), bound(s.data["spot"], args[1])
        if uid is None or b is None:
            log.warning("director: move %s to %s: no such troop or bound", args[0], args[1])
            return
        if uid in s.data.get("down", set()):            # fallen or gone (a wizard the player did not pick)
            return
        y = game.start_pos(s)[1] if uid == 0 else 0
        dx, dz = args[2] if len(args) > 2 else (0, 0)
        x, z = b["BoundCenterX"] + dx, b["BoundCenterZ"] + dz
        game.move_troop(s, uid, (x, y, z))
        if uid == 0:
            s.data["hero_pos"] = (round(x), y, round(z))
        elif uid in s.data.get("zone_troops", {}):      # where the room now has it (the pointer, the walker); a
            zt = s.data["zone_troops"]                  # copy: the zone content is cached and shared
            zt[uid] = dict(zt[uid], PosX=round(x), PosZ=round(z))
    elif kind == "open":
        if args[0] in s.data.get("barriers", {}):
            game.open_barriers(s, None, "the script", only=args[0])
        elif game.zone_prop(s.data["spot"], args[0]) is not None:
            game.switch_on(s, game.zone_prop(s.data["spot"], args[0]))
    elif kind == "cutscene":
        cutscene(s, args[0], args[1])
    elif kind == "fade":
        game.send_actions(s, [game.ACT_FADE, args[1], args[2], int(args[0])])
    elif kind == "notice":
        from . import game
        ids = (list(args) + [NO_TEXT] * 4)[:4]
        game.send_actions(s, [ACT_NOTICE_WINDOW, NOTICE_LEFT, *ids, NOTICE_S])
        for i in args:
            log.info("director: mission %s notice %s", s.data.get("spot"), i)
        net.journal("notice", spot=s.data.get("spot"), ids=list(args), text=lines(s.data["spot"]).get(args[0]))
    elif kind == "panel":
        game.panel_line(s, args[0], args[1])
    elif kind == "panel start":
        game.mission_panel(s)
    elif kind == "banner":
        ids = (list(args) + [NO_TEXT] * 4)[:4]
        game.send_actions(s, [ACT_NOTICE_WINDOW, NOTICE_MID, *ids, NOTICE_S])
        log.info("director: mission %s banner %s", s.data.get("spot"), list(args))
        net.journal("notice", spot=s.data.get("spot"), ids=list(args), text=lines(s.data["spot"]).get(args[0]),
                    where="mid")
    elif kind == "done":
        game.panel_done(s, args[0])
    elif kind == "count":
        _state(s).setdefault("counts", {})[args[2]] = (args[0], args[1])
        count(s, args[2])
    elif kind == "clock":
        _state(s).get("clocks_stopped", set()).discard(args[0])
        countdown(s, *args)
    elif kind == "clock off":
        stop_countdown(s, args[0])
    elif kind == "gauge":
        uid = troop_uid(s, args[2])
        t = (s.data.get("battle").troops.get(uid) if s.data.get("battle") and uid is not None else None) or {}
        from . import combat
        _state(s).setdefault("gauges", {})[uid] = (args[0], args[1], None)
        gauge(s, uid, combat.Battle.total(t) if t else 1, t.get("max") or 1)
    elif kind == "troops bar":
        uid = troop_uid(s, args[1])
        if uid in s.data.get("zone_troops", {}):
            game.panel_troops_bar(s, args[0], uid)
    elif kind == "force bar":
        game.panel_force_bar(s, args[0], args[1])
    elif kind == "tutorial":
        from . import game
        game.send_actions(s, [ACT_START_TUTORIAL, args[0]])
        log.info("director: mission %s tutorial %s", s.data.get("spot"), args[0])
        net.journal("lesson", spot=s.data.get("spot"), ev="start", name=args[0])
    elif kind == "finish":
        game.send_actions(s, [ACT_FINISH_TUTORIAL])
        log.info("director: mission %s lesson closed", s.data.get("spot"))
        net.journal("lesson", spot=s.data.get("spot"), ev="closed (finish)")
    elif kind == "complete":
        game.send_actions(s, [ACT_COMPLETE_TUTORIAL])
        log.info("director: mission %s lesson completed", s.data.get("spot"))
        net.journal("lesson", spot=s.data.get("spot"), ev="completed (page 1)")
    elif kind == "state":
        game.send_actions(s, [ACT_CAMERA_SET, args[0] & 0xFFFFFFFF])
        log.info("director: mission %s wait state %d", s.data.get("spot"), args[0])
    elif kind == "untouchable troop":
        uid = troop_uid(s, args[0])
        battle = s.data.get("battle")
        troop = battle and battle.troops.get(uid)
        if troop is not None and uid in s.data.get("zone_troops", {}) and args[1] in (0, 1):
            # Native 0xea9c ref(kind=0, uid), on -> 0x140b2e1a0. Damage is
            # server-owned, so retain the matching flag on this room's troop.
            troop["untouchable"] = bool(args[1])
            game.troop_order(s, uid, [0xea9c, 0, uid, args[1]])
            log.info("director: mission %s troop %d untouchable %d", s.data.get("spot"), uid, args[1])
    elif kind == "camera troop":
        uid = troop_uid(s, args[0])
        if uid in s.data.get("zone_troops", {}) and args[1] >= 0:
            # The next-frame control-mode transition and F1 use the tactical
            # default. Bind it too, or they overwrite the selected mission preset.
            # Room entry restores defaults before the next director starts.
            game.troop_order(s, uid, [ACT_CAMERA_ATTACH_TROOP, uid, 2])
            # 0x140b52520 updates the active default only from a tactical camera
            # (0x140aa65e0). Entry is still on action camera10052 until next frame.
            game.troop_order(s, uid, [ACT_CAMERA_SET, 10054])
            game.troop_order(s, uid, [ACT_CAMERA_SET_DEFAULT, 0xFFFFFFFF, args[1], 0xFFFFFFFF])
            game.troop_order(s, uid, [ACT_CAMERA_SET, args[1]])
            log.info("director: mission %s camera %d queued for troop %d", s.data.get("spot"), args[1], uid)
    elif kind == "escort":
        _state(s).setdefault("escort", set()).update(args)
    elif kind == "hand":
        uid = troop_uid(s, args[0])
        if uid in s.data.get("zone_troops", {}) and uid not in s.data.get("down", set()):
            game.hand_troop(s, uid)
    elif kind == "heal" and args:
        from . import combat
        uid = troop_uid(s, args[0])
        if uid is not None:
            combat.heal_troop(s, uid)
    elif kind == "heal":
        t = s.data.get("battle") and s.data["battle"].troops.get(0)
        if t:
            game.heal_hero(s, t["max"])
    elif kind == "win":
        game.mission_won(s, s.state)
    else:
        log.warning("director: unknown action %r", action)


def countdown(s, group, text, seconds):
    """A "clock" action: the panel's clock line at `seconds`, then one second less each second down to 0, where it
    stays; not once the mission is won."""
    if s.data.get("mission_won") or group in _state(s).get("clocks_stopped", set()):
        return
    from . import rules
    _state(s).setdefault("clocks", {})[group] = text
    rules.panel_time(s, group, text, seconds)
    if seconds > 0:
        s.later(1.0, lambda: countdown(s, group, text, seconds - 1))


CLOCK_GONE_S = 1                 # a stopped clock's group goes this long after it shows 00:00:00 (the tape 41:07-41:08)


def stop_countdown(s, group):
    """A "clock off" action: the clock under group stops counting, shows 00:00:00, and its group goes CLOCK_GONE_S
    later (ActGuiRemoveObjectiveGroupToMissionSituation 0xc7ed); nothing when no clock of that group runs."""
    d = _state(s)
    text = d.get("clocks", {}).get(group)
    if text is None or group in d.setdefault("clocks_stopped", set()):
        return
    d["clocks_stopped"].add(group)
    from . import game, rules
    rules.panel_time(s, group, text, 0)
    log.info("director: mission %s: the clock %s stops", s.data.get("spot"), group)
    net.journal("panel", spot=s.data.get("spot"), what="clock off", ids=[group])

    def gone():
        s.data.get("panel_groups", set()).discard(group)
        game.send_actions(s, [rules.ACT_SITUATION_REMOVE_GROUP, game.ALL_TEAMS, group])
    s.later(CLOCK_GONE_S, gone)


def fire(s, i, why=None):
    """Run step i once, then schedule the steps that come after it; why: the values that made its trigger hold (the
    journal's)."""
    steps = script(s.data["spot"])
    d = _state(s)
    step = steps[i]
    if i in d["fired"] or not for_hero(s, step):
        return
    if _excluded(s, step):                          # the other branch was taken
        _drop(s, i)
        return
    if step.get("needs") is not None and not _has_fired(s, step["needs"]):
        d.setdefault("waiting", set()).add(i)       # it fires right after the step it needs
        _journal_waits(s)
        return
    now = time.monotonic()
    if step.get("repeat"):                          # not again while its last lines still play (Glen's heal under
        if d.setdefault("again_at", {}).get(i, 0) > now:     # rapid hits queued 78 s of lines)
            return
    else:
        d["fired"].add(i)
    log.info("director: mission %s step %d (%s)", s.data.get("spot"), i, step.get("id") or step["on"])
    net.journal("step", spot=s.data.get("spot"), step=i, id=step.get("id"), on=step["on"], why=why, do=step.get("do"))
    told, held = False, []                           # a line of this step is queued: the actions after it wait, and
    for action in step.get("do", ()):               # go with the next line (two timers for one moment fire in no
        if action[0] in ("say", "cutscene"):        # set order: a tutorial came after the line it precedes)
            (say if action[0] == "say" else cutscene)(s, *action[1:], before=held)
            held, told = [], True
        elif (told or action[0] in ON_SCREEN) and d["free_at"] > time.monotonic():
            held.append(action)
        else:
            run(s, action)
    _after_lines(s, held)
    if step["on"] == "bound":                       # the CPU leads the allies to the story's place
        b = bound(s.data["spot"], step["bound"])
        for who in escort(s.data["spot"]) | d.get("escort", set()):
            if b is not None and b.get("EventBoundID") is not None:
                march(s, who, b["EventBoundID"])
    if step.get("repeat"):                          # not again while ITS lines play (a step with none: at once)
        d["again_at"][i] = d["free_at"] if told else 0.0
    for j, other in enumerate(steps):               # the branches this one closes
        if j not in d["fired"] and _excluded(s, other):
            _drop(s, j)
    if step.get("id") is None:
        _journal_waits(s)
        return
    ending = step["on"] == "won"
    for j, later in enumerate(steps):
        if later["on"] == "after" and later.get("step") == step["id"]:
            wait = max(0.0, d["free_at"] - time.monotonic()) + later.get("s", 0)
            s.later(wait, lambda j=j: _fire_live(s, j, ending))
            d.setdefault("timers", {})[j] = int((time.time() + wait) * 1000)     # its due time, for the wait list
    arm(s, step["id"])
    for j in sorted(d.get("waiting", ())):          # the steps that waited for this one
        if steps[j].get("needs") == step["id"]:
            d["waiting"].discard(j)
            fire(s, j, {"then": step["id"]})
    _journal_waits(s)


def _has_fired(s, sid):
    fired, dropped = _state(s)["fired"], _state(s).get("dropped", set())
    return any(st.get("id") == sid and j in fired and j not in dropped for j, st in enumerate(script(s.data["spot"])))


def _excluded(s, step):
    """Whether a step's "unless" (a step id, or a tuple of them) has fired: the other branch was taken."""
    unless = step.get("unless")
    if unless is None:
        return False
    return any(_has_fired(s, sid) for sid in (unless if isinstance(unless, tuple) else (unless,)))


def _drop(s, i):
    """Step i will never fire (its "unless" fired): marked done, no longer waiting, its key prompts taken down."""
    from . import game
    d = _state(s)
    d["fired"].add(i)
    d.setdefault("dropped", set()).add(i)
    d.get("waiting", set()).discard(i)
    for pid in [p for p, j in d.get("prompts", {}).items() if j == i]:
        del d["prompts"][pid]
        d.get("prompt_keys", {}).pop(pid, None)
        game.cancel_prompt(s, pid)
    net.journal("dropped", spot=s.data.get("spot"), step=i, id=script(s.data["spot"])[i].get("id"))


def _after_lines(s, actions):
    """Run actions when the queued lines are done (now, if none are), in the queue's order: the next line or scene
    queued takes them first (_take_held), since two timers for one moment fire in no set order (Grey Rock's FP notice,
    held behind 1260, came after the bridge's 1270 queued for that same moment by a later step; the tape has 1260,
    6010 / 6011, then 6004 / 6005 and 1270: part 2 31:28-32:02)."""
    if not actions:
        return
    d = _state(s)
    wait = d["free_at"] - time.monotonic()
    if wait > 0:
        entry = list(actions)
        d.setdefault("held", []).append(entry)

        def due():
            if any(e is entry for e in d.get("held", ())):      # no line took them
                d["held"] = [e for e in d["held"] if e is not entry]
                for a in entry:
                    _run_live(s, a)
        s.later(wait, due)
    else:
        for a in actions:
            run(s, a)


def _take_held(s):
    """The actions earlier steps left for the end of the queued lines (_after_lines), for the line or scene queued now:
    they run just before it shows, in their order."""
    return [a for e in _state(s).pop("held", ()) for a in e]


def _fire_live(s, i, ending=False):
    """A timed step: not once the mission is won, nor a story step while the ending plays."""
    _state(s).get("timers", {}).pop(i, None)
    if not s.data.get("mission_won") and (ending or not _state(s)["ending"]):
        st = script(s.data["spot"])[i]
        fire(s, i, {"after": st.get("step"), "s": st.get("s", 0)})


def _run_live(s, action):
    if not s.data.get("mission_won"):
        run(s, action)


def for_hero(s, st):
    """Whether step st is this room's: one with "class" only for a hero of that class, one with "difficulty" only in a
    room entered on it, any other for all."""
    if st.get("difficulty") is not None and not _one_of(st["difficulty"], s.data.get("difficulty", 0)):
        return False
    if st.get("class") is None:
        return True
    from . import game
    return game.hero_char(s).get("class") == st["class"]


def _pending(s, on):
    """(index, step) of the steps of trigger `on` that have not fired, in a room with a table (the hero's: for_hero)."""
    if s.data.get("mission_won"):
        return []
    fired = _state(s)["fired"]
    return [(i, st) for i, st in enumerate(script(s.data.get("spot")))
            if st["on"] == on and i not in fired and for_hero(s, st)]


def start(s):
    for i, _ in _pending(s, "start"):
        fire(s, i)
    arm(s, None)


def arm(s, sid):
    """The "cond" and "prompt" steps that need step sid (None: none) start to wait: the client is asked their
    condition, the player's keys are prompted."""
    d = _state(s)
    waiting = set(d.get("asked", {}).values()) | set(d.get("prompts", {}).values())   # once (a "repeat" sid fires
    for i, st in _pending(s, "cond") + _pending(s, "prompt"):                          # again)
        if st.get("needs") != sid or i in waiting:
            continue
        if st["on"] == "cond":
            log.info("director: mission %s step %d asks the client 0x%x %r", s.data.get("spot"), i, st["cond"][0],
                     st["cond"][1:])
            ask(s, i)
        else:
            prompt(s, i)
    _journal_waits(s)


def waits(s):
    """What the room's table waits for now (the journal's wait list): each step not fired whose turn has come, as
    {"step": i, "id": sid, "on": trigger, ...}: a bound (its name when the table gives its id), a force or a troop (a
    count, an hp %), a timer's due time (epoch ms), a condition asked (its id and args), the key prompts up ([prompt
    id, InputEvent, name]); a step whose trigger came first and still needs a step says which ("then"). Steps whose
    needed step has not fired, and "after" steps whose step has not, are left out."""
    steps, d = script(s.data.get("spot")), _state(s)
    if s.data.get("mission_won"):
        return []
    out = []
    for i, st in enumerate(steps):
        if i in d["fired"] or not for_hero(s, st):
            continue
        w = {"step": i, "on": st["on"], **({"id": st["id"]} if st.get("id") else {})}
        if i in d.get("waiting", ()):
            w["then"] = st["needs"]
        elif st.get("needs") is not None and not _has_fired(s, st["needs"]):
            continue
        elif st["on"] == "after":
            if i not in d.get("timers", {}):
                continue
            w.update(after=st["step"], due=d["timers"][i])
        elif st["on"] == "cond":
            w.update(cond=st["cond"][0], args=list(st["cond"][1:]))
        elif st["on"] == "prompt":
            keys = d.get("prompt_keys", {})
            up = [[p, keys.get(p), KEY_NAMES.get(keys.get(p))] for p, j in d.get("prompts", {}).items() if j == i]
            if up:
                w["prompts"] = up
            else:
                w["keys"] = [[k, KEY_NAMES.get(k)] for k in st["keys"]]
        elif st["on"] == "bound":
            w["bound"] = st["bound"]
            if isinstance(st["bound"], int):
                w["name"] = (bound(s.data["spot"], st["bound"]) or {}).get("EventBoundName")
        else:
            w.update({k: st[k] for k in ("force", "troop", "count", "below", "prop", "bound") if k in st})
        out.append(w)
    return out


def _journal_waits(s):
    """The wait list into the journal when it changed, with what changed: the entries new or different, the steps
    gone."""
    if net.journal_out is None:
        return
    w, d = waits(s), _state(s)
    old = d.get("waits_told")
    if w != old:
        d["waits_told"] = w
        now = {x["step"] for x in w}
        net.journal("waits", spot=s.data.get("spot"), waits=w, new=[x for x in w if x not in (old or ())],
                    gone=[x["step"] for x in old or () if x["step"] not in now])


def ask(s, i):
    """Ask the client step i's condition (S2C 0x5086, a new serial); its answer comes to on_condition."""
    from . import game
    d = _state(s)
    d["serial"] = serial = d.get("serial", 0) + 1
    d.setdefault("asked", {})[serial] = i
    game.send_condition(s, serial, *script(s.data["spot"])[i]["cond"])


def on_condition(s, serial, holds):
    """The client's answer to a condition asked (C2S 0x5089): its step fires when it holds, else it is asked again
    POLL_S later while the step still waits. An answer to nothing asked (or asked again since) is dropped."""
    d = _state(s)
    i = d.get("asked", {}).pop(serial, None)
    if i is None or i in d["fired"] or s.data.get("mission_won"):
        return
    if holds:
        cond = script(s.data["spot"])[i]["cond"]
        fire(s, i, {"cond": cond[0], "args": list(cond[1:])})
        return

    def again():
        if i not in d["fired"] and not s.data.get("mission_won"):
            ask(s, i)
    s.later(POLL_S, again)


def prompt(s, i):
    """Put up a key prompt (S2C 0x50c1) for each of step i's keys; the one pressed comes to on_prompt. Before the
    room's first one, the client's list is emptied (0x50c3 id 0: a prompt an earlier room left up would answer with
    an id of ours) and a keyless prompt goes first (NO_KEY_PROMPT): the client then answers a key, never a timeout."""
    from . import game
    d = _state(s)
    up = d.setdefault("prompts", {})
    if not d.get("no_timeout"):
        game.cancel_prompt(s, 0)
        game.send_prompt(s, NO_KEY_PROMPT, 0)
        d["no_timeout"] = True
    for key in script(s.data["spot"])[i]["keys"]:
        free = [p for p in range(1, NO_KEY_PROMPT) if p not in up]    # ids 1..0x7e (a u8 the client keeps signed),
        pid = next((p for p in free if p > d.get("prompt_id", 0)), free[0])   # in turn: a late answer to one taken
        d["prompt_id"], up[pid] = pid, i                                      # down names no new prompt
        d.setdefault("prompt_keys", {})[pid] = key                            # (the journal's wait list)
        game.send_prompt(s, pid, key)
    log.info("director: mission %s step %d waits for key %s", s.data.get("spot"), i,
             ", ".join("0x%x" % k for k in script(s.data["spot"])[i]["keys"]))


def on_prompt(s, pid):
    """The player pressed a prompted key (C2S 0x50c2, the prompt id): its step fires; the step's other prompts come
    down (S2C 0x50c3). The client has already dropped the one answered."""
    from . import game
    up, keys = _state(s).get("prompts", {}), _state(s).get("prompt_keys", {})
    i = up.pop(pid, None)
    if i is None:
        return
    key = keys.pop(pid, None)
    for other in [p for p, j in up.items() if j == i]:
        del up[other]
        keys.pop(other, None)
        game.cancel_prompt(s, other)
    if s.data.get("mission_won") or i in _state(s)["fired"]:
        return
    where = script(s.data["spot"])[i].get("in")
    if where is not None:                           # pressed away from its place: up again, not taken
        b, pos = bound(s.data["spot"], where), s.data.get("hero_pos")
        if b is None or pos is None or not game.inside_bound(b, pos[0], pos[2]):
            prompt(s, i)
            return
    fire(s, i, {"prompt": pid, "key": key, "name": KEY_NAMES.get(key)})


def on_engage(s, a, d):
    """The client reports troop a engaging troop d (combat.on_engage): the steps of a force either belongs to."""
    troops = s.data.get("zone_troops", {})
    force = lambda u: (troops.get(u) or {}).get("ForceNum")
    for i, st in _pending(s, "engage"):
        by = {troop_uid(s, w) for w in st.get("by", ())}
        if by:                                           # only a fight between one of them and the force counts
            if (a in by and force(d) == st["force"]) or (d in by and force(a) == st["force"]):
                fire(s, i, {"troop": a, "engages": d})
        elif st["force"] in (force(a), force(d)):
            fire(s, i, {"troop": a, "engages": d})


def _one_of(spec, value):
    """Whether value is spec, or one of spec when spec is a tuple (a step's "force" / "prop")."""
    return value in spec if isinstance(spec, tuple) else value == spec


def on_skill(s, caster, target, ability):
    """A troop skill cast (combat.on_troop_cast): the steps of that caster on a troop of their force."""
    t = s.data.get("zone_troops", {}).get(target) or {}
    for i, st in _pending(s, "skill"):
        if troop_uid(s, st["troop"]) == caster and _one_of(st["force"], t.get("ForceNum")):
            fire(s, i, {"caster": caster, "target": target, "ability": ability})


def on_broken(s, prop_id):
    """The hero broke an attackable prop (game's props_hit): its "broken" steps."""
    if not any(st["on"] == "broken" for st in script(s.data.get("spot"))):     # (no director state in rooms
        return                                                                # without such a step)
    for i, st in _pending(s, "broken"):
        if _one_of(st["prop"], prop_id):
            fire(s, i, {"prop": prop_id})


def on_used(s, prop_id):
    """The hero finished a cast on a prop (game's prop_cast_done): its "used" steps."""
    if not any(st["on"] == "used" for st in script(s.data.get("spot"))):       # (no director state in rooms
        return                                                                # without such a step)
    for i, st in _pending(s, "used"):
        if _one_of(st["prop"], prop_id):
            fire(s, i, {"prop": prop_id})


def on_arrive(s, places):
    """The host's troop positions ({uid: (x, y, z)}, game.troop_sync): the "arrive" steps whose force has a standing
    troop inside their bound."""
    if not any(st["on"] == "arrive" for st in script(s.data.get("spot"))):     # every room's reports come here
        return
    troops, down = s.data.get("zone_troops", {}), s.data.get("down", set())
    for i, st in _pending(s, "arrive"):
        b = bound(s.data["spot"], st["bound"])
        if b is None:
            continue
        from . import game
        hit = next((u for u, p in places.items() if u in troops and u not in down
                    and _one_of(st["force"], troops[u].get("ForceNum")) and game.inside_bound(b, p[0], p[2])), None)
        if hit is not None:
            fire(s, i, {"troop": hit, "bound": st["bound"]})


def on_finish(s, uid):
    """The hero's finishing attack fells troop uid (status.execution, before its fall is counted)."""
    for i, st in _pending(s, "finish"):
        if troop_uid(s, st["troop"]) == uid:
            fire(s, i, {"troop": uid})


def on_wake(s, forces):
    for i, st in _pending(s, "wake"):
        if st["force"] in forces:
            fire(s, i, {"forces": sorted(forces, key=str)})


def count(s, force):
    """Send a force's panel count (a "count" action): how many of its troops have fallen, of all."""
    c = _state(s).get("counts", {}).get(force)
    if c is None:
        return
    from . import game
    down = s.data.get("down", set())
    mine = [u for u, z in s.data.get("zone_troops", {}).items() if z.get("ForceNum") == force]
    game.panel_count(s, c[0], c[1], sum(1 for u in mine if u in down), len(mine))


def on_down(s, uid):
    """A zone troop fell (game.mission_troop_down): its own steps, and its force's when none of it stands or waits."""
    troops = s.data.get("zone_troops", {})
    t = troops.get(uid)
    if t is None:
        return
    if t.get("ForceNum") in _state(s).get("counts", {}):
        count(s, t.get("ForceNum"))
    from . import game
    down = s.data.get("down", set())
    f = t.get("ForceNum")
    held = any(w.get("ForceNum") == f for wave in s.data.get("waves", ()) for w in wave)
    mates = [(u, z) for u, z in troops.items() if z.get("ForceNum") == f]
    fighting = [(u, z) for u, z in mates if game.hostile(z)] or mates   # a force's staging members never fall
    wiped = not held and all(u in down for u, _ in fighting)            # (Tower F40000: 3 enemies of 7)
    if wiped and uid in dict(fighting):
        net.journal("down", spot=s.data.get("spot"), force=f)
    for i, st in _pending(s, "down"):
        if st.get("troop") == uid or (wiped and st.get("force") == f):
            fire(s, i, {"troop": uid, "force": f})
    standing = sum(1 for u, _ in fighting if u not in down)
    for i, st in _pending(s, "left"):
        if st["force"] == f and not held and standing == st["count"]:
            fire(s, i, {"force": f, "standing": standing})
    on_hp(s, uid, 0, 1)                             # fallen: below every threshold of its hp steps (Vert killed
                                                    # outright still summons and escapes: the room never waits)


POINT_S = 8                      # ours, as game.POINT_S


def point_ahead(s):
    """Nothing hostile stands and the table still holds forces for its story, or its own win (WIN = "table", Grey Fog's
    finale on the street): point at the first bound it waits on."""
    spot = s.data.get("spot")
    waiting = held(spot) and any(w[0].get("ForceNum") in held(spot) for w in s.data.get("waves", ()))
    if not (waiting or (table_wins(spot) and not s.data.get("mission_won"))):
        return
    for _, st in _pending(s, "bound"):
        b = bound(spot, st["bound"])
        if b is not None and b.get("EventBoundID") is not None:
            from . import game
            game.send_actions(s, [ACT_DIRECTION_TO_AREA, b["EventBoundID"], POINT_S])
            log.info("director: mission %s pointing at bound %s", spot, b.get("EventBoundName"))
            return


REPORT_REACH = 2500              # ours: the most a hero covers between two 0x50b0 reports (1.5 s solo, requests/
                                 # battle.md; ~800 units/s running, more on a Charge): a longer jump is a placement
CROSS_STEP = 100                 # ours: the way between two reports is tested this often


def crossed(b, prev, x, z):
    """Whether the hero went through bound b on the straight way from his last report prev (x, z) to (x, z): a strip
    a few hundred units deep is crossed between two reports 1.5 s apart (the prologue's Area_Tutorial_Close: 400)."""
    from . import game
    dx, dz = x - prev[0], z - prev[1]
    n = int(math.hypot(dx, dz) // CROSS_STEP)
    if math.hypot(dx, dz) > REPORT_REACH:
        return False
    return any(game.inside_bound(b, prev[0] + dx * k / (n + 1), prev[1] + dz * k / (n + 1)) for k in range(1, n + 1))


def on_position(s, x, z, prev=None):
    """The hero (or a troop of his) is at (x, z): the bound steps whose bound holds it, or (prev, the hero's last
    report) that he crossed on the way (crossed); the near steps whose troop can target him there (near)."""
    for i, st in _pending(s, "bound"):
        b = bound(s.data["spot"], st["bound"])
        if b is not None:
            from . import game
            if game.inside_bound(b, x, z) or (prev is not None and crossed(b, prev, x, z)):
                fire(s, i, {"bound": st["bound"], "at": [round(x), round(z)]})
    for i, st in _pending(s, "near"):
        hit = near(s, st["troop"], x, z)
        if hit is not None:
            fire(s, i, {"troop": hit, "at": [round(x), round(z)]})


def near(s, who, x, z):
    """The troop of `who` (TroopID or alias; a tuple: any of them) in the room whose acquisition range holds (x, z): its
    troop row's RANGE_ACQUISITION (what it can target, the range game.WAKE_RANGE stands for when the row has none),
    from where it was last seen (s.data["last_pos"], the host's reports) or stands; None when none does. Felled or
    not: the warning is the place's (the walker fells a force whole at its first contact)."""
    from . import game, zone
    troops, seen = s.data.get("zone_troops", {}), s.data.get("last_pos", {})
    for w in who if isinstance(who, tuple) else (who,):
        uid = troop_uid(s, w)
        t = troops.get(uid)
        if t is None:
            continue
        p = seen.get(uid)
        tx, tz = (p[0], p[2]) if p else (t["PosX"], t["PosZ"])
        reach = str((zone.np_troop(t["TroopTableID"]) or {}).get("RANGE_ACQUISITION", ""))
        if math.hypot(tx - x, tz - z) <= (float(reach) if reach.replace(".", "", 1).isdigit() else game.WAKE_RANGE):
            return uid
    return None


def gauge(s, uid, hp, top):
    """Send a troop's panel bar (a "gauge" action) its hp %, when the whole percent changed."""
    g = _state(s).get("gauges", {}).get(uid)
    if g is None or not top:
        return
    group, text, last = g
    pct = max(0, min(100, int(100 * hp / top)))
    if pct != last:
        from . import game
        game.panel_gauge(s, group, text, pct, 100)
        _state(s)["gauges"][uid] = (group, text, pct)


def start_panel(spot):
    """The table's PANEL, or None."""
    return mission(spot).get("PANEL")


def panel_later(spot):
    """Whether the table sends its start panel with a step ("panel start"), not at the room's start."""
    return any(a[0] == "panel start" for st in script(spot) for a in st.get("do", ()))


def next_warp(spot):
    """The warp the won room goes on through (the table's NEXT), or None."""
    return mission(spot).get("NEXT")


def table_wins(spot):
    """Whether the room is won only by its table's ("win",) (WIN = "table"; _table gives sets, this is a word)."""
    return mission(spot).get("WIN") == "table"


def by(s, st, attacker):
    """Whether a hit of `attacker` counts for step st's "by" (a troop, or "mine": the player's); no "by", any does."""
    if st.get("by") is None:
        return True
    if st["by"] == "mine":
        return attacker is not None and attacker in (s.data.get("plan") or {}).get("hand", ())
    return attacker is not None and troop_uid(s, st["by"]) == attacker


def on_hp(s, uid, hp, top, attacker=None):
    """A troop's hp changed (combat.apply_hits, by troop `attacker`; the hero is uid 0): its hp steps fire as it crosses
    below; a step with "by" at a hit of that troop's, or at the fall (hp 0: director.on_down)."""
    if not top:
        return
    gauge(s, uid, hp, top)
    low = _state(s).setdefault("low", set())
    for i, st in _pending(s, "hp"):
        if "force" in st:                           # any troop of the force (the first of Tower's wyrms hit)
            if (s.data.get("zone_troops", {}).get(uid) or {}).get("ForceNum") != st["force"]:
                continue
        elif uid not in ({troop_uid(s, w) for w in st["troop"]} if isinstance(st["troop"], tuple)
                         else {troop_uid(s, st["troop"])}):
            continue
        if hp > 0 and not by(s, st, attacker):      # another's hit: not yet (the step stays unarmed for its own)
            continue
        if hp * 100 >= st["below"] * top:
            low.discard(i)
        elif i not in low:
            low.add(i)
            fire(s, i, {"troop": uid, "hp": hp, "of": top})


def window_closed(s):
    """The victory window closed (game.mission_won schedules this RESULT_CLOSE_S after 0x5044): the table's "closed"
    steps, once each (the room is won, so _pending's gate is not used). The ending's lines played before the window,
    so nothing of the queue holds the screen now."""
    d = _state(s)
    d["free_at"], fired = min(d["free_at"], time.monotonic()), d["fired"]
    for i, st in enumerate(script(s.data.get("spot"))):
        if st["on"] == "closed" and i not in fired:
            fire(s, i)


def skip_ending(s):
    """The victory without the "won" steps' lines (world's !win: the owner gets past a stuck room at once)."""
    _state(s)["ending"] = "done"


def before_win(s, state):
    """Called first by game.mission_won: True while the win waits for the "won" steps' lines (the room's victory then
    comes after them), False when it goes ahead now."""
    d = _state(s)
    if d["ending"] == "done":
        return False
    if d["ending"] == "playing":
        return True
    steps = _pending(s, "won")
    if not steps:
        return False
    d["ending"] = "playing"
    for i, _ in steps:
        fire(s, i)

    def finish():
        from . import game
        d["ending"] = "done"
        game.mission_won(s, state)
    s.later(max(0.0, d["free_at"] - time.monotonic()) + ENDING_PAUSE, finish)
    return True

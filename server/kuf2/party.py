"""The party of one: the recruitment notice, the party waiting room and the start from it (CommonSubTeam scene 0x27,
CommonSubPartyBoard 0x39, CommonSubWaitingRoom 0x56). planning/todo/CONTRACT-COMPLETE-PLAN.md family 5; the dig and
every verdict: planning/agents/reports/2026-11-05_contract-party.md.

The gate (read 2026-11-05). The waiting room's open, 0x14065b760(room, spot), reads CommonSubTeam +0x51 ("in a party"):
  out of a party (0x14065b8a7..0x14065b8ce): spot row +0x14 in {4, 6, 8} -> text 0xd0c5, nothing sent. Row +0x14 is
      Spot_Sub_Type (the loader 0x141865a7b stores that column there; names at 0x1434a9f10: 4 RIFT, 6 Raid_16,
      8 PVE_AGGRESSiON; 7 PVP_AI is the PvP-vs-AI test), not Spot_Contents_Type (row +0x18). So the 16 rifts, the raids
      20950-20952 and the invasions 20908 / 20910 / 20911 need a party; the extremes 20349 / 20501 / 20503 (sub type
      "-") open the client's own solo room and arrive as 0x3f48. Any other spot: the solo room (0x3f48).
  in a party: Limit_Party (row +0x19c) < 2 -> text 0x1c96; else C2S 0x405b and the room is the server's.
+0x51 is set by two messages only: 0x544c (a member list) and 0x5441 (0x140e35e10: i16; 0 -> +0x51 = 1, leader = me,
the member vector = one member built from the client's own name / id / level / class; 0x3403 -> "You already have a
party!!", other -> "Failed to create a party!!"). This build has no request for 0x5441 (no builder writes 0x5440), so
the server alone decides when a lone player gets it: here, when he registers a recruitment notice (0x5461), the one
request of a lone player that names the mission he wants a party for. In the original a lone registrant stayed out of
a party until somebody joined (the client keeps both states: board button state 4, 0x140739430); offline nobody can,
and a notice without a party locks every waiting room (0x1d8d). Owner's decision 1 of the report.

State: s.data["team"] of the world session, not the save (the client holds no party at login and tells the server
on its way out: 0x5449 / 0x5463 from its exit paths 0x1408320b0, 0x140e1f680).
{"char": id, "party": bool, "notice": dict | None, "room": dict | None, "loot": (grade, rule), "next": id}.

Requests (plain fields unless noted; "coded u32" = obf.u32 / obf.dec_u32):
  C2S 0x5461 register / change my notice (0x140734c00, from the board's dialog 0x1407343b0 and, in a party, the world
      map 0x140d48d00): cstr title, 16 bytes B (+0 u8 category = the spot's State, +2 coded bool "new", +3 u8 password
      flag, +4 u8 1, +5 coded u32 spot, +10 u32 notice id, +14 u8 members wanted, +15 u8 difficulty), [cstr password].
      The dialog's list builder 0x1406d1c10 starts the spot list with "All" (text 0x41e, spot -1, 0x1406d1cb8) and skips
      every Spot_Sub_Type RIFT (0x1406d1d9b), and "All" takes difficulty 3 (0x1406d2657): under State 90 it offers only
      that, and the Rift NPC's panel 0x14085f150 opens the dialog with the same -1 and 3. So a rift's notice never names
      a map. Yet the party's spot must be one: team +0xa8 feeds the room's open (0x14065b760 opens nothing for -1: no row)
      and 0x5469's rift step compare (0x140e39540) shows the original carried real rift spots there. OURS: the notice
      takes group 1's first map at Normal, the one the client itself checks a rift against (0x14073456c, 0x140735383).
      "All" under another State stays -1 (no room to open; the world map registers the clicked spot before its room,
      0x140d48d00), up to 16 members as the dialog offers.
  S2C 0x5462 (0x140738ea0): i16 (< 2 bytes crashes); 0 -> the board asks its list again; 0x341a "Wrong number of
      person.", 0x341b "Only the Party leader can register.", unknown -> "Error code: %1%".
  S2C 0x5441: above.  S2C 0x5469 the party's setting (0x140e39020): 22 bytes (< 22 crashes: +4 u8 kind (0 = changed
      while a room is open, 1 / 2 = refresh the board), +5 u32 notice id -> team +0x60, +9 coded u32 spot -> +0xa8,
      +0xe i8 category, +0xf u8 members wanted, +0x10 u8 difficulty -> +0xbc, +0x11 u8 password flag, +0x12 u32 ->
      +0xc4), cstr title, cstr (the request's password field; a missing NUL crashes).
  C2S 0x5463 delete my notice (0x140f05e80): u32 id.  S2C 0x5464 (0x1407391d0): i16; 0 -> "The information has been
      deleted."; 0x341d "The list does not exist."
  C2S 0x545d the board's list (0x1407373b0), 13 bytes.  S2C 0x545e (0x140737b60): i16, on 0 an 8-byte head (i32 "entry 0
      is my notice", u16, u16 page), i16 n, n * (19 bytes E + cstr title + cstr): E+0 difficulty, +1 coded u32 spot,
      +5 u32, +10 u32 notice id, +0xe password flag, +0xf u8, +0x10 members wanted, +0x11 members, +0x12 i8 category.
      My notice goes to the board's own panel, not to the list (which holds other players' notices: none).
  C2S 0x5449 leave (0x140efe830), no body.  S2C 0x544a (0x140e36090): i16; 0 -> one member: "The party has been
      disolved." (silent when a notice is up, which the client then keeps: 0x140e35ade), the team reset.
  C2S 0x404e loot rule (0x140efeab0 from the party option window 0x140731bfa, leader only): T2[(grade * 8 + rule)],
      u8 grade.  S2C 0x404f (0x140e381c0): i16, on 0 three bytes (< 3 crashes): rule (T1[b] & 7), grade, 1 = announce.
  C2S 0x405b enter the party's room (0x1406629c0): u32 spot.  S2C 0x4058 room made (0x140663020): i16, u32 spot,
      u8 difficulty, u8 (the rift step cleared, room +0xb20).  S2C 0x405c a member entered (0x140663230): i16, u32
      character id, u8 slot; non-zero -> the error map 0x140d680e0 (0x1c07 "The room doesn't exist.") and the window
      closes.  Copy readers: a short body cannot crash these.
  C2S 0x4059 leave the room: no body.  S2C 0x405a (0x140663420): i16, u32 character id.
  C2S 0x405d ready: u8.  S2C 0x405e (0x140663590): i16, u32 character id, u8 ready.
  C2S 0x405f difficulty: u8.  S2C 0x4060 (0x1406636e0): i16; 0 does nothing: the room takes the new difficulty from
      the setting push 0x5469 kind 0 (0x14065aef0).
  C2S 0x4063 employ an AI PC: u8 slot, u32 AIPC_ID.  S2C 0x4064 (0x140663b40): i16, u8 slot, u32 id; 0x340f -> text
      0x2b0b (room full).  C2S 0x4061 dismiss: u8 slot.  S2C 0x4062 (0x140663d60): i16, u8 slot.
  C2S 0x5472 start (0x140f056c0 from 0x140660240, room +0xac8 == 0), no body.  S2C 0x5473 (0x140663a00): i16 (< 2
      crashes); 0 -> the room stays locked for the entry, non-zero -> the error map's text and the room unlocks. The
      entry itself is 0x3f48's (world.enter_spot: day limits, Min_Limit_Troop, the mission entry, 0x3f41).
  C2S 0x547b give up the mission (0x140f0e1f0, the ESC menu 0x140e35690: in a party, leader, 60 s apart), no body.
      S2C 0x547c (0x140e39860): i16; 0 -> the cooldown; 0x3426 -> text 0xd0cf.  One member: nobody is left to vote,
      the room is left as the ESC menu's MissionExit leaves it (0x4048).
  C2S 0x407b the rift's step (0x140662cd0 from the step list's click 0x14065b200, room mode 0x66): u8 step.
      S2C 0x407c (0x140663fc0): i16 (< 2 bytes crashes), on 0 one more byte (read, unused: the step); non-zero -> the
      room error map 0x140d680e0 with (the step's group's first spot, the step's difficulty) and the widget back on
      the room's own step. The room then follows by a 0x5469 kind 0 (0x140e39020: the same spot and another
      difficulty -> 0x14065aef0; another rift spot of the same State whose step differs -> 0x14065b0b0; both print
      text 0x1d86. A spot change inside one step changes nothing in the room: 0x140e39560).

The AI PCs in the mission room (third builder, 2026-11-05: planning/agents/reports/2026-11-05_contract3-partyroom.md).
The room's employed AI PCs go with the start (s.data["party_aipc"] of the world session) and take_aipc hands them to
the room's game session at its login (s.data["party_ai"]: ai_players, the records pvp.players builds). A room of one
with AI PCs is a 2-5 player start on the player's team:
  S2C 0x3f4e one more start record each (start_records: the player's team, the AI player's id, obool FALSE, 1 + troops).
  S2C 0x3f4f one more struct each (write_players), the preset's ActiveTroopAISet at +0xa9: the client, as host, runs
      that player itself and leaves him out of the solo count (pvp.py's docstring).
  S2C 0x3f50 their heroes and troops after the player's, in record order (write_troops).
At the loading's end their battle records and zone entries (ai_enters), a second later their places and states
(place_ai), and the room's enable-all shows them with the rest. They are allies: game.hostile is False for them, so
they decide no win, and a fall of theirs is a troop's: the kill feed, no exp, loot or Battle Points.
  S2C 0x4065 (0x140663e90) is not sent. It is a joining member's list: only in a party (team +0x51) it clears the room's
      AI map (+0xaf0, 0x14065c160) and refills it from u8 n, n * (u32 AIPC_ID, u8 slot) without refreshing the slots.
      A room of one has no joiner, and 0x4064 / 0x4062 keep it in step (they insert, erase and refresh).
  Ours, in no table: the ids (pvp.AI_PLAYER, AI_TROOP, AI_CHAR with the room slot as the seat); an AI PC's place on a
  map with fewer start groups than the party (ai_place); no comeback after a fall, as the AI players of pvp.py; the
  fee (%AIPCPreset AIPC_Fee) is not taken, since nothing says when it was.
  No shipped spot reaches this: the client lists a preset only at its ActiveSpot (0x141889ec0, the window 0x140592ec0)
  and none of those is a mission of this build, so 0x4063 stays unsent in play. The client's solo room (+0xac8) sends
  its own AI list as 0x3f48's tail, which world.enter_spot does not read.

The rift's steps (table rift; the client's holder *0x1435a6dc0; second builder, 2026-11-05:
planning/agents/reports/2026-11-05_contract2-riftraid.md). %Basic: State 90, Max_Step 6. %Step_Group: two groups of
four maps (1: 10335, 10336, 10338, 10339; 2: 10342, 20354, 20355, 20356). A step is a group at a difficulty:
step = Step_GroupID * 3 + difficulty - 2 (0x1418cf2d0, which finds the group of any of its maps), so group =
(step - 1) / 3 + 1 and difficulty = (step - 1) % 3 (0x140663fc0); the designers' own names say the same
(mission_reward: "(균열 미션)_1단계" .. "_3단계" on 10335 Normal / Hard / Hell). The client names a group by its
first row (0x1418cf3f0 is a lower bound in a multimap the loader 0x1418cf720 fills in table order): the board checks a
rift notice's entry against group 1's first map at Normal (0x14073456c) and its matching request names no spot at all
(-1, 0x140736f59). The step list offers the step the room's leader cleared (room +0xb20, 0x4058's third byte) and the
next one freely; another step only where %Select_Step has a row (step 4: one Dimensional Crystal 351500600, step 6:
one Dimensional Compass 351500700), with the tooltip 0x1580 "When you change the level, the following currency will
be spent when entering the mission."; any other click puts the widget back and sends nothing.
  Built: the step's refusals and cost (step_entry), the room's spot for a step (step_spot), the cost taken at the
  start, the map rolled at the start (rift_map), the cleared step kept on the character (c["rift_step"]) and raised
  at a rift win with the step's reward (on_mission_won; mission_reward_entranceui %Rift: Crack Shard 760000050 x5 /
  10 / 20 for steps 1-3, Crack Crystal 760000090 x5 / 10 / 100 for 4-6, under the items' own day caps).
  Ours, in no table: the cleared step never resets and a step below it stays free (the client offers none below);
  the roll is uniform and made at the start; a room opened on a map keeps it as the room's spot for its group.

Raids (Spot_Type Raid, Spot_Sub_Type Raid_16, contents PVE_RAID: 20950 Scourged Mountains, 20951 Grave of Time; 20952
has no zone file). Table raid (the client's holder *0x1435a6d80): %Raid (Raid_ID, Mission_Difficulty) gives
Default_Number_Resurrection 3 and the ordered checkpoints; %Check_Point gives a restart point (the zone's
PlayerStartPointInfoData of that StartPointID, SPTypes 3), the script phase that arms it, Number_Resurrection and a
boss troop. The battle HUD (0x14068e280) takes its revive limit for a Raid_16 spot from Default_Number_Resurrection,
then from the armed checkpoint's row (S2C 0x5139, 0x140d00d00: u32 checkpoint id -> text 0x16062 and that limit).
spottable %Revival PVE_RAID: Cubic, Hero_ / Troop_Revival_BanTime 10 s. The client starts the ban itself when the
hero or a troop of the player's falls (0x14068e990 from the HUD's alive flags, 0x14076c431 / 0x14076c6a5) and refuses
a revive under it with text 0xd03d before sending; S2C 0x513e's second list (u16 troop, i32 ms) restores the bans
when the HUD starts again.
  Built: the rooms (game.is_mission), the limit (raid_row through game.revival), the ban (on_troop_down, ban_left,
  bans: enforced in game.revive_here, listed by 0x513d), the camp revive kept off the restart points of unarmed
  checkpoints (restart_points through game.revive_point), the reward dummies' loot at the win (on_mission_won).
  raid.py: arming a checkpoint (a rule of ours: its boss falls; Active_Trigger_Phase / Sub are phases of the raid's
  script, which is not shipped), 0x5139, the checkpoint's resurrections, the restart from it, and the binding
  (0x5a4a-c, the error map's 0x2407 / 0x2408), whose schedule is off until the owner picks one.
  Not built: the party's choice of a checkpoint (team +0xc4 carries the binding alone).
"""
import functools
import random
import struct
import time

from . import obf, raid, tables
from .net import journal, log
from .packet import OBOOL_FALSE, Reader, Writer

S2C_CREATED = 0x5441
C2S_LEAVE, S2C_LEAVE = 0x5449, 0x544a
C2S_BOARD, S2C_BOARD = 0x545d, 0x545e
C2S_NOTICE, S2C_NOTICE = 0x5461, 0x5462
C2S_NOTICE_DELETE, S2C_NOTICE_DELETE = 0x5463, 0x5464
S2C_SETTING = 0x5469
C2S_LOOT_RULE, S2C_LOOT_RULE = 0x404e, 0x404f
S2C_ROOM_MADE = 0x4058
C2S_ROOM_LEAVE, S2C_ROOM_LEAVE = 0x4059, 0x405a
C2S_ROOM_ENTER, S2C_ROOM_ENTER = 0x405b, 0x405c
C2S_READY, S2C_READY = 0x405d, 0x405e
C2S_DIFFICULTY, S2C_DIFFICULTY = 0x405f, 0x4060
C2S_AIPC_DISMISS, S2C_AIPC_DISMISS = 0x4061, 0x4062
C2S_AIPC_EMPLOY, S2C_AIPC_EMPLOY = 0x4063, 0x4064
C2S_STEP, S2C_STEP = 0x407b, 0x407c
C2S_START, S2C_START = 0x5472, 0x5473
C2S_GIVE_UP, S2C_GIVE_UP = 0x547b, 0x547c
C2S_MATCH, S2C_MATCH = 0x5474, 0x5475

SILENT = 0x0001                 # a code no handler of this family names: an assert in the client's log, no text
NO_ROOM = 0x1c07                # the room error map 0x140d680e0: "The room doesn't exist."
NOT_THIS_ROOM = 0x0402          # the same map: "You can not enter this room."
ROOM_FULL = 0x340f              # 0x4064: text 0x2b0b
WRONG_NUMBER = 0x341a           # 0x5462: "Wrong number of person." (text 53213)
NO_SUCH_NOTICE = 0x341d         # 0x5464: "The list does not exist." (text 53189); 0x5462 prints it as "Error code: %1%"
VOTE_REFUSED = 0x3426           # 0x547c: text 0xd0cf (the constant sent before this module)
ITEMS_SHORT = 0x043c            # the room error map: text 0x1194e "Not enough items." (0x140d681be; world.BUFF_NO_ITEM)
ROOM_TYPES = ("Battle", "Raid", "Invasion")     # E_SpotType 2, 3, 5: what a waiting room opens for (0x140d4c028)
ANY_SPOT, ANY_DIFFICULTY, ANY_MEMBERS = 0xFFFFFFFF, 3, 16       # the notice dialog's "All" (module docstring)
SETTING_REFRESH, SETTING_CHANGED = 1, 0         # 0x5469 +4
MY_SLOT = 0                     # the leader's slot in his room


def team(s):
    """The session's party record (see the module docstring), a new one when another character plays on it."""
    cid = (s.data.get("char") or {}).get("id")
    t = s.data.get("team")
    if t is None or t["char"] != cid:
        t = s.data["team"] = {"char": cid, "party": False, "notice": None, "room": None, "loot": (0, 0), "next": 1}
    return t


def spot_row(spot):
    return tables.by_id("spottable").get(str(spot))


def limit_party(row):
    v = (row or {}).get("Limit_Party", "")
    return int(v) if v.isdigit() else 0


def has_difficulty(row, difficulty):
    return 0 <= difficulty <= 2 and (row or {}).get(f"Mission_Diffi_{difficulty + 1}", "-") not in ("-", "")


def default_difficulty(row):
    """The spot's first defined difficulty (the client's 0x141864af0), 0 when none is."""
    return next((d for d in range(3) if has_difficulty(row, d)), 0)


def aipc_preset(aipc_id, spot):
    """The aipctrooptable %AIPCPreset row of this AI PC when the data offers it at this spot (ActiveSpot), else None.
    Only the PvP-vs-AI spots 20954-20956 and test spots carry presets (UI-WIRING U22)."""
    return next((r for r in tables.sections("aipctrooptable")["AIPCPreset"]
                 if r["AIPC_ID"] == str(aipc_id) and r["ActiveSpot"] == str(spot)), None)


def ai_players(aipc):
    """{room slot: AIPC_ID} as the mission room's AI players, in slot order: pvp.players' record of each (his preset's
    hero, troops, stats and AI set), the room slot his seat, the player's team his. By AIPC_ID alone: a rift's start
    rolls another map than the room's (rift_map), and the employ checked the preset against the room's."""
    from . import game, pvp, troops
    out = []
    for seat, aipc_id in sorted(aipc.items()):
        preset, rows = pvp._rows("AIPCPreset", "AIPC_ID")[str(aipc_id)], pvp._rows("AIPCTroop", "AIPCTroop_Id")
        c = pvp.ai_char(preset)
        mine = [pvp.ai_troop(seat, k, rows[preset[f"AIPC_Troop_Slot_{k:02d}"]]) for k in pvp.TROOP_SLOTS
                if preset[f"AIPC_Troop_Slot_{k:02d}"] in rows]
        stats = game.hero_stat_values(c)
        out.append({"seat": seat, "side": game.PLAYER_TEAM, "pid": pvp.AI_PLAYER + seat, "ai": aipc_id,
                    "hero": pvp.AI_PLAYER + seat, "name": c["name"], "char": c, "kit": pvp.ai_kit(c), "stats": stats,
                    "hp": max(1, stats.get(0, game.HERO_HP)),
                    "troops": [t for t in mine if troops.troop_row(t["id"]) is not None],
                    "set": max(1, pvp._int(preset.get("ActiveTroopAISet"), 1))})
    return out


def take_aipc(s, state):
    """The game login: the AI PCs the party's start left on the account's world session (once: the next room has its
    own start) become this room's players, s.data["party_ai"]. Nothing is kept for a room without any."""
    world_session = getattr(state, "world_sessions", {}).get(s.data["account"]["id"])
    aipc = world_session.data.pop("party_aipc", None) if world_session is not None else None
    s.data.pop("party_ai", None)
    if aipc:
        s.data["party_ai"] = ai_players(aipc)


def start_records(ai):
    """The AI players' 0x3f4e records (pvp.py's docstring: the obool is FALSE for a player with a struct)."""
    from . import game
    return b"".join(struct.pack("<HH", game.PLAYER_TEAM, p["pid"]) + bytes([OBOOL_FALSE])
                    + struct.pack("<H", 1 + len(p["troops"])) for p in ai)


def write_players(w, ai, spot):
    """The AI players' 0x3f4f structs, each with its AI set at +0xa9 (pvp.send_start)."""
    from . import game
    for p in ai:
        block = bytearray(game.player_struct(p["char"], spot, p["troops"]))
        struct.pack_into("<I", block, 0xa9, p["set"])
        w.raw(bytes(block)).cstr(p["name"]).cstr("")


def write_troops(w, ai):
    """The AI players' 0x3f50 entries: each hero, then his troops (pvp.send_start)."""
    from . import game
    for p in ai:
        c = p["char"]
        game.write_troop(w, slot=0, uid=1, troop_id=game.HERO_TROOP_ID, leader_id=c["class"], leader_level=c["level"],
                         hp=p["hp"], abilities=sorted(p["kit"].items()), troop_uid=p["hero"])
        for t in p["troops"]:
            game.write_troop(w, slot=t["slot"], uid=t["units"], troop_id=t["id"], leader_id=None, leader_level=0,
                             hp=t["unit_hp"] * t["units"], units=t["units"], abilities=sorted(t["skills"].items()),
                             passives=sorted(t["passives"].items()), barracks_uid=(c["id"] << 8) | t["slot"],
                             troop_uid=t["uid"])


def ai_place(s, seat, place=0):
    """(x, y, z) of an AI PC's hero (place 0) or troop (its preset slot): the player's team's start groups are the
    party's seats (43 of the 75 party maps hold four groups of nine places, for Limit_Party 4; the player stands on
    the first, game.mission_start) [I], a group's places as game.deck_offset reads them. Without a group for the seat
    (25 maps hold one), beside the player's: 300 apart, a row per seat (ours)."""
    from . import game, zone
    spot = s.data["spot"]
    pts = zone.for_spot(spot)["PlayerStartPointInfoData"] if zone.available(spot) else ()
    groups = [g for g in pts if g.get("LongTeamID") == game.PLAYER_TEAM]
    places = groups[seat]["StartPointInfoData"] if seat < len(groups) else ()
    if place < len(places):
        return round(places[place]["PosX"]), 0, round(places[place]["PosZ"])
    x, y, z = game.start_pos(s)
    return x + 300 * place, y, z + 300 * seat


def ai_enters(s, battle):
    """The AI PCs join the battle at the room start, as pvp.start_room's AI players: a hero as a troop of no units led
    by himself, each troop its units, every one a zone entry of the player's team (pvp.zone_entry: the shared paths
    read it, status.side, the kill feed; TroopTableID 0: no exp, loot or quest count is the table's for it)."""
    from . import combat, game, hero, pvp
    ai = s.data.get("party_ai")
    if not ai:
        return
    troops_in = s.data.setdefault("zone_troops", {})
    for p in ai:
        rec = dict(game.hero_combatant(p["char"]), team=p["side"], skills=dict(p["kit"]),
                   hp_rec=hero.regen_tick(p["char"]))
        battle.add_np(p["hero"], 1, 0, c=rec, leader_hp=p["hp"], leader_c=rec)
        troops_in[p["hero"]] = pvp.zone_entry(p, p["hero"], ai_place(s, p["seat"]), game.HERO_TROOP_ID)
        for t in p["troops"]:
            battle.add_np(t["uid"], t["unit_hp"], t["units"],
                          c=combat.combatant_troop(t["row"], p["side"], t["skills"], t["passives"]))
            troops_in[t["uid"]] = pvp.zone_entry(p, t["uid"], ai_place(s, p["seat"], t["slot"]), t["id"])


def ai_states(s):
    """[(position, game.write_troop_state arguments)] of the AI PCs' start troops (pvp.troop_states' own): on the
    player's team, each under its player's id."""
    from . import game
    out = []
    for p in s.data.get("party_ai") or ():
        c = p["char"]
        pools = game.pools_for(c, s.data["spot"], p["troops"])
        out.append((ai_place(s, p["seat"]), dict(
            flags=game.HERO_FLAGS, uid=p["hero"], hp=p["hp"], team=game.PLAYER_TEAM, owner=p["pid"], level=c["level"],
            stats={**p["stats"], **game.pool_stats(pools)})))
        for t in p["troops"]:
            resist = game.hit_resist("trooptype", t["row"].get("TroopType"))
            out.append((ai_place(s, p["seat"], t["slot"]), dict(
                flags=game.HERO_FLAGS, uid=t["uid"], troop_id=t["id"], hp=t["unit_hp"] * t["units"],
                team=game.PLAYER_TEAM, owner=p["pid"], units=t["units"], level=t["level"],
                troop_stats={game.STAT_IDS["HIT_RESIST"]: resist} if resist > 0 else None)))
    return out


def place_ai(s):
    """The AI PCs' start troops into the world, after the player's (game.send_enter_cell, send_mission_troop_info):
    0x50cb and 0x50b8 for each, then their passives' held statuses (pvp.place). Nothing in a room without any."""
    from . import game, status
    states = ai_states(s)
    for pos, kw in states:
        w = Writer(game.S2C_ENTER_CELL_TROOP).u16(1)
        w.obool(False)                                  # no player block: the room start built the troop
        game.write_troop_state(w, pos, **kw)
        s.send(w)
    for pos, kw in states:
        w = Writer(game.S2C_MISSION_TROOP_INFO)
        game.write_troop_state(w, pos, **kw)
        s.send(w)
    for p in s.data.get("party_ai") or ():
        status.troop_passives(s, p["hero"], p["kit"])
        for t in p["troops"]:
            status.troop_passives(s, t["uid"], t["passives"])


@functools.lru_cache(maxsize=None)
def rift_groups():
    """{State: {Step_GroupID: [SpotID, ...]}} of rift %Step_Group, each group's maps in table order, for the States
    rift %Basic lists (the client's loader 0x1418cf720 drops a row of another State)."""
    rift = tables.sections("rift")
    out = {int(r["State"]): {} for r in rift["Basic"]}
    for r in rift["Step_Group"]:
        if int(r["State"]) in out:
            out[int(r["State"])].setdefault(int(r["Step_GroupID"]), []).append(int(r["SpotID"]))
    return out


def rift_state(spot):
    """The State of a map the rift's steps play (Spot_Sub_Type RIFT, 0x141864b60, in a %Step_Group row of its State),
    else None: 8 of the 16 rift spots; the other 8 are in no group (0x1418cf2d0 answers -1 for them)."""
    row = spot_row(spot) or {}
    state_id = row.get("State", "")
    if row.get("Spot_Sub_Type") != "RIFT" or not state_id.isdigit():
        return None
    return int(state_id) if any(spot in maps for maps in rift_groups().get(int(state_id), {}).values()) else None


def step_of(spot, difficulty):
    """The step a rift map plays at a difficulty (0x1418cf2d0: Step_GroupID * 3 + difficulty - 2), else None."""
    state_id = rift_state(spot)
    if state_id is None:
        return None
    return next(g for g, maps in rift_groups()[state_id].items() if spot in maps) * 3 + difficulty - 2


def step_parts(step):
    """(Step_GroupID, difficulty) of a step, as the 0x407c handler splits it (0x140663fc0)."""
    return (step - 1) // 3 + 1, (step - 1) % 3


def max_step(state_id):
    return next((int(r["Max_Step"]) for r in tables.sections("rift")["Basic"] if r["State"] == str(state_id)), 0)


def select_cost(state_id, step):
    """rift %Select_Step's (Cost_Item, Cost_Value) of a step, or None: step 4 one Dimensional Crystal, step 6 one
    Dimensional Compass (the rows carry no currency: SelectCurrencyType "-")."""
    r = next((r for r in tables.sections("rift")["Select_Step"]
              if r["State"] == str(state_id) and r["Step"] == str(step)), None)
    if r is None or not r["Cost_Item"].isdigit() or not r["Cost_Value"].isdigit():
        return None
    return int(r["Cost_Item"]), int(r["Cost_Value"])


def step_reward(state_id, step):
    """mission_reward_entranceui %Rift's (Itemcode, Value) of a step, the reward the step list shows for it, or None
    (the official notes agree on the last: "L6 reward 50 -> 100 crack crystals", 2020-02-18)."""
    r = next((r for r in tables.sections("mission_reward_entranceui")["Rift"]
              if r["State"] == str(state_id) and r["Step"] == str(step) and r["Open"] == "True"), None)
    if r is None or not r["Itemcode"].isdigit() or not r["Value"].isdigit():
        return None
    return int(r["Itemcode"]), int(r["Value"])


def cleared_step(c):
    """The highest rift step the character has won (c["rift_step"], 0 before the first): 0x4058's third byte. That it
    is kept for good is OURS: the original's reset, if it had one, is in no table."""
    return int(c.get("rift_step", 0))


def step_entry(c, state_id, step):
    """(refusal, cost) of entering a rift step: free up to the step after the one the character cleared; a later step
    costs its %Select_Step item, which he must hold (ITEMS_SHORT); a later step without a row is not offered (SILENT).
    The client's list offers the cleared step and the next freely and the %Select_Step steps at their cost
    (0x14065b200); that the steps below the cleared one stay free is OURS (the client never asks for one)."""
    if not 1 <= step <= max_step(state_id):
        return SILENT, None
    if step <= cleared_step(c) + 1:
        return None, None
    cost = select_cost(state_id, step)
    if cost is None:
        return SILENT, None
    held = sum(it.get("count", 0) for it in c.get("bag", ()) if it.get("code") == cost[0])
    return (ITEMS_SHORT if held < cost[1] else None), cost


def step_spot(state_id, step, asked):
    """The spot a rift room shows for a step: the map the room was opened on while the step is of its group, else the
    group's first map, the one the client itself names a group by (0x1418cf3f0). Which map of the group the room
    shows is OURS; the client shows no other map of a step (0x140e39560)."""
    maps = rift_groups()[state_id][step_parts(step)[0]]
    return asked if asked in maps else maps[0]


def rift_map(state_id, step):
    """The map a start of a rift step plays: one of its group's four (rift %Step_Group), rolled when the party
    starts. The official notes: "Crack 1-3 / 4-6: random map from earlier missions" (OFFICIAL-NOTES.md, the
    missions table, [O] SN-U2 / SN-GoT); the client fits it: its matching request for the rift names no spot and its
    room ignores a map change inside a step. The uniform roll and its moment are OURS (no weight is in a table)."""
    return random.choice(rift_groups()[state_id][step_parts(step)[0]])


def raid_row(spot, difficulty=0):
    """The raid %Raid row of a 16-player raid (Spot_Type Raid, Spot_Sub_Type Raid_16) at a difficulty, or None."""
    row = spot_row(spot) or {}
    if row.get("Spot_Type") != "Raid" or row.get("Spot_Sub_Type") != "Raid_16" or not 0 <= difficulty <= 2:
        return None
    name = ("Normal", "Hard", "Hell")[difficulty]
    return next((r for r in tables.sections("raid")["Raid"]
                 if r["Raid_ID"] == str(spot) and r["Mission_Difficulty"] == name), None)


def checkpoints(spot, difficulty=0):
    """A raid's checkpoints in order (raid %Raid Check_Point_ID1..20 -> %Check_Point): [{"id", "text", "point" (the
    zone's StartPointID it restarts at), "phase" (Active_Trigger_Phase, Sub: the script's, not shipped),
    "resurrections", "boss" (an nptrooptable id or None)}]. Read from the data alone; raid.py arms them."""
    raid = raid_row(spot, difficulty)
    if raid is None:
        return []
    rows = {r["Check_Point_ID"]: r for r in tables.sections("raid")["Check_Point"]}
    num = lambda v: int(v) if v.isdigit() else None
    out = []
    for k in range(1, 21):
        r = rows.get(raid.get(f"Check_Point_ID{k}", "-"))
        if r is not None and r["Restart_Spot_ID"] == str(spot):
            out.append({"id": int(r["Check_Point_ID"]), "text": num(r["Check_Point_Text"]),
                        "point": num(r["Restart_Point_ID"]),
                        "phase": (num(r["Active_Trigger_Phase"]), num(r["Active_Trigger_Sub"])),
                        "resurrections": num(r["Number_Resurrection"]), "boss": num(r["Boss_Troop_ID"])})
    return out


@functools.lru_cache(maxsize=None)
def restart_points(spot):
    """The StartPointIDs of a zone that are a raid checkpoint's restart point on any difficulty (raid %Check_Point
    Restart_Spot_ID / Restart_Point_ID: 20950's 100-115, 20951's 100-105): where a party restarts from an armed
    checkpoint, so not a start point the camp revive may use until that one is armed (game.revive_point)."""
    return frozenset(int(r["Restart_Point_ID"]) for r in tables.sections("raid")["Check_Point"]
                     if r["Restart_Spot_ID"] == str(spot) and r["Restart_Point_ID"].isdigit())


def revive_ban(spot, hero):
    """Seconds a fallen hero (Hero_Revival_BanTime) or troop (Troop_Revival_BanTime) cannot be revived in place, from
    spottable %Revival for the spot's Spot_Contents_Type: 10 / 10 for PVE_RAID, none elsewhere (the client's
    0x14068e990 reads the same row, +4 / +8)."""
    ctype = (spot_row(spot) or {}).get("Spot_Contents_Type")
    row = next((r for r in tables.sections("spottable")["Revival"] if r["ID"] == ctype), None)
    v = (row or {}).get("Hero_Revival_BanTime" if hero else "Troop_Revival_BanTime", "")
    return int(v) if v.isdigit() else 0


def on_troop_down(s, uid, now=None):
    """For game.troop_down: the fall of the hero or of a troop of the player's starts its revive ban where the spot
    has one (revive_ban), as the client's HUD starts it from its own table at that moment (0x14068e990). Kept on the
    room's session: s.data["revive_bans"] = {troop uid: time.monotonic() when it ends}."""
    from . import status
    if not status.players(s, uid):                      # the hero (troop 0), a deck troop, a troop handed to him
        return
    seconds = revive_ban(s.data.get("spot"), uid == 0)
    if seconds > 0:
        s.data.setdefault("revive_bans", {})[uid] = (time.monotonic() if now is None else now) + seconds


def ban_left(s, uid, now=None):
    """Seconds of revive ban left on a troop of this room, 0 when none runs."""
    end = s.data.get("revive_bans", {}).get(uid)
    return max(0.0, end - (time.monotonic() if now is None else now)) if end is not None else 0.0


def bans(s, now=None):
    """[(troop uid, milliseconds left)] of the room's running revive bans: S2C 0x513e's second list."""
    out = [(uid, int(ban_left(s, uid, now) * 1000)) for uid in sorted(s.data.get("revive_bans", {}))]
    return [(uid, ms) for uid, ms in out if ms > 0]


def on_mission_won(s, state, c, spot, difficulty):
    """For game.mission_won, once a win, before its record or its leave. A rift step: the character's cleared step
    rises to it (cleared_step) and the step's reward goes to the bag (step_reward; a token's day cap holds:
    world.add_item). A 16-player raid: its reward dummies' loot and gold (game.reward_dummies: 20950's four, 20951's
    two; the original's script killed one as its boss fell). A raid has no reward row, so its room is left at the win
    with no window (game.windowless) and nothing could be picked up: the loot goes into the bag, which is OURS."""
    from . import events, game, items, loot, world
    state_id = rift_state(spot)
    if state_id is not None:
        step = step_of(spot, difficulty)
        c["rift_step"] = max(cleared_step(c), step)
        reward = step_reward(state_id, step)
        if reward:
            world.add_item(s, state, reward[0], reward[1], why=f"rift step {step}")
        state.save()
        log.info("rift step %d won at spot %d: cleared %d, reward %s", step, spot, c["rift_step"], reward)
        journal("party", ev="rift step", char=c.get("id"), spot=spot, step=step, cleared=c["rift_step"])
    elif raid_row(spot, difficulty) is not None:
        for t, tid in game.reward_dummies(spot, difficulty):
            got = [(code, n) for code, n in loot.roll_drops(spot, tid, game.difficulty_leader(t.get("NPLeaderID"),
                                                                                             difficulty))
                   if items.row(code)]
            gold = events.boosted("gold", game.repeat_gold(c, spot, difficulty, game.roll_gold(tid)))
            for code, n in got:
                world.add_item(s, state, code, n, why=f"raid {spot} reward {tid}")
            if gold:
                world.add_gold(s, state, gold, why=f"raid {spot} reward {tid}")
            log.info("raid %d reward dummy %d (%d): %s, gold %d", spot, t["TroopID"], tid, got, gold)
        raid.on_won(s, state, c, spot, difficulty)


def setting_packet(t, kind, spot=None, difficulty=None, c=None):
    """S2C 0x5469: the party's setting as the notice holds it; without a notice (id 0) the room's spot and difficulty.
    +0x12 is the checkpoint c is bound to there (raid.bound_checkpoint), 0 while the binding is off."""
    n = t["notice"] or {}
    spot = n.get("spot", 0xFFFFFFFF) if spot is None else spot
    difficulty = n.get("difficulty", 0) if difficulty is None else difficulty
    mine = n.get("spot") == spot
    row = spot_row(spot) or {}
    b = bytearray(22)
    b[4] = kind
    struct.pack_into("<I", b, 5, n.get("id", 0))
    b[9:13] = obf.u32(spot)
    state = row.get("State", "0")
    b[0xe] = (n["category"] if mine else int(state) if state.isdigit() else 0) & 0xFF
    b[0xf] = (n["max"] if mine else limit_party(row)) & 0xFF
    b[0x10] = difficulty & 0xFF
    b[0x11] = 1 if n.get("password") else 0
    struct.pack_into("<I", b, 0x12, raid.bound_checkpoint(c, spot, difficulty))
    return Writer(S2C_SETTING).raw(bytes(b)).cstr(n.get("title", "")).cstr(n.get("password") or "")


def board_packet(t, c):
    """S2C 0x545e: my notice (the board's own panel) and no other party's."""
    n = t["notice"]
    w = Writer(S2C_BOARD).u16(0).raw(struct.pack("<iHH", 1 if n else 0, 0, 0)).raw(struct.pack("<h", 1 if n else 0))
    if n:
        e = bytearray(0x13)
        e[0] = n["difficulty"] & 0xFF
        e[1:5] = obf.u32(n["spot"])
        struct.pack_into("<I", e, 10, n["id"])
        e[0xe] = 1 if n.get("password") else 0
        e[0x10] = n["max"] & 0xFF
        e[0x11] = 1                             # members: the leader
        e[0x12] = n["category"] & 0xFF
        w.raw(bytes(e)).cstr(n["title"]).cstr(c.get("name", ""))
    return w


def make(role, state):
    from . import game, rules, world

    def frame(proto, body=b""):
        return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)

    @role.on(C2S_BOARD)
    def board(s, pkt):
        s.send(board_packet(team(s), s.data.get("char") or {}))

    @role.on(C2S_NOTICE)
    def notice(s, pkt):
        t, c = team(s), s.data["char"]
        try:
            title = pkt.cstr()
            b = pkt.take(16)
            password = pkt.cstr() if b[3] == 1 else ""
        except ValueError:                      # a body cut short: nothing to register
            s.send(Writer(S2C_NOTICE).u16(SILENT))
            return
        spot, wanted, difficulty = obf.dec_u32(b[5:9]), b[14], b[15]
        if spot == ANY_SPOT and b[0] in rift_groups():  # a rift's notice names no map (module docstring)
            groups = rift_groups()[b[0]]
            spot, difficulty = groups[min(groups)][0], 0
        anywhere = spot == ANY_SPOT and difficulty <= ANY_DIFFICULTY
        row = spot_row(spot)
        if not anywhere and (row is None or row.get("Spot_Type") not in ROOM_TYPES
                             or not has_difficulty(row, difficulty)):
            log.warning("party notice refused: spot %d difficulty %d is no mission", spot, difficulty)
            s.send(Writer(S2C_NOTICE).u16(NO_SUCH_NOTICE))
            return
        if not 1 <= wanted <= (ANY_MEMBERS if anywhere else max(limit_party(row), 1)):
            s.send(Writer(S2C_NOTICE).u16(WRONG_NUMBER))
            return
        bound = raid.refusal(c, spot, difficulty)
        if bound:
            s.send(Writer(S2C_NOTICE).u16(bound))
            return
        old = t["notice"]
        if old is None:
            t["next"] += 1
        t["notice"] = {"id": old["id"] if old else t["next"] - 1, "title": title, "spot": spot, "category": b[0],
                       "max": wanted, "difficulty": difficulty, "password": password or None}
        s.send(Writer(S2C_NOTICE).u16(0))
        if not t["party"]:                      # a lone registrant: the party of one, its leader (module docstring)
            t["party"] = True
            s.send(Writer(S2C_CREATED).u16(0))
            journal("party", ev="created", char=c.get("id"), spot=spot)
        s.send(setting_packet(t, SETTING_REFRESH, c=c))
        log.info("party notice %d: spot %d difficulty %d, %d wanted, title %r", t["notice"]["id"], spot, difficulty,
                 wanted, title)

    @role.on(C2S_NOTICE_DELETE)
    def notice_delete(s, pkt):
        t, b = team(s), pkt.rest()
        if t["notice"] is None or len(b) < 4 or struct.unpack_from("<I", b)[0] != t["notice"]["id"]:
            s.send(Writer(S2C_NOTICE_DELETE).u16(NO_SUCH_NOTICE))
            return
        log.info("party notice %d deleted", t["notice"]["id"])
        t["notice"] = None
        s.send(Writer(S2C_NOTICE_DELETE).u16(0))

    @role.on(C2S_LEAVE)
    def leave(s, pkt):
        t = team(s)
        if not t["party"]:
            s.send(Writer(S2C_LEAVE).u16(SILENT))
            return
        t["party"], t["room"], t["loot"] = False, None, (0, 0)      # the notice stays, as the client keeps it
        s.send(Writer(S2C_LEAVE).u16(0))
        journal("party", ev="left", char=s.data["char"].get("id"))

    @role.on(C2S_LOOT_RULE)
    def loot_rule(s, pkt):
        t, b = team(s), pkt.rest()
        if not t["party"] or len(b) < 2:
            s.send(Writer(S2C_LOOT_RULE).u16(SILENT))
            return
        grade = b[1]
        rule = (obf.T1[b[0]] - 8 * grade) & 7
        t["loot"] = (grade, rule)
        s.send(Writer(S2C_LOOT_RULE).u16(0).u8(obf.via_t1(rule)).u8(grade).u8(0))

    @role.on(C2S_ROOM_ENTER)
    def room_enter(s, pkt):
        t, c, b = team(s), s.data["char"], pkt.rest()
        spot = struct.unpack_from("<I", b)[0] if len(b) >= 4 else 0
        row = spot_row(spot)
        if not t["party"] or row is None or row.get("Spot_Type") not in ROOM_TYPES or limit_party(row) < 2:
            s.send(Writer(S2C_ROOM_ENTER).u16(NO_ROOM))
            return
        n = t["notice"]
        if n is not None and n["spot"] == spot and has_difficulty(row, n["difficulty"]):
            difficulty = n["difficulty"]
        else:                                   # the party's setting follows its room, as the world map's spot menu
            difficulty = default_difficulty(row)                # makes it (0x140d48d00 registers the notice again
            if n is not None:                                   # for the spot before it opens the room): team +0xa8
                state_id = row.get("State", "0")                # / +0xbc are what a later change is compared with
                n.update(spot=spot, category=int(state_id) & 0xFF if state_id.isdigit() else 0,
                         max=limit_party(row), difficulty=difficulty)
            s.send(setting_packet(t, SETTING_REFRESH, spot, difficulty, c))
        t["room"] = {"spot": spot, "difficulty": difficulty, "ready": False, "aipc": {}, "asked": spot}
        cleared = min(cleared_step(c), 0xFF) if rift_state(spot) is not None else 0     # room +0xb20: the step list
        s.send(Writer(S2C_ROOM_MADE).u16(0).u32(spot).u8(difficulty).u8(cleared))       # offers it and the next
        s.send(Writer(S2C_ROOM_ENTER).u16(0).u32(c["id"]).u8(MY_SLOT))
        journal("party", ev="room", char=c.get("id"), spot=spot, difficulty=difficulty)

    @role.on(C2S_ROOM_LEAVE)
    def room_leave(s, pkt):
        t = team(s)
        if not t["party"] or t["room"] is None:
            s.send(Writer(S2C_ROOM_LEAVE).u16(SILENT))
            return
        t["room"] = None
        s.send(Writer(S2C_ROOM_LEAVE).u16(0).u32(s.data["char"]["id"]))

    @role.on(C2S_READY)
    def ready(s, pkt):
        t, b = team(s), pkt.rest()
        if not t["party"] or t["room"] is None or not b:
            s.send(Writer(S2C_READY).u16(NO_ROOM))
            return
        t["room"]["ready"] = bool(b[0])
        s.send(Writer(S2C_READY).u16(0).u32(s.data["char"]["id"]).u8(1 if b[0] else 0))

    @role.on(C2S_DIFFICULTY)
    def difficulty(s, pkt):
        t, b = team(s), pkt.rest()
        room = t["room"]
        if not t["party"] or room is None or not b:
            s.send(Writer(S2C_DIFFICULTY).u16(NO_ROOM))
            return
        if not has_difficulty(spot_row(room["spot"]), b[0]):
            s.send(Writer(S2C_DIFFICULTY).u16(NOT_THIS_ROOM))
            return
        room["difficulty"] = b[0]
        if (t["notice"] or {}).get("spot") == room["spot"]:
            t["notice"]["difficulty"] = b[0]
        s.send(Writer(S2C_DIFFICULTY).u16(0))
        s.send(setting_packet(t, SETTING_CHANGED, room["spot"], b[0], s.data["char"]))

    @role.on(C2S_AIPC_EMPLOY)
    def aipc_employ(s, pkt):
        t, b = team(s), pkt.rest()
        room = t["room"]
        if not t["party"] or room is None or len(b) < 5:
            s.send(Writer(S2C_AIPC_EMPLOY).u16(SILENT))
            return
        slot, aipc = b[0], struct.unpack_from("<I", b, 1)[0]
        if aipc_preset(aipc, room["spot"]) is None or aipc in room["aipc"].values():
            log.warning("AI PC %d refused: the data does not offer it at spot %d", aipc, room["spot"])
            s.send(Writer(S2C_AIPC_EMPLOY).u16(SILENT))
            return
        if slot == MY_SLOT or slot >= limit_party(spot_row(room["spot"])) or slot in room["aipc"]:
            s.send(Writer(S2C_AIPC_EMPLOY).u16(ROOM_FULL))
            return
        room["aipc"][slot] = aipc
        s.send(Writer(S2C_AIPC_EMPLOY).u16(0).u8(slot).u32(aipc))

    @role.on(C2S_AIPC_DISMISS)
    def aipc_dismiss(s, pkt):
        t, b = team(s), pkt.rest()
        room = t["room"]
        if not t["party"] or room is None or not b or b[0] not in room["aipc"]:
            s.send(Writer(S2C_AIPC_DISMISS).u16(SILENT))
            return
        del room["aipc"][b[0]]
        s.send(Writer(S2C_AIPC_DISMISS).u16(0).u8(b[0]))

    @role.on(C2S_STEP)
    def step(s, pkt):
        """The rift room's step list (module docstring): the room takes the step's spot (step_spot) and difficulty
        and the party's setting follows (0x5469 kind 0, as a difficulty change). Refused: no room (0x1c07); a room
        that is no rift step's, a step outside 1..Max_Step or one the list does not offer (SILENT: the widget goes
        back, no text); a %Select_Step item the character does not hold (ITEMS_SHORT). The item is taken at the
        start, as the client's tooltip 0x1580 says."""
        t, c, b = team(s), s.data["char"], pkt.rest()
        room = t["room"]
        if not t["party"] or room is None:
            s.send(Writer(S2C_STEP).u16(NO_ROOM))
            return
        state_id = rift_state(room["spot"])
        refused, cost = step_entry(c, state_id, b[0]) if state_id is not None and b else (SILENT, None)
        if refused:
            log.info("rift step %s refused (%#x) at spot %d", b[:1].hex() or "-", refused, room["spot"])
            s.send(Writer(S2C_STEP).u16(refused))
            return
        spot, difficulty = step_spot(state_id, b[0], room["asked"]), step_parts(b[0])[1]
        room.update(spot=spot, difficulty=difficulty)
        if t["notice"] is not None:             # the notice names the party's destination: it follows the room
            t["notice"].update(spot=spot, difficulty=difficulty)
        s.send(Writer(S2C_STEP).u16(0).u8(b[0]))
        s.send(setting_packet(t, SETTING_CHANGED, spot, difficulty))
        journal("party", ev="step", char=c.get("id"), step=b[0], spot=spot, difficulty=difficulty,
                cost=list(cost) if cost else None)

    @role.on(C2S_START)
    def start(s, pkt):
        t, c = team(s), s.data["char"]
        room = t["room"]
        enter = role.handlers.get(world.C2S_ENTER_SPOT)
        if not t["party"] or room is None:
            s.send(Writer(S2C_START).u16(NO_ROOM))
            return
        spot, level = room["spot"], room["difficulty"]
        state_id, cost, refused = rift_state(spot), None, None
        if state_id is not None:                # a rift step: its own gate, then the map this start plays (rift_map)
            refused, cost = step_entry(c, state_id, step_of(spot, level))
            refused = NOT_THIS_ROOM if refused == SILENT else refused      # a step the list would not offer
            spot = rift_map(state_id, step_of(spot, level))
        refused = (refused or raid.refusal(c, spot, level) or rules.day_refusal(c, spot, level)
                   or game.entry_refusal(c, spot, level)
                   or (None if enter and game.is_mission(spot) else world.NO_GAME))
        if refused:                             # the entry's own refusals (world.enter_spot), told on the room's reply
            log.info("party start at spot %d refused (%#x)", spot, refused)
            s.send(Writer(S2C_START).u16(refused))
            return
        s.send(Writer(S2C_START).u16(0))
        if cost:                                # "spent when entering the mission" (the step list's tooltip 0x1580)
            world.remove_item(s, state, cost[0], cost[1], why=f"rift step {step_of(spot, level)}")
        s.data["party_aipc"] = dict(room["aipc"])       # the room's AI PCs, for the mission room (take_aipc)
        t["room"] = None                        # the client clears its room marks on the 0 (0x140e34f10)
        journal("party", ev="start", char=c.get("id"), spot=spot, difficulty=level)
        enter(s, frame(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes([level])))

    @role.on(C2S_MATCH)
    def match(s, pkt):
        """0x5474 start matching (12 bytes, 0x140f05a60): u8 State, u8, coded u32 spot, u8 1, u32, u8 difficulty.
        Sarah's "[Crack] Mysterious Corridor Enter" (NPC menu ENTRANCE_RIFT 0x140ea0f2f -> OnStartMatching
        0x140735290) names the rift by its State alone: live 2026-11-06 `5a02 97169716 01 00000000 00`, State 90, spot
        -1 (the group lookup 0x1418cf3f0 answered -1; the board's matching names -1 too, 0x140736f59), difficulty 0.
        Such a request means the rift's group 1 first map (what that lookup is for): step 1 at difficulty 0. 0x5475
        `0100` as before (0x140739460: no text, no "finding members" left on the client). OURS (owner, 2026-11-06,
        ROADMAP Q74 "Open the rift for one"): the original matched players first and nobody is here, so a free rift
        step asked for alone starts at once, as the room's start would (its map rolled, then world.enter_spot, which
        tells its own refusals on 0x3f41 as at an NPC entrance). Anything but a rift: the 0x5475 alone."""
        b = pkt.rest()
        s.send(Writer(S2C_MATCH).u16(SILENT))
        enter = role.handlers.get(world.C2S_ENTER_SPOT)
        if len(b) < 12 or enter is None:
            return
        spot, level = obf.dec_u32(b[2:6]), b[11]
        state_id = rift_state(spot)
        if state_id is None and b[0] in rift_groups():                  # named by its State: group 1's first map
            state_id = b[0]
            groups = rift_groups()[state_id]
            spot = groups[min(groups)][0]
        if state_id is None:
            return
        c, step = s.data["char"], step_of(spot, level)
        refused, cost = step_entry(c, state_id, step)
        if refused or cost:                     # a step past the free ones: the room's step list is the way there
            log.info("rift for one at spot %d, step %d: not a free step", spot, step)
            return
        spot = rift_map(state_id, step)
        journal("party", ev="rift for one", char=c.get("id"), spot=spot, step=step)
        enter(s, frame(world.C2S_ENTER_SPOT, obf.u32(spot) + bytes([level])))

    @role.on(C2S_GIVE_UP)
    def give_up(s, pkt):
        t = team(s)
        escape = role.handlers.get(world.C2S_MISSION_ESCAPE)
        spot = s.data.get("battle_spot")
        if not t["party"] or escape is None or not spot or not game.is_mission(spot):
            s.send(Writer(S2C_GIVE_UP).u16(VOTE_REFUSED))
            return
        s.send(Writer(S2C_GIVE_UP).u16(0))
        journal("party", ev="give up", char=s.data["char"].get("id"), spot=spot)
        escape(s, frame(world.C2S_MISSION_ESCAPE))

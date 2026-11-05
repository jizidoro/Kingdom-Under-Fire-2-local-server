"""World role: the client connects here after login's 0x1007 (server group login, characters)."""
import math, random, socket, struct, time
from copy import deepcopy

from . import (coinshop, craft, cubicshop, daily, diary, hero, items, mail as mailbox, obf, quest, rules, settings,
               serials, skills, status, summon, tables, titles, troops)
from .net import Role, cause, journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_GROUP_LOGIN = 0x103B        # u32 account id, u32 build, u32 service code, u8
S2C_GROUP_LOGIN_RES = 0x1003    # client handler @ 0x140e7cf70: 10-byte result block, then a 33-byte struct
C2S_CHAR_LIST = 0x1009          # u8 (varies per request)
S2C_CHAR_LIST = 0x100A          # client handler @ 0x140e78af0: u8, u8 count, entries (reader @ 0x140e7a350)
C2S_CHAR_CREATE = 0x100B        # cstr name + 56-byte appearance struct (builder @ 0x140e71f90)
S2C_CHAR_CREATE_RES = 0x100C    # client handler @ 0x140e72e40: u16 result, u32 (new character id)
C2S_CHAR_DELETE = 0x100F        # u8 (table-coded flag), u32 character id (builder @ 0x140e78740); reply 0x1010
S2C_CHAR_DELETE = 0x1010        # 0x140e62c80, one 15-byte read (shorter crashes): flag byte (obool, TRUE = delete, FALSE
                                # = a pending deletion cancelled), u32 id, i16 result, i64 seconds (0 = gone now: text 78
                                # and the entry leaves the list; > 0 = the pending-deletion timer)
C2S_NAME_CHECK = 0x100d         # LobbySubCustomize (builder 0x140e72ab0): cstr name, sent only after the client's own
                                # length / forbidden-word checks
S2C_NAME_CHECK = 0x100e         # 0x140e62cc0: i16 (value reader); 0 free (text 278), 0x1404 taken (text 77)
NAME_TAKEN = 0x1404
C2S_START_GAME = 0x1011         # u32 character id, u8 (table-coded flag) (builder @ 0x140ef1a00)
START_REFUSED = 0x1407          # a 0x1012 result that re-enables the select screen (planning/client/session_lobby.md)
C2S_LEAVE_NOTICE, S2C_LEAVE_NOTICE = 0x5644, 0x5645
S2C_START_GAME_RES = 0x1012     # client handler @ 0x140e79030: u16 result, P (37 bytes), Q (32 bytes)
C2S_GUIDE_SEEN = 0x101b         # builder 0x140f07310: u8 plain E_TutorialType (names 0x1434aaa00, 0x8f types), sent when
                                # the guide object (common+0x88, flags at +9+type) marks a hint seen; only 0x57 (first
                                # quest accept, 0x140a9b240) and 0x58 (first bag item, 0x140a9b020) call it. No reply.
GUIDE_BITS_AT = (0x02, 0x0a)    # Q u64 at +0x02: seen bits of types 0..0x3f, u64 at +0x0a: types 0x40..0x7f; the 0x1012
                                # handler (0x140e793e3 -> 0x140a9a6e0) sets flag = bit (1 = seen), 0x80.. always unseen
S2C_PREPARE_ENTER_TOWN = 0x3745 # u16 result, u32 spot, packed x/z (4 bytes), i16 y, nibble byte
C2S_ENTER_TOWN_REQ = 0x3744     # plain u32 spot (builder 0x140efb980): the world map arrived at a City/Field spot
                                # (0x140d489f0 sends it when 0x1406f8d70 finds no battle there); reply 0x3745
C2S_MOVE_SPOT = 0x3742          # encoded u32 spot id (builder @ 0x140efb600); reply 0x3743 is handled in the world-map state
C2S_TOWN_MOVE = 0x1040          # ~3/s while walking; two builders (planning/client/session_lobby.md §2 0x1040): town
                                # 0x140efc540, 10 bytes: packed x/z (4) + i16 y + nibble byte + 3 bytes; world map
                                # 0x140efc110, 13 bytes: the same 7, f32, coded u16 (not a town position)
TOWN_MOVE_SIZE = 10
SAVE_EVERY_S = 5                # persist the walked position at most this often
C2S_NPC_MENU = 0x5a48           # no payload; sent once when an NPC menu of kind 0x31..0x34 opens (builder @ 0x140634eb0)
S2C_NPC_MENU = 0x5a49           # Common case -> scene 0x5f, 0x1406365a0: u8 n, n * 3 bytes; clears the "requested" flag
C2S_ENTER_TOWN = 0x3746         # encoded u32 spot, sent after the town loads (builder @ 0x140ef55c0)
S2C_ENTER_TOWN = 0x3747         # GameStateTown::ProcessPacket_EnterTown @ 0x140e89570: u8 channel, i16 result
TOWN_CHANNEL = 1
C2S_ENTER_SPOT = 0x3f48         # encoded u32 spot (obf.u32), u8 difficulty, [AI PC list] (builder @ 0x140f04310)
S2C_GAME_SERVER = 0x3f41        # global handler @ 0x140cbe770: u16 result, u16 port, u32 ip (host order), u32, u8; a
                                # failure is i16 code, u8 n, n x u32 (reader 0x1405cee80)
NO_GAME = 0x1c0a                # 0x3f41 failure -> text 7313 "There is no game available." (world_travel.md §2 0x3f48)
SCALE_ONE = 20                  # entry byte +0x0e * 0.05 = model scale
# spottable Start_X/Start_Z of every City/Field/Field_PK spot (the town path: 0x3744 -> 0x3745 -> 0x3746 -> 0x3747).
# They are a corner of the spot's rectangle in the map (Start..End_X/Z, the minimap zone), not a spawn point: at
# 10352 the hero landed on a mountain at the map edge.
# TOWN_ENTRY wins where a map's entry point has been measured; the rest land on this table until measured.
TOWN_SPOT_START = {
    10000: (10000, 30000), 10001: (6500, 84000), 10201: (15000, 14500), 10202: (-20000, 20000), 10325: (5000, 5000),
    10332: (10000, 30000), 10350: (138000, 68000), 10351: (54500, 28500), 10352: (138000, 68000),
    10354: (54500, 28500), 10359: (138000, 68000), 10360: (54500, 28500), 10363: (-18304, 26282),
    20100: (31000, 43500), 20200: (8000, 15000), 20506: (31000, 43500), 20507: (30000, 75000), 20600: (95000, 50000),
    20906: (95000, 50000), 20940: (94000, 173500), 20953: (137500, 21000), 30000: (0, 0), 50068: (20000, 7000),
    50069: (5000, 5000), 50070: (0, 4500), 880101: (0, 0), 880353: (0, 0), 880370: (31000, 43500),
    880423: (6500, 84000), 880433: (0, 0), 880434: (0, 0), 880436: (66000, 36500), 880583: (0, 0),
    880900: (6500, 84000), 880901: (31000, 43500), 880902: (-20000, 20000), 880910: (8000, 15000),
    990330: (7400, 16800), 990331: (-29801, 17633), 990348: (0, 0), 990351: (10000, 20000), 990352: (0, 0),
    990363: (0, 0), 990364: (0, 0), 990365: (0, 0), 990366: (0, 0),
}
START_SPOT = 10001              # spottable: 1_City_Accolade_New (City, level 1, open)
START_POS = (16304, 0, 98025)   # the city map's entry point 0 (GameStateTown+0x350, tools/frida/townentry.js); the
                                # spottable Start_X/Start_Z (6500, 84000) is outside the walls. y: the client snaps to ground
# Each map's entry point 0 (tools/frida/townentry.js with the hero in that map). 10352 measured 2026-09-27.
TOWN_ENTRY = {START_SPOT: START_POS, 10352: (329756, 0, 175403)}
# Where a new character starts: Mist Field 10352, Glen's camp, where the prologue (50116) ends and the story begins
# (questtable %SpotEvent 6: 10352 -> NextQuest 1003; 1003 BeginSpot 10352, AcquireLevel 1; Accolade shows on the world
# map from level 9, spottable Spot_Visible_Value_1). A new character is saved there and plays the prologue first, which
# leaves for it (game.leave_mission); with the prologue off he enters the camp directly (NEW-PLAYER-FLOW-PLAN §3);
# START_SPOT stays the fallback for everything else.
NEW_CHAR_SPOT = 10352
# The other start points of a map, by group (warpinfo SPGroupID; point 0 is TOWN_ENTRY), same probe.
START_POINTS = {10352: {1: (329747, 0, 175407), 2: (325660, 0, 184365)}}
S2C_WARP_PROCESS = 0x5641       # GameStateManager::ProcessPacket_WarpProcess 0x140cbf850: u8 type, then by type 7/5/14/6/
                                # 4/14 bytes (0x140cc11e0). Type 0 is an error (u16 code, warp id); type 5 moves the hero:
                                # packed x/z (4), i16 y, u8 kind (2 = town/field), 2 bytes, coded spot (must be the current
                                # one), then runs the pending SpotWarp's EnterScript (a cutscene, 0x140cc09ed)
WARP_KIND_TOWN = 2
WARP_KIND_FIELD = 3             # 0x5641 type 1 / 0x4049 kind of a warp into a field's battle room (probe 2026-09-27)
SCENE_SCRIPT = "RTS.PlayCutScene"   # a warp EnterScript that plays a cutscene: the client's own test before it fades
#                                     for one (0x140b6d3b0, the string at 0x142222fd8; world.plain_group)
C2S_MISSION_ESCAPE = 0x4048     # no payload: NPC menu TO_WORLDMAP (battle state only), chat "MissionExit" outside town,
                                # "Leave the battle now?"; sets GameStateManager+0x129 (the client drops the game link)
ESCAPE_TO_WORLDMAP = 1          # 0x4049 block +6 for kind 0: 2 = town, anything else = the world map (0x140d00590)
ESCAPE_TO_TOWN = 2
C2S_WARP_REQUEST = 0x5640       # inside a room: every non-mission door (boxes 0x1d42 TOWN / 0x1d43 FIELD / 0x1d2c WORLD),
                                # the test-script binding "ReqWarp", the prologue's "End the tutorial?" (warp 205);
                                # 15 bytes: packed x/z +0..3 / +6, i16 y +4, u8 +7, u16 unit +8, coded u32 warp +10, u8
                                # facing +14 (planning/features/WORLD.md); the client waits (common+0x16e0) for the move
C2S_LEAVE_TOWN = 0x1241         # no payload: "Do you want to go to the World map?" (0x140e86850), a WORLD door, the chat
                                # command in town; sets common+0x16e0
S2C_LEAVE_TOWN = 0x1242         # GameStateTown::ProcessPacket_LeaveTown 0x140e89660: i16; 0 -> 7-byte position, plain u32
                                # spot (11 bytes; short crashes); no state change
S2C_TO_WORLDMAP = 0x107b        # common case 0x140d5989e (reader 0x140d72720), 11 bytes: position, coded u32 spot -> Loading
                                # -> WorldMap; the only town-reachable packet that does it (that the original sent it
                                # after 0x1242 is inferred)
C2S_CHANNEL_SELECT = 0x374f     # plain u32 channel (0xffffffff = any): the channel list, and WorldMapSubSpotMenu::EnterField
                                # (0x140d4bef0) for a Field spot, which also sets common+0x16e0
S2C_CHANNEL_SELECT = 0x3750     # 0x140d6d860: cstr channel name, obool stay (TRUE); clears common+0x16e0
C2S_QUEST_ITEM_USE = 0x4067     # QuestManager::UpdateTargetingInfo 0x140d7a700 when the use timer ends, 9 bytes: kind byte
                                # T2[(b1 * 8 + kind) & 0xff] (1 = an NPC), coded u32 item, coded u32 target (the NPC id)
S2C_QUEST_ITEM_USE = 0x4068     # Process_QuestItemUse 0x140d7cf70: i16; 0 -> the use effect; 0x6c0a "Not ready yet."
NOT_READY = 0x6c0a
C2S_REALM_JOIN = 0x5a44         # CommonSubRealmInfo (menus REALM_JOIN_A/B) after the confirm 0x1dd8: one T2-coded byte,
                                # realm = T1[b] & 3 (1 A, 2 B; the upper bits are stack junk)
S2C_REALM_JOIN = 0x5a45         # 0x140635fc0: i16 (under 2 bytes crashes); 0 -> coded realm byte (T1[b] & 0x80000003 ->
                                # common+0xd0), message 0x1ff3 with the realm's name
C2S_RIDE = 0x125e               # plain u16 vehicle id, 0 = dismount (CommonSubVehiclebook)
S2C_ROOM_RIDE = 0x5113          # the hero mounts or dismounts in a room (world.ride)
S2C_FIREWORK = 0x4044           # a firework over a player (pushes_common.md): obf.u32 item code, u32 character id
S2C_RIDE = 0x125f               # 0x140e8a680, 6 bytes: i16 the vehicle id (not a result), i32 player id
C2S_NPC_BUFF = 0x4073           # CommonSubNPC::SelectBuffSkill 0x140ea17c0 (menu BUFF), 9 bytes: u32 NPC id, u8 level,
                                # coded u32 ability; npctable %Skill_NPC: every row is ability 200083 = a heal
S2C_NPC_BUFF = 0x4074           # 0x140e9d0e0: i16; 0x6401 / 0x43c "not enough" (text 0x157e)
BUFF_NO_ITEM = 0x43c
S2C_MISSION_ESCAPE = 0x4049     # GameStateBattleField::Packet_MissionEscape 0x140d00590: i16 result, 29-byte block: u40 gold
                                # +0, packed x/z +7..+10 (nibbles +13), u64 exp +0xe, u8 kind +0x16, coded spot +0x17,
                                # u16 player id +0x1b; the client leaves the battle state
FIELD_REDIRECT_S = 2.0          # a field entered through the town path: the town reply, then the battle-path redirect
ESCAPE_S = 5.0                  # MissionEscape, then 0x3f41 (the probe waited 12 s; the client must be out of battle)
# New-character prologue: spottable 50116 "1-11 Azilia's royal castle (do not change the ID)", map 1_AziliaCastle.
# The client hard-codes 50116 (common+0x1724 "in prologue" flag @ 0x140d61c40, world-map escape point).
# 10203 (1_ValleyofLichen_Tutorial) is a TestMap whose files are not in this build's packages.
TUTORIAL_SPOT = 50116
TUTORIAL_POS = (0, 0, 0)        # spottable Start_X/Start_Z are 0; the mission file has the start point
S2C_ENTER_TUTORIAL = 0x3763     # GameStateLobby 0x3763 -> 0x140e79d70
# Owner's call (2026-09-26): new characters skipped the prologue "until it is playable" (no script then). It is played
# now (2026-10-24, scenes/m50116.py: the tape's beats to the king's end, then Glen's camp; the headless walker plays it
# to its win, tools/playthrough.py): a character created from now on starts there (char_create: tutorial_done False);
# the ones created before keep their place (no tutorial_done key: never sent back, start_game).
PROLOGUE_FOR_NEW_CHARACTERS = True
C2S_PROLOGUE_DONE = 0x10d6      # no payload, no reply: quest 9900287 completed, or the first spot change away from 50116
                                # while the client is in the prologue (0x140d7a4d0, 0x140d61c40)
C2S_TO_LOBBY = 0x1055           # system menu "Returning to the character selection" (0x140e2e680), no payload
S2C_TO_LOBBY = 0x1056           # 0x140e2e840 reads nothing: resets the common state and loads the lobby (Loading target 0)
C2S_OPTIONS = 0x10b0            # the 38 game options (builder 0x140f074b0): u8 n, n * (u8 value, u8 index 0..0x25); no reply
S2C_OPTIONS = 0x10b1            # 0x140d6ecc0: the same list (n > 0 with short data crashes); n = 0 -> the client uploads
                                # all 38 with 0x10b0
S2C_SPOT_SCHEDULE = 0x4078      # inline in the Common dispatcher (0x140d5ce25): u16 n, n * 7 bytes (u8 weekday mask, coded
                                # u32 spot, u8 close hour, u8 open hour); see spot_schedule_packet
C2S_CLEARED, S2C_CLEARED = 0x108e, 0x108f  # the won-spot list at city entry (once a session, 0x140674690); see
                                # cleared_packet
WEEKDAY_BIT = {"Sunday": 0x01, "Monday": 0x40, "Tuesday": 0x20, "Wednesday": 0x10, "Thursday": 0x08, "Friday": 0x04,
               "Saturday": 0x02}  # the client's tm_wday -> mask table at 0x142e3d088 (Sun 1, Mon 0x40 ... Sat 2)
C2S_ESCAPE = 0x10b5             # ReqEscapePlayer 0x140d69510 (the escape command's cast), 12 bytes: packed x/z (+0..3, +6
                                # nibbles), i16 y +4, u32 character id +7, u8 kind +11 (1 world map, 2 town/field, 3 battle);
                                # the client picks the destination itself
S2C_ESCAPE = 0x10b6             # Process_NotifyEscapePlayer 0x140d6f0f0: i16; 0 -> the request's 12 bytes (the hero is
                                # placed there); else u32 seconds (text 0xd065, a cooldown); short replies crash
C2S_BAG_TAB = 0x10cd            # bag window 'OpenBag' (0x140dd6710): u8 tab + 1; the client checked the main bag has room
S2C_BAG_TAB = 0x10ce            # 0x140dd1570, one 3-byte read: u8, i16 result (0x411 = bag full text); the client does not
                                # move the items itself, and clears its pending flag common+0x16e0 either way
C2S_OPEN_GACHA = 0x10a4         # using a GACHA_ITEM (0x140dd8630; also the "open all" repeat 0x140dd96c0): u16 bag slot
S2C_OPEN_GACHA = 0x10a5         # 0x140dd1130: i16; 0 -> u32 item code, u16 count (the gained notice; the bag must follow);
                                # 0x447 bag full; any error stops "open all"
C2S_ATTACK_REFRESH = 0x10b7     # no payload; after skill-learn replies (0x3d86, 0x3d89, 0x10af)
S2C_ATTACK_REFRESH = 0x10b8     # 0x140da28f0, one 18-byte read: obool leader, obool kind (stat 15 + kind: physical,
                                # magical), u32 max, u64 uid, u32 min (tenths, as HERO_ATTACK_AT)
# WorldMapTroopListMgr lists. A solo loading (GameStateManager+0x114) finishes only once both replies have
# arrived: Loading update 0x140e58b30 waits for mgr+0x330 == 2 (set by 0x1341) and +0x334 == 2 (0x1343).
C2S_TROOP_LIST = 0x1340
S2C_TROOP_LIST = 0x1341         # 0x140da1040: u64, u8 n, n * (9 bytes, u8 m, m * 9 bytes)  (reader 0x140da6300)
C2S_BARRACK_TROOP_LIST = 0x1342
C2S_HERO_DETAIL = 0x134a        # no body (0x140d9e280), on entering the city
S2C_HERO_DETAIL = 0x134b        # WorldMapTroopListMgr 0x140da1a20: 0xb5-byte hero block, then u8 n, n * item (0x140da6410,
                                # records as in the bag; they go to the equipment slots). The block fills the hero record
                                # that roster slot 0 (the u64 of 0x1341) points to (mgr+0x30); offsets below.
HERO_BLOCK = 0xb5
HERO_UID_AT = 0x9c              # u64 -> record +0x08 (must be non-zero: 0x124a's exp update needs it)
HERO_EXP_AT = 0xa4              # u64 -> record +0x38, exp within the level (what 0x124a also writes)
HERO_NEED_AT = 0x90             # u64 -> record +0x40, exp the level needs
HERO_LEVEL_AT = 0xb0            # u8  -> record +0x14, the level the HUD shows
HERO_CLASS_AT = 0xac            # u32 -> record +0x10 (0x140da1aad; 0x1081: 0x140da1d72), the hero's HeroTable key =
                                # E_HeroCode (the class, as 0x3f50's leader id). The solo waiting room's own member
                                # reads it (0x14065e1f4 -> member +0x28 -> addMember $class, 0x1409ef027): 0 showed
                                # every hero as Glen (live 2026-09-30, ISABELLA's qwe123)
# Stats (hero.stats names). Bytes 0x04..0x8b are copied to record +0x1c0..0x247, so block = record offset - 0x1bc; the
# record offset of each stat is the Info panel's read for that stat id (0x140984f00) and UpdateDetailInfo's write
# (0x140d9ce40, whose base is record +0x20). i32 unless noted.
HERO_STAT_AT = {
    "DEFENCE_MAGICAL_ICE": 0x04, "CRITICALPROB_RESIST": 0x0c, "MDP": 0x10, "ACCURACY": 0x18,
    "DEFENCE_MAGICAL_FIRE": 0x20, "MAGICAL_PENETRATE": 0x24, "MISS": 0x28, "DEFENCE_MAGICAL_DARK": 0x2c,
    "DEFENCE_PHYSICAL_RANGE": 0x30, "MAX_MOVE_SPEED": 0x38, "HERO_DEFENCE_RATE": 0x40, "RANGE_ATTACK_MIN": 0x44,
    "RANGE_SIGHT": 0x48, "DEFENCE_PHYSICAL_CLOSE": 0x4c, "DEFENCE_MAGICAL_HOLY": 0x50, "CRITICALPROB_PHYSICAL": 0x54,
    "DEFENCE_MAGICAL_NATURE": 0x58, "PHYSICAL_PENETRATE": 0x5c, "RANGE_ATTACK_MAX": 0x64, "IMMUNE_CAPTURE": 0x6c,
    "DEFENCE_MAGICAL_LIGHTNING": 0x74, "SP_RECOVERY": 0x78, "CRITICALPROB_MAGICAL": 0x80, "ATTACK_SPEED": 0x84,
    "CRITICAL_REDUCE": 0x88,
    "SP_CURRENT": 0x00,         # -> record +0x20
    "SP_MAX": 0xb1,             # -> record +0x24
}
HERO_STAT_F32_AT = {"CRITICAL_MAGICAL": 0x08, "CRITICAL_PHYSICAL": 0x34}
HERO_ATTACK_AT = {"ATTACK_PHYSICAL_MIN": 0x7c, "ATTACK_PHYSICAL_MAX": 0x1c,    # in tenths: the panel shows
                  "ATTACK_MAGICAL_MIN": 0x3c, "ATTACK_MAGICAL_MAX": 0x68}      # min / 10 " ~ " max / 10
HERO_STAT_CODED_AT = {"HP_RECOVERY": 0x60,  # record +0x21c, decoded (0x14061b040) when shown
                      "HP_MAX": 0x98,       # decoded into record +0x30 (u64) by the reader
                      "HP_CURRENT": 0x8c}   # decoded into record +0x28: the HP the HUD shows
C2S_IDLE = 0x1258               # u16 (builder 0x140ef4640): the idle timer 0x140db60a0 sends 0x14f + idle level after
                                # the hero stands still (with an emote 0x1042 and 0x1246), 0xffff when active again
S2C_IDLE = 0x1259               # 0x140cc0d60: i32 character id, u8 idle -> common+0x15cc and the player's idle pose; the
                                # client sets its own state only from this reply
IDLE_OFF = 0xFFFF
C2S_SOCIAL = 0x1246             # u32 player id, u16 action (0x140ef5300): the client already played it (0x140cbdb60,
                                # 0x140db52d0); the reply 0x1247 is for the other players in town, and there are none
C2S_CHAT = 0x1042               # u8 channel, cstr text (0x140ef3d70)
S2C_CHAT = 0x1043               # 0x140dded00: u8 channel, 0x17-byte header (only a block-list check reads it), cstr
                                # sender name, cstr text (reader 0x140e631e0) -> shown by 0x140ddc1e0 (channel 0xb as 4)
CHAT_HEADER = 0x17
FORCE_WIN_COMMANDS = ("!win", "/win", ".win")   # the owner's chat command: win the mission room now (force_win)
QUEST_DONE_COMMANDS = ("!questdone", "/questdone", ".questdone")   # fill and hand in (force_quests)
QUEST_COMMANDS = ("!quest", "/quest", ".quest") + QUEST_DONE_COMMANDS  # fill only: ready at the NPC
C2S_EQUIP = 0x164e              # SendPacket_ReqChangeEquipItem 0x140f007a0 (from the drag 0x140e4a270), both directions:
                                # coded u64 bag-side serial (0 = none), coded u64 equip-side serial (0 = none), coded u16
                                # equipment index (E_ItemParts - 1), coded u16 bag slot (obf.dec_u64 / dec_u16)
C2S_LOOK_SHOWN = 0x107f         # u32 plain = the shown mask - 0x200000, bit i = equipment index i (builder 0x1405f6c60)
S2C_EQUIP = 0x164f              # Process_ChangeEquipItem 0x140e50920: i16 result; on 0 the client swaps the two itself
EQUIP_FAIL = 1
S2C_BARRACK_TROOP_LIST = 0x1343 # ProcessPacket_BarrackTroopList 0x140da13f0: u16 n, n * troop (reader 0x140da8ad0)


# Requests the client makes on entering the city whose replies can be empty: request -> (reply, body). The body is
# the smallest one the reply handler (Common state case, address) reads without error.
EMPTY_REPLIES = {
    0x1267: (0x1268, b"\0"),             # 0x1405993b0 (scene 0xf): u8 n, n * (5 bytes, cstr)
    0x1265: (0x1266, b"\0"),             # 0x1405c0cd0 (scene 0x4a): u8 n, n * (0x11 bytes, cstr)
    0x126a: (0x126b, b"\0"),             # 0x1405bd810 (scene 0x49): u8 n, n * (0x15 bytes, cstr, cstr)
    0x1078: (0x1079, b"\0\0"),          # 0x140675340: u16 n, n * 0xb
    0x112e: (0x112f, b"\0\0" + bytes(3)),  # 0x140676ca0: i16 result; 0 -> 3 bytes
    0x10e9: (0x10ea, b"\0\0\0\0"),     # 0x140d3bd40: i16 result; 0 -> reader 0x140d3c090: u16 n, n * 5
    0x1031: (0x1032, b""),               # channel list poll (every 10 s); 0x140e158c0 does not read the packet
    0x5346: (0x5347, bytes(2)),          # CommonSubFriend friend list 0x140deba70: u16 n, entries (0x140df3960)
    0x5344: (0x5345, bytes(2)),          # CommonSubFriend ban list 0x140debed0: u16 n
    0x524d: (0x524e, bytes(1)),          # CommonSubMail list 0x140e05f80 (reader 0x1405bf140): u8 n, ...
    0x5a4e: (0x5a4f, bytes(4)),          # CommonSubMail 0x140e069d0: i16 result, u8; 0 -> 0x140e08200: u8 n, ...
    0x5240: (0x5241, bytes(3)),          # CommonSubMail::ReqRecvList 0x140e01100: u8 page, u16 total; 0 -> no list
    0x534c: (0x534d, bytes(2)),          # 0x140ded390 friends list: i16 n, n * entries (0x140df3b20) - none offline
    0x545d: (0x545e, bytes(12)),         # 0x140737b60 party setting: i16 result 0 (non-zero shows an error text),
                                         # 8-byte party block (0x140739850; party id 0 = no party), i16 members 0
    # Session, account, world map (specs/session_account_worldmap.md, 2026-09-27): single channel, and refusals
    # for what needs other players, the cash shop or Cubic; each body is what the handler reads.
    0x1016: (0x1017, bytes(2)),          # survey answer: i16 0 (under 2 bytes crashes)
    0x1044: (0x1045, bytes.fromhex("e80301010001")),   # 0x140883950 channel list: u16 capacity 1000, u8 n 1,
                                         # (u16 users 1, u8 channel TOWN_CHANNEL)
    0x1049: (0x104a, bytes.fromhex("000001")),         # world-map entry (WorldMap state 0x140d36d40): i16 0, u8 channel
    0x104b: (0x104c, bytes.fromhex("0100")),           # another player's info: silent refusal
    0x104d: (0x104e, bytes.fromhex("1504")),           # channel select: "Wrong channel." (one channel)
    0x1052: (0x1053, bytes.fromhex("0100")),           # whisper: "The user doesn't exist."
    0x1064: (0x1065, bytes.fromhex("0604")),           # report a player: "This player is invalid."
    0x1076: (0x1077, bytes.fromhex("1964")),           # compound items (item_combine is empty in this build)
    0x107c: (0x107d, bytes.fromhex("1204")),           # other player info: "not logged in or does not exist"
    0x108a: (0x108b, bytes(3)),          # cash storage page: u8 mode 0, u16 total 0 (the client asks pages 0..5)
    0x108c: (0x108d, bytes.fromhex("01c4")),           # cash storage take: text 0x1c64
    0x10ca: (0x10cb, bytes(2)),          # world chat: i16 0, the client prints its own text
    0x10cf: (0x10d0, bytes.fromhex("01c4")),           # cash shop purchase: text 0x1c64
    0x10f7: (0x10f8, bytes(0x29)),       # realm-war status on world-map entry: one 41-byte read, zeros = no war
    0x10fc: (0x10fd, bytes.fromhex("0100")),           # realm-war spot action / register: text 7268
    0x10fe: (0x10ff, bytes.fromhex("0100")),
    # PvP, mail, friends, party (specs/pvp_mail_social.md): other players only. Each body is what its handler reads;
    # the room lists 0x3e41 / 0x3e64 pop a request queue, so they answer requests only; joins refuse quietly
    # (a text code leaves the join flag set).
    0x3e40: (0x3e41, bytes(6)),          # PvP room list: empty
    0x3e42: (0x3e43, b""),               # create room: the handler reads nothing, clears its pending flag
    0x3e44: (0x3e45, bytes.fromhex("00009716971600")),   # join room (quiet)
    0x3e53: (0x3e54, bytes.fromhex("2d1c")),   # move slot: "Can't proceed..."
    0x3e5a: (0x3e5b, bytes.fromhex("0100")),   # ready
    0x3e5c: (0x3e5d, bytes(2)),          # leave room
    0x3e5e: (0x3e5f, bytes.fromhex("0204")),   # PvP against AI: "You can not enter this room." (not built)
    0x3e61: (0x3e65, bytes.fromhex("0100")),   # create PvP room: "You have failed to create a room."
    0x3e62: (0x3e45, bytes.fromhex("00009716971600")),   # join PvP room (quiet)
    0x3e63: (0x3e64, bytes(6)),          # PvP room list: empty
    0x5242: (0x5243, bytes.fromhex("0100")),   # read player mail (none exist)
    0x5244: (0x5245, bytes.fromhex("0604")),   # send mail: "This player is invalid."
    0x5246: (0x5247, bytes.fromhex("2a64")),   # player mail delete / take gold / take item: none exist
    0x5248: (0x5249, bytes.fromhex("2a64")),
    0x524a: (0x524b, bytes.fromhex("2a64")),
    0x524f: (0x5250, bytes(3)),          # sent mail: empty
    0x5340: (0x5341, bytes.fromhex("0604")),   # add friend / block: "... not logged in or does not exist."
    0x5349: (0x534a, bytes(2)),          # friend request answer, favourite, memo: nothing to change
    0x534e: (0x534f, b""),
    0x5351: (0x5352, bytes(2)),
    0x5353: (0x5354, bytes(2)),
    0x5442: (0x5443, bytes.fromhex("1204")),   # party invite by name: "This player is invalid."
    0x5445: (0x5446, bytes(2)),
    0x5449: (0x544a, bytes.fromhex("0100")),
    0x5451: (0x5452, bytes(2)),
    0x5453: (0x5454, bytes.fromhex("1204")),   # join a party by name
    0x5455: (0x5456, b""),
    0x5458: (0x5459, bytes.fromhex("010000")),
    0x545a: (0x545b, b""),
    0x545f: (0x5460, bytes.fromhex("1d34")),   # party board detail / delete / join: "The list does not exist."
    0x5461: (0x5462, bytes.fromhex("1b34")),   # register on the board: "Only the Party leader can register."
    0x5463: (0x5464, bytes.fromhex("1d34")),
    0x5465: (0x5466, bytes.fromhex("1d34")),
    0x5472: (0x5473, bytes.fromhex("0204")),   # party mission start (solo start is 0x3f48)
    0x5474: (0x5475, bytes.fromhex("0100")),   # party matching start / cancel
    0x5476: (0x5477, bytes(2)),
    0x547b: (0x547c, bytes.fromhex("2634")),   # give-up vote / answer (< 5 bytes crashes 0x547f)
    0x547e: (0x547f, bytes.fromhex("0000000001")),
    0x5740: (0x5741, bytes.fromhex("0100")),   # PvP matching
    0x5742: (0x5743, bytes(2)),
    0x5748: (0x5749, bytes(1)),          # PvP spot list: empty
    0x5840: (0x5841, bytes.fromhex("2b04")),   # PvP records and rankings: empty / quiet
    0x5846: (0x5847, bytes.fromhex("2b04")),
    0x584c: (0x584d, bytes.fromhex("2b04")),
    **{req: (req + 1, bytes(8)) for req in (0x5842, 0x5848, 0x584e)},
    **{req: (req + 1, bytes.fromhex("1204")) for req in (0x5844, 0x584a, 0x5850)},
    0x15a8: (0x15a9, bytes([1, 1, 1])),  # auction follow-up (only after a list success): 3 x obool false
    0x5a50: (0x5a51, bytes.fromhex("2a64")),   # packages: none exist
    0x5a52: (0x5a53, bytes.fromhex("2a64")),
    # Field, NPC, travel (specs/field_npc_travel.md): guild captures, PvP, cash goods, waiting rooms (party only),
    # rift, war rewards and realm transfer need the live service or other players.
    0x1260: (0x1261, bytes.fromhex("0100")),   # tower capture register
    0x1262: (0x1263, bytes.fromhex("010000")),     # field capture list (the window stays empty)
    0x1440: (0x1441, bytes.fromhex("0100")),   # PvP info at the unlock level
    0x3751: (0x3752, bytes(6)),          # limited sale: none
    0x3757: (0x3758, bytes.fromhex("4264")),   # cash buy
    0x3764: (0x3765, bytes.fromhex("051c")),   # friend invite (never 0)
    0x3f49: (0x3f4a, bytes.fromhex("0a1c")),   # QuickStart: "There is no game available."
    0x4045: (0x4046, bytes.fromhex("542c")),   # summon an NP item (not built; 0 needs 8 bytes and a known item)
    0x404a: (0x404b, bytes.fromhex("0100")),   # /Restart (0 would restart the room)
    0x404e: (0x404f, bytes.fromhex("0100")),   # party loot rule
    0x4059: (0x405a, bytes.fromhex("0100")),   # waiting rooms: party only; solo missions start with 0x3f48
    0x405b: (0x405c, bytes.fromhex("071c")),
    0x405d: (0x405e, bytes.fromhex("071c")),
    0x405f: (0x4060, bytes.fromhex("071c")),
    0x4061: (0x4062, bytes.fromhex("0100")),
    0x4063: (0x4064, bytes.fromhex("0100")),
    0x4076: (0x4077, bytes(1)),          # HUD timed list: empty
    0x407b: (0x407c, bytes.fromhex("071c")),   # rift step
    0x5548: (0x5549, bytes.fromhex("0100")),   # share a quest
    0x5a40: (0x5a41, bytes.fromhex("0100")),   # war reward claim / list (an empty 0x5a43 crashes: 2 bytes)
    0x5a42: (0x5a43, bytes(2)),
    0x5a46: (0x5a47, bytes.fromhex("0100")),   # realm transfer
    # Realm war, exchange, cash store, trade, guild (specs/guild_trade_realm.md): other players or the live service.
    0x1100: (0x1101, bytes.fromhex("0100")), # realm war (War Info map only): spot detail
    0x1102: (0x1103, bytes.fromhex("01000000000000000000")), # spot occupation: no result code, 10 bytes (shorter crashes), 'unoccupied'
    0x1104: (0x1105, bytes.fromhex("0100")),
    0x1108: (0x1109, bytes.fromhex("0100")),
    0x110a: (0x110b, bytes.fromhex("0100")),
    0x1115: (0x1116, bytes.fromhex("0100")),
    0x111a: (0x111b, bytes.fromhex("0100")),
    0x111c: (0x111d, bytes.fromhex("0100")),
    0x111e: (0x111f, bytes.fromhex("00000000")), # war state poll: stops polling (< 4 bytes crashes)
    0x1120: (0x1121, bytes.fromhex("0100")), # by-name player request (clears the pending name)
    0x1124: (0x1125, b""),                   # the handler reads nothing
    0x112a: (0x112b, bytes.fromhex("3764")), # 'You failed to buy a cash item.'
    0x112c: (0x112d, bytes.fromhex("00000000")), # /escape check: go ahead (the cast, then 0x10b5); < 4 bytes crashes
    0x1130: (0x1131, bytes.fromhex("00000000000000000000000000")), # exchange (other players): empty price book (< 12 bytes crashes)
    0x1132: (0x1133, bytes.fromhex("00000000000000000000")), # recent trades: empty
    0x1134: (0x1135, bytes.fromhex("0100")), # place an order (never 0)
    0x1139: (0x113a, bytes.fromhex("00000000")), # my orders / my trades: empty (sent when the exchange opens)
    0x113b: (0x113c, bytes.fromhex("00000000")),
    0x113d: (0x113e, bytes.fromhex("0100")),
    0x1140: (0x1141, bytes.fromhex("0100000000000000000000")), # collect (11 bytes: kind and id, unreachable)
    0x1142: (0x1143, bytes.fromhex("0100")),
    0x1144: (0x1145, bytes.fromhex("2664")), # 'You are low on cash.'
    0x114f: (0x1150, bytes.fromhex("00")),   # status popup notice: none (an empty body crashes)
    0x1155: (0x1156, bytes.fromhex("641c0000")), # cash shop tab: text 0x1c64 (< 4 bytes crashes)
    0x3c40: (0x3c41, bytes.fromhex("0964")), # trade: 'You can not trade with this user.'
    0x3c43: (0x3c44, bytes.fromhex("0964")),
    0x3c45: (0x3c46, bytes.fromhex("0000")), # cancel deal (the window's Close)
    0x3c49: (0x3c4a, bytes.fromhex("0100")),
    0x3c4b: (0x3c4c, bytes.fromhex("0100")),
    0x3c4d: (0x3c4e, bytes.fromhex("0964")), # never 0x6408 (a resend loop)
    0x3c4f: (0x3c50, bytes.fromhex("000000000964")),
    0x3d40: (0x3d41, bytes.fromhex("0554")), # guild: none ('0554'); the ranking, applicant and search windows get quiet empties
    0x3d42: (0x3d43, bytes.fromhex("0554")),
    0x3d44: (0x3d45, bytes.fromhex("0154")), # create: 'You don't have authorization to do this.'
    0x3d46: (0x3d47, bytes.fromhex("0554")),
    0x3d48: (0x3d49, bytes.fromhex("0554")), # invite by name (clears the pending invite)
    0x3d4e: (0x3d4f, bytes.fromhex("0554")),
    0x3d51: (0x3d52, bytes.fromhex("0554")),
    0x3d53: (0x3d54, bytes.fromhex("0554")),
    0x3d57: (0x3d58, bytes.fromhex("1554")), # ranking page / search: never 0 with an empty list (crash)
    0x3d59: (0x3d5a, bytes.fromhex("1554")),
    0x3d5d: (0x3d5e, bytes.fromhex("0554")),
    0x3d5f: (0x3d60, bytes.fromhex("0554")),
    0x3d62: (0x3d63, bytes.fromhex("1554")), # applicants (every guild-window open)
    0x3d64: (0x3d65, bytes.fromhex("00000000")), # guild search: empty
    0x3d66: (0x3d67, bytes.fromhex("015400000000")),
    0x3d69: (0x3d6a, bytes.fromhex("1554")),
    0x3d6b: (0x3d6c, bytes.fromhex("055400000000")),
    0x3d6d: (0x3d6e, bytes.fromhex("055400000000")),
    0x3d6f: (0x3d70, bytes.fromhex("015400000000")),
    0x3d71: (0x3d72, bytes.fromhex("0554")),
    0x3d73: (0x3d74, bytes.fromhex("0000000000000000000000000000000000000000000000000000")), # my guild points: none (every guild-window open)
    0x3d76: (0x3d77, bytes.fromhex("0754")),
    0x3d78: (0x3d79, bytes.fromhex("0554")),
    0x3d7b: (0x3d7c, bytes.fromhex("0554")),
    0x3d7d: (0x3d7e, bytes.fromhex("0554")),
    0x3d82: (0x3d83, bytes.fromhex("1554")),
    0x3d84: (0x3d85, bytes.fromhex("055400000000")),
    0x3d87: (0x3d88, bytes.fromhex("055400000000")),
    0x3d8c: (0x3d8d, bytes.fromhex("0554")),
    0x3d91: (0x3d92, bytes.fromhex("0554")),
    # Items and shops (specs/items_troops_skills.md): the auction needs other players, "Cannot connect to the
    # auction server." (0x041b) closes its window (the coin-shop paid refresh 0x1552 is coinshop.py's);
    # enlisting has no stock (every TroopSaleTable slot is "-"); officer / troop skill books have no data rows.
    **{req: (req + 1, bytes.fromhex("1b04")) for req in (0x1590, 0x1595, 0x1597, 0x1599, 0x159b, 0x159d, 0x15a0,
                                                          0x15a2, 0x15a4, 0x15a6)},
    0x1544: (0x1545, bytes.fromhex("0100")),
    0x174e: (0x174f, bytes.fromhex("112c")),
    0x175c: (0x175d, bytes.fromhex("112c")),
}
# 0x1749 (skills.py) history: an earlier reply stopped after the first u64, so the second block's pointer stayed null and
# 0x140da3448 (mov r12, [rax]) faulted; the 20-byte reply above carries both blocks.
C2S_USE_ITEM = 0x4042           # QuickSlotManager::UseItem (builder 0x140efd8b0), 27 bytes: coded u32 +0, coded u16 +4,
                                # coded u32 item code +6, u16 +10, coded u64 serial +12, coded u16 count +20, coded u16
                                # +22, coded u16 +24, coded bool +26 (live: an HP potion from the quick slot)
S2C_USE_ITEM = 0x4043           # ProcessPacket_ResUseItem 0x1408edd60: i16 result; on 0 coded u32 item code + 4 bytes
                                # (cooldown from the item row, the type's message); other codes show a refusal text
ITEM_USE_REFUSED = 1            # any code the client does not name: its generic refusal text (0x1b9b)
S2C_COOLDOWNS = 0x125a          # QuickSlotManager 0x1408eeb70: u16 n * (coded u32 item, i32 cooldown left; the
                                # client keys it by the row's cooldown group and keeps CoolTime - left, so left <=
                                # CoolTime), then u16 m * (coded u32 item, i16 used today) -> the cargo's day-limit map
                                # (0x140690440); `00 00 00 00` is safe, a count longer than its bytes crashes
ITEM_USE_LEVEL, ITEM_USE_MAXED = 0x2c07, 0x2c18   # 0x4043 codes: level too low (text 0x1b9e), skill at max (0x11978)
C2S_OPEN_CONTAINER = 0x1667     # CommonSubCargo (builder 0x1408a8700), 13 bytes: coded u64 serial, coded u16 count,
                                # u8, coded u16; the count is the dialog's on a stack (SeperateItemOk 0x140dcca0c): that
                                # many open at once (planning/client/items_troops_skills.md 0x1667)
S2C_OPEN_CONTAINER = 0x1668     # ContainerItemOpener::ProcessPacket_ResOpenContainerItem 0x1408a9960: i16 result; on 0
                                # (reader 0x1408aa820) coded u40 gold, u16 n, n * 8 (coded u16 count, coded u32 item,
                                # coded u16); 0x447 = bag full (text 0x1dc7), other codes assert
BAG_FULL = 0x447
C2S_TAKE_CONTAINER = 0x1669     # ContainerItemOpener, after the shown result (builder 0x1408a8fe0): the 0x1667 fields + 2
S2C_TAKE_CONTAINER = 0x166a     # ProcessPacket_ResGainItem 0x1408aa2a0: i16; 0 -> "gained" notices for the shown items;
                                # 0x411 / 0x2c0b / 0x6c26 are texts
C2S_BAG_MOVE = 0x1646           # DragAndDropManager bag -> bag, whole stack (builder 0x140e488b0), 20 bytes: coded u16
                                # source slot, coded u16 target slot, coded u64 source serial, coded u64 target serial
S2C_BAG_MOVE = 0x1647           # Process_MoveItemToCargo 0x140e4fc80: i16; 0 -> a sound and the bag's dirty flag +0x25e58
                                # only (the client moves nothing: the bag follows); 0x42b -> text 0x1c64; other codes
                                # assert (planning/client/items_troops_skills.md 0x1646)
C2S_BAG_SPLIT = 0x1652          # bag -> bag with a count (builder 0x140e4b220), 14 bytes: coded u16 source slot, coded u16
                                # target slot, coded u64 source serial, coded u16 count
S2C_BAG_SPLIT = 0x1653          # 0x140e51990: i16; 0 -> the client marks the bag for a refresh; 0x42b -> text 0x1c64
BAG_MOVE_REFUSED = 0x42b
C2S_STORE_BUY = 0x1540          # shop -> bag (builder 0x140e4e880), 13 bytes: coded u16 target bag slot, u32, u32 shop id
                                # (the NPC's MENU_VALUE = itemsaletable ID), coded u16 count, u8 shop slot
S2C_STORE_BUY = 0x1541          # 0x140e50310, 15 bytes: i16 result, u64 guild points (common[0x24]), coded u40 new gold;
                                # 0x447 = bag full, 0x6401 = not enough gold (the client checks that first)
NOT_ENOUGH_GOLD = 0x6401
C2S_STORE_SELL = 0x1542         # bag -> shop (0x140e4ed10, after the sell check), 12 bytes: coded u16 count, coded u16 bag
                                # slot, coded u64 serial
S2C_STORE_SELL = 0x1543         # Common case 0x140d5ae0a, by the pending sale: CommonSubShop::Process_SellItem 0x140e2d180,
                                # the bag's 0x140dd0240 or the drag's 0x140e50530, each 7 bytes (shorter crashes): coded u40
                                # gold, i16 result; 0 -> "You have sold %s.", the gold, rebuy list dirty; non-zero -> 7090
                                # "You can not sell the item.". One per 0x1542, refused or in a room, or the client's sell
                                # queue goes stale (planning/client/items_troops_skills.md 0x1543)
SELL_REFUSED = 1
C2S_REPAIR = 0x1255             # shop repair (builder 0x140e2c900): u16 n, n * (u8 where: 0 bag / 1 equipment, coded u64
                                # serial, coded u16 bag slot or equipment index); the client computes the cost itself
S2C_REPAIR = 0x1256             # 0x140e2d430: i16 (0 repaired, 0x6401 gold); the client changes no durability: resend
S2C_EQUIP_ONE = 0x1676          # one worn item (GameStateCommon 0x140d6d1e0): coded u16 equipment index + the record; it
                                # refreshes the HUD durability icons
C2S_COMPOSE = 0x1251            # CommonSubCompose (builder 0x14072ff30), 22 bytes: coded u64 stone serial, u8 target
                                # (0 bag, 1 equipment), coded u64 target serial, u8 socket, coded u16 stone bag slot,
                                # coded u16 target bag slot or equipment index
S2C_COMPOSE = 0x1252            # 0x14072e000: i16 only (0 set; the client changes no socket: resend the records)
C2S_DISARM = 0x1253             # take a stone out (builder 0x1407304f0), 13 bytes: u8 socket, coded u16 target slot, u8
                                # payment (0 gold), coded u64 target serial, u8 target (0 bag, 1 equipment)
S2C_DISARM = 0x1254             # 0x14072e200: i16 only (0 taken out; the client neither charges nor returns the stone)
DISARM_CUBIC = 1                # payment 1: Cubic (items.compose_cubic; census H10). The client's one caller sends 0
                                # (xor r8d, r8d at 0x14072dd04), so only gold arrives from this build
COMPOSE_REFUSED = 0x42b         # "Can't proceed. Please try again later." (the client puts the stone back)
COMPOSE_LEVEL = 0x2c0b          # the equipping requirements are not met
COMPOSE_FAILED = 0x6413         # "You have failed to equip the items."
C2S_HERO_EDIT = 0x126c          # CommonSubCustomize heroEdit_ok (builder 0x1405bb4e0), 0x34 bytes: 5 coded u32 part ids,
                                # 5 (U, V) colour lookups, 21 face-morph bytes, u8 two-tone ratio; the client sends it
                                # only with a HERO_EDIT ticket (358300050) in the bag
S2C_HERO_EDIT = 0x126d          # ProcessPacket_ResCustomChange 0x1405bb990: i16; 0 -> the 0x34 block (read, unused: the
                                # client applies its own selection); under 2 bytes crashes; no reply leaves it busy
C2S_REBUY_LIST = 0x1665         # the shop's rebuy tab (0x140e2c3e0), no payload
S2C_REBUY_LIST = 0x1666         # 0x140e2ce40: u8 n, n * item record (slot = the entry's index)
C2S_REBUY = 0x1546              # drag from the rebuy tab (0x140e47d90 -> 0x140e4f210), 4 bytes: coded u16 bag slot, u16 index
S2C_REBUY = 0x1547              # 0x140e50750, always 7 bytes (shorter crashes): coded u40 gold, i16 result (0x6401 gold,
                                # 0x6403 bag full); the client re-asks the rebuy list, the bag must follow
REBUY_KEEP = 10                 # sold stacks kept for buying back (the original's number is not known)
BAG_NO_ROOM = 0x6403
C2S_DESTROY = 0x164a            # drag out of the bag + "destroy?" (0x140e4bba0), 12 bytes: coded u16 slot, coded u16
                                # count, coded u64 serial
S2C_DESTROY = 0x164b            # 0x140e51b10: i16; 0 -> "You have destroyed %s."
C2S_DESTROY_KEPT = 0x164c       # the same from the warehouse (0x140e4c130)
S2C_DESTROY_KEPT = 0x164d
C2S_DESTROY_WORN = 0x1674       # the same from the hero's equipment (0x140e4c650), 10 bytes: coded u64 serial, coded u16 index
S2C_DESTROY_WORN = 0x1675       # Process_HeroEquipItemDiscard 0x140e51d00: i16; 0 -> coded u16 index (missing: crash)
S2C_ITEM_EXPIRED = 0x1075       # Process_ItemPeriodExpireAlram 0x140dcfea0, 3 bytes: coded u16 slot, u8 0 worn (the
                                # equipment index: the client undresses it) / other a bag slot (the message only, the
                                # item stays until the next 0x1656); text 0xcfd7 "It was destroyed due to expiration of
                                # the term." (pushes_common.md 0x1075). Never an index >= 21 or a slot >= 0x500
C2S_SWAP_PAIR = 0x1672          # ring / earring pair drag 7<->8, 9<->10 (0x140e4a7d0), 10 bytes: coded u64 serial, coded
                                # u16 source index
S2C_SWAP_PAIR = 0x1673          # 0x140e50f60: i16; 0 -> the client swaps the two
C2S_BAG_ARRANGE = 0x1661        # the bag's arrange button (0x140dd80b0): u8 tab (0 main bag); sent while cargo+0x25e28 = 9
S2C_BAG_ARRANGE = 0x1662        # 0x140dd04a0: i16; 0 -> the tab's range is cleared, u16 n, n * item record (n must match)
C2S_OPEN_CHOICE = 0x166b        # a CHOICE_CONTAINER (builder shared with 0x1667): the 0x1667 fields
S2C_OPEN_CHOICE = 0x166c        # 0x1408a9e00: i16; 0 -> coded u40 gold, u16 n (< 256), n * (coded u16 count, coded u32
                                # item, coded u16 0)
C2S_TAKE_CHOICE = 0x166d        # the pick (0x1408a9480), 13 bytes: u8 source, coded u64 serial, coded u16 index, coded u16 slot
S2C_TAKE_CHOICE = 0x166e        # ProcessPacket_ResGainItem (as 0x166a): i16; 0x411 = bag full text
CHOICE_BAG_FULL = 0x411
C2S_DISMANTLE = 0x154a          # the bag's dismantle mode (CommonSubCargo 0x140dd81a0), 12 bytes: coded u16 slot, coded u16
                                # count, coded u64 serial
S2C_DISMANTLE = 0x154b          # 0x140dd0c10: i16; 0 -> u8 n, n * (coded u16 count, coded u32 item) shown as gained; the
                                # client removes and adds nothing itself; 0x2c1f "Can not disassemble this item."
DISMANTLE_NO = 0x2c1f
C2S_ENCHANT = 0x1670            # CommonSubItemEnchant 'CompleteEnchant' (0x1405fd910), 16 bytes: u8 add-type (0 none, 1/2
                                # Cubic stones), coded u16 slot (bag slot / equipment index), coded u32 material, coded u64
                                # serial, u8 source (0 bag, 1 equipment); the client already checked material and gold
S2C_ENCHANT = 0x1671            # 0x1405fa2a0: i16; 0 -> i16 new level, u8 outcome (0 success, 1..4 FailN; missing: crash);
                                # the bag must already hold the new level (costs are recomputed from it)
ENCHANT_NOT_ALLOWED = 0x40a     # "[%s] can't be enhanced."
ENCHANT_MATERIAL = 0x40e
ENCHANT_CASH = 0x6426           # "You are low on cash." (an add-type the step does not offer, or its Cubic short)
ENCHANT_STAY = 1                # 0x1671 outcome Fail1: the failure that keeps the level (every %Probability row)
C2S_ENCHANT_TRANSFER = 0x1679   # CommonSubItemEnchantTransfer (NPC menu ENCHANT_TRANS, builder 0x1406017a0), 26
                                # bytes plain: u8 target worn, u16 target slot / index, u64 target serial, u16 source
                                # slot, u32 material, u8 source worn, u64 source serial; sent only when the chance, the
                                # material and the Cubic cover it
S2C_ENCHANT_TRANSFER = 0x167a   # Process_ResEnchantTransfer 0x1406001c0: i16; 0 -> obool success; 0x6430 -> text
                                # 0xd01b, 0x402 / 0x40e / 0x40f / 0x445 / 0x642a -> 0x1c64 (both slots cleared)
TRANSFER_REFUSED = 0x402
C2S_UNBIND = 0x10ac             # message 0xd01a answered Yes (0x140dc77eb, builder 0x140dd8760), 6 bytes plain: u16 bag
                                # slot, u32 item code; the client checked BindType, the period and its Cubic
S2C_UNBIND = 0x10ad             # 0x140dd1350: i16; 0 -> text 0xd037, 0x6430 -> 0xd01b, other -> 0xd039; the handler
                                # changes nothing, the bag resend carries the flag
C2S_BAG_EXPAND = 0x10a6         # the bag's message 0xd017 answered Yes (0x140dc7846, after 0x140dd6140 checked open
                                # slots < 0x40 and priced it with 0x14188db50): no payload
S2C_BAG_EXPAND = 0x10a7         # 0x140dd12b0: i16; 0 -> text 0xd035, 0x6430 -> 0xd01b, other -> 0xd01d "Cannot expand
                                # anymore."; the count arrives with the next 0x1656
C2S_WAREHOUSE_EXPAND = 0x10a8   # CommonSubWareHouse message 0xd05b answered Yes (0x140e424b0; town only, open < 0x40)
S2C_WAREHOUSE_EXPAND = 0x10a9   # 0x140e44bf0: i16 as 0x10a7 (0 -> text 0x13bf); the count arrives with the next 0x1641
EXPAND_OPEN_MAX = 0x40          # the bag and warehouse windows sell nothing from 0x40 open slots (the walk's caps
                                # are 128 / 64)
SERVICE_REFUSED = 1             # any other code: the service's own refusal text (0xd01d cannot expand, 0xd039 unbind)
C2S_QUICK_BAR_EXPAND = 0x1762   # CommonSubMainHUD clickAddSlot (0x1407867b0 -> builder 0x140787960), 2 bytes plain: u8
                                # expansions bought + QUICK_BAR_BASE, u8 2; priced item_currency Expand_Quickslot at the
                                # count + 1, the client checked its Cubic
S2C_QUICK_BAR_EXPAND = 0x1763   # 0x140787de0: i16; 0 -> u8 count + QUICK_BAR_BASE (-> bar +0x50), u8; with a request
                                # pending text 0x1e79 and the new slots drawn (C2A_setAddSlot), else +0x50 only (the
                                # bar's init draws from it, C2A_initAddSlot 0x1407869c0); 0x6430 -> text 0xd01b
QUICK_BAR_BASE = 4
CUBIC_SHORT = 0x6430            # every Cubic service's "Not enough Cubics." (text 0xd01b)
C2S_OPTION_REROLL = 0x10d2      # the random-option window's 'ChangeRandomOption' (0x14060c840 -> builder 0x14060ed10),
                                # 12 bytes + locks: coded u16 slot, coded u64 serial (obf.u64), u8 source (0 bag, 1
                                # worn, 2 other), a bool keyed by byte 2 (T2[2 x b[2] + locks present]), then u8 n + n
                                # locked option slots; sent after the client checked the stones (0x14060e3b0) and the
                                # locks' Cubic (0x14060e400 x locks) and kept one option unlocked (text 0x16a9)
S2C_OPTION_REROLL = 0x10d3      # 0x14060f540 (window 0x58 open): i16; 0 -> u8 n + n x (u8 option slot + the record's
                                # 10-byte option); the preview copies the item's options, sized to its option slots,
                                # and overwrites the slots named; non-zero -> "Failure"
C2S_OPTION_APPLY = 0x10d4       # 'ApplyRandomOption' (0x14060f1f0), u8 1
S2C_OPTION_APPLY = 0x10d5       # 0x14060f8a0: i16; 0 -> the preview becomes the item's options
OPTION_REFUSED = 1
S2C_CARGO = 0x1656             # CommonSubCargo::AssignItemInfos 0x140dce7d0: gold (obf.u40), i16 open bag slots
                                # (cargo+0x25d4c; 0 = "inventory is full"), u16 n, n * item (0x140619ae0: 31 + 8 bytes,
                                # u8 m + m * 4, u8 k + k * 10); the client clears its bag first
S2C_CARGO_CHANGE = 0x1657       # Process_InvenItemChange 0x140dcef40: u16 n + full item records; redraws changed slots
S2C_GOLD = 0x1658               # 0x140dcfc40: the new gold total (obf.u40); the client shows the gain (text 7051 / 7052).
                                # Common jump table 0x140d5ecd8: 0x1657 is Process_InvenItemChange 0x140dcef40 (u16 n +
                                # item records), so the gold total sent as 0x1657 until 2026-09-27 was misread there
S2C_EXP = 0x124a                # GameStateCommon::Process_PlayerUpdateExpALvAlarm 0x140d6c3c0: u8 kind, i32 character id,
                                # 18 * 17 bytes: nine troop slots, then nine leader slots; the hero is leader slot 0:
                                # u8 level, u64 exp within the level, u64 exp the level needs (lvexptable %HeroExp)
EXP_SLOT = 17
S2C_HERO_BLOCK = 0x1081         # 0x140da1d10: the 0xb5-byte hero block of 0x134b without the equipment list (a
                                # level-up refresh; under 0xb5 bytes crashes)
S2C_QUICK_BAR_SLOT = 0x1754     # QuickSlotManager 0x1408ed9a0: u8 mode, u16 slot a[, u16 b]: mode 0 empties the item
                                # quick slots on bag slot a, else swaps a <-> b; the client never remaps them itself
S2C_QUICK_BAR_SLOTS = 0x1755    # 0x1408eda40: u8 n, n * (u16 a, u16 b) swaps (a pair whose a is an earlier b is skipped)
CARGO_SLOTS = 32                # open bag slots before any Cubic expansion (c["bag_slots"], bag_slots): the client's own
                                # base (0x14188db50), grown by its Expand_inven rows (owner 2026-09-30: "there is the
                                # mechanism to extend the inventory size")
OLD_BAG_SLOTS = 48              # what opened before (ITEMS-WIRING.md D3 (a)): saves from then keep it (keep_old_bag)
# The warehouse (NPC menu WAREHOUSE, CommonSubWareHouse; the character's c["warehouse"], records as in the bag).
C2S_WAREHOUSE_LIST = 0x1640     # on opening (0x140e41850 -> builder 0x140e45f50): u8 tab, 0 at open; the client asserts
                                # tab <= 1 and keeps a tab's list once it is loaded
S2C_WAREHOUSE_LIST = 0x1641     # Process_WareHouseItemList 0x140e43810: u8 tab, i16 open slots (>= 1), coded u40 warehouse
                                # gold, then the bag's list (0x140dd9860: u16 n, n * item); slots 0..63 (asserted)
WAREHOUSE_SLOTS = 16            # unexpanded, the client's own base (0x14188db50: 16, six 8-slot expansions to 64);
                                # c["warehouse_slots"] after an expansion (warehouse_slots)
C2S_BAG_TO_WAREHOUSE = 0x1642   # drag bag -> warehouse (builder 0x140e48eb0), 22 bytes: coded u64 source serial, coded u16
                                # target slot, coded u64 target serial (0 if empty), coded u16 count, coded u16 source slot
S2C_BAG_TO_WAREHOUSE = 0x1643   # Process_MoveItemCargoToWareHouse 0x140e4fe40: i16; 0 -> the client moves it itself;
                                # 0xc15 -> text 0x1c64; others assert
C2S_WAREHOUSE_TO_BAG = 0x1644   # builder 0x140e495b0: the 0x1642 layout, source in the warehouse, target in the bag
S2C_WAREHOUSE_TO_BAG = 0x1645   # Process_MoveItemWareHouseToCargo 0x140e4ffe0: as 0x1643
C2S_WAREHOUSE_MOVE = 0x1648     # builder 0x140e49c90: the 0x1646 layout inside the warehouse
S2C_WAREHOUSE_MOVE = 0x1649     # Process_MoveItemToWareHouse 0x140e501a0: i16; 0 -> a sound only (the client moves
                                # nothing: the list follows, items_troops_skills.md 0x1648); others assert, text 0x4e50
C2S_WAREHOUSE_SPLIT = 0x1654    # builder 0x140e4b6f0: the 0x1652 layout inside the warehouse
S2C_WAREHOUSE_SPLIT = 0x1655    # 0x140e51a70: i16 -> a notice either way; the list follows
WAREHOUSE_REFUSED = 0xc15
C2S_WAREHOUSE_SORT = 0x1663     # the ItemRange button (CommonSubWareHouse::OnUICallBack 0x140e41c60), no payload; sent
                                # only while +0x1e95 is set (at open, and again by 0x1659)
S2C_WAREHOUSE_SORT = 0x1659     # 0x140e43ec0: u16 n, n * item applied slot by slot; sets +0x1e95
C2S_WAREHOUSE_GOLD = 0x165e     # MoneyIn / MoneyOut (0x140e43030 -> builder 0x140e46350), 6 bytes: coded u40 amount, u8
                                # 0 deposit / 1 withdraw; the client checks both golds and the cap first
S2C_WAREHOUSE_GOLD = 0x165f     # 0x140e44150: i16; 0 -> coded u40 warehouse gold, coded u40 bag gold (texts 0x1bf5 /
                                # 0x1bf6 with the difference); a refusal changes nothing
GOLD_CAP = 999_999_999          # the client's cap on either gold (0x1bd0 / 0x1bdf)
C2S_WARP_LIST = 0x406e          # no payload, on entering the city
S2C_WARP_LIST = 0x406f          # 0x140d6fa90: u16 n, n * encoded u32 warp id (warpinfo.csv) -> discovered set
C2S_WARP_FOUND = 0x406c         # encoded u32 warp id, when the hero first comes near it (0x14089b570)
S2C_WARP_FOUND = 0x406d         # 0x14089d670: i16 result; 0 -> marks it discovered and shows the notice
# Teleport crystals (npctable OBJECT rows with menu WARP_CRYSTAL, e.g. 6200/6201 in Mist Field). Both requests carry
# 11 bytes: coded warp id (4), packed position (x/z bytes 4..7 in obf.pos_xz order, i16 y at 8, nibble byte at 10).
# The same four messages in town and in a field room (each handler has a battle-state branch; the room's tactical
# map asks its confirm through CommonSubWorldMap 0x55: quest.py "Tutorial quests").
C2S_WARP_START = 0x4071         # 0x14089c790: the destination picked on the map; reply lets the cast start
S2C_WARP_START = 0x4072         # 0x14089d920: u32, coded warp id, i16 result (0: cast, then 0x4069)
C2S_WARP_USE = 0x4069           # 0x14089bfc0: sent when the cast ends
S2C_WARP_USE = 0x406a           # 0x14089d0f0: i16 result; 0 -> the request's 11 bytes (the id must be the pending
                                # one), tutorial event 0x59 with the pending id, the hero moves to the destination
WARP_REQ_SIZE = 11
WARP_NO_GOLD = 0x7C0B           # 0x4072 result the client shows as text 0x1d49 with the reply's u32 (the cost; the text
                                # is not in Info.pkg, so "not enough gold" is inferred from its shape)


def crystal_warp(s, state, warp, cost):
    """A 0x5640 with a warpinfo %Portal id (which %Move lacks: 126 of 129). Only the client's test-script binding
    ReqWarp (0x140903240) sends one: the player's map crystal sends 0x4071 in a room too (warp_start; quest.py
    "Tutorial quests", corrected 2026-10-24). Pays its Cost_Gold and re-enters the crystal's field at the start group
    nearest the crystal's point (the zone's start point whose LongWarpID is the portal id; the client's
    FindPlayerStartPoint takes group points only, so the nearest group is ours). False when it is not a crystal of a
    field with a zone or the gold is short (planning/wiring/UI-WIRING.md U27)."""
    from . import game, zone
    row = next((r for r in tables.sections("warpinfo")["Portal"] if r["Portal_ID"] == str(warp)), None)
    c = s.data["char"]
    if row is None or not row["SpotID"].isdigit() or c.get("gold", 0) < cost:
        return False
    spot = int(row["SpotID"])
    if not (game.is_field(spot) and zone.available(spot)):
        return False
    pts = zone.for_spot(spot)["PlayerStartPointInfoData"]
    at = next((p["StartPointInfoData"][0] for p in pts if p.get("LongWarpID") == warp and p["StartPointInfoData"]), None)
    groups = {p["LongGroupID"]: p["StartPointInfoData"][0] for p in pts
              if p.get("SPTypes") == 0 and not p.get("LongWarpID") and p["StartPointInfoData"]}
    if at is None or not groups:
        return False
    group = min(groups, key=lambda g: (groups[g]["PosX"] - at["PosX"]) ** 2 + (groups[g]["PosZ"] - at["PosZ"]) ** 2)
    change_gold(c, -cost)
    state.save()
    journal("warp", how="crystal", warp=warp, spot=spot, group=group, cost=cost)
    send_field_entry(s, spot, group, leave_battle=in_battle_room(s))
    log.info("crystal %d: spot %d group %d (cost %d)", warp, spot, group, cost)
    return True


def warp_cost(warp):
    """Gold to teleport to a portal: warpinfo %Portal Cost_Gold of the destination (0 for the Mist Field crystals)."""
    row = next((r for r in tables.sections("warpinfo")["Portal"] if r["Portal_ID"] == str(warp)), None)
    return int(row["Cost_Gold"]) if row and row["Cost_Gold"].isdigit() else 0
C2S_QUICK_SLOT_PAGE = 0x1746    # u8 page 0..8, sent 9 times on entering the city
S2C_QUICK_SLOT_PAGE = 0x1747    # 0x1408ebf50: u8 page, then 0x1408efa00: page 0 -> u8 n, list, u8 n, list;
                                # other pages -> u64, u8 n, list
C2S_QUICK_SLOT_SET = 0x1740     # SendPacket_ReqCommonSlotRegister 0x140efce30, 11 bytes: coded flag byte, u8 type (0 / 2 page
                                # 0's two lists, 1 the other pages), u8 bar slot, u8 kind (0 item), u32 id (the item code),
                                # u16 bag slot or the skill entry's handle (skills.handle), u8 group (the page)
S2C_QUICK_SLOT_SET = 0x1741     # ResRegisterSlot 0x1408ec2e0: i16; 0 -> the request's [1], [8:10], [2], [0], [3], [10];
                                # the slot exists only once this arrives (1: text 7058 "failed to assign")
C2S_QUICK_SLOT_CLEAR = 0x1742   # 3 bytes: u8 bar slot, u8 type, u8 group
S2C_QUICK_SLOT_CLEAR = 0x1743   # ProcessPacket_ResDeRegisterSlot 0x1408eca30: i16, then the 3 request bytes
C2S_QUICK_SLOT_SWAP = 0x1744    # ReqQuickSlotSwap, 4 bytes: u8 bar slot, u8 mode (the two lists' types), u8 group, u8 bar slot
S2C_QUICK_SLOT_SWAP = 0x1745    # ProcessPacket_ResSlotSwap 0x1408ece40: i16, then the 4 request bytes


def make(state, port, game_host, game_port):
    role = Role("world", port, state)

    role.empty_replies(EMPTY_REPLIES)

    @role.on(rules.C2S_DAY_LIMITS)
    def day_limits(s, pkt):
        s.send(rules.day_limits_packet(s.data.get("char") or {}))

    quest.make(role, state)
    diary.make(role, state)
    craft.make(role, state)
    coinshop.make(role, state)
    cubicshop.make(role, state)                 # the cash shop's Cubic tab: 0x3755 / 0x1128
    summon.make(role, state)                    # the troop summon board: 0x110f / 0x1111, 0x1113
    skills.make(role, state)
    mailbox.make(role, state)
    troops.make(role, state)
    daily.make(role, state)
    titles.make(role, state)

    @role.on(C2S_MOVE_SPOT)
    def move_spot(s, pkt):
        spot = obf.dec_u32(pkt.take(4))
        s.data["target_spot"] = spot
        log.info("move to spot %d (rest %s)", spot, pkt.rest().hex())

    @role.on(C2S_TOWN_MOVE, quiet=True)
    def town_move(s, pkt):
        b = pkt.rest()
        if len(b) != TOWN_MOVE_SIZE:            # the world map's 13-byte form would overwrite the town position
            return
        x, z = obf.dec_pos_xz(b[0:4], b[6])
        y = struct.unpack_from("<h", b, 4)[0]
        c = s.data["char"]
        c["pos"] = [x, y, z]
        if time.monotonic() - s.data.get("saved_at", 0) >= SAVE_EVERY_S:
            s.data["saved_at"] = time.monotonic()
            state.save()

    @role.on(status.C2S_STATUS_INFO)
    def status_info(s, pkt):
        s.send(status.info_packet(s.data.get("char")))

    @role.on(C2S_WARP_LIST)
    def warp_list(s, pkt):
        warps = s.data["char"].get("warps", [])
        w = Writer(S2C_WARP_LIST).u16(len(warps))
        for warp in warps:
            w.raw(obf.u32(warp))
        s.send(w)

    @role.on(C2S_WARP_START)
    def warp_start(s, pkt):
        b = pkt.rest()
        if len(b) < WARP_REQ_SIZE:
            log.warning("warp start too short: %s", b.hex())
            return
        warp = obf.dec_u32(b[:4])
        cost, gold = warp_cost(warp), s.data["char"].get("gold", 0)
        if gold < cost:
            log.info("warp %d: %d gold needed, %d held", warp, cost, gold)
            s.send(Writer(S2C_WARP_START).u32(cost).raw(b[:4]).u16(WARP_NO_GOLD))
            return
        log.info("warp %d: start (cost %d)", warp, cost)
        s.send(Writer(S2C_WARP_START).u32(0).raw(b[:4]).u16(0))

    @role.on(C2S_WARP_USE)
    def warp_use(s, pkt):
        b = pkt.rest()
        if len(b) < WARP_REQ_SIZE:
            log.warning("warp use too short: %s", b.hex())
            return
        x, z = obf.dec_pos_xz(b[4:8], b[10])
        y = struct.unpack_from("<h", b, 8)[0]
        s.data["char"]["pos"] = [x, y, z]
        state.save()
        log.info("warp %d: hero to (%d, %d, %d)", obf.dec_u32(b[:4]), x, y, z)
        s.send(Writer(S2C_WARP_USE).u16(0).raw(b[:WARP_REQ_SIZE]))
        cost = warp_cost(obf.dec_u32(b[:4]))
        journal("warp", how="portal", warp=obf.dec_u32(b[:4]), spot=s.data["char"].get("spot"), pos=[x, y, z],
                cost=cost)
        if cost:
            add_gold(s, state, -cost)          # 0x1658: the client shows the difference

    @role.on(C2S_WARP_FOUND)
    def warp_found(s, pkt):
        warp = obf.dec_u32(pkt.take(4))
        warps = s.data["char"].setdefault("warps", [])
        if warp not in warps:
            warps.append(warp)
            state.save()
        log.info("warp point %d discovered (%d known)", warp, len(warps))
        s.send(Writer(S2C_WARP_FOUND).u16(0))

    @role.on(C2S_QUICK_SLOT_PAGE)
    def quick_slot_page(s, pkt):
        page = pkt.u8()
        c = s.data["char"]
        if page == 0 and c.get("quick_bar_expansions"):
            # the bought quick-bar slots after a relog: only the 0x1763 handler writes the bar's count (+0x50, read by
            # the bar's init), so an unsolicited success carries it (UI-WIRING.md U4; that it is drawn is a live check)
            s.send(quick_bar_packet(c))
        if page == 0 and not s.data.get("cooldowns_sent"):
            s.data["cooldowns_sent"] = True     # item cooldowns and today's uses, once a session (UI-WIRING.md U3)
            s.send(cooldown_packet(c))
        s.send(quick_slot_page_packet(c, page))

    @role.on(C2S_QUICK_BAR_EXPAND)
    def quick_bar_expand(s, pkt):
        b = pkt.rest()
        c = s.data["char"]
        n = c.get("quick_bar_expansions", 0)
        if b and b[0] - QUICK_BAR_BASE != n:
            log.warning("quick-bar expansion: the client counts %d bought, the character %d", b[0] - QUICK_BAR_BASE, n)
        cost = items.currency("Expand_Quickslot", n + 1)
        result = SERVICE_REFUSED if not cost else 0 if spend_cubic(s, state, cost) else CUBIC_SHORT
        if result:
            s.send(Writer(S2C_QUICK_BAR_EXPAND).u16(result))
            return
        c["quick_bar_expansions"] = n + 1
        state.save()
        s.send(quick_bar_packet(c))
        log.info("quick bar: expansion %d for %d Cubic", n + 1, cost)

    @role.on(C2S_QUICK_SLOT_SET)
    def quick_slot_set(s, pkt):
        b = pkt.rest()
        if len(b) < 11:
            log.warning("quick slot register not understood: %s", b.hex())
            return
        kind_type, slot, kind = b[1], b[2], b[3]
        entry = {"kind": kind, "id": struct.unpack_from("<I", b, 4)[0], "bag": struct.unpack_from("<h", b, 8)[0]}
        c = s.data["char"]
        ok = (entry["id"] in skills.hero_skills(c) if kind == 1 else
              any(i["code"] == entry["id"] for i in c.get("bag", [])) if kind == 0 else True)
        if not ok:
            s.send(Writer(S2C_QUICK_SLOT_SET).u16(1))
            return
        c.setdefault("quick_slots", {})[f"{kind_type}:{b[10]}:{slot}"] = entry
        state.save()
        s.send(Writer(S2C_QUICK_SLOT_SET).u16(0).raw(b[1:2] + b[8:10] + b[2:3] + b[0:1] + b[3:4] + b[10:11]))

    @role.on(C2S_QUICK_SLOT_CLEAR)
    def quick_slot_clear(s, pkt):
        b = pkt.rest()[:3]
        if len(b) < 3:
            return
        s.data["char"].setdefault("quick_slots", {}).pop(f"{b[1]}:{b[2]}:{b[0]}", None)
        state.save()
        s.send(Writer(S2C_QUICK_SLOT_CLEAR).u16(0).raw(b))

    @role.on(C2S_QUICK_SLOT_SWAP)
    def quick_slot_swap(s, pkt):
        b = pkt.rest()[:4]
        if len(b) < 4:
            return
        slots = s.data["char"].setdefault("quick_slots", {})
        # byte 1 names both lists (ProcessPacket_ResSlotSwap): the first slot's type and the other's
        ta, tb = {0: (0, 0), 1: (1, 1), 2: (2, 2), 3: (0, 2), 4: (2, 0), 5: (1, 2), 6: (2, 1)}.get(b[1], (b[1], b[1]))
        group = lambda t: b[2] if t == 1 else 0
        a, o = f"{ta}:{group(ta)}:{b[0]}", f"{tb}:{group(tb)}:{b[3]}"
        ea, eo = slots.pop(a, None), slots.pop(o, None)
        if ea is not None:
            slots[o] = ea
        if eo is not None:
            slots[a] = eo
        state.save()
        s.send(Writer(S2C_QUICK_SLOT_SWAP).u16(0).raw(b))

    @role.on(C2S_NPC_MENU)
    def npc_menu(s, pkt):
        """The realm window's list (0x1406365a0): both realms, each 3 bytes: realm T1[b0] & 3 (1 A, 2 B), b1 plain
        (A's goes to the panel and windows 0x5b / 0x2b; its meaning is not pinned, 0 is the contract's guess), join
        allowed T1[b2] & 1. The menu's realm's flag becomes +0x3c, without which clickJoin 0x140635240 refuses before
        sending 0x5a44 (u8 0 did that: 43 opens, no join; planning/client/town_quest_npc.md 0x5a48, Gap 1)."""
        w = Writer(S2C_NPC_MENU).u8(2)
        for realm in (1, 2):
            w.u8(obf.via_t1(realm)).u8(0).u8(obf.via_t1(1))
        s.send(w)

    @role.on(C2S_ENTER_TOWN_REQ)
    def enter_town_req(s, pkt):
        travel_to(s, struct.unpack("<I", pkt.take(4))[0])

    def travel(s, spot):
        travel_to(s, spot)

    def travel_to(s, spot):
        if spot in TOWN_ENTRY:
            pos = TOWN_ENTRY[spot]
        elif zone_start(spot) is not None:
            # the zone file's warp-less group-0 start point is the map's entry point: 10352's is 190 units from the
            # measured TOWN_ENTRY, 10001's 140 (Windstone 20200: (58609, 70069); its spottable corner (8000, 15000) is
            # off the playable map)
            pos = zone_start(spot)
        elif spot in TOWN_SPOT_START:
            x, z = TOWN_SPOT_START[spot]
            pos = (x, 0, z)
            log.warning("travel to spot %d: entry point not measured, using the spottable point", spot)
        else:
            log.warning("travel to spot %d: not a known City/Field spot", spot)
            return
        c = s.data["char"]
        c["spot"], c["pos"] = spot, list(pos)
        state.save()
        log.info("travel to spot %d at %s", spot, pos)
        journal("warp", how="travel", spot=spot, pos=list(pos))
        send_prepare_enter_town(s, spot, pos)

    @role.on(C2S_CHANNEL_SELECT)
    def channel_select(s, pkt):
        channel = pkt.u32()
        s.send(Writer(S2C_CHANNEL_SELECT).cstr(str(TOWN_CHANNEL)).obool(True))
        if channel == 0xFFFFFFFF and not in_battle_room(s):
            # the world map's "Enter field": the client waits for the server to take it in (inferred: nothing on
            # the client continues after 0x3750); the same way as arriving at the spot (0x3744)
            travel_to(s, s.data.get("target_spot") or s.data["char"].get("spot", START_SPOT))

    @role.on(C2S_LEAVE_TOWN)
    def leave_town(s, pkt):
        c = s.data["char"]
        x, y, z = c.get("pos", START_POS)
        q, n = obf.pos_xz(x, z)
        pos = q + struct.pack("<h", y) + bytes([n])
        s.send(Writer(S2C_LEAVE_TOWN).u16(0).raw(pos).u32(c.get("spot", START_SPOT)))
        s.send(Writer(S2C_TO_WORLDMAP).raw(pos).raw(obf.u32(c.get("spot", START_SPOT))))
        s.data["on_worldmap"] = True
        log.info("leave town %s for the world map", c.get("spot"))
        journal("warp", how="world map", spot=c.get("spot"))

    @role.on(C2S_MISSION_ESCAPE)
    def mission_escape(s, pkt):
        from . import game
        if s.data.get("entering"):          # a second leave while the first one's room change is under way (an
            # impatient second Esc -> Exit in the 5 s before the 0x3f41): the scheduled 0x3f41 still takes the client
            # into that room; answering it would mark this session as on the world map with no room (on_worldmap,
            # no battle_spot) while the client is in the room, and a later warp from there would skip its 0x4049
            log.info("leave ignored: the room change to spot %s is under way", s.data["entering"])
            return
        room = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        spot = room.data.get("spot") if room is not None else s.data.get("battle_spot")
        if spot and game.is_mission(spot):
            leave_mission_room(s, spot)
        else:
            escape_to_worldmap(s)           # a field room's leave: the world map at the field (its own spot)

    def leave_mission_room(s, spot):
        """0x4048 in a mission room (the Esc menu's MissionExit "Leave the battle now?", the chat MissionExit, an NPC's
        TO_WORLDMAP): the quest kept, the abort paid (game.deck_aborted: Troop_Mission_aborted), then
        - before the win, on another map than the spot it was entered from (c["spot"]): the world map at that spot,
          0x4049 kind 0 +6 1 (escape_to_worldmap). The original's: the client prints a mission exit's penalty (0x4049
          +0 gold, +0xe exp lost: common+0x16a8 / +0x16a0, written by 0x140d00590 only) at one place, the world map's
          OnEnter 0x140d363d0 -> 0x140d66680 (its only caller; texts 7382 "You lost %1% Gold because you left the game
          during the mission." / 7381 the exp, each only when non-zero), and 0x4048's own senders name it (NPC menu
          45 TO_WORLDMAP). No table gives a gold or exp penalty, so both stay 0 and the client prints neither.
        - before the win, on the same map (the client's own same-map rule, same_map): back into that field's room,
          as a field warp is (send_field_entry: 0x5641 with the group's warp, 0x4049 kind 3, then 0x3f41). Its
          handler 0x140d00590 first makes the block's spot current (0x140d65b10 -> 0x140d65c60), which sets
          common+0x1728 when the mission and that spot share a map (spottable Map_File, e.g. Lunawing I 10361 and Mist
          Field 10350, both 1_MistField); then it neither ends the battle nor loads, drops the game link and waits for
          the next room's 0x3f41 whatever the kind (native run 2026-10-09 15:00:08: kind 0 and no 0x3f41, a black
          screen for over 40 s). The group is a plain one (field_entry_group: no arrival cutscene replayed).
        - after the win, where Mission Complete would have ended it (game.mission_way_back), a field as a field warp,
          a town through 0x4049 kind 0 +6 2."""
        from . import game, zone
        c = s.data["char"]
        room = getattr(state, "game_sessions", {}).pop(s.data["account"]["id"], None)
        won = room is not None and room.data.get("mission_won")
        if room is not None:
            game.deck_aborted(s, state, room)
        if won:
            back, group, _ = game.mission_way_back(c)
        else:
            c.pop("mission", None)          # its way back was for a win; the next entry writes a new one
            back = c.get("spot", START_SPOT)
            group = field_entry_group(c, back)
        state.save()
        log.info("left mission %d %s for spot %d group %d", spot, "after its win" if won else "before its win", back,
                 group)
        journal("room", ev="escape", spot=spot, back=back, group=group, won=bool(won))
        if not won and not same_map(spot, back):
            escape_to_worldmap(s)
        elif game.is_field(back) and zone.available(back):
            send_field_entry(s, back, group, leave_battle=True)
        else:
            row = tables.by_id("spottable").get(str(back)) or {}
            escape_to_worldmap(s, town=row.get("Spot_Type") == "City")

    @role.on(C2S_WARP_REQUEST)
    def warp_request(s, pkt):
        b = pkt.rest()
        if len(b) < 14:
            log.warning("warp request not understood: %s", b.hex())
            return
        warp = obf.dec_u32(b[10:14])
        row = tables.by_id("warpinfo").get(str(warp))
        c = s.data["char"]
        cost = warp_cost(warp)
        if row is None and crystal_warp(s, state, warp, cost):
            return
        if row is None or not row["SpotID"].isdigit() or c.get("gold", 0) < cost:
            log.warning("warp request %d refused (row %s, cost %d)", warp, row is not None, cost)
            return
        spot, kind = int(row["SpotID"]), row["WARP_POSITION"]
        group = int(row["SPGroupID"]) if row.get("SPGroupID", "").isdigit() else 0
        from . import game, zone
        if kind == "FIELD" and game.is_field(spot) and zone.available(spot):
            if cost:
                change_gold(c, -cost)
            send_field_entry(s, spot, group, leave_battle=in_battle_room(s))
        elif kind in ("TOWN", "WORLD", "FIELD"):
            c["spot"], c["pos"] = spot, list(start_point(spot, group) or TOWN_ENTRY.get(spot) or c.get("pos", START_POS))
            if cost:
                change_gold(c, -cost)
            state.save()
            escape_to_worldmap(s, town=kind == "TOWN")
        else:
            log.warning("warp request %d: %s warps are not handled", warp, kind)
            return
        log.info("warp request %d: %s spot %d group %d (cost %d)", warp, kind, spot, group, cost)
        journal("warp", how="request", warp=warp, kind=kind, spot=spot, group=group, cost=cost)

    def escape_to_worldmap(s, town=False):
        """0x4049 kind 0 out of the room: to the world map, or (town) straight into the town at c["spot"] (+6 = 2,
        read from 0x140d00590; the client then loads the town and asks 0x3746)."""
        from . import game
        c = s.data["char"]
        spot = c.get("spot", START_SPOT)
        x, y, z = c.get("pos", START_POS)
        blk = bytearray(0x1d)
        blk[0:5] = obf.u40(0)                   # gold LOST by leaving (text 7382 "You have lost %d Gold. Due to exit
    #                                         during the mission.", 0x140d66680): no penalty offline
        blk[6] = ESCAPE_TO_TOWN if town else ESCAPE_TO_WORLDMAP
        blk[7:11], blk[13] = obf.pos_xz(x, z)
        blk[11:13] = struct.pack("<h", y)
        blk[0x16] = 0
        blk[0x17:0x1b] = obf.u32(spot)
        blk[0x1b:0x1d] = struct.pack("<H", game.MY_SLOT)
        s.send(Writer(S2C_MISSION_ESCAPE).u16(0).raw(bytes(blk)))
        s.data.pop("battle_spot", None)
        s.data["on_worldmap"] = not town
        c.pop("field_group", None)
        room = getattr(state, "game_sessions", {}).pop(s.data["account"]["id"], None)
        if room is not None:
            game.deck_aborted(s, state, room)   # a mission left before its win: Troop_Mission_aborted AP
        state.save()
        log.info("left the room at spot %d for the world map", spot)
        journal("room", ev="escape", spot=spot)

    @role.on(C2S_CLEARED)
    def cleared(s, pkt):
        s.send(cleared_packet(s.data["char"]))

    @role.on(0x4040)
    def mission_leave(s, pkt):
        from . import game                          # the leave after the result window (either connection)
        game.leave_mission(s, state)

    @role.on(0x4052)
    def drop_pick(s, pkt):
        from . import game                          # the drops live in the room's session
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        game.pick_drop(s, g, state, pkt.rest())

    @role.on(0x404c)
    def reward_card(s, pkt):
        from . import game                          # a card on the result screen; the cards live in the room's session
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        game.open_card(s, g, state, pkt.rest())

    @role.on(C2S_QUEST_ITEM_USE)
    def quest_item_use(s, pkt):
        b = pkt.rest()
        if len(b) < 9:
            return
        kind, code, target = (obf.T1[b[0]] - 8 * b[1]) & 0xff, obf.dec_u32(b[1:5]), obf.dec_u32(b[5:9])
        c = s.data["char"]
        r = items.row(code) or {}
        held = any(i["code"] == code for i in c.get("bag", []))
        if not held or r.get("Usable") != "True" or (kind == 1 and r.get("UseTargetID") != str(target)):
            log.warning("quest item %d on %d (kind %d) refused: held %s, row %s", code, target, kind, held,
                        {k: r.get(k) for k in ("Usable", "UseTarget", "UseTargetID")})
            s.send(Writer(S2C_QUEST_ITEM_USE).u16(NOT_READY))
            return
        s.send(Writer(S2C_QUEST_ITEM_USE).u16(0))
        quest.count(s, state, "UseItem", "ID1", {str(code)})
        log.info("quest item %d used on %d", code, target)

    @role.on(C2S_REALM_JOIN)
    def realm_join(s, pkt):
        realm = obf.T1[pkt.u8()] & 3
        c = s.data["char"]
        if c.get("realm") or realm not in (1, 2):
            s.send(Writer(S2C_REALM_JOIN).u16(1))           # already in one: a logged refusal on the client
            return
        c["realm"] = realm
        state.save()
        s.send(Writer(S2C_REALM_JOIN).u16(0).u8(obf.via_t1(realm)))
        quest.count(s, state, "Realm", "ID1", {"3", str(realm)})     # 1160442: Realm 3 = either realm (inferred)
        log.info("joined realm %d", realm)

    @role.on(C2S_RIDE)
    def ride(s, pkt):
        vehicle = pkt.u16()
        c = s.data["char"]
        c["vehicle"] = vehicle
        s.send(Writer(S2C_RIDE).u16(vehicle).i32(c["id"]))
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        if g is not None and "battle" in g.data and not g.w.is_closing():
            # the battle state mounts through 0x5113 (0x140d07750: i16 vehicle, u32 player key = Player +0x54,
            # game.player_key; 0 dismounts, else UnitHero::RideVehicle 0x140bfd140)
            from . import game
            g.send(Writer(S2C_ROOM_RIDE).u16(vehicle).u32(game.player_key(c)))
            log.info("ride %d in the room", vehicle)

    @role.on(C2S_NPC_BUFF)
    def npc_buff(s, pkt):
        b = pkt.rest()
        if len(b) < 9:
            return
        npc, ability = struct.unpack_from("<I", b, 0)[0], obf.dec_u32(b[5:9])
        c = s.data["char"]
        row = next((r for r in tables.sections("npctable")["Skill_NPC"] if r["ID"] == str(npc)), None)
        k = next((k for k in (1, 2, 3) if row and row[f"AbilityId{k}"] == str(ability)), None)
        if k is None:
            s.send(Writer(S2C_NPC_BUFF).u16(BUFF_NO_ITEM))
            return
        kind, value = row[f"Skill_Cost{k}"], int(row[f"Cost_Value{k}"]) if row[f"Cost_Value{k}"].isdigit() else 0
        if kind == "Gold" and c.get("gold", 0) < value:
            s.send(Writer(S2C_NPC_BUFF).u16(NOT_ENOUGH_GOLD))
            return
        if kind == "Item" and sum(i["count"] for i in c.get("bag", []) if i["code"] == int(row[f"Cost_Item{k}"])) < value:
            s.send(Writer(S2C_NPC_BUFF).u16(BUFF_NO_ITEM))
            return
        if kind not in ("Gold", "Item"):
            s.send(Writer(S2C_NPC_BUFF).u16(BUFF_NO_ITEM))        # Nectar: no such currency offline
            return
        if kind == "Gold":
            add_gold(s, state, -value)
        else:
            remove_item(s, state, int(row[f"Cost_Item{k}"]), value)
        from . import game
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        healed = g is not None and not g.w.is_closing() and game.heal_hero(g, 1 << 30)
        s.send(Writer(S2C_NPC_BUFF).u16(0))
        log.info("NPC %d heal (%s %d): %s", npc, kind, value, "hero healed" if healed else "no battle room")

    @role.on(C2S_ENTER_TOWN)
    def enter_town(s, pkt):
        s.data.pop("on_worldmap", None)
        spot = obf.dec_u32(pkt.take(4))
        c = s.data["char"]
        c["spot"] = spot
        s.data.pop("battle_spot", None)
        s.data["game_addr"] = (game_host, game_port)
        log.info("enter town spot %d -> channel %d", spot, TOWN_CHANNEL)
        journal("town", spot=spot)
        s.send(Writer(S2C_ENTER_TOWN).u8(TOWN_CHANNEL).u16(0))
        send_cargo(s)
        s.send(rebuy_packet(c))                # first shop open uses its cache; no1665 until a sale dirties it
        send_exp(s)
        quest.on_level(s, state, send=False)
        quest.send_lists(s)
        s.send(cleared_packet(c))                # a mission won since the last list (the client asks once a session)
        s.send(rules.day_limits_packet(c))       # the same for the day's counts, and a day turned (0x10b3 replaces)
        s.send(summon.board_packet(c))           # the summon board of the game day (0x1113; the window asks nothing)
        state.save()
        from . import game, zone
        if game.is_field(spot) and zone.available(spot):    # fields run as battle rooms (FIELD-BATTLE-PLAN); a field
            # without a zone file stays in the town state, where it worked before
            group = field_entry_group(c, spot)
            s.later(FIELD_REDIRECT_S, lambda: send_field_entry(s, spot, group, leave_battle=False))

    @role.on(C2S_ENTER_SPOT)
    def enter_spot(s, pkt):
        spot = obf.dec_u32(pkt.take(4))         # the client table-encodes the spot id
        rest = pkt.rest()                       # u8 difficulty (entry UI +0xa48; 0 from CAutoSpotRun and the NPC
                                                # menu), then the AI-PC list when some were added (specs)
        log.info("enter spot %d (rest %s) -> game %s:%d", spot, rest.hex(), game_host, game_port)
        refused = rules.day_refusal(s.data["char"], spot, rest[0] if rest else 0)
        if refused:                             # today's entries / clears are spent (spottable %DayLimit); the client
            log.info("enter spot %d refused: its day limit is spent", spot)      # checks it too, from 0x10b3
            s.send(Writer(S2C_GAME_SERVER).u16(refused).u8(0))
            return
        from . import game
        refused = game.entry_refusal(s.data["char"], spot, rest[0] if rest else 0)
        if refused:                             # too few deck troops organised (Min_Limit_Troop, the original's check)
            log.info("enter spot %d refused (%#x): too few troops organised", spot, refused)
            s.send(Writer(S2C_GAME_SERVER).u16(refused).u8(0))
            return
        journal("warp", how="door", spot=spot, difficulty=rest[0] if rest else 0)
        s.data["game_addr"] = (game_host, game_port)
        if game.is_mission(spot) and s.data.get("entering") == spot:     # the client's answer to the warp an entry
            log.info("enter spot %d: its entry is under way (a quest's warp)", spot)   # sent: no second entry (live
            return                                                         # 2026-09-30 13:44: two game logins, hung)
        if game.is_mission(spot):               # a mission with a zone file: leave a field room first, remember the way back
            game.pay_entry(s, state, spot, rest[0] if rest else 0)             # a PayItem requirement's ticket
            rules.count_day(s.data["char"], spot, rest[0] if rest else 0, rules.ENTER, s=s)   # (saved with the entry)
            send_mission_entry(s, state, spot, mission_quest(s.data["char"], spot), rest[0] if rest else 0)
            return
        if not game.is_field(spot):             # a Battle spot with no zone file (144 of 260): no room to build, the
            # client shows the refusal (world_travel.md Gaps 1; the room used to be one endless test enemy)
            log.info("enter spot %d: no zone file, refused", spot)
            s.send(Writer(S2C_GAME_SERVER).u16(NO_GAME).u8(0))
            return
        s.data["battle_spot"] = spot
        mission_door(s, state, spot)
        send_game_server(s, spot, game_host, game_port)

    role.ignore(C2S_SOCIAL)
    # Nothing waits on these (specs/session_account_worldmap.md): the EAC message 0x102e, the GM notice 0x1047, the
    # developer console 0x1051, the party map ping 0x1068 (sent only with party members).
    role.ignore(0x102e, 0x1047, 0x1051, 0x1068)

    @role.on(C2S_LOOK_SHOWN)
    def look_shown(s, pkt):
        """The hero window's "Look item" checkboxes (LookItemCheckBoxToggle 0x1405f5b50): the client has shown / hidden
        the part itself; the mask is kept on the character (hero.look_shown) so a room's player struct shows the same
        parts (census V3; before, every room drew every part again). No reply: 0x1080 is the broadcast to others."""
        b = pkt.rest()
        if len(b) < 4:
            return
        c = s.data["char"]
        c["look_shown"] = hero.decode_look_shown(struct.unpack_from("<I", b, 0)[0])
        state.save()
        log.info("look: parts shown %#x", c["look_shown"])
    # specs/pvp_mail_social.md: world-map route cancelled 0x2740, room start 0x3e4b (no reply handler), unfriend
    # 0x5342, party kick 0x544e and entry flag 0x5478 (party only), an oversized-packet report 0x4f4f, package opened
    # 0x5a54, reconnect keys 0x5941 / 0x5943 (never armed).
    role.ignore(0x2740, 0x3e4b, 0x5342, 0x544e, 0x5478, 0x4f4f, 0x5a54, 0x5941, 0x5943)
    # specs/field_npc_travel.md: flag toggles and marks nothing reads back (0x1248, 0x124f, 0x1257, 0x4079), the PvP
    # status 0x1443, the cash-shop open 0x375b, developer bindings (0x3f40 ForceGameStart, 0x5551 force complete,
    # 0x5640 WarpRequest), builders without callers (0x3f42, 0x3f46, 0x3f4b), the ack 0x5643. The tutorial skip 0x5550
    # is quest.py's (planning/client/town_quest_npc.md Gap 3).
    role.ignore(0x1248, 0x124f, 0x1257, 0x4079, 0x1443, 0x375b, 0x3f40, 0x5551, 0x3f42, 0x3f46, 0x3f4b, 0x5643)

    @role.on(C2S_LEAVE_NOTICE)
    def leave_notice(s, pkt):
        """0x5644: in game, the exit-game notice (the client quits right after); in the lobby, "Back" from character
        select, which waits for 0x5645 before it logs in again and returns to server select (planning/client/
        session_lobby.md: 0x140e784f6 -> 0x140eff230; the lobby's 0x5645 case reads nothing)."""
        if "char" not in s.data:
            s.send(Writer(S2C_LEAVE_NOTICE))
    # specs/guild_trade_realm.md: realm-war player pick 0x1106 and ticket 0x110d, by-name answer 0x1123 (never asked),
    # server-triggered checksums 0x114c / 0x114d, leaving a deal 0x3c53, a guild invitation answer 0x3d4c (its reply
    # has no result code and 25 bytes; invitations never arrive).
    role.ignore(0x1106, 0x110d, 0x1123, 0x114c, 0x114d, 0x3c53, 0x3d4c)
    # Login paths this client does not take (specs/session_account_worldmap.md): the clock echo 0x1000, other
    # publishers' and NHN logins (0x1002, 0x1013, 0x1020, 0x1022, 0x1033, 0x1035), the no-Steam-API login 0x1039, the
    # second password (0x1025, 0x1027) and the server queue (0x1029, 0x102c; 0x1007 always admits), builders nothing
    # calls (0x1019, 0x101c, 0x101d, 0x1023, 0x1034). Registered so they are logged as decided, not as unknown.
    role.ignore(0x1000, 0x1002, 0x1013, 0x1020, 0x1022, 0x1033, 0x1035, 0x1039, 0x1025, 0x1027, 0x1029, 0x102c,
                0x1019, 0x101c, 0x101d, 0x1023, 0x1034)
    # Builders nothing calls or empty handlers (0x106a, 0x1084, 0x1094, 0x1098, 0x109c, 0x10b9, 0x10be, 0x10e7), the
    # chat cheats SkillReset 0x1756 / SkillTrainReset 0x1758, 0x175e (no caller), the dead PvP 0x3e51 (never send
    # 0x3e52), dead party builders 0x546c / 0x546e / 0x5470.
    role.ignore(0x106a, 0x1084, 0x1094, 0x1098, 0x109c, 0x10b9, 0x10be, 0x10e7, 0x1756, 0x1758, 0x175e, 0x3e51,
                0x546c, 0x546e, 0x5470)

    @role.on(C2S_IDLE)
    def idle(s, pkt):
        s.send(Writer(S2C_IDLE).i32(s.data["char"]["id"]).u8(pkt.u16() != IDLE_OFF))

    @role.on(C2S_CHAT)
    def chat(s, pkt):
        channel, text = pkt.u8(), pkt.cstr()
        if text.strip().lower() in FORCE_WIN_COMMANDS:
            force_win(s, channel)
            return
        words = text.strip().lower().split()
        if words and words[0] in QUEST_COMMANDS:
            force_quests(s, channel, words)
            return
        s.send(Writer(S2C_CHAT).u8(channel).raw(bytes(CHAT_HEADER)).cstr(s.data["char"]["name"]).cstr(text))

    def force_win(s, channel):
        """The owner's command (2026-09-28: "create a command to force completion of a mission when it have some
        issue"): typed in chat inside a mission room, the mission is won as a real clear (game.mission_won: the
        victory window, MissionLevelClear for the held quests, the clear record, the card pick). Our mission layer
        stands in for scripts that never shipped, so a room it cannot finish would otherwise block the story."""
        from . import game
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        spot = g and g.data.get("spot")
        if g is None or g.w.is_closing() or not game.is_mission(spot) or g.data.get("mission_won"):
            reply = "!win works inside a mission room that is not won yet"
        else:
            from . import director
            director.skip_ending(g)                     # a command to get past a stuck room: the window at once
            game.mission_won(g, g.state)
            reply = f"mission {spot} completed by command"
            log.info("mission %d won by the owner's command", spot)
        s.send(Writer(S2C_CHAT).u8(channel).raw(bytes(CHAT_HEADER)).cstr("Server").cstr(reply))

    def force_quests(s, channel, words):
        """The owner's quest commands (2026-09-28: "another one to complete the quests ... to at least do some e2e
        wire and then start the tunning"): !quest [id] fills every condition of the active quests (or that one), so
        they show ready to hand in at their NPC; !questdone [id] also hands them in (rewards, gold, exp, finish
        warp), as the NPC's hand-in does (quest.fill / quest.hand_in)."""
        from . import quest
        active = list(quest.record(s.data["char"])["active"])
        ids = [w for w in words[1:] if w.isdigit()] or active
        filled = [qid for qid in ids if quest.fill(s, state, qid)]
        done = [qid for qid in filled if quest.hand_in(s, state, int(qid))] if words[0] in QUEST_DONE_COMMANDS else []
        reply = (f"quests handed in: {', '.join(done) or 'none'}" if words[0] in QUEST_DONE_COMMANDS
                 else f"quests ready to hand in: {', '.join(filled) or 'none (no active quest by that id)'}")
        s.send(Writer(S2C_CHAT).u8(channel).raw(bytes(CHAT_HEADER)).cstr("Server").cstr(reply))

    @role.on(C2S_EQUIP)
    def equip(s, pkt):
        b = pkt.take(20)
        args = (obf.dec_u64(b[0:8]), obf.dec_u64(b[8:16]), obf.dec_u16(b[16:18]), obf.dec_u16(b[18:20]))
        before = list(hero.equipment(s.data["char"]))
        why = change_equip(s.data["char"], *args)
        if why:
            log.warning("equip refused (%s)", why)
            s.send(Writer(S2C_EQUIP).u16(EQUIP_FAIL))
            return
        state.save()
        log.info("equip: bag %#x <-> equipment %#x (index %d, bag slot %d)", *args)
        s.send(Writer(S2C_EQUIP).u16(0))
        send_hero_detail(s)                     # the stats follow the new equipment
        g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
        if g is not None and "battle" in g.data and not g.w.is_closing():
            from . import game
            game.gear_changed(g, s.data["char"], before)    # and in a room, the hero's own numbers there
        # AssignItemInfos replaces the data but does not redraw an open inventory.
        # Native2026-10-09: unequip left a blank slot until I was reopened. The
        # item-change handler redraws the slot (140dca560/140dca7f0). Send it before
        # the snapshot: clearing a slot needs the old item still in the native bag.
        send_cargo(s, changed_slots=[args[3]])

    @role.on(C2S_USE_ITEM)
    def use_item(s, pkt):
        b = pkt.rest()
        if len(b) < 27:
            log.warning("item use not understood: %s", b.hex())
            return
        code, serial = obf.dec_u32(b[6:10]), obf.dec_u64(b[12:20])
        c = s.data["char"]
        it = bag_item(c, serial)
        row = items.row(code) or {}
        kind = row.get("ConsumeItemType")
        mine = it is not None and it["code"] == code and it.get("count", 0) > 0
        count = max(1, min(obf.dec_u16(b[20:22]), it["count"])) if mine else 0
        # Only these handlers consume the quantity dialog's whole selection; the others consume one item.
        if kind not in ("CUBIC", "BARRACK_TROOP_EXP", "TROOP_SKILL_BOOK"):
            count = min(count, 1)
        refused = item_use_refusal(c, code, count) if mine else ITEM_USE_REFUSED
        if not refused and kind in ("POTION", "FOOD", "SKILL_ITEM"):
            # QuickSlotManager::UseItem (0x1408e73e0): battle state and a living hero are required.
            g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
            t = g.data.get("battle") and g.data["battle"].troops.get(0) if g is not None else None
            if g is None or g.w.is_closing() or not t or t["hp"] <= 0 or t.get("down"):
                refused = ITEM_USE_REFUSED
        if refused:
            s.send(Writer(S2C_USE_ITEM).u16(refused))
            return
        if kind == "TROOP_SUMMON":
            # a troop contract (e.g. 355000000 from tutorial 9900103): the troop joins the barracks (troops.py)
            known = set(s.data["char"].get("troop_pedia", []))
            t, refused = troops.grant(s.data["char"], row.get("GainSetId"))
            if refused:
                s.send(Writer(S2C_USE_ITEM).u16(refused))
                return
            take_serial(s.data["char"], serial, 1)
            s.send(use_reply(s.data["char"], code))
            state.save()                              # save the cooldown together with the newly recruited troop
            s.send(troops.new_troop_packet(t))          # after 0x4043, which arms its "new troop" notice
            if t["id"] not in known and troops.pedia_one_packet(t["id"]):
                s.send(troops.pedia_one_packet(t["id"]))    # a type new to the troop book (0x1371)
            send_cargo(s, changed_slots=[it["slot"]])
            titles.achieve(s, state, "TroopGain", add=1)
            return
        num = lambda v: int(v) if str(v).isdigit() else 0
        used = lambda n=1: (take_serial(c, serial, n), s.send(use_reply(c, code, n)), state.save())
        if mine and kind == "SETENTERCOUNT_INIT":
            # a Reset Entry ticket (the Cubic shop's 8129000..8136000): its EnterCount_Init is the spottable %DayLimit
            # group it empties (100..102 the extremes, 301..303 the Colonock invasions); refused while nothing of the
            # group was used today, so the ticket is not lost (ours; census L13)
            group = str(num(row.get("EnterCount_Init")))
            counts = rules.day_counts(c)
            if not counts.get(group):
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_REFUSED))
                return
            del counts[group]
            used(1)
            s.send(rules.day_limits_packet(c))
            send_cargo(s, changed_slots=[it["slot"]])
            log.info("reset entry %d: day group %s emptied", code, group)
            return
        if mine and kind == "CUBIC":
            # a Cubic bundle (ChargeValue each; quest rewards, containers, daily tasks) into the balance (ROADMAP Q8 as
            # recommended, 2026-09-27: the bundles are a real source), pushed as 0x375d
            c["cubic"] = c.get("cubic", 0) + num(row.get("ChargeValue")) * count
            used(count)
            s.send(cubic_packet(c))
            send_cargo(s, changed_slots=[it["slot"]])
            log.info("cubic bundle %d x%d: balance %d", code, count, c["cubic"])
            return
        if mine and kind == "BARRACK_TROOP_EXP":
            # troop strategy books: ChargeValue each into the barracks exp pool (the client checked the cap)
            troops.add_pool(c, num(row.get("ChargeValue")) * count)
            used(count)
            s.send(troops.pool_packet(c))
            send_cargo(s, changed_slots=[it["slot"]])
            return
        if mine and kind == "TROOP_SKILL_BOOK":
            # a tactics skill's book (SkillBookAbilityID, SkillBookExp): learned / exp / levels in the academy (0x10bd)
            ability = num(row.get("SkillBookAbilityID"))
            t = None
            for _ in range(count):
                t = troops.tactics_book(c, ability, num(row.get("SkillBookExp"))) or t
            if t is None:
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_MAXED))
                return
            used(count)
            s.send(troops.tactics_one_packet(ability, t))
            send_cargo(s, changed_slots=[it["slot"]])
            log.info("tactics book %d: skill %d level %d exp %d", code, ability, t["level"], t["exp"])
            return
        if mine and kind == "HERO_SKILL_BOOK":
            # a level-30 hero skill (SkillBookAbilityID, heroskillbook AutoLearn False, RequireTP 0): learned
            ability = num(row.get("SkillBookAbilityID"))
            book = skills.book(c["class"]).get(ability)
            if book is None:
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_REFUSED))
                return
            if c.get("level", 1) < num(book.get("HeroLevel")):
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_LEVEL))
                return
            learned = c.setdefault("skills", {})
            learned[str(ability)] = max(1, learned.get(str(ability), 0))
            used()
            s.send(skills.info_packet(c))
            send_cargo(s, changed_slots=[it["slot"]])
            return
        if mine and kind == "EQUIPMENT_REPAIR":
            # the repair coupon 351500400 "Universal Repair: Repairs all equipped items when used." (its Explain
            # text; rules census ECONOMY I3): the worn items back to full durability, the bag's stay as they are
            worn = [e for e in hero.equipment(c) if "dur" in e]
            mended = any(hero.broken(e) for e in worn)
            for e in worn:
                e.pop("dur", None)
            used()
            for e in worn:
                s.send(equip_one(e))
            if mended:
                refresh_worn(s, state)
            send_cargo(s, changed_slots=[it["slot"]])
            return
        if mine and kind == "BARRACK_TROOP_CHEER":
            # the troop cheer item: every troop's action points back to the top (as 0x135c without the gold)
            for t in c.get("troops", []):
                t["ap"] = troops.cheer_cost(t)[1]
            used()
            s.send(troops.ap_packet(c.get("troops", [])))   # 0x1365: 0x1343 would insert only unknown troops
            send_cargo(s, changed_slots=[it["slot"]])                                   # (0x140da82e0), the window kept the old AP (T4.7)
            return
        if mine and kind == "TRANSPORT":
            # a teleport scroll (SpotID): the client moves by itself only on the world map; from a town the server
            # travels, from a room it leaves for the world map at the scroll's spot (the room -> town jump is unverified)
            spot = num(row.get("SpotID"))
            if not spot or spot == c.get("spot"):
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_REFUSED))
                return
            used()
            send_cargo(s, changed_slots=[it["slot"]])
            if in_battle_room(s):
                c["spot"], c["pos"] = spot, list(TOWN_ENTRY.get(spot) or zone_start(spot) or c.get("pos", START_POS))
                state.save()
                escape_to_worldmap(s)
            elif not s.data.get("on_worldmap"):       # on the world map the client moves by itself
                travel(s, spot)
            log.info("teleport scroll %d to spot %d", code, spot)
            return
        if it is not None and it["code"] == code and kind in ("VEHICLE_ACQUIRE", "TITLE_ITEM"):
            c = s.data["char"]
            if kind == "VEHICLE_ACQUIRE" and not titles.grant_vehicle(s, state, c, int(row.get("GainVehicleID", 0) or 0)):
                s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_REFUSED))
                return
            if kind == "TITLE_ITEM":
                titles.earn_title(s, c, int(row.get("GainTitleID", 0) or 0))
            take_serial(c, serial, 1)
            s.send(use_reply(c, code))
            state.save()
            send_cargo(s, changed_slots=[it["slot"]])
            return
        if mine and (str(row.get("ConsumeAbilityID", "")).isdigit() or kind == "FIREWORK") \
                and not (items.heal(code) or items.sp_gain(code)):         # two ALL potions heal as well: below
            # buff potions, food, skill items: the client cast the item's ability first (its statuses come from that
            # cast) and asks 0x4042 to spend the item; refusing it printed "You can not use this now" and kept the
            # item (planning/wiring/ITEMS-WIRING.md I9). Fireworks play over the hero (0x4044, I10)
            used()
            send_cargo(s, changed_slots=[it["slot"]])
            if bag_item(c, serial) is None:
                s.send(Writer(S2C_QUICK_BAR_SLOT).u8(0).u16(it["slot"]))    # the last one: its quick slots empty
            if kind == "FIREWORK":             # in a room the battle state finds the player by key (0x140de4a40)
                from . import game
                room = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
                s.send(Writer(S2C_FIREWORK).raw(obf.u32(code)).u32(game.player_key(c) if room else c["id"]))
            log.info("item %d used (%s)", code, kind)
            return
        hp, sp = items.heal(code), items.sp_gain(code)
        if it is None or it["code"] != code or not (hp or sp):
            log.info("item use refused: %d (serial %#x, in bag %s, heal %d)", code, serial, it is not None, hp)
            s.send(Writer(S2C_USE_ITEM).u16(ITEM_USE_REFUSED))
            return
        take_serial(s.data["char"], serial, 1)
        s.send(use_reply(s.data["char"], code))
        state.save()
        send_cargo(s, changed_slots=[it["slot"]])
        if bag_item(s.data["char"], serial) is None:
            s.send(Writer(S2C_QUICK_BAR_SLOT).u8(0).u16(it["slot"]))      # the last one: its quick slots empty
        from . import game
        g = getattr(state, "game_sessions", {}).get(s.data["account"]["id"])
        live = g is not None and not g.w.is_closing()
        healed = live and hp and game.heal_hero(g, hp)
        if live and sp:
            from . import combat
            combat.gain_sp(g, sp)
        log.info("item %d used: +%d hp, +%d sp (%s)", code, hp, sp, "in the room" if live else "no battle room")

    @role.on(C2S_OPEN_CONTAINER)
    def open_container(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            log.warning("container open not understood: %s", b.hex())
            return
        serial, want = obf.dec_u64(b[0:8]), obf.dec_u16(b[8:10])
        c = s.data["char"]
        it = bag_item(c, serial)
        if it is None or items.container(it["code"]) is None:
            log.warning("container open refused: serial %#x (%s)", serial, it and it["code"])
            s.send(Writer(S2C_OPEN_CONTAINER).u16(BAG_FULL))
            return
        opened = max(1, min(want, it["count"]))     # the stack's count dialog: that many boxes, one merged result
        if item_use_refusal(c, it["code"], opened):
            s.send(Writer(S2C_OPEN_CONTAINER).u16(BAG_FULL))
            return
        gold, merged = 0, {}
        for _ in range(opened):
            g, one = items.open_container(it["code"], random.randrange)
            gold += g
            for code, k in one:
                merged[code] = merged.get(code, 0) + k
        got = list(merged.items())
        if not fits(c, got, it["slot"] if it["count"] == opened else None):
            log.info("container %d: no room for %s", it["code"], got)
            s.send(Writer(S2C_OPEN_CONTAINER).u16(BAG_FULL))
            return
        s.data["container"] = (serial, it["code"], gold, got, opened)     # shown now, given on 0x1669
        w = Writer(S2C_OPEN_CONTAINER).u16(0).raw(obf.u40(gold)).u16(len(got))
        for code, n in got:
            w.raw(obf.u16(n)).raw(obf.u32(code)).raw(obf.u16(0))
        s.send(w)
        log.info("container %d x%d opened: gold %d, items %s", it["code"], opened, gold, got)

    @role.on(C2S_TAKE_CONTAINER)
    def take_container(s, pkt):
        b = pkt.rest()
        pending = s.data.pop("container", None)
        c = s.data["char"]
        serial = obf.dec_u64(b[0:8]) if len(b) >= 8 else None
        if pending is None or pending[0] != serial or (bag_item(c, serial) or {}).get("count", 0) < pending[4]:
            log.warning("container take without an open result: %s", b.hex())
            s.send(Writer(S2C_TAKE_CONTAINER).u16(BAG_FULL))
            return
        _, code, gold, got, opened = pending
        it = bag_item(c, serial)
        if (it["code"] != code or item_use_refusal(c, code, opened)
                or not fits(c, got, it["slot"] if it["count"] == opened else None)):
            s.send(Writer(S2C_TAKE_CONTAINER).u16(BAG_FULL))
            return
        take_serial(c, serial, opened)
        count_item_day(c, code, opened)
        change_gold(c, gold)
        for item, n in got:
            add_item(s, state, item, n)
        state.save()
        s.send(Writer(S2C_TAKE_CONTAINER).u16(0))
        send_cargo(s)
        log.info("container %d x%d taken: gold %d, items %s", code, opened, gold, got)

    @role.on(C2S_BAG_MOVE)
    def bag_move(s, pkt):
        b = pkt.rest()
        if len(b) < 20:
            log.warning("bag move not understood: %s", b.hex())
            return
        src, dst = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4])
        serial, other = obf.dec_u64(b[4:12]), obf.dec_u64(b[12:20])
        c = s.data["char"]
        it = bag_item(c, serial)
        there = next((i for i in c.get("bag", []) if i["slot"] == dst), None)
        if (it is None or it["slot"] != src or not slot_ok(c, it["code"], dst)
                or (there["serial"] if there else 0) != other
                or (there is not None and not slot_ok(c, there["code"], src))):
            log.warning("bag move refused: %d -> %d (serial %#x, target %#x)", src, dst, serial, other)
            s.send(Writer(S2C_BAG_MOVE).u16(BAG_MOVE_REFUSED))
            return
        it["slot"] = dst
        if there is not None:
            there["slot"] = src                 # a whole-stack drop on another item swaps them
        state.save()
        s.send(Writer(S2C_BAG_MOVE).u16(0))
        s.send(Writer(S2C_QUICK_BAR_SLOT).u8(1).u16(src).u16(dst))
        send_cargo(s, changed_slots=[src, dst])                           # 0x1647 moves nothing on the client

    @role.on(C2S_BAG_SPLIT)
    def bag_split(s, pkt):
        b = pkt.rest()
        if len(b) < 14:
            log.warning("bag split not understood: %s", b.hex())
            return
        src, dst, serial, n = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12]), obf.dec_u16(b[12:14])
        c = s.data["char"]
        it = bag_item(c, serial)
        there = next((i for i in c.get("bag", []) if i["slot"] == dst), None)
        ok = (it is not None and it["slot"] == src and 1 <= n <= it["count"] and slot_ok(c, it["code"], dst)
              and dst != src
              and (there is None or (items.can_stack(there, it)
                                     and there["count"] + n <= items.max_stack(it["code"]))))
        if not ok:
            log.warning("bag split refused: %d -> %d, %d of serial %#x", src, dst, n, serial)
            s.send(Writer(S2C_BAG_SPLIT).u16(BAG_MOVE_REFUSED))
            return
        if there is not None:
            there["count"] += n                 # onto the same item
            take_serial(c, serial, n)
            if bag_item(c, serial) is None:
                s.send(Writer(S2C_QUICK_BAR_SLOT).u8(0).u16(src))
        elif n == it["count"]:
            it["slot"] = dst                    # the whole stack into an empty slot
            s.send(Writer(S2C_QUICK_BAR_SLOT).u8(1).u16(src).u16(dst))
        else:
            c["bag"].append({**deepcopy(it), "slot": dst, "count": n, "serial": serials.allocate(c)})
            take_serial(c, serial, n)
        state.save()
        s.send(Writer(S2C_BAG_SPLIT).u16(0))
        send_cargo(s, changed_slots=[src, dst])                           # the new stack's serial

    @role.on(C2S_WAREHOUSE_LIST)
    def warehouse_list(s, pkt):
        s.send(warehouse_packet(s.data["char"], pkt.u8()))

    @role.on(C2S_BAG_TO_WAREHOUSE)
    def bag_to_warehouse(s, pkt):
        box_transfer(s, state, pkt.rest(), "bag", "warehouse", S2C_BAG_TO_WAREHOUSE)

    @role.on(C2S_WAREHOUSE_TO_BAG)
    def warehouse_to_bag(s, pkt):
        box_transfer(s, state, pkt.rest(), "warehouse", "bag", S2C_WAREHOUSE_TO_BAG)

    @role.on(C2S_WAREHOUSE_MOVE)
    def warehouse_move(s, pkt):
        b = pkt.rest()
        if len(b) < 20:
            log.warning("warehouse move not understood: %s", b.hex())
            return
        src, dst, serial, other = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12]), obf.dec_u64(b[12:20])
        c = s.data["char"]
        it = box_item(c, "warehouse", serial)
        if it is None or not move_stack(c, "warehouse", "warehouse", serial, src, dst, it["count"], other):
            log.warning("warehouse move refused: %d -> %d (serial %#x, target %#x)", src, dst, serial, other)
            s.send(Writer(S2C_WAREHOUSE_MOVE).u16(WAREHOUSE_REFUSED))
            return
        state.save()
        s.send(Writer(S2C_WAREHOUSE_MOVE).u16(0))
        s.send(warehouse_packet(c, 0))          # 0x1649 moves nothing on the client

    @role.on(C2S_WAREHOUSE_SPLIT)
    def warehouse_split(s, pkt):
        b = pkt.rest()
        if len(b) < 14:
            log.warning("warehouse split not understood: %s", b.hex())
            return
        src, dst, serial, n = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12]), obf.dec_u16(b[12:14])
        c = s.data["char"]
        ok = move_stack(c, "warehouse", "warehouse", serial, src, dst, n)
        if not ok:
            log.warning("warehouse split refused: %d -> %d, %d of serial %#x", src, dst, n, serial)
        else:
            state.save()
        s.send(Writer(S2C_WAREHOUSE_SPLIT).u16(0 if ok else WAREHOUSE_REFUSED))
        s.send(warehouse_packet(c, 0))

    @role.on(C2S_WAREHOUSE_SORT)
    def warehouse_sort(s, pkt):
        # by item, then the fuller stack first, packed from slot 0; the whole list follows (0x1659's per-slot rule
        # for add vs clear is not pinned, so it only carries the re-enable)
        c = s.data["char"]
        for slot, it in enumerate(sorted(c.get("warehouse", []), key=lambda i: (i["code"], -i["count"], i["serial"]))):
            it["slot"] = slot
        state.save()
        s.send(Writer(S2C_WAREHOUSE_SORT).u16(0))
        s.send(warehouse_packet(c, 0))

    @role.on(C2S_WAREHOUSE_GOLD)
    def warehouse_gold(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            log.warning("warehouse gold not understood: %s", b.hex())
            return
        amount, withdraw = obf.dec_u40(b[0:5]), b[5] == 1
        c = s.data["char"]
        bag, kept = c.get("gold", 0), c.get("warehouse_gold", 0)
        frm, to = (kept, bag) if withdraw else (bag, kept)
        if b[5] > 1 or not 0 < amount <= frm or to + amount > GOLD_CAP:
            log.warning("warehouse gold refused: %s %d (bag %d, warehouse %d)", "out" if withdraw else "in", amount,
                        bag, kept)
            s.send(Writer(S2C_WAREHOUSE_GOLD).u16(NOT_ENOUGH_GOLD))
            return
        sign = -1 if withdraw else 1
        change_gold(c, -sign * amount)
        c["warehouse_gold"] = kept + sign * amount
        state.save()
        s.send(Writer(S2C_WAREHOUSE_GOLD).u16(0).raw(obf.u40(c["warehouse_gold"])).raw(obf.u40(c["gold"])))

    @role.on(C2S_STORE_BUY)
    def store_buy(s, pkt):
        b = pkt.rest()
        if len(b) < 13:
            log.warning("store buy not understood: %s", b.hex())
            return
        dst, shop, n, slot = obf.dec_u16(b[0:2]), struct.unpack_from("<I", b, 6)[0], obf.dec_u16(b[10:12]), b[12]
        code, bundle = items.sale_slot(shop, slot)
        c = s.data["char"]
        qty = n * max(1, bundle)
        cost = items.buy_price(code) * qty if code else 0
        if code is None or n < 1:
            log.warning("store buy refused: shop %d slot %d", shop, slot)
            s.send(Writer(S2C_STORE_BUY).u16(BAG_FULL).u64(0).raw(obf.u40(c.get("gold", 0))))   # the handler reads 15
            return                                                                              # bytes on every result
        money = int(items.row(code).get("MoneyType", "0")) if str(items.row(code).get("MoneyType", "")).isdigit() else 0
        have = c.get("gold", 0) if money == 0 else sum(i["count"] for i in c.get("bag", []) if i["code"] == money)
        if have < cost:                                  # a token shop's goods cost their MoneyType token item
            s.send(Writer(S2C_STORE_BUY).u16(NOT_ENOUGH_GOLD).u64(0).raw(obf.u40(c.get("gold", 0))))
            return
        # Check the bag after payment: exhausting token stacks may free the space for the purchase.
        # No intermediate save may contain the reward without its payment (add_item saves the completed change).
        left, payment = cost if money else 0, []
        if money:
            for it in sorted((i for i in c.get("bag", []) if i["code"] == money), key=lambda i: -i["slot"]):
                paid = min(left, it["count"])
                payment.append((it["serial"], paid))
                left -= paid
        paid_by_serial = dict(payment)
        after = [dict(i, count=i["count"] - paid_by_serial.get(i["serial"], 0)) for i in c.get("bag", [])
                 if i["count"] > paid_by_serial.get(i["serial"], 0)]
        if not fits(dict(c, bag=after), [(code, qty)]):
            s.send(Writer(S2C_STORE_BUY).u16(BAG_FULL).u64(0).raw(obf.u40(c.get("gold", 0))))
            return
        before = {it["slot"]: deepcopy(it) for it in c.get("bag", [])}
        for serial, paid in payment:
            take_serial(c, serial, paid)
        if money:
            journal("item", ev="spend", code=money, name=items.name(money), n=cost, why="shop purchase")
        else:
            change_gold(c, -cost)
        add_item(s, state, code, qty, prefer_slot=dst, mail=False, refresh=False)
        journal("item", ev="buy", code=code, name=items.name(code), n=qty, shop=shop, slot=slot, price=cost,
                money=money or None)
        state.save()
        s.send(Writer(S2C_STORE_BUY).u16(0).u64(0).raw(obf.u40(c["gold"])))
        #1541 must see the old common gold:140dcbdb0 skips the open shop's
        # refresh when1656 has already installed the new total.
        after = {it["slot"]: it for it in c.get("bag", [])}
        changed = sorted(slot for slot in before.keys() | after.keys() if before.get(slot) != after.get(slot))
        send_cargo(s, changed_slots=changed)
        log.info("store %d slot %d: bought %d x%d for %d of currency %d", shop, slot, code, qty, cost, money)

    @role.on(C2S_STORE_SELL)
    def store_sell(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            log.warning("store sell not understood: %s", b.hex())
            return
        n, slot, serial = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12])
        c = s.data["char"]
        it = bag_item(c, serial)
        price = items.sell_price(it["code"]) if it else 0
        if it is None or it["slot"] != slot or not 1 <= n <= it["count"] or price <= 0:
            log.warning("store sell refused: %d of serial %#x at slot %d (price %d)", n, serial, slot, price)
            s.send(Writer(S2C_STORE_SELL).raw(obf.u40(c.get("gold", 0))).u16(SELL_REFUSED))
            send_cargo(s)
            return
        rebuy = c.setdefault("buyback", [])
        rebuy.append({"code": it["code"], "count": n, "bound": it.get("bound", False), "price": price,
                      "enchant": it.get("enchant", 0), **items.extras(it),
                      "serial": it["serial"] if n == it["count"] else None})
        del rebuy[:-REBUY_KEEP]
        take_serial(c, serial, n)
        change_gold(c, price * n)
        journal("item", ev="sell", code=it["code"], name=items.name(it["code"]), n=n, price=price * n)
        state.save()
        s.send(Writer(S2C_STORE_SELL).raw(obf.u40(c["gold"])).u16(0))    # in a room too: its gold refresh 0x140dcbdb0
        send_cargo(s, changed_slots=[slot])                               # is the one 0x1541 already runs there
        log.info("sold %d x%d for %d gold", it["code"], n, price * n)

    @role.on(C2S_REPAIR)
    def repair(s, pkt):
        b = pkt.rest()
        n = struct.unpack_from("<H", b, 0)[0] if len(b) >= 2 else 0
        c = s.data["char"]
        chosen = []
        for k in range(n):
            e = b[2 + 11 * k:13 + 11 * k]
            if len(e) < 11:
                break
            serial = obf.dec_u64(e[1:9])
            it = next((i for i in (hero.equipment(c) if e[0] == 1 else c.get("bag", [])) if i["serial"] == serial), None)
            if it is not None and all(it is not x for x, _ in chosen):
                chosen.append((it, e[0] == 1))
        total = sum(items.repair_cost(it) for it, _ in chosen)
        if c.get("gold", 0) < total:
            s.send(Writer(S2C_REPAIR).u16(NOT_ENOUGH_GOLD))
            return
        mended = any(worn and hero.broken(it) for it, worn in chosen)   # a broken worn piece counts again (G20)
        for it, _ in chosen:
            it.pop("dur", None)
        if total:
            add_gold(s, state, -total)
        state.save()
        s.send(Writer(S2C_REPAIR).u16(0))
        for it, worn in chosen:
            if worn:
                s.send(equip_one(it))
        if mended:                              # the window follows its stats
            refresh_worn(s, state)
        if any(not worn for _, worn in chosen):
            send_cargo(s)
        log.info("repaired %d item(s) for %d gold", len(chosen), total)

    def compose_target(c, where, serial, slot):
        pool = hero.equipment(c) if where == 1 else c.get("bag", []) if where == 0 else []
        return next((i for i in pool if i["serial"] == serial and i["index" if where == 1 else "slot"] == slot), None)

    @role.on(C2S_COMPOSE)
    def compose(s, pkt):
        b = pkt.rest()
        if len(b) < 22:
            return
        stone_serial, where, target_serial, idx = obf.dec_u64(b[0:8]), b[8], obf.dec_u64(b[9:17]), b[17]
        stone_slot, target_slot = obf.dec_u16(b[18:20]), obf.dec_u16(b[20:22])
        c = s.data["char"]
        stone = bag_item(c, stone_serial)
        target = compose_target(c, where, target_serial, target_slot)
        row = items.row(stone["code"]) if stone else None
        socks = items.sockets(target) if target else []
        if (row is None or stone["slot"] != stone_slot or row.get("ItemKind") != "COMPOSE_ITEM"
                or not idx < len(socks)):
            log.warning("compose refused: stone %#x slot %d, target %#x (%d) slot %d, socket %d", stone_serial,
                        stone_slot, target_serial, where, target_slot, idx)
            s.send(Writer(S2C_COMPOSE).u16(COMPOSE_REFUSED))
            return
        if row["ReqLevel"].isdigit() and int(row["ReqLevel"]) > c.get("level", 1):
            s.send(Writer(S2C_COMPOSE).u16(COMPOSE_LEVEL))
            return
        prob = next((int(x["EquipProb"]) for x in tables.sections("item_compose")["EquipProb"]
                     if x["Rarity"] == row.get("Rarity")), 100000)
        take_serial(c, stone_serial, 1)
        if random.randrange(100000) < prob:
            socks[idx] = stone["code"]                   # a stone already there is lost (message 0x1c59)
            target["sockets"] = socks
            result = 0
        else:                                            # unreachable with the shipped EquipProb (100000 everywhere):
            target["bound"] = True                       # message 0x1c5a says the item is bound (inferred)
            result = COMPOSE_FAILED
        state.save()
        s.send(Writer(S2C_COMPOSE).u16(result))
        send_cargo(s)
        if where == 1:
            send_hero_detail(s)
        log.info("compose: stone %d into %d socket %d -> %#x", stone["code"], target["code"], idx, result)

    @role.on(C2S_DISARM)
    def disarm(s, pkt):
        b = pkt.rest()
        if len(b) < 13:
            return
        idx, target_slot, pay, target_serial, where = b[0], obf.dec_u16(b[1:3]), b[3], obf.dec_u64(b[4:12]), b[12]
        c = s.data["char"]
        target = compose_target(c, where, target_serial, target_slot)
        socks = items.sockets(target) if target else []
        stone = socks[idx] if idx < len(socks) else -1
        cost = (items.compose_cost(stone) if pay == 0 else items.compose_cubic(stone)) if stone != -1 else 0
        short = c.get("gold", 0) < cost if pay == 0 else c.get("cubic", 0) < cost
        if stone == -1 or pay > DISARM_CUBIC or short:       # the reply has no "not enough Cubic" text (0x14072e200)
            log.warning("disarm refused: target %#x (%d) slot %d, socket %d, payment %d", target_serial, where,
                        target_slot, idx, pay)
            s.send(Writer(S2C_DISARM).u16(COMPOSE_REFUSED))
            return
        socks[idx] = -1
        target["sockets"] = socks
        if pay == DISARM_CUBIC:
            spend_cubic(s, state, cost)
        else:
            change_gold(c, -cost)
        state.save()
        s.send(Writer(S2C_DISARM).u16(0))
        add_item(s, state, stone, 1)                     # the bag resend carries the new gold
        if where == 1:
            send_hero_detail(s)
        log.info("disarm: stone %d out of %d socket %d for %d %s", stone, target["code"], idx, cost,
                 "Cubic" if pay else "gold")

    @role.on(C2S_HERO_EDIT)
    def hero_edit(s, pkt):
        blk = pkt.rest()[:0x34]
        c = s.data["char"]
        ticket = next((it for it in c.get("bag", [])
                       if (items.row(it["code"]) or {}).get("ConsumeItemType") == "HERO_EDIT"), None)
        look = bytearray(bytes.fromhex(c.get("look", "")))
        if len(blk) < 0x34 or ticket is None or len(look) < 0x34:
            log.warning("hero edit refused (%d bytes, ticket %s)", len(blk), ticket and ticket["code"])
            s.send(Writer(S2C_HERO_EDIT).u16(1))
            return
        look[0x00:0x15] = blk[0x1e:0x33]              # face morph
        look[0x15:0x1f] = blk[0x14:0x1e]              # colour U/V pairs
        look[0x1f:0x33] = blk[0x00:0x14]              # coded part ids
        look[0x33] = blk[0x33]                        # two-tone ratio
        c["look"] = bytes(look).hex()
        take_serial(c, ticket["serial"], 1)
        state.save()
        s.send(Writer(S2C_HERO_EDIT).u16(0).raw(blk))
        send_cargo(s)
        log.info("hero appearance changed (ticket %d)", ticket["code"])

    @role.on(C2S_REBUY_LIST)
    def rebuy_list(s, pkt):
        s.send(rebuy_packet(s.data["char"]))

    @role.on(C2S_REBUY)
    def rebuy(s, pkt):
        b = pkt.rest()
        if len(b) < 4:
            return
        slot, index = obf.dec_u16(b[0:2]), struct.unpack_from("<H", b, 2)[0]
        c = s.data["char"]
        rebuy = c.get("buyback", [])
        e = rebuy[index] if index < len(rebuy) else None
        there = next((it for it in c.get("bag", []) if it["slot"] == slot), None)
        can_merge = e is not None and there is not None and items.can_stack(there, e) \
            and there["count"] + e["count"] <= items.max_stack(e["code"])
        result = (1 if e is None else NOT_ENOUGH_GOLD if c.get("gold", 0) < e["price"] * e["count"] else
                  BAG_NO_ROOM if (there is not None and not can_merge) or not slot_ok(c, e["code"], slot) else 0)
        if not result:
            rebuy.pop(index)
            change_gold(c, -e["price"] * e["count"])
            journal("item", ev="rebuy", code=e["code"], name=items.name(e["code"]), n=e["count"],
                    price=e["price"] * e["count"])
            if there is not None:
                there["count"] += e["count"]
            else:
                c["bag"].append({"code": e["code"], "slot": slot, "count": e["count"], "bound": e["bound"],
                                 "enchant": e.get("enchant", 0), **items.extras(e),
                                 "serial": e["serial"] or serials.allocate(c)})
            state.save()
        s.send(Writer(S2C_REBUY).raw(obf.u40(c.get("gold", 0))).u16(result))
        if not result:
            send_cargo(s, changed_slots=[slot])

    @role.on(C2S_DESTROY)
    def destroy(s, pkt):
        destroy_in(s, pkt, "bag", S2C_DESTROY, BAG_MOVE_REFUSED)

    @role.on(C2S_DESTROY_KEPT)
    def destroy_kept(s, pkt):
        destroy_in(s, pkt, "warehouse", S2C_DESTROY_KEPT, WAREHOUSE_REFUSED)

    def destroy_in(s, pkt, box, reply, refused):
        b = pkt.rest()
        if len(b) < 12:
            return
        slot, n, serial = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12])
        c = s.data["char"]
        it = box_item(c, box, serial)
        if it is None or it["slot"] != slot or not 1 <= n <= it["count"]:
            log.warning("destroy refused: %d of serial %#x at %s slot %d", n, serial, box, slot)
            s.send(Writer(reply).u16(refused))
            return
        it["count"] -= n
        if not it["count"]:
            c[box].remove(it)
        state.save()
        s.send(Writer(reply).u16(0))
        s.send(warehouse_packet(c, 0)) if box == "warehouse" else send_cargo(s)
        log.info("destroyed %d x%d from the %s", it["code"], n, box)

    @role.on(C2S_DESTROY_WORN)
    def destroy_worn(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            return
        serial, index = obf.dec_u64(b[0:8]), obf.dec_u16(b[8:10])
        c = s.data["char"]
        eq = hero.equipment(c)
        e = next((e for e in eq if e["index"] == index and e["serial"] == serial), None)
        if e is None:
            s.send(Writer(S2C_DESTROY_WORN).u16(1))
            return
        eq.remove(e)
        state.save()
        s.send(Writer(S2C_DESTROY_WORN).u16(0).raw(obf.u16(index)))
        send_hero_detail(s)

    @role.on(C2S_SWAP_PAIR)
    def swap_pair(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            return
        serial, index = obf.dec_u64(b[0:8]), obf.dec_u16(b[8:10])
        other = {7: 8, 8: 7, 9: 10, 10: 9}.get(index)
        eq = hero.equipment(s.data["char"])
        e = next((e for e in eq if e["index"] == index), None)
        if other is None or e is None or e["serial"] != serial:
            s.send(Writer(S2C_SWAP_PAIR).u16(1))
            return
        mate = next((x for x in eq if x["index"] == other), None)
        e["index"] = other
        if mate is not None:
            mate["index"] = index
        state.save()
        s.send(Writer(S2C_SWAP_PAIR).u16(0))

    @role.on(C2S_DISMANTLE)
    def dismantle(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            return
        slot, n, serial = obf.dec_u16(b[0:2]), obf.dec_u16(b[2:4]), obf.dec_u64(b[4:12])
        c = s.data["char"]
        it = bag_item(c, serial)
        if it is None or it["slot"] != slot or not 1 <= n <= it["count"]:
            s.send(Writer(S2C_DISMANTLE).u16(1))
            return
        got = items.dismantle(it["code"], it.get("enchant", 0), n, random.randrange)
        if got is None:
            s.send(Writer(S2C_DISMANTLE).u16(DISMANTLE_NO))
            return
        bag = c["bag"]
        if not fits(c, got, it["slot"] if n == it["count"] else None):
            s.send(Writer(S2C_DISMANTLE).u16(BAG_FULL))
            return
        take_serial(c, serial, n)
        for code, k in got:
            add_item(s, state, code, k)
        state.save()
        w = Writer(S2C_DISMANTLE).u16(0).u8(len(got))
        for code, k in got:
            w.raw(obf.u16(k)).raw(obf.u32(code))
        s.send(w)
        send_cargo(s)
        log.info("dismantled %d x%d: %s", it["code"], n, got)
        titles.achieve(s, state, "ItemDismantle", add=n)

    @role.on(C2S_ENCHANT)
    def enchant(s, pkt):
        b = pkt.rest()
        if len(b) < 16:
            log.warning("enchant not understood: %s", b.hex())
            return
        add, slot, material, serial, source = b[0], obf.dec_u16(b[1:3]), obf.dec_u32(b[3:7]), obf.dec_u64(b[7:15]), b[15]
        c = s.data["char"]
        if add not in (0, 1, 2) or source not in (0, 1):
            s.send(Writer(S2C_ENCHANT).u16(ENCHANT_NOT_ALLOWED))
            return
        it = held_item(c, source == 1, slot, serial)
        level = it.get("enchant", 0) if it else 0
        rule = items.enchant_rule(it["code"], level) if it else None
        held = sum(i["count"] for i in c.get("bag", []) if i["code"] == material)
        cubic = items.enchant_add_cost(it["code"], level, add) if it and add else 0
        result = (ENCHANT_NOT_ALLOWED if rule is None or level >= rule["max"] else
                  ENCHANT_CASH if add and (not cubic or c.get("cubic", 0) < cubic) else
                  ENCHANT_MATERIAL if material != rule["material"] or held < rule["count"] else
                  NOT_ENOUGH_GOLD if c.get("gold", 0) < rule["cost"] else 0)
        if result:
            log.warning("enchant of %s refused: %#x", it and it["code"], result)
            s.send(Writer(S2C_ENCHANT).u16(result))
            return
        if add:
            spend_cubic(s, state, cubic)            # the Cubic add-types (items.enchant_add_cost; checked above)
        # success-up adds %LuckyStone's weight to the success (ours, ITEMS-WIRING.md D1 (a))
        outcomes = [(lv, w + (items.lucky_bonus() if add == 1 and k == 0 else 0), k) for lv, w, k in rule["outcomes"]]
        x, new, outcome = random.randrange(sum(w for _, w, _ in outcomes)), level, 5
        for lv, w, k in outcomes:
            if x < w:
                new, outcome = lv, k
                break
            x -= w
        if add == 2 and new < level:
            new, outcome = level, ENCHANT_STAY      # prevent-down: a failure that would drop the level keeps it (D1)
        change_gold(c, -rule["cost"])
        it["enchant"] = new
        if new > level:
            titles.achieve(s, state, "ItemEnchantLv", add=1,
                           cond={1: (items.row(it["code"]) or {}).get("Parts"), 2: new})
        remove_item(s, state, material, rule["count"])       # saves and sends the bag (gold and the new level)
        if source == 1:
            refresh_worn(s, state)                  # the enchant level counts in the hero's stats (enchant_traits)
        s.send(Writer(S2C_ENCHANT).u16(0).u16(new).u8(outcome))
        quest.count(s, state, "AnyEnchant", "ID1", {"", "-"})
        log.info("enchant %d: %d -> %d (outcome %d, %d gold, add-type %d for %d Cubic)", it["code"], level, new,
                 outcome, rule["cost"], add, cubic)

    @role.on(C2S_ENCHANT_TRANSFER)
    def enchant_transfer(s, pkt):
        b = pkt.rest()
        if len(b) < 26:
            log.warning("enchant transfer not understood: %s", b.hex())
            return
        to_worn, to_slot, to_serial = b[0], *struct.unpack_from("<HQ", b, 1)
        from_slot, material = struct.unpack_from("<HI", b, 0x0b)
        from_worn, from_serial = b[0x11], struct.unpack_from("<Q", b, 0x12)[0]
        c = s.data["char"]
        if from_worn not in (0, 1) or to_worn not in (0, 1):
            s.send(Writer(S2C_ENCHANT_TRANSFER).u16(TRANSFER_REFUSED))
            return
        src, dst = held_item(c, from_worn == 1, from_slot, from_serial), held_item(c, to_worn == 1, to_slot, to_serial)
        level = src.get("enchant", 0) if src else 0
        rule = items.enchant_transfer(src["code"], level, dst["code"]) if src and dst and src is not dst else None
        top = (items.enchant_rule(dst["code"], 0) or {}).get("max", 0) if dst else 0
        held = sum(i["count"] for i in c.get("bag", []) if i["code"] == material)
        # every shipped chance is 100 % or 0 (items.enchant_transfer), so a transfer the client lets through succeeds
        if rule is None or not rule["chance"] or not top or material != rule["material"] or held < rule["count"]:
            log.warning("enchant transfer refused: %s +%d -> %s (%s, material %d x%d held)", src and src["code"], level,
                        dst and dst["code"], rule, material, held)
            s.send(Writer(S2C_ENCHANT_TRANSFER).u16(TRANSFER_REFUSED))
            return
        if not spend_cubic(s, state, rule["cubic"]):
            s.send(Writer(S2C_ENCHANT_TRANSFER).u16(CUBIC_SHORT))
            return
        dst["enchant"] = min(level, top)            # capped at the target's own maximum (ours)
        src["enchant"] = 0                          # what the source keeps is not in the client: 0 (ours, I5)
        remove_item(s, state, material, rule["count"])       # saves and sends the bag (both levels)
        if from_worn == 1 or to_worn == 1:
            refresh_worn(s, state)
        s.send(Writer(S2C_ENCHANT_TRANSFER).u16(0).obool(True))
        log.info("enchant transfer: +%d from %d onto %d for %d Cubic and %d x%d", level, src["code"], dst["code"],
                 rule["cubic"], material, rule["count"])

    @role.on(C2S_UNBIND)
    def unbind(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            log.warning("unbind not understood: %s", b.hex())
            return
        slot, code = struct.unpack_from("<HI", b)
        c = s.data["char"]
        it = next((i for i in c.get("bag", []) if i["slot"] == slot and i["code"] == code), None)
        r = items.row(code) or {}
        cost = items.unbind_cost(code)
        # as the client checks (0x140dd6310): a bound bag item whose BindType is BIND_EQUIP_TIME, not a timed one
        if (it is None or not it.get("bound") or r.get("BindType") != "BIND_EQUIP_TIME"
                or r.get("ItemPeriod") == "REAL_TIME" or not cost):
            log.warning("unbind of %d at bag slot %d refused (%s)", code, slot, it and r.get("BindType"))
            s.send(Writer(S2C_UNBIND).u16(SERVICE_REFUSED))
            return
        if not spend_cubic(s, state, cost):
            s.send(Writer(S2C_UNBIND).u16(CUBIC_SHORT))
            return
        it["bound"] = False
        state.save()
        s.send(Writer(S2C_UNBIND).u16(0))
        send_cargo(s)
        log.info("unbound %d for %d Cubic", code, cost)

    @role.on(C2S_OPTION_REROLL)
    def option_reroll(s, pkt):
        """A random-option reroll (rules census ECONOMY H11): the item's stones (items.reroll_stones) and each lock's
        Cubic (items.option_lock_cost; at most the rarity's %FixAvailable locks, one option left unlocked), then every
        unlocked option rolled again from its own randomoption row; a preview until 0x10d4 applies it."""
        b = pkt.rest()
        if len(b) < 12:
            log.warning("option reroll not understood: %s", b.hex())
            return
        slot, serial, source = obf.dec_u16(b[0:2]), obf.dec_u64(b[2:10]), b[10]
        locked = (obf.T1[b[11]] - 2 * b[2]) & 1
        locks = sorted(set(b[13:13 + b[12]])) if locked and len(b) > 12 else []
        c = s.data["char"]
        pool = hero.equipment(c) if source == 1 else c.get("bag", [])
        it = next((i for i in pool if i.get("serial") == serial), None)
        opts = (it or {}).get("options") or []
        stone, need = items.reroll_stones(it["code"]) if it else (None, 0)
        held = sum(i["count"] for i in c.get("bag", []) if i["code"] == stone) if stone else 0
        cost = items.option_lock_cost(it["code"]) * len(locks) if it else 0
        why = ("no item" if it is None else "no options" if not opts else "stones" if not stone or held < need else
               "locks" if (any(k >= len(opts) for k in locks) or len(locks) >= len(opts)
                           or len(locks) > items.option_locks_allowed(it["code"])) else
               "cubic" if c.get("cubic", 0) < cost else None)
        if why:
            log.warning("option reroll of serial %#x (source %d, slot %d, locks %s) refused: %s", serial, source, slot,
                        locks, why)
            s.send(Writer(S2C_OPTION_REROLL).u16(CUBIC_SHORT if why == "cubic" else OPTION_REFUSED))
            return
        if cost and not spend_cubic(s, state, cost):
            s.send(Writer(S2C_OPTION_REROLL).u16(CUBIC_SHORT))
            return
        remove_item(s, state, stone, need, why="option reroll")
        preview, changed = [list(o) for o in opts], []
        for k, o in enumerate(opts):
            row = items._option_rows().get(str(o[4])) if k not in locks else None
            if row:
                preview[k] = list(items.option_from_row(row, random.randrange))
                changed.append(k)
        s.data["option_preview"] = {"serial": serial, "source": source, "options": preview}
        state.save()
        w = Writer(S2C_OPTION_REROLL).u16(0).u8(len(changed))
        for k in changed:
            w.u8(k).raw(items.option_tail([preview[k]])[1:])
        s.send(w)
        log.info("option reroll of %d: %d stones, %d Cubic, slots %s", it["code"], need, cost, changed)

    @role.on(C2S_OPTION_APPLY)
    def option_apply(s, pkt):
        c = s.data["char"]
        p = s.data.pop("option_preview", None)
        pool = (hero.equipment(c) if p["source"] == 1 else c.get("bag", [])) if p else []
        it = next((i for i in pool if i.get("serial") == p["serial"]), None) if p else None
        if it is None:
            s.send(Writer(S2C_OPTION_APPLY).u16(OPTION_REFUSED))
            return
        it["options"] = p["options"]
        state.save()
        journal("item", ev="options", code=it["code"], name=items.name(it["code"]), options=it["options"])
        s.send(Writer(S2C_OPTION_APPLY).u16(0))
        if p["source"] == 1:
            s.send(equip_one(it))
        else:
            send_cargo(s)

    @role.on(C2S_BAG_EXPAND)
    def bag_expand(s, pkt):
        c = s.data["char"]
        result = expand(s, state, "inven", "bag_slots", bag_slots(c), EXPAND_OPEN_MAX)
        s.send(Writer(S2C_BAG_EXPAND).u16(result))
        if not result:
            send_cargo(s)

    @role.on(C2S_WAREHOUSE_EXPAND)
    def warehouse_expand(s, pkt):
        c = s.data["char"]
        result = expand(s, state, "warehouse", "warehouse_slots", warehouse_slots(c), EXPAND_OPEN_MAX)
        s.send(Writer(S2C_WAREHOUSE_EXPAND).u16(result))
        if not result:
            s.send(warehouse_packet(c, 0))

    @role.on(C2S_BAG_ARRANGE)
    def bag_arrange(s, pkt):
        tab = pkt.u8()
        c = s.data["char"]
        lo, hi = BAG_TABS.get(tab) or (0, bag_slots(c))
        main = sorted((i for i in c.get("bag", []) if lo <= i["slot"] < hi) if tab in BAG_TABS else (),
                      key=lambda i: (i["code"], -i["count"], i["serial"]))
        moved = {}
        for slot, it in enumerate(main, start=lo):
            if it["slot"] != slot:
                moved[it["slot"]] = slot
            it["slot"] = slot
        state.save()
        w = Writer(S2C_BAG_ARRANGE).u16(0).u16(len(main))
        for it in main:
            w.raw(items.record(it["code"], it["slot"], it["serial"], it["count"], items.durability(it),
                               bound=it.get("bound", False), enchant=it.get("enchant", 0), sockets=items.sockets(it), expiry=items.seconds_left(it),
                               options=it.get("options", ())))
        s.send(w)
        pairs = swap_pairs(moved)[:255]
        if pairs:
            w = Writer(S2C_QUICK_BAR_SLOTS).u8(len(pairs))
            for a, b in pairs:
                w.u16(a).u16(b)
            s.send(w)

    @role.on(C2S_OPEN_CHOICE)
    def open_choice(s, pkt):
        b = pkt.rest()
        serial = obf.dec_u64(b[0:8]) if len(b) >= 8 else None
        c = s.data["char"]
        it = bag_item(c, serial)
        if it is None or items.choice_container(it["code"]) is None or item_use_refusal(c, it["code"]):
            log.warning("choice box refused: serial %s (%s)", serial, it and it["code"])
            s.send(Writer(S2C_OPEN_CHOICE).u16(BAG_FULL))
            return
        gold, got = items.open_container(it["code"], random.randrange, items.choice_container)
        got = [(code, n) for code, n in got if n > 0][:255]
        s.data["choice"] = (serial, it["code"], gold, got)
        w = Writer(S2C_OPEN_CHOICE).u16(0).raw(obf.u40(gold)).u16(len(got))
        for code, n in got:
            w.raw(obf.u16(n)).raw(obf.u32(code)).raw(obf.u16(0))
        s.send(w)

    @role.on(C2S_TAKE_CHOICE)
    def take_choice(s, pkt):
        b = pkt.rest()
        pending = s.data.pop("choice", None)
        c = s.data["char"]
        if len(b) < 11 or pending is None or pending[0] != obf.dec_u64(b[1:9]) or bag_item(c, pending[0]) is None:
            s.send(Writer(S2C_TAKE_CHOICE).u16(BAG_FULL))
            return
        serial, code, gold, got = pending
        index = obf.dec_u16(b[9:11])
        if not 0 <= index < len(got):
            s.send(Writer(S2C_TAKE_CHOICE).u16(BAG_FULL))
            return
        item, n = got[index]
        it = bag_item(c, serial)
        if it["code"] != code or item_use_refusal(c, code):
            s.send(Writer(S2C_TAKE_CHOICE).u16(BAG_FULL))
            return
        if not fits(c, [(item, n)], it["slot"] if it["count"] == 1 else None):
            s.send(Writer(S2C_TAKE_CHOICE).u16(CHOICE_BAG_FULL))
            return
        take_serial(c, serial, 1)
        count_item_day(c, code)
        change_gold(c, gold)
        add_item(s, state, item, n)
        s.send(Writer(S2C_TAKE_CHOICE).u16(0))
        log.info("choice box %d: took %d x%d (gold %d)", code, item, n, gold)

    @role.on(C2S_HERO_DETAIL)
    def hero_detail(s, pkt):
        send_hero_detail(s)

    @role.on(C2S_GROUP_LOGIN)
    def group_login(s, pkt):
        acct_id = pkt.u32()
        build = pkt.u32()
        service = pkt.u32()
        flag = pkt.u8()
        acct = state.account_by_id(acct_id)
        s.data["account"] = acct
        log.info("world login account=%d build=0x%x service=%d flag=%d", acct_id, build, service, flag)
        w = Writer(S2C_GROUP_LOGIN_RES)
        w.u16(0).zeros(8)
        # 33-byte struct (offsets as the handler reads them)
        w.u8(0)                 # +0x00
        w.u32(0)                # +0x01 int -> 0x140675170
        w.u32(0)                # +0x05
        w.u32(acct["id"])       # +0x09 user id (stored in the local player info)
        w.u8(settings.get("CharSlotMax"))    # +0x0d -> player info +0x39 (no reader found; 6 as before)
        w.u8(open_char_slots(acct))         # +0x0e -> +0x18: the open character slots
        now = int(time.time())
        w.raw(obf.time64(now))  # +0x0f the server clock (Unix seconds): the time manager (common+0xb8, setter
        w.raw(obf.time64(now))  # +0x17 0x140674dc0) runs from it; with 0 the client's date was January 1970
        w.u8(0)                 # +0x1f table-decoded byte
        w.obool(False)          # +0x20 false -> character select (sub-state 4); true -> sub-state 5
        s.send(w)

    @role.on(C2S_CHAR_LIST)
    def char_list(s, pkt):
        nonce = pkt.u8()
        chars = s.data["account"]["characters"]
        log.info("char list request nonce=0x%02x -> %d characters", nonce, len(chars))
        w = Writer(S2C_CHAR_LIST)
        w.u8(0)                 # compared against a player-info byte (selected slot?)
        w.u8(len(chars))
        for c in chars:
            write_char_entry(w, c)
        s.send(w)

    def name_taken(name):
        return any(ch["name"] == name for a in state.db["accounts"].values() for ch in a["characters"])

    @role.on(C2S_CHAR_CREATE)
    def char_create(s, pkt):
        name = pkt.cstr()
        look = pkt.take(56)
        cls = struct.unpack_from("<I", look, 0x34)[0]
        acct = s.data["account"]
        if name_taken(name):                    # 0x100c 0x1404 -> text 77 (0x140e62c40, session_lobby.md §3)
            log.info("char create name=%r refused: taken", name)
            s.send(Writer(S2C_CHAR_CREATE_RES).u16(NAME_TAKEN))
            return
        c = state.create_character(acct, name, cls, look.hex())
        c["spot"], c["pos"] = NEW_CHAR_SPOT, list(TOWN_ENTRY[NEW_CHAR_SPOT])     # where the prologue hands over
        c["tutorial_done"] = not PROLOGUE_FOR_NEW_CHARACTERS     # False: the prologue first (start_game)
        c["bag_slots"] = CARGO_SLOTS                    # the client's base; keep_old_bag leaves it
        give_starter_bag(c)
        seat_skills(c, skills.bar_skills(c))           # the class's level-1 skills on the hero bar, keys 1 and 2
        state.save()
        log.info("char create name=%r class=%d id=%d look=%s", name, cls, c["id"], look.hex())
        w = Writer(S2C_CHAR_CREATE_RES)
        w.u16(0).u32(c["id"])
        s.send(w)

    @role.on(C2S_CHAR_DELETE)
    def char_delete(s, pkt):
        delete = obf.T1[pkt.u8()] & 1            # T2[flag + 2k] with a random k (0x140e78740)
        char_id = pkt.u32()
        acct = s.data["account"]
        c = next((ch for ch in acct["characters"] if ch["id"] == char_id), None)
        result = 0
        if not delete:
            pass                                 # deletion is immediate offline: nothing is pending
        elif c is None:
            result = 1                           # "Failed to delete the character."
        else:
            acct["characters"].remove(c)
            acct.setdefault("deleted", []).append(c)     # kept in the save file, not shown
            state.save()
        log.info("char %s %d: result %d", "delete" if delete else "cancel deletion", char_id, result)
        s.send(Writer(S2C_CHAR_DELETE).obool(bool(delete)).u32(char_id).u16(result).u64(0))

    @role.on(C2S_NAME_CHECK)
    def name_check(s, pkt):
        name = pkt.cstr()
        s.send(Writer(S2C_NAME_CHECK).u16(NAME_TAKEN if name_taken(name) else 0))

    @role.on(C2S_TO_LOBBY)
    def to_lobby(s, pkt):
        from . import game
        c = s.data.get("char")
        if c is not None:
            room = getattr(state, "game_sessions", {}).pop(s.data["account"]["id"], None)
            if room is not None:            # the Esc menu's CurrentStateExit from a mission: an abort, as MissionExit's
                game.deck_aborted(s, state, room)    # (the saved spot is still the field it was entered from)
        state.save()
        s.data.pop("char", None)
        s.send(Writer(S2C_TO_LOBBY))

    @role.on(C2S_PROLOGUE_DONE)
    def prologue_done(s, pkt):
        c = s.data["char"]
        c["tutorial_done"] = True
        if (c.get("mission") or {}).get("spot") == TUTORIAL_SPOT:    # left by the system menu's "End the tutorial?"
            c.pop("mission")                                         # (warp 205): its way out is spent
        state.save()

    @role.on(C2S_GUIDE_SEEN)
    def guide_seen(s, pkt):
        """A first-time hint was shown: kept so the next start game (Q bits) does not show it again."""
        b, c = pkt.rest(), s.data.get("char")
        if not b or c is None:
            log.warning("guide seen without a character or id: %s", b.hex())
            return
        k = b[0]
        seen = c.setdefault("guides", [])
        if k < 0x80 and k not in seen:
            seen.append(k)
            state.save()
        log.info("guide %d seen%s", k, "" if k < 0x80 else " (not carried back: 0x1012 holds types below 0x80)")

    @role.on(C2S_OPTIONS)
    def options_save(s, pkt):
        b = pkt.rest()
        opts = s.data["char"].setdefault("options", {})
        for i in range(min(b[0] if b else 0, (len(b) - 1) // 2)):
            value, index = b[1 + 2 * i], b[2 + 2 * i]
            if index < 0x26:
                opts[str(index)] = value
        state.save()

    @role.on(C2S_ESCAPE)
    def escape(s, pkt):
        b = pkt.rest()[:12]
        if len(b) < 12:
            log.warning("escape not understood: %s", b.hex())
            return
        if b[11] == 2:
            x, z = obf.dec_pos_xz(b[0:4], b[6])
            s.data["char"]["pos"] = [x, struct.unpack_from("<h", b, 4)[0], z]
            state.save()
        s.send(Writer(S2C_ESCAPE).u16(0).raw(b))

    @role.on(C2S_BAG_TAB)
    def bag_tab(s, pkt):
        # every grant goes to the main bag (slots < bag_slots(c)), so the extra tabs hold nothing to move
        s.send(Writer(S2C_BAG_TAB).u8(0).u16(0))
        send_cargo(s)

    @role.on(C2S_OPEN_GACHA)
    def open_gacha(s, pkt):
        slot = pkt.u16()
        c = s.data["char"]
        it = next((i for i in c.get("bag", []) if i["slot"] == slot), None)
        if it is not None and item_use_refusal(c, it["code"]):
            s.send(Writer(S2C_OPEN_GACHA).u16(BAG_FULL))
            return
        got = items.open_gacha(it["code"], random.randrange) if it else None
        if got is None:
            log.warning("gacha at bag slot %d refused (%s)", slot, it and it["code"])
            s.send(Writer(S2C_OPEN_GACHA).u16(BAG_FULL if it else 1))
            return
        code, n = got
        if not fits(c, [(code, n)], slot if it["count"] == 1 else None):
            s.send(Writer(S2C_OPEN_GACHA).u16(BAG_FULL))
            return
        take_serial(c, it["serial"], 1)
        count_item_day(c, it["code"])
        add_item(s, state, code, n)            # saves and sends the bag before the reply ("open all" reads it)
        s.send(Writer(S2C_OPEN_GACHA).u16(0).u32(code).u16(n))
        log.info("gacha %d opened: %d x%d", it["code"], code, n)

    @role.on(C2S_ATTACK_REFRESH)
    def attack_refresh(s, pkt):
        c = s.data["char"]
        st = hero.char_stats(c)
        for kind, name in ((0, "ATTACK_PHYSICAL"), (1, "ATTACK_MAGICAL")):
            s.send(Writer(S2C_ATTACK_REFRESH).obool(True).obool(kind == 1).u32(round(st.get(name + "_MAX", 0) * 10))
                   .u64(c["id"]).u32(round(st.get(name + "_MIN", 0) * 10)))

    @role.on(C2S_START_GAME)
    def start_game(s, pkt):
        char_id = pkt.u32()
        flag = pkt.u8()
        acct = s.data["account"]
        c = next((ch for ch in acct["characters"] if ch["id"] == char_id), None)
        if c is None:                                   # refused: without a 0x1012 every select button stays dead
            log.warning("start game: no character %d", char_id)
            s.send(Writer(S2C_START_GAME_RES).u16(START_REFUSED).raw(bytes(37 + 32)))
            return
        s.data["char"] = c
        getattr(state, "world_sessions", {})[acct.get("id")] = s     # a room's win may send the client on (continue_mission)
        s.data.pop("cooldowns_sent", None)            # this character's cooldowns go with its first quick-bar page
        if normalize_bag(c):                          # items from before the bag ranges: into their own tab
            state.save()
        if troops.give_default_skills(c):             # troops from before troops came with skills: theirs now
            state.save()
        if replace_made_up_kit(c):                    # the made-up kit of saves from before hero.starter_kit
            state.save()
        if raise_auto_skills(c):                      # AutoLearn rows held at 1 by saves from before skills.auto_level
            state.save()
        if "quick_slots" not in c:                    # never touched the bar (a save from before it was seeded): what
            seat_skills(c, skills.bar_skills(c))      # it would hold by this level, kept by the next save (as "mission")
        if keep_old_bag(c):                           # saves from when 48 bag slots opened keep them
            log.info("char %d keeps its %d bag slots", c["id"], OLD_BAG_SLOTS)
            state.save()
        if stamp_timed(c):                            # timed items from before the expiry rule: their period starts
            state.save()
        if quest.collect_leftovers(c):                # finished quests' collected items, once (owner E9 (a))
            state.save()
        if items.roll_missing_options(c, random.randrange):   # gear from before random options: theirs now (H11)
            state.save()
        expire_items(s, state, notify=False)          # what ran out while offline goes before the lists are sent
        arm_expiry(s, state)
        tutorial, spot, (x, y, z) = login_point(c)    # the prologue only for a character created for it
        log.info("start game char=%d %r spot=%d pos=(%d,%d,%d) flag=0x%02x", char_id, c["name"], spot, x, y, z, flag)
        journal("char", id=char_id, name=c["name"], spot=spot, pos=[x, y, z], level=c.get("level", 1),
                exp=c.get("exp", 0), need=hero_need(c.get("level", 1)), gold=c.get("gold", 0), quests=quest.held(c))
        w = Writer(S2C_START_GAME_RES)
        w.u16(0)
        # P: 37 bytes (handler @ 0x140e79030)
        p = bytearray(0x25)
        p[0x00] = c.get("realm", 0)                   # the realm (plain, -> common+0xd0, re/start.c:332): 1 A, 2 B;
                                                      # a relog kept it 0 (realm quests, guild create refused)
        struct.pack_into("<q", p, 0x01, c.get("exp", 0))  # exp within the level -> PlayerInfo +0x18 (common+0xe8,
                                                          # the HUD exp bar and tooltip read it)
        p[0x09] = 0                                   # 1 = no spot
        p[0x0a] = 0 if tutorial else 1                # obool: true -> client keeps spot/+0x20/+0x16 for 0x3763
        p[0x0b:0x0f] = obf.u32(spot)
        q, p15 = obf.pos_xz(x, z)
        p[0x0f:0x13] = q
        struct.pack_into("<h", p, 0x13, y)
        p[0x15] = p15
        p[0x24] = 1                                   # obool false
        w.raw(bytes(p))
        # Q: 32 bytes
        qd = bytearray(0x20)
        qd[0x01] = hero_max_level()                   # plain u8 -> PlayerInfo +0x31 (common+0x101): the exp bar
                                                      # (0x140769640) fills only while level < this
        for at, first in zip(GUIDE_BITS_AT, (0, 0x40)):   # the guides this character has seen (0x101b)
            struct.pack_into("<Q", qd, at, sum(1 << (k - first) for k in c.get("guides", []) if first <= k < first + 64))
        qd[0x12] = 1                                  # obool false (-> guide object +8)
        w.raw(bytes(qd))
        s.send(w)
        if c.get("cubic"):
            s.send(cubic_packet(c))            # after 0x1012, before the first bag window (pushes_common.md 0x375d)
        from . import game
        s.send(game.free_revives_packet(c))    # the day's free resurrections (0x1089, census ECONOMY J5)
        diary.send_diary(s)                    # before the HUD init decides whether to open the calendar
        opts = sorted((int(k), v) for k, v in c.get("options", {}).items())
        w = Writer(S2C_OPTIONS).u8(len(opts))
        for index, value in opts:
            w.u8(value).u8(index)
        s.send(w)                              # none saved yet: the client uploads its own (0x10b0)
        s.send(craft.state_packet(c))          # craft levels, exp and favourites (0x10e1)
        s.send(craft.running_packet(c))        # crafts in progress or waiting to be received (0x10e2)
        s.send(skills.reset_count_packet(c))   # the skill-reset count that prices the next reset (0x1114)
        for w in daily.list_packets(c):        # today's daily tasks and the rewards taken (0x5600, 0x5601)
            s.send(w)
        for w in titles.login_packets(c):      # titles, achievement counters, vehicles (0x10f0, 0x10f2, 0x10f3)
            s.send(w)
        s.send(spot_schedule_packet())         # when the time-limited spots open (0x4078)
        if tutorial:
            # new character: straight into the first mission (lobby handler @ 0x140e79d70: u16 result;
            # sets the solo-mission flag GameStateManager+0x114 and switches state)
            s.send(Writer(S2C_ENTER_TUTORIAL).u16(0))
            # its way out: Glen's camp (game.leave_mission at its win, no window; the system menu's "End the
            # tutorial?" is warp 205, the same camp, group 1)
            c["mission"] = {"spot": TUTORIAL_SPOT, "back": NEW_CHAR_SPOT, "difficulty": 0}
            # the solo loading waits for BattleField+0x98 (the spot from the 0x3f4e room-start header,
            # 0x140d09380): point the client at the game role, which sends the room start on login
            send_game_server(s, spot, game_host, game_port)
        else:
            # move the client into the town (handler @ 0x140cc0b20 -> game state 2)
            send_prepare_enter_town(s, spot, (x, y, z))

    return role


def spot_schedule_packet():
    """S2C 0x4078 at start game: the opening days and hours of the time-limited spots, one record per spottable
    %SpotSchedule row (20: the Unknown Corridor dailies 10540-10546, the Colonock invasions 20908-20914). The client
    keeps them in a map at common+0x1738 (replaced whole) and `0x140d65b50` opens a spot that has a SpotSchedule row
    only while an entry has today's weekday bit and open <= hour < close (tm_hour / tm_wday of 0x141b9ef60, a gmtime
    of the server clock: UTC unless the 0x1003 +0x01 offset shifts it, not pinned); without it those spots stay closed
    for good (planning/requests/pushes_common.md 0x4078). A short body with n > 0 would crash: n always matches."""
    rows = tables.sections("spottable")["SpotSchedule"]
    w = Writer(S2C_SPOT_SCHEDULE).u16(len(rows))
    for r in rows:
        mask = sum(bit for day, bit in WEEKDAY_BIT.items() if r[day] == "True")
        w.u8(mask).raw(obf.u32(int(r["SpotID"]))).u8(int(r["SpotCloseHour"])).u8(int(r["SpotOpenHour"]))
    return w


def cleared_packet(c):
    """S2C 0x108f (0x140675a10, into GamePlayInfo common[0x17] +8, replaced whole): u16 n, n * 10 bytes: u16 Normal
    clears, coded u32 spot, u16 Hell clears, u16 Hard clears (the map value's three ints, indexed by the difficulty in
    0x140674bb0: wire +0, +8, +6). The spots the character has won (game.record_clear); the client's SpotClear entry
    requirement looks the spot up there."""
    rows = sorted((int(k), v) for k, v in c.get("cleared", {}).items())
    w = Writer(S2C_CLEARED).u16(len(rows))
    for spot, (normal, hard, hell) in rows:
        w.u16(normal).raw(obf.u32(spot)).u16(hell).u16(hard)
    return w


def send_prepare_enter_town(s, spot, pos):
    """S2C 0x3745 (0x140cc0b20): u16 result, u32 spot, packed x/z, i16 y, nibble byte -> the client loads the town
    or field and continues with 0x3746."""
    x, y, z = pos
    q, p15 = obf.pos_xz(x, z)
    s.send(Writer(S2C_PREPARE_ENTER_TOWN).u16(0).u32(spot).raw(q).raw(struct.pack("<h", y)).u8(p15))


S2C_CUBIC = 0x375d              # the Cubic balance (0x140d6e790): coded u32 -> common+0x118 (bag line, shops, services)


def cubic_packet(c):
    return Writer(S2C_CUBIC).raw(obf.u32(c.get("cubic", 0)))


def spend_cubic(s, state, amount):
    """Take `amount` from the character's Cubic balance, save and push the new balance (0x375d). False, with nothing
    changed, when the balance is short: the caller answers its own 0x6430 (UI-WIRING.md, the shared helper)."""
    c = s.data["char"]
    if amount < 0 or c.get("cubic", 0) < amount:
        return False
    c["cubic"] = c.get("cubic", 0) - amount
    state.save()
    s.send(cubic_packet(c))
    return True


def expand(s, state, kind, key, have, limit=None):
    """A Cubic expansion (bag 0x10a6, warehouse 0x10a8, barracks 0x10aa): the next items.expansion row at `have` open
    slots, paid with spend_cubic, adds its slots to c[key]. Returns the reply code: 0, CUBIC_SHORT, or SERVICE_REFUSED
    at the window's limit or when nothing is left to sell (text 0xd01d)."""
    c = s.data["char"]
    row = items.expansion(kind, have) if limit is None or have < limit else None
    if row is None:
        return SERVICE_REFUSED
    cost, added = row
    if not spend_cubic(s, state, cost):
        return CUBIC_SHORT
    c[key] = have + added
    state.save()
    log.info("%s expanded to %d for %d Cubic", kind, c[key], cost)
    return 0


def quick_bar_packet(c):
    """0x1763 success: the quick-bar expansions bought (the reply to 0x1762, and unsolicited at login)."""
    return Writer(S2C_QUICK_BAR_EXPAND).u16(0).u8(c.get("quick_bar_expansions", 0) + QUICK_BAR_BASE).u8(0)


def day_uses(c, now=None):
    """{item code: uses} of items with a DayLimit today (the game day, 07:00 UTC: rules.game_day; census L6)."""
    today = rules.game_day(now)
    if c.get("day_uses", {}).get("day") != today:
        c["day_uses"] = {"day": today, "counts": {}}
    return c["day_uses"]["counts"]


def item_use_refusal(c, code, n=1, now=None):
    """Table requirements, shared cooldown and daily quota, without mutating a rejected request's save.

    DayLimit is separate from the client's NumberOfUse (+0x268); see VANILLA-ITEMS.md native row evidence.
    Battle-only checks belong to the world handler because they need the active game session.
    """
    r = items.row(code) or {}
    num = lambda k: int(r[k]) if str(r.get(k, "")).isdigit() else 0
    now = time.time() if now is None else now
    if not r or n < 1:
        return ITEM_USE_REFUSED
    if c.get("level", 1) < num("ReqLevel"):
        return ITEM_USE_LEVEL
    if num("ReqLevelMax") and c.get("level", 1) > num("ReqLevelMax"):
        return ITEM_USE_REFUSED
    if r.get("ReqHero", "NONE") not in ("NONE", "ALL", "-", "", hero.HERO_CODE[c["class"]]):
        return ITEM_USE_REFUSED
    cooldown = c.get("cooldowns", {}).get(str(r.get("CoolTimeGroupId")))
    if cooldown and cooldown[1] > now:
        return ITEM_USE_REFUSED
    day = c.get("day_uses", {})
    used = day.get("counts", {}).get(str(code), 0) if day.get("day") == rules.game_day(now) else 0
    if num("DayLimit") and used + n > num("DayLimit"):
        return ITEM_USE_REFUSED
    return 0


def count_item_day(c, code, n=1):
    """Spend a DayLimit quota on a successful use/claim, never on its preview."""
    limit = str((items.row(code) or {}).get("DayLimit", ""))
    if limit.isdigit() and int(limit) > 0:
        uses = day_uses(c)
        uses[str(code)] = uses.get(str(code), 0) + n


def use_reply(c, code, n=1):
    """0x4043 for a used item (the client starts its cooldown from it), after keeping what 0x125a gives back at the next
    login: the cooldown group's end (CoolTime in seconds). The separate DayLimit quota stays in the save."""
    r = items.row(code) or {}
    group, cool = r.get("CoolTimeGroupId", ""), r.get("CoolTime", "")
    if group.isdigit() and cool.isdigit() and int(cool) > 0:
        c.setdefault("cooldowns", {})[group] = [code, time.time() + int(cool)]
    count_item_day(c, code, n)
    journal("item", ev="use", code=code, name=items.name(code), n=n, kind=r.get("ConsumeItemType"))
    return Writer(S2C_USE_ITEM).u16(0).raw(obf.u32(code)).raw(bytes(4))


def cooldown_packet(c):
    """0x125a: running cooldowns. Its second list is NumberOfUse, not DayLimit (native rows, 2026-10-01).

    The two guild consumables with NumberOfUse are unsupported; none of the supported uses belongs in that list.
    """
    now = time.time()
    live = {g: v for g, v in c.get("cooldowns", {}).items() if v[1] > now}
    w = Writer(S2C_COOLDOWNS).u16(len(live))
    for code, end in live.values():
        cool = str((items.row(code) or {}).get("CoolTime", ""))
        w.raw(obf.u32(code)).i32(min(int(cool) if cool.isdigit() else 0, math.ceil(end - now)))
    w.u16(0)
    return w


def bag_slots(c):
    """The character's open main-bag slots: CARGO_SLOTS, plus what Cubic expansions added (0x10a6)."""
    return c.get("bag_slots", CARGO_SLOTS)


def keep_old_bag(c):
    """A save from before the client's base (created without c["bag_slots"]) keeps the OLD_BAG_SLOTS it had, as two
    expansions bought, so nothing is left in a shut slot; whether it changed. New characters get CARGO_SLOTS at
    creation."""
    if "bag_slots" in c:
        return False
    c["bag_slots"] = OLD_BAG_SLOTS
    return True


def warehouse_slots(c):
    return c.get("warehouse_slots", WAREHOUSE_SLOTS)


def rebuy_packet(c):
    """Restore the merchant's cache on entry as well as on explicit1665 requests."""
    rebuy = c.get("buyback", [])
    w = Writer(S2C_REBUY_LIST).u8(len(rebuy))
    for i, e in enumerate(rebuy):
        w.raw(items.record(e["code"], i, e["serial"] or 0, e["count"], items.durability(e),
                           bound=e["bound"], enchant=e.get("enchant", 0), sockets=items.sockets(e),
                           expiry=items.seconds_left(e), options=e.get("options", ())))
    return w


def send_cargo(s, *, changed_slots=()):
    """The bag: the character's gold, open slots (bag_slots) and its items. The client clears all 0x500 slots before
    placing the list (0x140dce7d0). For a mutation, redraw its changed slots before replacing the data."""
    if changed_slots:
        send_cargo_change(s, changed_slots)
    c = s.data["char"]
    bag = c.get("bag", [])
    w = Writer(S2C_CARGO).raw(obf.u40(c.get("gold", 0))).u16(bag_slots(c)).u16(len(bag))
    for it in bag:
        w.raw(items.record(it["code"], it["slot"], it["serial"], it["count"], items.durability(it),
                           bound=it.get("bound", False), enchant=it.get("enchant", 0), sockets=items.sockets(it), expiry=items.seconds_left(it),
                               options=it.get("options", ())))
    s.send(w)


def send_cargo_change(s, slots):
    """Refresh changed bag slots; an absent item clears its previously occupied native slot.

    Call before send_cargo, since the removal handler needs the previous native item.
    """
    bag = {it["slot"]: it for it in s.data["char"].get("bag", [])}
    w = Writer(S2C_CARGO_CHANGE).u16(len(slots))
    for slot in slots:
        it = bag.get(slot, {"code": 0xffffffff, "slot": slot, "serial": 0, "count": 0})
        w.raw(items.record(it["code"], it["slot"], it["serial"], it["count"], items.durability(it),
                           bound=it.get("bound", False), enchant=it.get("enchant", 0), sockets=items.sockets(it),
                           expiry=items.seconds_left(it), options=it.get("options", ())))
    s.send(w)


def warehouse_packet(c, tab):
    """0x1641 for a warehouse tab: the character's warehouse on tab 0; tab 1 (asserted as the last) is empty."""
    kept = c.get("warehouse", []) if tab == 0 else []
    w = Writer(S2C_WAREHOUSE_LIST).u8(tab).u16(warehouse_slots(c)).raw(obf.u40(c.get("warehouse_gold", 0)))
    w.u16(len(kept))
    for it in kept:
        w.raw(items.record(it["code"], it["slot"], it["serial"], it["count"], items.durability(it),
                           bound=it.get("bound", False), enchant=it.get("enchant", 0), sockets=items.sockets(it), expiry=items.seconds_left(it),
                               options=it.get("options", ())))
    return w


def box_slots(c, box):
    return bag_slots(c) if box == "bag" else warehouse_slots(c)


def held_item(c, worn, slot, serial):
    """An item by the enchant windows' address: the equipped one at equipment index `slot` (worn), else the bag's at
    bag slot `slot`; its serial must match. None when it is not there."""
    if worn:
        return next((e for e in hero.equipment(c) if e["index"] == slot and e["serial"] == serial), None)
    it = bag_item(c, serial)
    return it if it and it["slot"] == slot else None


def refresh_worn(s, state):
    """A worn item changed its numbers: the hero record (0x134b), and in a room the hero's own stats there."""
    send_hero_detail(s)
    g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
    if g is not None and "battle" in g.data and not g.w.is_closing():
        from . import game
        game.room_stats(g, s.data["char"])


def box_item(c, box, serial):
    return next((it for it in c.get(box, []) if it.get("serial") == serial), None)


def move_stack(c, src_box, dst_box, serial, src_slot, dst_slot, n, dst_serial=None):
    """Move n of stack `serial` (at src_slot of the character's "bag" or "warehouse") to dst_slot of the same or the
    other box: into an empty slot (a new serial when only part of it moves), onto the same item up to its MaxStack,
    or, a whole stack onto a different item, a swap. dst_serial is the target the client saw (0 = empty), checked
    even when now empty. Returns False, with nothing changed, when the request does not fit the boxes."""
    src, dst = c.get(src_box, []), c.get(dst_box, [])
    it = box_item(c, src_box, serial)
    there = next((i for i in dst if i["slot"] == dst_slot), None)
    def allowed(box, code, slot):
        return slot_ok(c, code, slot) if box == "bag" else 0 <= slot < warehouse_slots(c)
    if (it is None or it["slot"] != src_slot or not 1 <= n <= it["count"]
            or not allowed(dst_box, it["code"], dst_slot) or there is it
            or (dst_serial is not None and (there["serial"] if there else 0) != dst_serial)):
        return False
    if there is None and n == it["count"]:
        src.remove(it)
        it["slot"] = dst_slot
        c.setdefault(dst_box, []).append(it)
    elif there is None:
        split = {**deepcopy(it), "slot": dst_slot, "count": n, "serial": serials.allocate(c)}
        c.setdefault(dst_box, []).append(split)
        it["count"] -= n
    elif items.can_stack(there, it) and there["count"] + n <= items.max_stack(it["code"]):
        there["count"] += n
        it["count"] -= n
        if not it["count"]:
            src.remove(it)
    elif n == it["count"] and allowed(src_box, there["code"], src_slot):
        src.remove(it)
        dst.remove(there)
        it["slot"], there["slot"] = dst_slot, src_slot
        dst.append(it)
        src.append(there)
    else:
        return False
    return True


def box_transfer(s, state, b, src_box, dst_box, reply):
    """0x1642 / 0x1644: the stack (or the count picked) between the bag and the warehouse; both lists follow, so the
    client holds the serials the server gave."""
    if len(b) < 22:
        log.warning("%s -> %s not understood: %s", src_box, dst_box, b.hex())
        return
    serial, dst_slot, dst_serial = obf.dec_u64(b[0:8]), obf.dec_u16(b[8:10]), obf.dec_u64(b[10:18])
    n, src_slot = obf.dec_u16(b[18:20]), obf.dec_u16(b[20:22])
    c = s.data["char"]
    if not move_stack(c, src_box, dst_box, serial, src_slot, dst_slot, n, dst_serial):
        log.warning("%s -> %s refused: %d of serial %#x at %d -> %d (target %#x)", src_box, dst_box, n, serial,
                    src_slot, dst_slot, dst_serial)
        s.send(Writer(reply).u16(WAREHOUSE_REFUSED))
        return
    state.save()
    s.send(Writer(reply).u16(0))
    s.send(warehouse_packet(c, 0))
    send_cargo(s)


HERO_BAR_KEYS = 8                       # slots per hero bar row: keys 1-8 = slot bytes 0-7 (type 0, group 0; the live
                                        # 0x1740 for key 1 carried slot 0), the lower row 100-107 (skills.bar_row)


def seat_skills(c, ids):
    """Put each hero skill of ids that is not on the hero bar yet on the first free slot of its row (type 0, group 0;
    skills.bar_row: slots 0-7, or 100-107 for a tactics skill), as the original's server did with a skill the hero
    learned (skills.bar_skills: keys 1 and 2 at creation, key 3 at Lv.2, Supplement on the lower row at Lv.6, key 4
    at Lv.8 on the tape); a full row takes no more. The client shows it from the next 0x1747 page 0: asked for (0x1746
    x9 on entering the prologue's battle field, the city or a field: 0x140d9b2c0) or pushed (add_exp); the entry's
    slot byte goes to the HUD as it is (0x1408eee00 keys the page map by it, 0x1408ea370 passes it to 0x140e0dae0), so
    slot 100 is the lower row's first. Returns the ids seated."""
    slots = c.setdefault("quick_slots", {})
    held = {e["id"] for k, e in slots.items() if e.get("kind") == 1 and k.startswith("0:0:")}
    seated = []
    for aid in ids:
        row = skills.bar_row(c, aid)
        free = next((n for n in range(row, row + HERO_BAR_KEYS) if f"0:0:{n}" not in slots), None)
        if aid in held or free is None:
            continue
        slots[f"0:0:{free}"] = {"kind": 1, "id": aid, "bag": skills.handle(c, aid)}
        held.add(aid)
        seated.append(aid)
    return seated


def quick_slot_page_packet(c, page):
    """0x1747 for a page, from the character's registered quick slots: page 0 = the type-0 list then the type-2 list
    (u8 n, n * (u64 hero uid, entry)); pages 1..8 = u64 hero uid, u8 n, n * entry. Entry (0x1408f1450 / 0x1408f1330,
    applied by 0x1408eee00): u8 kind, u8 bar slot, i16 bag slot, then kind 0 a coded u32 item code, else u32 id + u8.
    An item's bag slot is taken from the bag now (the item may have moved since it was placed)."""
    slots = c.get("quick_slots", {})

    def entries(kind_type, group):
        out = []
        for key, e in sorted(slots.items()):
            t, g, slot = (int(x) for x in key.split(":"))
            if t != kind_type or g != group:
                continue
            bag = e["bag"]
            if e["kind"] == 0:
                held = next((i for i in c.get("bag", []) if i["code"] == e["id"]), None)
                if held is None:
                    continue                    # used up: the slot is dropped
                bag = held["slot"]
            if e["kind"] == 1:                  # a hero skill: its current handle and level
                bag = skills.handle(c, e["id"])
                level = skills.hero_skills(c).get(e["id"], 1)
            else:
                level = 1
            tail = obf.u32(e["id"]) if e["kind"] == 0 else struct.pack("<IB", e["id"], level)
            out.append(bytes([e["kind"], slot]) + struct.pack("<h", bag) + tail)
        return out

    w = Writer(S2C_QUICK_SLOT_PAGE).u8(page)
    if page == 0:
        for kind_type in (0, 2):
            es = entries(kind_type, 0)
            w.u8(len(es))
            for e in es:
                w.u64(c["id"]).raw(e)
    else:
        es = entries(1, page)
        w.u64(c["id"]).u8(len(es))
        for e in es:
            w.raw(e)
    return w


def bag_item(c, serial):
    """The bag record with this serial, or None."""
    return next((it for it in c.get("bag", []) if it.get("serial") == serial), None)


def take_serial(c, serial, n):
    """Take n from the bag record with this serial (removed when it reaches 0)."""
    it = bag_item(c, serial)
    it["count"] -= n
    if it["count"] <= 0:
        c["bag"].remove(it)


BAG_TABS = {0: None, 1: (0x40, 0x50), 2: (0x50, 0x60), 3: (0x60, 0x70), 4: (0x70, 0x80), 5: (0x80, 0xc0),
            8: (0xc0, 0x100), 6: (0x100, 0x500)}   # arrange tab -> its slots (None: the main bag), the 0x1662
                                                   # handler's switch 0x140dd0be0 (planning/client/items_troops_skills.md;
                                                   # the old 3 / 7 / 5 blanked the quest, stone and costume tabs)


def bag_range(c, code):
    return items.bag_range(code, bag_slots(c))


def slot_ok(c, code, slot):
    lo, hi = bag_range(c, code)
    return lo <= slot < hi


def free_slots(c, code, freed=None):
    """Free slots in the range item `code` lives in (freed: a slot about to empty)."""
    lo, hi = bag_range(c, code)
    used = {i["slot"] for i in c.get("bag", []) if lo <= i["slot"] < hi} - ({freed} if freed is not None else set())
    return (hi - lo) - len(used)


def fits(c, got, freed=None):
    """Whether all rewards fit, accounting for MaxStack, shared ranges and partial stacks.

    freed is a slot consumed by this transaction; it cannot also supply stack capacity.
    Uses the same attribute compatibility as add_item, without changing the bag.
    """
    totals = {}
    for code, n in got:
        if n < 0:
            return False
        totals[code] = totals.get(code, 0) + n
    need = {}
    bag = [i for i in c.get("bag", []) if i["slot"] != freed]
    for code, n in totals.items():
        cap = items.max_stack(code)
        gained = {"code": code, "bound": items.bound_on_gain(code)}
        room = sum(max(0, cap - i["count"]) for i in bag if items.can_stack(i, gained))
        rng = bag_range(c, code)
        need[rng] = need.get(rng, 0) + (max(0, n - room) + cap - 1) // cap
    return all(n <= hi - lo - len({i["slot"] for i in bag if lo <= i["slot"] < hi})
               for (lo, hi), n in need.items())


def normalize_bag(c):
    """Items granted before the bag ranges were known sit in the main bag; the client looks for a quest item, a troop
    stone or a costume only in its own range, so each moves to the first free slot there (returns the count moved)."""
    moved = 0
    for it in c.get("bag", []):
        lo, hi = bag_range(c, it["code"])
        if not lo <= it["slot"] < hi:
            used = {i["slot"] for i in c["bag"]}
            free = next((k for k in range(lo, hi) if k not in used), None)
            if free is not None:
                it["slot"] = free
                moved += 1
    return moved


def replace_made_up_kit(c):
    """hero.replace_made_up_kit at login, logged and journaled ("gear": what went, what came, HP before and after);
    whether anything changed."""
    hp = lambda: round(hero.char_stats(c)["HP_MAX"])                                                    # noqa: E731
    before = hp()
    changes = hero.replace_made_up_kit(c)
    if changes:
        log.info("gear: %r's made-up kit replaced by the original set (where, at, old, new): %s; HP %d -> %d",
                 c.get("name"), changes, before, hp())
        journal("gear", id=c["id"], name=c.get("name"), replaced=changes, hp=[before, hp()])
    return bool(changes)


def raise_auto_skills(c):
    """skills.record_auto at login (rules census HERO L9, decision A4: saves from before gain their levels at the next
    login), logged and journaled ("skill", ev "login": each row's level before and after, HP before and after); whether
    anything changed. A second login changes nothing."""
    changes = skills.record_auto(c)
    if not changes:
        return False
    held = skills.battle_abilities(c)
    hp = lambda held: round(hero.char_stats(c, held)["HP_MAX"])                                        # noqa: E731
    before, after = hp({**held, **{a: old for a, old, _ in changes}}), hp(held)
    log.info("hero skills: %r's AutoLearn rows raised to the level's (id, before, after): %s; HP %d -> %d",
             c.get("name"), changes, before, after)
    journal("skill", ev="login", id=c["id"], name=c.get("name"), level=c.get("level", 1),
            levels=[list(x) for x in changes], hp=[before, after])
    return True


def remove_item(s, state, code, count, why=None):
    """Take up to `count` of item `code` out of the bag (last stacks first); saves and resends the bag. Returns the
    count that was not there. Journaled with its reason (why, else the request being handled)."""
    bag = s.data["char"].setdefault("bag", [])
    wanted = count
    for it in sorted((it for it in bag if it["code"] == code), key=lambda it: -it["slot"]):
        n = min(count, it["count"])
        it["count"] -= n
        count -= n
        if not it["count"]:
            bag.remove(it)
    if wanted - count:
        journal("item", ev="spend", code=code, name=items.name(code), n=wanted - count, why=cause(why))
    state.save()
    send_cargo(s)
    return count


def take_back(s, state, code, count):
    """remove_item, and a lent item the hero is wearing when the bag is short (a quest EquipItem weapon the quest text
    asks to equip, planning/wiring/WORLD-WIRING.md Q1): the worn entry goes with the discard push 0x1675 (u16 0,
    coded u16 index; Process_HeroEquipItemDiscard 0x140e51d00) and the hero record is resent."""
    left = remove_item(s, state, code, count)
    eq = hero.equipment(s.data["char"])
    worn = [e for e in eq if e["code"] == code][:left]
    for e in worn:
        eq.remove(e)
        s.send(Writer(S2C_DESTROY_WORN).u16(0).raw(obf.u16(e["index"])))
    if worn:
        state.save()
        send_hero_detail(s)
    return left - len(worn)


TIMED_BOXES = ("bag", "warehouse", "buyback")


def stamp_timed(c, now=None):
    """Timed items held from before timed items expired (no "expires" stamp) start their period now: none is taken
    for time that ran before the rule (a save migration, run at every login and a no-op once stamped). Returns how
    many were stamped (journaled)."""
    now = int(time.time() if now is None else now)
    n = 0
    for e in [e for box in TIMED_BOXES for e in c.get(box, [])] + hero.equipment(c):
        life = items.valid_seconds(e["code"])
        if life and "expires" not in e:
            e["expires"] = now + life
            journal("item", ev="timed", code=e["code"], name=items.name(e["code"]), expires=e["expires"],
                    why="a timed item from before the expiry rule: its period starts now")
            n += 1
    return n


def expire_items(s, state, now=None, notify=True):
    """Remove character c's timed items whose period is over, from the bag, the equipment, the warehouse and the
    rebuy list (journaled). With notify, the client hears 0x1075 for each worn or bag item (a worn one is undressed by
    the client itself), then the bag and the hero record follow; at login (notify False) the lists sent later carry
    the change. Returns the item codes removed."""
    c = s.data["char"]
    now = time.time() if now is None else now
    over = lambda e: "expires" in e and e["expires"] <= now
    gone, alarms = [], []
    for box in TIMED_BOXES:
        for it in [it for it in c.get(box, []) if over(it)]:
            c[box].remove(it)
            gone.append(it["code"])
            if box == "bag" and 0 <= it["slot"] < 0x500:
                alarms.append(obf.u16(it["slot"]) + b"\x01")
    eq = hero.equipment(c)
    for e in [e for e in eq if over(e)]:
        eq.remove(e)
        gone.append(e["code"])
        if 0 <= e["index"] < 21:
            alarms.append(obf.u16(e["index"]) + b"\x00")
    for code in gone:
        journal("item", ev="expired", code=code, name=items.name(code), why="its period ran out")
    if gone:
        state.save()
        log.info("timed items expired: %s", gone)
    if gone and notify:
        for a in alarms:
            s.send(Writer(S2C_ITEM_EXPIRED).raw(a))
        send_cargo(s)
        if any(a[2] == 0 for a in alarms):
            send_hero_detail(s)
    return gone


def arm_expiry(s, state, now=None):
    """Check the timed items again when the first of them runs out (session.later; one timer at a time, re-armed
    by each check and by a gain that expires sooner)."""
    c = s.data.get("char")
    if c is None or not hasattr(s, "later"):
        return
    now = time.time() if now is None else now
    ends = [e["expires"] for box in TIMED_BOXES for e in c.get(box, []) if "expires" in e]
    ends += [e["expires"] for e in hero.equipment(c) if "expires" in e]
    if not ends:
        return
    at = min(ends)
    if s.data.get("expiry_at") is not None and s.data["expiry_at"] <= at and s.data["expiry_at"] > now:
        return

    def check():
        s.data.pop("expiry_at", None)
        if s.data.get("char") is c:
            expire_items(s, state)
            arm_expiry(s, state)
    s.data["expiry_at"] = at
    s.later(max(0.0, at - now) + 1, check)


def give_starter_bag(c):
    """A new hero's bag: herotable %Inventory's INVENTORY rows (hero.starter_bag: the class's Level-up Celebration
    Chest [Lv 5], none for Helena), from the first slot of each item's range, as add_item makes records. The original's
    level-1 Berserker has the chest in his first slot (part 1 18:30, tiouWoPSPks f_00556; tests/test_hero_pools.py)."""
    bag = c.setdefault("bag", [])
    for code, count in hero.starter_bag(c["class"]):
        lo, hi = bag_range(c, code)
        used = {it["slot"] for it in bag}
        bag.append({"code": code, "slot": next(k for k in range(lo, hi) if k not in used), "count": count,
                    "serial": serials.allocate(c), "bound": items.bound_on_gain(code)})


def token_cap(c, code, count, now=None):
    """How many of `count` gained token `code` the day's cap lets in (rules census ECONOMY A5): a TOKEN_ITEM's DayLimit
    is its gains a game day (item_token: Crack Shard 200, Crack Crystal 100, Time Fragment 10, Coliseum Silver Coin 40,
    Clash Coin 50, Easter Egg 40; the official notes' "crack shards 200 / day, crystals 100 / day"). This is distinct
    from the client's NumberOfUse counter in 0x125a/0x4043; native +0x268 is not DayLimit (VANILLA-ITEMS.md).
    Counted in c["token_gains"] for rules.game_day; the rest of the day's gains are not given. The original's notice
    (textsystem 5763 "[%1%] You've reached the max. acquirable amount per day.") is not sent: its packet is not known."""
    r = items.row(code) or {}
    limit = r.get("DayLimit", "")
    if r.get("ItemKind") != "TOKEN_ITEM" or not limit.isdigit() or int(limit) <= 0:
        return count
    today = rules.game_day(now)
    if c.get("token_gains", {}).get("day") != today:
        c["token_gains"] = {"day": today, "counts": {}}
    got = c["token_gains"]["counts"]
    n = max(0, min(count, int(limit) - got.get(str(code), 0)))
    got[str(code)] = got.get(str(code), 0) + n
    if n < count:
        log.info("token %d: %d over today's cap of %s not given", code, count - n, limit)
    return n


def add_item(s, state, code, count, prefer_slot=None, mail=True, why=None, now=None, capped=True, refresh=True):
    """Put `count` of item `code` into the character's bag: onto its stacks up to the item's MaxStack, then into the
    first free slot of its range (the main bag 0 .. bag_slots-1, the client's first tab). Saves and resends the bag;
    returns the count that did not fit, which goes out as a system mail unless mail=False (an offline choice: the
    original's full-bag rule is not known). Journaled with its reason (why, else the request being handled). A timed
    item (items.valid_seconds; MaxStack 1 on all of them) is stamped with its "expires" time (rules census H13, owner
    decision B4: timed costumes expire as the original). A gained token stops at its day's cap (token_cap; capped=False
    for a move of something already gained, a mail's attachment). With refresh=False the caller must publish
    its cargo change after its transaction acknowledgement; purchases need that ordering for native gold/UI."""
    c = s.data["char"]
    if capped:
        count = token_cap(c, code, count, now)
    life = items.valid_seconds(code)
    bag = c.setdefault("bag", [])
    cap = items.max_stack(code)
    added = count
    gained = {"code": code, "bound": items.bound_on_gain(code)}
    for it in bag:
        if count and it["count"] < cap and items.can_stack(it, gained):
            n = min(count, cap - it["count"])
            it["count"] += n
            count -= n
    used = {it["slot"] for it in bag}
    lo, hi = bag_range(c, code)
    first = [prefer_slot] if prefer_slot is not None and lo <= prefer_slot < hi and prefer_slot not in used else []
    free = iter(first + [slot for slot in range(lo, hi) if slot not in used and slot not in first])
    while count:
        slot = next(free, None)
        if slot is None:
            log.warning("bag full: %d of item %d not added%s", count, code, ", mailed" if mail else "")
            break
        n = min(count, cap)
        bag.append({"code": code, "slot": slot, "count": n, "serial": serials.allocate(c),
                    "bound": items.bound_on_gain(code)})
        if items.option_slots(code):                    # gear gets its random options when gained (census H11)
            bag[-1]["options"] = items.roll_options(code, random.randrange)
        if life:
            bag[-1]["expires"] = int(time.time() if now is None else now) + life
        count -= n
    if life and added - count:
        arm_expiry(s, state, now)
    if added:
        journal("item", ev="gain", code=code, name=items.name(code), n=added - count, mailed=count if mail else 0,
                why=cause(why))
    state.save()
    if refresh:
        send_cargo(s)
    if added - count:
        quest.on_item(s, state, code, added - count)
    if count and mail:
        mailbox.deliver(s, state, c, "Bag full", "These did not fit in your bag.", grant=[(code, count)])
    return count


def hero_need(level):
    """Exp to finish a hero level (lvexptable %HeroExp), or None past the last level."""
    for r in tables.sections("lvexptable")["HeroExp"]:
        if r["Level"] == str(level):
            return int(r["Hero"])
    return None


def hero_max_level():
    """The hero level cap: the Level setting (GAMEFORGE 30; the client's init puts the same value in its settings'
    +0x348, which 0x1012's Q+1 then sets), within lvexptable %HeroExp (to 30; the last level's need is %HeroExtraExp's
    ExtraExp, the exp gathered past the cap)."""
    return min(settings.get("Level"), max(int(r["Level"]) for r in tables.sections("lvexptable")["HeroExp"]))


def open_char_slots(acct):
    """The account's open character slots (0x1003 +0x0e): CharSlotMax less LockedCharSlot (GAMEFORGE 6 - 2 = 4; the
    other two stay locked until a CHARSLOT_EXPAND item, which the client caps at CharSlotMax), or more when the
    account already holds more characters (ours: our older builds opened all 6, and a character in a locked slot
    cannot be selected)."""
    return max(settings.get("CharSlotMax") - settings.get("LockedCharSlot"), len(acct["characters"]))


def send_hero_detail(s):
    """0x134b: the hero record (uid = character id, as the roster's slot 0 in 0x1341), level, exp, stats and the
    equipped items."""
    c = s.data["char"]
    equipped = equipped_items(c)
    w = Writer(S2C_HERO_DETAIL).raw(hero_block(c)).u8(len(equipped))
    for rec in equipped:
        w.raw(rec)
    s.send(w)


def hero_block(c):
    """The 0xb5-byte hero block of 0x134b / 0x1081."""
    level, exp = c.get("level", 1), c.get("exp", 0)
    b = bytearray(HERO_BLOCK)
    struct.pack_into("<Q", b, HERO_UID_AT, c["id"])
    struct.pack_into("<Q", b, HERO_EXP_AT, exp)
    struct.pack_into("<Q", b, HERO_NEED_AT, hero_need(level) or 0)
    struct.pack_into("<I", b, HERO_CLASS_AT, c["class"])
    b[HERO_LEVEL_AT] = level
    st = hero.char_stats(c)
    st["HP_CURRENT"] = st["HP_MAX"]             # full health outside battle
    st["SP_CURRENT"] = st["SP_MAX"]             # and the SP pool full: the town HUD reads SP 200 (part 9 35:16,
                                                # 9NwV8ikwLYk f_01059), not %Contents SP_INIT 150 (rules census S12)
    write_hero_stats(b, st)
    return bytes(b)


def swap_pairs(moved):
    """The 0x1755 pairs that carry quick slots along a slot move {old: new}: per chain or cycle c1 -> c2 -> ... -> ck,
    (c1, c2), (c1, c3), ..., (c1, ck); swapped in order they give that move, and no pair's a is an earlier b."""
    targets, pairs, done = set(moved.values()), [], set()
    starts = [a for a in moved if a not in targets] + list(moved)
    for start in starts:
        if start in done:
            continue
        cur = start
        while cur in moved and moved[cur] != start and cur not in done:
            done.add(cur)
            cur = moved[cur]
            pairs.append((start, cur))
        if cur in moved and moved[cur] == start and cur not in done:
            done.add(cur)
    return pairs


def stat_code(v):
    """The client's compact stat value (encoder 0x14061af80, decoder 0x14061b040): high u16, then low u16."""
    v = int(v)
    if v < 0:
        u = 0
    elif v < 0x40000000:
        u = v
    elif v < 0xc0000000:
        u = (v - 0x3fffffff) // 2 + 0x40000000
    elif v < 0x200000000:
        u = (v - 0xbffffffe) // 5 + 0x80000000
    elif v < 0x480000000:
        u = (v - 0x1fffffffb) // 10 + 0xc0000000
    else:
        u = 0xffffffff
    return struct.pack("<HH", u >> 16, u & 0xffff)


def write_hero_stats(b, st):
    for name, at in HERO_STAT_AT.items():
        struct.pack_into("<i", b, at, round(st.get(name, 0)))
    for name, at in HERO_STAT_F32_AT.items():
        struct.pack_into("<f", b, at, st.get(name, 0))
    for name, at in HERO_ATTACK_AT.items():
        struct.pack_into("<i", b, at, round(st.get(name, 0) * 10))
    for name, at in HERO_STAT_CODED_AT.items():
        b[at:at + 4] = stat_code(round(st.get(name, 0)))


def equip_one(e):
    """0x1676 for one worn item, after its durability changed."""
    return Writer(S2C_EQUIP_ONE).raw(obf.u16(e["index"])).raw(
        items.record(e["code"], e["index"], e["serial"], durability=items.durability(e), bound=e.get("bound", False),
                     enchant=e.get("enchant", 0), sockets=items.sockets(e), expiry=items.seconds_left(e),
                     options=e.get("options", ())))


def wear_down(s, state, kind):
    """Durability loss for an event (item_durability %DurabilityReduce: DIE takes 4 from each worn weapon and armour
    piece); each worn item that lost some is resent (0x1676)."""
    c = s.data.get("char") or s.data["account"]["characters"][0]
    changed = items.wear(hero.equipment(c), kind, random.randrange)
    for e in changed:
        s.send(equip_one(e))
    if changed:
        state.save()
        log.info("durability %s: %s", kind, [(e["code"], e["dur"]) for e in changed])
    if any(hero.broken(e) for e in changed) and "battle" in s.data:
        from . import game                      # a piece broke: its stats stop counting (G20), the room's follow
        game.room_stats(s, c)


def equipped_items(c):
    """The hero's equipped items as records, slot = the equipment index, E_ItemParts - 1 (the equip drag checks
    index == Parts - 1, 0x140e4a270; slot = part showed the main weapon one place over)."""
    return [items.record(e["code"], e["index"], e["serial"], durability=items.durability(e),
                         bound=e.get("bound", False), enchant=e.get("enchant", 0), sockets=items.sockets(e),
                         expiry=items.seconds_left(e), options=e.get("options", ())) for e in hero.equipment(c)]


def change_equip(c, bag_serial, equip_serial, index, bag_slot):
    """Swap between a bag slot and an equipment index as a 0x164e drag asks (either side may be empty). Returns
    None when done, else why not."""
    bag, eq = c.setdefault("bag", []), hero.equipment(c)
    b = next((it for it in bag if it["serial"] == bag_serial), None) if bag_serial else None
    e = next((it for it in eq if it["index"] == index), None)
    if (e["serial"] if e else 0) != equip_serial:
        return f"equipment index {index} holds {e['serial'] if e else 0:#x}, not {equip_serial:#x}"
    if bag_serial and (b is None or b["slot"] != bag_slot):
        return f"no item {bag_serial:#x} in bag slot {bag_slot}"
    if not bag_serial and (e is None or not slot_ok(c, e["code"], bag_slot)
                           or any(it["slot"] == bag_slot for it in bag)):
        return f"bag slot {bag_slot} is not free"
    if b is None and e is None:
        return "nothing to move"
    if b and not items.fits_index(b["code"], index):
        return f"item {b['code']} does not go in equipment index {index}"
    if b and (why := hero.wear_refusal(c, b["code"])):
        return why                              # its Use Conditions: class, level (census G14)
    if b:
        bag.remove(b)
        eq.append({"code": b["code"], "index": index, "serial": b["serial"], "enchant": b.get("enchant", 0),
                   "bound": b.get("bound", False) or items.bound_on_equip(b["code"]),
                   **items.extras(b)})
    if e:
        eq.remove(e)
        bag.append({"code": e["code"], "slot": bag_slot, "count": 1, "serial": e["serial"],
                    "enchant": e.get("enchant", 0), "bound": e.get("bound", False),
                    **items.extras(e)})
    return None


def send_exp(s):
    """0x124a with the hero's level and exp (leader slot 0); the client levels up when the level differs."""
    c = s.data["char"]
    level, exp = c.get("level", 1), c.get("exp", 0)
    hero = struct.pack("<BQQ", level, exp, hero_need(level) or 0)
    deck = b"".join(struct.pack("<BQQ", *t) for t in troops.deck_levels(c))   # zeros would reset a deck troop's exp
    block = deck + hero + bytes(8 * EXP_SLOT)
    s.send(Writer(S2C_EXP).u8(0).i32(c["id"]).raw(block))


def add_exp(s, state, amount, why=None):
    """Add hero exp, level up through %HeroExp (up to the cap, hero_max_level), save, send 0x124a; journaled with its
    reason (why: a kill, a quest, a mission; else the request being handled)."""
    c = s.data["char"]
    before = c.get("level", 1)
    level, exp = before, c.get("exp", 0) + amount
    while (need := hero_need(level)) is not None and exp >= need and level < hero_max_level():
        exp -= need
        level += 1
    grew = level != before
    journal("exp", add=amount, level=level, up=level - before, exp=exp, need=hero_need(level),
            why=cause(why))
    c["level"], c["exp"] = level, exp
    send_exp(s)
    if grew:                                    # after "The hero levelled up." (0x124a), as on the tape: the AutoLearn
        skills.level_up(s, c, before)           # rows the level brings and raises (0x1761, recorded in c["skills"])
        was = skills.bar_skills(c, before)
        if seat_skills(c, [a for a in skills.bar_skills(c) if a not in was]):
            s.send(quick_slot_page_packet(c, 0))    # the new skill on its row's first free slot (tape: Capture to
                                                    # key 3 at Lv.2, Supplement to slot 100 at 6, Extinction to 4 at 8)
    state.save()
    if grew:                                    # the hero window's stats and the skill points follow the level
        s.send(Writer(S2C_HERO_BLOCK).raw(hero_block(c)))
        s.send(skills.tp_packet(c))
        if daily.top_up(c):                     # a level band with more daily tasks (17+): today's list grows
            for w in daily.list_packets(c):
                s.send(w)
        if "battle" in s.data:                  # levelled inside a room (kill exp): the effect and new numbers
            from . import game
            game.room_level_up(s, c)
        titles.achieve(s, state, "HeroLv", value=level)
        quest.on_level(s, state)


def change_gold(c, amount, why=None):
    """Move character c's gold by amount, journaled with its reason (why, else the request being handled); the caller
    saves and sends the new total (add_gold, or a store's reply, or the bag resend). A gain stops at GOLD_CAP, the
    client's own cap (texts 0x1bd0 / 0x1bdf; rules census A1). Returns the amount moved."""
    have = c.get("gold", 0)
    if amount > 0:
        amount = max(0, min(amount, GOLD_CAP - have))
    c["gold"] = have + amount
    if amount:
        journal("gold", delta=amount, gold=c["gold"], why=cause(why))
    return amount


def add_gold(s, state, amount, why=None):
    """Add to the character's gold, save, and send the new total: 0x1658 in town (the client shows the gain); inside a
    battle room the bag refresh 0x1656 instead, until 0x1658 has been tried there: the crash seen in a room was the
    old gold packet sent as 0x1657 (Process_InvenItemChange; the id was wrong), and 0x1657
    (handler 0x140dcfc40: window refresh 0x140dcbdb0, gain notice 0x140d641a0) killed the client within a second in
    a room (live 2026-09-27, probe: 0x124a and 0x1656 survived; the failing call is not pinned, the room has all
    the windows the refresh reads)."""
    c = s.data["char"]
    amount = change_gold(c, amount, why)
    state.save()
    if amount > 0:
        titles.achieve(s, state, "GoldGain", add=amount)
    if in_battle_room(s):
        send_cargo(s)
    else:
        s.send(Writer(S2C_GOLD).raw(obf.u40(c["gold"])))


def in_battle_room(s):
    """Whether this session's client is in a battle room: a world session that sent it to one (battle_spot, cleared by
    the next town entry) or the game session of the room."""
    return bool(s.data.get("battle_spot")) or "battle" in s.data


def start_point(spot, group):
    """A map's start point by group (warpinfo SPGroupID): measured, else the group's first start point in the zone
    file (Mist Field's zone points lie within 200 of the measured ones: the client picks a place in the start area),
    else None. Lake Bled 10202 is measured nowhere; its spottable corner (-20000, 20000) is off the map."""
    measured = TOWN_ENTRY.get(spot) if group == 0 else START_POINTS.get(spot, {}).get(group)
    return measured if measured is not None else zone_start(spot, group)


def send_teleport(s, spot, pos):
    """S2C 0x5641 type 5: move the hero to pos on the current town/field map (client snaps y to the ground)."""
    journal("warp", how="teleport", spot=spot, pos=list(pos))
    x, y, z = pos
    q, p15 = obf.pos_xz(x, z)
    s.send(Writer(S2C_WARP_PROCESS).u8(5).raw(q).raw(struct.pack("<h", y)).u8(p15).u8(WARP_KIND_TOWN).raw(bytes(2))
           .raw(obf.u32(spot)))


def field_warp(spot, group):
    """The warpinfo id of a field spot's start-point group (WARP_POSITION FIELD), or None. Warps that require a quest
    are left out: they are the missions' ways back (30001 / 30002, game.return_group), sent once after the mission;
    a 0x5641 type 1 queues the warp's EnterScript for the next room entry, so 30001 (10350 group 0) would replay
    11_Village_chief on every entry there (0x140cee4c0 runs BattleField +0x6e0's script on OnEnter, read 2026-09-27)."""
    return next((int(r["ID"]) for r in tables.load("warpinfo") if r["SpotID"] == str(spot)
                 and r["SPGroupID"] == str(group) and r["WARP_POSITION"] == "FIELD"
                 and "Quest" not in r["Require1_Type"]), None)


def field_entry_group(c, spot):
    """The start group a field is entered at when nothing names one (a login, the town path's redirect, a mission left
    before its win): the group of the last entry into that field (c["field_group"]), else the measured group nearest
    the saved position; then a plain one (plain_group), unless a won mission's way back names that group (its return
    warp's cutscene is the first arrival: game.mission_way_back)."""
    fg = c.get("field_group")
    group = fg[1] if fg and fg[0] == spot else nearest_group(spot, c.get("pos"))
    back = c.get("mission_return")
    if back and back["spot"] == spot and back["group"] == group:
        return group
    return plain_group(spot, group)


def plain_group(spot, group):
    """A start group a plain entry (no warp walked through: a login, the town path's redirect, a mission left before
    its win) can take without replaying an arrival cutscene: `group` itself when it is the room's default start
    (spottable SPGroupID_1, which the client takes with no 0x5641: 0x140cf4a60 -> battle state +0x9c, used by
    SetupTroopStartPos 0x140cfed00 when no pending warp names the room) or its warp's EnterScript plays no scene;
    else the nearest such group of the field's zone start points. The client runs the pending warp's EnterScript on
    every battle-room OnEnter (0x140ceeb38: valid warp, 0x140b6d3b0, 0x140a83640; no once-only record), and the
    groups 5 / 6 of Mist Field 10350 and 2 of Glen's camp 10352 have only a scene warp (704 17_LEV_MoonLight, 705
    16_LEV_GraySmoke, 620 15_LEV_MistForest: the SpotWarps of quests 1150502, 1150602 and 1150110's accepts), so a
    plain entry there replayed it (native run 2026-10-09 14:56:47: a relog into 10350 group 6, 0x5641 705, the
    cutscene 14:57:04-14:57:13). That the original's server sent no scene warp on a plain entry is inferred from
    the client having no guard; the nearest plain group is ours."""
    def plain(g):
        warp = field_warp(spot, g)
        if warp is None:
            return g == default_group(spot)
        return SCENE_SCRIPT not in (tables.by_id("warpinfo").get(str(warp)) or {}).get("EnterScript", "")
    if plain(group):
        return group
    here = start_point(spot, group)
    points = {g: start_point(spot, g) for g in zone_groups(spot) if plain(g)}
    points = {g: p for g, p in points.items() if p is not None}
    if here is None or not points:
        return default_group(spot)
    return min(points, key=lambda g: (points[g][0] - here[0]) ** 2 + (points[g][2] - here[2]) ** 2)


def default_group(spot):
    """The start group a field's room takes when no warp names one: spottable SPGroupID_1 (0 on every Field and City
    spot)."""
    v = (tables.by_id("spottable").get(str(spot)) or {}).get("SPGroupID_1", "")
    return int(v) if v.isdigit() else 0


def zone_groups(spot):
    """The start-point groups of a map's zone file (PlayerStartPointInfoData LongGroupID of the plain start points: no
    LongWarpID, SPTypes 0, as crystal_warp reads them), sorted."""
    from . import zone
    if not zone.available(spot):
        return []
    return sorted({p["LongGroupID"] for p in zone.for_spot(spot)["PlayerStartPointInfoData"]
                   if p.get("SPTypes") == 0 and not p.get("LongWarpID") and p["StartPointInfoData"]})


def client_map(spot):
    """The map name the client compares for a spot (0x140d71c00 on spottable Map_File, row +0x110): a leading
    "<number>_" or "Test_" dropped, and a trailing "_P..." part; None for an unknown spot."""
    row = tables.by_id("spottable").get(str(spot))
    if row is None:
        return None
    m = row.get("Map_File", "")
    head, _, rest = m.partition("_")
    if rest and (head.isdigit() or head == "Test"):
        m = rest
    j = m.rfind("_")
    if j > 0 and len(m) - j > 2 and m[j + 1] == "P":
        m = m[:j]
    return m


def same_map(old, new):
    """Whether the client keeps its map going from spot old to spot new (0x140d65c60 sets common+0x1728): two different
    spots whose client_map is the same and the new one's has no "_RIFT". Then a 0x4049 naming new ends nothing and
    loads nothing: the client waits for the next room's 0x3f41."""
    a, b = client_map(old), client_map(new)
    return old != new and a is not None and a == b and "_RIFT" not in b


def same_map_field(room, spot):
    """Whether a spot change of the client in room `room` to `spot` (a 0x4049 or 0x4041 naming it) would leave the
    client holding common+0x1728 = 1: `spot` is a Field (spottable Spot_Type, the client's spot type 4) on the room's
    own map (same_map; 0x140d65c60 sets 1 for a Field, 2 for any other type). With 1 the MissionEscape handler
    0x140d00590 neither ends the battle nor loads, and the next room's 0x3f4e start cannot end it either: its header
    0x140d09380 does (0x140cf2e10, then the state's leave vt+0x30, before the player info) only for 2 (a same-map
    mission, live many times), and with 1 the go 0x140d07ec0 changes state (0x140cbc870 -> 0x140cbc720), whose
    BattleField leave 0x140cefc00 -> 0x140cf2130 then clears the PlayerManager (0x140b42910 deletes every Player) and
    the start info 0x3f4f / 0x3f50 had just filled. That room has no local player: the hero is built from its 0x50cb
    for an owner-0 Player, the host sync 0x50b0 carries no record, and the first 0x50cf reads the missing local player
    (0x140b431e0, called at 0x140d1c501, returns null; 0x140d1c506 reads its +0x50): the 2026-10-24 13:54:21 crash in
    Wolf Fang Field 10359,
    entered from Mist Field 10350 by 1150808's CurrentWarp. Nothing clears the 1 later but a start in place
    (0x140cf3320) or another spot change. The client's own way into a same-map field room is the late join 0x50ba
    (0x140d086b0 ends the battle for 1 as 0x3f4e's header does for 2), which we do not build."""
    row = tables.by_id("spottable").get(str(spot)) or {}
    return bool(room) and same_map(room, spot) and row.get("Spot_Type") == "Field"


def nearest_group(spot, pos):
    """The measured start-point group nearest pos (x, y, z) on a field, 0 (the entry point) when nothing is known."""
    points = {0: TOWN_ENTRY.get(spot), **START_POINTS.get(spot, {})}
    points = {g: p for g, p in points.items() if p is not None}
    if not pos or not points:
        return 0
    return min(points, key=lambda g: (points[g][0] - pos[0]) ** 2 + (points[g][2] - pos[2]) ** 2)


def send_field_entry(s, spot, group, leave_battle):
    """Into a field's battle room at a start-point group. 0x5641 type 1 with the group's warp id makes the client keep
    (spot, group) for MissionInfo::FindPlayerStartPoint (battle state +0x6e8 / +0x6ec); from inside a battle room
    0x4049 takes the client out first; then 0x3f41 sends it to the game server, where it loads at that start point.
    Group 0 (no warp) is the field's default start point. Probe-verified 2026-09-27 (group 2 of Mist Field).
    Into a Field of the room's own map the 0x4049 names the room's own spot (same_map_field; ours): that changes
    nothing in 0x140d65c60, so the client ends the battle and waits in WarpWait for the 0x3f41 that names the field,
    as for warp 704 into the same field (live 13:30:06); the field's own spot would keep the battle (13:54:21)."""
    c = s.data["char"]
    room = s.data.get("battle_spot")            # the room the client is in (its current spot), before this entry
    named = room if leave_battle and same_map_field(room, spot) else spot
    back = c.pop("mission_return", None)        # a finished mission's way back (game.leave_mission): its warp, once
    warp = back["warp"] if back and back["spot"] == spot and back["group"] == group else field_warp(spot, group)
    if warp is not None:
        s.send(Writer(S2C_WARP_PROCESS).u8(1).raw(obf.u32(warp)).u8(WARP_KIND_FIELD))
    pos = start_point(spot, group)
    if pos is not None:
        c["pos"] = list(pos)
    c["spot"] = spot
    c["field_group"] = [spot, group]
    if back and getattr(s, "state", None) is not None:
        s.state.save()                          # the way back is used: a later login must not replay its scene
    host, port = s.data["game_addr"]
    s.data["battle_spot"] = spot
    log.info("field %d: to start group %d (warp %s)%s", spot, group, warp, ", leaving the battle room" if leave_battle
             else "")
    journal("warp", how="field", spot=spot, group=group, warp=warp, **({"escape": named} if named != spot else {}))
    if not leave_battle:
        send_game_server(s, spot, host, port)
        return
    if named != spot:
        log.info("field %d: the leave names room %d's own spot (the same map: same_map_field)", spot, named)
    from . import game
    x, _, z = pos or (0, 0, 0)
    blk = bytearray(0x1d)
    blk[0:5] = obf.u40(0)                   # gold LOST by leaving (text 7382 "You have lost %d Gold. Due to exit
    #                                         during the mission.", 0x140d66680): no penalty offline
    blk[7:11], blk[13] = obf.pos_xz(x, z)
    blk[0x16] = WARP_KIND_FIELD
    blk[0x17:0x1b] = obf.u32(named)
    blk[0x1b:0x1d] = struct.pack("<H", game.MY_SLOT)
    s.send(Writer(S2C_MISSION_ESCAPE).u16(0).raw(bytes(blk)))
    s.data["entering"] = spot                   # until the game server is sent (mission_escape ignores a 2nd leave)

    def to_game():
        s.data.pop("entering", None)
        send_game_server(s, spot, host, port)
    s.later(ESCAPE_S, to_game)


def zone_start(spot, group=0):
    """The first start point of a map's group in its zone file (PlayerStartPointInfoData, LongGroupID; the warp-less
    entry), or None."""
    from . import zone
    if not zone.available(spot):
        return None
    for p in zone.for_spot(spot)["PlayerStartPointInfoData"]:
        if p.get("LongGroupID") == group and not p.get("LongWarpID") and p["StartPointInfoData"]:
            pt = p["StartPointInfoData"][0]
            return (round(pt["PosX"]), 0, round(pt["PosZ"]))
    return None


def mission_quest(c, spot):
    """The held quest a mission spot clears: a MissionLevelClear condition with IngSpot<n> = spot (1150406 -> 10233,
    1150601 -> 10234), or None."""
    for qid in quest.record(c)["active"]:
        row = tables.by_id("questtable").get(qid) or {}
        if any(row.get(f"Complete{n}_Type") == "MissionLevelClear" and row.get(f"IngSpot{n}") == str(spot)
               for n in range(1, quest.CONDITIONS + 1)):
            return int(qid)
    return None


def send_mission_entry(s, state, spot, qid, difficulty=0, warp=None, back=None):
    """Into a mission battle (a Battle spot with a zone file): a quest's MISSION SpotWarp on accept (1150301 -> 10358,
    the way out of Glen's camp) or the client's own 0x3f48 (a MISSION warp door's solo room, e.g. warp 500 -> 10233
    beside Glen 6008 for 1150406; NPC menu ENTRANCE3; the world map), with qid the held quest it clears or None. The
    saved spot stays the field (a relog does not land in the mission); c["mission"] keeps where it ends: `back` when
    given (a mission carried on from another keeps that one's end: continue_mission), else the quest's EndSpot, else
    the spot the hero left. From inside a room (a field's, or a won mission's) 0x4049 takes the client out first, as
    for a field warp, then 0x3f41 sends it to the game server; the room's start group comes from `warp` when given,
    else mission_warp."""
    from . import game
    c = s.data["char"]
    end = tables.by_id("questtable")[str(qid)].get("EndSpot", "") if qid else ""
    if back is None:
        back = int(end) if end.isdigit() else c.get("spot", START_SPOT)
    c["mission"] = {"spot": spot, "quest": qid, "back": back}
    if difficulty:
        c["mission"]["difficulty"] = difficulty  # 1 Hard, 2 Hell (game.mission_difficulty; absent = Normal)
    state.save()
    host, port = s.data["game_addr"]
    leave = bool(s.data.get("battle_spot"))
    s.data["battle_spot"] = spot
    log.info("quest %s: into mission %d (back to %s)%s", qid, spot, c["mission"]["back"],
             ", leaving the room" if leave else "")
    journal("warp", how="mission", spot=spot, quest=qid, back=c["mission"]["back"])
    if not leave:
        send_game_server(s, spot, host, port)
        return
    warp = warp if warp is not None else mission_warp(spot, qid)
    if warp is not None:                        # the room's start group: without it the client kept the field's
        s.send(Writer(S2C_WARP_PROCESS).u8(1).raw(obf.u32(warp)).u8(WARP_KIND_FIELD))
    x, _, z = game.mission_start(spot) or (0, 0, 0)
    blk = bytearray(0x1d)
    blk[0:5] = obf.u40(0)                   # gold LOST by leaving (text 7382 "You have lost %d Gold. Due to exit
    #                                         during the mission.", 0x140d66680): no penalty offline
    blk[7:11], blk[13] = obf.pos_xz(x, z)
    blk[0x16] = WARP_KIND_FIELD
    blk[0x17:0x1b] = obf.u32(spot)
    blk[0x1b:0x1d] = struct.pack("<H", game.MY_SLOT)
    s.send(Writer(S2C_MISSION_ESCAPE).u16(0).raw(bytes(blk)))
    s.data["entering"] = spot                   # until the game server is sent: the client's 0x3f48 answer is not a new
    #                                             entry, and a leave (0x4048) is ignored (mission_escape)

    def to_game():
        s.data.pop("entering", None)
        send_game_server(s, spot, host, port)
    s.later(ESCAPE_S, to_game)


def mission_warp(spot, qid=None):
    """The warpinfo id that enters a mission spot: the quest's accept SpotWarp when it names this spot (1150301 -> 613),
    else the spot's first MISSION warp without an EnterScript (all of them start group 0), or None. Leaving a field room
    for a mission, 0x4049 names the mission spot but no start group, so the client kept the field's group (+0x6ec) and
    SetupTroopStartPos 0x140cfed00 found no such group in the mission: the hero stood at (0, 0), off the map (live
    2026-09-27: 10358 entered from Glen's camp group 2, the 0x50b0 reports at (46, 47))."""
    rows = {r["ID"]: r for r in tables.load("warpinfo")}
    q = (tables.by_id("questtable").get(str(qid)) or {}) if qid else {}
    v = q.get("QuestAccept_Action_Value", "")
    if q.get("QuestAccept_Action") == "SpotWarp" and rows.get(v, {}).get("SpotID") == str(spot):
        return int(v)
    return next((int(r["ID"]) for r in rows.values() if r["SpotID"] == str(spot) and r["WARP_POSITION"] == "MISSION"
                 and not r.get("EnterScript")), None)


def continue_mission(g, state, warp):
    """A won mission the original's script carried on into another (the table's NEXT, director.next_warp): Lunawing
    Sortie I 10361 into Sortie II 10362 through warp 622 (MISSION, 10362 group 1), the one warp of the data nothing
    else uses. The tape (part 3): Sortie I's last line 4:56, no result window, the loading screen "New Hampton Highway"
    5:23, Sortie II's panel 5:58; no field between. g is the won room's game session; the world session sends the
    entry (send_mission_entry from inside a room: 0x5641 type 1 with the warp, 0x4049, then 0x3f41) and the next
    mission keeps the won one's quest and end spot (1150703, back 10351: the crash site after Sortie II). True when
    sent; False without a live world session (the caller then leaves the room as before)."""
    acct = g.data.get("account") or {}
    s = getattr(state, "world_sessions", {}).get(acct.get("id"))
    row = tables.by_id("warpinfo").get(str(warp)) or {}
    if s is None or s.w.is_closing() or not row.get("SpotID", "").isdigit():
        log.warning("mission %s: no world session to go on through warp %s; leaving", g.data.get("spot"), warp)
        return False
    c = s.data["char"]
    before = c.get("mission") or {}
    spot = int(row["SpotID"])
    log.info("mission %s won: on into mission %d through warp %d", g.data.get("spot"), spot, warp)
    send_mission_entry(s, state, spot, before.get("quest"), before.get("difficulty", 0), warp=warp,
                       back=before.get("back", c.get("spot", START_SPOT)))
    return True


def leave_for_same_map_field(g, state):
    """A windowless win whose way back is a Field on the mission's own map (Grey Fog 10358 -> Mist Field 10350, Lunawing
    Sortie II 10362 -> 10351): left as a field warp from the won room (send_field_entry: the return warp's 0x5641, the
    0x4049 naming the room's own spot, then 0x3f41), not by 0x4041. 0x4041 ends the battle whatever the flag
    (0x140d003f0), but it makes the end spot current (0x140d65b10), which leaves common+0x1728 = 1 (same_map_field) in
    the field's room: every later 0x4049 there would keep the battle (a field warp: the 13:54:21 crash; Esc to the world
    map: the 2026-10-09 black screen). The 0x4041 of a windowless win was ours already (game.end_without_window). g is
    the won room's game session; True when sent through a live world session, else False (the caller leaves by 0x4041
    as before)."""
    from . import game, zone
    acct = g.data.get("account") or {}
    s = getattr(state, "world_sessions", {}).get(acct.get("id"))
    if s is None or s.w.is_closing():
        return False
    c = s.data["char"]
    room = g.data.get("spot")
    back = (c.get("mission") or {}).get("back", c.get("spot", START_SPOT))
    if not (same_map_field(room, back) and zone.available(back)):
        return False
    back, group, _ = game.mission_way_back(c)
    state.save()
    s.data["battle_spot"] = room                # the won room the client is in: the leave names it
    log.info("mission %s won: back to field %d of its own map as a field warp (group %d)", room, back, group)
    journal("room", ev="leave", spot=room, back=back, how="field warp")
    send_field_entry(s, back, group, leave_battle=True)
    return True


def mission_door(s, state, spot):
    """A mission entered by the client itself (0x3f48: a MISSION warp door's solo room or an ENTRANCE NPC, e.g. 10235
    New Hampton Castle through door 502, which 1160113 has no accept warp for) ends where a quest warp would have sent
    it (send_mission_entry): the EndSpot of the held quest whose MissionLevelClear is at this spot (IngSpot<n>);
    1160113 -> 10354, the castle side of the highway. Without such a quest the leave goes back to the saved spot, and
    a record left by an escaped mission is dropped. (No zone lookup here: decoding an uncached zone takes seconds.)"""
    c = s.data["char"]
    for qid in quest.record(c)["active"]:
        row = tables.by_id("questtable").get(qid) or {}
        if any(row.get(f"Complete{n}_Type") == "MissionLevelClear" and row.get(f"IngSpot{n}") == str(spot)
               for n in range(1, quest.CONDITIONS + 1)):
            end = row.get("EndSpot", "")
            c["mission"] = {"spot": spot, "quest": int(qid), "back": int(end) if end.isdigit() else c.get("spot", START_SPOT)}
            log.info("mission %d entered by its door for quest %s (back to %s)", spot, qid, c["mission"]["back"])
            break
    else:
        c.pop("mission", None)
    state.save()


def send_game_server(s, spot, game_host, game_port):
    w = Writer(S2C_GAME_SERVER)
    w.u16(0).u16(game_port).u32(int.from_bytes(socket.inet_aton(game_host), "big")).u32(spot).u8(0)
    s.send(w)


def login_point(c):
    """(prologue, spot, pos): where start game sends character c. Only a character created for the prologue
    (char_create: tutorial_done False) plays it, until it ends (its win, or 0x10d6); one without the key was created
    before the prologue existed and never goes back. The lobby entry names the same spot (write_char_entry)."""
    prologue = PROLOGUE_FOR_NEW_CHARACTERS and c.get("tutorial_done") is False
    if prologue:
        return True, TUTORIAL_SPOT, TUTORIAL_POS
    return False, c.get("spot", START_SPOT), c.get("pos", START_POS)


def write_char_entry(w, c):
    """Character list entry: 88-byte struct, cstr name, cstr (guild?), then the worn items as 0x134b lists them (the
    reader 0x140e7a350 calls 0x134b's list reader 0x140da6410: u8 n, n * record, slot = the equipment index), so the
    lobby hero shows its gear and costumes (UI-WIRING.md U23).
    The select screen's "Character Location" (InfoBox.as UpdateCharDetailInfo $area, filled by 0x140ed7470 at
    0x140ed76c1): entry +0x4e false (-> LobbyCharacter +0x1539) shows spot 50116's name whatever the entry says (the
    client's own 0xc3c4); true shows +0x0f (plain u32 -> +0x14f8, kind 2 of the spot-name lookup 0x140578a90: the
    WAR_SPOT_NAME, "Mist Field" for 10359), text 20033 for 0 / -1. +0x1539 false also raises box 90 at JoinChar for a
    level-1 hero (0x140e78056). So +0x4e is "past the prologue" and +0x0f the saved spot (login_point)."""
    prologue, spot, _ = login_point(c)
    look = bytes.fromhex(c["look"])
    e = bytearray(0x58)
    e[0x00:0x0a] = look[0x15:0x1f]          # 5 colour U/V pairs -> LobbyCharacter+0xd8
    struct.pack_into("<I", e, 0x0a, c["class"])
    e[0x0e] = SCALE_ONE
    struct.pack_into("<I", e, 0x0f, spot)   # plain spot -> +0x14f8 (the location; 0x140a94550 for +0x4f 2 / 5)
    e[0x13:0x28] = look[0x00:0x15]          # 21 face sliders -> +0x14d0
    e[0x28:0x3c] = look[0x1f:0x33]          # 5 coded part ids (hair, face, tattoo, ...; as the create packet sent them)
    e[0x3c] = c["level"]
    e[0x3d] = 1                             # obool false
    struct.pack_into("<I", e, 0x46, c["id"])
    e[0x4e] = OBOOL_FALSE if prologue else OBOOL_TRUE    # past the prologue -> +0x1539: the location from +0x0f
    worn = equipped_items(c)
    w.raw(bytes(e)).cstr(c["name"]).cstr("").u8(len(worn))
    for rec in worn:
        w.raw(rec)

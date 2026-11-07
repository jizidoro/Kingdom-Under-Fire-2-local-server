"""PvP against AI: the three War Tutorial spots (spottable Spot_Type PVP_POINT, Spot_Sub_Type PVP_AI: 20954 Field of
Smash, 20955 / 20956 Stonehall Siege attack / defence) as a 16-player room with 15 AI players. Family 4 of
planning/todo/CONTRACT-COMPLETE-PLAN.md; the dig: planning/agents/reports/2026-11-05_contract-pvp.md §2, this
module's own: planning/agents/reports/2026-11-05_contract2-pvpai.md.

The data. aipctrooptable %AIPVP gives a spot 16 seats (AIPC_ID_0..15): "-" the player's (seat 0, 8, 0), each other an
%AIPCPreset of that spot: a hero (%AIPCHero: class, level, gear with its enchants, costume, face, hair) and its
troops (%AIPCTroop: trooptable id, level, skills). Seats 0-7 are the map's team 0, 8-15 team 1: the zone holds 16
start groups (StartPointID = the seat, LongTeamID 0 / 1, nine places each) and names its siege engines by seat
(수비팀_유저0..7, 공격팀_유저08..15), so 20955 puts the player on the attacking team and 20956 on the defending one.
The client seats a player itself, by his id: MissionInfo::FindPlayerStartPoint 0x140cd6f20 takes the start points of
his team and group in the zone's order (0x140cd7240: eight here) and picks number id mod 8 (an id above 8 less 8
first), so the original's player ids were the seats.

The waiting room is the client's own (CommonSubPvpWaitingRoom::EnterPvPAIRoom 0x140628e10 fills it from the same
rows and sends nothing; closing it sends nothing), so the server learns of it at the start:
  C2S 0x3e5e (0x140629b50 from the "start" callback 0x1406279c0, room +0xec set): coded u32 spot.
  S2C 0x3e5f Process_ResPVPAIStart (0x14062bbf0): i16 (under 2 bytes crashes); non-zero clears the room's pending
      flag and prints the room error map's text (0x140d680e0: 0x402 -> 5036 "Cannot enter the room."); 0 does nothing.
  S2C 0x3f41 follows a 0 (0x140cbe770 has the PvP room's branch): the game server's address, as 0x3f48's.
The room's slot move 0x3e53 and ready 0x3e5a keep their fixed refusals (world.EMPTY_REPLIES): the server holds no
waiting room, the seat is the spot's, and a 0x3e54 with 0 would make the client erase the AI seat moved onto
(0x14062acb0) while 0x3e5e names only the spot. The server's room of one (0x3e42 / 0x3e61) is pvproom.py's.

The room start (the game role; game.send_start_header hands over its header):
  S2C 0x3f4e header + 16 start records (0x140d09380): u16 team, u16 player id, obool, u16 troops. The obool is "no
      player struct" (Player +4, an NP owner: 0x140d09720 skips the struct, 0x140b3fb30 clears troop +0xf17), FALSE
      for all 16; the header counts the FALSE ones as the structs 0x3f4f must bring (0x143793770).
  S2C 0x3f4f (0x140d09720): u16 16, each 191 bytes + cstr name + cstr, in record order (game.player_struct). What
      makes a player an AI player is the u32 at +0xa9: non-zero sets Player +0x358 and is kept at +0x35c. It is the
      preset's ActiveTroopAISet, the key of %AIPCTroopAISet: the client's own lookup of that value
      (0x140709c80 -> 0x141889f30) reads the map the %AIPCTroopAISet parser fills (0x14188ad50, table +0x70), and the
      client never reads the preset's column of that name. With the flag the client itself, as host, runs the
      player (SyncManager::RegisterNPCTroops 0x140c16780: its troops are simulated here (+0x230), its hero's troop
      takes TROOPAITYPE_OFFENSIVE with the set's TROOPAI_OFFENSIVE program (0x1407e85e0: 11000 / 11010), its other
      troops Hero Support; Player::AddTroop 0x140b3fb30 copies the flag to troop +0x749, which lets the hero's unit
      AI tick, 0x140bf97c0: the Hero_AI combos) and leaves it out of the solo count (0x140b43210: Players with an
      id under 5000 and no flag), so the room stays "solo" and the relays stay off.
  S2C 0x3f50 (0x140d0a370): every player's troops in record order, the first of each his hero (game.write_troop).
  S2C 0x3f4e go.
Then, at the loading's end, each start troop's place and state (0x50cb, 0x50b8: game.write_troop_state), the zone's
NP troops and props, and the battle records for all of them (combat.Battle), so hits both ways resolve.

The end:
  S2C 0x5043 Packet_MissionCompletePVP (0x140d00090 -> the result window 0x71's reader 0x14085afd0): u8 result (1 the
      window's "won" state +0xc0 = 1, 2 leaves it, anything else lost), u8 match type -> +0xe9 (5 is the waiting
      room's "none", 0x1406277ac: the two numbers are then not read), 8 bytes (u32, u32 -> +0xc4 / +0xc8, the pointer
      always taken), u8 n, n x 8 (coded u32 item, coded u16 count, 2 unread: 0x14085f800). Under 11 bytes crashes.

Ours (the map's script is not shipped: aipctrooptable %PlayerAISet names 2_FieldofSmash_Tutorial.lua and
2_StonehallSiege_Tutorial.lua, and no table holds a rule), named so in the report:
  - the room is won when every hero and troop of the other team's eight players is down (the standing rule for
    rooms whose script is not shipped, ROADMAP Q1); the zone's own troops (gates, towers, the crystal) decide nothing;
  - no defeat (ROADMAP Q2): the player's hero comes back by the room's timed revival (changetroop.py), the AI
    players' do not come back;
  - no reward (table pvp has none for an AI match); c["pvp_ai"] counts the rooms played and won, a room left before
    its win being the loss;
  - the ids: the player keeps the id every room gives him (game.MY_SLOT 0: the header, the host, the HUD's
    replies), which the client seats on his team's first start point; the AI of that seat, if any, takes the seat
    the table left him (seating), so every start point still has one player and nobody is moved after the start. An
    AI player's id and hero uid are 200 + its seat (200 is a multiple of 8: the client's pick is the seat), its
    troops' uids 2000 + 10 x seat + the preset's troop slot;
  - the server's side numbers stay relative (0 the player's side: game.PLAYER_TEAM, status.side) while the client
    is told the map's teams;
  - an AI hero's abilities: its class's kit at its level (skills.battle_abilities), the row's own skills, and the
    abilities its Hero_AI section names (the client's AI starts only abilities in the list)."""
import functools
import struct
import time

from . import guild, obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, Writer

C2S_AI_START, S2C_AI_START = 0x3e5e, 0x3e5f
S2C_PVP_RESULT = 0x5043
NO_ROOM = 0x402                 # 0x3e5f: text 5036 "Cannot enter the room." (the constant sent before this module)
SEATS, TEAM_SEATS = 16, 8
AI_PLAYER = 200                 # ours: an AI player's id and its hero's troop uid are 200 + the seat: a multiple of 8
                                # (the client's own seating, start_index), under 5000, not ours (0) nor the NP
                                # owner 0xfa (250); a player's troop uid is under 10000
AI_TROOP = 2000                 # ours: an AI player's troop uid is 2000 + 10 x seat + its preset troop slot (1..8)
AI_CHAR = 900000                # ours: an AI hero's character id is 900000 + its AIPC_ID (the player key's base)
TROOP_SLOTS = range(1, 9)       # %AIPCPreset AIPC_Troop_Slot_01..08
RESULT_WON = 1                  # 0x5043's first byte
NO_MATCH_TYPE = 5               # 0x5043's second: no match type (the waiting room's reset value), no numbers shown
NEUTRAL = 10                    # ours [I]: a face slider's middle (the saves' sliders run 0..20)
COMBO_KEYS = (4004, 4005)       # Hero_AI's L_CLICK / R_CLICK: combo keys to the hero's AI, not abilities to start
GEAR = (("MAIN_WEAPON", "MAIN_WEAPON_ENCHANT"), ("SUB_WEAPON", None), ("UPPERBODY", "UPPERBODY_ENCHANT"),
        ("LOWERBODY", "LOWERBODY_ENCHANT"), ("SHOULD", "SHOULD_ENCHANT"), ("GAUNTLET", "GAUNTLET_ENCHANT"),
        ("BOOTS", "BOOTS_ENCHANT"), ("LOOK_UPPER", None), ("LOOK_LOWER", None), ("LOOK_SHOULDER", None),
        ("LOOK_GAUNTLET", None), ("LOOK_BOOTS", None))      # %AIPCHero's item columns and their enchant columns


def _int(v, default=0):
    return int(v) if str(v).lstrip("-").isdigit() else default


@functools.cache
def _rows(section, key):
    return {r[key]: r for r in tables.sections("aipctrooptable")[section]}


def seats(spot):
    """The spot's 16 seats (aipctrooptable %AIPVP AIPC_ID_0..15): None the player's ("-"), else the seat's AIPC_ID;
    None for a spot without a row."""
    row = _rows("AIPVP", "SpotID").get(str(spot))
    if row is None:
        return None
    return tuple(None if row[f"AIPC_ID_{k}"] == "-" else _int(row[f"AIPC_ID_{k}"]) for k in range(SEATS))


def ai_room(spot):
    """A spot whose room is the PvP against AI: Spot_Sub_Type PVP_AI with an %AIPVP row that leaves one seat to the
    player and names a preset on every other, and a zone file whose start groups are the 16 seats (StartPointID =
    the seat, in order, team 0 then team 1)."""
    from . import zone
    row = tables.by_id("spottable").get(str(spot)) or {}
    held = seats(spot)
    if not (row.get("Spot_Sub_Type") == "PVP_AI" and held is not None and held.count(None) == 1
            and all(str(a) in _rows("AIPCPreset", "AIPC_ID") for a in held if a is not None) and zone.available(spot)):
        return False
    groups = [(g.get("StartPointID"), g.get("LongTeamID")) for g in zone.for_spot(spot)["PlayerStartPointInfoData"]]
    return groups == [(k, k // TEAM_SEATS) for k in range(SEATS)]


def start_index(pid):
    """The client's own pick among a team's eight start points for a player id (FindPlayerStartPoint 0x140cd6f20:
    an id above the count less the count, then modulo it)."""
    return (pid - TEAM_SEATS if pid > TEAM_SEATS else pid) % TEAM_SEATS


def seating(spot):
    """The room's 16 seats: the table's (seats), with the player on the seat the client gives his id (his team's
    start point number start_index(game.MY_SLOT), the first) and the AI of that seat on the one the table left the
    player. Ours: the original's ids were the seats; the player's stays the room's 0."""
    from . import game
    held = list(seats(spot))
    table = held.index(None)
    mine = table - table % TEAM_SEATS + start_index(game.MY_SLOT)
    held[table], held[mine] = held[mine], None
    return tuple(held)


def my_seat(spot):
    return seating(spot).index(None)


def start_place(spot, seat, place=0):
    """(x, 0, z) of a seat's start group (the zone's PlayerStartPointInfoData with StartPointID = the seat) at one of
    its nine places: 0 the hero's, a troop's its lineup slot, as game.deck_offset reads a mission's group [I]; past the
    group's places 300 apart beside the hero (ours, as there)."""
    from . import zone
    group = next(g for g in zone.for_spot(spot)["PlayerStartPointInfoData"] if g.get("StartPointID") == seat)
    places = group["StartPointInfoData"]
    if place < len(places):
        return round(places[place]["PosX"]), 0, round(places[place]["PosZ"])
    return round(places[0]["PosX"]) + 300 * place, 0, round(places[0]["PosZ"])


def ai_name(preset):
    """An AI player's name: textnpname <AIPC_Name>/TEXT ("Roger", "Virginia": the [Cheering Squad] names); without
    the row or the table, "AI <id>"."""
    key = preset["AIPC_Name"] + "/TEXT"
    try:
        rows = tables.sections(r"text\eng\textnpname_eng")["TextTable"]
    except KeyError:
        rows = ()
    for r in rows:
        k, text = list(r.values())[:2]
        if k == key and text:
            return text.encode("latin-1", "ignore").decode("latin-1")
    return "AI " + preset["AIPC_ID"]


def ai_look(h, cls):
    """The look blob of an %AIPCHero row, laid out as a character's (world.char_create: 21 face sliders, 5 colour U / V
    pairs, 5 coded part ids): HeroHair / HeroFace are customize %Hair / %Face ids of the hero's class (Glen 1 / 1,
    Isabella 7 / 7-9, Regnier 14 / 14-16, Olivia 22 / 22); HeroHair_Color / HeroSkinColor (1 on all 132 rows) are read
    as the place in the class's customize %Base HAIR_COLOR / SKIN_COLOR list, whose first entries are a new
    character's own colours [I]; eyes and lips the class's first; the sliders in the middle (ours)."""
    lists = {r["Name"]: [_int(v, -1) for k, v in r.items() if k.startswith("Parameter")]
             for r in tables.sections("customize")["Base"] if r["HeroId"] == str(cls)}
    colours = {_int(r["Id"]): (_int(r["X"]) & 0xFF, _int(r["Y"]) & 0xFF) for r in tables.sections("customize")["Color"]}

    def colour(name, nth=1):
        ids = [i for i in lists.get(name, ()) if i >= 0]
        return colours.get(ids[min(max(nth, 1), len(ids)) - 1], (0xFF, 0xFF)) if ids else (0xFF, 0xFF)

    uv = (colour("HAIR_COLOR", _int(h.get("HeroHair_Color"), 1)) + colour("EYE_COLOR")
          + colour("SKIN_COLOR", _int(h.get("HeroSkinColor"), 1)) + colour("LIPS_COLOR") + (0xFF, 0xFF))
    parts = [_int(h.get("HeroHair"), -1), _int(h.get("HeroFace"), -1), -1, -1, -1]
    return (bytes([NEUTRAL] * 21) + bytes(uv) + b"".join(obf.u32(p & 0xFFFFFFFF) for p in parts) + bytes(5)).hex()


def ai_char(preset):
    """An AI player's hero as a character record, so the room reads it as it reads the player's (game.player_struct,
    hero.char_stats, skills.battle_abilities): class, level, the row's gear on its equipment indexes with its
    enchants (a column naming no item is left empty: the level-16 heroes carry no weapon, Olivia's LOOK_GAUNTLET
    59002830 is no item), the row's own skills, its look."""
    from . import hero, items
    h = _rows("AIPCHero", "AIPCHero_Id")[preset["AIPCHeroID"]]
    cls = hero.HERO_CODE.index(h["AIPC_Type"])
    equip = []
    for column, enchant in GEAR:
        code = _int(h.get(column), -1)
        part = (items.row(code) or {}).get("Parts") if code > 0 else None
        if part in items.PART_INDEXES:
            equip.append({"code": code, "index": min(items.PART_INDEXES[part]), "serial": 0, "bound": True,
                          "enchant": _int(h.get(enchant)) if enchant else 0})
    own = {str(_int(h.get(f"r_ActiveSkill{k:02d}"))): max(1, _int(h.get(f"r_ActiveSkillLv{k:02d}"), 1))
           for k in range(1, 5) if _int(h.get(f"r_ActiveSkill{k:02d}")) > 0}
    return {"id": AI_CHAR + _int(preset["AIPC_ID"]), "name": ai_name(preset), "class": cls,
            "level": max(1, _int(h["LEVEL_CURRENT"], 1)), "look": ai_look(h, cls), "equip": equip, "skills": own}


def ai_kit(c):
    """{ability: level} an AI hero's troop entry lists: skills.battle_abilities of its record (the class's kit at its
    level and the row's own skills) and the abilities its class's Hero_AI section names, at 1, since the client's
    hero AI starts only abilities in the list. Left out: Hero_AI's 4004 / 4005 (L_CLICK / R_CLICK: the AI's tick
    0x140bf9800 queues them as the mouse's combo keys, no player's list holds them) and an id without an
    abilitytypeinfo row (the client asserts on it)."""
    from . import hero, skills
    known = {r["AbilityId"] for r in tables.sections("abilitytypeinfo")["Basic"]}
    kit = {a: lv for a, lv in skills.battle_abilities(c).items() if str(a) in known}
    for r in tables.sections("hero_ai").get(hero.HERO_CODE[c["class"]].title(), ()):
        for k in range(1, 11):
            a = _int(r.get(f"Skill{k}"))
            if a > 0 and a not in COMBO_KEYS and str(a) in known:
                kit.setdefault(a, 1)
    return kit


def ai_troop(seat, slot, row):
    """One troop of an AI player from its %AIPCTroop row: the trooptable row at AIPC_TroopLevel (troops.level_row, with
    its passives' traits as a deck troop's room row), its units and their hp, its skills."""
    from . import status, troops
    level = max(1, _int(row["AIPC_TroopLevel"], 1))
    pick = lambda kind: {_int(row.get(f"{kind}{k:02d}")): max(1, _int(row.get(f"{kind}{k:02d}LV"), 1))
                         for k in range(1, 5) if _int(row.get(f"{kind}{k:02d}")) > 0}
    skills, passives = pick("r_ACTIVESKILL"), pick("r_PASSIVESKILL")
    stats = troops.level_row(row["TROOP_ID"], level, traits=status.passive_traits(passives, level, live=False))
    return {"uid": AI_TROOP + 10 * seat + slot, "slot": slot, "id": _int(row["TROOP_ID"]), "level": level,
            "row": stats, "units": stats["UNIT_COUNT"], "unit_hp": troops.unit_hp(stats), "skills": skills,
            "passives": passives}


def players(spot, char, deck):
    """The room's 16 players in seat order: the map's team (seat // 8), the player id, the hero's troop uid and the
    troops; for the 15 AI players their preset's AI set, character record, abilities, stats and hp."""
    from . import game, troops
    out = []
    for seat, aipc in enumerate(seating(spot)):
        team = seat // TEAM_SEATS
        if aipc is None:
            out.append({"seat": seat, "team": team, "pid": game.MY_SLOT, "ai": None, "hero": 0, "name": char["name"],
                        "troops": [{"uid": uid, "slot": uid} for uid in deck]})
            continue
        preset = _rows("AIPCPreset", "AIPC_ID")[str(aipc)]
        c = ai_char(preset)
        mine = [ai_troop(seat, k, _rows("AIPCTroop", "AIPCTroop_Id")[preset[f"AIPC_Troop_Slot_{k:02d}"]])
                for k in TROOP_SLOTS if preset[f"AIPC_Troop_Slot_{k:02d}"] in _rows("AIPCTroop", "AIPCTroop_Id")]
        mine = [t for t in mine if troops.troop_row(t["id"]) is not None]
        stats = game.hero_stat_values(c)
        out.append({"seat": seat, "team": team, "pid": AI_PLAYER + seat, "ai": aipc, "hero": AI_PLAYER + seat,
                    "name": c["name"], "char": c, "kit": ai_kit(c), "stats": stats,
                    "hp": max(1, stats.get(0, game.HERO_HP)), "troops": mine,
                    # the AI flag: %AIPCTroopAISet's key, never 0 (1, the Aggressive set, is the client's own
                    # default program 11000 when the lookup misses, 0x1407e87c1)
                    "set": max(1, _int(preset.get("ActiveTroopAISet"), 1))})
    return out


def room(s):
    """The session's PvP room record (set by send_start), or None in any other room."""
    return s.data.get("pvp")


def relative(team, mine):
    """The server's side number of one of the map's teams: 0 the player's team, 1 the other one of the two; the
    neutral and monster teams (255, 2) as they are (status.side: anything but 0 is the other side)."""
    return 0 if team == mine else 1 if team in (0, 1) else team


def record(c):
    """The character's count of PvP against AI rooms: played (started) and won; the difference is the rooms lost
    (left before the win: ours)."""
    return c.setdefault("pvp_ai", {"played": 0, "won": 0})


def send_start(s, spot, header):
    """The room start for an AI room: game.send_start_header's own header, then 16 start records, 16 player structs
    and every player's troops (the module docstring), then the go. The player brings his deck troops as into a
    mission (troops.room_deck: the first Limit_Troop_1 filled main-deck slots; game.deploy takes none in a room
    that is no mission)."""
    from . import game, skills, troops
    char = game.hero_char(s)
    deck = s.data["deck"] = dict(troops.room_deck(char, spot, s.data.get("difficulty", 0)))
    seated = players(spot, char, deck)
    me = my_seat(spot)
    s.data["pvp"] = {"spot": spot, "seat": me, "team": me // TEAM_SEATS, "players": seated}
    w = Writer(game.S2C_SPOT_ROOM_START).obool(False).raw(bytes(header)).u16(len(seated))
    for p in seated:
        w.raw(struct.pack("<HH", p["team"], p["pid"]) + bytes([OBOOL_FALSE]) + struct.pack("<H", 1 + len(p["troops"])))
    s.send(w)
    w = Writer(game.S2C_START_PLAYER_INFO).u16(len(seated))
    for p in seated:
        if p["ai"] is None:
            block = game.player_struct(char, spot, deck.values())
        else:
            block = bytearray(game.player_struct(p["char"], spot, p["troops"]))
            struct.pack_into("<I", block, 0xa9, p["set"])       # -> Player +0x358 / +0x35c: an AI player
        w.raw(bytes(block)).cstr(p["name"]).cstr(guild.name_of(char) if p["ai"] is None else "")
    s.send(w)
    w = Writer(game.S2C_START_TROOP_INFO).u16(sum(1 + len(p["troops"]) for p in seated))
    for p in seated:
        if p["ai"] is None:
            game.write_troop(w, slot=0, uid=1, troop_id=game.HERO_TROOP_ID, leader_id=char["class"],
                             leader_level=char["level"], abilities=sorted(skills.battle_abilities(char).items()))
            for uid, t in deck.items():
                game.write_deck_troop(w, uid, t, char)
            continue
        c = p["char"]
        game.write_troop(w, slot=0, uid=1, troop_id=game.HERO_TROOP_ID, leader_id=c["class"], leader_level=c["level"],
                         hp=p["hp"], abilities=sorted(p["kit"].items()), troop_uid=p["hero"])
        for t in p["troops"]:
            game.write_troop(w, slot=t["slot"], uid=t["units"], troop_id=t["id"], leader_id=None, leader_level=0,
                             hp=t["unit_hp"] * t["units"], units=t["units"], abilities=sorted(t["skills"].items()),
                             passives=sorted(t["passives"].items()), barracks_uid=(c["id"] << 8) | t["slot"],
                             troop_uid=t["uid"])
    s.send(w)
    s.send(Writer(game.S2C_SPOT_ROOM_START).obool(True))
    log.info("pvp against AI %d: seat %d (team %d), %d players, %d troops", spot, me, me // TEAM_SEATS, len(seated),
             sum(1 + len(p["troops"]) for p in seated))


def zone_entry(p, uid, pos, troop=0):
    """An AI player's troop as s.data["zone_troops"] holds a zone troop, so the room's shared paths read it
    (status.side, the kill feed, the journal): its side, its player as the force, no NP row (TroopTableID 0: no exp,
    loot, quest count or Battle Point is the table's for it), no respawn."""
    return {"TroopID": uid, "TroopTableID": 0, "TeamNum": p["side"], "ForceNum": p["pid"], "PosX": pos[0], "PosZ": pos[2],
            "UseSpawnSystem": 0, "RespawnLoopNum": 0, "NPLeaderID": -100, "AIPC": p["ai"], "Troop": troop}


def start_room(s, state, troop_down):
    """The loading's end in an AI room, in game.load_progress's order: the host change and the render start, the
    battle with the player's hero and deck troops as in any room, then the 15 AI players' records: a hero as a troop
    of no units led by himself (Battle.add_np with a leader, as the missions' CPU heroes Glen and Thompson: a fall of
    his is a troop's, not the player's death window), his record the hero's own (game.hero_combatant of his character
    record, with his abilities' levels and a hero's regeneration), each troop its units (combat.combatant_troop).
    A second later every start troop's place and state, three seconds later the zone's troops and props."""
    from . import changetroop, combat, director, game, hero, skills, status
    r = room(s)
    spot = r["spot"]
    s.data["started"] = True
    s.data["started_at"] = time.monotonic()
    journal("room", ev="start", spot=spot)
    game.snapshot(s, first=True)
    s.send(Writer(game.S2C_HOST_CHANGE).u16(game.MY_SLOT))
    s.send(Writer(game.S2C_ALL_LOADED).obool(False))
    game.send_actions(s, [game.ACT_RENDER_START])
    s.later(1.0, lambda: (place(s), status.room_start(s), changetroop.start(s),
                          game.send_actions(s, [director.ACT_CAMERA_RESTORE_DEFAULT], [game.ACT_FADE, 1, 0, 1],
                                            [game.ACT_ENABLE_INPUT, 1])))
    battle = s.data["battle"] = combat.Battle()
    s.data["hit_callbacks"] = (game.send_troop_hp, troop_down)
    char = game.hero_char(s)
    battle.add_hero(0, game.hero_max_hp(s), c=game.hero_combatant(char))
    game.deck_enters(s, state, battle)
    s.data["pools"] = game.pools_for(char, spot, (s.data.get("deck") or {}).values())
    s.data["pools"]["hp_rec"] = hero.regen_tick(char)
    s.data["kit"] = skills.battle_abilities(char)
    combat.start_regen(s)
    s.data["hero_pos"] = start_place(spot, r["seat"])      # until his first 0x50b0: where a revive puts him
    troops_in = s.data.setdefault("zone_troops", {})
    for p in r["players"]:
        p["side"] = relative(p["team"], r["team"])
        if p["ai"] is None:
            continue
        rec = dict(game.hero_combatant(p["char"]), team=p["side"], skills=dict(p["kit"]),
                   hp_rec=hero.regen_tick(p["char"]))
        battle.add_np(p["hero"], 1, 0, c=rec, leader_hp=p["hp"], leader_c=rec)
        troops_in[p["hero"]] = zone_entry(p, p["hero"], start_place(spot, p["seat"]), game.HERO_TROOP_ID)
        for t in p["troops"]:
            battle.add_np(t["uid"], t["unit_hp"], t["units"],
                          c=combat.combatant_troop(t["row"], p["side"], t["skills"], t["passives"]))
            troops_in[t["uid"]] = zone_entry(p, t["uid"], start_place(spot, p["seat"], t["slot"]), t["id"])
    c = record(char)
    c["played"] += 1
    if state is not None:
        state.save()
    s.later(3.0, lambda: (spawn_zone(s), game.send_zone_props(s, spot, char),
                          game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1],
                                            [game.ACT_CONTROL_MODE, game.start_control_mode(spot)])))
    journal("pvp", ev="start", spot=spot, seat=r["seat"], team=r["team"], played=c["played"], won=c["won"],
            players=[[p["seat"], p["pid"], p["name"], p["ai"]] for p in r["players"]])


def troop_states(s):
    """[(position, write_troop_state arguments)] of every start troop: the player's hero and deck troops as
    game.send_enter_cell / write_deck_state write them, the AI players' the same way from their records; each at its
    seat's start group, on the map's team, an AI troop under its player's id."""
    from . import combat, game, troops
    r = room(s)
    spot, battle, char = r["spot"], s.data["battle"], game.hero_char(s)
    hit = lambda kind: {game.STAT_IDS["HIT_RESIST"]: game.hit_resist("trooptype", kind)} \
        if game.hit_resist("trooptype", kind) > 0 else None
    out = []
    for p in r["players"]:
        if p["ai"] is None:
            out.append((start_place(spot, p["seat"]), dict(
                flags=game.HERO_FLAGS, stats=game.hero_stats(s), level=game.hero_level(s), hp=game.hero_max_hp(s),
                team=p["team"])))
            for uid, t in (s.data.get("deck") or {}).items():
                row = troops.room_row(char, t)
                hp = round(combat.Battle.total(battle.troops[uid])) if uid in battle.troops \
                    else troops.unit_hp(row) * row["UNIT_COUNT"]
                out.append((start_place(spot, p["seat"], uid), dict(
                    flags=game.HERO_FLAGS, uid=uid, troop_id=t["id"], hp=hp, team=p["team"], units=row["UNIT_COUNT"],
                    level=t["level"], troop_stats=hit(row.get("TroopType")))))
            continue
        c = p["char"]
        pools = game.pools_for(c, spot, p["troops"])
        out.append((start_place(spot, p["seat"]), dict(
            flags=game.HERO_FLAGS, uid=p["hero"], hp=p["hp"], team=p["team"], owner=p["pid"], level=c["level"],
            stats={**p["stats"], **game.pool_stats(pools)})))
        for t in p["troops"]:
            out.append((start_place(spot, p["seat"], t["slot"]), dict(
                flags=game.HERO_FLAGS, uid=t["uid"], troop_id=t["id"], hp=t["unit_hp"] * t["units"], team=p["team"],
                owner=p["pid"], units=t["units"], level=t["level"], troop_stats=hit(t["row"].get("TroopType")))))
    return out


def place(s):
    """Every start troop into the world: 0x50cb (a known troop is moved there) and 0x50b8 (its hp, level and stats:
    a hero's speed is stat 14 of this block) for each, the player's deck troops enabled at once as in a mission
    (game.send_enter_cell); then the AI players' passives' held statuses, as the player's get theirs
    (status.room_start)."""
    from . import game, status
    states = troop_states(s)
    for pos, kw in states:
        w = Writer(game.S2C_ENTER_CELL_TROOP).u16(1)
        w.obool(False)                                  # no player block: the room start built the troop
        game.write_troop_state(w, pos, **kw)
        s.send(w)
        uid = kw.get("uid", 0)
        if uid in (s.data.get("deck") or {}):
            game.troop_order(s, uid, [game.ACT_ENABLE_TROOP, 0, uid, 1, 1])
    for pos, kw in states:
        w = Writer(game.S2C_MISSION_TROOP_INFO)
        game.write_troop_state(w, pos, **kw)
        s.send(w)
    for p in room(s)["players"]:
        if p["ai"] is not None:
            status.troop_passives(s, p["hero"], p["kit"])
            for t in p["troops"]:
                status.troop_passives(s, t["uid"], t["passives"])


def spawn_zone(s):
    """The zone's NP troops (its gates, towers, engines and garrisons), every activated one as a field's
    (game.spawn_zone_troop: its table row, AI program and record). The client is told the map's team; where the
    player sits on team 1 (20955) the server's own copy takes the relative side afterwards (the record's team and
    the zone entry's TeamNum: combat's mates and status.side read those)."""
    from . import game, zone
    r = room(s)
    n = 0
    for t in zone.for_spot(r["spot"])["NPCTroopInfoData"]:
        if not (t.get("IsActivated") and t.get("SpawnActivated")) or not game.spawn_zone_troop(s, t):
            continue
        n += 1
        side = relative(t.get("TeamNum", game.NP_TEAM), r["team"])
        if side != t.get("TeamNum", game.NP_TEAM):
            uid = t["TroopID"]
            bt = s.data["battle"].troops[uid]
            for key in ("c", "leader_c"):
                if bt.get(key) is not None:
                    bt[key] = dict(bt[key], team=side)       # a copy: the records are cached and shared
            s.data["zone_troops"][uid] = dict(s.data["zone_troops"][uid], TeamNum=side)
    log.info("pvp against AI %d: %d zone troops spawned", r["spot"], n)


def enemies(s):
    """The troop uids the win waits on: the heroes and troops of the other team's players."""
    r = room(s)
    return [uid for p in r["players"] if p["team"] != r["team"] for uid in [p["hero"]] + [t["uid"] for t in p["troops"]]]


def check_win(s, state):
    """Ours (the module docstring): the room is won once every hero and troop of the other team's players is down."""
    from . import combat
    battle = s.data.get("battle")
    if room(s) is None or battle is None or s.data.get("mission_won"):
        return False
    foes = enemies(s)
    if not foes or any(combat.Battle.total(battle.troops[u]) > 0 for u in foes if u in battle.troops):
        return False
    won(s, state)
    return True


def won(s, state):
    """The room's win: counted on the character, told by 0x5043 (won, no match type, no numbers, no reward). The
    result window's leave is 0x4040 (game.leave_mission: back to the spot the hero left for the world map)."""
    from . import game
    s.data["mission_won"] = True                        # (changetroop's income stops; the leave reads it)
    c = record(game.hero_char(s))
    c["won"] += 1
    if state is not None:
        state.save()
    now = time.monotonic()
    secs = int(now - s.data.get("started_at", now))
    s.send(Writer(S2C_PVP_RESULT).u8(RESULT_WON).u8(NO_MATCH_TYPE).u32(0).u32(0).u8(0))
    log.info("pvp against AI %d won in %d s (%d of %d)", room(s)["spot"], secs, c["won"], c["played"])
    journal("room", ev="won", spot=room(s)["spot"], secs=secs, pvp="ai", played=c["played"], won=c["won"])


def make_game(role, state, troop_down):
    """The game role's part, after game.make's own handlers (troop_down is its fall handler, for the hits the server
    starts itself): the loading's end of an AI room is start_room's, and the host's troop report (0x50b0, every
    1.5 s) is where the win is looked for, so a fall by any path (a hit report, a cast, a status tick) ends the room
    within that beat. Any other room goes on to the handlers this wraps."""
    from . import game
    load, sync = role.handlers[game.C2S_LOAD_PROGRESS], role.handlers[game.C2S_TROOP_SYNC]

    @role.on(game.C2S_LOAD_PROGRESS, quiet=getattr(load, "quiet", False))
    def load_progress(s, pkt):
        if room(s) is None:
            return load(s, pkt)
        b = pkt.rest()
        pct = b[0] if b else 0
        log.info("load progress %d%%", pct)
        s.send(Writer(game.S2C_LOAD_PROGRESS).u32(game.MY_SLOT).u8(pct))
        if pct >= 100 and not s.data.get("started"):
            start_room(s, state, troop_down)

    @role.on(game.C2S_TROOP_SYNC, quiet=getattr(sync, "quiet", True))
    def troop_sync(s, pkt):
        sync(s, pkt)
        if room(s) is not None:
            check_win(s, state)


def make(role, state):
    """The world role's part: the AI room's start."""
    from . import world

    @role.on(C2S_AI_START)
    def ai_start(s, pkt):
        """0x3e5e: a spot with an AI room answers 0, keeps the battle spot and names the game server, as the solo
        start 0x3f48 does for a room entered from the world map (world.mission_door: a mission record an escaped
        room left goes, so the result's leave ends at the spot the hero left). Anything else keeps the refusal:
        another spot, a room change already under way (its 0x3f41 is still to come), or a session that never
        learnt the game server's address (it comes with the town entry)."""
        b = pkt.rest()
        spot = obf.dec_u32(b[:4]) if len(b) >= 4 else 0
        addr = s.data.get("game_addr")
        if s.data.get("char") is None or not ai_room(spot) or addr is None or s.data.get("entering"):
            log.info("pvp against AI at spot %d refused (room %s, game address %s, entering %s)", spot, ai_room(spot),
                     addr is not None, s.data.get("entering"))
            s.send(Writer(S2C_AI_START).u16(NO_ROOM))
            return
        s.send(Writer(S2C_AI_START).u16(0))
        world.mission_door(s, state, spot)
        s.data["battle_spot"] = spot
        journal("warp", how="pvp ai", spot=spot)
        world.send_game_server(s, spot, *addr)

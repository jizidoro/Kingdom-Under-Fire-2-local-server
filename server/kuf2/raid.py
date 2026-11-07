"""A raid's checkpoints and its binding (Spot_Sub_Type Raid_16: 20950 Scourged Mountains, 20951 Grave of Time; 20952 has
no zone file). The tables, the default limit and the revive ban are party.py's (raid_row, checkpoints, restart_points,
on_troop_down); this module is what a fallen boss changes in the room and what stays on the character afterwards. It
answers no request: game.py and party.py call in. The dig and every verdict:
planning/agents/reports/2026-11-05_contract3-raid.md.

S2C 0x5139, a checkpoint armed (0x140d00d00, dispatcher 0x140ceff90): u32 id (a pointer reader of 4: shorter crashes).
  The gate 0x140d00d50 drops it while common+0x1674 is -1. common+0x1628 is the room info (reset 0x140624660, every id
  -1): +8 difficulty, +0x34 spot, +0x4c = common+0x1674 the party's spot, +0x50 = common+0x1678 the checkpoint. +0x4c
  has two writers, the handlers of 0x4058 (0x140663020) and 0x4066 (0x1406637c0): for a Raid_16 spot of a team in a party,
  room +0xa8c = team +0xa8 (0x5469's spot) and room +0xa90 = team +0xc4 (0x5469 +0x12); 0x405c's handler copies the room
  over common (0x14065ab90). So it passes on party.py's way in, 0x5469 -> 0x4058 -> 0x405c, and nothing resets it from
  there to the battle (the resets: GameStateWorldMap / GameStateTown enter, 0x3e4d, 0x3e5d, scene 0x57). A raid entered
  by 0x3f48 alone never opens it: the client drops the packet, the server's limit and restart below still hold.
  Past the gate: common+0x1678 = id, team +0xc4 = id (0x140d65730), text 0x16062 "Checkpoint activated.", and the HUD's
  limit = the row's Number_Resurrection (0x1418c97f0 +8 -> 0x140e0f220, HUD +0x24). The used count (map +0x38, from
  0x50f5 / 0x513c) is not touched, so it is not reset here either (nothing shows the original did).

Arming is OURS. %Check_Point's Active_Trigger_Phase / Sub are phases of the raid's script, which is not shipped, so
the rule is ours: a checkpoint arms when a troop of its Boss_Troop_ID falls in the room (at the room's difficulty:
game.difficulty_troop). What that reaches with the fallback's waves: 20950's first (295410 결계석3, wave 29 on Normal) and
last (Manelos: the win follows), 20951's 296010, 296020, 296030, 296050. Never: 295010-30 and their Hard / Hell rows and
296000, whose bosses are reward dummies no fallback spawns (force 41000 / 10050, game.reward_dummies: the script killed
them), and 296040, which names no boss.

Armed: the room's revive limit is the last armed row's Number_Resurrection (limit, in game.revive_here); the restart
points of the armed rows join the camp revive's start points (armed_points, in game.revive_point), so the revive goes
to the nearest of those. No resurrection left: the HUD refuses the revive itself (0x14068f0b0, text 0xd03d, nothing
sent) and the camp button, which no ban or limit gates (0x14085a16e jumps straight to the builder 0x140eff140), is the
way out: it is the move "to the closest checkpoint". Its text 0x16068 is in no client code or data (no immediate, no
table): the original's server or script sent it. The one way to print a system text by id from here is the action
ActGuiShowSystemTextWithGuild 0xc779 of S2C 0x5087 (0x140b36290: u32 a1 unread, u32 text, cstr, u32 a4 unread ->
GetSystemText 0x140567c50 -> 0x140d631c0, colour 0xffff33). It fills %1% with the cstr; a text without %1% is safe, the
client's format object has its exception bits cleared (0x140514ad0, +0x68 = 0; 0x140511ed0 returns). Printed at the fall
(ours: when is not in the client). The move is the player's press: no timer moves a hero of ours.

The binding. key (raid spot, difficulty) -> checkpoint id and a completed flag, in the client's GamePlayInfo map.
  Entry, 10 bytes: +0 u8 difficulty (3 asserts and is skipped), +1 coded u32 spot (-1 skipped), +5 coded bool completed,
  +6 u32 checkpoint id.
  S2C 0x5a4a (0x1406768f0): clears the map, u16 n, n entries.  S2C 0x5a4b (0x140676ae0): one entry, an upsert (a pointer
  reader of 10: shorter crashes).  S2C 0x5a4c (0x1406752a0): no body, clears the map, refreshes the room and the board,
  text 0x160c1 "Checkpoint has been reset."
  The client's entry gate 0x140d6bec0, for Raid_16: flag -> 0x2407 (text 0x160be "You already completed this Raid.");
  a value at this key -> pass; a value at another difficulty -> 0x2408 (0x16063 "bound"). An empty map passes all. The
  panels compare the binding with room +0xa90 (0x14065d91a, 0x140661eac), so 0x5469 +0x12 carries it (bound_checkpoint).
  No table holds a schedule; the notes say only weekly, locked by the last boss (OFFICIAL-NOTES.md:228). RESET_SCHEDULE
  is the owner's question (ROADMAP Q72): built, wired, tested, inert. With None nothing below sends, saves or refuses.
  Not built with it: the reward a bound character may take ("You can acquire the reward when the current party passes
  by my checkpoint", 0x160c2), and starting a bound party at its checkpoint: both are the script's.
  Saved: c["raid_binding"] = {"period": n, "raids": {"spot/difficulty": {"checkpoint": id, "completed": bool}}}.
"""
import time

from . import obf
from .net import journal, log
from .packet import Writer

S2C_CHECKPOINT = 0x5139
S2C_BINDINGS, S2C_BINDING, S2C_BINDING_RESET = 0x5a4a, 0x5a4b, 0x5a4c
ACT_SYSTEM_TEXT = 0xc779
TEXT_NO_RESURRECTION = 0x16068  # "You will move to the closest checkpoint because you don't have resurrection count."
COMPLETED = 0x2407              # 0x5462, 0x5473 (the room error map 0x140d680e0): text 0x160be
BOUND_ELSEWHERE = 0x2408        # the same: text 0x16063
DAY, WEEK = 86400, 7 * 86400
EPOCH_WEEKDAY = 3               # 1970-01-01, a Thursday (Monday 0)

RESET_SCHEDULE = None           # the owner's pick (ROADMAP Q72): (weekday, Monday 0, hour UTC), weekly; None: never bound


def armed(s):
    """The rows of party.checkpoints this room has armed, in the order their bosses fell."""
    return s.data.get("raid_armed", [])


def armed_points(s):
    """The StartPointIDs the room's armed checkpoints restart at (game.revive_point stops holding them back)."""
    return frozenset(row["point"] for row in armed(s))


def limit(s, default):
    """The revive limit in this room: the last armed checkpoint's Number_Resurrection, else the spot's (game.revival).
    The HUD does the same past 0x5139's gate; a bound character's HUD starts at his checkpoint's (common+0x1678 from
    0x5469 +0x12), stricter than this until one arms, and the HUD refuses first."""
    rows = armed(s)
    return rows[-1]["resurrections"] if rows else default


def on_troop_down(s, state, t):
    """For game.troop_down, a zone troop t fell: the checkpoints whose boss it is arm, once each (module docstring)."""
    from . import game, party
    spot, difficulty = s.data.get("spot"), s.data.get("difficulty", 0)
    rows = party.checkpoints(spot, difficulty)
    if not rows:
        return
    fallen = game.difficulty_troop(t["TroopTableID"], difficulty)
    held = s.data.setdefault("raid_armed", [])
    for row in rows:
        if row["boss"] == fallen and row not in held:
            held.append(row)
            s.send(Writer(S2C_CHECKPOINT).u32(row["id"]))
            bind(s, state, game.hero_char(s), spot, difficulty, checkpoint=row["id"])
            log.info("raid %d checkpoint %d armed: restart point %d, %d resurrections", spot, row["id"], row["point"],
                     row["resurrections"])
            journal("raid", ev="armed", spot=spot, difficulty=difficulty, checkpoint=row["id"], point=row["point"])


def on_hero_down(s):
    """For game.troop_down, the hero fell: with a checkpoint armed and no resurrection left the client's text says the
    camp revive is what comes next (module docstring). Nothing armed: no checkpoint to move to, no text."""
    from . import game
    rows = armed(s)
    if rows and s.data.get("revivals", 0) >= rows[-1]["resurrections"]:
        game.send_actions(s, [ACT_SYSTEM_TEXT, 0, TEXT_NO_RESURRECTION, "", 0])


def on_won(s, state, c, spot, difficulty):
    """For party.on_mission_won: the raid is done for this period (the notes: locked by the last boss)."""
    rows = armed(s)
    bind(s, state, c, spot, difficulty, checkpoint=rows[-1]["id"] if rows else None, completed=True)


def _start():
    weekday, hour = RESET_SCHEDULE
    return (weekday - EPOCH_WEEKDAY) % 7 * DAY + hour * 3600


def period(now=None):
    """Which reset period a moment falls in: the weeks since the schedule's first moment after the epoch."""
    return int(((time.time() if now is None else now) - _start()) // WEEK)


def next_reset(now=None):
    """Seconds from a moment to the next reset."""
    t = time.time() if now is None else now
    return (period(t) + 1) * WEEK + _start() - t


def _key(spot, difficulty):
    return f"{spot}/{difficulty}"


def raids(c, now=None):
    """The character's binding of this period, {key: {"checkpoint", "completed"}}: empty with no schedule, with nothing
    bound and past a reset."""
    b = (c or {}).get("raid_binding")
    return b["raids"] if RESET_SCHEDULE is not None and b and b["period"] == period(now) else {}


def bound_checkpoint(c, spot, difficulty, now=None):
    """0x5469 +0x12 -> team +0xc4 -> room +0xa90, what the panels compare the binding with: 0 when not bound."""
    return raids(c, now).get(_key(spot, difficulty), {}).get("checkpoint", 0)


def refusal(c, spot, difficulty, now=None):
    """The original's answer to a notice or a start at a raid the character may not enter, or None: the client's own
    gate 0x140d6bec0 read over the saved binding (module docstring)."""
    rows = raids(c, now)
    mine = rows.get(_key(spot, difficulty), {})
    if mine.get("completed"):
        return COMPLETED
    if mine.get("checkpoint"):
        return None
    others = (rows.get(_key(spot, d), {}).get("checkpoint") for d in range(3) if d != difficulty)
    return BOUND_ELSEWHERE if any(others) else None


def entry(spot, difficulty, row):
    """The binding's 10-byte entry (0x5a4a, 0x5a4b)."""
    return bytes(Writer(0).u8(difficulty).raw(obf.u32(spot)).obool(row["completed"]).u32(row["checkpoint"]).buf)


def bind(s, state, c, spot, difficulty, checkpoint=None, completed=False, now=None):
    """A checkpoint armed or the raid won: saved on the character and told by 0x5a4b. Nothing with no schedule."""
    if RESET_SCHEDULE is None:
        return
    reset(s, state, c, now)
    b = c.setdefault("raid_binding", {"period": period(now), "raids": {}})
    row = b["raids"].setdefault(_key(spot, difficulty), {"checkpoint": 0, "completed": False})
    row["checkpoint"] = checkpoint or row["checkpoint"]
    row["completed"] = row["completed"] or completed
    state.save()
    s.send(Writer(S2C_BINDING).raw(entry(spot, difficulty, row)))


def reset(s, state, c, now=None):
    """A reset has passed: the saved binding goes, and the client's with it (0x5a4c, when there was any to clear)."""
    b = c.get("raid_binding")
    if RESET_SCHEDULE is None or not b or b["period"] == period(now):
        return
    del c["raid_binding"]
    state.save()
    if b["raids"]:
        s.send(Writer(S2C_BINDING_RESET))
        log.info("raid binding of character %s reset", c.get("id"))


def watch(s, state, c, now=None):
    """Reset the client's map at the moment it falls due, for as long as this session plays this character."""
    def due():
        if s.data.get("char") is c:
            reset(s, state, c)
            watch(s, state, c)
    s.later(next_reset(now), due)


def on_login(s, state, c, now=None):
    """For world.start_game: 0x5a4a, the whole map (it clears the client's first, so a reset passed while offline needs
    no 0x5a4c), and the watch for the next reset. Nothing with no schedule."""
    if RESET_SCHEDULE is None:
        return
    rows = raids(c, now)
    if not rows and c.pop("raid_binding", None) is not None:
        state.save()
    w = Writer(S2C_BINDINGS).u16(len(rows))
    for key, row in rows.items():
        spot, difficulty = key.split("/")
        w.raw(entry(int(spot), int(difficulty), row))
    s.send(w)
    watch(s, state, c, now)

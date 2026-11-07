"""The battle HUD's troop slots on a spot with a spottable %Point row: BattleFieldSubChangeTroop (BattleField sub-scene
0x78, vtable 0x1420a2de0, Flash UI 0xac) and the Battle Points it spends. Family 4 of
planning/todo/CONTRACT-COMPLETE-PLAN.md: troop change, upgrade, timed revival, summon, withdraw (17 requests).

When the HUD exists (read from the client, nothing from the server opens it): GameStateBattleField::OnEnter
0x140cee4c0 opens sub 0x78 (0x140cee703-0x140cee736) when the spot has a %Point row (0x141864970) with
Troop_Change_Able (+0x2c) or Troop_Upgrade_Able (+0x2d) and the player manager's +4 is not 0xfa. Its OnEnter
0x14056a240 keeps the row at +0x8d0 and builds nine slot records (0xe8 bytes at +0x40, 0x14056f0e0) from the local
player's troops (uid below 10000, not the hero's): the record index is the troop's main-deck slot (0x140d97c50 on its
barracks uid, troop +0x7e0), deployed = troop +0x94 bit 0x10, its change cost trooptable TroopChangePoint, its upgrade
type trooptype %System TroopUpgradeType. So a reserve troop is one the room start (0x3f50) built and nothing enabled.
The UI's load (0x14056f670) reads the deploy cap from the room header's first byte (common+0x165a, at most 3) and the
points from BattleField+0xcfc, which only S2C 0x50d8 writes.

  S2C 0x50d8 (0x140d1c7f0 -> 0x140d0b610), 11 bytes always, shorter crashes: u32, u8, u32 points at +5, 2 unread ->
      BattleField+0xcfc, sub 0x78 +0x3c, the HUD's number. The client refuses every paid action below its cost itself
      (text 0x276f) and never changes the total.
  S2C 0x50d9, team points, is not sent. Its handler 0x140d1c740 reads a u32 (under 4 bytes a null read) and acts only
      while sub 0x75 is open (0x1405685a0 -> UI 0xaa, BattleField+0x7dc); GameStateBattleField::OnEnter opens sub 0x75
      on Spot_Type 5 alone (0x140cee6db), and the one such spot, 880391, is a TestMap with no zone file: no room here
      has the panel, and no other reader takes the number.

The room start (game.send_start_header), on a spot whose reserve_limit is not 0 and whose room takes a deck: the
reserve goes into the player's 0x3f50 after the deck (his 0x3f4e record counts them), with no 0x50cb and no enable, and
the header's first byte is deploy_cap. The client's enable-all (ActTroopSetEnableAllTroops: 0x140ba3400 -> 0x140bc0ed0
/ 0x140bc0da0, Troop::Enable on every troop of the TroopManager) takes no notice of who is deployed, and the rooms send
it at their start and after; game.send_actions follows each with the reserve's own disable, [ACT_ENABLE_TROOP, 0, uid,
0, 1] (the kind-0 branch 0x140b2e136: the third argument 0 disables through 0x140ba3450, which finds only an enabled
troop (0x1407096f0), so a troop not enabled or not bound yet costs nothing; the fourth 1 sends dl 0 to 0x1407e2bb0,
at once rather than by its fade). That pair is ours: nothing in the data says how the original kept them out.

Troop change (%Point Troop_Change_Able; cast TroopChangeCastTime):
  C2S 0x50f7 (builder 0x140698ab0 from the slot UI 0x140571760), 5 bytes: u16 uid in the target slot (0xffff empty),
      u16 reserve troop uid, u8 HUD slot 1..3.
  S2C 0x50f8 (0x140d1cfb0): i16 result, u16 player id, the 5 bytes; the i16 always dereferenced, the rest when 0 ->
      NotiStartChangeTroop 0x14056b990 (a pending entry with the cast timer). Non-zero: nothing.
  C2S 0x50ec (builder 0x1406983b0 from the update 0x14056fb60 when the timer ends and the slot was empty), 3 bytes:
      u8 slot, u16 new uid.
  S2C 0x50ed (0x140d1cdf0): i16; 0 -> 5 bytes u16 uid, u8 slot, u16 player id -> NotiTroopEntryEnter 0x14056bf50:
      the troop (it must exist) is put at the hero (vt+0x370), reset and enabled (0x1407e3900), its HUD slot set; the
      replaced troop is disabled and cools down (trooptable TroopChangeCooldown x %Point
      AnnihilationTroopChangeCooldownRevision when it is dead).
  C2S 0x50f0 (builder 0x140698700, same sender, the slot held a troop), 5 bytes: u8 slot, coded u16 old, coded u16 new.
  S2C 0x50f1 (0x140d1cee0): i16; 0 -> 7 bytes u8 slot, u16 new uid, u16 (unread), u16 player id -> the same.
  C2S 0x50f2 (builder 0x14069b290 from 0x14056e900; the client has swapped already), 6 bytes: u16 moved uid, u16 uid
      in the target slot (0xffff), u8 target slot, u8 previous slot.
  S2C 0x50f3 (0x140d1d1d0): i16; 0 -> 6 bytes read and unused; non-zero only logs an assert.
  C2S 0x50f9 (builder 0x140698e10 from the slot's cancel 0x140571410), 3 bytes: u16 new uid, u8 slot.
  S2C 0x50fa (0x140d1d0c0): u16 result, u16 player id, u16 uid, u8, all dereferenced (under 7 bytes crashes) ->
      NotiCancelChangeTroop 0x14056bd80: 0 drops the entry, non-zero lets it run on.

Troop upgrade (Troop_Upgrade_Able; cast TroopUpgradeCastTime; troopupgrade %TroopUpgrade by type and level 1..3:
ConsumeBattlePoint, the status of Attack_AbilityID / HP_AbilityID at their levels):
  C2S 0x5101 (builder 0x1406993d0 from 0x140571bf0), 10 bytes: u32 upgrade type, u32 level wanted (troop +0xf68 + 1),
      u16 uid. 0x5103 (builder 0x140699730, the cancel) and 0x5105 (builder 0x140699a90, the update 0x14056ffb0 when
      the timer ends) carry the same three from the pending entry.
  S2C 0x5102 (0x140d1d890), 8 bytes always: i16, u32, u16 uid; 0 -> 0x14056dc40: a pending entry that keeps the u32
      (+0x18) and sends it back as the level, so the u32 is the level (requests/battle.md's "req[0:4]" would make
      0x5105 carry the type twice).
  S2C 0x5104 (0x140d1d920), 8 bytes always: u16 result, u32 (unread), u16 uid -> 0x14056df00.
  S2C 0x5106 (0x140d1d9b0), 8 bytes always: u16 result, u32 level, u16 uid -> 0x14056e210: 0 sets troop +0xf68 and
      the next cost; 0x2c4f sets the entry's timer to 0.5 s and the client asks again.

Timed revival (the HUD's revive on a spot with no %Revival row, 0x140690410; cast TroopRevivalCastTime; cost the
slot's change cost, or the hero's, x TroopRevivalRevision, 0x14056d3a0):
  C2S 0x5108 / 0x510a / 0x510c (builders 0x140699160 / 0x140699230 / 0x140699300): u16 uid.
  S2C 0x5109 / 0x510b (0x140d1da30 / 0x140d1dab0), 4 bytes always: u16 uid, i16 result.
  S2C 0x510d (0x140d1db30), 4 bytes always -> 0x14056d9c0: 0 revives the troop in place (vt+0x370(0)), 0x2c4f retries.

Summon and withdraw (Troop_Summon_Able, at most Limit_Troop_Summon; cast TroopChangeCastTime):
  C2S 0x5120 (builder 0x140699df0 in 0x14056ec10, command 3 of 0x1405719e0), 7 bytes: 5 packed x/z (the hero's
      place), u16 uid. 0x5124 (builder 0x14069a510, the update 0x14056f8a0) the same when the cast ends.
  S2C 0x5121 (0x140d1d390): i16; 0 -> 9 bytes: the 5, u16 uid, u16 player id -> 0x14056adf0.
  S2C 0x5125 (0x140d1d2c0): i16 and 9 bytes always (under 11 crashes); the uid at +5 -> 0x14056b150: placed, enabled.
  C2S 0x5122 / 0x5128 (builders 0x14069a1e0 / 0x14069ac30, the cancels): u16 uid.
  S2C 0x5123 / 0x5129 (0x140d1d530 / 0x140d1d7c0): i16, u16 uid, both always (under 4 crashes) -> 0x14056b7a0.
  C2S 0x5126 (builder 0x14069a900 from 0x1405719e0) / 0x512a (builder 0x14069af60, the update): u16 uid.
  S2C 0x5127 (0x140d1d6d0): i16; u16 uid, u16 player id used when 0. 0x512b (0x140d1d600): i16 and 4 bytes always
      (under 6 crashes): the troop is disabled.
  S2C 0x5135 (0x140d1ec70 -> 0x1407e15b0), 3 bytes (under 3 crashes): u16 uid, obool: every unit of the troop plays
      action 610 TROOP_SUMMON (TRUE) or 611 TROOP_UNSUMMON (FALSE). None of the replies above carries an action, so
      only this shows either. Its moment is ours [I]: the summon's once the troop stands, the withdrawal's just before
      0x512b disables it (at the cast's start, a cancel would leave the units on the unsummon action).

Ours, named in planning/agents/reports/2026-11-05_contract-changetroop.md: a paid action is charged when it starts
and given back when it is cancelled (the client checks the points at the click only; a refusal there is silent, one
at the timer's end would leave a dead entry on the HUD); a withdrawal is free (the official notes: "Retreat is free,
no refund"); every refusal is result 1 (no result but 0 and 0x2c4f has a text or an effect in this family).
"""
import functools
import struct
import time

from . import obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_CHANGE_START, S2C_CHANGE_START = 0x50f7, 0x50f8
C2S_CHANGE_ENTER, S2C_CHANGE_ENTER = 0x50ec, 0x50ed
C2S_CHANGE_REPLACE, S2C_CHANGE_REPLACE = 0x50f0, 0x50f1
C2S_SWAP_SLOTS, S2C_SWAP_SLOTS = 0x50f2, 0x50f3
C2S_CHANGE_CANCEL, S2C_CHANGE_CANCEL = 0x50f9, 0x50fa
C2S_UPGRADE, S2C_UPGRADE = 0x5101, 0x5102
C2S_UPGRADE_CANCEL, S2C_UPGRADE_CANCEL = 0x5103, 0x5104
C2S_UPGRADE_DONE, S2C_UPGRADE_DONE = 0x5105, 0x5106
C2S_REVIVAL, S2C_REVIVAL = 0x5108, 0x5109
C2S_REVIVAL_CANCEL, S2C_REVIVAL_CANCEL = 0x510a, 0x510b
C2S_REVIVAL_DONE, S2C_REVIVAL_DONE = 0x510c, 0x510d
C2S_SUMMON, S2C_SUMMON = 0x5120, 0x5121
C2S_SUMMON_CANCEL, S2C_SUMMON_CANCEL = 0x5122, 0x5123
C2S_SUMMON_DONE, S2C_SUMMON_DONE = 0x5124, 0x5125
C2S_WITHDRAW, S2C_WITHDRAW = 0x5126, 0x5127
C2S_WITHDRAW_CANCEL, S2C_WITHDRAW_CANCEL = 0x5128, 0x5129
C2S_WITHDRAW_DONE, S2C_WITHDRAW_DONE = 0x512a, 0x512b
S2C_SUMMON_SHOW = 0x5135
S2C_POINTS = 0x50d8
NO_TROOP = 0xffff                # an empty slot in 0x50f7 / 0x50f2
REFUSED = 1                      # any result but 0 (and NOT_YET) is silent in every reply of this family
NOT_YET = 0x2c4f                 # 0x5106 / 0x510d: the entry's timer back to 0.5 s, the client reports again
HUD_SLOTS = 3                    # the HUD's troop slots 1..3 (the UI load 0x14056f670 caps the room's limit at 3)
LINEUP_SLOTS = range(1, 9)       # the main deck's troop slots: the nine slot records, 0 the hero's
SUMMON, WITHDRAW = 0, 1          # the cast record's mode (0x14056adf0's last argument)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@functools.cache
def _point_rows():
    return {r["SpotID"]: r for r in tables.sections("spottable")["Point"]}


def point_row(spot):
    """The spot's spottable %Point row, or None: 65 spots, of them the story mission 10370, the 16 rifts, 6 invasion
    spots, 3 raids and the PVP_POINT maps."""
    return _point_rows().get(str(spot))


def able(spot, column):
    return (point_row(spot) or {}).get(column) == "True"


def opens(spot):
    """The client opens sub 0x78 in this spot's room (GameStateBattleField::OnEnter 0x140cee71a-0x140cee736)."""
    return able(spot, "Troop_Change_Able") or able(spot, "Troop_Upgrade_Able")


@functools.cache
def _upgrade_types():
    return {r["TroopType"]: int(r["TroopUpgradeType"]) for r in tables.sections("trooptype")["System"]
            if str(r.get("TroopUpgradeType", "-")).isdigit()}


@functools.cache
def _upgrade_rows():
    return {(int(r["TroopUpgradeType_ID"]), int(r["Level"])): r
            for r in tables.sections("troopupgrade")["TroopUpgrade"]}


def upgrade_type(troop_id):
    """A troop's in-battle upgrade type: trooptype %System TroopUpgradeType of its trooptable TroopType (the slot
    record's +0xac, 0x140571d00), 0 for none."""
    from . import troops
    return _upgrade_types().get((troops.troop_row(troop_id) or {}).get("TroopType"), 0)


def upgrade_row(troop_id, level):
    """troopupgrade %TroopUpgrade for the troop's type at an upgrade level (1..3), or None."""
    return _upgrade_rows().get((upgrade_type(troop_id), level))


def change_cost(troop_id, level=0):
    """The Battle Points a troop costs to bring in, summon or (x TroopRevivalRevision) revive: trooptable
    TroopChangePoint plus its upgrade level's TroopAddBattlePoint (the slot record's +0x20, 0x14056e6a3; 0 on every
    row today)."""
    from . import troops
    add = (upgrade_row(troop_id, level) or {}).get("TroopAddBattlePoint", 0) if level else 0
    return int(_num((troops.troop_row(troop_id) or {}).get("TroopChangePoint"))) + int(_num(add))


def hero_cost(c):
    """The hero's base for the timed revival (sub 0x78 +0x910, from his herotable row, 0x14056f242): herotable
    %Contents BattlePoint, 500 for all six (the column is inferred: the row's other point column is
    VICTORY_DECREASE_POINT)."""
    from . import hero
    rows = tables.sections("herotable")["Contents"]
    row = next((r for r in rows if r.get("CHARACTER_TYPE") == hero.HERO_CODE[c.get("class", 0)]), rows[0])
    return int(_num(row.get("BattlePoint")))


def room(s):
    """This room's record: the points, the pending changes / upgrades / revivals / casts, each troop's upgrade level,
    the battle records of the troops off the field, their cooldowns, the summoned ones."""
    st = s.data.get("changetroop")
    if st is None:
        st = s.data["changetroop"] = {"points": None, "started": False, "change": {}, "upgrade": {}, "revival": {},
                                      "cast": {}, "levels": {}, "bench": {}, "cooldown": {}, "summoned": set(),
                                      "base_hp": {}}
    return st


def points(s):
    """The room's Battle Points: %Point BattlePointDefault until something changes them."""
    st = room(s)
    if st["points"] is None:
        st["points"] = int(_num((point_row(s.data.get("spot")) or {}).get("BattlePointDefault")))
    return st["points"]


def points_packet(n):
    return Writer(S2C_POINTS).u32(0).u8(0).u32(n).u16(0)        # 11 bytes: the reader wants them all, the last two unused


def set_points(s, n):
    """The total, kept within 0..MaxBattlePoint and pushed (0x50d8) when it changed."""
    top = int(_num((point_row(s.data.get("spot")) or {}).get("MaxBattlePoint")))
    n = max(0, min(n, top) if top else n)
    if n != points(s):
        room(s)["points"] = n
        s.send(points_packet(n))
    return n


def spend(s, cost):
    """Take cost points; False (and nothing taken) when there are fewer."""
    if cost > points(s):
        return False
    if cost:
        set_points(s, points(s) - cost)
    return True


def start(s):
    """Room start, once the battle state is up (game.load_progress's one-second block, or the first request of the
    family): the starting points pushed and the timed income begun: BattlePointIncrease every BattlePointInterval
    seconds (rifts and 10370: 0; invasion 20911: 10 a 5 s; the PVP_POINT maps 5 or 20). Nothing on a spot with no
    %Point row."""
    row = point_row(s.data.get("spot"))
    st = room(s)
    if row is None or st["started"]:
        return
    st["started"] = True
    s.send(points_packet(points(s)))
    every, gain = _num(row.get("BattlePointInterval")), int(_num(row.get("BattlePointIncrease")))
    if every > 0 and gain > 0:
        def income():
            if s.data.get("changetroop") is not st or s.data.get("mission_won"):
                return
            set_points(s, points(s) + gain)
            s.later(every, income)
        s.later(every, income)
    log.info("battle points: %d at the start (%s)", points(s), s.data.get("spot"))


@functools.cache
def _leader_points():
    return {r["NPLEADER_ID"]: r.get("BattlePoint") for r in tables.sections("npleadertable")["Contents"]}


def on_kill(s, np_troop_id, leader_id=None):
    """A wiped enemy troop's Battle Points: nptrooptable BattlePoint (1-5 for the common troops; the official notes'
    "+2 per enemy troop killed") plus its commander's npleadertable BattlePoint, x %Point EnermyBattlePointRevision.
    For game.troop_down, where the kill is credited to the player. Returns the points gained."""
    row = point_row(s.data.get("spot"))
    if row is None:
        return 0
    from . import zone
    base = _num((zone.np_troop(np_troop_id) or {}).get("BattlePoint"))
    if leader_id not in (None, 0, -100):
        base += _num(_leader_points().get(str(leader_id)))
    gain = int(base * _num(row.get("EnermyBattlePointRevision")))
    if gain > 0:
        start(s)
        set_points(s, points(s) + gain)
    return gain


def reserve_limit(spot):
    """How many reserve troops a spot's room takes: spottable Limit_SubTroop (7 on the rifts, raids and PVP_POINT maps,
    0 on 10370) where the spot's %Point row lets troops change or be summoned, else 0."""
    if not (able(spot, "Troop_Change_Able") or able(spot, "Troop_Summon_Able")):
        return 0
    return int(_num((tables.by_id("spottable").get(str(spot)) or {}).get("Limit_SubTroop")))


def reserve_for(c, spot, difficulty, deck):
    """{room uid: troop} of the reserve a room takes: the main deck's other filled slots (the room uid is the deck
    slot, as a deployed troop's, game.deploy), the first reserve_limit of them. They go into the room start's 0x3f50
    (game.send_start_header) and stay disabled until a change or a summon brings them in."""
    from . import troops
    limit = reserve_limit(spot)
    if not limit:
        return {}
    slots = troops.lineup(c)["slots"]
    out = {}
    for k in LINEUP_SLOTS:
        t = troops.find(c, slots[k]) if k not in deck and k < len(slots) and slots[k] else None
        if t is not None and troops.troop_row(t["id"]) is not None and len(out) < limit:
            out[k] = t
    return out


def reserve(s):
    """The room's reserve troops, {room uid: troop} (s.data["reserve"]; worked out here when the room start did not)."""
    from . import game
    if "reserve" not in s.data:
        if s.data.get("char") is None and s.data.get("account") is None:
            return {}                                    # asked before the room's login: nobody's troops
        s.data["reserve"] = reserve_for(game.hero_char(s), s.data.get("spot"), s.data.get("difficulty", 0),
                                        s.data.get("deck") or {})
    return s.data["reserve"]


def deploy_cap(s):
    """How many troops may stand in the HUD's slots: the spot's Limit_Troop of the difficulty, at most 3 (sub 0x78
    +0x914, from the room header's first byte)."""
    from . import troops
    return min(HUD_SLOTS, troops.deck_limit(s.data.get("spot"), s.data.get("difficulty", 0)))


def wiped(s, uid):
    """The troop is dead in the room: the hero at 0 hp, a troop with no unit and no leader left."""
    t = (s.data.get("battle") and s.data["battle"].troops.get(uid)) or room(s)["bench"].get(uid)
    if not t:
        return False
    return t["hp"] <= 0 if t["hero"] else not any(t["units"]) and not t.get("leader")


def busy(s, uid):
    """The troop has a change, an upgrade, a revival or a cast pending (the client's texts 0x1118c-0x1118e, 0x1668)."""
    st = room(s)
    return (uid in st["change"] or any(p["old"] == uid for p in st["change"].values()) or uid in st["upgrade"]
            or uid in st["revival"] or uid in st["cast"])


def upgrade_statuses(s, uid):
    """The troop's upgrade level on it: the statuses its %TroopUpgrade row's Attack_AbilityID / HP_AbilityID give at
    their levels (80028 -> 800280 ATTACK_PHYSICAL / _MAGICAL +10 / 30 / 60 %, 80029 -> 800290 HP_MAX +10 / 30 / 60 %,
    held 99999 s), and the HP_MAX one's rise on the room's record (the cap only: nothing is healed). Again after
    anything that clears a troop's statuses (an entry, a revive)."""
    from . import status
    st = room(s)
    level = st["levels"].get(uid, 0)
    t = (s.data.get("deck") or {}).get(uid)
    row = t and upgrade_row(t["id"], level)
    if not row:
        return
    rec = s.data.get("battle") and s.data["battle"].troops.get(uid)
    for column in ("Attack", "HP"):
        ability, lv = int(_num(row.get(f"{column}_AbilityID"), -1)), int(_num(row.get(f"{column}_AbilityLV"), 1))
        if ability <= 0:
            continue
        for sid, slv, *_ in status.ability_statuses(ability, lv):
            status.apply(s, [uid], sid, slv, uid)
            imp = status.improvement(sid, slv)
            for j in ("01", "02"):
                if rec and imp.get(f"TraitType{j}") == "HP_MAX" and imp.get(f"FunctionType{j}") == "ADD":
                    base = st["base_hp"].setdefault(uid, rec["unit_max"])
                    rec["unit_max"] = round(base * (1 + _num(imp.get(f"Traitvalue{j}1")) / 100)
                                            + _num(imp.get(f"Traitvalue{j}2")))
                    rec["max"] = rec["unit_max"] * len(rec["units"]) + rec.get("leader_max", 0)


def enter(s, uid, fresh=False):
    """A reserve troop takes the field: into the room's deck with its battle record (the one it left with; a new one
    when it never fought here or comes back whole, fresh), its cooldown over, and its statuses again: the client's
    entry resets the troop (0x1407e3900), which clears them. The client places and enables it itself (0x50ed /
    0x50f1 / 0x5125)."""
    from . import combat, game, status, troops
    st, c = room(s), game.hero_char(s)
    t = reserve(s).pop(uid)
    s.data.setdefault("deck", {})[uid] = t
    battle = s.data.get("battle")
    kept = st["bench"].pop(uid, None)
    if battle is not None:
        if kept is not None and not fresh:
            battle.troops[uid] = kept
        else:
            r = troops.room_row(c, t, live=False)       # as game.deck_enters builds a deck troop's record
            battle.add_np(uid, troops.unit_hp(r), r["UNIT_COUNT"], c=combat.combatant_troop(
                r, game.PLAYER_TEAM, {a: lv for _, a, lv in troops.equipped(c, t, range(8))}, troops.passives(c, t)))
            st["base_hp"].pop(uid, None)
            s.data.get("deck_wiped", set()).discard(uid)
    st["cooldown"].pop(uid, None)
    status.forget(s, uid)
    status.troop_passives(s, uid, troops.passives(c, t))
    worn = troops.set_effect(c)
    if worn:
        status.apply(s, [uid], worn[0], worn[1], uid)
    from . import guild
    for gst, glv in guild.troop_statuses(c, t["id"]):   # the guild's learned troop skills, as at the room's start
        status.apply(s, [uid], gst, glv, uid)
    upgrade_statuses(s, uid)
    journal("troop", ev="enter", spot=s.data.get("spot"), troop=uid, id=t["id"], fresh=fresh)


def leave(s, uid, cooldown=False):
    """A deployed troop leaves the field: back to the reserve, its battle record kept aside as it is (the client keeps
    the troop, disabled, with its units as they were), its statuses gone. cooldown: it was replaced, and may not come
    back for trooptable TroopChangeCooldown seconds, x %Point AnnihilationTroopChangeCooldownRevision when it left
    dead (the slot's state 5, 0x14056c4ff-0x14056c541)."""
    from . import status, troops
    st = room(s)
    t = s.data["deck"].pop(uid)
    reserve(s)[uid] = t
    dead = wiped(s, uid)
    rec = s.data.get("battle") and s.data["battle"].troops.pop(uid, None)
    if rec is not None:
        st["bench"][uid] = rec
    st["summoned"].discard(uid)
    status.forget(s, uid)
    if cooldown:
        secs = _num((troops.troop_row(t["id"]) or {}).get("TroopChangeCooldown"))
        if dead:
            secs *= _num((point_row(s.data.get("spot")) or {}).get("AnnihilationTroopChangeCooldownRevision"), 1.0)
        st["cooldown"][uid] = time.monotonic() + secs
    journal("troop", ev="leave", spot=s.data.get("spot"), troop=uid, id=t["id"], dead=dead)


def make(role, state):
    from . import game

    def cast_time(s, column):
        return _num((point_row(s.data.get("spot")) or {}).get(column))

    def deployed(s):
        """The uids standing in the HUD's slots: the deck less the summoned ones."""
        return [u for u in s.data.get("deck") or {} if u not in room(s)["summoned"]]

    # --- troop change ---

    @role.on(C2S_CHANGE_START)
    def change_start(s, pkt):
        """A reserve troop starts coming into HUD slot n (0x50f7): refused unless the spot lets troops change, the
        troop is in the reserve, idle and off its cooldown, the slot's troop (if any) is deployed and idle, an empty
        slot is within the deploy cap, and the points cover its change cost, which is taken now."""
        b = pkt.rest()
        if len(b) < 5:
            return
        start(s)
        old, new, slot = struct.unpack_from("<HHB", b)
        st, t = room(s), reserve(s).get(new)
        taking = sum(1 for p in st["change"].values() if p["old"] == NO_TROOP)
        ok = (able(s.data.get("spot"), "Troop_Change_Able") and s.data.get("battle") is not None and t is not None
              and 1 <= slot <= HUD_SLOTS and not busy(s, new)
              and st["cooldown"].get(new, 0) <= time.monotonic()
              and (len(deployed(s)) + taking < deploy_cap(s) if old == NO_TROOP
                   else old in deployed(s) and not busy(s, old)))
        cost = change_cost(t["id"], st["levels"].get(new, 0)) if ok else 0
        if not ok or not spend(s, cost):
            s.send(Writer(S2C_CHANGE_START).u16(REFUSED).u16(game.MY_SLOT).raw(b[:5]))
            log.info("troop change refused: %d into slot %d for %d", new, slot, old)
            return
        st["change"][new] = {"old": old, "slot": slot, "cost": cost, "at": time.monotonic()}
        s.send(Writer(S2C_CHANGE_START).u16(0).u16(game.MY_SLOT).raw(b[:5]))
        log.info("troop change: %d into slot %d for %d, %d points", new, slot, old, cost)

    def change_done(s, new, old, slot, reply, refusal):
        """The change's timer ended on the client (0x50ec / 0x50f0): the reserve troop enters, the slot's troop leaves
        with its cooldown. One the server has no such pending change for is refused, and the client's entry dropped
        (0x50fa 0) so the slot is not left waiting."""
        st = room(s)
        p = st["change"].get(new)
        if p is None or p["old"] != old or p["slot"] != slot or new not in reserve(s):
            s.send(refusal)
            s.send(Writer(S2C_CHANGE_CANCEL).u16(0).u16(game.MY_SLOT).u16(new).u8(slot))
            return
        del st["change"][new]
        if old != NO_TROOP and old in (s.data.get("deck") or {}):
            leave(s, old, cooldown=True)
        s.send(reply)
        enter(s, new)
        log.info("troop %d entered slot %d%s", new, slot, f" for {old}" if old != NO_TROOP else "")

    @role.on(C2S_CHANGE_ENTER)
    def change_enter(s, pkt):
        b = pkt.rest()
        if len(b) < 3:
            return
        slot, new = struct.unpack_from("<BH", b)
        change_done(s, new, NO_TROOP, slot, Writer(S2C_CHANGE_ENTER).u16(0).u16(new).u8(slot).u16(game.MY_SLOT),
                    Writer(S2C_CHANGE_ENTER).u16(REFUSED))

    @role.on(C2S_CHANGE_REPLACE)
    def change_replace(s, pkt):
        b = pkt.rest()
        if len(b) < 5:
            return
        slot, old, new = b[0], obf.dec_u16(b[1:3]), obf.dec_u16(b[3:5])
        change_done(s, new, old, slot,
                    Writer(S2C_CHANGE_REPLACE).u16(0).u8(slot).u16(new).u16(old).u16(game.MY_SLOT),
                    Writer(S2C_CHANGE_REPLACE).u16(REFUSED))

    @role.on(C2S_SWAP_SLOTS)
    def swap_slots(s, pkt):
        """Two deployed troops swapped HUD slots (0x50f2; the client has done it): right when both are deployed and
        neither waits for a change. The server keeps no slot order: the echo is the answer."""
        b = pkt.rest()
        if len(b) < 6:
            return
        moved, other, slot, before = struct.unpack_from("<HHBB", b)
        ok = (moved in deployed(s) and (other == NO_TROOP or other in deployed(s)) and moved != other
              and 1 <= slot <= HUD_SLOTS and 1 <= before <= HUD_SLOTS and not busy(s, moved)
              and (other == NO_TROOP or not busy(s, other)))
        if not ok:
            s.send(Writer(S2C_SWAP_SLOTS).u16(REFUSED))
            return
        s.send(Writer(S2C_SWAP_SLOTS).u16(0).raw(b[:6]))

    @role.on(C2S_CHANGE_CANCEL)
    def change_cancel(s, pkt):
        """A pending change called off (0x50f9): its points come back. None pending: non-zero, the client's entry (if
        it has one) runs on."""
        b = pkt.rest()
        if len(b) < 3:
            return
        uid, slot = struct.unpack_from("<HB", b)
        p = room(s)["change"].pop(uid, None)
        if p is not None:
            set_points(s, points(s) + p["cost"])
        s.send(Writer(S2C_CHANGE_CANCEL).u16(0 if p is not None else REFUSED).u16(game.MY_SLOT).u16(uid).u8(slot))

    # --- troop upgrade ---

    def upgrade_reply(proto, result, level, uid):
        return Writer(proto).u16(result).u32(level).u16(uid)

    @role.on(C2S_UPGRADE)
    def upgrade(s, pkt):
        """A troop's next upgrade level starts (0x5101): refused unless the spot lets troops upgrade, the troop is the
        player's and idle, the level is its next one and its type's %TroopUpgrade row exists, and the points cover the
        row's ConsumeBattlePoint, taken now."""
        b = pkt.rest()
        if len(b) < 10:
            return
        start(s)
        kind, level, uid = struct.unpack_from("<IIH", b)
        st = room(s)
        t = (s.data.get("deck") or {}).get(uid) or reserve(s).get(uid)
        row = t and upgrade_row(t["id"], level)
        ok = (able(s.data.get("spot"), "Troop_Upgrade_Able") and s.data.get("battle") is not None and row
              and kind == upgrade_type(t["id"]) and level == st["levels"].get(uid, 0) + 1 and not busy(s, uid))
        cost = int(_num(row.get("ConsumeBattlePoint"))) if ok else 0
        if not ok or not spend(s, cost):
            s.send(upgrade_reply(S2C_UPGRADE, REFUSED, level, uid))
            log.info("troop upgrade refused: %d to level %d (type %d)", uid, level, kind)
            return
        st["upgrade"][uid] = {"level": level, "cost": cost, "at": time.monotonic()}
        s.send(upgrade_reply(S2C_UPGRADE, 0, level, uid))
        log.info("troop upgrade: %d to level %d, %d points", uid, level, cost)

    @role.on(C2S_UPGRADE_CANCEL)
    def upgrade_cancel(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            return
        _, level, uid = struct.unpack_from("<IIH", b)
        p = room(s)["upgrade"].pop(uid, None)
        if p is not None:
            set_points(s, points(s) + p["cost"])
        s.send(upgrade_reply(S2C_UPGRADE_CANCEL, 0 if p is not None else REFUSED, level, uid))

    @role.on(C2S_UPGRADE_DONE)
    def upgrade_done(s, pkt):
        """The upgrade's timer ended on the client (0x5105): before the server's own TroopUpgradeCastTime has run it
        is told to ask again (0x2c4f); else the level is the troop's, with its statuses."""
        b = pkt.rest()
        if len(b) < 10:
            return
        _, level, uid = struct.unpack_from("<IIH", b)
        st = room(s)
        p = st["upgrade"].get(uid)
        if p is None or p["level"] != level:
            s.send(upgrade_reply(S2C_UPGRADE_DONE, REFUSED, level, uid))
            return
        if time.monotonic() - p["at"] < cast_time(s, "TroopUpgradeCastTime"):
            s.send(upgrade_reply(S2C_UPGRADE_DONE, NOT_YET, level, uid))
            return
        del st["upgrade"][uid]
        st["levels"][uid] = level
        s.send(upgrade_reply(S2C_UPGRADE_DONE, 0, level, uid))
        upgrade_statuses(s, uid)
        journal("troop", ev="upgrade", spot=s.data.get("spot"), troop=uid, level=level, points=p["cost"])
        log.info("troop %d upgraded to level %d", uid, level)

    # --- timed revival ---

    def revival_reply(proto, uid, result):
        return Writer(proto).u16(uid).u16(result)

    @role.on(C2S_REVIVAL)
    def revival(s, pkt):
        """The HUD's revive on a spot with no %Revival row (0x5108): the hero (uid 0) or a deployed troop of his,
        dead and idle, for its change cost (the hero: hero_cost) x %Point TroopRevivalRevision in Battle Points,
        taken now; the spot's revive rules as game.revive_here reads them (game.revival: none where the content
        allows none, none past its limit)."""
        b = pkt.rest()
        if len(b) < 2:
            return
        start(s)
        uid = struct.unpack_from("<H", b)[0]
        st, row = room(s), point_row(s.data.get("spot"))
        t = (s.data.get("deck") or {}).get(uid)
        goods, limit = game.revival(s.data.get("spot"))
        ok = (row is not None and (uid == 0 or t is not None) and wiped(s, uid) and not busy(s, uid)
              and goods != "IMPOSIBLE" and not 0 <= limit <= s.data.get("revivals", 0))
        cost = 0
        if ok:
            base = hero_cost(game.hero_char(s)) if uid == 0 else change_cost(t["id"], st["levels"].get(uid, 0))
            cost = int(base * _num(row.get("TroopRevivalRevision")))
        if not ok or not spend(s, cost):
            s.send(revival_reply(S2C_REVIVAL, uid, REFUSED))
            log.info("timed revival refused: troop %d", uid)
            return
        st["revival"][uid] = {"cost": cost, "at": time.monotonic()}
        s.send(revival_reply(S2C_REVIVAL, uid, 0))
        log.info("timed revival: troop %d, %d points", uid, cost)

    @role.on(C2S_REVIVAL_CANCEL)
    def revival_cancel(s, pkt):
        b = pkt.rest()
        if len(b) < 2:
            return
        uid = struct.unpack_from("<H", b)[0]
        p = room(s)["revival"].pop(uid, None)
        if p is not None:
            set_points(s, points(s) + p["cost"])
        s.send(revival_reply(S2C_REVIVAL_CANCEL, uid, 0 if p is not None else REFUSED))

    @role.on(C2S_REVIVAL_DONE)
    def revival_done(s, pkt):
        """The revival's timer ended on the client (0x510c): too early by the server's TroopRevivalCastTime it asks
        again (0x2c4f); else the troop is back (the reply revives it on the client; the room's record and the pushes
        are game.revive_hero's / game.revive_troop's) and the room's revivals-used count rises (0x513b reports it)."""
        b = pkt.rest()
        if len(b) < 2:
            return
        uid = struct.unpack_from("<H", b)[0]
        st = room(s)
        p = st["revival"].get(uid)
        t = s.data.get("battle") and s.data["battle"].troops.get(uid)
        if p is None or not t:
            s.send(revival_reply(S2C_REVIVAL_DONE, uid, REFUSED))
            return
        if time.monotonic() - p["at"] < cast_time(s, "TroopRevivalCastTime"):
            s.send(revival_reply(S2C_REVIVAL_DONE, uid, NOT_YET))
            return
        del st["revival"][uid]
        s.data["revivals"] = s.data.get("revivals", 0) + 1
        s.send(revival_reply(S2C_REVIVAL_DONE, uid, 0))
        if uid == 0:
            game.revive_hero(s, t, s.data.get("hero_pos") or game.start_pos(s))
        else:
            game.revive_troop(s, uid, t)                    # (it puts the upgrade's statuses back: upgrade_statuses)

    # --- summon and withdraw ---

    @role.on(C2S_SUMMON)
    def summon(s, pkt):
        """A reserve troop summoned to the hero's place (0x5120): refused unless the spot lets troops be summoned, the
        troop is in the reserve and idle, fewer than Limit_Troop_Summon stand summoned, the hero lives, and the points
        cover its change cost, taken now."""
        b = pkt.rest()
        if len(b) < 7:
            return
        start(s)
        uid = struct.unpack_from("<H", b, 5)[0]
        st, row = room(s), point_row(s.data.get("spot")) or {}
        t = reserve(s).get(uid)
        casting = sum(1 for p in st["cast"].values() if p["mode"] == SUMMON)
        ok = (able(s.data.get("spot"), "Troop_Summon_Able") and s.data.get("battle") is not None and t is not None
              and not busy(s, uid) and not wiped(s, 0)
              and len(st["summoned"]) + casting < int(_num(row.get("Limit_Troop_Summon"))))
        cost = change_cost(t["id"], st["levels"].get(uid, 0)) if ok else 0
        if not ok or not spend(s, cost):
            s.send(Writer(S2C_SUMMON).u16(REFUSED))
            log.info("troop summon refused: %d", uid)
            return
        st["cast"][uid] = {"mode": SUMMON, "cost": cost, "at": time.monotonic()}
        s.send(Writer(S2C_SUMMON).u16(0).raw(b[:7]).u16(game.MY_SLOT))
        log.info("troop summon: %d, %d points", uid, cost)

    def cast_cancel(s, pkt, mode, reply):
        b = pkt.rest()
        if len(b) < 2:
            return
        uid = struct.unpack_from("<H", b)[0]
        st = room(s)
        p = st["cast"].get(uid)
        if p is None or p["mode"] != mode:
            s.send(Writer(reply).u16(REFUSED).u16(uid))
            return
        del st["cast"][uid]
        set_points(s, points(s) + p["cost"])
        s.send(Writer(reply).u16(0).u16(uid))

    @role.on(C2S_SUMMON_CANCEL)
    def summon_cancel(s, pkt):
        cast_cancel(s, pkt, SUMMON, S2C_SUMMON_CANCEL)

    @role.on(C2S_SUMMON_DONE)
    def summon_done(s, pkt):
        """The summon's cast ended on the client (0x5124): the troop takes the field as a summoned one; one that left
        the field dead comes back whole (the official notes: "dead ones re-summonable at full HP")."""
        b = pkt.rest()
        if len(b) < 7:
            return
        uid = struct.unpack_from("<H", b, 5)[0]
        st = room(s)
        p = st["cast"].get(uid)
        ok = p is not None and p["mode"] == SUMMON and uid in reserve(s)
        s.send(Writer(S2C_SUMMON_DONE).u16(0 if ok else REFUSED).raw(b[:7]).u16(game.MY_SLOT))
        if not ok:
            return
        del st["cast"][uid]
        dead = wiped(s, uid)
        enter(s, uid, fresh=dead)
        st["summoned"].add(uid)
        if dead:                                            # the client still holds its units dead
            game.revive_troop(s, uid, s.data["battle"].troops[uid])   # (and the upgrade's statuses: game.revive_troop)
        s.send(Writer(S2C_SUMMON_SHOW).u16(uid).u8(OBOOL_TRUE))
        log.info("troop %d summoned", uid)

    @role.on(C2S_WITHDRAW)
    def withdraw(s, pkt):
        """A troop on the field called back (0x5126): free (the official notes: "Retreat is free, no refund")."""
        b = pkt.rest()
        if len(b) < 2:
            return
        uid = struct.unpack_from("<H", b)[0]
        st = room(s)
        ok = point_row(s.data.get("spot")) is not None and uid in (s.data.get("deck") or {}) and not busy(s, uid)
        if ok:
            st["cast"][uid] = {"mode": WITHDRAW, "cost": 0, "at": time.monotonic()}
        s.send(Writer(S2C_WITHDRAW).u16(0 if ok else REFUSED).u16(uid).u16(game.MY_SLOT))

    @role.on(C2S_WITHDRAW_CANCEL)
    def withdraw_cancel(s, pkt):
        cast_cancel(s, pkt, WITHDRAW, S2C_WITHDRAW_CANCEL)

    @role.on(C2S_WITHDRAW_DONE)
    def withdraw_done(s, pkt):
        b = pkt.rest()
        if len(b) < 2:
            return
        uid = struct.unpack_from("<H", b)[0]
        st = room(s)
        p = st["cast"].get(uid)
        ok = p is not None and p["mode"] == WITHDRAW and uid in (s.data.get("deck") or {})
        if ok:
            s.send(Writer(S2C_SUMMON_SHOW).u16(uid).u8(OBOOL_FALSE))
        s.send(Writer(S2C_WITHDRAW_DONE).u16(0 if ok else REFUSED).u16(uid).u16(game.MY_SLOT))
        if ok:
            del st["cast"][uid]
            leave(s, uid)
            log.info("troop %d withdrawn", uid)

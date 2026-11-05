"""The hero's pools against the original's HUD: the room's SP (its max, its start, its regeneration), the HP on a gear
swap, and the bag a new hero is made with.

The tape: Sorrowh's Berserker (REGNIER, class 4) in playthrough parts 1-5, frames cached in
captures/video/<video>_0_<length>_frames_0.5 (f_<n> is (n - 1) * 2 s in) and, at 2 fps,
<video>_<from s>_<to s>_frames_2 (f_<n> is from + (n - 1) / 2 s). The HUD's SP box shows the current SP; with the bar
full it is the max.

SP max. Outside a mission the HUD reads 200 at every level (part 2 f_01381 46:00 Lv.6, part 5 f_00060 1:58 Lv.11): the
class's herotable %ApSp SP_MAX (200 for all six). In a mission the troops the hero brings add their trooptable
SP_ADD: the conscripted light infantry (troop 100, SP_ADD 700) and the Grey Wood Bowmen (2202311, "Grey Wood Bowmen
Conscription Paper", part 3 f_00683 22:44; SP_ADD 150). Only the deck troops that take part count (spottable
Limit_Troop_<difficulty>, troops.room_deck): Flamegrass Valley takes one of his two and reads 900, New Hampton Castle
and Ramparts take both and read 1,050. The troops the mission hands him (Grey Rock's archers 134060, the Lunawing, the
trebuchets and mortars; nptrooptable SP_ADD 0) add nothing, and a fallen troop still counts (part 3 f_01215 40:28:
F1 at 0 HP, 1,050). The hero's level does not enter (lvuptypetable %Hero LvSPMax is 0 for every class).

SP at the room start: the hero's own pool, full (200), not spottable Default_SP (100) or herotable SP_INIT (150). Grey
Rock's loading ends at 29:38 (f_00890), the first HUD reads 260 at 30:38 (f_00920) and 263 at 30:42 (f_00922): 58 s at
1 SP a second from 200. New Hampton Castle: loading to ~25:00 (f_00752), 300 at 25:58 (f_00780) at 5 per 3 s: 200.

SP regeneration: every 3 s, the hero's %ApSp SP_RECOVERY (3) plus the room troops' trooptable SP_RECOVERY (troop 100:
0, the bowmen: 2). Grey Rock, 3 per 3 s: 530 / 536 / 542 / 548 at 35:24 / 35:30 / 35:36 / 35:42 (f_01063-01072).
With the bowmen, 5 per 3 s: New Hampton Castle 310 / 325 / 355 / 365 / 380 / 395 / 405 at 26:06 .. 27:02 (f_00784-00812,
8 s apart: +10 or +15, two or three ticks); New Hampton Ramparts 270 / 370 / 470 at 3:58 / 4:58 / 5:58 (part 5
f_00120-00180, +100 a minute). Ours gave SP_RECOVERY x 3 every 3 s (9)."""
import struct

import pytest

from kuf2 import combat, game, hero, items, obf, tables, troops, world
from test_army import army, entered

INFANTRY, BOWMEN = 1, 2202311                   # troopsaletable sets: troop 100 at Lv.6, 2202311 at Lv.1
GREY_ROCK, NEW_HAMPTON_CASTLE, FLAMEGRASS, RAMPARTS, TOWER, MIST_FIELD = 10234, 10235, 10303, 10306, 10233, 10350
BERSERKER = 4

TAPE_SP_MAX = [   # (video, frame, time, spot, hero level, the army then, the HUD's SP with the bar full)
    ("qeeQjhgO8ss", "f_00200", "6:38", TOWER, 4, (INFANTRY,), 200),               # Limit_Troop 0: handed troops only
    ("qeeQjhgO8ss", "f_01171", "39:00", GREY_ROCK, 6, (INFANTRY,), 900),          # 200 + 700
    ("qeeQjhgO8ss", "f_01381", "46:00", MIST_FIELD, 6, (INFANTRY,), 200),         # the field takes no troop
    ("6uClEdAS__k", "f_01065", "35:28", NEW_HAMPTON_CASTLE, 8, (INFANTRY, BOWMEN), 1050),   # 200 + 700 + 150
    ("_0FD8aKDxto", "f_01224", "40:46", FLAMEGRASS, 10, (INFANTRY, BOWMEN), 900),  # Limit_Troop 1: the first only
    ("m-CmO76YaoA", "f_00390", "12:58", RAMPARTS, 11, (INFANTRY, BOWMEN), 1050),
]


def berserker(sets, level):
    c, _ = army(*sets, level=level)
    c["class"] = BERSERKER
    return c


def room_troops(c, spot):
    return [t for _, t in troops.room_deck(c, spot)]


@pytest.mark.parametrize("video, frame, at, spot, level, sets, sp_max", TAPE_SP_MAX)
def test_the_rooms_sp_max_is_the_heros_own_and_the_troops_that_take_part(video, frame, at, spot, level, sets, sp_max):
    c = berserker(sets, level)
    assert game.pools_for(c, spot, room_troops(c, spot))["sp_max"] == sp_max
    p = game.player_struct(c, spot, room_troops(c, spot))
    assert struct.unpack_from("<i", p, 0xb5)[0] == sp_max          # the 0x3f4f struct the HUD's max comes from


@pytest.mark.parametrize("cls", range(6))
def test_every_class_enters_grey_rock_with_the_infantrys_sp(cls):
    """%ApSp SP_MAX and SP_RECOVERY are 200 and 3 for all six; the ammo pools stay the class's (the Gunslinger 10 / 10)."""
    c, _ = army(INFANTRY, level=6)
    c["class"] = cls
    _, s = entered(GREY_ROCK, c)
    p = bytes(next(w for w in s.sent if w.proto == game.S2C_START_PLAYER_INFO).buf)[2:]
    assert struct.unpack_from("<i", p, 0xb5)[0] == 900 and struct.unpack_from("<i", p, 0x01)[0] == 200
    assert s.data["pools"]["sp_max"] == 900 and s.data["pools"]["sp_rec"] == 3
    assert (p[0x13], p[0x94]) == ((10, 10) if cls == 0 else (0, int(game.pools_for(c)["ammo_max"])))


def test_a_room_starts_with_the_heros_own_sp_full_and_regenerates_the_troops_recovery_every_three_seconds():
    c = berserker((INFANTRY, BOWMEN), 8)
    s = type("S", (), {})()
    s.data, s.sent, s.pending = {}, [], []
    s.send, s.later = s.sent.append, lambda delay, fn: s.pending.append((delay, fn))
    s.data["pools"] = game.pools_for(c, NEW_HAMPTON_CASTLE, room_troops(c, NEW_HAMPTON_CASTLE))
    assert (s.data["pools"]["sp"], s.data["pools"]["sp_max"], s.data["pools"]["sp_rec"]) == (200, 1050, 5)
    combat.start_regen(s)
    delay, tick = s.pending.pop()
    tick()
    assert delay == 3 and s.data["pools"]["sp"] == 205                             # 5 per 3 s
    grey = berserker((INFANTRY,), 6)
    pools = game.pools_for(grey, GREY_ROCK, room_troops(grey, GREY_ROCK))
    assert (pools["sp"], pools["sp_max"], pools["sp_rec"]) == (200, 900, 3)       # 3 per 3 s: 1 a second


def test_the_rooms_numbers_after_an_equip_or_a_level_keep_the_rooms_sp_max():
    """room_stats (0x5138 after an equip, an enchant, a level-up) sent the table's SP_MAX 200: in Grey Rock it would
    have cut the 900 pool back to 200. It sends the room's max and SP, as the room's own records (0x50cb / 0x50b8)."""
    c, _ = army(INFANTRY, level=6)
    _, s = entered(GREY_ROCK, c)
    s.sent.clear()
    game.room_stats(s, c)
    sent = {struct.unpack_from("<b", bytes(w.buf), 5 + 7 * i)[0]: struct.unpack_from("<I", bytes(w.buf), 1 + 7 * i)[0]
            for w in s.sent if w.proto == combat.S2C_STATS for i in range(bytes(w.buf)[0])}
    assert sent[7] == 900 and sent[combat.STAT_SP] == s.data["pools"]["sp"]
    assert game.hero_stats(s)[7] == 900 and game.hero_stats(s)[combat.STAT_SP] == s.data["pools"]["sp"]


# --- the HP on a gear swap -------------------------------------------------------------------------------------------
# Part 2 27:35, in the Mist Field village (the chat: "Cannot use the skill in the village or safety zone"), Lv.6:
# qeeQjhgO8ss_1655_1661_frames_2 f_00002 (27:35.5) HP 994 wearing the Supplied Adventurer Top (+469), f_00003 (27:36.0)
# 525 = 994 - 469 with the Supplied Trainee Top (+2815) on: the swap takes the old top off (the max falls to 525 and the
# HP with it) and puts the new one on (the max rises to 3,340, the HP stays). f_00004 is the tooltip pair and 525 in red.
# It then fills: 645 at 27:39.0 (f_00009), 765 at 27:42 (0.5 fps f_00832), 1,485 / 1,725 / 1,845 / 1,965 / 2,205 /
# 2,325 / 2,445 / 2,565 / 2,805 / 2,925 / 3,045 at 28:02 .. 28:42 (f_00842-00862, 4 s apart): +120 every 3 s in the
# village, full by ~28:50. Ours regenerates HP_RECOVERY x 3 every 3 s (30 for this hero): the rate is not built here.
ADVENTURER_TOP, TRAINEE_TOP = 151301110, 151306110


class St:
    saves = 0

    def __init__(self):
        self.game_sessions = {}

    def save(self):
        self.saves += 1


class Room:
    def __init__(self, c, hp):
        self.data = {"battle": combat.Battle(), "char": c, "spot": MIST_FIELD}
        self.sent, self.pending = [], []
        self.w = type("W", (), {"is_closing": lambda self: False})()
        self.data["battle"].add_hero(0, game.hero_stat_values(c)[0], c=game.hero_combatant(c))
        self.data["battle"].troops[0]["hp"] = hp
        self.data["pools"] = dict(game.pools_for(c, MIST_FIELD), sp=200, hp_rec=10)

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def village_berserker():
    c = {"id": 1, "class": BERSERKER, "level": 6, "name": "Sorrowh", "look": "00" * 0x33}
    for e in hero.equipment(c):
        if e["index"] == 2:
            e["code"] = ADVENTURER_TOP
    c["bag"] = [{"code": TRAINEE_TOP, "slot": 0, "count": 1, "serial": (1 << 32) | 0x10001, "bound": True}]
    return c


def equip(c, room, bag_serial, worn_serial, index, bag_slot):
    from test_battle import Session, pkt
    st = St()
    st.game_sessions[7] = room
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data.update(char=c, account={"id": 7})
    body = obf.u64(bag_serial) + obf.u64(worn_serial) + obf.u16(index) + obf.u16(bag_slot)
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    assert bytes(s.sent[0].buf) == b"\0\0"


def hp_sent(room):
    return [struct.unpack_from("<H", bytes(w.buf), 3)[0] for w in room.sent if w.proto == game.S2C_TROOP_HP]


def test_an_hp_raising_swap_takes_the_old_piece_off_first_and_keeps_the_hp_the_new_one_finds():
    c = village_berserker()
    assert game.hero_stat_values(c)[0] == 994
    room = Room(c, 994)
    top = next(e for e in hero.equipment(c) if e["index"] == 2)
    equip(c, room, c["bag"][0]["serial"], top["serial"], 2, 0)
    t = room.data["battle"].troops[0]
    assert (t["hp"], t["max"]) == (525, 3340)                         # 994 - 469, as the HUD read at 27:36
    assert hp_sent(room)[-1] == 525                                   # the HUD shows it (0x505d)
    delay, tick = room.pending.pop()
    tick()
    assert delay == combat.SP_TICK_S and 525 < t["hp"] < 3340         # and it fills toward the new max


def test_an_equip_into_an_empty_place_keeps_the_hp_and_taking_a_piece_off_caps_it():
    c = village_berserker()
    top = next(e for e in hero.equipment(c) if e["index"] == 2)
    c["equip"].remove(top)                                            # nothing on the upper body: 525
    room = Room(c, 400)
    equip(c, room, c["bag"][0]["serial"], 0, 2, 0)
    t = room.data["battle"].troops[0]
    assert (t["hp"], t["max"]) == (400, 3340)                         # kept, not raised by 2,815
    room.data["battle"].troops[0]["hp"] = 3000
    worn = next(e for e in hero.equipment(c) if e["index"] == 2)
    equip(c, room, 0, worn["serial"], 2, 1)                           # off again, into bag slot 1
    assert (t["hp"], t["max"]) == (525, 525) and hp_sent(room)[-1] == 525


def test_a_level_up_in_a_room_heals_the_hero_to_the_new_max():
    """Rules census L10: rTitaEjTUoc f_00460 -> f_00461, Lv.19 9,690 (~73 %) -> Lv.20 13,402 full, no potion."""
    c = village_berserker()
    room = Room(c, 900)
    c["level"] = 7
    game.room_level_up(room, c)
    t = room.data["battle"].troops[0]
    assert t["max"] == 994 + 48 and t["hp"] == 994 + 48


# --- the bag a new hero is made with ---------------------------------------------------------------------------------
# herotable %Inventory INVENTORY01 is a Level-up Celebration Chest [Lv 5] of the class (600000101 GLEN, 201 ISABELLA,
# 301 REGNIER, 401 OLIVIA, 501 DRUID; Helena's rows are all -1). Part 1 18:30 (tiouWoPSPks f_00556): the level-1
# Berserker's bag holds two items, the chest in its first slot (tooltip "Level-up Celebration Chest", "Bound Item")
# and a quest's HP potion. item_container gives, for the Berserker's: 5 [Lv 2] HP Recovery Potion, 3 [Lv 1] Heroic
# Attack Potion, 3 [Lv 1] Speed Potion and the [Lv 10] chest (the chain goes on at 15).
CHEST = {0: 600000101, 1: 600000401, 2: 600000501, 3: 600000201, 4: 600000301}


@pytest.mark.parametrize("cls", range(6))
def test_a_new_hero_carries_the_class_celebration_chest(cls):
    from test_lobby_travel import State, Session, pkt
    acct = {"id": 1, "characters": []}
    st = State(acct)
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["account"] = acct
    look = bytearray(56)
    struct.pack_into("<I", look, 0x34, cls)
    role.handlers[world.C2S_CHAR_CREATE](s, pkt(world.C2S_CHAR_CREATE, b"Sorrowh\0" + bytes(look)))
    c = acct["characters"][0]
    if cls == 5:
        assert c.get("bag", []) == []
        return
    assert [(i["code"], i["slot"], i["count"], i["bound"]) for i in c["bag"]] == [(CHEST[cls], 0, 1, True)]
    assert items.row(CHEST[cls])["ReqLevel"] == "5" and hero.starter_bag(cls) == ((CHEST[cls], 1),)


def test_the_berserkers_chest_opens_into_its_potions_and_the_next_chest():
    from test_battle import Session, pkt
    c = {"id": 1, "class": BERSERKER, "level": 5, "name": "Sorrowh", "look": "00" * 0x33}
    world.give_starter_bag(c)
    chest = c["bag"][0]
    role = world.make(St(), 0, "127.0.0.1", 0)
    s = Session()
    s.data.update(char=c, account={"id": 7})
    head = obf.u64(chest["serial"]) + obf.u16(1) + b"\0" + obf.u16(0)
    role.handlers[world.C2S_OPEN_CONTAINER](s, pkt(world.C2S_OPEN_CONTAINER, head))
    role.handlers[world.C2S_TAKE_CONTAINER](s, pkt(world.C2S_TAKE_CONTAINER, head + b"\0\0"))
    assert sorted((i["code"], i["count"]) for i in c["bag"]) == [(350000020, 5), (350550010, 3), (350554010, 3),
                                                                 (600000302, 1)]

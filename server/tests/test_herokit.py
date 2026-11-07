"""The hero's kit (planning/agents/reports/2026-11-05_contract3-herokit.md): the guild's cores 350013 Guild Defence and
350014 Guild Escape in the room kit (guild.hero_kit, skills.battle_abilities, guild.refresh_hero), a charged skill's
stage statuses (combat.charge_stage, status.ability_statuses, status.on_execute). GOLDEN pins a kit without the cores
byte for byte: it is the 0x3f50 list of every mission. Every number is read from its table row.
Run: py -m pytest -q server/tests"""
import hashlib
import struct
import types

import pytest

from kuf2 import combat, game, guild, hero, obf, skills, status, tables, world
from kuf2.packet import Reader, Writer
from test_army import army, entered
from test_battle import added, ended, execute, hero_session, pkt, use_ability
from test_rewards import Session, State, char

GOLDEN_LEVELS = (1, 2, 4, 6, 12, 30, 60)
GOLDEN = {                          # computed before the cores went in
    "GLEN": "ec62711169f10873", "OLIVIA": "dc0fa6bde4a75c10", "DRUID": "5293706b43861f95",
    "ISABELLA": "401f3787175a8e9c", "REGNIER": "8a2f90fc86eb80d6", "HELENA": "75cdf0834a1ce181"}
CORES = {100: 350013, 101: 350014}  # guild_point %Guild_Skill id -> Ability_ID
NO_CORE = [5, 15, 25, 35, 45, 50]   # hero, troop and util rows, none a core
HOLDERS = ("GLEN", "OLIVIA", "ISABELLA", "REGNIER")
GUARD = {"GLEN": (62, 350005, 341), "ISABELLA": (304, 350006, 3040), "REGNIER": (604, 350007, 6040),
         "OLIVIA": (909, 350008, 6339)}
ESCAPE = {"GLEN": (14, 350009), "ISABELLA": (310, 350010), "REGNIER": (614, 350011), "OLIVIA": (914, 350012)}


def cls(name):
    return hero.HERO_CODE.index(name)


def wire(kit):
    """The 0x3f50 ability block of a sorted kit (reader 0x140d0e0f0: u16 n, n * (u8 level, u32 id))."""
    return struct.pack("<H", len(kit)) + b"".join(struct.pack("<BI", level, aid) for aid, level in kit)


def kit_of(c):
    return sorted(skills.battle_abilities(c).items())


def digest(make):
    return hashlib.sha256(b"".join(wire(kit_of(make(level))) for level in GOLDEN_LEVELS)).hexdigest()[:16]


def with_guild(c, *known):
    c = dict(c, name="Aldric")
    c["guild"] = {**guild.new(c, "Ironwood", 1_800_000_000), "skills": list(known)}
    return c


def links(ability):
    row = next(r for r in tables.sections("abilitytypeinfo")["Link"] if r["AbilityId"] == str(ability))
    return [int(v) for k, v in row.items() if k.startswith("Link") and v.isdigit()]


def ask(role, s, proto, body=b""):
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def room_skills(g):
    """The ability ids of the 0x50a9 a session was sent (troop uid 0 each)."""
    out = []
    for w in g.sent:
        if w.proto == skills.S2C_ROOM_SKILL:
            uid, aid = struct.unpack("<HI", bytes(w.buf))
            assert uid == 0
            out.append(aid)
    return out


@pytest.fixture
def room():
    """A world session and the room's game session of one character, in a guild with 10 normal levels: both cores can
    be learned."""
    st = State()
    st.world_sessions = {}
    role = world.make(st, 0, "127.0.0.1", 0)
    c = {**char(level=20), "name": "Aldric", "gold": 100_000, "bag": []}
    c["guild"] = {**guild.new(c, "Ironwood", 1_800_000_000), "skills": [5, 15], "point": 30_000_000}
    g = Session(c, spot=10234)
    g.w, g.state = types.SimpleNamespace(is_closing=lambda: False), st
    g.data["kit"] = skills.battle_abilities(c)
    st.game_sessions[1] = g
    return role, Session(c), g, c


# --- the pin: no core, the same bytes ---

@pytest.mark.parametrize("name", hero.HERO_CODE)
def test_a_hero_without_the_cores_keeps_his_kit_byte_for_byte(name):
    plain = lambda level: {"id": 1, "class": cls(name), "level": level}     # noqa: E731
    assert digest(plain) == GOLDEN[name]
    assert digest(lambda level: with_guild(plain(level))) == GOLDEN[name]                # a guild, nothing learned
    assert digest(lambda level: with_guild(plain(level), *NO_CORE)) == GOLDEN[name]      # every other kind learned


@pytest.mark.parametrize("name", hero.HERO_CODE)
def test_the_room_lists_the_same_entry_with_and_without_a_guild(name):
    def entry(c):
        w = Writer(game.S2C_START_TROOP_INFO).u16(1)
        game.write_troop(w, slot=0, uid=1, troop_id=game.HERO_TROOP_ID, leader_id=c["class"], leader_level=c["level"],
                         abilities=kit_of(c))
        return bytes(w.buf)
    c = {"id": 1, "class": cls(name), "level": 30}
    assert entry(c) == entry(with_guild(c, *NO_CORE))
    assert wire(kit_of(c)) in entry(c)


# --- the cores: which rows, which classes ---

def test_the_tables_are_what_the_cores_read():
    rows = {k: guild.skill_rows()[k] for k in CORES}
    assert [(r["Ability_ID"], r["Skill_Type"], r["Core_Skill"], r["Skill_Level"]) for r in rows.values()] == [
        ("350013", "1", "True", "1"), ("350014", "1", "True", "1")]
    assert links(350013) == [350005, 350006, 350007, 350008, 350016] and links(350014) == [350009, 350010, 350011, 350012]
    change = {(r["Hero"], r["Skill_Id"]): r for r in tables.sections("stanceactioninfo")["CHANGE_SKILL"]
              if r["Condition"] == "CONDITION_ABILITY"}
    for name in HOLDERS:
        for base, variant in (GUARD[name][:2], ESCAPE[name]):
            r = change[(name, str(base))]
            assert (r["Change_Skill_Id"], r["Value"]) == (str(variant), str(variant))
    assert not {("DRUID", "1201"), ("DRUID", "1253")} & change.keys()
    assert not [k for k in change if k[0] == "HELENA"]
    assert "350016" not in {r["Change_Skill_Id"] for r in change.values()}              # dead data


@pytest.mark.parametrize("name", HOLDERS)
def test_a_learned_core_goes_last_in_the_kit_alone(name):
    c = {"id": 1, "class": cls(name), "level": 30}
    plain = kit_of(c)
    assert kit_of(with_guild(c, 5, 100)) == plain + [(350013, 1)]
    assert kit_of(with_guild(c, 5, 101)) == plain + [(350014, 1)]
    both = kit_of(with_guild(c, 5, 15, 100, 101))
    assert both == plain + [(350013, 1), (350014, 1)]
    assert not {a for a, _ in both} & set(links(350013) + links(350014))    # the client adds the %Link rows itself


@pytest.mark.parametrize("name", ("DRUID", "HELENA"))
def test_the_classes_without_a_book_row_get_nothing_from_the_cores(name):
    c = {"id": 1, "class": cls(name), "level": 30}
    assert not {350013, 350014} & skills.book(c["class"]).keys()
    assert guild.hero_kit(with_guild(c, 5, 15, 100, 101)) == {}
    assert wire(kit_of(with_guild(c, 5, 15, 100, 101))) == wire(kit_of(c))


def test_the_cores_change_no_number_and_announce_no_skill():
    c = {**char(level=20), "name": "Aldric"}
    bare = hero.char_stats(with_guild(c, 5, 15))
    held = with_guild(c, 5, 15, 100, 101)
    assert hero.char_stats(held) == bare
    assert not status.passive_statuses({350013: 1, 350014: 1})
    assert combat.checkskill_statuses(350005, skills.battle_abilities(held)) == []
    assert {a for a, _ in skills.announced(held, 19)} & {350013, 350014} == set()


def test_a_junk_save_lists_no_core():
    c = {"id": 1, "class": 0, "level": 30}
    for known in (["x", None, 999_999], [-1, 0], []):
        assert kit_of(with_guild(c, *known)) == kit_of(c)
    assert kit_of({**c, "guild": {}}) == kit_of(c) == kit_of({**c, "guild": None})
    assert kit_of(with_guild({**c, "skills": {"350013": 4}}, 100))[-1] == (350013, 1)   # the row's level, not the save's


# --- in a room: 0x50a9, the kit, what a reset leaves ---

def test_a_core_learned_in_a_room_reaches_the_hero_there(room):
    role, w, g, c = room
    assert ask(role, w, guild.C2S_LEARN, struct.pack("<I", 100))[0] == (guild.S2C_LEARN, bytes(2) + struct.pack("<I", 100))
    assert room_skills(g) == [350013] and g.data["kit"][350013] == 1
    ask(role, w, guild.C2S_LEARN, struct.pack("<I", 101))
    assert room_skills(g) == [350013, 350014] and g.data["kit"][350014] == 1


def test_a_passive_learned_in_a_room_sends_no_room_skill(room):
    role, w, g, c = room
    kit = dict(g.data["kit"])
    ask(role, w, guild.C2S_LEARN, struct.pack("<I", 21))
    assert 21 in c["guild"]["skills"] and room_skills(g) == [] and g.data["kit"] == kit


def test_a_reset_and_a_dismiss_drop_the_core_from_the_servers_kit_and_send_nothing(room):
    role, w, g, c = room
    ask(role, w, guild.C2S_LEARN, struct.pack("<I", 100))
    assert ask(role, w, guild.C2S_RESET)[0][1][:2] == bytes(2)
    assert 350013 not in g.data["kit"] and room_skills(g) == [350013]
    c["guild"]["skills"] = [5, 100]
    g.data["kit"] = skills.battle_abilities(c)
    ask(role, w, guild.C2S_DISMISS)
    assert "guild" not in c and 350013 not in g.data["kit"] and room_skills(g) == [350013]


def test_another_characters_room_is_left_alone(room):
    role, w, g, c = room
    other = {**char(level=20), "id": 2, "name": "Other"}
    g.data["char"] = other
    kit = dict(g.data["kit"])
    ask(role, w, guild.C2S_LEARN, struct.pack("<I", 100))
    assert room_skills(g) == [] and g.data["kit"] == kit


def test_a_closing_room_is_told_nothing(room):
    role, w, g, c = room
    g.w = types.SimpleNamespace(is_closing=lambda: True)
    assert ask(role, w, guild.C2S_LEARN, struct.pack("<I", 100))[0][1][:2] == bytes(2)
    assert room_skills(g) == [] and 350013 not in g.data["kit"]


def test_outside_a_room_a_core_waits_for_the_next_list(room):
    role, w, g, c = room
    del role, g
    st = State()
    st.world_sessions = {}
    role = world.make(st, 0, "127.0.0.1", 0)
    assert ask(role, w, guild.C2S_LEARN, struct.pack("<I", 100))[0][1][:2] == bytes(2)
    assert kit_of(c)[-1] == (350013, 1)


# --- the casts the client makes with a core held ---

@pytest.mark.parametrize("name", HOLDERS)
def test_the_guild_guard_is_the_class_guards_status_at_level_3(name):
    base, variant, st = GUARD[name]
    assert status.ability_statuses(base)[0][:2] == (st, 1)
    assert status.ability_statuses(variant)[0][:2] == (st, 3)
    assert status._basic()[variant]["Branch"] == "CHANT"
    assert combat._progress(st, 1, 1000.0, 1300.0) == 70 and combat._progress(st, 3, 1000.0, 1300.0) == 75
    groups = {r["AbilityId"]: r["CooldownGroupId"] for r in tables.sections("abilitycastinfo")["Basic"]}
    assert groups[str(variant)] == groups[str(base)]                # one clock, the client's


def test_the_guild_guard_cast_holds_and_ends_with_its_chant_and_stops_at_75():
    role, s = hero_session(a350013=1)
    use_ability(role, s, 350005)                                    # the id the client resolves the guard key to
    assert added(s)[-1] == (341, 3, combat.STATUS_HOLD_S, [0], 0)
    assert combat._progress(341, 3, 1000.0, 1300.0) == 75 and combat._progress(341, 1, 1000.0, 1300.0) == 70
    role.handlers[game.C2S_UNCHANT](s, pkt(game.C2S_UNCHANT, obf.u32(350005) + struct.pack("<H", 0)))
    assert ended(s)[-1] == (0, 341) and 341 not in status.holding(s, 0)


@pytest.mark.parametrize("name", HOLDERS)
def test_the_guild_escape_is_a_second_shorter_and_its_own_status_level(name):
    base, variant = ESCAPE[name]
    plain, row = status.cast_row(base, 1), status.cast_row(variant, 1)
    basic = {r["AbilityId"]: r for r in tables.sections("abilitycastinfo")["Improvement"] if r["SpotFilter"] == "COMMON"}
    assert basic[str(variant)]["StatusEffect1"] == "6321" and basic[str(variant)]["Level1"] == "1"
    assert plain["StatusEffect1"] == "6321" and plain["Level1"] == "3"
    assert int(float(plain["CooldownTime"])) - int(float(row["CooldownTime"])) == 1


def test_the_guild_escape_cast_makes_the_hero_invincible_for_its_row():
    role, s = hero_session(a350014=1)
    use_ability(role, s, 350009)
    assert added(s)[-1][:2] == (6321, 1) and added(s)[-1][2] == 1 and status.invincible(s, 0)
    role, s = hero_session(a14=1)
    use_ability(role, s, 14)
    assert added(s)[-1][:2] == (6321, 3) and added(s)[-1][2] == 3 and status.invincible(s, 0)


# --- a charged skill's stage statuses ---

def test_every_charged_stage_with_a_status_marks_its_executes_as_the_plain_row_does():
    # combat.charge_stage leaves ProcessStatusEffect<n> unread on this table fact; the 901 rows that differ have none
    for r in tables.sections("abilitytypeinfo")["Charge"]:
        plain = status.cast_row(int(r["AbilityId"]), int(r["Level"])) or {}
        for n in range(1, int(r["ChargeLevel"]) + 1):
            if str(r[f"StatusEffect{n}"]).isdigit():
                assert r[f"ProcessStatusEffect{n}"] == plain.get("ProcessStatusEffect"), (r["AbilityId"], n)
            assert r[f"StatusEffect{n}_2"] in ("", "-", "0")                                # no second slot is filled


def test_the_rain_of_arrows_rises_with_its_stage():
    levels = [status.ability_statuses(956, 1, stage)[0][:3] for stage in (0, 1, 2)]
    assert levels == [(6413, 1, "ENEMY"), (6413, 3, "ENEMY"), (6413, 5, "ENEMY")]
    assert status.ability_statuses(956, 1, 9) == status.ability_statuses(956, 1, 2)         # capped at ChargeLevel
    assert status.ability_statuses(1057, 1, 1)[0][1] == 4 and status.ability_statuses(1057, 1, 2)[0][1] == 6


def test_a_stage_with_no_status_puts_none_and_stage_0_is_the_plain_row():
    assert status.ability_statuses(1297, 1)[0][:2] == (3391, 1)
    assert status.ability_statuses(1297, 1, 1) == []
    assert status.ability_statuses(1297, 1, 0) == status.ability_statuses(1297, 1)


def test_a_skill_with_no_charge_row_keeps_its_row_at_any_stage():
    assert status.ability_statuses(164, 1, 3) == status.ability_statuses(164, 1)
    assert status.ability_statuses(62, 1, 2) == status.ability_statuses(62, 1)


def test_the_plain_rows_of_the_charged_skills_filter_nothing_a_stage_would_lose():
    # %Charge has no TargetBranch / TargetRace: the stage keeps the plain row's, and none of the 39 has one
    for a, level in {(r["AbilityId"], r["Level"]) for r in tables.sections("abilitytypeinfo")["Charge"]}:
        row = status.cast_row(int(a), int(level)) or {}
        assert all(row.get(k, "-") in ("", "-") for k in ("TargetBranch1", "TargetRace1", "TargetBranch2", "TargetRace2"))


def charged_cast(role, s, ability, steps, targets):
    """The hero's 0x5117, `steps` x 0x5062, one 0x5066, 0x506a; the cast's serial."""
    body = obf.u32(ability) + bytes(12) + struct.pack("<H", 0) + bytes(7) + obf.u16(0) + bytes(3)
    role.handlers[combat.C2S_USE_ABILITY](s, pkt(combat.C2S_USE_ABILITY, body))
    serial = s.data["cast_serial"]
    for _ in range(steps):
        role.handlers[combat.C2S_CHARGE_STEP](s, pkt(combat.C2S_CHARGE_STEP, struct.pack("<H", serial)))
    execute(role, s, serial, targets)
    role.handlers[combat.C2S_CAST_DONE](s, pkt(combat.C2S_CAST_DONE, struct.pack("<H", serial)))
    return serial


@pytest.mark.parametrize("steps, level", [(0, 1), (1, 3), (2, 5), (7, 5)])
def test_the_status_of_a_charged_cast_goes_out_at_its_stages_level(steps, level):
    role, s = hero_session(a956=1)
    s.data["zone_troops"] = {1: {"TroopTableID": 2, "TeamNum": 1}}
    s.data["battle"].add_np(1, 100000, 3)
    charged_cast(role, s, 956, steps, [1])
    assert added(s)[-1][:2] == (6413, level) and added(s)[-1][3] == [1]
    assert s.data.get("charge", {}) == {}


def test_a_cast_after_a_charged_one_is_plain_again():
    role, s = hero_session(a956=1)
    s.data["zone_troops"] = {1: {"TroopTableID": 2, "TeamNum": 1}}
    s.data["battle"].add_np(1, 100000, 3)
    charged_cast(role, s, 956, 2, [1])
    s.sent.clear()
    s.data["statuses"][1].pop(6413)
    charged_cast(role, s, 956, 0, [1])
    assert added(s)[-1][:2] == (6413, 1)


def test_the_dismiss_stage_of_1297_puts_nothing_on_the_caster():
    role, s = hero_session(a1297=1)
    charged_cast(role, s, 1297, 1, [])
    assert 3391 not in [a[0] for a in added(s)]
    charged_cast(role, s, 1297, 0, [])
    assert 3391 in [a[0] for a in added(s)]


def test_a_rooms_player_record_names_the_guild_and_no_guild_stays_empty():
    def record(c):
        _, s = entered(10235, c)
        return next(bytes(w.buf) for w in s.sent if w.proto == game.S2C_START_PLAYER_INFO)

    c, _ = army(1)
    name = c["name"].encode("latin-1") + b"\0"
    assert record(c).endswith(name + b"\0")
    c["guild"] = guild.new(c, "Ironwood", 1_800_000_000)
    assert record(c).endswith(name + b"Ironwood\0")

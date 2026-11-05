"""Regression tests for the battle relay (server/kuf2/combat.py) and the hero data game.py sends.
Run: py -m pytest -q server/tests"""
import struct
import time

import pytest

from kuf2 import combat, game, obf, status
from kuf2.obf import T1, T2
from kuf2.packet import Reader
from conftest import run_pending


class Session:
    def __init__(self):
        self.data = {"battle": combat.Battle()}
        self.sent = []

    def send(self, w):
        self.sent.append(w)


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def enc_uid(uid):
    return bytes([T2[uid >> 8], T1[uid & 0xff]])


def hit_header(troop=0, unit=0, action=72):
    """A 0x5053 header naming its attacker (combat.hit_source): +8 coded troop, +0xa unit << 7 | 29, +0xd action."""
    return bytes(8) + enc_uid(troop) + struct.pack("<H", (unit << 7) | 29) + bytes(1) + struct.pack("<H", action)


def hero_record(level=30, cls=0):
    """The hero's combatant record in his class kit (level 30: 31 physical attack + the Old Novice Longsword's 6 ~ 7 + the
    kit passive 70's 80 at its level 6, and its +1,500 penetration)."""
    return game.hero_combatant({"id": 1, "class": cls, "level": level})


class Even:
    """A resolver roll with no crit and V = 1 (the middle of every uniform draw)."""
    def uniform(self, a, b):
        return (a + b) / 2

    def random(self):
        return 1.0


def hit_until_down(role, s, uid, header, cap=2000):
    """0x5053 hits on every unit of troop uid until it is wiped; returns how many reports it took."""
    for n in range(1, cap + 1):
        units = s.data["battle"].troops[uid]["units"]
        target = enc_uid(uid) + struct.pack("<H", len(units)) + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in
                                                                          range(len(units)))
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, header + struct.pack("<H", 1) + target + struct.pack("<H", 0)))
        if not any(s.data["battle"].troops[uid]["units"]):
            return n
    raise AssertionError(f"troop {uid} still stands after {cap} hits")


def parse_stat(b):
    """Python port of the client's stat-entry parser 0x141593210, value form only (code < 0x80)."""
    code = b[1]
    if code == 0: return b[0], b[2] + 0x3e, 3
    if code == 1: return b[0], -0x3e - b[2], 3
    if code == 2: return b[0], struct.unpack_from("<H", b, 2)[0] + 0x13e, 4
    if code == 3: return b[0], -0x13e - struct.unpack_from("<H", b, 2)[0], 4
    if code == 4: return b[0], struct.unpack_from("<i", b, 2)[0], 6
    return b[0], code - 0x42, 2


@pytest.mark.parametrize("value", [-70000, -500, -62, -61, 0, 3, 61, 62, 317, 318, 800, 7500, 65853, 65854, 10**6])
def test_stat_encoding_round_trips(value):
    enc = game.encode_stat(14, value)
    assert parse_stat(enc) == (14, value, len(enc))


def test_hero_stats_block_has_move_speed_for_every_class():
    for cls in range(6):
        block = game.encode_stats(game.HERO_STATS[cls])
        assert block[0] == 0                                   # no troop stats
        i, seen = 1, {}
        while i < len(block):
            sid, v, n = parse_stat(block[i:])
            seen[sid] = v
            i += n
        assert seen.get(14, 0) > 0, f"class {cls}: no MAX_MOVE_SPEED -> the hero runs in place"


@pytest.mark.parametrize("cls", range(6))
def test_every_class_has_starter_abilities(cls):
    assert game.STARTER_ABILITIES.get(cls), f"class {cls} gets no abilities -> no attacks"


@pytest.mark.parametrize("handler,proto,body", [
    (combat.on_combat_mode, 0x5132, b"\x10\xc3"),
    (combat.on_engage, 0x5058, b"\x10\xc3\x01"),
    (combat.on_use_ability, 0x5117, bytes(10)),
])
def test_short_requests_are_ignored(handler, proto, body):
    s = Session()
    handler(s, pkt(proto, body))                               # must not raise (a raise ends the game session)
    assert s.sent == []


@pytest.mark.parametrize("uid,on", [(0, True), (0, False), (0x1234, True)])
def test_combat_mode_reply(uid, on):
    # the client's request (0x5132) is answered at once (0x5133), whatever the hero is doing
    s = Session()
    s.data["battle"].add_hero(uid, 1000)
    b = enc_uid(uid)
    combat.on_combat_mode(s, pkt(0x5132, b + bytes([T2[(int(on) + 2 * b[0]) & 0xff]])))
    out = bytes(s.sent[-1].buf)
    assert (out[0], struct.unpack_from("<H", out, 1)[0], T1[out[3]] & 1) == (1, uid, int(on))
    assert s.data["battle"].troops[uid]["combat"] == on


def combat_mode_pushes(s):
    """The 0x5133 pushes for the hero (troop 0), as their on / off bits."""
    return [T1[bytes(w.buf)[3]] & 1 for w in s.sent
            if w.proto == combat.S2C_COMBAT_MODE and struct.unpack_from("<H", bytes(w.buf), 1)[0] == 0]


def test_the_heros_request_puts_him_in_combat_at_once_mid_swing_and_mid_run():
    # live 2026-09-30 14:17:44-14:18:00 (field 10350, Isabella): the request waited for a stand the server guessed from
    # 0x50b0 (combat.maybe_draw); for 16 s she fought with the flag off, so between her swings the client played the
    # town set (0x50db 602 MOVE_NORMAL_RUN at 14:17:47.26 / 53.83 / 58.87, 601 COMMON_NORMAL_STAND at 48.31 / 59.15;
    # in Grey Fog 13:52:33-13:53:26, 53 s). The client asks only when a swing or a guard starts (0x140bf5b30), so no
    # answer can reach it standing; its setter 0x140bf9730 plays the draw itself whenever it finds the hero standing.
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    combat.hero_moved(s, (1000, 0, 1000))
    combat.hero_moved(s, (1500, 0, 1000))                           # running
    b = enc_uid(0)
    combat.on_combat_mode(s, pkt(0x5132, b + bytes([T2[(1 + 2 * b[0]) & 0xff]])))
    assert s.data["battle"].troops[0]["combat"] and combat_mode_pushes(s) == [1]


def test_the_combat_mode_is_never_turned_off_and_on_again_mid_fight(monkeypatch):
    # live 2026-09-30 14:18:19.876 (field 10350) the redraw's off made her play the sheath 606 COMMON_STAND_TO_NORMAL
    # mid-fight; she ran (0x50db 602 at 14:18:20.686) and its on, 1.5 s later on a timer, landed while she ran: no draw,
    # the combat set after a sheath. The same at 13:51:11.966 / 13:51:13.468 in 10352 (run reported 13:51:13.445).
    now = [1000.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    combat.hero_moved(s, (1500, 0, 1000))
    combat.hero_moved(s, (1500, 0, 1000))                           # standing
    b = enc_uid(0)
    for _ in range(6):                                             # she fights: her swings re-ask every 2 s
        combat.on_combat_mode(s, pkt(0x5132, b + bytes([T2[(1 + 2 * b[0]) & 0xff]])))
        now[0] += 2
        combat.hero_moved(s, (1500, 0, 1000))
        run_pending(s)
    assert combat_mode_pushes(s) == [1] * 6 and s.data["battle"].troops[0]["combat"]     # no off between the swings
    for _ in range(4):                                             # then she stands, quiet: one off (owner B1
        now[0] += 10                                               # 2026-09-30, combat.PEACE_S), no redraw
        combat.hero_moved(s, (1500, 0, 1000))
        run_pending(s)
    assert combat_mode_pushes(s) == [1] * 6 + [0] and not s.data["battle"].troops[0]["combat"]


@pytest.mark.parametrize("still", [True, False])
def test_an_engagement_or_a_hit_puts_the_hero_in_combat_at_once(still):
    # standing, the client's setter plays the draw 0x25f; moving, it flips the flag and the next run or stand is the
    # combat set's (38 MOVE_RUN, 50 COMBAT_CAUTION_STAND): no need to hold the push for a stand the server guesses
    for how in ("engage", "hit"):
        role = game.make(NoSave(), 0)
        s = FieldSession({"active": {}, "done": []})
        s.data["battle"] = combat.Battle()
        s.data["battle"].add_hero(0, 1000, c=record(100, 1, team=0))
        s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(1, 1))
        combat.hero_moved(s, (1000, 0, 1000))
        combat.hero_moved(s, (1000 if still else 1500, 0, 1000))
        if how == "engage":
            role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, obf.u16(20001) + bytes([1]) + obf.u16(0)))
        else:
            combat.apply_hits(s, [(0, [0])], game.send_troop_hp, attacker=20001, attack={"pr": 1.0, "ar": 1.0})
        assert s.data["battle"].troops[0]["combat"] and combat_mode_pushes(s) == [1], how


def test_use_ability_confirmation_layout():
    req = bytes.fromhex("3bc310c310fc9862220410fdffd510c3000010fc98622204109716030110fc9862220410")
    s = Session()
    combat.on_use_ability(s, pkt(0x5117, req))
    out = bytes(s.sent[-1].buf)
    ability = (T2[out[0x12]] << 24) | (T1[out[0x13]] << 16) | (T2[out[0x14]] << 8) | T1[out[0x11]]
    assert len(out) == 30 + len(req) - 0x1b and ability == 164 and out[0x15:0x1c] == req[0x12:0x19]


def test_room_start_and_troop_state_build_for_every_class():
    """The whole battle entry sequence builds without errors for each class (a NameError here killed the login)."""
    for cls in range(6):
        s = Session()
        s.data.update(account={"characters": [{"id": 1, "class": cls, "level": 1, "name": "T", "look": "00" * 0x33}]}, spot=10303)
        game.send_start_header(s, 10303)
        game.send_enter_cell(s)
        game.send_mission_troop_info(s)
        assert [w.proto for w in s.sent] == [0x3f4e, 0x3f4f, 0x3f50, 0x3f4e, 0x50cb, 0x50b8]


EXEC_5066 = bytes.fromhex("a9a8a45cf30410060001000001000500a00120010002800120000000")[:27]


def test_ability_execute_reply_echoes_targets_with_caster():
    s = Session()
    s.data["casts"] = {6: b"\x00\x00"}
    combat.on_ability_execute(s, pkt(0x5066, EXEC_5066))
    out = bytes(s.sent[-1].buf)
    assert struct.unpack_from("<H", out, 0)[0] == 6 and T1[out[2]] & 1 == 0 and out[3:5] == b"\x00\x00"
    assert out[5:] == EXEC_5066[9:26]                     # u16 n=1, (0, troop 1, m=5, 5 unit indexes)


def test_cast_done_and_engage_clear_replies():
    s = Session()
    combat.on_cast_done(s, pkt(0x506a, bytes.fromhex("0d00")))
    combat.on_engage_clear(s, pkt(0x506d, bytes.fromhex("0000")))
    assert bytes(s.sent[0].buf) == bytes.fromhex("000000000d00") and bytes(s.sent[1].buf) == bytes.fromhex("0000")


@pytest.mark.parametrize("handler,proto,body", [
    (combat.on_ability_execute, 0x5066, bytes(8)),
    (combat.on_cast_done, 0x506a, b"\x01"),
    (combat.on_engage_clear, 0x506d, b"\x00"),
])
def test_short_battle_requests_are_ignored(handler, proto, body):
    s = Session()
    handler(s, pkt(proto, body))
    assert s.sent == []


def test_battle_start_stubs_registered():
    role = game.make(None, 0)
    for req in (0x513b, 0x513d, 0x5146):
        s = Session()
        role.handlers[req](s, pkt(req, b""))
        assert s.sent[-1].proto == req + 1


def test_world_stubs_registered():
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    for req, size in ((0x534c, 2), (0x545d, 12), (0x5240, 3), (0x5251, 3)):
        s = Session()
        s.data["char"] = {}                     # no mail: 0x5251 is the empty list
        role.handlers[req](s, pkt(req, b"\x00"))
        assert s.sent[-1].proto == req + 1 and bytes(s.sent[-1].buf) == bytes(size)



def test_travel_to_field_answers_prepare_enter_town():
    from kuf2 import world

    class State:
        saves = 0

        def save(self):
            self.saves += 1
    st = State()
    s = Session()
    s.data["char"] = {"spot": 10001, "pos": [0, 0, 0]}
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[0x3744](s, pkt(0x3744, struct.pack("<I", 10352)))
    assert st.saves == 1
    out = s.sent[-1]
    assert out.proto == 0x3745 and struct.unpack_from("<HI", out.buf, 0) == (0, 10352)
    assert s.data["char"]["spot"] == 10352 and s.data["char"]["pos"] == [329756, 0, 175403]



def gold_of(b):
    from kuf2.obf import T1, T2
    return (T1[b[0]] << 32) | (T2[b[2]] << 24) | (T1[b[3]] << 16) | (T2[b[1]] << 8) | T1[b[4]]


def test_cargo_carries_gold_and_open_slots():
    from kuf2 import world
    s = Session()
    s.data["char"] = {"gold": 123456}
    world.send_cargo(s)
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_CARGO and gold_of(out) == 123456
    assert struct.unpack_from("<hH", out, 5) == (world.CARGO_SLOTS, 0) and len(out) == 9


@pytest.mark.parametrize("v", [0, 1, 50, 0x12345678, 0xFFFFFFFFFF])
def test_u40_round_trips(v):
    from kuf2 import obf
    assert gold_of(obf.u40(v)) == v



def warp_req(warp, x, y, z):
    from kuf2 import obf
    q, p15 = obf.pos_xz(x, z)
    return obf.u32(warp) + q + struct.pack("<h", y) + bytes([p15])


def test_crystal_warp_start_and_use():
    from kuf2 import obf, world

    class State:
        saves = 0

        def save(self):
            self.saves += 1
    st = State()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"spot": 10352, "pos": [0, 0, 0]}
    req = warp_req(6200, 329935, 120, 174344)
    role.handlers[world.C2S_WARP_START](s, pkt(world.C2S_WARP_START, req))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_WARP_START and len(out) == 10
    assert obf.dec_u32(out[4:8]) == 6200 and struct.unpack_from("<h", out, 8)[0] == 0
    role.handlers[world.C2S_WARP_USE](s, pkt(world.C2S_WARP_USE, req))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_WARP_USE and out == b"\0\0" + req
    assert s.data["char"]["pos"] == [329935, 120, 174344] and st.saves == 1


@pytest.mark.parametrize("proto", [0x4071, 0x4069])
def test_short_warp_requests_are_ignored(proto):
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"spot": 10352}
    role.handlers[proto](s, pkt(proto, bytes(5)))
    assert s.sent == []



@pytest.mark.parametrize("start,gain,level,exp", [((1, 0), 13, 1, 13), ((1, 70), 13, 2, 3), ((1, 0), 80 + 300 + 5, 3, 5),
                                                  ((30, 0), 99999999, 30, 99999999)])
def test_exp_levels_up_through_the_hero_curve(start, gain, level, exp):
    from kuf2 import world

    class State:
        def save(self):
            pass
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "level": start[0], "exp": start[1]}
    world.add_exp(s, State(), gain)
    assert (s.data["char"]["level"], s.data["char"]["exp"]) == (level, exp)
    sent = next(w for w in s.sent if w.proto == world.S2C_EXP)
    out = bytes(sent.buf)
    assert len(out) == 5 + 306
    assert struct.unpack_from("<i", out, 1)[0] == 1
    lv, xp, need = struct.unpack_from("<BQQ", out, 5 + 9 * 17)
    assert (lv, xp) == (level, exp) and need == (world.hero_need(level) or 0)



def test_hero_detail_carries_uid_level_and_exp():
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"id": 7, "class": 5, "level": 2, "exp": 30}
    role.handlers[world.C2S_HERO_DETAIL](s, pkt(world.C2S_HERO_DETAIL, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_HERO_DETAIL and out[world.HERO_BLOCK] == 0     # Helena's kit: none (all -1)
    assert struct.unpack_from("<Q", out, world.HERO_UID_AT)[0] == 7 and out[world.HERO_LEVEL_AT] == 2
    assert struct.unpack_from("<Q", out, world.HERO_EXP_AT)[0] == 30
    assert struct.unpack_from("<Q", out, world.HERO_NEED_AT)[0] == world.hero_need(2)



def test_item_record_round_trips():
    from kuf2 import items
    rec = items.record(150000001, 3, (7 << 32) | 3, count=2, durability=100)
    assert len(rec) == items.HEAD + 10
    assert items.decode_head(rec) == (150000001, 3, 2, (7 << 32) | 3)


def test_hero_detail_equips_the_class_kit():
    from kuf2 import hero, items, world
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "level": 1, "exp": 0}
    world.send_hero_detail(s)
    out = bytes(s.sent[-1].buf)
    n = out[world.HERO_BLOCK]
    kit = hero.starter_kit(0)                          # herotable %Inventory: the Old Novice set, no sub weapon
    assert n == len(kit) == 6
    recs = [out[world.HERO_BLOCK + 1 + i * (items.HEAD + 10):][:items.HEAD] for i in range(n)]
    assert [items.decode_head(r)[:2] for r in recs] == [(code, part - 1) for part, code in kit]


def client_stat_decode(b):
    """0x14061b040, as the client reads a coded stat."""
    u = (struct.unpack_from("<H", b)[0] << 16) | struct.unpack_from("<H", b, 2)[0]
    k, low = u >> 30, u & 0x3fffffff
    return (u, low * 2 + 0x40000000, low * 5 + 0xc0000000, low * 10 + 0x200000000)[k]


@pytest.mark.parametrize("v", [0, 1, 250, 0x3fffffff, 0x40000000, 0x40000001, 0xbfffffff, 0xc0000000, 0x1ffffffff])
def test_stat_code_round_trips_as_the_client_decodes(v):
    from kuf2 import world
    got = client_stat_decode(world.stat_code(v))
    assert got == v if v < 0x40000000 else abs(got - v) < 10    # beyond 2^30 the codec's 2 / 5 / 10 steps


def test_hero_stats_come_from_the_tables():
    from kuf2 import hero, items, tables, world
    kit = [e["code"] for e in hero.equipment({"id": 1, "class": 0})]
    st = hero.stats(0, 1, kit)
    base = next(r for r in tables.sections("herotable")["Contents"] if r["CHARACTER_TYPE"] == "GLEN")
    hp = next(r for r in tables.sections("lvuptypetable")["Hero_HP"] if r["ID"] == "GLEN")
    traits = [t for code in kit for t in items.traits(code)]
    assert st["ATTACK_PHYSICAL"] == float(base["ATTACK_PHYSICAL"]) == 3
    assert st["HP_MAX"] == float(hp["LV_1"]) + sum(v for n, v, _ in traits if n == "HP_MAX") == 31 + 371   # Old Novice Top
    assert st["DEFENCE_PHYSICAL_CLOSE"] == st["DEFENCE_PHYSICAL_RANGE"] == \
        sum(v for n, v, _ in traits if n == "M_DEFENCE_PHYSICAL") == 70
    assert len({st[n] for n in hero.MAGICAL_DEFENCES}) == 1 and st["DEFENCE_MAGICAL_FIRE"] == 45
    assert st["SP_MAX"] == 200 and st["SP_CURRENT"] == 150 and st["MAX_MOVE_SPEED"] == 800


@pytest.mark.parametrize("cls", range(6))
def test_the_hero_carries_his_hit_resist_so_light_blows_do_not_stagger_him(cls):
    """The client plays a hero's hit reaction only when the blow's AttackResistValue (its NewHit signal: a kobold's
    ATTACK_NORMAL_COMMON_1 / _2 10, its strong and dash blows 15, its counter and strong skill 30) reaches the hero's
    HIT_RESIST (stat 40, re-read into unit +0x710 on every action by 0x140a14980; the test in 0x140a2bde0). We never
    sent stat 40, so it was 0 and every blow staggered him (Grey Rock 2026-09-30 16:47-16:50: the 5 hits whose knock
    bit was set were the 5 DAMAGE_STANDING reactions). The value is herotable %System HITRESIST."""
    from kuf2 import hero, tables
    row = next(r for r in tables.sections("herotable")["System"] if r["CHARACTER_TYPE"] == hero.HERO_CODE[cls])
    c = {"id": 1, "class": cls, "level": 6}
    assert hero.stats(cls, 6, ())["HIT_RESIST"] == float(row["HITRESIST"]) == 15
    block = game.encode_stats(game.hero_stat_values(c))         # the troop-state stat block (0x50cb / 0x50b8)
    i, seen = 1, {}
    while i < len(block):
        sid, v, n = parse_stat(block[i:])
        seen[sid] = v
        i += n
    assert seen[40] == 15                                       # 40 HIT_RESIST: a kobold's 10 no longer knocks


def test_hero_growth_applies_from_level_two():
    from kuf2 import hero
    assert hero.stats(0, 1, ())["ATTACK_PHYSICAL"] == 3
    assert abs(hero.stats(0, 3, ())["ATTACK_PHYSICAL"] - (3 + 2 * 0.966)) < 1e-9     # lvuptypetable Hero GLEN
    assert hero.stats(0, 3, ())["HP_MAX"] == 59                                     # Hero_HP GLEN LV_3


def test_every_class_kit_belongs_to_its_hero():
    from kuf2 import hero, items
    for cls in range(5):                               # Helena has none
        assert {items.row(code)["ReqHero"] for _, code in hero.starter_kit(cls)} == {hero.HERO_CODE[cls]}


def test_every_wearable_item_trait_parses():
    from kuf2 import items, tables
    for name in ("item_weapon", "item_defence"):      # item_consume has text values ("50%.") for used, not worn, items
        for r in tables.load(name):
            items.traits(int(r["ItemCode"]))


def test_hero_detail_block_carries_the_stats_where_the_panel_reads_them():
    from kuf2 import world
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "level": 1, "exp": 0}
    world.send_hero_detail(s)
    out = bytes(s.sent[-1].buf)
    i32 = lambda at: struct.unpack_from("<i", out, at)[0]      # noqa: E731
    assert (i32(0x7c), i32(0x1c)) == (90, 100)                 # attack 3.0 + the Old Novice Longsword's 6 ~ 7, tenths
    assert client_stat_decode(out[0x98:]) == 402 and client_stat_decode(out[0x60:]) == 5    # HP_MAX, HP_RECOVERY
    assert client_stat_decode(out[0x8c:]) == 402                # current HP: full
    assert i32(0x4c) == i32(0x30) == 70 and i32(0x20) == 45     # physical close / range, fire
    assert struct.unpack_from("<f", out, 0x34)[0] == 750.0 + 758     # CRITICAL_PHYSICAL, the sword's 758 added
    assert i32(0x38) == 800 and i32(0x48) == 7500 and i32(0x84) == 100     # move speed, sight, attack speed
    assert i32(0x00) == 200 and i32(0xb1) == 200                # SP_CURRENT (the pool full, as the tape's town), SP_MAX
    assert out[world.HERO_LEVEL_AT] == 1 and struct.unpack_from("<Q", out, world.HERO_UID_AT)[0] == 1
    ats = [(at, 4) for at in world.HERO_STAT_AT.values()] + [(at, 4) for at in world.HERO_STAT_F32_AT.values()] + \
        [(at, 4) for at in world.HERO_ATTACK_AT.values()] + [(at, 4) for at in world.HERO_STAT_CODED_AT.values()] + \
        [(world.HERO_UID_AT, 8), (world.HERO_EXP_AT, 8), (world.HERO_NEED_AT, 8), (world.HERO_LEVEL_AT, 1),
         (world.HERO_CLASS_AT, 4)]
    used = [a + k for a, n in ats for k in range(n)]
    assert len(used) == len(set(used)) and max(used) < world.HERO_BLOCK      # no two fields share a byte


def test_start_game_carries_exp_and_the_level_cap():
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    c = {"id": 4, "name": "A", "class": 0, "level": 1, "exp": 50, "tutorial_done": True, "spot": world.START_SPOT,
         "bag_slots": world.CARGO_SLOTS,
         "pos": list(world.START_POS)}
    s.data["account"] = {"characters": [c]}
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
    out = bytes(next(w for w in s.sent if w.proto == world.S2C_START_GAME_RES).buf)
    p, q = out[2:2 + 0x25], out[2 + 0x25:2 + 0x25 + 0x20]
    assert len(out) == 2 + 0x25 + 0x20
    assert struct.unpack_from("<q", p, 1)[0] == 50             # PlayerInfo +0x18: the exp the HUD bar shows
    assert q[1] == world.hero_max_level() == 30                # PlayerInfo +0x31: the bar fills while level < cap


class Saves:
    n = 0

    def save(self):
        self.n += 1


def test_add_item_stacks_then_fills_free_slots():
    from kuf2 import world
    s, st = Session(), Saves()
    s.data["char"] = {"id": 2, "class": 0, "gold": 0}
    assert world.add_item(s, st, 350000010, 60) == 0                # consumable, MaxStack 100
    assert world.add_item(s, st, 350000010, 60) == 0
    assert [(i["slot"], i["count"]) for i in s.data["char"]["bag"]] == [(0, 100), (1, 20)]
    assert world.add_item(s, st, 101101110, 2) == 0                  # a weapon: one per slot
    assert [(i["code"], i["slot"], i["count"]) for i in s.data["char"]["bag"][2:]] == [(101101110, 2, 1),
                                                                                        (101101110, 3, 1)]
    assert len({i["serial"] for i in s.data["char"]["bag"]}) == 4 and st.n == 3


def test_add_item_reports_what_does_not_fit():
    from kuf2 import world
    s, st = Session(), Saves()
    s.data["char"] = {"id": 2, "class": 0, "bag": [{"code": 101101110, "slot": n, "count": 1, "serial": n}
                                                   for n in range(world.CARGO_SLOTS - 1)]}
    assert world.add_item(s, st, 102101110, 3) == 2
    assert s.data["char"]["bag"][-1]["slot"] == world.CARGO_SLOTS - 1


def test_equip_request_codec_round_trips():
    from kuf2 import obf
    body = bytes.fromhex("10c7c7c398c3c3c310c710c3c7c3c3c310c31012")     # live 2026-09-27: reward sword -> index 0
    assert (obf.dec_u64(body[0:8]), obf.dec_u64(body[8:16]), obf.dec_u16(body[16:18]), obf.dec_u16(body[18:20])) == \
        (0x100010002, 0x100000001, 0, 1)
    assert obf.u64(0x100010002) == body[0:8]


def equip_char():
    from kuf2 import hero
    c = {"id": 1, "class": 0, "level": 1,
         "bag": [{"code": 350000010, "slot": 0, "count": 1, "serial": 0x100010001, "bound": False},
                 {"code": 101101110, "slot": 1, "count": 1, "serial": 0x100010002, "bound": True}]}
    hero.equipment(c)
    return c


def test_equip_swaps_the_bag_item_with_the_worn_one():
    from kuf2 import world
    c = equip_char()
    assert world.change_equip(c, 0x100010002, 0x100000001, 0, 1) is None
    assert {e["index"]: e["code"] for e in c["equip"]}[0] == 101101110
    assert [(i["slot"], i["code"], i["serial"]) for i in c["bag"]] == [(0, 350000010, 0x100010001),
                                                                      (1, 101101119, 0x100000001)]


def test_unequip_into_a_free_slot_and_back():
    from kuf2 import world
    c = equip_char()
    assert world.change_equip(c, 0, 0x100000006, 5, 5) is None                      # the gloves to bag slot 5
    assert all(e["index"] != 5 for e in c["equip"]) and c["bag"][-1]["slot"] == 5
    assert world.change_equip(c, 0x100000006, 0, 5, 5) is None                      # and back on
    assert {e["index"]: e["serial"] for e in c["equip"]}[5] == 0x100000006 and len(c["bag"]) == 2


@pytest.mark.parametrize("args", [
    (0x100010002, 0x100000009, 0, 1),     # the worn serial is not what the client thinks
    (0x100010002, 0x100000001, 0, 3),     # the bag item is not in that slot
    (0x100010001, 0x100000001, 0, 0),     # a potion into the main weapon
    (0, 0x100000001, 0, 0),               # unequip into a taken slot
    (0, 0, 9, 7),                         # nothing on either side
    (0x100010002, 0, 8, 1),               # a sword into a ring slot (raised StopIteration before rings were mapped)
    (0x100010002, 0, 11, 1),              # a costume index (not mapped)
    (0, 0x123, 8, 7),                     # a worn serial where nothing is worn (the message raised TypeError)
])
def test_equip_refusals_leave_everything_in_place(args):
    import copy
    from kuf2 import world
    c = equip_char()
    before = copy.deepcopy(c)
    assert world.change_equip(c, *args) is not None and c == before


def test_equip_handler_replies_and_resends_the_hero():
    from kuf2 import obf, world

    class St:
        saves = 0

        def save(self):
            self.saves += 1
    st = St()
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = equip_char()
    body = obf.u64(0x100010002) + obf.u64(0x100000001) + bytes([obf.via_t1(0), obf.via_t2(0), obf.via_t1(0),
                                                                   obf.via_t2(1)])
    role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
    assert [w.proto for w in s.sent] == [world.S2C_EQUIP, world.S2C_HERO_DETAIL,
                                       world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert bytes(s.sent[0].buf) == b"\0\0"
    assert st.saves == 1


def test_idle_state_is_answered_for_the_hero():
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "name": "Aldric"}
    role.handlers[world.C2S_IDLE](s, pkt(world.C2S_IDLE, bytes.fromhex("5001")))    # live 02:57: idle level 1
    role.handlers[world.C2S_IDLE](s, pkt(world.C2S_IDLE, bytes.fromhex("ffff")))
    assert [(w.proto, bytes(w.buf)) for w in s.sent] == [(world.S2C_IDLE, struct.pack("<iB", 1, 1)),
                                                          (world.S2C_IDLE, struct.pack("<iB", 1, 0))]


def test_chat_is_echoed_with_the_sender_name():
    from kuf2 import world
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "name": "Aldric"}
    role.handlers[world.C2S_CHAT](s, pkt(world.C2S_CHAT, bytes.fromhex("0b2f62626c00")))  # live 02:57: "/bbl"
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_CHAT
    assert out == b"\x0b" + bytes(world.CHAT_HEADER) + b"Aldric\x00/bbl\x00"


def test_login_time_codec_matches_the_client_reader():
    from kuf2 import obf
    from kuf2.obf import T1, T2
    for v in (0, 1, 1790464661, 0x0102030405060708, 2 ** 64 - 1):
        b = obf.time64(v)
        # 0x1405aa3d0, transcribed
        got = ((((((((T2[b[7]] << 8 | T1[b[0]]) << 8 | T2[b[6]]) << 8 | T1[b[1]]) << 8 | T2[b[3]]) << 8 | T1[b[2]])
                  << 8 | T2[b[5]]) << 8) | T1[b[4]])
        assert got == v == obf.dec_time64(b)


def test_paid_portal_charges_on_arrival_and_refuses_when_short():
    from kuf2 import obf, world

    class State:
        def save(self):
            pass
    role = world.make(State(), 0, "127.0.0.1", 0)
    s = Session()
    s.data = {"char": {"spot": 10352, "pos": [0, 0, 0], "gold": 2500}}      # a world session (no battle room)
    req = warp_req(1601, 1000, 0, 2000)                      # warpinfo %Portal 1601: Cost_Gold 2000
    role.handlers[world.C2S_WARP_START](s, pkt(world.C2S_WARP_START, req))
    assert struct.unpack_from("<h", bytes(s.sent[-1].buf), 8)[0] == 0
    role.handlers[world.C2S_WARP_USE](s, pkt(world.C2S_WARP_USE, req))
    assert s.data["char"]["gold"] == 500 and s.sent[-1].proto == world.S2C_GOLD
    s.sent.clear()
    role.handlers[world.C2S_WARP_START](s, pkt(world.C2S_WARP_START, req))
    out = bytes(s.sent[-1].buf)
    assert struct.unpack("<I", out[:4])[0] == 2000 and struct.unpack_from("<H", out, 8)[0] == world.WARP_NO_GOLD
    assert world.warp_cost(6200) == 0


def test_rings_go_in_both_accessory_slots_and_old_saves_convert():
    from kuf2 import hero, items, world
    from kuf2 import tables
    ring = next(int(r["ItemCode"]) for r in tables.load("item_accessory") if r["Parts"] == "ACC1")
    c = {"id": 1, "class": 0, "level": 1, "equip": [{"code": 100000001, "part": 1, "serial": 5, "bound": True}],
         "bag": [{"code": ring, "slot": 0, "count": 1, "serial": 7, "bound": True},
                 {"code": ring, "slot": 1, "count": 1, "serial": 8, "bound": True}]}
    assert hero.equipment(c) == [{"code": 100000001, "index": 0, "serial": 5, "bound": True}]
    assert world.change_equip(c, 7, 0, 7, 0) is None and world.change_equip(c, 8, 0, 8, 1) is None
    assert sorted(e["index"] for e in c["equip"]) == [0, 7, 8] and c["bag"] == []
    assert world.change_equip(c, 0, 0, 9, 0) is not None                            # nothing there


def test_weapon_base_attack_makes_the_attack_range():
    from kuf2 import hero
    st = hero.stats(0, 1, [101101110])            # Adventurer Longsword: BasePhysical 6 ~ 7 (the tooltip's range)
    assert (st["ATTACK_PHYSICAL_MIN"], st["ATTACK_PHYSICAL_MAX"]) == (9, 10)
    assert (st["ATTACK_MAGICAL_MIN"], st["ATTACK_MAGICAL_MAX"]) == (0, 0)
    st = hero.stats(0, 1, [100000001])            # the kit sword carries none
    assert st["ATTACK_PHYSICAL_MIN"] == st["ATTACK_PHYSICAL_MAX"] == 3


LIVE_HIT = bytes.fromhex("d0bfb778db0ea7010001000033270100000000")   # 0x5066 body, live 2026-09-27: troop 10035 unit 0


def test_ability_hit_targets_parse():
    assert combat.ability_targets(LIVE_HIT, 9) == [(10035, [0])]


def test_ability_hit_damages_and_downs_the_target():
    s = Session()
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=hero_record(30))            # 31 attack: at least 27 a hit
    s.data["battle"].add_np(10035, 20, 1)
    s.data["casts"] = {1: struct.pack("<H", 0)}
    hp, down = [], []
    combat.on_ability_execute(s, pkt(combat.C2S_ABILITY_EXECUTE, LIVE_HIT),
                              lambda s, uid, troop_hp, leader_hp=None: hp.append((uid, troop_hp)),
                              lambda s, uid: down.append(uid))
    assert s.sent[0].proto == combat.S2C_ABILITY_EXECUTE and hp == [(10035, 0)] and down == [10035]


def test_a_cast_does_not_hit_its_own_troop():
    s = Session()
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_np(10035, 31, 1)
    s.data["casts"] = {1: struct.pack("<H", 10035)}
    hp = []
    combat.on_ability_execute(s, pkt(combat.C2S_ABILITY_EXECUTE, LIVE_HIT),
                              lambda s, uid, troop_hp, leader_hp=None: hp.append(uid))
    assert hp == []


def read_prop(b):
    """Python port of the 0x50d1 record fields 0x140d062c0 reads (T2 = its runtime table *0x1434a65b0)."""
    prop_id = (T2[b[4]] << 24) | (T1[b[5]] << 16) | (T2[b[6]] << 8) | T1[b[3]]
    x = ((T1[b[9]] & 0xf0) << 12) | (T1[b[10]] << 8) | T2[b[13]]
    z = ((T1[b[9]] & 0xf) << 16) | (T1[b[11]] << 8) | T2[b[12]]
    x, z = (v - 0x100000 if v > 0x7ffff else v for v in (x, z))
    return {"id": prop_id, "alive": T1[b[2]] & 1, "shown": T1[b[7]] & 1, "x": x, "z": z,
            "state": struct.unpack_from("<i", b, 14)[0]}


@pytest.mark.parametrize("prop_id, pos, shown", [(10012, (309641, 176113), True), (10257, (-5, 524287), False),
                                                  (0x7fffffff, (-524288, 0), True)])
def test_prop_record_reads_back(prop_id, pos, shown):
    from kuf2.packet import Writer
    w = Writer(game.S2C_PROP_LIST)
    game.write_prop(w, prop_id, pos, shown)
    rec = bytes(w.buf)
    assert len(rec) == 23
    assert read_prop(rec) == {"id": prop_id, "alive": 1, "shown": int(shown), "x": pos[0], "z": pos[1], "state": 0}


def test_prop_visibility_follows_hide_and_quests():
    r = {"active": {}, "done": []}
    assert game.prop_shown(64, r)                   # barricade: trigger-only but opened with F (2 s cast)
    assert not game.prop_shown(592, r)              # road-block tree: trigger-only, no cast: nothing opens it
    assert not game.prop_shown(592, r)              # road-block tree, same
    assert game.prop_shown(432, r)                  # breakable barricade (TYPE_ATTACK): the player's to break
    assert not game.prop_shown(402, r)              # cocoon: hidden until 1150201 is held
    r["active"]["1150201"] = {"counts": [0] * 5}
    assert game.prop_shown(402, r)
    assert not game.prop_shown(598, r)              # FinishOrCompletedQuest 1150205
    r["done"].append(1150205)
    assert game.prop_shown(598, r)
    assert game.prop_shown(999999, r)               # unknown type: the client's own prop, left shown


def test_field_entry_lists_every_zone_prop():
    s = Session()
    c = {"quests": {"active": {"1150201": {"counts": [0] * 5}}, "done": []}}
    game.send_zone_props(s, 10352, c)
    out = bytes(s.sent[-1].buf)
    n = struct.unpack_from("<H", out, 0)[0]
    recs = [read_prop(out[2 + 23 * i:25 + 23 * i]) for i in range(n)]
    assert s.sent[-1].proto == game.S2C_PROP_LIST and n == 150 and len(out) == 2 + 23 * n
    by_id = {r["id"]: r for r in recs}
    assert by_id[10012]["x"] == 309641 and by_id[10012]["z"] == 176113
    # hidden until their quests: 403, 404, 434, the 433 item boxes, 598/599; trigger-only: 64, 448-451, 553, 592-594
    assert sum(r["shown"] for r in recs) == 150 - (1 + 3 + 6 + 6 + 2) - (14 + 18)     # walls, trees


def test_quest_staging_props_are_shown_but_not_usable():
    # Mist Field 10350: prop 10293 (type 421, RequireQuestID_SW "1") stands beside the Nameless Mercenary's Grave (NPC
    # 651); in state 0 it took F from the grave and quest 1150316's Talk could not be done (live 2026-09-28)
    s = Session()
    game.send_zone_props(s, 10350, {"quests": {"active": {}, "done": []}})
    out = bytes(s.sent[-1].buf)
    recs = {r["id"]: r for r in (read_prop(out[2 + 23 * i:25 + 23 * i]) for i in range(struct.unpack_from("<H", out)[0]))}
    assert recs[10293]["shown"] == 1 and recs[10293]["state"] == game.PROP_ON
    from kuf2 import zone
    types = {p["SmartPropID"]: p["SmartPropTypeID"] for p in zone.for_spot(10350)["SmartPropData"]}
    assert all((r["state"] == game.PROP_ON) == game.staging_prop(game.prop_row(types[i]) or {}) for i, r in recs.items())
    assert game.staging_prop(game.prop_row(421)) and not game.staging_prop(game.prop_row(232))


class FieldSession(Session):
    def __init__(self, quests):
        super().__init__()
        self.data.update(spot=10352, account={"characters": [{"id": 1, "class": 0, "quests": quests}]})
        self.pending = []

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class NoSave:
    def save(self):
        pass


COCOON = 10219          # Mist Field zone 3, type 402 Spider Cocoon (1150201 "Operate Spider Cocoon" x2)


def cast(role, s, prop_id, uid=0):
    role.handlers[game.C2S_PROP_CAST](s, pkt(game.C2S_PROP_CAST, struct.pack("<H", uid) + obf.u32(prop_id)))
    return bytes(s.sent[-1].buf)


def test_a_cocoon_cast_activates_it_and_moves_the_quest():
    from kuf2 import quest
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150201": {"counts": [0] * 5}}, "done": []})
    out = cast(role, s, COCOON)
    assert s.sent[-1].proto == game.S2C_PROP_CAST and out == obf.u32(COCOON) + b"\0\0\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(COCOON)))
    done = next(w for w in s.sent if w.proto == game.S2C_PROP_CAST_DONE)
    b = bytes(done.buf)
    assert struct.unpack_from("<H", b)[0] == 0 and obf.dec_u32(b[2:6]) == COCOON and b[6:8] == b"\0\0"
    assert len(b) == 8 + 9 + 2 and struct.unpack_from("<i", b, 8 + 5)[0] == game.PROP_ON
    q = s.data["account"]["characters"][0]["quests"]["active"]["1150201"]
    assert q["counts"][0] == 1 and s.sent[-1].proto == quest.S2C_PROGRESS
    assert cast(role, s, COCOON)[4:6] == struct.pack("<H", game.PROP_REFUSED)     # on: not again until it returns
    [(delay, back)] = s.pending
    assert delay == 20.0                                                            # RechargeTime_SW of 402
    back()
    rec = read_prop(bytes(s.sent[-1].buf)[2:])
    assert s.sent[-1].proto == game.S2C_PROP_LIST and rec["id"] == COCOON and rec["state"] == game.PROP_OFF
    assert cast(role, s, COCOON)[4:6] == b"\0\0"


@pytest.mark.parametrize("prop_id, quests", [
    (COCOON, {"active": {}, "done": []}),                                   # 1150201 not held: hidden, no cast
    (10210, {"active": {}, "done": []}),                                    # barricade: shown, trigger only
    (10235, {"active": {}, "done": []}),                                    # road-block tree: not placed
    (99999, {"active": {}, "done": []}),                                    # not a prop of the zone
])
def test_prop_casts_are_refused(prop_id, quests):
    role = game.make(NoSave(), 0)
    s = FieldSession(quests)
    assert cast(role, s, prop_id)[4:6] == struct.pack("<H", game.PROP_REFUSED)
    assert "prop_casts" not in s.data


def test_a_cast_end_without_a_cast_is_refused_not_ignored():
    # without a 0x5097 the client's prop manager stays in state 3 for the rest of the room and ignores every later F
    # (planning/client/props_loot.md, 0x5096; one live case 2026-09-27 07:00:21): refused, nothing counted
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150201": {"counts": [0] * 5}}, "done": []})
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(COCOON)))
    assert [w.proto for w in s.sent] == [game.S2C_PROP_CAST_DONE]
    assert struct.unpack_from("<h", bytes(s.sent[0].buf), 6)[0] == 1
    assert s.data["account"]["characters"][0]["quests"]["active"]["1150201"]["counts"][0] == 0


def test_accepting_the_cocoon_quest_in_the_field_shows_its_cocoons():
    from kuf2 import quest
    s = FieldSession({"active": {"1150201": {"counts": [0] * 5}}, "done": []})
    s.data.update(battle_spot=10352, char=s.data["account"]["characters"][0])
    quest.field_props(s, 1150201)
    out = bytes(s.sent[-1].buf)
    n = struct.unpack_from("<H", out)[0]
    recs = [read_prop(out[2 + 23 * i:25 + 23 * i]) for i in range(n)]
    assert s.sent[-1].proto == game.S2C_PROP_LIST and n == 16 and all(r["shown"] for r in recs)


def test_a_prop_that_needs_an_item_is_refused_without_it():
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150203": {"counts": [0] * 5}}, "done": []})
    assert cast(role, s, 10012)[4:6] == struct.pack("<H", game.PROP_REFUSED)        # 403 black orb: 451000231
    s.data["account"]["characters"][0]["bag"] = [{"code": 451000231, "slot": 0, "count": 1}]
    assert cast(role, s, 10012)[4:6] == bytes(2)


def test_an_item_box_lists_its_item_hands_it_over_on_the_pick_and_comes_back():
    from kuf2 import zone
    box = next(p for p in zone.for_spot(10352)["SmartPropData"] if p["SmartPropTypeID"] == 433)
    bid = box["SmartPropID"]
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150312": {"counts": [0] * 5}}, "done": []})
    s.data["char"] = s.data["account"]["characters"][0]
    assert cast(role, s, bid)[4:6] == bytes(2)
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, bytes(2) + obf.u32(bid)))
    b = bytes(next(w for w in s.sent if w.proto == game.S2C_PROP_CAST_DONE).buf)
    assert b[8:13] == obf.u40(0) and struct.unpack_from("<i", b, 13)[0] == game.PROP_ON      # gold 0, looting
    assert b[17] == 1 and b[18:26] == obf.u16(1) + obf.u32(451000216) + obf.u16(0) and b[26:] == b"\0"
    assert "bag" not in s.data["char"]                                                       # not before the pick
    pick = obf.u32(451000216) + obf.u32(bid) + obf.u16(0) + obf.u16(1) + struct.pack("<H", 0)
    role.handlers[game.C2S_BOX_ITEM](s, pkt(game.C2S_BOX_ITEM, pick))
    assert bytes(s.sent[-1].buf) == obf.u32(bid) + bytes([1, 0, 0])
    assert [(i["code"], i["count"]) for i in s.data["char"]["bag"]] == [(451000216, 1)]    # GrantItem1_IB x1
    role.handlers[game.C2S_BOX_ITEM](s, pkt(game.C2S_BOX_ITEM, pick))                       # taken already
    assert bytes(s.sent[-1].buf)[5:] == struct.pack("<H", game.PROP_REFUSED)
    role.handlers[game.C2S_PROP_STATE](s, pkt(game.C2S_PROP_STATE, struct.pack("<IH", 2, 0) + obf.u32(bid)))
    assert bytes(s.sent[-1].buf) == bytes(2) + struct.pack("<I", 2) + obf.u32(bid)
    [(delay, back)] = s.pending
    assert delay == 10.0                                                                    # Regen_Time of 433
    assert game.box_loot(game.prop_row(402)) == [] and game.prop_back_after(game.prop_row(64)) is None


def test_an_item_box_left_open_comes_back_only_after_its_loot_window_closes():
    # AC3 item 14 (guest 2026-10-24, Mist Field box 10250, type 559, Regen_Time 10): cast done 13:45:49, the regen's
    # 0x50d1 at 13:45:59 while the loot window stayed open, its close (0x50a1 state 2) at 13:46:51 marked the box opened
    # again for good: "cast refused: already on" at 13:47:13. The box's time now counts from the window's close (ours:
    # the regen of a box still being looted is not shown by the original's data)
    from kuf2 import zone
    box = next(p for p in zone.for_spot(10352)["SmartPropData"] if p["SmartPropTypeID"] == 433)
    bid = box["SmartPropID"]
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150312": {"counts": [0] * 5}}, "done": []})
    s.data["char"] = s.data["account"]["characters"][0]
    assert cast(role, s, bid)[4:6] == bytes(2)
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, bytes(2) + obf.u32(bid)))
    assert s.pending == []                                                    # the window is open: no regen yet
    role.handlers[game.C2S_PROP_STATE](s, pkt(game.C2S_PROP_STATE, struct.pack("<IH", 2, 0) + obf.u32(bid)))
    role.handlers[game.C2S_PROP_STATE](s, pkt(game.C2S_PROP_STATE, struct.pack("<IH", 2, 0) + obf.u32(bid)))
    [(delay, back)] = s.pending                                               # one regen, however many closes
    assert delay == 10.0
    assert cast(role, s, bid)[4:6] == struct.pack("<H", game.PROP_REFUSED)    # opened until it is back
    back()
    assert cast(role, s, bid)[4:6] == bytes(2)


def test_a_cancelled_cast_frees_the_prop():
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150201": {"counts": [0] * 5}}, "done": []})
    assert cast(role, s, COCOON)[4:6] == b"\0\0"
    assert cast(role, s, COCOON)[4:6] == struct.pack("<H", game.PROP_REFUSED)       # being cast
    role.handlers[game.C2S_PROP_CANCEL](s, pkt(game.C2S_PROP_CANCEL, obf.u32(COCOON)))
    assert cast(role, s, COCOON)[4:6] == b"\0\0"


def test_hitting_an_attackable_prop_breaks_it_and_it_comes_back():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    # Mist Field's 10044 is type 432 (TYPE_ATTACK: HP_AT 50, HC_AT 10 -> 5 a hit, Regen_Time 30)
    hit = bytes(7) + struct.pack("<HH", 1, 0) + bytes([1]) + obf.u32(10044)       # no troop targets, one prop
    for k in range(9):
        role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))
    bar = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_PROP_HP and bar == struct.pack("<H", 1) + obf.u32(10044) + struct.pack("<ii", 5, 50)
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))
    assert s.sent[-1].proto == game.S2C_PROP_DELETE and bytes(s.sent[-1].buf) == struct.pack("<H", 1) + obf.u32(10044)
    sent = len(s.sent)
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))     # broken: no more bars
    assert all(w.proto != game.S2C_PROP_HP for w in s.sent[sent:])
    [(delay, mend)] = s.pending
    assert delay == 30.0
    mend()
    assert s.sent[-1].proto == game.S2C_PROP_REGEN
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 432) + obf.u32(10044) + bytes([obf.T2[2]])


def test_hit_report_props_and_whole_troop_targets_parse():
    from kuf2 import combat
    # 0x5053 layout: 15-byte header, u16 n targets (none), u16 k + k coded prop ids
    body = bytes(15) + struct.pack("<H", 0) + struct.pack("<H", 2) + obf.u32(10044) + obf.u32(10045)
    assert combat.parse_hit_props(body, 15) == (0, [], [10044, 10045])
    # an ability target with a non-zero flag byte has no unit list
    lst = struct.pack("<H", 2) + bytes([1]) + struct.pack("<H", 7) + bytes([0]) + struct.pack("<HH", 8, 1) + struct.pack("<H", 3 << 5)
    assert combat.target_list_len(lst, 0) == len(lst)
    assert combat.ability_targets(lst, 0) == [(7, [0]), (8, [3])]


def test_a_dead_hero_revives_at_the_camp_and_the_echoes_answer():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    role.handlers[game.C2S_REVIVE_CAMP](s, pkt(game.C2S_REVIVE_CAMP, b""))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1)                       # alive: quiet refusal
    s.data["battle"].troops[0]["hp"] = 0
    role.handlers[game.C2S_REVIVE_CAMP](s, pkt(game.C2S_REVIVE_CAMP, b""))
    protos = [w.proto for w in s.sent[-5:]]
    assert protos == [game.S2C_REVIVE_CAMP, game.S2C_TROOP_DOWN, game.S2C_TROOP_BACK, game.S2C_TROOP_HP,
                      combat.S2C_STATUS_ADD]                              # the revive's invincibility 33 (5 s)
    assert len(bytes(s.sent[-5].buf)) == 12 and bytes(s.sent[-4].buf) == bytes(5) + bytes([1]) + bytes(2)
    assert len(bytes(s.sent[-3].buf)) == 9
    assert struct.unpack_from("<I", bytes(s.sent[-1].buf), 10)[0] == 33
    assert s.data["battle"].troops[0]["hp"] == 1000
    cast = obf.u16(5) + struct.pack("<H", 0) + obf.u32(1101) + bytes(7)
    role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, cast))
    out = bytes(s.sent[-1].buf)
    assert len(out) == 17 and out[:2] == obf.u16(5) and out[2:6] == obf.u32(1101) and out[15:] == bytes(2)
    for req, rep, body in ((game.C2S_UNCHANT, game.S2C_UNCHANT, bytes(range(6))),
                           (game.C2S_MARK_TROOP, game.S2C_MARK_TROOP, bytes(range(9))),
                           (game.C2S_MARK_GROUND, game.S2C_MARK_GROUND, bytes(range(8)))):
        role.handlers[req](s, pkt(req, body))
        assert s.sent[-1].proto == rep and bytes(s.sent[-1].buf) == body
    role.handlers[game.C2S_PAUSE](s, pkt(game.C2S_PAUSE, bytes([1])))
    assert bytes(s.sent[-1].buf) == bytes([0, obf.T2[1], 0])


def test_loot_drops_on_the_ground_and_is_picked_up():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["char"] = s.data["account"]["characters"][0]
    s.data["char"].update(gold=0)
    s.data["battle"] = combat.Battle()
    game.drop_loot(s, [(350000010, 2)], 40)
    box = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_REWARD_BOX and box[0] == 2
    bag_id, gold_id = game.FIRST_DROP_ID, game.FIRST_DROP_ID + 1
    # item bag: at the hero (obool TRUE), owner MY_SLOT, gold 0, id, type 0, one item
    assert box[1] == 0 and box[9:11] == struct.pack("<H", game.MY_SLOT) and box[12:17] == obf.u40(0)
    assert struct.unpack_from("<iB", box, 17) == (bag_id, 0) and box[22] == 1
    assert box[23:31] == obf.u16(2) + obf.u32(350000010) + obf.u16(0)
    gold = box[31:]
    assert gold[11:16] == obf.u40(40) and struct.unpack_from("<iB", gold, 16) == (gold_id, game.TYPE_GOLD) and gold[21] == 0
    pick = obf.u16(2) + struct.pack("<I", bag_id) + obf.u32(350000010) + obf.u16(0)
    role.handlers[game.C2S_DROP_PICK](s, pkt(game.C2S_DROP_PICK, pick))
    out = bytes(s.sent[-1].buf)
    assert len(out) == 14 and out[:2] == bytes(2) and s.data["drops"] == {}
    # the client finds the picked item by code and the key it kept at drop entry +8 = the item record's first field
    assert obf.dec_u16(out[6:8]) == obf.dec_u16(box[23:25]) and obf.dec_u32(out[10:14]) == 350000010
    assert [(i["code"], i["count"]) for i in s.data["char"]["bag"]] == [(350000010, 2)]
    role.handlers[game.C2S_DROP_PICK](s, pkt(game.C2S_DROP_PICK, pick))                     # gone
    assert len(bytes(s.sent[-1].buf)) == 14 and bytes(s.sent[-1].buf)[:2] == struct.pack("<H", game.DROP_GONE)
    role.handlers[game.C2S_GOLD_PICK](s, pkt(game.C2S_GOLD_PICK, struct.pack("<Hi", 0, gold_id)))
    assert bytes(s.sent[-1].buf) == struct.pack("<HHi", 0, 0, gold_id) and s.data["char"]["gold"] == 40
    assert game.roll_gold(3210) == 500


def test_the_hero_falling_opens_the_death_window_once():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 2)
    s.data["battle"].add_np(1, 1072, 19, c=combat.np_combatant(2))  # the test enemy (attack 1): 1 a hit
    # a 0x5053 hit report by troop 1 on troop 0 (the hero), one unit record, no props
    target = bytes([obf.T2[0], obf.T1[0]]) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0])
    hit = hit_header(1) + struct.pack("<H", 1) + target + struct.pack("<H", 0)
    for _ in range(3):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    windows = [w for w in s.sent if w.proto == game.S2C_DEATH_WINDOW]
    assert len(windows) == 1 and bytes(windows[0].buf) == bytes(1)


def test_the_camp_barricade_stands_and_never_opens():
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    assert game.prop_shown(64, {"active": {}, "done": []}) and not game.prop_shown(592, {"active": {}, "done": []})
    assert cast(role, s, 10210)[4:6] == struct.pack("<H", game.PROP_REFUSED)       # F answers, nothing opens


def test_the_first_mission_is_won_by_its_hostile_troops_and_leads_out_of_the_camp():
    from kuf2 import combat, quest
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1150301": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10358
    c = s.data["account"]["characters"][0]
    c.update(level=5, spot=10352, pos=[329747, 0, 175407], mission={"spot": 10358, "quest": 1150301, "back": 10350})
    s.data["char"] = c
    assert game.is_mission(10358) and not game.is_mission(10352) and game.start_pos(s) == game.mission_start(10358)
    s.data["battle"] = combat.Battle()
    game.spawn_zone_troops(s)
    troops = s.data["zone_troops"]
    enemies = [u for u, t in troops.items() if game.hostile(t)]
    # team 1's forces 20000-22000 (11 troops); its force 25000 are 18 staging troops worth no exp, left standing
    assert len(enemies) == 11 and all(troops[u]["TeamNum"] == 1 for u in enemies)
    for u in enemies[:-1]:
        game.mission_troop_down(s, NoSave(), u)
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)       # one enemy still stands
    game.mission_troop_down(s, NoSave(), enemies[-1])
    run_pending(s)
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)       # the finale is on the street (WIN =
    from kuf2 import director                                                   # "table"): its hold-out, the window
    street = director.bound(10358, 10007)
    s.state = NoSave()
    director.on_position(s, street["BoundCenterX"], street["BoundCenterZ"])
    run_pending(s)
    # no result window (decision B2: Grey Fog has no reward or grade row; the tape goes from the finale to the field):
    # the clear counts and the room is left at once, unasked
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)
    assert c["quests"]["active"]["1150301"]["counts"][0] == 1                   # MissionLevelClear Any
    assert role.handlers[game.C2S_MISSION_LEAVE]                                # (the button's request, elsewhere)
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == game.S2C_MISSION_LEAVE and len(out) == 16 and out[:4] == bytes([0, 0, 0, 2])
    assert out[4:8] == obf.u32(10350) and c["spot"] == 10350 and "mission" not in c
    assert c["pos"] == [278357, 0, 190736]                                        # 10350's first start point


def test_an_ability_commit_is_echoed_with_its_caster():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["casts"] = {7: struct.pack("<H", 3)}
    req = bytes([9]) + struct.pack("<HI", 0x1234, 1101) + bytes(range(7)) + struct.pack("<H", 7) + obf.u16(5) + bytes([1]) + struct.pack("<H", 1) + obf.u16(5)
    role.handlers[combat.C2S_COMMIT](s, pkt(combat.C2S_COMMIT, req))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == combat.S2C_COMMIT and len(out) == 17 + len(req) - 0x12
    assert struct.unpack_from("<H", out, 0)[0] == 5 and out[2:9] == bytes(range(7)) and struct.unpack_from("<H", out, 9)[0] == 7
    assert struct.unpack_from("<H", out, 0xc)[0] == 3 and out[0xf:0x11] == struct.pack("<H", 0x1234) and out[17:] == req[0x12:]



def test_kill_exp_follows_the_troop_factor_and_the_level_difference():
    c = {"level": 1}
    assert game.kill_exp(c, 154030) == 3                  # Mist Field spider: level 1, EXP_FACTOR 3, same level
    assert game.kill_exp(c, 154010) == 0                  # EXP_FACTOR 0: nothing
    c["level"] = 9
    assert (game.kill_exp(c, 155230), game.kill_exp(c, 155210)) == (3, 5)   # Sawtooth, level 8: 4 and 6 x 0.9
    c["level"] = 5
    assert game.kill_exp(c, 155230) == 4                  # the troop 3 levels above: x1.15 = 4.6


def test_a_field_kill_gives_hero_exp_and_can_level_up():
    # Aldric's live state (2026-09-27): level 1 with 79 / 80 exp after 1150201 / 1150202, and 1150205 needs level 2
    from kuf2 import combat, world
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=1, exp=79)
    s.data["char"] = c
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, game.hero_max_hp(s), c=game.hero_combatant(c))
    game.spawn_zone_troops(s)
    uid = next(u for u, t in s.data["zone_troops"].items() if t["TroopTableID"] == 154030)   # a Mist Forest Tarantula
    hit_until_down(role, s, uid, hit_header(0))                             # the hero's hits (31 hp, defence 234)
    assert (c["level"], c["exp"]) == (2, 2)                                  # +3: EXP_FACTOR 3 at the same level
    protos = [w.proto for w in s.sent]
    assert world.S2C_EXP in protos and world.S2C_HERO_BLOCK in protos



def test_the_battle_kit_follows_the_skill_books_parent_links():
    from kuf2 import skills
    glen = skills.battle_abilities({"class": 0, "level": 1})
    assert {63, 64, 65, 66, 71, 72, 78, 79, 80, 81} <= set(glen)             # R reload stances and their slashes (15)
    assert {2, 14, 85, 91, 164, 77, 62} <= set(glen)                        # dash, evade, counter, execution, attacks
    assert not {44, 99, 56, 57, 83} & set(glen)                             # level 8 / 4, tree skill 8 not learned, 82 at 2
    assert {83, 99} <= set(skills.battle_abilities({"class": 0, "level": 4}))
    assert not {7000, 7004} & set(glen)                                     # Glen's common passives: TP tree skills
    assert {7004, 7005} <= set(skills.battle_abilities({"class": 5, "level": 1}))   # Helena's: 0-TP links of 1272
    for cls in range(6):
        c = {"class": cls, "level": 1}
        assert set(skills.hero_skills(c)) <= set(skills.battle_abilities(c)) and len(skills.battle_abilities(c)) < 256


def test_room_start_pools_level_and_hero_flags():
    c = {"id": 1, "class": 0, "level": 30, "look": bytes(56).hex()}
    p = game.player_struct(c, 10352)
    # SP: the hero's own pool, full (%ApSp SP_MAX), not Default_SP 100 / SP_INIT 150 (tests/test_hero_pools.py)
    assert struct.unpack_from("<i", p, 0x01)[0] == 200 and struct.unpack_from("<i", p, 0xb5)[0] == 200
    assert (p[0x13], p[0x94], p[0xb4]) == (10, 10, 0)             # Gunslinger ammo 10 / 10; the scale left at default
    assert struct.unpack_from("<i", game.player_struct(c), 0x01)[0] == 200
    s = FieldSession({"active": {}, "done": []})
    s.data["account"]["characters"][0].update(level=30)
    game.send_enter_cell(s)
    st = bytes(s.sent[-1].buf)[3:3 + 0x3d]
    assert st[0x06] == st[0x13] == 30 and st[0x3c] == game.HERO_FLAGS == 0x1c


def test_zone_troops_carry_their_ai_data_and_respawn_enabled():
    from kuf2 import combat, zone
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    zt = {"TroopID": 20001, "TroopTableID": 154340, "PosX": 1.0, "PosZ": 2.0, "TeamNum": 1, "FirstAttack": 1,
          "SharingSight": 1, "HoldMovement": 0, "CombackDist": 3000, "CombatDist": 3000, "WanderingDist": 500,
          "TargetTroopID": -1, "FallBackAreaID": -1, "DefaultPath1ID": -1, "DefaultPath2ID": -1, "UnitNum": 0}
    assert game.spawn_zone_troop(s, zt)
    enter, ai = s.sent[-2], s.sent[-1]
    b = bytes(enter.buf)[3:]
    assert b[0x3c] == game.TROOP_ALIVE | game.TROOP_FIRST_ATTACK | game.TROOP_SIGHT
    assert b[0x13] == int(zone.np_troop(154340)["LEVEL_CURRENT"])
    desc = b[0x3e:0x3e + 22]                                       # after the NP obool; the gnoll's own program,
    assert struct.unpack("<HHIHHiHI", desc) == (3000, 0xffff, 0xffffffff, 3000, 0xffff, 60000, 500, 0xffffffff)
    assert struct.unpack("<HfHHHfHfi", bytes(ai.buf)) == (0xffff, 3000.0, 0xffff, 20001, 0xffff, 500.0, 0xffff,
                                                           3000.0, 60000)   # nptrooptable TROOPAI 60000 (field map)
    s.sent.clear()
    game.respawn_zone_troop(s, 20001, zt)
    assert [w.proto for w in s.sent] == [game.S2C_TROOP_LEAVE, game.S2C_ENTER_CELL_TROOP, game.S2C_SET_SPAWN_AI,
                                         game.S2C_SCRIPT_ACTION]


def spawn_programs(s):
    """{uid: (descriptor AI, 0x5083 AI)} of the NP troops sent: the 22-byte descriptor's +0xc after each 0x50cb
    entry's NP obool, the last 0x5083's +0x16."""
    out = {}
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_ENTER_CELL_TROOP and len(b) > 3 + 0x3e + 22:
            uid = struct.unpack_from("<H", b, 3 + 0x11)[0]
            out[uid] = (struct.unpack_from("<i", b, 3 + 0x3e + 0xc)[0], None)
        elif w.proto == game.S2C_SET_SPAWN_AI:
            f = struct.unpack("<HfHHHfHfi", b)
            out[f[3]] = (out.get(f[3], (None,))[0], f[8])
    return out


def test_a_zone_troop_runs_its_own_table_program_not_the_generic_40000():
    # An AI id of -1 in the NP descriptor (0x140cf8645) or in 0x5083 (0x140d02f60) gives the troop its TAIBranch row's
    # +0x20 column (TROOPAI_NPINIT, 40000 on every troop branch), never nptrooptable TROOPAI: the client decodes
    # TROOPAI (row +0x60, parser 0x1418bdf98) only in BuildSpawnTroop's Invasion case (0x140cf98e2), so the table's
    # program reaches a server-spawned troop only when the server sends it (planning/controls/ENEMY-AI.md 2026-09-30)
    from kuf2 import zone
    assert game.table_ai(134060) == 41000                           # Grey Rock's archers: aggressive + ally support
    assert game.table_ai(154030) == 50000                            # Mist Field's spiders: non-aggressive
    assert game.table_ai(135110) == 0                                # New Hampton's boss Vert: TAI_0
    assert game.table_ai(100) == -1                                  # '-': the parser's default -1, the branch's
    assert game.table_ai(999999999) == -1                            # NPINIT; no row: the same
    s = mission_room(10234)
    sent = spawn_programs(s)
    for uid, t in s.data["zone_troops"].items():
        want = int(zone.np_troop(game.difficulty_troop(t["TroopTableID"], 0))["TROOPAI"])
        assert sent[uid] == (want, want), uid
    assert {sent[u][1] for u in s.data["zone_troops"]} == {41000}   # the start's troops; -1 gave them all 40000
    # the handed archers keep the stance the client gives the player's own troops: the hand (Troop::SetTroopAIType
    # Hero Support) comes after their program, and nothing sets a program after it
    order = [(w.proto, bytes(w.buf)) for w in s.sent]
    ai_at = max(i for i, (p, b) in enumerate(order) if p == game.S2C_SET_SPAWN_AI and struct.unpack_from("<H", b, 8)[0]
                == 10073)
    hand_at = next(i for i, (p, b) in enumerate(order) if p == game.S2C_SCRIPT_ACTION and
                   struct.unpack_from("<3I", b)[0::2] == (game.ACT_CHANGE_FORCE, 10073))
    assert ai_at < hand_at and sent[10073] == (41000, 41000)


def test_the_hero_draws_on_engagement_sheathes_in_peace_and_holds_his_guard():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, obf.u16(20001) + bytes([1]) + obf.u16(0)))
    assert bytes(s.sent[-1].buf) == bytes([1, 0, 0, T2[1]]) and s.data["battle"].troops[0]["combat"]
    s.data["hero_active_at"] -= combat.PEACE_S                   # ten quiet seconds, but the engagement is open
    for _, fn in list(s.pending):
        fn()
    assert s.data["battle"].troops[0]["combat"]
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, obf.u16(20001) + bytes([0]) + obf.u16(0)))
    s.data["hero_active_at"] -= combat.PEACE_S                   # it closed: the quiet spell sheathes him (B1)
    for _, fn in list(s.pending):
        fn()
    assert bytes(s.sent[-1].buf) == bytes([1, 0, 0, T2[0]]) and not s.data["battle"].troops[0]["combat"]
    use = obf.u32(62) + bytes(7) + bytes(3) + obf.u16(0) + struct.pack("<H", 0) + bytes(7) + obf.u16(0) + bytes([1])
    role.handlers[combat.C2S_USE_ABILITY](s, pkt(combat.C2S_USE_ABILITY, use + struct.pack("<H", 0)))
    serial = s.data["cast_serial"]
    execute = bytes(7) + struct.pack("<H", serial) + struct.pack("<H", 0) + bytes([0])
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, execute))
    add = next(w for w in s.sent if w.proto == combat.S2C_STATUS_ADD)
    assert bytes(add.buf) == struct.pack("<H", 1) + bytes([0]) + struct.pack("<HH", combat.STATUS_HOLD_S, 0) + \
        struct.pack("<HBIH", 0, 1, 341, 0)                        # guard: 341 STANCE_DEFENSE_GUARD on the hero
    role.handlers[game.C2S_UNCHANT](s, pkt(game.C2S_UNCHANT, obf.u32(62) + struct.pack("<H", 0)))
    end = s.sent[-1]
    assert end.proto == combat.S2C_STATUS_END and bytes(end.buf) == struct.pack("<H", 1) + bytes([0]) + \
        struct.pack("<HBIB", 0, 1, 341, 0)



def test_battle_numbers_follow_the_hero_and_hits_show_damage():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=1, exp=79)
    s.data["char"] = c
    stats = game.hero_stat_values(c)
    assert stats[0] == 402 and stats[14] == 800                    # HP_MAX at level 1 (the Info window), move speed
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, game.hero_max_hp(s), c=game.hero_combatant(c))
    game.spawn_zone_troops(s)
    uid = next(u for u, t in s.data["zone_troops"].items() if t["TroopTableID"] == 154030)
    s.sent.clear()
    hit_until_down(role, s, uid, hit_header(0))
    protos = [w.proto for w in s.sent]
    assert combat.S2C_DAMAGE_NUMBERS in protos and game.S2C_KILL_FEED in protos and game.S2C_COMBAT_BONUS in protos
    assert game.S2C_LEVEL_UP in protos and combat.S2C_STATS in protos and c["level"] == 2
    lv = next(w for w in s.sent if w.proto == game.S2C_LEVEL_UP)
    assert bytes(lv.buf) == struct.pack("<H", 0) + bytes([1, 2])
    assert s.data["battle"].troops[0]["max"] == game.hero_stat_values(c)[0] > 402



def test_sp_and_ammo_are_spent_reloaded_and_regenerated():
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=30)
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    s.data["pools"] = game.pools_for(c, 10352)
    assert (s.data["pools"]["sp"], s.data["pools"]["ammo"]) == (200, 10)
    use = lambda aid: role.handlers[combat.C2S_USE_ABILITY](s, pkt(combat.C2S_USE_ABILITY, obf.u32(aid) + bytes(12)
                                                             + struct.pack("<H", 0) + bytes(7) + obf.u16(0) + bytes(3)))
    use(5098)                                                      # first aid: 100 SP
    stats = [w for w in s.sent if w.proto == combat.S2C_STATS]
    assert s.data["pools"]["sp"] == 100 and bytes(stats[-1].buf) == bytes([1]) + struct.pack("<IbH", 100, 6, 0)
    use(15)                                                        # aimed shot: 2 bullets
    assert s.data["pools"]["ammo"] == 8
    use(63)                                                        # upper reload: +10, capped at 10
    last = [w for w in s.sent if w.proto == combat.S2C_STATS][-1]
    assert s.data["pools"]["ammo"] == 10 and bytes(last.buf) == bytes([1]) + struct.pack("<IbH", 10, combat.STAT_AMMO, 0)
    assert combat.gain_sp(s, 9) and s.data["pools"]["sp"] == 109



def test_the_hero_regenerates_and_quest_drops_are_announced():
    from kuf2 import combat
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=30)
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000)
    s.data["battle"].troops[0]["hp"] = 900
    s.data["pools"] = dict(game.pools_for(c, 10352), sp=200, hp_rec=3)
    combat.start_regen(s)
    delay, tick = s.pending[-1]
    tick()
    assert s.data["battle"].troops[0]["hp"] == 915 and s.sent[-2].proto == game.S2C_TROOP_HP   # out of combat: 5 x 3
    assert s.sent[-1].proto == combat.S2C_HERO_DAMAGE and struct.unpack_from("<i", bytes(s.sent[-1].buf))[0] == -15
    game.drop_loot(s, [(450000003, 1)], 0)                         # a quest item
    alarm = s.sent[-1]
    assert alarm.proto == game.S2C_QUEST_ITEM_ALARM
    assert bytes(alarm.buf) == obf.u32(game.FIRST_DROP_ID) + bytes([1]) + obf.u32(450000003) + struct.pack("<H", 1)



def test_a_mission_holding_its_enemies_brings_them_in_wave_by_wave():
    from kuf2 import combat
    s = FieldSession({"active": {"1150406": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10233
    c = s.data["account"]["characters"][0]
    c.update(level=5, spot=10350, pos=[0, 0, 0])
    s.data["char"] = c
    s.data["battle"] = combat.Battle()
    s.state = NoSave()
    game.spawn_zone_troops(s)
    waves = game.mission_waves(10233)
    assert [len(w) for w in waves][:1] == [13] and len(s.data["waves"]) == len(waves) - 1   # the first came at once
    from kuf2 import director
    for _ in range(3 * len(waves)):
        alive = [u for u, z in s.data["zone_troops"].items() if game.hostile(z) and u not in s.data.get("down", set())]
        assert not s.data.get("mission_won")
        if not alive:                                   # the director's table holds the camp attack for its steps;
            held = [w for w in s.data["waves"] if w[0]["ForceNum"] in director.held(10233)]
            if not held:                                # all in and down: its own win comes with Golden Hammer's
                break                                   # cannons (WIN = "table"), timers run below
            director.run(s, ("wake", held[0][0]["ForceNum"]))
            continue
        for u in alive:
            game.mission_troop_down(s, NoSave(), u)
        for pid in list(director._state(s).get("prompts", {})):   # the keys its lessons ask (the night attack's Z)
            director.on_prompt(s, pid)
        if s.data.get("director", {}).get("ending"):
            break
    run_pending(s)                                                              # the ending lines, then the window
    assert s.data.get("mission_won") and s.data["char"]["quests"]["active"]["1150406"]["counts"][0] == 1



def acts(s, act):
    return [list(struct.unpack_from("<%dI" % (len(w.buf) // 4), bytes(w.buf))) for w in s.sent
            if w.proto == game.S2C_SCRIPT_ACTION and struct.unpack_from("<I", bytes(w.buf))[0] == act]


def test_grey_fog_shows_its_mission_panel_and_points_at_the_enemy():
    from kuf2 import combat
    s = FieldSession({"active": {"1150301": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10358
    c = s.data["account"]["characters"][0]
    c.update(level=5, spot=10352, pos=[0, 0, 0])
    s.data["char"] = c
    s.data["battle"] = combat.Battle()
    game.spawn_zone_troops(s)
    # missiontext/eng/1_mistfield: 7000 "Burning Grey Fog Street", 7010 "Winning Conditions" / 7020 "Eliminate the
    # Encablossians", 7030 "Losing Conditions" / 7040 "Let Hero and all ally Troops die"
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, 0xff, 7000]]
    assert acts(s, game.ACT_SITUATION_GROUP) == [[game.ACT_SITUATION_GROUP, 0xff, 7010],
                                                 [game.ACT_SITUATION_GROUP, 0xff, 7030]]
    assert acts(s, game.ACT_SITUATION_LINE) == [[game.ACT_SITUATION_LINE, 0xff, 7010, 7020],
                                                [game.ACT_SITUATION_LINE, 0xff, 7030, 7040]]
    point = acts(s, game.ACT_DIRECTION_TO_TROOP)                   # the enemies stand 25 000+ units from the start
    assert len(point) == 1 and game.hostile(s.data["zone_troops"][point[0][1]]) and point[0][2] == game.POINT_S
    # beside an enemy, a kill points nowhere; from far away it points at the nearest one left
    target = s.data["zone_troops"][point[0][1]]
    s.data["hero_pos"] = (round(target["PosX"]), 0, round(target["PosZ"]))
    s.sent.clear()
    game.mission_troop_down(s, NoSave(), next(u for u, z in s.data["zone_troops"].items()
                                              if game.hostile(z) and u != point[0][1]))
    assert not acts(s, game.ACT_DIRECTION_TO_TROOP)
    s.data["hero_pos"] = game.mission_start(10358)
    game.mission_troop_down(s, NoSave(), point[0][1])
    again = acts(s, game.ACT_DIRECTION_TO_TROOP)
    assert len(again) == 1 and again[0][1] not in s.data["down"]


def test_a_map_shared_by_missions_gives_each_its_own_block():
    assert game.mission_text(10304)[0] == 600                      # Skywatch, not 100 "Reclaim the Skywatch village"
    assert game.mission_text(10319)[0] == 700                      # Claws Brotherhood Station on the same map
    assert game.mission_text(10234) == (100, ((110, (120, 121, 122, 123)), (200, (210,))))    # titled "Greyrock
                                                   # Fortress" (row 100 was dropped by the table reader until 2026-09-29)
    assert game.mission_text(10353) is None                        # Encablossian Attack: no block of its own


def test_the_hero_position_comes_from_the_troop_sync():
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    # captured 2026-09-27 20:17:11 in Glen's camp (10352), the hero walking toward Grey Fog Street
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC,
                                              bytes.fromhex("0100818b0000b8017829240a4210bcbc0a2924788100")))
    x, y, z = s.data["hero_pos"]
    assert abs(x - 309751) < 2 and abs(z - 182861) < 2 and s.sent == []
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, bytes.fromhex("0000")))      # nothing moved
    assert s.data["hero_pos"][0] == x



def test_a_mission_boss_gets_its_vitality_bar_until_it_falls():
    from kuf2 import combat
    s = FieldSession({"active": {"1150601": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10234                                          # Greyrock Fortress: the Mountain Troll 134080
    c = s.data["account"]["characters"][0]
    c.update(level=6, spot=10350, pos=[0, 0, 0])
    s.data["char"] = c
    s.data["battle"] = combat.Battle()
    game.spawn_zone_troops(s)
    troll = 20082
    for _ in range(60):                                             # wave after wave until the troll stands
        if troll in s.data["zone_troops"]:
            break
        alive = [u for u, z in s.data["zone_troops"].items() if game.hostile(z) and u not in s.data.get("down", set())]
        for u in alive:
            game.mission_troop_down(s, NoSave(), u)
    assert acts(s, game.ACT_BOSS_STATUS) == [[game.ACT_BOSS_STATUS, troll, 1]]
    game.mission_troop_down(s, NoSave(), troll)
    assert acts(s, game.ACT_BOSS_STATUS)[-1] == [game.ACT_BOSS_STATUS, troll, 0]



def test_a_timed_status_ends_after_its_duration_and_a_recast_restarts_it():
    s = FieldSession({"active": {}, "done": []})
    combat.expire_status(s, 0, 7002, 5)
    first = s.pending[-1]
    combat.expire_status(s, 0, 7002, 5)                             # cast again before it ran out
    second = s.pending[-1]
    assert first[0] == second[0] == 5
    first[1]()
    assert not [w for w in s.sent if w.proto == combat.S2C_STATUS_END]   # the old clock removes nothing
    second[1]()
    end = [w for w in s.sent if w.proto == combat.S2C_STATUS_END]
    from kuf2.packet import Writer
    want = Writer(combat.S2C_STATUS_END).u16(1).obool(True).u16(0).u8(1).u32(7002).u8(0)
    assert len(end) == 1 and bytes(end[0].buf) == bytes(want.buf)


def test_an_area_status_event_puts_its_status_on_the_troops_it_lists():
    # C2S 0x5075 (StatusEffectEventManager::Request 0x140c9f350, builder 0x1404fbda0; planning/client/combat.md gap 3):
    # u8 level, u16 event id, u32 status; u16 k x u16 (the event's id list, 0x1404fde50); u16 n x (u8 ratio x 255, 0 =
    # a unit list follows; u16 uid; [u16 m x u16 unit << 5 | code]) (0x1408201e0). Answered by the status engine: one
    # 0x5074 with the listed troops, the status's Duration, the event id
    from kuf2.packet import Writer
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    st = status.DEMORALIZE
    body = bytes([1]) + struct.pack("<HI", 7, st) + struct.pack("<HH", 1, 99) + struct.pack("<H", 2) \
        + bytes([255]) + struct.pack("<H", 10001) + bytes([0]) + struct.pack("<HHHH", 10002, 2, 3, (1 << 5) | 3)
    role.handlers[0x5075](s, pkt(0x5075, body))
    duration = status.num(status.improvement(st, 1)["Duration"])
    want = Writer(combat.S2C_STATUS_ADD).u16(2).obool(True).u16(duration).u16(10001).obool(True).u16(duration) \
        .u16(10002).u16(status.NO_CASTER).u8(1).u32(st).u16(7)
    assert [bytes(w.buf) for w in s.sent] == [bytes(want.buf)]
    assert st in status.holding(s, 10001) and st in status.holding(s, 10002)
    s.sent.clear()
    role.handlers[0x5075](s, pkt(0x5075, body[:-3]))                  # cut short: nothing, no raise
    assert s.sent == []


def test_a_status_removal_request_ends_the_status_and_is_answered():
    # C2S 0x5077 (ClientStatusEffectRemover 0x140869200 / 0x1407ba3b0, builder 0x1404fc5e0; planning/client/combat.md
    # gap 6): u8 level, u32 status, u8 reason; u16 n x (T2[whole + 2 * previous byte], u16 uid; when not whole u16 m x
    # u16 unit, 0x1404fedd0) (0x14081ff90). 0x5078 (0x140d1b3b0) takes the same records (obool) and the 6 bytes
    from kuf2.packet import Writer
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    st = status.DEMORALIZE
    status.apply(s, [10001, 10002], st, 1)
    s.sent.clear()
    whole = T2[(1 + 2 * 0x5a) & 0xff]
    part = T2[(0 + 2 * whole) & 0xff]
    body = bytes([1]) + struct.pack("<I", st) + bytes([5]) + struct.pack("<H", 2) + bytes([whole]) \
        + struct.pack("<H", 10001) + bytes([part]) + struct.pack("<HHH", 10002, 1, 3)
    role.handlers[0x5077](s, pkt(0x5077, body))
    want = Writer(combat.S2C_STATUS_END).u16(2).obool(True).u16(10001).obool(False).u16(10002).u16(1).u16(3) \
        .u8(1).u32(st).u8(5)
    assert [bytes(w.buf) for w in s.sent] == [bytes(want.buf)]
    assert st not in status.holding(s, 10001) and st in status.holding(s, 10002)   # one unit of 10002 only
    run_pending(s)                                    # the clocks: 10001's is stale, 10002's ends the rest of it
    assert [struct.unpack_from("<H", bytes(w.buf), 3)[0] for w in s.sent[1:] if w.proto == combat.S2C_STATUS_END] \
        == [10002]
    s.sent.clear()
    role.handlers[0x5077](s, pkt(0x5077, body[:-2]))                  # cut short: nothing, no raise
    assert s.sent == []



def test_respawn_follows_the_zone_spawn_fields():
    s = FieldSession({"active": {}, "done": []})
    spread = {game.respawn_delay(s, 1, {"RespawnTime": 35, "RespawnNoiseTime": 5, "RespawnLoopNum": -1})
              for _ in range(50)}
    assert all(30 <= d <= 40 for d in spread) and len(spread) > 1          # 35 +- 5, not one fixed clock
    assert game.respawn_delay(s, 2, {"RespawnTime": 10, "RespawnNoiseTime": 0, "RespawnLoopNum": -1}) == 10
    assert game.respawn_delay(s, 3, {"RespawnTime": 10, "UseSpawnSystem": 0}) is None
    assert game.respawn_delay(s, 4, {"RespawnTime": 10, "RespawnLoopNum": 0}) is None
    twice = {"RespawnTime": 10, "RespawnLoopNum": 2}
    assert [game.respawn_delay(s, 5, twice) for _ in range(3)] == [10, 10, None]   # at most RespawnLoopNum times
    assert game.respawn_delay(s, 6, {"RespawnTime": 0}) == 1



def test_the_dash_adds_its_status_when_the_passive_is_held():
    # abilitytypeinfo %Function: ability 2 CHECKSKILL_ADD_STATUSEFFECT_NODMG 7004 Lv n -> status 7000 Lv n
    got = combat.checkskill_statuses(2, {7004: 2})
    assert [(st, lv) for st, lv, _ in got] == [(7000, 2)]
    assert got[0][2] == combat.status_duration(7000, 2)
    assert combat.checkskill_statuses(2, {}) == [] and combat.checkskill_statuses(1, {7004: 2}) == []



def test_the_reloads_step_up_the_fast_reload_chain():
    # statuseffectinfo %StatusEffectChain 1 (Renewal True): 57 -> 58 -> 59, 30 s each; reload 63 is
    # STATUSEFFECT_CHAIN_NODAMAGE on chain 1
    s = FieldSession({"active": {}, "done": []})
    ends = lambda: [struct.unpack_from("<I", bytes(w.buf), 6)[0] for w in s.sent if w.proto == combat.S2C_STATUS_END]
    assert combat.chain_statuses(s, 63, now=0) == [(57, 1, 30)]
    assert combat.chain_statuses(s, 66, now=10) == [(58, 1, 30)] and ends() == [57]     # 57 makes way for 58
    assert combat.chain_statuses(s, 71, now=20) == [(59, 1, 30)] and ends() == [57, 58]
    assert combat.chain_statuses(s, 63, now=30) == [(59, 1, 30)] and ends() == [57, 58]  # the top renews itself
    assert combat.chain_statuses(s, 63, now=100) == [(57, 1, 30)]                        # ran out: from the first
    assert combat.chain_statuses(s, 2, now=100) == []                                     # no chain on the dash



def test_room_stats_follow_a_gear_change():
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=30)
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 500)
    s.data["battle"].troops[0]["hp"] = 400
    game.room_stats(s, c)
    push = s.sent[-1]
    assert push.proto == combat.S2C_STATS and push.buf[0] == len(game.hero_stat_values(c))
    t = s.data["battle"].troops[0]
    assert t["max"] == game.hero_stat_values(c)[0] and t["hp"] == 400 + (t["max"] - 500)   # the new max, hp raised
    # SP / ammo / FP as the live pools (SP_INIT 150 had left the client at 150 of a full 200 after an equip)
    s.data["pools"] = {"sp": 200, "ammo": 7, "fp": 400}
    game.room_stats(s, c)
    assert stat_sent(s, combat.STAT_SP)[-1] == 200 and stat_sent(s, combat.STAT_AMMO)[-1] == 7
    assert stat_sent(s, combat.STAT_FP)[-1] == 400
    push = s.sent[-1]
    # max HP (stat 0) as the client reads it: a plain LE u32 (was 1,895 << 16 live, the low-HP blood screen)
    b = bytes(push.buf)
    hp0 = next(struct.unpack_from("<I", b, 1 + 7 * i)[0] for i in range(b[0]) if b[5 + 7 * i] == 0)
    assert hp0 == t["max"]



def test_worn_set_pieces_add_their_set_bonus():
    from kuf2 import items, hero
    three = [103000100, 103000900, 153000100]                      # set 11011: weapon, off-hand, upper body
    assert items.set_traits(three[:2]) == []                        # tier 1 needs 3 pieces
    assert items.set_traits(three) == [("GIANT_ATTACK_RATE", 100.0, False), ("HP_MAX", 15.0, True)]   # "15%.": 15 %
    assert items.set_traits([]) == []
    base = hero.stats(0, 30, three[:2])["HP_MAX"]
    top = sum(v for n, v, _ in items.traits(three[2]) if n == "HP_MAX")
    assert abs(hero.stats(0, 30, three)["HP_MAX"] - (base + top) * 1.15) < 1e-6



def test_the_lake_bled_prop_summons_redin_who_drops_the_diary():
    # 1140325: PropActivate 246 (prop 10136 at Lake Bled 10202), NPNameKill 8019 (Redin, np troop 152620, in no zone),
    # ItemGain 450001251 (item_drop_quest: 152620 drops it at 100 %)
    from kuf2 import quest
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1140325": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10202
    s.data["battle"] = combat.Battle()
    s.data["account"]["characters"][0].update(level=13, spot=10202)
    assert cast(role, s, 10136)[4:6] == b"\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(10136)))
    q = s.data["account"]["characters"][0]["quests"]["active"]["1140325"]
    redin = [u for u, t in s.data["zone_troops"].items() if t["TroopTableID"] == 152620]
    assert q["counts"][0] == 1 and len(redin) == 1
    assert s.data["zone_troops"][redin[0]]["Prop"] == 10136          # the table's column called him, not the quest
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(10136)))
    assert len([t for t in s.data["zone_troops"].values() if t["TroopTableID"] == 152620]) == 1   # not twice
    assert "8019" in quest.kill_names(152620) and quest.name_troops(8019) == ["152620"]


def test_props_call_the_ambush_their_table_row_names_when_the_cast_completes():
    # smartproptable ActiveSpawnNPTroop_ID / SpawnNP_Rate / SpawnNP_Range, server-only columns (planning/client/
    # props_loot.md gap 2): quest 1160403's switches in 10351, types 435 / 436 / 437 -> 155280 / 155290 / 155270 at
    # 100 %, range 1; the troop comes on the cast's completion (0x5096), not its start (0x5094)
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1160403": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10351
    called = lambda tid: [(u, t) for u, t in s.data.get("zone_troops", {}).items() if t["TroopTableID"] == tid]
    cells = lambda: len([w for w in s.sent if w.proto == game.S2C_ENTER_CELL_TROOP])
    for n, (prop_id, tid) in enumerate(((10085, 155280), (10083, 155290), (10084, 155270))):
        assert cast(role, s, prop_id)[4:6] == b"\0\0" and not called(tid)
        role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(prop_id)))
        [(uid, t)] = called(tid)
        p = game.zone_prop(10351, prop_id)
        assert t["TeamNum"] == game.NP_TEAM and t["Prop"] == prop_id and uid in s.data["battle"].troops
        assert (t["PosX"], t["PosZ"]) == (p["PosX"] + game.PROP_RANGE_UNIT, p["PosZ"])     # SpawnNP_Range 1
        assert cells() == n + 1 and game.ACT_ENABLE_ALL_TROOPS in [a[0] for a in acts(s, game.ACT_ENABLE_ALL_TROOPS)]
    # the switch back (RechargeTime_SW 30): no second while its troop stands, a new one once it fell
    s.data["prop_states"][10085] = game.PROP_OFF
    assert cast(role, s, 10085)[4:6] == b"\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(10085)))
    [(uid, _)] = called(155280)
    s.data["battle"].troops[uid]["units"] = [0] * len(s.data["battle"].troops[uid]["units"])
    s.data["prop_states"][10085] = game.PROP_OFF
    assert cast(role, s, 10085)[4:6] == b"\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(10085)))
    assert len(called(155280)) == 2


def test_an_item_box_calls_its_ambush_and_still_opens_its_loot():
    # 20200 Windstone Desert: item box 276 (quest 2020145, GrantItem1_IB 451000219) -> 250360 desert tarantula
    from kuf2 import zone
    box = next(p for p in zone.for_spot(20200)["SmartPropData"] if p["SmartPropTypeID"] == 276)["SmartPropID"]
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"2020145": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 20200
    assert cast(role, s, box)[4:6] == b"\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(box)))
    b = bytes(next(w for w in s.sent if w.proto == game.S2C_PROP_CAST_DONE).buf)
    assert b[17] == 1 and b[20:24] == obf.u32(451000219)                                   # the loot window
    assert [t["Prop"] for t in s.data["zone_troops"].values() if t["TroopTableID"] == 250360] == [box]


def test_an_ambush_comes_at_its_rate_only():
    s = FieldSession({"active": {}, "done": []})
    s.data["spot"] = 10351
    p, row = game.zone_prop(10351, 10085), game.prop_row(435)
    assert not game.spawn_prop_ambush(s, p, dict(row, SpawnNP_Rate="40"), roll=lambda n: 40)
    assert game.spawn_prop_ambush(s, p, dict(row, SpawnNP_Rate="40"), roll=lambda n: 39)
    assert not game.spawn_prop_ambush(s, p, game.prop_row(423))          # no column: the quest inference's (423)


def test_a_prop_without_the_column_keeps_the_quest_inference():
    # 1160413: PropActivate 423 (10351's 10055-10057, no ActiveSpawnNPTroop_ID), NPNameKill 1000150 -> 158030, which no
    # troop of zone 1 carries: spawn_prop_targets still brings it beside the prop
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {"1160413": {"counts": [0] * 5}}, "done": []})
    s.data["spot"] = 10351
    assert cast(role, s, 10055)[4:6] == b"\0\0"
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(10055)))
    assert [t["Quest"] for t in s.data["zone_troops"].values() if t["TroopTableID"] == 158030] == [1160413]



def test_the_grey_fog_barricade_opens_when_its_barrels_are_broken():
    # 10358: invisible wall 10528 (type 232, resource 185 "switch, vanish, collision mesh") among barrels 10518-10527
    # (type 8, HP_AT 50, HC_AT 5)
    from kuf2 import combat
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["spot"] = 10358
    s.data["battle"] = combat.Battle()
    opened = lambda: [w for w in s.sent if w.proto == game.S2C_PROP_LIST]
    for barrel in range(10518, 10528):
        assert not opened()                                          # not while a barrel stands
        hit = bytes(7) + struct.pack("<HH", 1, 0) + bytes([1]) + obf.u32(barrel)
        for _ in range(5):
            role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))
        assert s.data["prop_states"][barrel] == game.PROP_BROKEN
    [w] = opened()
    rec = read_prop(bytes(w.buf)[2:])
    # shown, alive, in the state without collision (live: state 1 and alive false both left the hero behind it)
    assert (rec["id"], rec["shown"], rec["alive"], rec["state"]) == (10528, 1, 1, game.PROP_OPEN)
    assert s.data["prop_states"][10528] == game.PROP_ON



def test_np_troops_are_owned_by_their_force_so_each_keeps_its_team():
    # the client gives each owner id one Player, teamed by the first troop naming it; Grey Fog's first troop is an ally
    from kuf2 import combat
    s = FieldSession({"active": {}, "done": []})
    s.data["spot"] = 10358
    s.data["battle"] = combat.Battle()
    game.spawn_zone_troops(s)
    owners = {}
    for w in s.sent:
        if w.proto == game.S2C_ENTER_CELL_TROOP:
            st = bytes(w.buf)[3:3 + 0x3d]                            # u16 n, obool, then the 61-byte state
            uid, team, owner = struct.unpack_from("<H", st, 0x11)[0], struct.unpack_from("<h", st, 0)[0], \
                struct.unpack_from("<H", st, 0x30)[0]
            owners.setdefault(owner, set()).add(team)
    zt = s.data["zone_troops"]
    assert all(len(teams) == 1 for teams in owners.values())         # no owner mixes teams
    assert owners[21000] == {1} and owners[10000] == {0}             # enemies' force, Thompson's force
    assert game.np_owner({}) == game.NP_OWNER and game.np_owner({"ForceNum": 12000}) == 12000



def test_every_cached_zone_gives_each_force_one_team():
    # game.np_owner sends ForceNum as the owner; the client teams an owner's Player by its first troop, so a force
    # mixing teams would turn some of its troops (ENEMY-AI-WIRING batch 1)
    import json
    import pathlib
    zones = sorted((pathlib.Path(game.__file__).parent.parent / "data" / "zones").glob("*.json"))
    assert zones
    for f in zones:
        teams = {}
        for t in json.loads(f.read_text(encoding="utf-8")).get("NPCTroopInfoData", []):
            assert game.np_owner(t) == t["ForceNum"] >= 5000, (f.name, t["TroopID"])
            teams.setdefault(t["ForceNum"], set()).add(t.get("TeamNum"))
        mixed = {force: ts for force, ts in teams.items() if len(ts) > 1}
        assert not mixed, (f.name, mixed)



def test_enchant_level_adds_its_percent_of_the_items_own_trait():
    # ITEMS-WIRING I1: GLEN armour 159999962 (M_DEFENCE_PHYSICAL 169) at +3: 3 x 1.2 % -> 6.084 on each physical defence
    from kuf2 import items, hero
    got = dict(items.enchant_traits(159999962, 3))
    assert list(got) == ["M_DEFENCE_PHYSICAL"] and abs(got["M_DEFENCE_PHYSICAL"] - 6.084) < 1e-6
    assert items.enchant_traits(159999962, 0) == []
    weapon = dict(items.enchant_traits(100999001, 3))               # BasePhysical 10 ~ 20, 1.0 % a level
    assert abs(weapon["ATTACK_PHYSICAL_MIN"] - 0.3) < 1e-6 and abs(weapon["ATTACK_PHYSICAL_MAX"] - 0.6) < 1e-6
    plain = hero.stats(0, 30, [159999962])
    enchanted = hero.stats(0, 30, [159999962], [(159999962, 3)])
    assert abs(enchanted["DEFENCE_PHYSICAL_CLOSE"] - plain["DEFENCE_PHYSICAL_CLOSE"] - 6.084) < 1e-6
    assert enchanted["DEFENCE_MAGICAL_FIRE"] == plain["DEFENCE_MAGICAL_FIRE"]



# captures/game_20260926_232820_828928.log 23:28:33.751479 / .751816: one swing of the hero's cast 1 on units 17, 8,
# 13 of troop 1, reported by 0x504f and by 0x5066 (BATTLE-WIRING finding 2)
SWING_504F = bytes.fromhex("ffff7f00e19f001000a865ab10c301001012030000ddbc0014c000ea03010bc000dd430110c00000")
SWING_5066 = bytes.fromhex("153fae85f3041001000100000100030020020001a00100")


def test_a_swing_reported_by_0x504f_and_0x5066_lands_once(monkeypatch):
    # the 0x5066 carries the swing; the 0x504f copy (action 0xffff) is dropped
    monkeypatch.setattr(combat, "random", Even())
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=hero_record(30))
    s.data["battle"].add_np(1, 1072, 19, c=combat.np_combatant(2))   # the test enemy: 19 x 1072, defence 300
    s.data["casts"], s.data["cast_ability"] = {1: b"\0\0"}, {1: 164}  # the hero's basic attack 164 in flight
    role.handlers[combat.C2S_HERO_HIT](s, pkt(combat.C2S_HERO_HIT, SWING_504F))
    assert s.data["battle"].troops[1]["units"] == [1072] * 19        # dropped: the 0x5066 applies it
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, SWING_5066))
    units = s.data["battle"].troops[1]["units"]
    # 117.5 attack (31 + the sword's 6 ~ 7 + passive 70's 80 at its level 6 for hero level 30, Even: the middle) x AR 1
    # against defence 300 less the passive's penetration (1,562): none left, 117.514 -> 118 once on each unit
    assert [i for i, hp in enumerate(units) if hp < 1072] == [8, 13, 17] and {units[i] for i in (8, 13, 17)} == {954}
    role.handlers[combat.C2S_HERO_HIT](s, pkt(combat.C2S_HERO_HIT, SWING_504F))   # again, however late: its action
    assert {units[i] for i in (8, 13, 17)} == {954}                   # 0xffff makes it a copy (census E2: the 2 s
                                                                      # window let 13 of 1,182 live copies land twice)



def test_room_start_hero_troop_has_no_barracks_uid():
    # UI-WIRING U1: T+0x09 feeds troop +0x7e0, which the quick bar's gate compares with 0 on the hero page
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=30, name="Aldric", look="00" * 0x33, skills={})
    game.send_start_header(s, 10352)
    body = bytes(next(w for w in s.sent if w.proto == game.S2C_START_TROOP_INFO).buf)[2:]
    assert body[0x09:0x11] == bytes(8) and body[0x01:0x03] == b"\x01\x00" and body[0x1d:0x1f] == b"\x01\x00"



def test_mission_data_rules_difficulty_staging_control_and_undying():
    # MISSIONS-WIRING G1 / G2 / G7 / G8
    names = {20001: "하드전용", 20002: "헬 전용", 20003: ""}
    assert not game.for_difficulty({"ForceNum": 20001}, names, 0) and game.for_difficulty({"ForceNum": 20001}, names, 1)
    assert not game.for_difficulty({"ForceNum": 20002}, names, 1) and game.for_difficulty({"ForceNum": 20002}, names, 2)
    assert not game.for_difficulty({"ForceNum": 20003, "TroopAlias": "하드_궁병"}, names, 0)
    assert game.for_difficulty({"ForceNum": 20003, "TroopAlias": "궁병"}, names, 0)
    assert not game.hostile({"TeamNum": 1, "TroopTableID": 162120, "TroopAlias": "대사용 도적"})
    assert not game.hostile({"TeamNum": 1, "TroopTableID": 162120, "Staging": True})
    assert game.hostile({"TeamNum": 1, "TroopTableID": 162120})
    assert game.staging(10235, {"ForceNum": 49300}, {}) and not game.staging(10235, {"ForceNum": 49301}, {})
    assert game.start_control_mode(10358) == 1                       # Grey Fog: the hero alone, direct control
    assert game.start_control_mode(10233) == 0                       # Tower of Moonlight hands a troop over
    assert game.start_control_mode(10352) == 0                       # a field
    assert {10361, 10362, 10235} <= set(game.UNDYING_MISSIONS)


# Damage (BATTLE-WIRING B11 / B53 / B60 / B12 / B15; owner Q6 2026-09-27: §3 candidate A)

def record(atk, level, dfn=0.0, pen=0.0, team=1, branch=None):
    """A combatant with one attack value and one defence against every type (the anchor table's inputs)."""
    return combat.combatant(level, team, atk=(atk, atk), matk=(atk, atk), close=dfn, far=dfn,
                            magical=dict.fromkeys(combat.ELEMENTS, dfn), pen=pen, mpen=pen, branch=branch)


# §3 "Why 500 x level": attacker ATK, PR, level, target defence (after penetration) -> candidate A's damage
ANCHORS = [(109.6, 0.3, 2, 322, 24.9),     # Thompson (162010) vs Encablossian 162180: W71 "deals 25-50"
           (109.6, 0.45, 2, 74, 45.9),     # the same with ATTACK1_x 1.5 vs 162120
           (300, 1, 1, 74, 261),           # prologue hero (%LevelRevise) vs 111150 infantry
           (300, 1, 1, 322, 183),          # ... vs 111190 Encablossian beast
           (37.5, 1, 30, 74 - 69, 37.5),   # Aldric L30 (penetration 69) vs 162120
           (35, 1, 2, 74, 32.6),           # hero L2, level-1 weapon, vs 162120
           (48, 1, 6, 386, 42.5),          # hero L6 vs the Mountain Troll 134080
           (115, 1, 13, 837, 102),         # hero L13 vs Lake Bled 152550
           (34.2, 1, 2, 211, 28.2),        # Encablossian 162120 vs hero L2
           (513, 1, 30, 2800, 432),        # L30 troop vs hero L30 in level-30 gear
           (14, 1, 2, 74, 13.0)]           # militia 162030 vs 162120


def test_resolver_reproduces_the_anchor_table():
    for atk, pr, level, dfn, want in ANCHORS:
        got = combat.resolve(record(atk, level), record(0, 1, dfn), {"type": "LOOSE", "pr": pr, "ar": 1.0}, rng=Even())
        assert abs(got - want) <= 1, (atk, pr, level, dfn, got, want)
    # the cold zone: a fixed 2000 (flat) against 5000 ice resistance from a level-40 source, W1079 "about 20 %"
    cold = combat.resolve(record(0, 40), record(0, 1, 5000), {"type": "ICE", "pr": 1, "ar": 1, "flat": 2000}, rng=Even())
    assert cold == 1600
    # the same rows from the tables: Thompson's %Combat gives PR 0.3 (Default_PowerRate x ATTACK1) and 0.45 (x
    # ATTACK1_1 1.5); his penetration 322 (the §3 D row) lifts both into W71's 25-50 (33, 49)
    thompson = combat.combatant_leader(combat._rows_by("npleadertable", "Contents", "NPLEADER_ID")["162010"], 0)
    names = combat._action_names()
    common, rush = names.index("ATTACK_NORMAL_COMMON_1"), names.index("ATTACK_LIGHT_RUSH")
    assert abs(combat.hit_attack(thompson, common)["pr"] - 0.3) < 1e-9
    assert abs(combat.hit_attack(thompson, rush)["pr"] - 0.45) < 1e-9
    for target, action in ((162180, common), (162120, rush)):
        got = combat.resolve(thompson, combat.np_combatant(target), combat.hit_attack(thompson, action), rng=Even())
        shown = min(got, int(combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")[str(target)]["HP_BASEUNIT"]))
        assert 25 <= shown <= 50, (target, got)
    # the synastry (§3.1): 162180 (a clur, DEFENCE_TYPE 257) takes LOOSE x1; 162120 (a primitive, 260) takes LOOSE x4,
    # 197, which the number over the unit caps at its 42 hp (0x507b sends before - after): W71's 25-50 still holds
    # every hit takes at least 1; the spread stays within 10 %
    assert combat.resolve(record(0.1, 1), record(0, 1, 9999), {"pr": 1, "ar": 1}) == 1
    spread = {combat.resolve(record(1000, 1), record(0, 1), {"pr": 1, "ar": 1}) for _ in range(200)}
    assert min(spread) >= 900 and max(spread) <= 1100 * 1.0 and len(spread) > 20


def test_the_synastry_file_joins_every_troop_type():
    # Info.pkg entry 0x019e20b1c59402f5 (no name in any list): every DEFENCE_TYPE of the troop tables is a %Contents
    # TypeName (BATTLE-WIRING §3.1); 339 COMMON rows (2 PVP)
    from kuf2 import tables
    assert {k: len(v) for k, v in combat._synastry().items()} == {
        "Contents": 341, "StateMapper": 65, "TypeName": 387, "SynastryGroup": 6, "SynastryGroupMatrix": 6,
        "Line_Defence": 11}
    contents = combat._synastry_index()[0]
    assert len(contents) == 339
    for table in ("nptrooptype", "npleadertype", "trooptype", "herotable"):
        assert {r["DEFENCE_TYPE"] for r in tables.sections(table)["System"]} <= set(contents), table


@pytest.mark.parametrize("attacker, kind, target, state, want", [
    (133120, "RANGE", 133080, "IDLE", 3.0),       # Tower: the handed archers on a winged wyrm (278)
    (133120, "RANGE", 133080, "MELEE", 3.0),      # 278 has no %StateMapper row: the same row in every state
    (133120, "MUSKET", 133080, "IDLE", 5.0),
    (133120, "HOLY", 133080, "IDLE", 3.0),
    (133120, "BLAST", 133080, "IDLE", 0.5),
    (133080, "BLAST", 133120, "IDLE", 1.5),       # the wyrm's main attack on the archers (214)
    (133140, "RANGE", 133270, "IDLE", 0.5),       # human infantry (162) ...
    (133140, "RANGE", 133270, "MELEE", 1.0),      # ... engaged: its %StateMapper MELEE row 222
    (133270, "LOOSE", 133050, "IDLE", 4.0),       # a primitive (260) takes LOOSE x4
    (133140, "RANGE", 133050, "IDLE", 0.5),
    (133140, "RANGE", 133050, "MELEE", 3.0),      # engaged (262)
])
def test_the_synastry_multiplier_by_target_type_state_and_attack_type(attacker, kind, target, state, want):
    assert combat.synastry(combat.np_combatant(attacker, 0), combat.np_combatant(target, 1), kind, state) == want


def test_the_synastry_troop_revision_and_group_matrix():
    # TroopRevision 0.5 on LARGE (63): read as what a troop's units deal (ours), not the hero or a leader
    large = combat.combatant(1, 1, defence_type="63")
    loose = float(combat._synastry_index()[0]["63"]["LOOSE"])
    assert combat.synastry(combat.combatant(1, 0), large, "LOOSE") == loose * 0.5
    assert combat.synastry(combat.combatant(1, 0, hero=True), large, "LOOSE") == loose
    assert combat.synastry(combat.combatant(1, 0, leader=True), large, "LOOSE") == loose
    # %SynastryGroupMatrix: a colossal (5) target takes x3.2 from a storm (3) attacker; a "-" pair is 1
    colossal = combat.combatant(1, 1, defence_type="152", group="5")      # 152 무상성: 1 in every column
    assert combat.synastry(combat.combatant(1, 0, group="3"), colossal, "LOOSE") == 3.2
    assert combat.synastry(combat.combatant(1, 0, group="0"), colossal, "LOOSE") == 1.0
    assert combat.synastry(combat.combatant(1, 0), combat.combatant(1, 1), "LOOSE") == 1.0   # no DEFENCE_TYPE
    assert combat.np_combatant(133080)["defence_type"] == "278" and hero_record()["defence_type"] == "0"


def test_a_held_status_raises_the_attack_its_traits_name():
    # the archers' skill 200147 puts 2000418 on its caster troop: ATTACK_PHYSICAL +70 % (Traitvalue011) +1 (012) on its
    # units (TROOP), ATTACK_SPEED +100 % (the client runs that one); the client's trait code 0x1407bc0c0 -> 0x140a04c90
    # adds flat = Traitvalue_2 and base x Traitvalue_1 x 0.01
    assert combat.status_bonus({2000418: 8}, "ATTACK_PHYSICAL") == (70.0, 1.0)
    assert combat.status_bonus({2000418: 8}, "ATTACK_PHYSICAL", leader=True) == (0.0, 0.0)
    assert combat.status_bonus({57: 1}, "ATTACK_PHYSICAL", leader=True) == (5.0, 0.0)   # Speed Reload 1: +5 %
    assert combat.status_bonus({10: 1}, "ATTACK_SPEED")[0] < 0                            # a SUBTRACT trait
    archers, wyrm = combat.np_combatant(133120, 0), combat.np_combatant(133080, 1)
    volley = combat.hit_attack(archers, combat.VOLLEY_ACTION)                           # RANGE, PR 2 (the revision)
    term = (1 - 88 / (88 + 500 * 4)) * 3                                                # D 322 - pen 234; RANGE x3
    assert combat.resolve(archers, wyrm, volley, rng=Even()) == round(0.6 * 2 * term) == 3
    assert combat.resolve(archers, wyrm, volley, rng=Even(), own={2000418: 8}) == round((0.6 * 1.7 + 1) * 2 * term) == 12


def test_engage_reports_put_a_target_in_its_melee_row(monkeypatch):
    # 0x5058 on / off and 0x506d (plain u16) keep who is in melee; a volley on an engaged primitive takes its
    # %StateMapper MELEE row (262: RANGE x3), an idle one its own (260: x0.5)
    monkeypatch.setattr(combat, "random", Even())
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    b = s.data["battle"] = combat.Battle()
    b.add_np(11004, 392, 42, c=combat.np_combatant(133140, 0))
    b.add_np(20001, 10 ** 6, 1, c=combat.np_combatant(133050, 1))
    b.add_np(10100, 1813, 20, c=combat.np_combatant(133270, 0))

    def volley():
        before = b.troops[20001]["units"][0]
        body = enc_uid(11004) + struct.pack("<H", 1) + enc_uid(20001) + bytes([127 * 2])
        role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
        return before - b.troops[20001]["units"][0]

    def engage(flag):
        role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, enc_uid(10100) + bytes([flag]) + enc_uid(20001)))
    idle = volley()                                     # 42 arrows of 11.8 x PR 2 (no defence left after penetration)
    assert idle == 42 * round(11.8 * 2 * 0.5)
    engage(1)
    assert combat.engaged(s, 20001) and combat.engaged(s, 10100) and volley() == 42 * round(11.8 * 2 * 3)
    engage(0)
    assert not combat.engaged(s, 20001) and volley() == idle
    engage(1)
    role.handlers[combat.C2S_ENGAGE_CLEAR](s, pkt(combat.C2S_ENGAGE_CLEAR, struct.pack("<H", 20001)))
    assert not combat.engaged(s, 20001) and not combat.engaged(s, 10100)


@pytest.mark.parametrize("attacker, action, target, blows", [
    (133270, 72, 133050, 1),      # the scouts' blow on F20000 / F20100's primitives (85 hp): one a unit, as before
    (133170, 72, 133050, 1),      # the CPU infantry's (2 before)
    (133050, 72, 133270, 59),     # a primitive's on the scouts (1,813 hp): LOOSE on 162 is x1, as before
])
def test_towers_melee_fights_keep_their_blows_per_unit(attacker, action, target, blows):
    att, tgt = combat.np_combatant(attacker, 0), combat.np_combatant(target, 1)
    hp = int(combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")[str(target)]["HP_BASEUNIT"])
    for state in (combat.IDLE, combat.MELEE):
        hit = combat.resolve(att, tgt, combat.hit_attack(att, action), rng=Even(), state=state)
        assert -(-hp // hit) == blows, (state, hit)


# captures/game_20260926_202455_701360.log 20:25:05.969288: the test enemy's hit on the hero
NP_HIT_5053 = bytes.fromhex("1300 0c10 41a8b8a0 1012 9d08 00 4800 0100 10c3 0100 000cc70002d0 0000".replace(" ", ""))


def test_np_hit_reads_attacker_unit_and_action_from_the_header(monkeypatch):
    monkeypatch.setattr(combat, "random", Even())
    assert combat.hit_source(NP_HIT_5053, combat.C2S_HIT) == (1, 17, 72)
    assert combat.action_name(72) == "ATTACK_NORMAL_COMMON_1"
    enemy = combat.np_combatant(2)                                    # nptrooptable 2 -> nptrooptype 144
    assert enemy["powers"]["ATTACK_NORMAL_COMMON_1"] == (1.0, "TROOP_ATTACK1")
    assert combat.hit_attack(enemy, 72) == {"type": "LOOSE", "pr": 1.0, "ar": 1.0, "action": "ATTACK_NORMAL_COMMON_1"}
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=record(0, 1, 0, team=0))
    s.data["battle"].add_np(1, 1072, 19, c=combat.combatant(10, 1, atk=(40, 40)))   # a stronger attacker in its place
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, NP_HIT_5053))
    assert s.data["battle"].troops[0]["hp"] == 960                     # 40 at no defence, on the hero (unit -1)
    shown = next(w for w in s.sent if w.proto == combat.S2C_HERO_DAMAGE)
    assert struct.unpack_from("<iH", bytes(shown.buf))[0:2] == (40, 0)


def test_a_three_hit_skill_uses_each_process_rate(monkeypatch):
    # ability 15 (aimed shot): AttributeRate 2500, ProcessRate "70 100 50" -> 1.75 / 2.5 / 1.25 x ATK; the basic combo
    # 166 restates its 1250 as "125 125" -> 1.25 on each execute
    hero = hero_record(30)                                            # 117.514 physical attack with passive 70 at level 6 (Even: the middle)
    assert [round(combat.ability_attack(hero, 15, 1, k)["ar"], 4) for k in (1, 2, 3)] == [1.75, 2.5, 1.25]
    assert [combat.ability_attack(hero, 166, 1, k)["ar"] for k in (1, 2)] == [1.25, 1.25]
    monkeypatch.setattr(combat, "random", Even())
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=hero)
    s.data["battle"].add_np(9, 5000, 1, c=combat.combatant(1, 1))    # no defence
    s.data["casts"], s.data["cast_ability"] = {4: b"\0\0"}, {4: 15}
    execute = bytes(7) + struct.pack("<H", 4) + struct.pack("<H", 1) + bytes([0]) + struct.pack("<HHH", 9, 1, 0) + bytes(1)
    drops, last = [], 5000
    for _ in range(3):
        combat.on_ability_execute(s, pkt(combat.C2S_ABILITY_EXECUTE, execute), game.send_troop_hp)
        now = s.data["battle"].troops[9]["units"][0]
        drops, last = drops + [last - now], now
    # the first hit marks the target (status 86, STATUSEFFECT_ADD_DAMAGE +20 %), which the later hits then get
    assert drops == [round(117.514 * 1.75), round(117.514 * 2.5 * 1.2), round(117.514 * 1.25 * 1.2)]   # 206, 353, 176
    assert s.data["cast_ability"] == {4: 15} and s.data["executes"] == {4: 3}             # kept for the whole cast
    combat.on_cast_done(s, pkt(combat.C2S_CAST_DONE, struct.pack("<H", 4)))
    assert not s.data["cast_ability"] and not s.data["executes"] and not s.data["casts"]  # dropped at its 0x506a


def test_evade_status_makes_the_hero_take_nothing(monkeypatch):
    # 6321 (evade 14's escape status) is TROOP_INVINCIBLE_DPS / %Forbidden Invincibility; the guard's 341 is group 10
    # COMMON_GUARD: GUARD_REDUCE 700 + its +300, x its TRAITRATE_PROGRESS 90 % while fresh -> a tenth taken
    monkeypatch.setattr(combat, "random", Even())
    assert 6321 in combat.invincible_statuses()
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=hero_record(1))              # guard 700
    s.data["battle"].add_np(1, 1072, 19, c=combat.combatant(10, 1, atk=(100, 100)))
    hit = lambda: combat.apply_hits(s, [(0, [-1])], game.send_troop_hp, attacker=1, attack={"type": "LOOSE"})
    s.data["statuses"] = {0: {6321: {"level": 3, "until": time.monotonic() + 3}}}
    hit()
    assert s.data["battle"].troops[0]["hp"] == 1000 and not [w for w in s.sent if w.proto == combat.S2C_HERO_DAMAGE]
    s.data["statuses"] = {0: {6321: {"level": 3, "until": time.monotonic() - 1}}}            # ran out: it lands
    hit()
    full = 1000 - s.data["battle"].troops[0]["hp"]
    assert full == round(100 * (1 - 70 / (70 + 5000)))                # 99 against the hero's defence 70
    from kuf2 import status
    s.data["statuses"] = {0: {341: {"level": 1, "until": time.monotonic() + 600, "groups": status.groups(341),
                                     "caster": 0}}}                                   # guarding
    hit()                                                             # 700 + 341's +300, x 90 % fresh: a tenth
    assert 1000 - full - s.data["battle"].troops[0]["hp"] == round(99 * 0.1)
    # the 10358 floor still stops at 1 (test_walk_p2 runs every undying mission)
    s.data.pop("statuses")
    s.data["battle"].troops[0]["floor"] = 1
    for _ in range(20):
        hit()
    assert s.data["battle"].troops[0]["hp"] == 1


def test_the_hero_hits_large_monsters_twice_as_hard():
    # abilitytypeinfo %Function ability 3: RACE_BRANCH_ADD_DAMGE 영웅용중형피해 100 %, 영웅용대형피해 200 % (%TroopBranch
    # 95 / 96); an infantry troop is in neither group
    scorpion, infantry, ogre = (record(0, 1, 100, branch=b) for b in ("SCORPION", "INFANTRY", "OGRE"))
    assert combat.ability_modifiers(3, 1, scorpion) == 2.0 and combat.ability_modifiers(3, 1, infantry) == 1.0
    assert combat.ability_modifiers(3, 1, ogre) == 1.0                # the medium group, at 100 %
    hero, attack = record(1000, 30), combat.ability_attack(hero_record(30), 3, 1, 1)
    hero["hero"] = True
    big, small = (combat.resolve(hero, t, attack, rng=Even()) for t in (scorpion, infantry))
    assert abs(big - 2 * small) <= 1
    assert combat.np_combatant(134080)["branch"] == "SINGLE_MELEE"    # the Mountain Troll: medium, 100 %


def test_the_aim_debuff_adds_twenty_percent():
    # 15: STATUSEFFECT_ADD_DAMAGE 86 20 %; the guard group 10 (COMMON_GUARD) +235 % for the kits' 84-type rows
    troop = record(0, 1, branch="INFANTRY")
    assert combat.ability_modifiers(15, 1, troop, {86}) == pytest.approx(1.2)
    assert combat.ability_modifiers(15, 1, troop) == 1.0
    guard_breaker = next(a for (a, lv), rows in combat._functions().items()
                         if lv == "1" and any(r["FunctionType"] == "STATUSEFFECTGROUP_ADD_DAMAGE" for r in rows))
    assert combat.ability_modifiers(guard_breaker, 1, record(0, 1), {341}) == pytest.approx(3.35)   # 341: group 10
    # HP_BACEUNIT_ADD_DAMAGE 151 "70%, 0, 30%": +70 % on a unit below 30 % hp
    assert combat.ability_modifiers(151, 1, troop, (), 0.2) == pytest.approx(1.7)
    assert combat.ability_modifiers(151, 1, troop, (), 0.5) == 1.0


def test_a_heal_ability_raises_an_ally_and_never_damages_it(monkeypatch):
    # 357 (Isabella's rune heal): AttributeOperation ADD, NATURE, AttributeRate 3500 -> 3.5 x her magical attack
    monkeypatch.setattr(combat, "random", Even())
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    isabella = hero_record(30, cls=3)                                 # 113.2 magical attack (28.2 + the rapier's 5 + passive 368's 80 at level 6)
    s.data["battle"].add_hero(0, 1000, c=isabella)
    s.data["battle"].add_np(21000, 500, 2, c=combat.combatant(2, 0))   # an allied troop (team 0), hurt
    s.data["battle"].troops[21000]["units"] = [100, 500]
    s.data["casts"], s.data["cast_ability"] = {2: b"\0\0"}, {2: 357}
    execute = bytes(7) + struct.pack("<H", 2) + struct.pack("<H", 1) + bytes([0]) + struct.pack("<HHHH", 21000, 2, 0, 1 << 5) + bytes(1)
    combat.on_ability_execute(s, pkt(combat.C2S_ABILITY_EXECUTE, execute), game.send_troop_hp)
    assert s.data["battle"].troops[21000]["units"] == [100 + round(113.201 * 3.5), 500]   # capped at the unit's max
    heal = next(w for w in s.sent if w.proto == game.S2C_HEAL)
    assert bytes(heal.buf)[:10] == struct.pack("<IHI", game.HEAL_NO_SOURCE, 21000, 0)
    s.sent.clear()
    s.data["cast_ability"] = {2: 15}                                  # a SUBTRACT ability listing the ally
    s.data["executes"] = {}
    combat.on_ability_execute(s, pkt(combat.C2S_ABILITY_EXECUTE, execute), game.send_troop_hp)
    assert s.data["battle"].troops[21000]["units"] == [496, 500] and not [w for w in s.sent if w.proto == game.S2C_TROOP_HP]
    # %Heal Revival: dead units come back (0x505b alive TRUE), up to MaxHealUnitHp % of a unit
    b = combat.Battle()
    b.add_np(5, 400, 3)
    b.troops[5]["units"] = [0, 200, 0]
    assert b.heal(5, [1], 150, revive=0.2) == (80 + 350 + 80, None, [0, 2])


def test_a_charge_report_damages_each_target_by_its_ratio(monkeypatch):
    # 0x505a: coded source troop, n, n x (coded target, u8 (int)(ratio x 127) x 2 + flag): 127 = full, 64 = half
    monkeypatch.setattr(combat, "random", Even())
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_np(5, 10232, 1, c=combat.np_combatant(134080))   # the Mountain Troll charges (PR 1.2)
    for uid in (7, 8):
        s.data["battle"].add_np(uid, 1000, 3, c=combat.combatant(1, 0))
    s.data["battle"].troops[8]["units"][0] = 0                          # its front unit is already down
    body = enc_uid(5) + struct.pack("<H", 2) + enc_uid(7) + bytes([127 * 2]) + enc_uid(8) + bytes([64 * 2 + 1])
    role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
    full = round(123.8 * 1.2)                                            # 149 at no defence
    assert s.data["battle"].troops[7]["units"] == [1000 - full, 1000, 1000]
    assert s.data["battle"].troops[8]["units"] == [0, 1000 - round(123.8 * 1.2 * 64 / 127), 1000]   # the next unit


VOLLEY_S = 2.4          # ours, from live: the handed archers' 0x505a on the wyrms came 12-13 per 30 s (2026-09-29 03:55
                        # session, 334 volleys); the client fires twice as fast under ATTACK_SPEED +100 % (0x140a04c90
                        # caps the rate at x2)


def wyrm_fight(monkeypatch, skill=True, cap=300.0):
    """Tower's winged wyrms headless: the handed archers 11006 volley (0x505a, full share) at the first living wyrm
    every VOLLEY_S, half that while they hold 2000418, and cast 200147 (0x505f and its 0x5066: the status engine puts
    2000418 on them) whenever its CooldownTime allows; the scene's skill rule is off (the resolver alone), rolls
    without crits. -> [seconds from the first volley at which each wyrm fell]."""
    from kuf2 import director
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(combat, "random", Even())
    monkeypatch.setattr(director, "on_skill", lambda *a, **k: None)
    s = mission_room(10233)
    run_pending(s)
    game.spawn_force(s, 30000)
    director.run(s, ("hand", 11006))
    role, b = game.make(NoSave(), 0), s.data["battle"]
    cooldown = float(combat.improvement(200147, 8)["CooldownTime"])      # 20 s; 2000418 lasts 15 s
    ready = shot = start = clock[0]
    down = []
    while len(down) < 3 and clock[0] - start < cap:
        wyrm = next(w for w in (30001, 30002, 30000) if combat.Battle.total(b.troops[w]) > 0)
        if skill and clock[0] >= ready:
            body = enc_uid(wyrm) + struct.pack("<H", 11006) + obf.u32(200147) + bytes(7)
            role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, body))
            execute = bytes(7) + struct.pack("<HHBH", s.data["cast_serial"], 1, 1, 11006) + b"\0"
            role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, execute))
            ready = clock[0] + cooldown
        if clock[0] >= shot:
            body = enc_uid(11006) + struct.pack("<H", 1) + enc_uid(wyrm) + bytes([127 * 2])
            role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
            shot = clock[0] + VOLLEY_S / (2 if 2000418 in combat.held_levels(s, 11006) else 1)
        if combat.Battle.total(b.troops[wyrm]) == 0:
            down.append(round(clock[0] - start, 1))
        clock[0] += 0.1
    return down


def test_the_handed_archers_bring_the_wyrms_down_with_their_skill(monkeypatch):
    # Tower's staged wyrms (133080: 11,453 hp, DEFENCE_TYPE 278) under the handed archers (133120: 42 units, ATTACK 0.6,
    # RANGE x3 on 278): 3 an arrow, 12 with the skill's 2000418 (x1.7 + 1), at twice the rate. Ours 32 / 70 / 109 s
    # (with crits about 28 / 64 / 95); without the skill 224 s a wyrm. The original (part 2): the skill at 12:02, the
    # wyrms down at 12:12, 12:29, 12:46 (the count 1/3 2/3 3/3), with the other archers helping (Glen 1340; the handed
    # troop showed "Waiting for command" from 12:12)
    assert wyrm_fight(monkeypatch) == [31.8, 70.4, 109.0]


def test_without_the_skill_the_handed_archers_take_minutes_a_wyrm(monkeypatch):
    assert wyrm_fight(monkeypatch, skill=False, cap=250) == [224.0]


def test_the_handed_archers_are_their_np_row_with_the_zones_units():
    # the original's HUD at the wyrms (part 2 12:04, F2): HP 98,700 = the zone's UnitNum 42 x nptrooptable 133120
    # HP_BASEUNIT 2,350 (UNIT_COUNT 0, "편입궁병_0명"): an incorporated troop keeps its NP row (not a trooptable player
    # troop), so its attack is that row's 0.6, and its level 4 (the plate's "Lv.4")
    s = mission_room(10233)
    t = s.data["battle"].troops[11006]
    assert t["units"] == [2350] * 42 and combat.Battle.total(t) == 98700
    assert t["c"]["atk"][combat.PHYSICAL] == (0.6, 0.6) and t["c"]["level"] == 4 and t["c"]["main"] == "RANGE"


def test_one_volley_of_the_other_archers_takes_a_quarter_of_a_wyrm(monkeypatch):
    # the CPU archers 133140 (ATTACK 11.8): 42 x 68 = 2,856 of the wyrm's 11,453 a volley. The original's wyrms lost 62 %
    # in 4.5 s (12:15.5-12:20) and 98 % in 4 s (12:35-12:39) while the handed troop waited for command: 2-4 such volleys
    monkeypatch.setattr(combat, "random", Even())
    archers, wyrm = combat.np_combatant(133140, 0), combat.np_combatant(133080, 1)
    arrow = combat.resolve(archers, wyrm, combat.hit_attack(archers, combat.VOLLEY_ACTION))
    assert arrow == round(11.8 * 2 * (1 - 88 / 2088) * 3) == 68 and 0.24 < 42 * arrow / 11453 < 0.26


def test_a_ranged_volley_lands_its_arrows_by_each_targets_share(monkeypatch):
    # 0x505a from Tower of Moonlight's handed archers 11006 (133120, 42 units, main attack RANGE): the share is sent as
    # share ** 0.8; 42 arrows on the full-share target, 42 x (64/127) ** 1.25 = 18 on the other (live 2026-09-28: one
    # charge hit, 1 damage per target, before)
    monkeypatch.setattr(combat, "random", Even())
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    archers = combat.np_combatant(133120, team=0)
    assert combat.ranged(archers["main"])
    s.data["battle"].add_np(11006, 100, 42, c=archers)
    for uid in (7, 8):
        s.data["battle"].add_np(uid, 10 ** 6, 3, c=combat.combatant(1, 1))
    body = enc_uid(11006) + struct.pack("<H", 2) + enc_uid(7) + bytes([127 * 2]) + enc_uid(8) + bytes([64 * 2])
    role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
    arrow = combat.resolve(archers, combat.combatant(1, 1), combat.hit_attack(archers, combat.VOLLEY_ACTION))
    lost = lambda uid: 3 * 10 ** 6 - sum(s.data["battle"].troops[uid]["units"])
    assert arrow > 0 and lost(7) == 42 * arrow and lost(8) == 18 * arrow
    # a melee source keeps the charge rule (test_a_charge_report_damages_each_target_by_its_ratio)


def test_the_hero_damage_boost_multiplies_his_hits_only(monkeypatch):
    # owner 2026-09-28: "can you incress our hero damage by 10000x?" (combat.HERO_DAMAGE_SCALE; tests run it at 1)
    monkeypatch.setattr(combat, "random", Even())
    monkeypatch.setattr(combat, "HERO_DAMAGE_SCALE", 10000)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 10 ** 9, c=record(100, 1, team=0))
    s.data["battle"].add_np(1, 10 ** 9, 1, c=combat.combatant(1, 1, atk=(100, 100)))
    combat.apply_hits(s, [(1, [0])], game.send_troop_hp, attacker=0, attack={"pr": 1.0, "ar": 1.0})
    assert 10 ** 9 - s.data["battle"].troops[1]["units"][0] == 100 * 10000      # 100 at scale 1
    combat.apply_hits(s, [(0, [0])], game.send_troop_hp, attacker=1, attack={"pr": 1.0, "ar": 1.0})
    assert 10 ** 9 - s.data["battle"].troops[0]["hp"] < 10000                   # the enemy's hits are not boosted


@pytest.mark.parametrize("scale", [1.5, 0.5])
def test_a_fractional_hero_damage_boost_keeps_whole_hit_points(monkeypatch, scale):
    # adversarial 2026-11-05: `--hero-damage 1.5` made the hits floats; the first hero hit's packet raised TypeError
    monkeypatch.setattr(combat, "random", Even())
    monkeypatch.setattr(combat, "HERO_DAMAGE_SCALE", scale)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 10 ** 6, c=record(100, 1, team=0))
    s.data["battle"].add_np(1, 1000, 3, c=combat.combatant(1, 1, atk=(100, 100)))
    for _ in range(40):
        combat.apply_hits(s, [(1, [0, 1, 2])], game.send_troop_hp, attacker=0, attack={"pr": 1.0, "ar": 1.0})
    for w in s.sent:
        w.frame()                                                               # every packet still encodes
    assert all(isinstance(u, int) for u in s.data["battle"].troops[1]["units"])


def test_hits_tally_on_the_troop_icons(monkeypatch):
    # 0x507c (UiInGame::PlayTroopDamage): u16 n, n x (split HP value, u16 victim, u16 attacker), one record per victim
    monkeypatch.setattr(combat, "random", Even())
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, 1000, c=record(100, 1, team=0))
    s.data["battle"].add_np(1, 1000, 3, c=combat.combatant(1, 1))
    combat.apply_hits(s, [(1, [0, 1])], game.send_troop_hp, attacker=0, attack={"pr": 1.0, "ar": 1.0})
    [tally] = [w for w in s.sent if w.proto == combat.S2C_DAMAGE_TALLY]
    value = bytearray(4)
    game.pack_value(value, 0, 200)
    assert bytes(tally.buf) == struct.pack("<H", 1) + bytes(value) + struct.pack("<HH", 1, 0)
    s.sent.clear()
    combat.apply_hits(s, [(1, [0])], game.send_troop_hp)              # no attacker named: no tally
    assert not [w for w in s.sent if w.proto == combat.S2C_DAMAGE_TALLY]


# --- the status engine (planning/wiring/HERO-CONTROLS-WIRING.md batches 1-3; kuf2/status.py) ---

def use_ability(role, s, ability, targets=(), caster=0):
    """The hero's 0x5117 and one 0x5066 of that cast naming whole troops; returns the serial."""
    body = obf.u32(ability) + bytes(12) + struct.pack("<H", caster) + bytes(7) + obf.u16(0) + bytes(3)
    role.handlers[combat.C2S_USE_ABILITY](s, pkt(combat.C2S_USE_ABILITY, body))
    execute(role, s, s.data["cast_serial"], targets)
    return s.data["cast_serial"]


def execute(role, s, serial, targets=()):
    lst = struct.pack("<H", len(targets)) + b"".join(bytes([255]) + struct.pack("<H", uid) for uid in targets)
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE,
                                                     bytes(7) + struct.pack("<H", serial) + lst + bytes([0])))


def added(s):
    """[(status, level, duration, [uids], caster)] of the 0x5074 sent."""
    out = []
    for w in s.sent:
        if w.proto == combat.S2C_STATUS_ADD:
            b = bytes(w.buf)
            n = struct.unpack_from("<H", b)[0]
            recs = [struct.unpack_from("<HH", b, 3 + 5 * i) for i in range(n)]
            caster, level, st, _ = struct.unpack_from("<HBIH", b, 2 + 5 * n)
            out.append((st, level, recs[0][0], [u for _, u in recs], caster))
    return out


def ended(s):
    """[(uid, status)] of the 0x5078 sent."""
    return [(struct.unpack_from("<H", bytes(w.buf), 3)[0], struct.unpack_from("<I", bytes(w.buf), 6)[0])
            for w in s.sent if w.proto == combat.S2C_STATUS_END]


def stat_sent(s, stat):
    """The values of one leader stat in the 0x5138 sent (stat ids above 2: plain u32)."""
    out = []
    for w in s.sent:
        if w.proto == combat.S2C_STATS:
            b = bytes(w.buf)
            out += [struct.unpack_from("<I", b, 1 + 7 * i)[0] for i in range(b[0])
                    if struct.unpack_from("<b", b, 5 + 7 * i)[0] == stat]
    return out


def hero_session(**kit):
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    c = s.data["account"]["characters"][0]
    c.update(level=30)
    s.data["char"] = c
    s.data["battle"].add_hero(0, 1000, c=hero_record())            # a combatant record: real damage (resolve)
    s.data["kit"] = {int(k[1:]): v for k, v in kit.items()}
    return role, s


def test_statuses_are_kept_held_and_sent_at_the_held_level():
    from kuf2 import status
    role, s = hero_session(a7024=3, a903=1, a62=1)
    use_ability(role, s, 7024)
    assert added(s)[-1] == (7002, 3, 5, [0], 0)                   # the held level 3 (it went out at level 1)
    use_ability(role, s, 903)                                      # the Ranger's bow stance: AUTOCASTING, no chant
    assert added(s)[-1] == (6338, 1, 0xffff, [0], 0) and (903, 0) not in s.data.get("chant_statuses", {})
    for _, fn in list(s.pending):                                  # every clock runs out (600 s and more)
        fn()
    assert 6338 in status.holding(s, 0) and 7002 not in status.holding(s, 0) and ended(s) == [(0, 7002)]
    use_ability(role, s, 903)                                      # held: not sent again
    assert [a[0] for a in added(s)].count(6338) == 1
    use_ability(role, s, 62)                                       # the guard still ends with its chant
    assert added(s)[-1] == (341, 1, combat.STATUS_HOLD_S, [0], 0)
    role.handlers[game.C2S_UNCHANT](s, pkt(game.C2S_UNCHANT, obf.u32(62) + struct.pack("<H", 0)))
    assert ended(s)[-1] == (0, 341) and 341 not in status.holding(s, 0)


def test_a_timed_buff_that_outlives_its_room_is_kept_and_put_again_in_the_next():
    # a fire potion (350400010): the client casts its ability 110004 -> SELF 1000038, ALLY 1000039, Duration 1800; the
    # statuseffectinfo %Maintain rows keep them across maps (world_travel.md Gaps 2). Both are category 146 (one
    # attribute elixir at a time): on the hero his own version stays, the troops' one is for his troops (overlap)
    role, s = hero_session(a7024=3)
    c = s.data["char"]
    c["look"] = bytes(56).hex()
    use_ability(role, s, 110004)
    use_ability(role, s, 7024)                                      # 7002 for 5 s: a room's own status (DELETE)
    kept = c["timed_statuses"]
    assert set(kept) == {"1000038"} and 1000039 not in status.holding(s, 0)
    assert all(k["level"] == 1 and 1790 <= k["until"] - time.time() <= 1800 for k in kept.values())
    kept["1000039"] = {"level": 1, "until": time.time() - 1}       # one that ran out between the rooms
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["account"]["characters"] = [c]
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    next(fn for delay, fn in s.pending if delay == 1.0)()        # after the enter-cell
    put = [a for a in added(s) if a[0] in (1000038, 1000039)]
    assert len(put) == 1 and put[0][0] == 1000038 and put[0][1] == 1 and 1790 <= put[0][2] <= 1800
    assert put[0][3] == [0] and 1000038 in status.holding(s, 0)
    assert any(delay == put[0][2] for delay, _ in s.pending)       # it ends with the rest of its clock


def test_ability_statuses_reach_enemies_allies_and_npc_casters():
    role, s = hero_session(a5090=1, a5010=1, a15=1, a4=1)
    b = s.data["battle"]
    s.data["zone_troops"] = {1: {"TroopTableID": 2, "TeamNum": 1},       # LIGHT_INFANTRY
                             2: {"TroopTableID": 3225, "TeamNum": 1},    # a VEHICLE (not in 5090's row 39)
                             3: {"TroopTableID": 1000, "TeamNum": 1}}    # a worm: ACTIVESKILL10 10190 WORM_GROGGY
    for uid in (1, 2, 3):
        b.add_np(uid, 100000, 3)                                   # (a whole-troop record strikes every unit: census E6)
    use_ability(role, s, 5090, [1, 2])                             # flash grenade: ENEMY blind 6438 L2, stun 87 L3
    assert added(s) == [(6438, 2, 20, [1], 0), (87, 3, 3, [1], 0)]   # one 0x5074 per status; the vehicle gets none
    use_ability(role, s, 5010)                                     # battle fury, no targets: ALLY on the hero
    assert added(s)[2:] == [(6313, 1, 20, [0], 0), (6314, 1, 20, [0], 0)]
    use_ability(role, s, 15, [1])                                  # aimed shot: ENEMY LEADER 86 = the whole troop
    assert added(s)[-1] == (86, 1, 20, [1], 0)
    cast = obf.u16(3) + struct.pack("<H", 3) + obf.u32(10190) + bytes(7)   # the worm's own 0x505f cast of 10190
    role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, cast))
    execute(role, s, s.data["cast_serial"])
    assert added(s)[-1] == (10190, 1, 20, [3], 3)                  # SELF TROOP, cast by troop 3 at its %Skill level
    use_ability(role, s, 4, [3])                                   # the groggy attack removes group 9 (10190)
    assert (3, 10190) in ended(s)


def test_group_removal_ends_the_stances():
    role, s = hero_session(a903=1, a1029=1, a737=1, a738=1)
    use_ability(role, s, 903)
    use_ability(role, s, 1029)                                     # dagger: removes group 127
    assert ended(s) == [(0, 6338)]
    use_ability(role, s, 737)                                      # iron wall: 6201 (+ 6203), 6292, group 118
    assert [a[0] for a in added(s)[-3:]] == [6201, 6203, 6292]
    use_ability(role, s, 738)                                      # frenzy: removes 118, 6200 (+ 620202) once
    assert sorted(st for _, st in ended(s)[1:]) == [6201, 6203, 6292]
    assert [a[0] for a in added(s)[-2:]] == [6200, 620202] and [a[0] for a in added(s)].count(6200) == 1
    use_ability(role, s, 737)                                      # and back: removes 117
    assert sorted(st for _, st in ended(s)[4:]) == [6200, 620202]


def test_an_escaping_hero_takes_no_damage():
    role, s = hero_session(a14=1)
    hero = s.data["battle"].troops[0]
    s.data["battle"].add_np(5, 1000, 1, c=combat.combatant(10, 1, atk=(100, 100)))   # the attacker (real damage)
    hit = pkt(combat.C2S_HIT, hit_header(5) + struct.pack("<H", 1) + obf.u16(0) + struct.pack("<H", 1)
              + bytes([0, 0, 0, 0, 3, 0]) + struct.pack("<H", 0))
    use_ability(role, s, 14)                                       # evade: 6321 ABILITY_ESCAPE level 3, 3 s
    assert added(s)[-1] == (6321, 3, 3, [0], 0)
    role.handlers[combat.C2S_HIT](s, hit)
    assert hero["hp"] == 1000 and not [w for w in s.sent if w.proto == combat.S2C_HERO_DAMAGE]
    for delay, fn in list(s.pending):
        if delay == 3:
            fn()                                                   # the escape runs out
    role.handlers[combat.C2S_HIT](s, hit)
    assert hero["hp"] < 1000


def boss_session(troop_id):
    role, s = hero_session(a91=1, a90=1)
    s.data["spot"] = 10234                                         # Greyrock Fortress (the Mountain Troll's)
    s.data["char"].update(level=6, spot=10350, pos=[0, 0, 0])
    s.data["pools"] = game.pools_for(s.data["char"], 10234)
    zt = {"TroopID": 20001, "TroopTableID": troop_id, "PosX": 1.0, "PosZ": 2.0, "TeamNum": 1, "UnitNum": 0}
    assert game.spawn_zone_troop(s, zt)
    hit = pkt(combat.C2S_HERO_HIT, bytes(12) + bytes.fromhex("10c3") + struct.pack("<H", 1) + obf.u16(20001) + struct.pack("<H", 1)
              + bytes([0, 0, 0, 0, 3, 0]))
    return role, s, s.data["battle"].troops[20001], hit


def test_a_low_boss_can_be_executed():
    role, s, troll, hit = boss_session(134080)                     # 1 x 10,232 hp, FINISH_HP_RATE 1000, status 32
    assert troll["max"] == 10232
    for _ in range(1500):                                          # hits until the 10 % line (the Troll's DEFENCE_TYPE 98
                                                                   # MISSION_BOSS_TYPE_1 takes the hero's HERO hits x0.5)
        if sum(troll["units"]) <= 1023:
            break
        assert not [a for a in added(s) if a[0] == 32]
        role.handlers[combat.C2S_HERO_HIT](s, hit)
    assert 0 < sum(troll["units"]) <= 1023 and added(s)[-1] == (32, 1, 30000, [20001], 0xffff)
    s.data["pools"]["fp"] = 1000
    s.sent.clear()
    use_ability(role, s, 91, [20001])                              # E: the execution's start, FP 1000
    assert (20001, 32) in ended(s) and (31, 1, 99, [20001], 0) in added(s) and stat_sent(s, 82) == [0]
    s.sent.clear()
    use_ability(role, s, 90, [20001])                              # the Troll's finish group 1: 90 kills it
    protos = [w.proto for w in s.sent]
    live = next(w for w in s.sent if w.proto == combat.S2C_UNIT_LIVE)
    from kuf2.packet import Writer
    assert bytes(live.buf) == bytes(Writer(combat.S2C_UNIT_LIVE).u16(20001).u16(1).obool(False).raw(bytes(2)).buf)
    assert feed(s) == [(0, 20001)] and (20001, 31) in ended(s) and troll["units"] == [0]   # the executing hero
    assert [a[:4] for a in added(s)] == [(6410, 1, 30, [0]), (6411, 1, 30, [0])]   # FINISH_DEAD_PROC 5075


def test_a_troop_without_a_finish_rate_never_enters_the_finish_state():
    role, s, troop, hit = boss_session(700)                        # nptrooptable 700: FINISH_HP_RATE 0
    troop["units"] = [1 + i for i in range(len(troop["units"]))]
    for _ in range(50):
        role.handlers[combat.C2S_HERO_HIT](s, hit)
    assert not [a for a in added(s) if a[0] in (6, 32)]


def test_finisher_points_fill_with_kills_and_an_execution_spends_them():
    from kuf2 import status
    role, s = hero_session(a91=1)
    s.data["pools"] = game.pools_for(s.data["char"], 10352)
    assert (s.data["pools"]["fp"], s.data["pools"]["fp_max"]) == (0, 1000)   # herotable %ApSp FP_Max
    b = s.data["battle"]
    b.add_np(1, 1, 3)                                              # an enemy troop, 3 units
    three = obf.u16(1) + struct.pack("<H", 3) + b"".join(bytes([0, 0, 0, 0, 3 + k, 0]) for k in range(3))
    for _ in range(50):
        if not any(b.troops[1]["units"]):
            break
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit_header(0) + struct.pack("<H", 1) + three
                                             + struct.pack("<H", 0)))
    assert s.data["pools"]["fp"] == 3 * status.FP_PER_UNIT and stat_sent(s, 82)[-1] == 3 * status.FP_PER_UNIT
    s.data["zone_troops"] = {2: {"TroopTableID": 2, "TeamNum": game.PLAYER_TEAM}}
    b.add_np(2, 1, 1)                                              # an ally's unit falls: no points
    status.after_hit(s, 2, [0])
    assert s.data["pools"]["fp"] == 3 * status.FP_PER_UNIT
    s.data["pools"]["fp"] = 990
    assert status.gain_fp(s, 100) and s.data["pools"]["fp"] == 1000 and not status.gain_fp(s, 100)   # capped
    use_ability(role, s, 91)
    assert s.data["pools"]["fp"] == 0 and stat_sent(s, 82)[-1] == 0


def test_a_commander_kill_gives_sp_and_the_bonus_banner():
    role, s = hero_session()
    s.data["pools"] = dict(game.pools_for(s.data["char"], 10352), sp=100)     # room below the max for the kill's SP
    # zone 10303, force 24300: orc infantry 103080 (9 units), 24202 led by commander 103010, 24301 without one
    first = {"TroopID": 24202, "TroopTableID": 103080, "NPLeaderID": 103010, "ForceNum": 24300, "TeamNum": 1,
             "PosX": 1.0, "PosZ": 2.0, "UnitNum": 0}
    for zt in (first, dict(first, TroopID=24301, NPLeaderID=-100)):
        assert game.spawn_zone_troop(s, zt)
    b = s.data["battle"]
    units = len(b.troops[24202]["units"])
    b.troops[24202]["units"] = [1] * units
    b.troops[24202]["leader"] = 1                       # the commander himself (npleadertable 103010)
    wipe = obf.u16(24202) + struct.pack("<H", units) + b"".join(bytes([0, 0, 0, 0, 3 + k, 0]) for k in range(units))
    lead = obf.u16(24202) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 2, 0])      # unit index -1: the leader
    s.sent.clear()
    for body in (wipe, lead):
        for _ in range(50):
            if not status.alive(s, 24202) or (body is wipe and not any(b.troops[24202]["units"])):
                break
            role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit_header(0) + struct.pack("<H", 1) + body
                                                 + struct.pack("<H", 0)))
        if body is wipe:                                # his units down, he stands: no banner yet
            assert status.alive(s, 24202) and not any(w.proto == game.S2C_COMBAT_BONUS for w in s.sent)
    bonus = next(w for w in s.sent if w.proto == game.S2C_COMBAT_BONUS)
    assert bonus.buf[0] == 4 and struct.unpack_from("<I", bytes(bonus.buf), 9)[0] == 28      # Death_Give_Sp
    assert stat_sent(s, combat.STAT_SP)[-1] == 128 and s.data["pools"]["fp"] == 25 * units + 250
    assert units == 9 and all(a[0] != 10202 for a in added(s))          # 10202 is on no list: nothing casts it
    # (his troop's own 300127 does the leader's-death weakening, cast by the client's AI: T8.7, test_troop_hunt)


def test_passive_skills_add_their_traits_and_statuses():
    from kuf2 import hero
    c = {"id": 1, "class": 0, "level": 30, "look": bytes(56).hex(),
         "skills": {"7000": 3, "7001": 3, "7002": 3, "7003": 3, "7021": 3, "7023": 3}}
    plain = hero.stats(0, 30, hero.worn_codes(c), hero.worn_enchants(c))
    stats = game.hero_stat_values(c)
    assert stats[game.STAT_IDS["HP_MAX"]] == round(plain["HP_MAX"] + 3000)                 # 69 (from 4) at level 6 at 30
    assert stats[game.STAT_IDS["CRITICAL_REDUCE"]] == round(plain["CRITICAL_REDUCE"] + 300)  # 7003 level 3
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["account"]["characters"][0].update(c)
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    next(fn for delay, fn in s.pending if delay == 1.0)()        # after the enter-cell
    want = {(7010, 3, 0xffff, (0,)), (7012, 3, 0xffff, (0,)), (7011, 3, 0xffff, (0,)), (7014, 3, 0xffff, (0,)),
            (7013, 3, 0xffff, (0,))}
    assert {(st, lv, d, tuple(u)) for st, lv, d, u, _ in added(s)} == want and stat_sent(s, 82) == [0]
    s.sent.clear()
    t = s.data["battle"].troops[0]
    t["hp"] = 0
    game.revive_hero(s, t, (0, 0, 0))                              # the revive cleared them on the client
    assert {a[0] for a in added(s)} == {7010, 7011, 7012, 7013, 7014, 33}   # and its invincibility 33 goes on


def mission_room(spot, difficulty=0):
    """A mission room at its start: the battle and the zone troops (the 3 s after loading), session state for wins."""
    s = FieldSession({"active": {}, "done": []})
    s.data.update(spot=spot, difficulty=difficulty)
    s.data["char"] = s.data["account"]["characters"][0]
    s.state = NoSave()
    s.data["battle"].add_hero(0, 1000)
    game.spawn_zone_troops(s)
    return s


def walk(s, x, z):
    combat.hero_moved(s, (x, 0, z))                                 # what a 0x50b0 report does (game.troop_sync)


def down_all(s, uids):
    for u in uids:
        game.mission_troop_down(s, NoSave(), u)


def opened(s):
    """Props a 0x50d1 opened: {prop id} (one-record lists with the open state, game.switch_on)."""
    out = set()
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_PROP_LIST and struct.unpack_from("<H", b)[0] == 1 and read_prop(b[2:])["state"] == game.PROP_OPEN:
            out.add(obf.dec_u32(b[5:9]))
    return out


def test_held_forces_wake_where_the_hero_walks_before_the_fallback_order():
    # MISSIONS-WIRING G3 (owner Q1): Greyrock 10234 holds 31 forces along one route; the fallback brings F20010 first,
    # the bridge looters F20091 / F20092 (36-43k) wake as the hero crosses the bridge, before the troll F20080 (91k)
    s = mission_room(10234)
    troops = s.data["zone_troops"]
    assert 20000 in troops and not {20131, 20137, 20082} & set(troops)       # F20010 by the fallback, nothing else
    walk(s, 91927, 114023)                                           # the bound P1_S2_다리 코볼트 전투
    assert 20131 in troops and 20137 not in troops and 20082 not in troops    # F20092 3.3k away, F20091 8k
    walk(s, 90673, 122115)
    assert 20137 in troops and 20082 not in troops
    # a bound naming a ForceNum wakes that force wherever it stands: Lunawing Sortie I's 포스활성화_23000 (68k), 9.7k
    # from F23000
    s = mission_room(10361)
    assert 10334 not in s.data["zone_troops"]
    walk(s, 201535, 190766)
    assert 10334 in s.data["zone_troops"]


def test_numbered_phases_order_the_fallback_and_later_phases_wait():
    # G3b: Spirits Land 20347's boss F50001 [파괴의 정령] has the lowest ForceNum and came first; now after Phase1..5
    assert [w[0]["ForceNum"] for w in game.mission_waves(20347)][:12] == [50002, 50003, 50004, 50005, 50006, 50007,
                                                                         50008, 50009, 50010, 50011, 50016, 50012]
    assert game.mission_waves(20347)[-1][0]["ForceNum"] == 50001
    # Angel's Halo 10215 activates all four tablet waves (석판페이즈 1..4차); 2..4 wait, each for the one before
    s = mission_room(10215)
    troops = s.data["zone_troops"]
    first = [u for u, t in troops.items() if t.get("ForceNum") == 30000]
    assert len(first) == 6 and not {29023, 29035, 29050} & set(troops)
    walk(s, 46407, 59844)                                            # beside the 2nd wave: the 1st still stands
    assert 29023 not in troops
    down_all(s, first)
    walk(s, 46407, 59844)
    assert 29023 in troops and 29035 not in troops                   # the 2nd comes, the 3rd waits for it


def test_held_allies_join_with_their_paired_force():
    # G4: Tower of Moonlight 10233's reinforcements F13000 / F14xxx beside the tower come with the tower force F40005
    # (the nearest held force); Fort Valley 10306's elf archers F10100 with their mirror F20100
    s = mission_room(10233)
    assert 13002 not in s.data["zone_troops"]
    tower = next(w for w in s.data["waves"] if w[0]["ForceNum"] == 40005)
    game.wake(s, tower, "test")
    assert 13002 in s.data["zone_troops"] and not game.hostile(s.data["zone_troops"][13002])
    s = mission_room(10306)
    assert 10100 not in s.data["zone_troops"]
    game.wake(s, next(w for w in s.data["waves"] if w[0]["TroopID"] == 20100), "test")
    assert {10100, 10102} <= set(s.data["zone_troops"])
    assert game.mission_plan(10324, 0)["allies"] != game.mission_plan(10324, 1)["allies"]   # Hard reinforcements


def test_the_players_troops_are_handed_over_at_the_start():
    # G5: Tower of Moonlight 10233's 편입 infantry (held) at the start, its archer (active) when the table hands it
    # (HAND_LATER: the original's F2 first shows at the winged wyrms); the temple entrance 10310's 편입1P only
    s = mission_room(10233)
    assert [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)] == [10100]
    assert game.mission_plan(10233)["hand"] == (11006, 10100) and s.data["plan"]["hand"] == (10100,)
    s = mission_room(10310)
    assert [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)] == [10001]
    assert not {10002, 10003, 10004} & set(s.data["zone_troops"])  # 편입2P..4P: the other players' shares
    assert game.mission_plan(10321)["hand"] == (10011, 10012)       # Limit_Troop 2 of four elf wizards


def test_a_handed_troop_takes_the_stance_the_client_gives_the_players_own_troops():
    # owner live 2026-09-30 16:50 Grey Rock: "archers don't move to be in position to attack they just start the atack
    # from where they are". ActTroopChangeForce's last value is the troop's TROOPAITYPE: ControlCenter::ChangeForceID
    # 0x140afe700 -> Troop::SetTroopAIType 0x1407e85e0 installs that TAIBranch column (0 Offensive TAI 10000,
    # 1 Defensive 10010, 2 Hero Support 10020, 3 Hold 10030). The client gives each of the player's own troops 2
    # (SyncManager::RegisterPlayerTroops 0x140c1651a); we handed with 0, so the archers ran Offensive, shooting what
    # stood in range from where they were, while the deck troop, on Hero Support, went with the hero.
    s = mission_room(10234)                                          # Grey Rock: the archers, at the start
    assert [a[2:] for a in acts(s, game.ACT_CHANGE_FORCE)] == [[10073, game.MY_SLOT, game.TROOPAITYPE_HEROSUPPORT]]
    s = mission_room(10233)                                          # Tower: the infantry at the start, the archers
    game.hand_troop(s, 11006)                                        # at the winged wyrms (the director's "hand")
    assert [a[2:] for a in acts(s, game.ACT_CHANGE_FORCE)] == [[10100, game.MY_SLOT, game.TROOPAITYPE_HEROSUPPORT],
                                                               [11006, game.MY_SLOT, game.TROOPAITYPE_HEROSUPPORT]]


def test_the_clients_force_change_ack_counts_the_troop_as_the_players():
    # C2S 0x50e6 (builder 0x140f08560; ControlCenter::ChangeForceID 0x140afe8a7 when the new force is mine;
    # planning/client/room_troops.md gap 2): T2[(flag != 0) + 2 * b1], coded u16 uid. Live bodies (19/13, all TRUE):
    # 5b96d7 = 10100, df03a1 = 11006. No reply (0x50e7's handler is `ret 0`)
    role = game.make(NoSave(), 0)
    s = mission_room(10233)
    s.sent.clear()
    assert s.data["plan"]["hand"] == (10100,)
    for body in ("5b96d7", "df03a1", "df03a1"):                      # 11006 twice: counted once
        role.handlers[0x50e6](s, pkt(0x50e6, bytes.fromhex(body)))
    assert s.data["plan"]["hand"] == (10100, 11006) and s.sent == []
    uid = enc_uid(10073)
    role.handlers[0x50e6](s, pkt(0x50e6, bytes([T2[(0 + 2 * uid[0]) & 0xff]]) + uid))   # FALSE: logged only
    role.handlers[0x50e6](s, pkt(0x50e6, b"\x5b"))                                      # short: nothing
    assert s.data["plan"]["hand"] == (10100, 11006)


def test_barriers_open_with_their_force_or_when_the_hero_comes_near():
    # G6 (owner Q4): Fort Valley 10306's collapsed walls (type 48) open as their forces wake ("They're coming through
    # the collapsed castle walls"); its fence gate 10000 when the start force F20000 beside it is down
    s = mission_room(10306)
    assert not {20000, 20001, 10000} & opened(s)
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20600), "test")
    assert 20000 in opened(s) and 20001 not in opened(s)
    down_all(s, [20000, 20001, 20002])
    assert 10000 in opened(s)
    assert game.prop_refusal(s, 10000) == "mission trigger only"   # opened, still not the player's to use
    # Grey Fog 10358's curtain 10532 beside F22000: open when the hero comes within 2500
    s = mission_room(10358)
    walk(s, 282374 + 3000, 182258)
    assert 10532 not in opened(s)
    walk(s, 282374 + 2000, 182258)
    assert 10532 in opened(s)


def test_grey_rock_starts_at_its_opening_scene():
    # owner live 2026-09-28 "it throw me to the wrong place at the start of the mission": the zone start point is 16 000
    # units from P1_S1_영웅 위치; the hero goes there (0x50c0) and Glen, Thompson and the troop pairs spawn at theirs
    s = mission_room(10234)
    move = [w for w in s.sent if w.proto == game.S2C_TROOP_BACK]
    assert move and struct.unpack_from("<H", bytes(move[-1].buf), 7)[0] == 0          # 7 packed position bytes, u16 troop
    assert s.data["hero_pos"][0] == 98488 and s.data["hero_pos"][2] == 90014
    glen = s.data["zone_troops"][10000]
    assert (round(glen["PosX"]), round(glen["PosZ"])) == (98796, 90122)
    assert not [w for w in mission_room(10358).sent if w.proto == game.S2C_TROOP_BACK]   # no bound: left alone


def test_hidden_invisible_walls_open_like_barriers():
    # Tower of Moonlight 10233's 10015 (type 232, never shown, its collision up) stopped the hero live 2026-09-28; it
    # opens (shown, state 2) as he comes near. Grey Fog's 10528 among its barrels keeps the barrel rule
    s = mission_room(10233)
    assert 10015 in s.data["barriers"]
    walk(s, 39383 + 3000, 109463)
    assert 10015 not in opened(s)
    walk(s, 39383 + 2000, 109463)
    assert 10015 in opened(s)
    assert 10528 not in mission_room(10358).data["barriers"]
    # Grey Rock 10234's transparent rectangle 20085 (type 68) stopped the hero at (84357, 128564) live
    s = mission_room(10234)
    assert 20085 in s.data["barriers"]
    walk(s, 83893, 129033 + 2000)
    assert 20085 in opened(s)


def test_reaching_the_destination_wins():
    # G11: Lunawing Sortie I 10361 "Move to New Hampton": the hero entering 목적지 wins with every enemy standing
    s = mission_room(10361)
    walk(s, 191505, 272969 + 3000)
    assert not s.data.get("mission_won")
    walk(s, 191505, 272969 + 2000)
    assert s.data.get("mission_won") and any(w.proto == game.S2C_MISSION_LEAVE for w in s.sent)   # no window (B2)


def test_the_panel_table_names_the_blocks_matching_cannot_pick():
    # G12: the camps' own blocks, the Death Woods blocks, Vandall Valley's failure rows, New Hampton Castle's headings
    assert game.mission_text(10345) == (30000, ((30010, (30030, 30040)), (30020, (30050, 30060))))
    assert game.mission_text(10346)[1][0][0] == 530100 and game.mission_text(10331)[1][0][0] == 710
    assert game.mission_text(10312)[0] == 1600 and game.mission_text(10323)[0] == 1700
    assert game.mission_text(20318)[1][1] == (630, (640, 641, 651))
    assert game.mission_text(10235) == (None, ((200, (210, 220, 230, 240)), (300, (310,))))
    assert game.mission_text(20920) is None



def test_a_leader_only_enemy_formation_can_fall():
    # 10233 troop 20014: 133050 with UNIT_COUNT 0 / UnitNum 0, led by 133040 (npleadertable HP_BASEUNIT 1268); with no
    # unit it could never fall and the Tower of Moonlight could never be won
    s = FieldSession({"active": {}, "done": []})
    s.data["spot"] = 10233
    s.data["battle"] = combat.Battle()
    from kuf2 import zone
    zt = next(t for t in zone.for_spot(10233)["NPCTroopInfoData"] if t["TroopID"] == 20014)
    assert game.spawn_zone_troop(s, zt)
    troop = s.data["battle"].troops[20014]
    assert troop["units"] == [] and troop["leader"] == 1268       # his leader carries it (npleadertable 133040)
    downs = []
    s.data["battle"].add_np(1, 100, 1, c=combat.np_combatant(133170, 0))          # an ally infantry unit hits him
    for _ in range(3):                                  # any hit lands on him: he is all there is
        combat.apply_hits(s, [(20014, [0])], game.send_troop_hp, lambda s, uid: downs.append(uid), attacker=1,
                          attack={"kill": True})
    assert troop["leader"] == 0 and downs == [20014]


def test_the_allies_melee_blows_from_the_hit_reaction_sync_land():
    # live 2026-09-29 01:55, Tower: the player's troop 10100 on the Encablossian 20008, three 0x5056 records (action
    # 69 at +3, units 0, 0, 1); the client never sends these blows as 0x5053 in a solo room (owner: "they keep there
    # fighting for ever but they neveer kill"). An archer's record is its melee blow and lands too; the hero's
    # (+3 = 0xffff, his 0x5066 repeats it) does not (planning/client/combat.md)
    blows = bytes.fromhex("1f1000450096d7cf2c00b0f30003c0" "1f1000450096d7cf2c00b4a50103c0" "1f1000450096d7cf2c009bef0104c0")
    s = mission_room(10233)
    foe = s.data["battle"].troops[20008]
    before = list(foe["units"])
    combat.on_hit_sync(s, pkt(combat.C2S_HIT_SYNC, blows), game.send_troop_hp)
    assert sum(foe["units"]) < sum(before) and foe["units"][:2] == [0, 0]   # 85-hp units (a blow on a fallen
                                                                            # one lands on a living one)
    hero, archer = bytearray(blows[:15]), bytearray(blows[:15])
    hero[5:7], hero[3:5] = enc_uid(0), bytes([0xff, 0xff])
    archer[5:7], archer[3:5] = enc_uid(11006), (72).to_bytes(2, "little")
    after = list(foe["units"])
    combat.on_hit_sync(s, pkt(combat.C2S_HIT_SYNC, bytes(hero)), game.send_troop_hp)
    assert foe["units"] == after
    combat.on_hit_sync(s, pkt(combat.C2S_HIT_SYNC, bytes(archer)), game.send_troop_hp)
    assert sum(foe["units"]) < sum(after)


def test_a_troops_orders_wait_until_the_client_has_bound_it():
    # live 2026-09-29 02:27:12: F20100 spawned at .556, its marches at .559, the client's binds (0x50ab) at .569-.58;
    # six troops never moved. An order waits for the troop's 0x50ab once the client reports binds.
    from kuf2 import director
    s = mission_room(10233)
    for u in list(s.data["zone_troops"]):
        game.troop_bound(s, u)
    game.spawn_force(s, 20100)
    director.march(s, 20100, 18023)
    assert not [a for a in acts(s, director.ACT_MOVE_TO_AREA) if a[2] == 20101]
    game.troop_bound(s, 20101)
    assert [a[2] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[2] == 20101] == [20101]


def test_the_heros_stop_record_says_he_stands():
    # planning/client/room_troops.md: 0x50b0 reports a troop at rest (flags & 0x7f == 0) once, then goes silent
    q, p15 = obf.pos_xz(51000, 82000)

    def body(flags):
        return (struct.pack("<H", 1) + bytes([flags, 0]) + struct.pack("<Hh", 0, 0) + q + struct.pack("<h", 0)
                + bytes([p15, 0]))
    seen = {}
    assert game.sync_positions(body(0x00), seen)[0][::2] == (51000, 82000) and seen == {0: 0}
    s = mission_room(10233)
    role = game.make(NoSave(), 0)
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, body(0x00)))
    assert s.data["hero_pos"][::2] == (51000, 82000)


def test_a_batch_of_hero_skills_is_checked_as_a_whole():
    # live world_20260928_025527:1997 (0x1760): Aldric (class 0, level 30) chose nine skills at once and the server,
    # checking them one by one in id order, refused the batch; the client checks the batch as a whole
    from kuf2 import skills
    body = bytes.fromhex("09000a0000000273000000027700000002840000000289000000029800000002581b0000035a1b0000036f1b000003")
    wanted = [struct.unpack_from("<IB", body, 2 + 5 * i) for i in range(9)]
    c = {"class": 0, "level": 30, "skills": {}}
    assert skills.learn(c, wanted) == 0
    assert {int(k): v for k, v in c["skills"].items()} == dict(wanted)


def test_an_attack_zero_troop_deals_nothing():
    # the designers' "attack x0" allies (133010: Glen's and Thompson's carriers, Tower's camp formations; DESIGNER-NOTES
    # finding 7) are decoration: ATTACK 0 must stay 0, not the resolver's floor of 1; a real attack still floors at 1
    ally, wyrm = combat.np_combatant(133010, 0), combat.np_combatant(133080, 1)
    assert ally["atk"][combat.PHYSICAL] == (0.0, 0.0)
    swing = combat.hit_attack(ally, None)
    assert combat.resolve(ally, wyrm, swing, rng=Even()) == 0
    archers = combat.np_combatant(133120, 0)
    assert combat.resolve(archers, wyrm, combat.hit_attack(archers, combat.VOLLEY_ACTION), rng=Even()) >= 1


def kill_room(level=10):
    """The hero (level 10: 103080's own level, so its kill is worth exp), an ally zone troop 11000 (Tower's CPU
    infantry 133170, team 0, not the player's) and three orc infantry troops 24301-24303 (103080, 9 units of 1 hp)."""
    role, s = hero_session()
    s.data["char"].update(level=level, exp=0)
    s.data["pools"] = game.pools_for(s.data["char"], 10352)
    ally = {"TroopID": 11000, "TroopTableID": 133170, "ForceNum": 11000, "TeamNum": 0, "PosX": 1.0, "PosZ": 2.0,
            "UnitNum": 0}
    foe = {"TroopID": 24301, "TroopTableID": 103080, "NPLeaderID": -100, "ForceNum": 24300, "TeamNum": 1,
           "PosX": 1.0, "PosZ": 2.0, "UnitNum": 0}
    for zt in (ally, foe, dict(foe, TroopID=24302), dict(foe, TroopID=24303)):
        assert game.spawn_zone_troop(s, zt)
    for uid in (24301, 24302, 24303):
        s.data["battle"].troops[uid]["units"] = [1] * 9
    return role, s


def wipe(role, s, uid, by):
    """0x5053 reports of troop `by` on every unit of troop uid until it falls."""
    for _ in range(50):
        if not status.alive(s, uid):
            return
        body = obf.u16(uid) + struct.pack("<H", 9) + b"".join(bytes([0, 0, 0, 0, 3 + k, 0]) for k in range(9))
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit_header(by) + struct.pack("<H", 1) + body
                                             + struct.pack("<H", 0)))
    raise AssertionError(f"troop {uid} still stands")


def feed(s):
    """(killer, victim) of the 0x50fd sent."""
    return [struct.unpack_from("<HH", bytes(w.buf)) for w in s.sent if w.proto == game.S2C_KILL_FEED]


def test_the_kill_feed_names_the_troop_whose_hit_felled_it_and_credits_follow_the_players_fight():
    # B7 / I9: the 03:55 run's 39 kills all read "killer 0" (game.py wrote 0) while the hero never struck. The feed
    # names the troop whose hit felled the victim. Kill exp, the banner and finisher points follow the client's own
    # finisher-orb test (unit death 0x140a0af10 -> 0x140d0b450: the dying unit's troop lists the hero's troop or another
    # of the player's): a troop the player's side never fought gives nothing when an ally fells it
    role, s = kill_room()
    s.sent.clear()
    wipe(role, s, 24301, 11000)                         # an ally alone (Glen's forces at Tower): named, no credit
    assert feed(s) == [(11000, 24301)]
    assert not any(w.proto == game.S2C_COMBAT_BONUS for w in s.sent)
    assert s.data["pools"]["fp"] == 0 and s.data["char"]["exp"] == 0
    s.sent.clear()
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, enc_uid(0) + bytes([1]) + enc_uid(24302)))
    role.handlers[combat.C2S_ENGAGE_CLEAR](s, pkt(combat.C2S_ENGAGE_CLEAR, struct.pack("<H", 24302)))
    wipe(role, s, 24302, 11000)                         # the hero fought it (a hate list outlives the engagement):
                                                        # the ally's kill is his too
    assert feed(s) == [(11000, 24302)]
    bonus = next(w for w in s.sent if w.proto == game.S2C_COMBAT_BONUS)
    exp = game.kill_exp(s.data["char"], 103080)
    assert bonus.buf[0] == 3 and struct.unpack_from("<I", bytes(bonus.buf), 1)[0] == exp > 0
    assert s.data["pools"]["fp"] == 9 * status.FP_PER_UNIT
    s.sent.clear()
    s.data["plan"] = {"hand": (11000,)}                 # the troop handed to the player: its kills are his
    wipe(role, s, 24303, 11000)
    assert feed(s) == [(11000, 24303)] and s.data["pools"]["fp"] == 18 * status.FP_PER_UNIT
    assert any(w.proto == game.S2C_COMBAT_BONUS for w in s.sent)


def test_the_heros_fall_names_his_killer_in_the_kill_feed():
    # the chat battle log (0x140dddb20) prints text 0x2726 "The hero is dead." only for a 0x50fd whose victim is the
    # local hero and whose killer is a troop the client knows (the handler 0x140d07920 drops an unknown killer)
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"].add_hero(0, 2)
    s.data["battle"].add_np(1, 1072, 19, c=combat.np_combatant(2))
    target = bytes([obf.T2[0], obf.T1[0]]) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0])
    for _ in range(3):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit_header(1) + struct.pack("<H", 1) + target
                                             + struct.pack("<H", 0)))
    assert feed(s) == [(1, 0)]


def test_same_effect_statuses_do_not_stack_the_stronger_applies():
    # HANGAME-DEVNOTES §3.2 [O 2010]: a buff "does not stack with other abilities of the same effect; only the stronger
    # one applies". Same effect = statuseffectinfo %Basic Category (with %Category OverlapCount, 1 on 106 of 107
    # categories); the stronger = the higher CategoryLevel (ours: at equal level the newer replaces the older)
    s = FieldSession({"active": {}, "done": []})
    held = lambda uid: combat.held_levels(s, uid)
    status.apply(s, [7], 6528, 1)                       # scorpion war drum: category 8, level 0, ALL +10 %
    status.apply(s, [7], 919992, 1)                     # orc shout III: category 8, level 3, ALL +30 %
    assert held(7) == {919992: 1} and (7, 6528) in ended(s)
    assert combat.status_bonus(held(7), "ATTACK_PHYSICAL") == (30.0, 0.0)          # not 40
    s.sent.clear()
    status.apply(s, [7], 6528, 1)                       # weaker: refused, nothing sent
    assert held(7) == {919992: 1} and not added(s)
    status.apply(s, [7], 2000418, 8)                    # the archers' rapid fire has no category: it adds
    assert held(7) == {919992: 1, 2000418: 8}
    assert combat.status_bonus(held(7), "ATTACK_PHYSICAL") == (100.0, 1.0)
    status.apply(s, [8], 58, 1)                         # speed reload 2 (category 7, level 2, +10 %) ...
    status.apply(s, [8], 57, 1)                         # ... keeps out speed reload 1 (level 1, +5 %)
    assert held(8) == {58: 1} and combat.status_bonus(held(8), "ATTACK_PHYSICAL", leader=True) == (10.0, 0.0)
    status.apply(s, [9], 70, 1)                         # finish buffs 70 / 72: category 27, both level 5
    status.apply(s, [9], 72, 1)
    assert held(9) == {72: 1} and (9, 70) in ended(s)
    for st in (80, 81, 82):                             # Test_D / E / F: category 106, OverlapCount 3
        status.apply(s, [10], st, 1)
    assert set(held(10)) == {80, 81, 82}


def sync_body(*records):
    """A 0x50b0 body of (uid, flags) records (planning/client/room_troops.md §2.2), no leader block, formation 1."""
    body = struct.pack("<H", len(records))
    for uid, flags in records:
        q, p15 = obf.pos_xz(51000, 82000)
        body += bytes([flags, 0]) + struct.pack("<Hh", uid, 440) + q + struct.pack("<h", 0) + bytes([p15, 1])
    return body


@pytest.mark.parametrize("attacker, kind, target, state, want", [
    (157, "MOUNTED", 154, "FRONTAL", 0.1),    # the counter chart: a spear square (230 -> 213) takes MOUNTED x0.1
    (157, "MOUNTED", 154, "IDLE", 1.0),
    (154, "DENSE", 157, "CHARGE", 6.0),       # charging cavalry (205 -> 208) takes DENSE x6
    (154, "DENSE", 157, "IDLE", 3.0),
    (157, "MOUNTED", 153, "IDLE", 1.0),       # human infantry (162) idle / moving (202) / engaged (222): MOUNTED 1 / 2 / 3
    (157, "MOUNTED", 153, "MOVE", 2.0),
    (157, "MOUNTED", 153, "MELEE", 3.0),
    (157, "MOUNTED", 153, "FRONTAL", 1.0),    # light infantry has no formation row: its own
])
def test_the_counter_charts_state_rows(attacker, kind, target, state, want):
    assert combat.synastry(combat.np_combatant(attacker, 0), combat.np_combatant(target, 1), kind, state) == want


def test_the_troop_state_reports_pick_the_synastry_row(monkeypatch):
    # 0x50b0's flags & 0x7f is the client's own state class (0x14158e8a0 over the TROOP_BEHAVIOR enum, pointer table
    # 0x1434a7120): 0 READY..STORMRIDER_READY, 1 MOVE..CHASE_*, 2 MELEE*, 3 ATTACK_RANGE*, 4 ATTACK_CHARGE / MOVE_CHARGE /
    # CHASE_CHARGE (or troop +0x451), 5 the FRONTAL behaviours, 7 FORCED_RETURN: the %StateMapper columns in order
    monkeypatch.setattr(combat, "random", Even())
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    b = s.data["battle"]
    b.add_np(11004, 392, 42, c=combat.np_combatant(133140, 0))
    b.add_np(10100, 10 ** 6, 1, c=combat.np_combatant(133270, 1))       # human infantry 162
    b.add_np(20001, 10 ** 6, 1, c=combat.np_combatant(154, 1))          # human spearmen 230
    b.add_np(20002, 10 ** 6, 1, c=combat.np_combatant(157, 1))          # human cavalry 205
    sync = lambda *r: role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body(*r)))
    assert [combat.state_of(s, u) for u in (10100, 20001, 20002)] == ["IDLE"] * 3
    sync((10100, 1), (20001, 5), (20002, 4))
    assert [combat.state_of(s, u) for u in (10100, 20001, 20002)] == ["MOVE", "FRONTAL", "CHARGE"]
    sync((10100, 2), (20001, 3), (20002, 7))
    assert [combat.state_of(s, u) for u in (10100, 20001, 20002)] == ["MELEE", "RANGE_ATTACK", "RETURN"]
    sync((10100, 0))                                    # at rest, reported once ...
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, enc_uid(20001) + bytes([1]) + enc_uid(10100)))
    assert combat.state_of(s, 10100) == "MELEE"          # ... an engagement since is fresher (ours)
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, enc_uid(20001) + bytes([0]) + enc_uid(10100)))
    assert combat.state_of(s, 10100) == "IDLE"
    archers = combat.np_combatant(133140, 0)
    arrow = combat.hit_attack(archers, combat.VOLLEY_ACTION)

    def volley(uid):
        before = b.troops[uid]["units"][0]
        body = enc_uid(11004) + struct.pack("<H", 1) + enc_uid(uid) + bytes([127 * 2])
        role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
        return before - b.troops[uid]["units"][0]
    for cls, state in ((0, "IDLE"), (5, "FRONTAL")):
        sync((20001, cls))
        want = 42 * combat.resolve(archers, b.troops[20001]["c"], arrow, rng=Even(), state=state)
        assert volley(20001) == want
    assert combat.synastry(archers, b.troops[20001]["c"], "RANGE", "FRONTAL") == 2.0   # the square's row 213


def test_a_charge_report_puts_its_source_in_the_charge_row():
    # a non-volley 0x505a comes from Charge::Execute (0x1408c1300): its source troop is charging (ours: until its next
    # 0x50b0 record says otherwise)
    role = game.make(NoSave(), 0)
    s = FieldSession({"active": {}, "done": []})
    b = s.data["battle"]
    b.add_np(20002, 10 ** 6, 20, c=combat.np_combatant(157, 1))         # human cavalry: MOUNTED, not ranged
    b.add_np(10100, 10 ** 6, 20, c=combat.np_combatant(133270, 0))
    body = enc_uid(20002) + struct.pack("<H", 1) + enc_uid(10100) + bytes([127 * 2])
    role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
    assert combat.state_of(s, 20002) == "CHARGE" and combat.state_of(s, 10100) == "IDLE"
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body((20002, 1))))
    assert combat.state_of(s, 20002) == "MOVE"

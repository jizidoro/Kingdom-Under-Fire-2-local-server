"""The troop rules the hunt of 2026-09-30 / 10-01 settled (planning/rules/TROOPS.md), each expectation recomputed from the
shipped tables the way the client computes it, or read off the original's footage (the tape):
- T4.6: the cheer-up price is GetTroopCheerUpMoney 0x140d99f20's: per troop (int)(grade x (rarity x (LevelTreatment[level]
  x missing AP))) in float32, the barrack loader's LevelTreatment row index 1 (ID 2; 0x14192f910 seeks row 1, where the
  BarrackLimitExp parser 0x14192fdc0 seeks row 0), no discount (the term is x 0.0); part 4 f_00745-f_00747: the Lv 7
  Drafted Infantry at 45 / 100 AP costs 50 gold, the lineup 66.
- T12.4 / T12.5 (N5): a promoted troop keeps its level and exp and refills its AP: part 5 f_00598 -> f_00600 (Drafted
  Infantry Lv 9, AP bar 60 % -> Long Swordsman Lv 9, AP bar full) and the next window, 10211 S at f_00921: the Long
  Swordsman Lv 10 "423 XP" = 353 - 352 + 422, the exp kept at the promotion (a reset would have shown 553).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import tables, troops
from test_troop_rules import world_session, wpkt


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def client_cheer(tid, level, missing):
    """GetTroopCheerUpMoney 0x140d99f20 for one troop, as its SSE code runs: xmm7 = LevelTreatment[level] x missing,
    xmm6 = rarity constant x xmm7, xmm0 = grade constant x xmm6, cvttss2si; LevelTreatment from the parser's row
    index 1 (0 above level 50: 0x14192f740)."""
    b = tables.sections("barrack")
    r = troops.troop_row(tid)
    lt = f32(float(b["LevelTreatment"][1][f"LV_{level}"])) if 1 <= level <= 50 else 0.0
    rc = f32(float(next(x["TreatmentConstant"] for x in b["TreatmentConstant"] if x["TroopRarity"] == r["TroopRarity"])))
    gc = f32(float(next(x["TreatmentConstant_Grade"] for x in b["TreatmentConstant"]
                        if x["TroopGrade"] == r["TroopGrade"])))
    return int(f32(gc * f32(rc * f32(lt * missing))))


def player_troops():
    return [int(r["TROOP_ID"]) for r in tables.sections("trooptable")["Contents"]
            if r.get("MAX_LEVEL", "").isdigit() and r.get("ActingPower", "").isdigit()
            and r.get("TroopRarity", "").startswith("RARITY") and r.get("TroopGrade", "").startswith("GRADE")]


# --- T4.6: the cheer-up price ---

def test_the_tapes_cheer_up_prices():
    # part 4 _0FD8aKDxto f_00745 / f_00746: the Drafted Infantry Lv 7 (troop 100) at 45 / 100 AP, "Recovery Cost: 50";
    # row 0 of LevelTreatment (1.0 at Lv 7) would have asked 38
    t = {"uid": 1, "id": 100, "level": 7, "ap": 45}
    assert troops.cheer_cost(t) == (50, 100)
    assert client_cheer(100, 7, 55) == 50


@pytest.mark.parametrize("tid", player_troops()[::37])
def test_every_troops_cheer_price_is_the_clients_float_product(tid):
    top = int(troops.troop_row(tid)["ActingPower"])
    for level in (1, 7, 10, 20, 30):
        for ap in (0, 1, 45, 70, 99, top):
            t = {"uid": 1, "id": tid, "level": level, "ap": ap}
            assert troops.cheer_cost(t) == (client_cheer(tid, level, max(0, top - ap)), top), (tid, level, ap)


def test_encouraging_the_lineup_charges_the_sum_of_the_troops_prices():
    # 0x135a (the lineup, slots 1..8 of the main deck): the client sums each troop's truncated price (mode 1 of
    # 0x140d99f20); the server charges the same and refills them
    role, s = world_session()
    c = s.data["char"]
    c.update(level=10, gold=1000)
    a, _ = troops.grant(c, 1)                                   # troop 100
    b, _ = troops.grant(c, 1)
    a.update(level=7, ap=45)
    b.update(level=2, ap=70)
    slots = troops.lineup(c)["slots"]
    slots[1], slots[2] = a["uid"], b["uid"]
    role.handlers[0x135a](s, wpkt(0x135a, b""))
    price = client_cheer(100, 7, 55) + client_cheer(100, 2, 30)
    assert c["gold"] == 1000 - price and a["ap"] == b["ap"] == 100
    assert bytes(s.sent[-1].buf)[:2] == b"\0\0"


# --- T12.4 / T12.5 (N5): a promotion keeps the level and the exp, and refills the AP ---

def test_a_promoted_troop_keeps_its_level_and_exp_as_the_next_window_shows():
    # part 5 m-CmO76YaoA f_00598 -> f_00600: Drafted Infantry Lv 9 -> Long Swordsman Lv 9 (the preview and the card), the
    # card's AP bar (TroopListItem_biggest mc_ap = currentAp / maxAp) 137 / 228 px -> full; f_00921, 10211 S: Troop_Exp
    # 553 (Barracks Saved EXP 138 = floor(553 / 4)), the Long Swordsman "Lv. 10 423 XP" = need(9) 353 - 352 + need(10)
    # 423 - 1: the 352 the infantry held after 10306 (f_00481: Lv 9 353 = 290 - 289 + 352) survived the promotion
    import struct as st
    from kuf2 import game
    role, s = world_session()
    c = s.data["char"]
    c.update(level=11, gold=100000, bag=[{"code": 354000000, "slot": 1, "count": 10, "serial": 92, "bound": True},
                                         {"code": 354100000, "slot": 2, "count": 10, "serial": 93, "bound": True}])
    t, _ = troops.grant(c, 1)
    t.update(level=9, exp=352, ap=60)
    role.handlers[troops.C2S_PROMOTE](s, wpkt(troops.C2S_PROMOTE, st.pack("<QQIQ", t["uid"], 0, 1000000, 0)))
    reply = bytes(next(w for w in s.sent if w.proto == troops.S2C_PROMOTE).buf)
    assert reply[:3] == b"\0\0\x09"                              # the reply's level byte (0x140e40800 rebuilds from it)
    assert (t["id"], t["level"], t["exp"], t["ap"]) == (1100111, 9, 352, 100)
    row = game.reward_row(10211, 0, game.GRADES.index("S"))
    amount = game.troop_mission_exp(10211, 0, row, 0)
    assert amount == 553 and troops.barracks_share(amount) == 138
    assert troops.gain_exp(c, t, amount) == (9, 423) and (t["level"], t["exp"]) == (10, 422)


# --- T14.4: a deck troop revived in place gets its passives back (the revive itself: MISSIONS I5, 8176c08) ---

def test_a_revived_deck_troop_regains_its_passives_and_the_revive_invincibility(monkeypatch):
    # 0x505c dead FALSE clears the troop's statuses on the client (0x1407e3900 -> 0x140bed610), as the hero's revive
    # does (status.revived puts his passives back): the deck troop's passives' held statuses and the lineup's set
    # status go on again (status.troop_revived), then COMMON_INVINCIBLE_TROOP 34
    from kuf2 import game, status
    from test_army import army, entered
    c, ts = army(1)
    role, s = entered(10235, c)
    monkeypatch.setattr(troops, "passives", lambda c, t: {70148: 1})       # a held passive: its SELF status 701480
    b = s.data["battle"].troops[1]
    b["units"] = [0] * len(b["units"])
    s.sent.clear()
    game.revive_troop(s, 1, b)
    assert 701480 in status.holding(s, 1) and 34 in status.holding(s, 1)
    assert all(hp == b["unit_max"] for hp in b["units"])


def test_a_troops_revive_price_is_its_grade_and_rarity_row():
    # RevivalCostSetting 0x1406902f0 -> 0x140690040 for a troop that is no hero: ItemCurrencyInfoHolder +0x80 maps
    # (TroopGrade, TroopRarity) to a Resurrect index (item_currency %Troop_Resurrect), whose %Base Resurrect row is the
    # Cubic the confirm box asks (troop +0x7c8's trooptable row, 0x140c5b7f0)
    from kuf2 import game, items
    rows = tables.sections("item_currency")["Troop_Resurrect"]
    for tid in player_troops()[::23]:
        r = troops.troop_row(tid)
        index = next(int(x["Index"]) for x in rows if (x["TroopGrade"], x["TroopRarity"]) ==
                     (r["TroopGrade"], r["TroopRarity"]))
        assert game.troop_revive_cost({"id": tid}) == items.currency("Resurrect", index)
    assert game.troop_revive_cost({"id": 100}) == 10                  # GRADE1 RARITY1 -> index 1: 10 Cubic


# --- T8.7 / T8.8: the leader's death weakens his troop through its own list ---

def test_a_leaders_troop_carries_300127_and_its_cast_takes_his_buffs_and_weakens_his_allies():
    # 300127 NP리더버프_제거스킬 (ACTIVESKILL on 2,191 nptrooptable rows; orc infantry 103080's first): %AiCondition
    # OneTimeEvent DEATH_SELF_LEADER, so the client's AI casts it when the leader falls; its execute removes status group
    # 137 (the leaders' buffs 300000-300107) and puts 300110 (HP_MAX -50, ATTACK_PHYSICAL -50 x level, 30 s) on ALLY ALL.
    # 10202 NPT_LEADER_DEATH has the same event but sits on no list: nothing casts it
    from kuf2 import combat, game, status
    from test_battle import hero_session
    role, s = hero_session()
    zt = {"TroopID": 24202, "TroopTableID": 103080, "NPLeaderID": 103010, "ForceNum": 24300, "TeamNum": 1,
          "PosX": 1.0, "PosZ": 2.0, "UnitNum": 0}
    for z in (zt, dict(zt, TroopID=24301, NPLeaderID=-100)):
        assert game.spawn_zone_troop(s, z)
    rec = s.data["battle"].troops[24202]["c"]
    actives, _ = game.cell_abilities(rec, s.data["battle"].troops[24202].get("leader_c"), 24202)
    assert (300127, 1) in actives
    status.apply(s, [24202], 300000, 1, 24202)                # a leader's buff (group 137) on his troop
    s.data["battle"].troops[24202]["leader"] = 0              # the leader fell
    s.sent.clear()
    status.on_execute(s, 91, 300127, 24202, [(24202, [0]), (24301, [0])], game.send_troop_hp)
    assert 300000 not in status.holding(s, 24202)
    assert 300110 in status.holding(s, 24202) and 300110 in status.holding(s, 24301)
    assert not any(10202 in status.holding(s, u) for u in (24202, 24301))
    sources = [r for name in ("nptrooptable", "npleadertable") for r in tables.sections(name)["Skill"]]
    assert not any("10202" == v for r in sources for k, v in r.items() if k.startswith("ACTIVESKILL"))


# --- T9.3: a zone troop's units are its table's UNIT_COUNT; the zone's UnitNum sizes only a 0-unit row ---

def test_a_zone_troop_takes_its_tables_unit_count_and_the_zone_size_only_for_a_zero_row():
    # the client's own zone spawn (LoadInitPlayerData 0x140d08120 and ScriptTroop::RequestTroop 0x140b95540 pass no
    # count to MakeSpawnNPTroopGenInfo 0x140f67fb0 -> 0x140f6c780): units = nptrooptable UNIT_COUNT (row +0xe8, the
    # Contents parser 0x1418bd92a / 0x1418bdee3) when it is 1 or more, else the zone entry's UnitNum (+0x40, its name at
    # the reader 0x1419c9139). Flamegrass 10303's orc infantry (9 in the table; 12 / 30 / 4 / 16 in the zone) are 9;
    # Tower's wyrm-fight archers 133120 (0 in the table) the zone's 42 (the tape's 98,700 = 42 x 2,350)
    from kuf2 import game, zone
    from test_battle import hero_session
    role, s = hero_session()
    for troop, units in ((103080, 12), (103080, 30), (103080, 4), (133120, 42), (135300, 48)):
        zt = {"TroopID": 24000 + units, "TroopTableID": troop, "PosX": 1.0, "PosZ": 2.0, "TeamNum": 1, "UnitNum": units,
              "NPLeaderID": -100}
        assert game.spawn_zone_troop(s, zt)
        table = int(zone.np_troop(troop)["UNIT_COUNT"])
        assert len(s.data["battle"].troops[24000 + units]["units"]) == (table if table >= 1 else units)


# --- T1.14: a troop's units regenerate their floored HP_RECOVERY every 3 s ---

def test_a_deck_troops_units_regenerate_their_floored_hp_recovery_every_3_s():
    # the tape, part 2 qeeQjhgO8ss 2 fps frames 2331-2356 s (38:51-39:16, Grey Rock): the F1 Drafted Infantry ★1 Lv 6
    # (troop 100: HP_RECOVERY 1 + LvHPRecovery 0.9 x 5 = 5.5) climbs 6,282 -> 6,332 -> 6,382 ... -> 6,661, +50 on the
    # 3 s beat (2334.5, 2337.5 ... 2355), the hero's own SP beat: each of its 10 units + floor(5.5) = 5, the fraction
    # dropped as the unit HP's (T1.3); the handed archers (134060, HP_RECOVERY 0) stay at 913 the while
    from kuf2 import combat, game
    from test_army import army, entered
    c, ts = army(1)
    ts[0]["level"] = 6
    role, s = entered(10234, c)
    b = s.data["battle"].troops[1]
    top = b["unit_max"]
    assert top == 883 and len(b["units"]) == 10 and b["c"]["hp_rec"] == 5.5
    b["units"] = [top - 100] * 9 + [0]
    s.pending.clear()
    s.sent.clear()
    combat.start_np_regen(s, 1)
    delay, tick = s.pending.pop()
    assert delay == combat.SP_TICK_S == 3.0
    tick()
    assert b["units"] == [top - 95] * 9 + [0]                 # the fallen unit stays down
    assert [w for w in s.sent if w.proto == game.S2C_TROOP_HP] and combat.Battle.total(b) == 9 * (top - 95)
    assert [d for d, _ in s.pending] == [3.0]                 # still hurt: the next beat is set
    b["units"] = [top - 3] * 10
    s.pending.pop()[1]()
    assert b["units"] == [top] * 10 and not s.pending         # full: the beat stops


def test_np_troops_regenerate_only_by_their_rows_hp_recovery():
    from kuf2 import combat, game
    from test_battle import hero_session
    role, s = hero_session()
    zt = {"TroopID": 24100, "TroopTableID": 134060, "PosX": 1.0, "PosZ": 2.0, "TeamNum": 0, "UnitNum": 16,
          "NPLeaderID": -100}
    assert game.spawn_zone_troop(s, zt)
    t = s.data["battle"].troops[24100]
    t["units"][0] -= 50
    before = list(t["units"])
    s.pending.clear()
    combat.start_np_regen(s, 24100)
    assert t["c"]["hp_rec"] == 0 and not s.pending and t["units"] == before


# --- T1.2 / T1.6: every stat grows by its Lv column, the element defences are DEFENCE_MAGICAL + their offset ---

# the original's Troop Details "Stats Calculator" (part 8 RVJnrq3zPlo f_00722-f_00728, Lake Bled): the Long Swordsman 2★
# (1100112, 21 units) at the calculator's levels, its numbers the original server's 0x1549 template (troops.template):
# (level, Physical Attack (x units), Physical Defence Penetration, Hit, Melee / Ranged Physical Defence, Fire, Ice,
# Lightning Defence). The f_00727 frame (level box 4) still shows level 3's reply
CALCULATOR = [(1, 357, 15, 50, 74, -38, 118, 15),
              (2, 714, 30, 85, 148, -76, 236, 30),
              (3, 1071, 45, 120, 222, -114, 354, 45),
              (6, 2142, 90, 225, 444, -228, 708, 90)]


@pytest.mark.parametrize("level, attack, pen, hit, defence, fire, ice, lightning", CALCULATOR)
def test_the_stats_calculators_numbers_are_the_level_rows(level, attack, pen, hit, defence, fire, ice, lightning):
    r = troops.level_row(1100112, level)
    assert r["ATTACK_PHYSICAL"] * r["UNIT_COUNT"] == attack and r["PHYSICAL_PENETRATE"] == pen
    assert r["ACCURACY"] == hit and r["DEFENCE_PHYSICAL"] == defence
    assert (r["DEFENCE_MAGICAL_FIRE"], r["DEFENCE_MAGICAL_ICE"], r["DEFENCE_MAGICAL_LIGHTNING"]) == (fire, ice, lightning)


def test_a_regeneration_below_one_a_beat_sets_no_endless_beat():
    # the floor: HP_RECOVERY 0.5 brings back nothing a beat, so no beat is set (a timer that never heals would tick
    # for ever while the troop stays hurt)
    from kuf2 import combat
    from test_combat_rules import room
    s = room()
    s.data["battle"].add_np(20001, 100, 2, c=dict(combat.combatant(6, 1), hp_rec=0.5))
    s.data["battle"].troops[20001]["units"] = [50, 100]
    s.pending.clear()
    combat.start_np_regen(s, 20001)
    assert not s.pending

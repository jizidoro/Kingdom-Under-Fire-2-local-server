"""The guild's second wave (planning/todo/CONTRACT-COMPLETE-PLAN.md 7c, the guild entry's "Not built"): what a learned
guild skill does, the guild shop's buying side, the missions' pay and the Guild Name Change Form (server/kuf2/guild.py
and its call sites in hero.py, status.py, troops.py, world.py, craft.py, cubicshop.py). Every number is read from its
table row here too (guild_point %Guild_Skill / %Util_Skill, abilitycastinfo, statuseffectinfo, itemsaletable 1000, the
item rows, mission_reward); each effect is shown with the skill and gone without it.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import combat, craft, cubicshop, game, guild, hero, items, market, obf, status, tables, troops, world
from kuf2.packet import Reader
from test_army import army, entered
from test_rewards import Session, State, char

NOW = 1_800_000_000
SHOP = 1000                     # itemsaletable 1000: the GUILD_STORE NPCs' MENU_VALUE (npctable 314, 315, 806, 1150)
SNOW_WOLF = 351300360           # %Guild_ItemSale Type Point: slot 4 of the shop, BuyPrice 200,000
LV1_POTION = 350550010          # [Lv 1] Heroic Attack Potion: slot 29, not on %Guild_ItemSale, BuyPrice 3,000
FORM = 351400030                # Guild Name Change Form (item_cash SellID 8105000, 7,500 Cubic)


def ask(role, s, proto, body=b""):
    """One request through the role's handler table; the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def last(replies, proto):
    return next(b for p, b in reversed(replies) if p == proto)


def member(c, *skills, **more):
    """Put character c in a guild of one that has learned `skills` (%Guild_Skill ids)."""
    c.setdefault("name", "Aldric")
    c["guild"] = {**guild.new(c, "Ironwood", NOW), "skills": list(skills), **more}
    return c["guild"]


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(guild.time, "time", lambda: NOW)
    st = State()
    st.world_sessions = {}
    role = world.make(st, 0, "127.0.0.1", 0)
    c = {**char(level=20), "name": "Aldric", "gold": 100_000, "bag": [], "bag_slots": 32, "next_serial": 0x30000}
    return role, st, Session(c), c


def cast_trait(ability, level, k=1):
    row = status.cast_row(ability, level)
    return row[f"TraitType{k}"], float(row[f"TraitValue{k}"].rstrip("%"))


# --- the hero skills (Skill_Type 1): 350001-350004 at levels 1..5 ---

@pytest.mark.parametrize("first, ability, stats", [
    (1, 350001, ("ATTACK_PHYSICAL", "ATTACK_MAGICAL", "ATTACK_PHYSICAL_MAX", "ATTACK_MAGICAL_MIN")),
    (11, 350002, ("DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE")),
    (21, 350003, ("SP_MAX",)),
    (31, 350004, hero.GROUPS["M_DEFENCE_MAGICAL"])])
def test_a_learned_hero_skill_adds_its_rows_percent_to_the_heros_stats(first, ability, stats):
    c = {**char(level=20), "class": 4}                  # Regnier: a physical and a magical attack
    plain = hero.char_stats(c)
    assert any(plain.get(stat, 0) > 0 for stat in stats), stats
    for level in range(1, 6):
        row = guild.skill_rows()[first + level - 1]
        assert (row["Ability_ID"], row["Skill_Level"], row["Skill_Type"]) == (str(ability), str(level), "1")
        name, percent = cast_trait(ability, level)
        assert percent == level and status.cast_row(ability, level)["TraitValue1"] == f"{level}%"
        member(c, first + level - 1)
        with_skill = hero.char_stats(c)
        for stat in stats:
            base = plain.get(stat, 0.0)
            if stat.startswith("ATTACK_") and stat.endswith(("_MIN", "_MAX")):  # the range moves by the attack's gain
                assert with_skill[stat] == pytest.approx(base + plain[stat[:-4]] * percent / 100), (stat, level)
            else:
                assert with_skill.get(stat, 0.0) == pytest.approx(base * (1 + percent / 100)), (stat, level)
        changed = {s for s in with_skill if with_skill[s] != plain.get(s)}
        assert changed and "HP_MAX" not in changed and (ability == 350003) == ("SP_MAX" in changed)
    del c["guild"]
    assert hero.char_stats(c) == plain                  # and gone without the guild


def test_the_stat_names_of_the_hero_skills_are_the_tables():
    assert [cast_trait(350001, 3, k)[0] for k in (1, 2)] == ["ATTACK_PHYSICAL", "ATTACK_MAGICAL"]
    assert cast_trait(350002, 3)[0] == "M_DEFENCE_PHYSICAL" and cast_trait(350003, 3)[0] == "SP_MAX"
    assert cast_trait(350004, 3)[0] == "M_DEFENCE_MAGICAL"
    assert hero.GROUPS["M_DEFENCE_PHYSICAL"] == ("DEFENCE_PHYSICAL_CLOSE", "DEFENCE_PHYSICAL_RANGE")


def test_the_core_hero_skills_are_not_passives_and_change_no_number():
    basic = {r["AbilityId"]: r for r in tables.sections("abilitytypeinfo")["Basic"]}
    assert [basic[a]["Category"] for a in ("350013", "350014")] == ["MOTION", "MOTION"]     # cast, not held
    c = char(level=20)
    plain = hero.char_stats(c)
    member(c, 5, 15, 100, 101)
    assert guild.hero_abilities(c) == {350001: 5, 350002: 5}
    with_cores = hero.char_stats(c)
    c["guild"]["skills"] = [5, 15]
    assert hero.char_stats(c) == with_cores != plain


def test_a_learn_and_a_reset_send_the_heros_block_with_the_new_numbers(server):
    role, st, s, c = server
    g = member(c, point=3_000_000)
    before = world.hero_block(c)
    out = ask(role, s, guild.C2S_LEARN, struct.pack("<I", 1))
    assert out[0] == (guild.S2C_LEARN, bytes(2) + struct.pack("<I", 1)) and g["skills"] == [1]
    block = last(out, world.S2C_HERO_BLOCK)
    assert block == world.hero_block(c) != before
    # the attack the Info window shows (0x10b8, tenths), as the reset push 0x3d89 makes the client ask (0x10b7)
    asked = ask(role, s, world.C2S_ATTACK_REFRESH)
    st_now = hero.char_stats(c)
    assert struct.unpack_from("<I", asked[0][1], 2)[0] == round(st_now["ATTACK_PHYSICAL_MAX"] * 10)
    g["point"] = guild.RESET_COST
    out = ask(role, s, guild.C2S_RESET)
    assert [p for p, _ in out[:2]] == [guild.S2C_RESET, guild.S2C_RESET_DONE] and g["skills"] == []
    assert last(out, world.S2C_HERO_BLOCK) == before
    asked = ask(role, s, world.C2S_ATTACK_REFRESH)
    assert struct.unpack_from("<I", asked[0][1], 2)[0] < round(st_now["ATTACK_PHYSICAL_MAX"] * 10)


def test_a_dismissed_guild_takes_its_hero_skills_with_it(server):
    role, st, s, c = server
    plain = world.hero_block(c)
    member(c, 5)
    assert world.hero_block(c) != plain
    out = ask(role, s, guild.C2S_DISMISS)
    assert out[0] == (guild.S2C_DISMISS, bytes(2)) and last(out, world.S2C_HERO_BLOCK) == plain


def test_the_rooms_hero_fights_with_the_guilds_attack_and_sp():
    c = char(level=20)
    plain_sp = game.pools_for(c, 10234, [])["sp_max"]
    low, high = game.hero_combatant(c)["atk"]["PHYSICAL"]
    attack = hero.char_stats(c)["ATTACK_PHYSICAL"]
    member(c, 5, 25)                                    # 350001 and 350003 at level 5: +5 %
    assert game.pools_for(c, 10234, [])["sp_max"] == round(plain_sp * 1.05) > plain_sp
    assert game.hero_combatant(c)["atk"]["PHYSICAL"] == pytest.approx((low + attack * 0.05, high + attack * 0.05))
    assert game.hero_stat_values(c)[game.STAT_IDS["ATTACK_PHYSICAL"]] == round(attack * 1.05)


# --- the troop skills (Skill_Type 2): a status on each deck troop ---

def test_the_troop_skills_statuses_are_their_cast_rows():
    c = char()
    member(c, 113, 125, 131, 145, 200, 201)
    assert guild.troop_statuses(c) == [(750270, 3), (750280, 5), (750290, 1), (750340, 5), (750310, 1), (750320, 1)]
    for skill, (st_id, lv) in zip(c["guild"]["skills"], guild.troop_statuses(c)):
        row = guild.skill_rows()[skill]
        cast = status.cast_row(int(row["Ability_ID"]), int(row["Skill_Level"]))
        assert (cast["StatusEffect1"], cast["Level1"], cast["TargetBranch1"]) == (str(st_id), str(lv), "26")
    member(c, 5, 215)                                   # hero and utility skills put nothing on a troop
    assert guild.troop_statuses(c) == []


def test_branch_26_leaves_the_ogres_and_scorpions_out():
    row = next(r for r in tables.sections("abilitytypeinfo")["TroopBranch"] if r["BranchId"] == "26")
    upper = {k.upper(): v for k, v in row.items()}
    assert upper["INFANTRY"] == "O" and upper["OGRE"] == "-" and upper["SCORPION"] == "-"
    kinds = {r["TroopType"]: r["BRANCH"] for r in tables.sections("trooptype")["System"]}
    ogre = next(r["TROOP_ID"] for r in tables.sections("trooptable")["Contents"] if kinds.get(r["TroopType"]) == "OGRE")
    c = char()
    member(c, 115)
    assert guild.troop_statuses(c, 1100113) == [(750270, 5)] and guild.troop_statuses(c, int(ogre)) == []


def test_a_troop_skill_raises_the_deck_troops_room_stats_by_its_status_row():
    c, (t,) = army(1)
    t.update(id=1100113, level=21, skills=[])
    plain = troops.room_row(c, t)
    assert plain == troops.troop_level_row(t)
    member(c, 135)                                      # 75029 level 5 -> 750290 level 5: HP_MAX +10 %
    assert status.improvement(750290, 5)["Traitvalue011"] == "10"
    assert troops.unit_hp(troops.room_row(c, t)) == pytest.approx(troops.unit_hp(plain) * 1.10, abs=1)
    member(c, 125)                                      # 75028 level 5 -> 750280: M_DEFENCE_PHYSICAL +30 x the level
    imp = status.improvement(750280, 5)
    assert (imp["FunctionType01"], imp["Traitvalue012"]) == ("ADD_TARGET_LEVEL", "30")
    raised = troops.room_row(c, t)
    gained = {k: raised[k] - plain[k] for k in plain if isinstance(plain[k], (int, float)) and raised[k] != plain[k]}
    assert gained and set(gained.values()) == {30 * 21}
    member(c, 115)                                      # 75027 level 5 -> 750270: ATTACK +10 %, the resolver's to read
    live, record = troops.room_row(c, t), troops.room_row(c, t, live=False)
    assert record == plain and live != plain            # the record's row leaves it to the held status
    del c["guild"]
    assert troops.room_row(c, t) == plain


def test_the_room_puts_the_guilds_statuses_on_the_deck_troops_and_a_revive_brings_them_back():
    c, (t,) = army(1)
    t.update(id=1100113, level=21, skills=[])
    member(c, 115, 135, 200)
    role, s = entered(10234, c)
    held = s.data["statuses"][1]
    assert {k: v["level"] for k, v in held.items() if k in (750270, 750290, 750310)} == {750270: 5, 750290: 5, 750310: 1}
    assert held[750270]["until"] is None                # held, as the troop set's status
    rec = s.data["battle"].troops[1]
    assert rec["units"][0] == troops.unit_hp(troops.room_row(c, t)) > troops.unit_hp(troops.troop_level_row(t))
    physical = combat.status_bonus(combat.held_levels(s, 1), "ATTACK_PHYSICAL")
    assert physical[0] == float(status.improvement(750270, 5)["Traitvalue011"]) == 10
    status.troop_revived(s, 1)
    assert {750270, 750290, 750310} <= set(s.data["statuses"][1])
    # without the guild the same room holds none of them
    del c["guild"]
    role, s = entered(10234, c)
    assert not {750270, 750290, 750310} & set(s.data.get("statuses", {}).get(1, {}))


# --- the utility skills (Skill_Type 3): %Util_Skill ---

def test_the_discounts_are_the_util_rows_values():
    c = char()
    for first, effect in ((211, "Repair_Discount"), (221, "Enchant_Discount"), (231, "MakeCost_Discount"),
                          (241, "Auction_Discount")):
        for level in range(1, 6):
            row = guild.util_rows()[first + level - 1]
            assert (row["Skill_Effect"], row["value"]) == (effect, str(2 * level))
            member(c, first + level - 1)
            assert guild.discount(c, effect) == 2 * level
            assert {e: guild.discount(c, e) for e in ("Repair_Discount", "Enchant_Discount", "MakeCost_Discount",
                                                       "Auction_Discount", "TroopExp_Up") if e != effect} == dict.fromkeys(
                [e for e in ("Repair_Discount", "Enchant_Discount", "MakeCost_Discount", "Auction_Discount",
                             "TroopExp_Up") if e != effect], 0)
    member(c, 301)
    assert guild.util_rows()[301]["Skill_Effect"] == "TroopExp_Up" and guild.discount(c, "TroopExp_Up") == 10
    del c["guild"]
    assert guild.discount(c, "Repair_Discount") == 0 and guild.discounted(c, "Repair_Discount", 999) == 999


def test_the_client_truncates_the_discount():
    c = char()
    member(c, 213)                                      # 6 %
    # 0x140e2af90: discount = trunc(percent x cost / 100), paid = cost - discount
    assert [guild.discounted(c, "Repair_Discount", n) for n in (0, 1, 16, 17, 99, 100, 1234)] == [0, 1, 16, 16, 94, 94, 1160]


def worn_down(c, missing=40):
    armour = [e for e in hero.equipment(c) if items.full_durability(e["code"]) > 0]
    for e in armour:
        e["dur"] = items.full_durability(e["code"]) - missing
    return armour


def repair(role, s, pieces):
    body = struct.pack("<H", len(pieces)) + b"".join(bytes([1]) + obf.u64(e["serial"]) + obf.u16(e["index"])
                                                     for e in pieces)
    return ask(role, s, world.C2S_REPAIR, body)


def test_a_repair_costs_less_with_the_guilds_skill_and_the_full_price_without(server):
    role, st, s, c = server
    armour = worn_down(c)
    full = sum(items.repair_cost(e) for e in armour)
    assert full >= 50
    member(c, 215)                                      # Repair_Discount 10 %
    repair(role, s, armour)
    assert c["gold"] == 100_000 - (full - 10 * full // 100) and all("dur" not in e for e in armour)
    c["gold"] = 100_000
    c["guild"]["skills"] = [211]                        # 2 %
    assert sum(items.repair_cost(e) for e in worn_down(c)) == full
    repair(role, s, armour)
    assert c["gold"] == 100_000 - (full - 2 * full // 100)
    c["gold"] = 100_000
    del c["guild"]
    worn_down(c)
    repair(role, s, armour)
    assert c["gold"] == 100_000 - full
    # the gold check is against the discounted total
    member(c, 215)
    worn_down(c)
    c["gold"] = full - 10 * full // 100 - 1
    assert last(repair(role, s, armour), world.S2C_REPAIR) == struct.pack("<H", world.NOT_ENOUGH_GOLD)
    c["gold"] += 1
    assert last(repair(role, s, armour), world.S2C_REPAIR) == bytes(2) and c["gold"] == 0


WEAPON, STONE = 101119323, None


def enchant_setup(c, level=3):
    rule = items.enchant_rule(WEAPON, level)
    c["bag"] = [{"code": WEAPON, "slot": 1, "count": 1, "serial": 61, "bound": False, "enchant": level},
                {"code": rule["material"], "slot": 2, "count": 500, "serial": 62, "bound": False}]
    return rule


def enchant(role, s, material):
    return ask(role, s, world.C2S_ENCHANT, bytes([0]) + obf.u16(1) + obf.u32(material) + obf.u64(61) + bytes([0]))


def test_an_enchant_costs_less_gold_with_the_guilds_skill(server, monkeypatch):
    role, st, s, c = server
    monkeypatch.setattr(world.random, "randrange", lambda n: 0)        # the first outcome: success
    rule = enchant_setup(c)
    assert rule and rule["cost"] > 100
    c["gold"] = 10 ** 7
    enchant(role, s, rule["material"])
    assert c["gold"] == 10 ** 7 - rule["cost"]                         # no guild: the table's price
    rule = enchant_setup(c)
    member(c, 225)                                                     # Enchant_Discount 10 %
    c["gold"] = 10 ** 7
    out = enchant(role, s, rule["material"])
    assert last(out, world.S2C_ENCHANT)[:2] == bytes(2)
    assert c["gold"] == 10 ** 7 - (rule["cost"] - 10 * rule["cost"] // 100)
    rule = enchant_setup(c)                                            # a purse that holds the discounted price only
    c["gold"] = rule["cost"] - 10 * rule["cost"] // 100
    assert last(enchant(role, s, rule["material"]), world.S2C_ENCHANT)[:2] == bytes(2) and c["gold"] == 0
    rule = enchant_setup(c)
    c["guild"]["skills"] = [215]                                       # another effect's skill takes nothing off
    c["gold"] = rule["cost"] - 1
    assert last(enchant(role, s, rule["material"]), world.S2C_ENCHANT) == struct.pack("<H", world.NOT_ENOUGH_GOLD)


POTION_RECIPE = 350000030       # M_ALCHEMY, Gold 500 a craft, materials 404000100 x1 and 404000800 x3


def craft_start(role, s, count=2):
    return ask(role, s, craft.C2S_START, struct.pack("<II", count, 7) + obf.u32(POTION_RECIPE))


def test_a_craft_costs_gold_rate_less_ten_per_mille_a_percent_and_a_cancel_returns_what_was_paid(server):
    role, st, s, c = server
    r = craft.recipe(POTION_RECIPE)
    mats = lambda: [{"code": 404000100, "slot": 0, "count": 3, "serial": 41, "bound": False},     # noqa: E731
                    {"code": 404000800, "slot": 1, "count": 6, "serial": 42, "bound": False}]
    full = craft.cost(r, 1, 2)
    assert full == int(r["Gold"]) * 2                                  # craft level 1: Gold_Rate 1000
    c.update(gold=5000, level=5, bag=mats())
    assert craft_start(role, s)[-1][1][:2] == bytes(2) and c["gold"] == 5000 - full
    ask(role, s, craft.C2S_CANCEL, obf.u32(POTION_RECIPE))
    assert c["gold"] == 5000
    member(c, 235)                                                     # MakeCost_Discount 10 %: 1000 -> 900 per mille
    assert guild.make_rate_off(c) == 100 and craft.cost(r, 1, 2, 100) == -(-int(r["Gold"]) * 2 * 900 // 1000)
    c.update(gold=5000, bag=mats())
    assert craft_start(role, s)[-1][1][:2] == bytes(2) and c["gold"] == 5000 - craft.cost(r, 1, 2, 100) > 5000 - full
    c["guild"]["skills"] = []                                          # the skill reset while the craft runs
    ask(role, s, craft.C2S_CANCEL, obf.u32(POTION_RECIPE))
    assert c["gold"] == 5000                                           # what was paid comes back, no more
    # a craft level's own rate and the guild's add up: level 6 is 950 per mille, less 60 for 6 %
    assert craft.cost(r, 6, 3, 60) == -(-int(r["Gold"]) * 3 * 890 // 1000)


def test_the_auction_discount_is_for_the_collect_fee_and_the_deposit_stays():
    # textui 13203: "Guild Auction Hall fee only applies to Item Collect Fee."; nothing sells on a server of one
    c = char()
    before = market.deposit(WEAPON, 6)
    member(c, 245)
    assert guild.discount(c, "Auction_Discount") == 10 and market.deposit(WEAPON, 6) == before


def test_troop_exp_up_adds_ten_percent_to_a_troops_mission_exp():
    c, (t,) = army(1)
    t.update(id=1100113, level=5, exp=0)
    need = troops.troop_need(t["id"], 5)
    amount = min(1000, need // 2)
    assert troops.gain_exp(c, t, amount) == (5, amount) and t["exp"] == amount
    t["exp"] = 0
    member(c, 301)                                                     # TroopExp_Up 10
    assert guild.troop_exp(c, 1191) == 1191 + 119 and guild.troop_exp(c, 9) == 9
    assert troops.gain_exp(c, t, amount) == (5, amount + amount * 10 // 100) and t["exp"] == amount + amount * 10 // 100
    t["exp"] = 0
    c["guild"]["skills"] = [215]
    assert troops.gain_exp(c, t, amount) == (5, amount)


# --- the guild shop: itemsaletable 1000 through 0x1540 ---

def buy_body(slot, count=1, dst=0):
    return obf.u16(dst) + struct.pack("<II", 0, SHOP) + obf.u16(count) + bytes([slot])


def store_reply(replies):
    b = last(replies, world.S2C_STORE_BUY)
    assert len(b) == 15                                                # the handler reads 15 bytes on every result
    return struct.unpack_from("<HQ", b) + (obf.dec_u40(b[10:15]),)


def test_the_guild_shops_goods_are_the_tables_priced_in_contribution():
    row = next(r for r in tables.sections("itemsaletable")["ItemSaleTable"] if r["ID"] == str(SHOP))
    slots = [int(row[f"SLOT{k}_ID"]) for k in range(1, 61) if row[f"SLOT{k}_ID"].isdigit()]
    assert len(slots) == 33 and set(guild.shop_rows()) < set(slots) and len(guild.shop_rows()) == 28
    always = [code for code in slots if code not in guild.shop_rows()]
    assert always == [350550010, 350551010, 350552010, 350553010, 350554010]          # the [Lv 1] potions
    assert all(items.row(code)["MoneyType"] == str(guild.MONEY_CONTRIBUTION) for code in slots)
    assert items.sale_slot(SHOP, 3) == (SNOW_WOLF, 1) and items.buy_price(SNOW_WOLF) == 200_000
    assert items.sale_slot(SHOP, 28) == (LV1_POTION, 1) and items.buy_price(LV1_POTION) == 3_000
    menus = [r for r in tables.sections("npctable")["NpcTable"] if r["MENU_TYPE1"] == "GUILD_STORE"]
    assert len(menus) == 4 and {r["MENU_VALUE1"] for r in menus} == {str(SHOP)}


def test_a_character_with_no_guild_buys_nothing_there(server):
    role, st, s, c = server
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28))) == (guild.NOT_IN_GUILD, 0, 100_000)
    assert c["bag"] == [] and c["gold"] == 100_000


def test_a_good_the_guild_has_not_opened_is_refused_and_an_open_one_costs_its_buy_price(server):
    role, st, s, c = server
    g = member(c, contribution=450_000)
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(3))) == (guild.NO_RIGHT, 450_000, 100_000)
    assert c["bag"] == [] and g["contribution"] == 450_000
    g["shop"] = {str(SNOW_WOLF): NOW + 3600}                           # opened (0x3d7d) for another hour
    out = ask(role, s, world.C2S_STORE_BUY, buy_body(3, dst=5))
    assert store_reply(out) == (0, 250_000, 100_000)                   # the u64 is the contribution left; no gold
    assert [(i["code"], i["count"], i["slot"]) for i in c["bag"]] == [(SNOW_WOLF, 1, 5)]
    assert g["contribution"] == 250_000 and c["gold"] == 100_000
    assert [p for p, _ in out].index(world.S2C_STORE_BUY) < [p for p, _ in out].index(world.S2C_CARGO_CHANGE)
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(3))) == (0, 50_000, 100_000)
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(3))) == (world.NOT_ENOUGH_GOLD, 50_000, 100_000)
    assert sum(i["count"] for i in c["bag"]) == 2 and g["contribution"] == 50_000
    g["shop"][str(SNOW_WOLF)] = NOW - 1                                # its time ran out
    g["contribution"] = 10 ** 6
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(3)))[0] == guild.NO_RIGHT
    assert g["contribution"] == 10 ** 6 and g["shop"] == {}


def test_the_lv1_potions_are_always_sold_and_a_count_multiplies_the_price(server):
    role, st, s, c = server
    g = member(c, contribution=20_000)
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28, count=5))) == (0, 5_000, 100_000)
    assert [(i["code"], i["count"]) for i in c["bag"]] == [(LV1_POTION, 5)] and g["contribution"] == 5_000
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28, count=2)))[0] == world.NOT_ENOUGH_GOLD
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28, count=0)))[0] == world.ITEM_LOCKED    # as any shop
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(40)))[0] == world.ITEM_LOCKED             # an empty slot
    assert g["contribution"] == 5_000 and st_saved(c) == [(LV1_POTION, 5)]


def st_saved(c):
    return [(i["code"], i["count"]) for i in c["bag"]]


def test_a_full_bag_keeps_the_contribution(server):
    role, st, s, c = server
    g = member(c, contribution=20_000)
    c["bag_slots"] = 0                                                 # no room in the bag
    assert not world.fits(c, [(LV1_POTION, 1)])
    assert store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28))) == (guild.SHOP_BAG_FULL, 20_000, 100_000)
    assert g["contribution"] == 20_000 and c["bag"] == []


def test_an_ordinary_shop_still_answers_with_the_members_contribution(server):
    role, st, s, c = server
    member(c, contribution=777)
    code, _ = items.sale_slot(103, 0)
    out = ask(role, s, world.C2S_STORE_BUY, obf.u16(1) + struct.pack("<II", 0, 103) + obf.u16(1) + b"\0")
    assert store_reply(out) == (0, 777, 100_000 - items.buy_price(code))


# --- a won mission pays the guild ---

def reward_row(spot=10331, difficulty="Normal", grade="S"):
    return next(r for r in tables.sections("mission_reward")["DATA"]
                if r["ID"] == str(spot) and r["Difficulty"] == difficulty and r["Grade"] == grade)


def test_a_won_mission_pays_its_rows_guild_columns_on_the_world_connection():
    row = reward_row()
    exp, point, gift = (int(row[k]) for k in ("Guild_Exp", "Guild_Point", "Guild_Contribution"))
    assert (exp, point, gift) == (100, 100, 100)
    c = {**char(level=20), "name": "Aldric"}
    st = State()
    st.world_sessions = {}
    room, town = Session(c, spot=10331), Session(c)
    st.world_sessions[1] = town
    assert guild.on_mission(room, st, row) is False                    # no guild: nothing
    g = member(c)
    assert guild.on_mission(room, st, None) is False and guild.on_mission(room, st, {}) is False
    assert guild.on_mission(room, st, row) is True
    assert (g["exp"], g["point"], g["contribution"]) == (exp, point, gift)
    assert room.sent == []                                             # the guild's pushes are the world connection's
    assert [w.proto for w in town.sent] == [guild.S2C_LEVEL, guild.S2C_GUILD_POINTS, guild.S2C_EARNED,
                                           guild.S2C_POINTS_PUSH]
    assert bytes(town.sent[2].buf) == struct.pack("<II", point, 0)     # "<guild> acquired <n> Guild Points."
    assert bytes(town.sent[3].buf) == struct.pack("<QQQ", point, gift, guild.DAILY_POINTS)
    # a second win adds again; with the world connection gone the save alone changes
    del st.world_sessions[1]
    town.sent.clear()
    assert guild.on_mission(room, st, row) is True
    assert (g["point"], g["contribution"]) == (2 * point, 2 * gift) and town.sent == room.sent == []
    # called with the world session itself, as on_quest is
    assert guild.on_mission(town, st, row) is True and len(town.sent) == 4 and g["point"] == 3 * point


def test_every_mission_reward_row_has_the_three_guild_columns():
    rows = tables.sections("mission_reward")["DATA"]
    assert all({"Guild_Exp", "Guild_Point", "Guild_Contribution"} <= set(r) for r in rows)
    paying = [r for r in rows if r["Guild_Point"].isdigit() and int(r["Guild_Point"]) > 0]
    assert (len(rows), len(paying)) == (988, 923)                      # the rest pay 0 (the Tower 10233 among them)
    assert all(guild._guild_columns(r) == (int(r["Guild_Point"]),) * 3 for r in paying)   # the three always equal
    assert (min(int(r["Guild_Point"]) for r in paying), max(int(r["Guild_Point"]) for r in paying)) == (100, 2500)


# --- the Guild Name Change Form ---

def test_the_form_is_sold_for_cubic_again_and_renames_the_guild(server):
    role, st, s, c = server
    good = cubicshop.good(8105000)
    assert good is not None and int(good["ItemCode"]) == FORM and good["CashPrice"] == "7500"
    assert items.row(FORM)["ConsumeItemType"] == "GUILD_NAME"
    g = member(c)
    c["cubic"] = 8000
    out = ask(role, s, cubicshop.C2S_BUY, bytes([1]) + struct.pack("<I", 8105000))
    assert last(out, cubicshop.S2C_BUY) == bytes(2) + bytes([1]) + struct.pack("<I", 8105000) and c["cubic"] == 500
    form = next(i for i in c["bag"] if i["code"] == FORM)
    # the bag's right-click opens the name input itself (0x140dd3d64) and its answer is 0x3d8c: slot, serial, name
    body = obf.u16(form["slot"]) + obf.u64(form["serial"]) + b"Oakshield\0"
    out = ask(role, s, guild.C2S_RENAME, body)
    assert out[0] == (guild.S2C_RENAME, bytes(2))
    assert last(out, guild.S2C_RENAMED) == struct.pack("<I", g["id"]) + b"Oakshield\0"
    assert g["name"] == "Oakshield" and not any(i["code"] == FORM for i in c["bag"])
    assert guild.name_of(c) == "Oakshield"                             # what the character list carries at a relog


# --- attacks (run, kept) ---

def test_a_save_with_a_skill_id_the_table_lacks_does_not_break_the_heros_numbers():
    c = char(level=20)
    plain = hero.char_stats(c)
    member(c, 9999, "x", 5)
    assert guild.hero_abilities(c) == {350001: 5} and guild.troop_statuses(c) == [] and guild.discount(c, "TroopExp_Up") == 0
    assert hero.char_stats(c)["ATTACK_PHYSICAL"] == pytest.approx(plain["ATTACK_PHYSICAL"] * 1.05)


def test_a_mission_won_by_another_character_than_the_world_connections_tells_nobody():
    row = reward_row()
    aldric, qwe = {**char(level=20), "name": "Aldric"}, {**char(level=6), "id": 2, "name": "qwe123"}
    st = State()
    st.world_sessions = {1: Session(aldric)}                           # the account's world connection plays Aldric
    room = Session(qwe, spot=10331)
    g = member(qwe)
    assert guild.on_mission(room, st, row) is True and g["point"] == 100
    assert st.world_sessions[1].sent == [] and room.sent == [] and "guild" not in aldric


@pytest.mark.parametrize("body", [b"", b"\0", bytes(12), bytes(13), b"\xff" * 13, b"\xff" * 64,
                                  obf.u16(0) + struct.pack("<II", 0, SHOP) + obf.u16(0xffff) + bytes([28]),
                                  obf.u16(0xffff) + struct.pack("<II", 0xffffffff, SHOP) + obf.u16(1) + bytes([255]),
                                  obf.u16(0) + struct.pack("<II", 0, SHOP) + obf.u16(1) + bytes([33])])
def test_junk_and_greedy_shop_requests_take_nothing(server, body):
    role, st, s, c = server
    g = member(c, contribution=100_000, shop={str(SNOW_WOLF): NOW + 60})
    out = ask(role, s, world.C2S_STORE_BUY, body)
    assert all(len(b) == 15 for p, b in out if p == world.S2C_STORE_BUY)
    assert g["contribution"] == 100_000 and c["bag"] == [] and c["gold"] == 100_000
    assert not out or struct.unpack_from("<H", last(out, world.S2C_STORE_BUY))[0] != 0


def test_a_buy_never_spends_more_than_the_price_nor_goes_below_zero(server):
    role, st, s, c = server
    g = member(c, contribution=3_000 * 7 + 2_999)
    bought = 0
    for _ in range(12):
        code_, left, _gold = store_reply(ask(role, s, world.C2S_STORE_BUY, buy_body(28)))
        bought += code_ == 0
        assert left == g["contribution"] >= 0
    assert bought == 7 and g["contribution"] == 2_999
    assert sum(i["count"] for i in c["bag"] if i["code"] == LV1_POTION) == 7


def test_the_guild_family_is_still_answered_through_the_wired_world_role(server):
    role, st, s, c = server
    assert role.handlers[guild.C2S_LEARN].__module__ == "kuf2.guild" and "8105000" not in cubicshop.HIDDEN

"""Grey Rock native failure: F1/Y for wiped borrowed archers got 0x7413, 2026-10-09 02:26:34."""
import copy
import struct

import pytest

from kuf2 import combat, game, obf, status
from test_army import army, entered, pkt


def greyrock():
    c, owned = army(1, level=6)
    c.update(id=2, name="qwe123", **{"class": 3}, cubic=100)
    role, s = entered(10234, c)
    assert 10073 in s.data["plan"]["hand"] and 10073 not in s.data["deck"]
    return role, s, owned


def wipe(s, uid):
    t = s.data["battle"].troops[uid]
    t["units"] = [0] * len(t["units"])
    if t.get("leader_max"):
        t["leader"] = 0


def request(role, s, uid=10073, item=0xFFFFFFFF):
    s.sent.clear()
    role.handlers[game.C2S_REVIVE_HERE](s, pkt(game.C2S_REVIVE_HERE,
                                             struct.pack("<H", uid) + obf.u32(item)))
    return struct.unpack_from("<HI", bytes(next(w for w in s.sent if w.proto == game.S2C_REVIVE_HERE).buf))


def test_greyrock_borrowed_archers_revive_with_one_free_use_and_no_roster_change():
    role, s, owned = greyrock()
    wipe(s, 10073)
    before = copy.deepcopy(owned)
    free = game.free_revives(s.data["char"])
    assert request(role, s) == (0, 1)
    t = s.data["battle"].troops[10073]
    assert len(t["units"]) == 16 and all(hp == 163 for hp in t["units"])
    assert game.free_revives(s.data["char"]) == free - 1
    assert s.data["char"]["cubic"] == 100 and owned == before
    assert status.REVIVE_TROOP in status.holding(s, 10073)
    assert {game.S2C_TROOP_DOWN, combat.S2C_UNIT_LIVE, game.S2C_TROOP_HP} <= {w.proto for w in s.sent}
    assert request(role, s) == (game.REVIVE_NOT_NOW, 1)
    assert game.free_revives(s.data["char"]) == free - 1


def test_native_archer_confirmation_uses_a_coupon_before_daily_free_count():
    # Native02:53:42: body59278d66e309 names10073 and COUPON_REVIVAL351500300.
    role, s, _ = greyrock()
    wipe(s, 10073)
    c = s.data["char"]
    c["bag"] = [{"code":351500300,"slot":25,"count":3,"serial":8590000161,"bound":False}]
    free = game.free_revives(c)
    assert bytes.fromhex("59278d66e309") == struct.pack("<H",10073) + obf.u32(351500300)
    assert request(role,s,item=351500300) == (0,1)
    assert c["bag"][0]["count"] == 2 and game.free_revives(c) == free
    assert c["cubic"] == 100


@pytest.mark.parametrize("uid", [1, 10000, 20000, 65534])
def test_alive_owned_or_unowned_dead_troops_cannot_consume_a_revive(uid):
    role, s, owned = greyrock()
    if uid not in (1, 65534):
        wipe(s, uid)
    before = copy.deepcopy(owned)
    free = game.free_revives(s.data["char"])
    assert request(role, s, uid) == (game.REVIVE_NOT_NOW, 0)
    assert game.free_revives(s.data["char"]) == free
    assert s.data["char"]["cubic"] == 100 and owned == before


def test_borrowed_troop_still_obeys_the_mission_revive_ban():
    role, s, _ = greyrock()
    wipe(s, 10073)
    s.data["spot"] = 10540
    free = game.free_revives(s.data["char"])
    assert request(role, s) == (game.REVIVE_NOT_HERE, 0)
    assert game.free_revives(s.data["char"]) == free


def test_borrowed_troop_uses_none_grade_price_after_free_revives():
    from kuf2 import items, rules, world
    role, s, _ = greyrock()
    c = s.data["char"]
    c["free_revives"] = {"day": rules.game_day(), "used": game.FREE_REVIVES}
    price = items.currency("Resurrect", 26)
    assert price == 25
    wipe(s, 10073)
    c["cubic"] = price - 1
    assert request(role, s) == (world.CUBIC_SHORT, 0)
    assert c["cubic"] == price - 1 and not any(s.data["battle"].troops[10073]["units"])
    c["cubic"] = price
    assert request(role, s) == (0, 1)
    assert c["cubic"] == 0


@pytest.mark.parametrize("code,count", [(351500300,0),(350000010,1),(0,1)])
def test_missing_or_unrelated_coupon_cannot_buy_a_revival(code,count):
    role, s, _ = greyrock()
    wipe(s,10073)
    c=s.data["char"]
    c["bag"]=[{"code":code,"slot":0,"count":count,"serial":1,"bound":False}] if count else []
    free=game.free_revives(c)
    before=copy.deepcopy(c)
    assert request(role,s,item=code) == (game.REVIVE_NOT_NOW,0)
    assert c == before and game.free_revives(c) == free
    assert not any(s.data["battle"].troops[10073]["units"])

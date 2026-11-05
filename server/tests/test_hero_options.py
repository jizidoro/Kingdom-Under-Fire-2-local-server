"""Gear's random options in the hero's stats (planning/rules/HERO.md G10; the roll, the record and the reroll window are
the economy hunt's build, ECONOMY H11, tests/test_economy_hunt.py).

The wire, pinned 2026-10-01 from the client's tooltip use of the record tail (0x140d66e69, 0x1406a11fc, 0x14069e140): u8 k
+ k x (E_TraitTypes index, Target 1 = LEADER "[Hero]", f32 a percent as a fraction, i32 a whole value); the tooltip prints
(int)(f32 x 100) "%". The tape: tUb99Vs2t_g f_00406, an owned Mercenary Bracelet A (OLIVIA 202410311, RandomOptionID_1
941031) shows "[Hero] Skill Attack Retreat Chain Skill (Ranger) : +2.0%" - the whole 20 (ABILITY_ADD_DAMAGE_RATE traits
print tenths), rolled on gain."""
import struct

import pytest

from kuf2 import hero, items

RING = 201324412                 # Senior Centurion Ring B (REGNIER): RandomOptionID_1 = _2 = 832441, Prob 100000
PCT, WHOLE = items.TRAIT_TYPES.index("ATTACK_PHYSICAL"), items.TRAIT_TYPES.index("PHYSICAL_PENETRATE")


@pytest.mark.parametrize("option, wire", [
    ([PCT, 1, 0.06, 0, 0], "0f 01 8f c2 75 3d 00 00 00 00"),                           # "+6%"
    ([WHOLE, 1, 0.0, 120, 0], "1d 01 00 00 00 00 78 00 00 00"),                        # "+120"
    ([items.TRAIT_TYPES.index("ABILITY_ADD_DAMAGE_RATE_01"), 1, 0.0, 20, 0], "42 01 00 00 00 00 14 00 00 00"),  # "+2.0%"
])
def test_an_option_goes_on_the_wire_as_the_tooltip_reads_it(option, wire):
    assert items.option_tail([option])[1:].hex(" ") == wire


def test_every_percent_in_the_data_shows_its_own_number():
    """The tooltip truncates float32(f32 x 100): each percent of randomoption, sent as its fraction, shows itself."""
    percents = {int(items._leading_number(r[f"Value{i}_{end}"])) for r in items._option_rows().values()
                for i in range(1, 21) for end in ("Min", "Max") if "%" in str(r.get(f"Value{i}_{end}", ""))}
    for p in sorted(percents):
        f = struct.unpack("<f", struct.pack("<f", round(p / 100, 4)))[0]
        assert int(struct.unpack("<f", struct.pack("<f", f * 100))[0]) == p


def test_options_count_in_the_heros_stats_numbers_first_then_percents():
    worn = lambda opts: {"id": 1, "class": 4, "level": 24,                                           # noqa: E731
                         "equip": [{"code": RING, "index": 7, "serial": 1, "options": opts}]}
    bare = hero.char_stats(worn([list(items.NO_OPTION)]))
    got = hero.char_stats(worn([[WHOLE, 1, 0.0, 120, 832441], [PCT, 1, 0.1, 0, 832441]]))
    assert got["PHYSICAL_PENETRATE"] == bare["PHYSICAL_PENETRATE"] + 120
    assert got["ATTACK_PHYSICAL"] == pytest.approx(bare["ATTACK_PHYSICAL"] * 1.1)
    broken = worn([[WHOLE, 1, 0.0, 120, 832441]])
    broken["equip"][0]["dur"] = 0                                        # a broken piece's options count for nothing
    assert hero.char_stats(broken)["PHYSICAL_PENETRATE"] == bare["PHYSICAL_PENETRATE"]
    assert hero.char_stats(broken)["SP_MAX"] == bare["SP_MAX"] - 51                     # nor its own trait

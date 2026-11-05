"""Every story mission of the proof audit's "C3 by mission" (planning/audit/proof-2026-09-29/C.md) that has no director
table is won today by the wave rule (game.mission_troop_down / next_wave: Q1's fallback, MISSIONS-WIRING G3): the room
starts with something to fight, every held wave wakes, every hostile falls, and the mission is won once, at the last
fall. The audit's scratch probe (C_probe.py, row C16) made a repo test, so "winnable" is HEADLESS proof, not a probe.
The rule is ours; a mission's own rule (a table, a boss, a clock) replaces it mission by mission. What this does not
prove: that a spot is winnable on foot (the waves are brought down here, not walked to; the walls are not modelled).
The tabled missions (10358, 10233, 10234, 10361, 10362, 10235, 10303 and the training camps 10331, 10345, 10347,
10349) are won by their tables: test_mission_playthrough."""
import pytest

from kuf2 import game
from test_battle import NoSave, mission_room
from conftest import run_pending

ROUNDS = 100                    # each round downs every hostile standing; the most waves a C3 spot holds is 25 (10305)

WAVE_RULE = {                   # the C3 rows (the audit's names; the Windstone / Chasm names from textspotname_eng)
    10306: "fort-valley", 10211: "posterus-outskirts", 10212: "posterus-centre",
    10318: "steel-plain",
    10307: "green-flow", 10319: "claws-station", 10328: "forest-of-fog", 10205: "dark-veil", 10305: "stalker-forest",
    10312: "swidden-deadwood", 10323: "centre-deadwood", 10313: "shield-keep", 10309: "essex-outskirts",
    10322: "essex-centre", 10310: "temple-entrance", 10321: "inner-court", 10206: "desert-eye",
    10320: "kedington", 10314: "greendale-outskirts", 10324: "greendale-centre",
    10317: "ancient-temple",
    10213: "engelberg-entrance", 10214: "engelberg-midpoint", 10215: "angels-halo", 10327: "grey-wood",
    20301: "dry-golden-path", 20303: "valley-of-alteration", 20304: "field-of-veteran", 20305: "shining-spring",
    20325: "queens-maze", 20347: "spirits-land", 20306: "urka-village-south", 20324: "urka-village-north",
    20318: "vandall-valley", 20320: "secluded-scarp", 20321: "watchers-valley", 20308: "daroka-village",
    20915: "borderline", 20917: "pillar-of-twilight", 20918: "deathfell-land", 20920: "luminent-hill",
    10346: "camp-rifleman",                                 # no table: the playlist never enters it
}
# C3 spots won by their own rules (rules.py), proved in test_rules.py: the Unknown Corridor 10540-10546 (the day's boss
# in its 5:00 clock, Q16, C13) and the Treasure Goblin Nest 10237 (its three real goblins, won when the clock runs
# out, Q33, C12). Grey Wood 10327 (a subjugation) is won by its waves here; its 3:30 clock wins it at 0:00 too
# (rules.py, test_rules.py). Grey Hampton 10315 is won by its storm's clock after its relic device breaks (rules.py
# STORM, the tape part 14; test_mission_rules.py), not by its last hostile. The prologue 50116 (0 hostile troops) is
# won by its table's last scene (test_scenes_50116). C3 spots no rule of ours wins today:
NOT_YET = {}
SPOTS = [pytest.param(spot, id=f"{spot}-{name}") for spot, name in WAVE_RULE.items()] + [
    pytest.param(spot, id=str(spot), marks=pytest.mark.skip(reason=why)) for spot, why in NOT_YET.items()]


def standing(s):
    return [u for u, z in s.data.get("zone_troops", {}).items() if game.hostile(z) and u not in s.data.get("down", set())]


def windows(s):
    """The room's end: its result window, or for a mission the original gave none (decision B2) its leave (0x4041)."""
    end = game.S2C_MISSION_LEAVE if game.windowless(s.data["spot"]) else game.S2C_MISSION_COMPLETE
    return sum(w.proto == end for w in s.sent)


@pytest.mark.parametrize("spot", SPOTS)
def test_the_mission_is_won_by_the_wave_rule(spot):
    s = mission_room(spot)
    assert game.is_mission(spot) and standing(s), "nothing to fight at the start"   # the zone's, or the first wave's
    planned = {t["TroopID"] for w in game.mission_waves(spot) for t in w}
    at_win = None
    for _ in range(ROUNDS):
        alive = standing(s)
        if not alive or s.data.get("mission_won"):
            break
        for u in alive:
            game.mission_troop_down(s, NoSave(), u)
            if at_win is None and windows(s):
                at_win = standing(s)                    # who still stood when the victory window went out
    run_pending(s)
    assert s.data["waves"] == [] and planned <= set(s.data["zone_troops"]), "held waves never came: %s" % (
        [w[0].get("ForceNum") for w in s.data["waves"]])
    assert standing(s) == [], "hostiles left standing"
    assert windows(s) == 1 and s.data.get("mission_won")
    assert at_win == [], "won while %s still stood" % at_win

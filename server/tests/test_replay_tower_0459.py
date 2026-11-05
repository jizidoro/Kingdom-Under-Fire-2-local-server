"""The live Tower run of 2026-09-29 04:59-05:20 (captures/game_20260929_045953_418826.log, on 0c84258) replayed through
today's handlers: the client's own reports, copied with their line numbers into replay_tower_0459.txt (the captures
are gitignored), fed to the game role as the client sent them. The proof audit's offline proofs 1 and 3 (planning/
audit/proof-2026-09-29/AB.md section 4): the wyrm's pace under the current resolver, and attack-0 against the leaders."""
import pathlib

from kuf2 import combat, game
from kuf2.packet import Reader
from test_battle import NoSave, mission_room
from conftest import run_pending

FIXTURE = pathlib.Path(__file__).with_name("replay_tower_0459.txt")
WYRM, FLAG, TARGET, LEADERS = 30001, 11000, 20101, (10000, 10001)


def lines(*sections):
    """(capture line number, direction, message, frame) of the fixture's sections, in the capture's order."""
    out = []
    for row in FIXTURE.read_text(encoding="utf-8").splitlines():
        if row and not row.startswith("#"):
            section, n, _, direction, proto, _, frame = row.split()
            if section in sections:
                out.append((int(n), direction, int(proto, 16), bytes.fromhex(frame)))
    return sorted(out)


def replay(s, rows, after=None):
    role = game.make(NoSave(), 0)
    for n, direction, proto, frame in rows:
        if direction == "C2S":
            role.handlers[proto](s, Reader(frame))
            if after:
                after(n, proto)


class Lowest:
    """Every draw at its lowest and no crit: the slowest the resolver can bring a troop down."""
    def uniform(self, a, b):
        return min(a, b)

    def random(self):
        return 1.0


def test_the_archers_volleys_bring_the_wyrm_down_within_five(monkeypatch):
    # the old server (the chain without the synastry) needed 11 of these volleys (953 hp a volley, 11,431 hp), the
    # original 4.5 s to 62 % (TOWER-FORCES); the synastry row 278 takes RANGE x3, so at most 5 on the lowest rolls
    rows = lines("wyrm")
    old_fall = next(n for n, d, proto, _ in rows if d == "S2C" and proto == 0x50fd)
    assert sum(1 for n, d, proto, _ in rows if proto == combat.C2S_AREA_DAMAGE and n < old_fall) == 11
    monkeypatch.setattr(combat, "random", Lowest())
    s = mission_room(10233)
    run_pending(s)
    game.spawn_force(s, 30000)
    wyrm = s.data["battle"].troops[WYRM]
    fired, fell_at = [], []

    def count(n, proto):
        if proto == combat.C2S_AREA_DAMAGE:
            fired.append(n)
        if not fell_at and combat.Battle.total(wyrm) == 0:
            fell_at.append(len(fired))
    replay(s, rows, count)
    assert len(fired) == 12 and fell_at and fell_at[0] <= 5, (fell_at, combat.Battle.total(wyrm))
    assert WYRM in s.data["down"]


def test_the_flag_troop_deals_nothing_and_glen_and_thompson_strike_as_leaders(monkeypatch):
    # the flag troop 11000 (133010, "attack x0" by design: DESIGNER-NOTES finding 7) was the F20100 fight's most
    # frequent attacker live (91 blows on 20101, 05:05:06-05:05:29): 0 each now (b335664), 1 each on the old server.
    # Glen and Thompson ride attack-0 shells too (133010 / 133030); their blows carry the leader bit, so they strike
    # with their leaders' records (npleadertable: 214.5 / 143 attack) and deal damage
    s = mission_room(10233)
    run_pending(s)
    for force in (20010, 20100):
        game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == force), "test")
    hits = []
    monkeypatch.setattr(combat, "journal_hit", lambda s, attacker, uid, dealt, n=1: hits.append((attacker, uid, dealt)))
    replay(s, lines("flag", "leaders"))
    flag = [dealt for attacker, uid, dealt in hits if attacker == FLAG and uid == TARGET]
    assert len(flag) == 91 and sum(flag) == 0
    for leader in LEADERS:
        dealt = [d for attacker, _, d in hits if attacker == leader]
        assert dealt and sum(dealt) > 0 and max(dealt) > 1, (leader, dealt)

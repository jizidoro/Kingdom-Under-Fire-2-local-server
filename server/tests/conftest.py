import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


def pytest_addoption(parser):
    parser.addoption("--game", help="the game's folder (default: found through Steam's library list)")


def pytest_configure(config):
    """Most tests read the installed game's tables: find it first (tools/pkg.py use_game), or stop naming where."""
    from kuf2.tables import pkg
    try:
        pkg.use_game(config.getoption("game"))
    except SystemExit as e:
        pytest.exit(str(e), returncode=4)


def run_pending(s, limit=500):
    """Run what a room scheduled (s.later), in delay order, until nothing is left: the director's lines, then its
    ending and the victory window (director.before_win). Capped, as timers may schedule themselves again."""
    for _ in range(limit):
        if not s.pending:
            return
        s.pending.sort(key=lambda p: p[0])
        s.pending.pop(0)[1]()


@pytest.fixture(autouse=True)
def game_damage(monkeypatch):
    """The tests check the game's own numbers: the owner's hero damage boost (combat.HERO_DAMAGE_SCALE) is off here."""
    from kuf2 import combat
    monkeypatch.setattr(combat, "HERO_DAMAGE_SCALE", 1)

"""KUF2 offline server.

  py server/main.py                         the game found through Steam's library list, the game's own damage
  py server/main.py --game "D:/Games/Kingdom Under Fire 2"   the game's folder, when Steam doesn't list it
  py server/main.py --hero-damage 10000     the hero's hits on troops multiplied (1 = the game's own)

Then start the game with `py tools/launch.py`. The save is server/data/db.json; logs go to captures/.
"""
import argparse, asyncio, logging, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from kuf2 import combat, game, login, net, world
from kuf2.tables import pkg
from kuf2.state import State

HOST = "127.0.0.1"
LOGIN_PORT = 25002   # the port the launcher passes on the command line (tools/launch.py)
WORLD_PORT = 25003
GAME_PORT = 25004


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    net.log.info("game %s, hero damage x%s", net.private(str(pkg.GAME)), combat.HERO_DAMAGE_SCALE)
    net.log.info("journal %s", net.private(str(net.open_journal())))     # the events tools/live.py follows
    state = State()
    servers = [
        await login.make(state, LOGIN_PORT, HOST, WORLD_PORT).serve(HOST),
        await world.make(state, WORLD_PORT, HOST, GAME_PORT).serve(HOST),
        await game.make(state, GAME_PORT).serve(HOST),
    ]
    await asyncio.gather(*(s.serve_forever() for s in servers))


def options(argv=None):
    ap = argparse.ArgumentParser(description="Kingdom Under Fire 2 offline server (then: py tools/launch.py)")
    ap.add_argument("--game", help="the game's folder (default: found through Steam's library list)")
    ap.add_argument("--hero-damage", type=float, default=1, help="multiply the hero's hits on troops (default 1)")
    a = ap.parse_args(argv)
    if not 0 < a.hero_damage < math.inf:                 # nan fails both
        ap.error("--hero-damage must be a number above 0")
    pkg.use_game(a.game)
    combat.HERO_DAMAGE_SCALE = int(a.hero_damage) if a.hero_damage == int(a.hero_damage) else a.hero_damage
    return a


if __name__ == "__main__":
    options()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

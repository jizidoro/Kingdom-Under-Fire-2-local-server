# Kingdom Under Fire 2: local server

A server you run on your own PC that makes **Kingdom Under Fire 2** (Steam app 1132210) playable offline, with your own
Steam copy of the game. The official servers are gone; this project rebuilds what they did, so the game's single-player
story can be played again. It's a game-preservation project in the spirit of "Stop Killing Games".

- **You need your own copy of the game** from Steam. No game files are included here; the server reads the game's
  data from your install while it runs.
- Not affiliated with, or endorsed by, Blueside, Gameforge or anyone who owns Kingdom Under Fire. All game names and
  content belong to their owners.
- One player, one PC: the server listens on `127.0.0.1` only.

## Status

Work in progress. What has been played through in the real game client, start to finish:

- character creation and the prologue;
- Mist Field: Glen's camp quest chain, its tutorials (riding, troops, equipment, teleport crystals) and item boxes;
- the missions Grey Fog and Tower;
- returning to fields and towns, saving and reloading, and the Steam-free login.

The quest chain up to level 10 (119 quests) passes the automated playthrough, at the game's own damage numbers.
Live play from Grey Rock on (around level 6) hasn't been proven on this version yet, so expect rough edges from
there. Please report what breaks (see [Reporting a problem](#reporting-a-problem)).

## What you need

| | |
|---|---|
| Windows | 10 or 11, 64-bit |
| The game | Kingdom Under Fire 2 installed through Steam: the last build, 4766023 |
| Steam | running and logged in, for your first login (it creates your local account); after that the game can start without Steam |
| Python | 3.11 or newer, 64-bit, from [python.org](https://www.python.org/downloads/windows/) (keep the "py launcher" option ticked). Playing needs no extra packages |
| DirectX | the [DirectX End-User Runtimes (June 2010)](https://www.microsoft.com/en-us/download/details.aspx?id=8109), if the game doesn't start (a fresh Windows lacks them) |
| Two small DLLs | prebuilt on the [Releases](../../releases) page, or built by you (below) |

## Install

1. Get this project: **Code → Download ZIP** and unzip it anywhere, or `git clone` it.
2. Put the two DLLs in place, either way:
   - **Prebuilt:** from the latest release, put `eac_stub.dll` in `stub\eac\build\` and `gameforge_api64.dll` in
     `stub\platform\build\` (create the `build` folders). The release lists their SHA-256 checksums.
   - **Built yourself:** install [Build Tools for Visual Studio](https://visualstudio.microsoft.com/downloads/)
     with the "Desktop development with C++" workload (any Visual Studio 2017 or newer with it works too), then
     double-click `stub\eac\build.cmd` and `stub\platform\build.cmd`.

The server finds the game through Steam's own list of library folders, wherever your library is.

## Play

Open two Command Prompt (or PowerShell) windows in the project folder.

1. **Start the server**, and leave it running:

   ```
   py server\main.py
   ```

2. **Start the game**, with Steam running:

   ```
   py tools\launch.py
   ```

3. In the game, pick the server **(EU) Curian**, create a character, and play. Your character starts in the prologue.

The first time you enter each map, loading pauses for ten seconds or more while the server reads that map from the
game's files. After that it's cached in `server\data\zones\`.

Your save is `server\data\db.json`. Back it up by copying it while the server is stopped.

To stop, close the game, then press **Ctrl+C** in the server's window.

### Without Steam

Once you've logged in through Steam a single time, the game can start with Steam closed:

```
py tools\launch.py --offline-account 1
```

`1` is your local account: the first one, created by your first Steam login. Each account's `id` is in
`server\data\db.json`.

### Options

| Command | What it does |
|---|---|
| `py server\main.py --game "D:\Games\Kingdom Under Fire 2"` | use the game in that folder, when Steam doesn't list it (give the launcher the same `--game`) |
| `py server\main.py --hero-damage 5` | multiply your hero's damage to enemy troops (default `1`, the game's own; `0.5` halves it) |
| `py tools\launch.py --offline-account N` | start without Steam, as saved account `N` |
| `py tools\launch.py --restore-eac` | put the game's original `EasyAntiCheat_x64.dll` back |
| `py tools\launch.py --restore-platform` | put the game's original `gameforge_api64.dll` back |

## What it changes in your game folder

`tools\launch.py` changes two files in the game's folder. The first time it touches each one, it keeps the original
beside it (`.orig`), and only if it's the original from build 4766023 (it checks the checksum):

- `EasyAntiCheat\EasyAntiCheat_x64.dll` becomes a stub that tells the game anti-cheat started (it can't run without
  the official servers). The stub writes a small `EasyAntiCheat\eac_stub.log`.
- `gameforge_api64.dll` is swapped only in Steam-free mode, for an adapter that logs the game in to your local server.
  A normal launch puts the original back.

Nothing else is changed: no system files, no hosts file, no registry, no firewall rule.

**To undo everything:** run `py tools\launch.py --restore-eac` and `py tools\launch.py --restore-platform`, or use
Steam's **Properties → Installed Files → Verify integrity of game files**. Then delete the `.orig` files and
`eac_stub.log` if you like.

## Troubleshooting

| What you see | What to do |
|---|---|
| `Kingdom Under Fire 2 not found` | Steam doesn't list the game: pass `--game "<the game's folder>"` to both the server and the launcher |
| `... is neither the recorded original nor backed up; refusing to overwrite` | your DLL isn't build 4766023's: verify the game's files in Steam, then try again |
| `missing ...eac_stub.dll` | step 2 of [Install](#install) |
| The game says it can't reach the server | start `py server\main.py` first, and keep its window open |
| The server stops with an "address already in use" error | another program uses port 25002, 25003 or 25004: close it (or the server you already started) |
| The game doesn't start at all | install the DirectX June 2010 runtimes (above) |
| Antivirus flags a DLL | they're unsigned. Build them yourself from the source in `stub\` (two short C files) |
| `captures\` keeps growing | it holds the server's logs and packet traces; delete it whenever the server is stopped |

## Reporting a problem

Open an issue with what you did, what you expected and what happened, plus:

- `captures\logs\server_<time>.log` from that session (the server's log);
- `captures\journal\<time>.jsonl` from the same session (the meaning-level events: quests, steps, loot, warps).

They're plain text. They name your local account number, not your Steam ID or name, and they show your user folder
as `~` in file paths. Don't attach your save (`server\data\db.json`) or the packet traces (`captures\*_<time>.log`):
they hold your Steam ID and name. Don't paste the server's window either: its error tracebacks show full file paths.

## Running the tests

The tests read the game's tables from your install, so the game must be installed.

```
py -m pip install -r requirements-dev.txt
py tools\recon\cutscenes.py
py -m pytest server\tests
```

`tools\recon\cutscenes.py` builds `planning\scripts\cutscenes.json` (the missions' cutscene scripts) from your install,
once; some tests compare the scenes against it.

Add `--game "<the game's folder>"` if Steam doesn't list it. The first run takes a while (about 20 minutes), because
it reads every map it needs from the game's files; later runs take under a minute.

## How it works

The game client talks to three servers: login (port 25002), world (25003) and game (25004), all on `127.0.0.1`. The
launcher starts `KUF2.exe` with the same command line Steam's launcher passes, but pointing at `127.0.0.1` instead of
the official login server. The server (`server\kuf2\`, plain Python, no packages) answers the client's packets the way
the original servers did, reading the game's own tables and maps from `Packages\*.pkg`. Missions follow the original's
scripts as tables in `server\kuf2\scenes\`.

## License

[GPL-3.0](LICENSE). You may use, change and share this code. If you share a changed version, share its source under
the same licence.

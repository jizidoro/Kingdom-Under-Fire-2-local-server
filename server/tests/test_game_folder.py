"""Where the game is: Steam's library list (tools/pkg.py steam_install), or a --game folder; and the server's options."""
import importlib.util
import pathlib

import pytest

from kuf2 import combat
from kuf2.tables import pkg

ROOT = pathlib.Path(__file__).resolve().parents[2]

LIBRARIES = r'''"libraryfolders"
{
	"0"
	{
		"path"		"%s"
		"apps"
		{
			"228980"		"1"
		}
	}
	"1"
	{
		"path"		"%s"
		"apps"
		{
			"1132210"		"25178419565"
		}
	}
}
'''


def game_in(lib, name="Kingdom Under Fire 2"):
    g = lib / "steamapps" / "common" / name
    (g / "Packages").mkdir(parents=True)
    (g / "Packages" / "Info.pkg").write_bytes(b"")
    return g


def steam(tmp_path, *libs):
    s = tmp_path / "Steam"
    (s / "steamapps").mkdir(parents=True)
    paths = [str(p).replace("\\", "\\\\") for p in libs]
    (s / "steamapps" / "libraryfolders.vdf").write_text(LIBRARIES % tuple(paths))
    return s


def test_the_game_is_found_in_the_library_steam_lists_it_in(tmp_path):
    main, other = tmp_path / "Steam", tmp_path / "D" / "Games"
    game = game_in(other)
    s = steam(tmp_path, main, other)
    assert pkg.steam_libraries(s) == [other, main]                   # the one listing 1132210 first
    assert pkg.steam_install(s) == game


def test_the_manifests_install_folder_is_used(tmp_path):
    lib = tmp_path / "Lib"
    game = game_in(lib, "KUF2")
    (lib / "steamapps" / "appmanifest_1132210.acf").write_text('"AppState"\n{\n\t"appid"\t\t"1132210"\n\t"installdir"\t\t"KUF2"\n}\n')
    assert pkg.steam_install(steam(tmp_path, tmp_path / "Steam", lib)) == game


def test_a_library_list_in_the_pre_2021_format_is_read(tmp_path):
    # adversarial 2026-11-05: "LibraryFolders" holding plain "1" "<path>" values (Steam's format before mid-2021)
    lib = tmp_path / "D"
    game = game_in(lib)
    s = tmp_path / "Steam"
    (s / "steamapps").mkdir(parents=True)
    (s / "steamapps" / "libraryfolders.vdf").write_text(
        '"LibraryFolders"\n{\n\t"TimeNextStatsReport"\t\t"1"\n\t"ContentStatsID"\t\t"2"\n\t"1"\t\t"%s"\n}\n'
        % str(lib).replace("\\", "\\\\"))
    assert pkg.steam_install(s) == game


def test_no_install_is_none_and_use_game_names_the_folder(tmp_path):
    assert pkg.steam_install(steam(tmp_path, tmp_path / "Steam", tmp_path / "Empty")) is None
    with pytest.raises(SystemExit, match="not found"):
        pkg.use_game(tmp_path / "nowhere")


def test_a_game_folder_given_by_hand_is_taken(tmp_path, monkeypatch):
    monkeypatch.setattr(pkg, "GAME", pkg.GAME)
    game = game_in(tmp_path / "Lib")
    assert pkg.use_game(str(game)) == game and pkg.GAME == game


def test_the_servers_options_set_the_game_and_the_hero_damage(monkeypatch):
    spec = importlib.util.spec_from_file_location("server_main", ROOT / "server" / "main.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    monkeypatch.setattr(pkg, "GAME", pkg.GAME)
    found = pkg.GAME
    main.options([])
    assert combat.HERO_DAMAGE_SCALE == 1 and pkg.GAME == found      # the game's own damage by default
    main.options(["--hero-damage", "10000", "--game", str(found)])
    assert combat.HERO_DAMAGE_SCALE == 10000
    main.options(["--hero-damage", "0.5"])
    assert combat.HERO_DAMAGE_SCALE == 0.5
    for bad in ("0", "-1", "inf", "nan"):                          # inf / nan ended in a traceback (adversarial)
        with pytest.raises(SystemExit):
            main.options(["--hero-damage", bad])

"""Recovery checks use fake DLLs and an isolated save, never the installed game."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('local_launcher', Path(__file__).resolve().parents[2] / 'tools/launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


@pytest.fixture
def files(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    game.mkdir()
    dll = game / 'gameforge_api64.dll'
    dll.write_bytes(b'original')
    backup = game / 'gameforge_api64.dll.orig'
    adapter = tmp_path / 'stub/platform/build/gameforge_api64.dll'
    adapter.parent.mkdir(parents=True)
    adapter.write_bytes(b'adapter')
    save = tmp_path / 'server/data/db.json'
    save.parent.mkdir(parents=True)
    save.write_text(json.dumps({'accounts': {'a': {'id': 7}}}))
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    monkeypatch.setattr(launch, 'GAME', game)
    monkeypatch.setattr(launch, 'PLATFORM_ORIGINAL_SHA', hashlib.sha256(b'original').hexdigest())
    return dll, backup, save


def test_install_is_repeatable_and_restore_recovers_missing_dll(files):
    dll, backup, save = files
    before = save.read_bytes()
    launch.install_local_platform(7)
    launch.install_local_platform(7)
    assert dll.read_bytes() == b'adapter' and backup.read_bytes() == b'original'
    dll.unlink()
    launch.restore_platform()
    assert dll.read_bytes() == b'original' and save.read_bytes() == before


@pytest.mark.parametrize('case', ['unknown-dll', 'bad-backup', 'unknown-account', 'duplicate-account'])
def test_install_refuses_ambiguous_or_unrecoverable_state(files, case):
    dll, backup, save = files
    if case == 'unknown-dll':
        dll.write_bytes(b'unknown')
    if case == 'bad-backup':
        backup.write_bytes(b'unknown')
    if case == 'duplicate-account':
        save.write_text(json.dumps({'accounts': {'a': {'id': 7}, 'b': {'id': 7}}}))
    before = dll.read_bytes()
    with pytest.raises(ValueError):
        launch.install_local_platform(8 if case == 'unknown-account' else 7)
    assert dll.read_bytes() == before


def test_steam_free_before_any_save_or_adapter_says_what_to_do(files):
    # adversarial 2026-11-05: --offline-account before the first Steam login, or without the adapter, ended in a raw
    # FileNotFoundError traceback; the launcher's command line prints these messages on one line
    dll, backup, save = files
    adapter = launch.ROOT / 'stub/platform/build/gameforge_api64.dll'
    adapter.unlink()
    with pytest.raises(FileNotFoundError, match='platform.build.cmd'):
        launch.install_local_platform(7)
    save.unlink()
    with pytest.raises(ValueError, match='log in through Steam once'):
        launch.install_local_platform(7)
    assert dll.read_bytes() == b'original' and not backup.exists()


def test_steam_launch_preserved_and_local_launch_stays_loopback():
    assert launch.game_args() == '#127.0.0.1#25002#gf#steam#b'
    assert launch.game_args(offline_account=7) == '#127.0.0.1#25002#gf#offline:7'
    for kw in ({'host': '192.168.1.2'}, {'port': 80}, {'offline_account': 0}, {'offline_account': 1.5}):
        with pytest.raises(ValueError):
            launch.game_args(**({'offline_account': 7} | kw))

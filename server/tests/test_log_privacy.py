"""The server log and the journal are what players attach to public issues (README, Reporting a problem): file paths in
them show the home folder, which holds the Windows user name, as ~."""
import json
import logging
import pathlib

from kuf2 import net

HOME = pathlib.Path(r"D:\Profiles\Jane Doe")                       # a profile folder named after its user


def test_a_traceback_in_the_journal_and_the_log_shows_the_home_folder_as_tilde(tmp_path, monkeypatch):
    # adversarial 2026-11-05: a traceback through the standard library named the profile folder's AppData\Local
    # \Programs\Python\... (python.org's default install) in both files, and the project's own files in Downloads
    monkeypatch.setattr(net, "HOME", str(HOME))
    monkeypatch.setattr(net, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(net, "LOGS_DIR", tmp_path / "logs")
    path = net.open_journal()
    try:
        tb = (f'  File "{HOME}\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\json\\decoder.py", line 345\n'
              f'  File "d:\\profiles\\jane doe\\Downloads\\server\\kuf2\\game.py", line 9\n')    # any case
        net.journal("error", text="handler failed", tb=tb)
        logging.getLogger("kuf2").warning("refused: %s", HOME / "x")
    finally:
        net.close_journal()
    journal = path.read_text(encoding="utf-8")
    log = next((tmp_path / "logs").glob("server_*.log")).read_text(encoding="utf-8")
    for text in (journal, log):
        assert "jane doe" not in text.lower(), text
    [error] = [e for e in map(json.loads, journal.splitlines()) if e["k"] == "error"]
    assert error["tb"].count('File "~\\') == 2
    assert net.private(str(HOME / "Downloads" / "kuf2")) == "~\\Downloads\\kuf2"

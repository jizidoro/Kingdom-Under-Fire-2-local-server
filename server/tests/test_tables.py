"""kuf2.tables: the %Name sections of the game's data tables, as the client's own loader reads them."""
from kuf2 import quest, tables


def test_utf8_text_without_a_bom_reads_as_utf8():
    # textquest_eng and the maps' English missiontext are UTF-8 without a BOM. Read as cp949, "’" (E2 80 99) and the
    # letter after it came out as two U+FFFD and a Hangul syllable: the server's log named quest 1150802 "Golden
    # Hammer��셲 Apprentice" (captures/logs/server_20260930_000627.log, 00:53:14), the tape's corpus read "Let��셲"
    assert quest.title(1150802) == "Golden Hammer’s Apprentice"
    rows = {r["textID"]: r["text"] for r in tables.sections(r"missiontext\eng\1_towerofmoonlight")["TextTable"]}
    assert rows["1060"] == "I see destroyed buildings ahead of us.<br>Let’s move forward."
    assert not any("�" in t for t in rows.values())


def test_cp949_tables_keep_their_korean():
    # trooptype, nptrooptable, leadertable and 39 more tables are cp949 (strict UTF-8 fails on them): read as before
    assert any(r["StringID"] == "데이터없음" for r in tables.load("trooptype"))
    assert tables.pkg.text("데이터없음".encode("cp949")) == "데이터없음"
    assert tables.pkg.text("﻿é".encode("utf-8")) == "é"          # a BOM: UTF-8, the BOM dropped
    assert tables.pkg.text("Stärke".encode("utf-8")) == "Stärke"      # also valid cp949 ("St채rke"): UTF-8 first


def test_a_section_without_a_types_row_keeps_its_first_row():
    # %TextTable,18,3 has no "WithParamTypes": its data starts right after the column row. The reader skipped a row
    # there, so every such table lost its first line (the rules builder, 2026-09-29: the Goblin Nest's title 10000)
    rows = tables.sections(r"missiontext\eng\1_goblindungeon")["TextTable"]
    assert len(rows) == 18
    assert rows[0] == {"textID": "10000", "text": "Golden Goblin Nest", "repeat": "True"}


def test_a_typed_section_skips_its_types_row():
    # "%Name,rows,cols,WithParamTypes": the column row, then the types row, then the data
    rows = tables.sections("nptrooptable")["Contents"]
    assert all(r["NPTROOP_ID"] != "Int32" for r in rows)
    assert rows[0]["NPTROOP_ID"].isdigit()

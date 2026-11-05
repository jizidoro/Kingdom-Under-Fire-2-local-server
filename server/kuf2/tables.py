"""Game data tables for the server, read from the installed game's Packages/Info.pkg (roadmap O7; reader tools/pkg.py).

A table is data/info/<name>.csv (UTF-8, a few cp949: pkg.text): a '%Name,ncols,...' line, column names, column
types, then rows.
"""
import csv, functools, io, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import pkg  # noqa: E402


@functools.cache
def sections(name):
    """{section name: rows as dicts} for every '%Name,...' section of data/info/<name>.csv (read once, ~0.4 s)."""
    return by_hash(pkg.name_hash(f"data\\info\\{name}.csv"), name)


@functools.cache
def by_hash(h, name=None):
    """sections() of the Info.pkg entry with package hash h: the tables no name list has (INVENTORY "Unnamed tables
    found by a content crawl"), e.g. by_hash(0x23593bf19b78f161)["Table"], the drop categories."""
    p = pkg.Pkg(pkg.GAME / "Packages" / "Info.pkg")
    e = next((e for e in p.entries if e["hash"] == h), None)
    if e is None:
        raise KeyError(f"Info.pkg has no data\\info\\{name}.csv" if name else f"Info.pkg has no entry {h:#018x}")
    text = pkg.text(p.read(e))                 # UTF-8 (BOM or not), else cp949: read as cp949, U+2019 (E2 80 99)
    #                                            became two U+FFFD and a Hangul syllable (quest 1150802's title)
    rows = list(csv.reader(io.StringIO(text)))
    out, i = {}, 0
    while i < len(rows):
        r = rows[i]
        if r and r[0].startswith("%"):
            cols = rows[i + 1]                  # then a types row only when the header says WithParamTypes: an
            j = i + 3 if "WithParamTypes" in r else i + 2    # untyped table (%TextTable,18,3) lost its first row
            data = []
            while j < len(rows) and not (rows[j] and rows[j][0].startswith("%")):
                if len(rows[j]) == len(cols):
                    data.append(dict(zip(cols, rows[j])))
                j += 1
            out.setdefault(r[0][1:], data)
            i = j
        else:
            i += 1
    return out


@functools.cache
def load(name):
    """Rows of the first section of data/info/<name>.csv as dicts keyed by column name (INVENTORY section 5)."""
    return next(iter(sections(name).values()))


@functools.cache
def by_id(name):
    return {r["ID"]: r for r in load(name)}

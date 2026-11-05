"""The original's content settings (ORIGINAL-RULES-PLAN B, ROADMAP Q20): Info.pkg's unnamed %Content table (hash
0x875e939056a99d9d, INVENTORY "Unnamed tables found by a content crawl"), 62 settings (ContentName) by publisher:
DEV, CHANGYOU, INNOVA, GAMEFORGE. The Steam build is GAMEFORGE's: its exe compiles that column in (the built-in config
init 0x140a92160 fills the settings object [0x1508c0f28] from string constants such as "_GAMEFORGE", NationCode
"10000" and Event_Diary "20191114", the last one GAMEFORGE's alone; planning/client/settings.md maps each setting to
its client field and to its consumer here). A server rule that duplicates a setting reads it from here.

  get(name)       the value the server uses: GAMEFORGE's, or OVERRIDES' where the Steam game is known to differ;
                  an int or a float when the text is one, else the text
  original(name)  GAMEFORGE's own text, as the table holds it
"""
import functools

from . import tables

CONTENT = 0x875e939056a99d9d    # the Info.pkg entry of %Content
PUBLISHER = "GAMEFORGE"         # the Steam build's column (above)

# Settings where the Steam game is known to differ from its column: {name: (value, evidence)} (plan falsifier F3).
OVERRIDES = {
    "UseCubic": ("1", "GAMEFORGE says 0, but the Steam build had Cubic: the Cubic shop sold hero troops for 15,000 "
                      "Cubic and Reset Entry for ~120 (planning/reference/OFFICIAL-NOTES.md, ROADMAP Q20). The exe "
                      "agrees: both enchant windows get _root.g_nUseCubic = 1.0, a constant (0x140990d19, 0x1409934b9; "
                      "the double at 0x142935208: the 'Use Cubic' box, not the luck-stone one), while the settings "
                      "byte its init fills from UseCubic's '0' (+0x3cf, inferred from the order) has no reader."),
}


@functools.cache
def column():
    """{setting: GAMEFORGE's text} of all 62 settings."""
    return {r["ContentName"]: r[PUBLISHER] for r in tables.by_hash(CONTENT)["Content"]}


def original(name):
    col = column()
    if name not in col:
        raise KeyError(f"%Content has no setting {name!r}")
    return col[name]


def get(name):
    text = OVERRIDES[name][0] if name in OVERRIDES else original(name)
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text

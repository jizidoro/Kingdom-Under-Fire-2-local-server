"""A mission's director table as Lua (VIDEO-HARNESS-PLAN step 2, Lua format B): a small subset of Lua the owner reads
and edits, parsed back into the director's steps (director.py's docstring lists the triggers and actions). No Lua
engine runs it: `emit` prints a table, `parse` / `load` read one, and director.mission loads scenes/m<spot>.lua over
the .py table when that file exists.

    -- a comment; --[[ a block ]] too
    local GLEN = "글렌_1"                  -- an alias, above its first use: a value, or {a table of values}
    Mission{hold = {20100, 35000}, escort = {GLEN}, hand = {10100}, win = "table",
            panel = {title = 500700, groups = {{110, {120, 121}}}}}
    Step("hero", On.Key{keys = {InputEvent.KEY_SelectTroop1}, needs = "select hero"}, function()
      RTS.System_FinishTutorial()
      RTS.Gui_CompleteObjectiveToMissionSituation(210)
    end)
    Step(On.After{step = "scouts", seconds = 12}, function() RTS.Gui_ShowNoticeWindow(8000, 8010) end)
    Step("select hero", On.Cond{cond = {Cond.TutorialPast, "133_SelectHero", 1}, needs = "lesson1"})

Step([id,] trigger[, body]): no id, a step no other names; no body, a step that only gates others. Mission{...}: the
table's settings (HOLD, ESCORT, HAND, HAND_LATER, HOLD_PROPS, PANEL, WIN, NEXT; SETTINGS). Values: numbers (decimal, 0x
hex, a leading -), strings ("..." or '...', Lua's escapes; UTF-8), true / false / nil, {a, b} (a tuple), the aliases,
InputEvent.KEY_* (the client's InputEvent names) and Cond.TutorialPast. A parse error names the file, line and column.

The names, the one mapping both directions read (ACTIONS, TRIGGERS, SETTINGS, INPUT_EVENTS, CONDS):
- an action is a call named as the game names it: RTS.<name> of the client's cutscene Lua
  (planning/scripts/cutscenes.json) where that call is there ("cutscene Lua"), else after the client's script action
  handler MissionScriptMsgHandler::Act<Group><Name> (re/actions.txt, planning/client/mission_script.md) as
  RTS.<Group>_<Name> ("Act handler"); Ours.<Name> where the client has no action for it ("ours"). The arguments are
  the director's, in its order (say takes (speaker, line[, seconds]), not the client's five values);
- a trigger is ours, On.<Name>{field = value, ...}; any takes needs = "step id" and repeats = true (the director's
  "repeat", a Lua keyword)."""
import re

CUTSCENE, HANDLER, OURS = "cutscene Lua", "Act handler", "ours"

# director action: (Lua call, where its name comes from, least arguments, most (None: any number))
ACTIONS = {
    "say": ("RTS.System_GuiShowMissionHelpTextByTroopId", CUTSCENE, 2, 3),
    "wake": ("RTS.Troop_EnableForce", CUTSCENE, 1, None),
    "spawn": ("RTS.Troop_EnableTroop", CUTSCENE, 1, None),
    "leave": ("RTS.Troop_DisableTroop", CUTSCENE, 1, 1),
    "march": ("RTS.Troop_MoveToArea", CUTSCENE, 2, 2),
    "move": ("RTS.Troop_SetTroopPosition", CUTSCENE, 2, 3),        # (troop, bound[, {dx, dz}]): the game's is
    "move deck": ("Ours.PlaceDeckTroop", OURS, 2, 3),           # optional owned actor at a scene's troop mark
    "shoot": ("RTS.Troop_RangeAttack", CUTSCENE, 2, 2),            # (troop, area); the offset is ours
    "tutorial": ("RTS.System_StartTutorial", CUTSCENE, 1, 1),
    "finish": ("RTS.System_FinishTutorial", CUTSCENE, 0, 0),
    "complete": ("RTS.System_CompleteTutorial", CUTSCENE, 0, 0),
    "cutscene": ("RTS.CutScene_PlayCutScene", HANDLER, 2, 2),
    "fade": ("RTS.System_Fade", CUTSCENE, 3, 3),                 # (in, seconds, color), as the native scene script
    "highlight": ("RTS.Gui_SetHighlightArea", HANDLER, 1, 2),
    "highlight troop": ("RTS.Gui_SetHighlightTroop", HANDLER, 1, 3),   # (troop[, on[, seconds]]): the director's order
    "point": ("RTS.Gui_ShowDirectionToTargetArea", HANDLER, 1, 1),
    "notice": ("RTS.Gui_ShowNoticeWindow", HANDLER, 1, 4),
    "banner": ("Ours.CentreNotice", OURS, 1, 4),               # ActGuiShowNoticeWindow on NoticeTable 6 (centred)
    "panel": ("RTS.Gui_AddTextOnlyObjectiveToMissionSituation", HANDLER, 2, 2),
    "count": ("RTS.Gui_AddValueObjectiveToMissionSituation", HANDLER, 3, 3),
    "clock": ("RTS.Gui_AddTimeObjectiveToMissionSituation", HANDLER, 3, 3),   # (group, text, seconds)
    "gauge": ("RTS.Gui_AddGageObjectiveToMissionSituation", HANDLER, 3, 3),
    "done": ("RTS.Gui_CompleteObjectiveToMissionSituation", HANDLER, 1, 1),
    "state": ("RTS.Camera_SetCamera", HANDLER, 1, 1),              # ActCameraSetCamera(-n) releases WaitState(n)
    "camera troop": ("Ours.FollowTroopCamera", OURS, 2, 2),       # attach axis 5, then select the shipped preset
    "untouchable troop": ("Ours.UntouchableTroop", OURS, 2, 2),  # native ref(0, uid), on + server damage flag
    "troops bar": ("RTS.Gui_AddTroopsBarToMissionSituation", HANDLER, 2, 2),   # (text, troop): ref(0, uid), a6 uid
    "force bar": ("Ours.ForceTroopsBar", OURS, 2, 2),           # (text, force): the same action, ref(2, force)
    "panel start": ("Ours.MissionPanel", OURS, 0, 0),           # the start panel now (Mission{panel} or the map's)
    "hand": ("RTS.Troop_ChangeForce", HANDLER, 1, 1),
    "open": ("Ours.Open", OURS, 1, 1),                              # a prop record in its open state (game.switch_on)
    "heal": ("Ours.Heal", OURS, 0, 1),
    "escort": ("Ours.Escort", OURS, 1, None),
    "route": ("Ours.Route", OURS, 2, 3),                          # (troop, MissionPath[, exit bound]): 0x5083 path 1
    "win": ("Ours.Win", OURS, 0, 0),
    "clock off": ("RTS.Gui_RemoveObjectiveGroupToMissionSituation", HANDLER, 1, 1),   # (group): 00:00:00, then gone
}
# director trigger: (On.<Name>, its fields as (director key, Lua key, required))
TRIGGERS = {
    "start": ("Start", ()),
    "bound": ("Enter", (("bound", "area", True),)),
    "wake": ("Wake", (("force", "force", True),)),
    "down": ("Down", (("force", "force", False), ("troop", "troop", False))),
    "hp": ("Hp", (("troop", "troop", False), ("force", "force", False), ("below", "below", True), ("by", "by", False))),
    "left": ("Left", (("force", "force", True), ("count", "count", True))),
    "engage": ("Engage", (("force", "force", True), ("by", "by", False))),
    "won": ("Won", ()),
    "closed": ("Closed", ()),
    "after": ("After", (("step", "step", True), ("s", "seconds", False))),
    "skill": ("Skill", (("troop", "troop", True), ("force", "force", True))),
    "cond": ("Cond", (("cond", "cond", True),)),
    "prompt": ("Key", (("keys", "keys", True), ("in", "within", False))),    # "in" is a Lua keyword
    "finish": ("Finish", (("troop", "troop", True),)),
    "broken": ("Broken", (("prop", "prop", True),)),
    "arrive": ("Arrive", (("force", "force", True), ("bound", "area", True))),
    "near": ("Near", (("troop", "troop", True),)),
}
EVERY = (("needs", "needs", False), ("repeat", "repeats", False),      # fields of any trigger
         ("class", "class", False),                                      # (the hero's class only: m50116)
         ("unless", "unless", False))                                    # (a branch not taken: m10303)
# a table's settings (director.mission), in the order printed: module name -> (Mission{} field, kind)
SETTINGS = {"HOLD": ("hold", set), "ESCORT": ("escort", set), "HAND": ("hand", tuple),
            "HAND_LATER": ("hand_later", set), "HOLD_PROPS": ("hold_props", set), "PANEL": ("panel", "panel"),
            "WIN": ("win", str), "NEXT": ("next", int)}
# InputEvent names (the client's enum, re/input_events.txt: value = its line) of the keys the director prompts
INPUT_EVENTS = {
    "KEY_UseAbility1": 0x15, "KEY_UseAbilityC1": 0x23, "KEY_UseAbilityC9": 0x2b, "KEY_ChangeControlMode": 0x30,
    "KEY_ActionKey": 0x32, "KEY_Select_AllTroop": 0x33, "KEY_SelectTroop1": 0x34, "KEY_SelectTroop2": 0x35, "KEY_SelectTroop3": 0x36,
    "KEY_SelectTroop4": 0x37, "KEY_AIOffensive": 0x38, "KEY_AIDefensive": 0x39, "KEY_AIHeroSupport": 0x3a,
    "KEY_SceneToggleDown": 0x3f, "KEY_SceneToggleUp": 0x40, "KEY_MouseRClick": 0x57, "KEY_MouseCameraRotEnd": 0x77,
    "KEY_CameraMoveForward": 0x7c, "KEY_CameraMoveBack": 0x7d, "KEY_CameraMoveLeft": 0x7e,
    "KEY_CameraMoveRight": 0x7f, "KEY_SelectTarget": 0x81, "KEY_Interaction": 0x83, "KEY_DefensiveMove": 0x84,
    "KEY_UseRuneAbilitySpecialKey": 0x44,     # the prologue's rune lessons (1_AziliaCastle 12_Azilia_Reg_R)
    "KEY_Pad_A_Press": 0x06, "KEY_Pad_X_Press": 0x07, "KEY_Pad_X_Hold": 0x96, "KEY_UseAbilitySpecialKey1": 0x08,
    "KEY_UseAbilitySpecialKey2": 0x09, "KEY_UseAbility2": 0x16, "KEY_UseAbility3": 0x17, "KEY_UseAbility4": 0x18,
    "KEY_UseAbility5": 0x19, "KEY_UseAbility6": 0x1a, "KEY_UseAbility7": 0x1b, "KEY_UseAbility8": 0x1c,
    "KEY_ActionKey": 0x32, "KEY_FriendAndFoe": 0x43}    # the prologue's other lessons (m50116)
# conditions (S2C 0x5086) by name: ours, the client has none for 0xcb2b (mission_script.md §5.1; director
# COND_TUTORIAL_PAST)
CONDS = {"TutorialPast": 0xcb2b}
GLOBALS = ("RTS", "Ours", "On", "Step", "Mission", "InputEvent", "Cond")

ACTION_BY_CALL = {call: kind for kind, (call, _, _, _) in ACTIONS.items()}
TRIGGER_BY_NAME = {name: kind for kind, (name, _) in TRIGGERS.items()}
KEY_NAMES = {v: k for k, v in INPUT_EVENTS.items()}
COND_NAMES = {v: k for k, v in CONDS.items()}


class LuaError(ValueError):
    """A script outside the subset: "<file>:<line>:<column>: what"."""

    def __init__(self, source, line, col, what):
        super().__init__(f"{source}:{line}:{col}: {what}")
        self.source, self.line, self.col = source, line, col


# ---- printing ----

def emit(steps, spot, settings=None, names=None, texts=None, notes=None, head=None):
    """A mission's Lua: its settings ({"HOLD": ..., ...}, SETTINGS) in Mission{}, then one Step per step. names
    {string: NAME}: those strings written as NAME, each `local NAME = "string"` at the top (py_names); texts {line id:
    text}: a said, noticed or panel line's text as a comment after its call (director.lines); notes [[comment line,
    ...] per step]: comments above each step (the video harness's evidence); head [comment line, ...]: the file's
    heading in place of the table printer's."""
    names, texts, used, notes, heading = names or {}, texts or {}, {}, notes or [], head

    def value(v, key=None):
        if isinstance(v, bool):
            return "true" if v else "false"
        if v is None:
            return "nil"
        if isinstance(v, int) and key == "keys" and v in KEY_NAMES:
            return "InputEvent." + KEY_NAMES[v]
        if isinstance(v, int) and key == "cond":                    # a condition id: by name, else in hex as the
            return "Cond." + COND_NAMES[v] if v in COND_NAMES else hex(v)     # client docs write it
        if isinstance(v, (int, float)):
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError(f"mission {spot}: {v!r} has no Lua numeral")
            return repr(v)
        if isinstance(v, str):
            if v in names:
                used[v] = names[v]
                return names[v]
            return quote(v)
        if isinstance(v, (tuple, list, set, frozenset)):
            items = sorted(v, key=lambda x: (isinstance(x, str), x)) if isinstance(v, (set, frozenset)) else v
            return "{" + ", ".join(value(x, key if (key != "cond" or i == 0) else None)
                                   for i, x in enumerate(items)) + "}"
        raise ValueError(f"mission {spot}: {v!r} has no Lua form")

    body = []
    if settings:
        rows = []
        for name, (field, kind) in SETTINGS.items():
            if name not in settings:
                continue
            v = settings[name]
            if kind == "panel":
                title, groups = v
                v = "{" + ("" if title is None else f"title = {value(title)}, ") + f"groups = {value(groups)}}}"
            else:
                v = value(v)
            rows.append(f"  {field} = {v},")
        body += ["Mission{", *rows, "}", ""]
        unknown = set(settings) - set(SETTINGS)
        if unknown:
            raise ValueError(f"mission {spot}: no Lua name for the settings {sorted(unknown)}")
    for k, st in enumerate(steps):
        body += [re.sub(r"\s+", " ", "-- " + str(n)).rstrip() for n in (notes[k] if k < len(notes) else None) or ()]
        kind = st["on"]
        if kind not in TRIGGERS:
            raise ValueError(f"mission {spot}: no Lua name for the trigger {kind!r}")
        name, fields = TRIGGERS[kind]
        known = {"on", "id", "do"} | {k for k, _, _ in fields + EVERY}
        if set(st) - known:
            raise ValueError(f"mission {spot}: no Lua name for the step fields {sorted(set(st) - known)}: {st}")
        kv = ", ".join(f"{lua} = {value(st[key], key)}" for key, lua, _ in fields + EVERY if key in st)
        head = ([quote(st["id"])] if "id" in st else []) + [f"On.{name}{{{kv}}}"]
        if "do" not in st:
            body.append(f"Step({', '.join(head)})")
            continue
        body.append(f"Step({', '.join(head)}, function()")
        for a in st["do"]:
            if a[0] not in ACTIONS:
                raise ValueError(f"mission {spot}: no Lua name for the action {a!r}")
            line = f"  {ACTIONS[a[0]][0]}({', '.join(value(x) for x in a[1:])})"
            said = {"say": 2, "notice": 1, "panel": 2, "done": 1}.get(a[0])
            if said and len(a) > said and texts.get(a[said]):
                line += "  -- " + re.sub(r"\s*(<br>|\r?\n)\s*", " / ", str(texts[a[said]]), flags=re.I).strip()
            body.append(line)
        body.append("end)")
    head = ["-- " + h for h in heading] if heading else [
        f"-- Mission {spot}: the director's steps as Lua (server/kuf2/lua_script.py). RTS.* are the game's names "
        "(its cutscene Lua's calls,", "-- else its script handlers' Act<Group><Name>), Ours.* the server's own, "
        "On.* our triggers; the arguments are the director's."]
    aliases = [f"local {n} = {quote(v)}" for v, n in names.items() if v in used]
    return "\n".join(head + ([""] + aliases if aliases else []) + [""] + body) + "\n"


def quote(s):
    """A Lua string literal of s (double quotes; control characters as \\ddd)."""
    out = []
    for c in s:
        if c in '"\\':
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 32 or ord(c) == 127:
            out.append("\\%03d" % ord(c))
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def py_names(mod):
    """{string: NAME} of a scenes .py module's upper-case string constants (GLEN = "글렌_1"), the aliases emit writes."""
    out = {}
    for k, v in vars(mod).items():
        if (isinstance(v, str) and k.isupper() and k.isascii() and k.isidentifier() and not k.startswith("_")
                and k not in SETTINGS and k not in GLOBALS and v not in out):
            out[v] = k
    return out


# ---- reading ----

_NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LONG = re.compile(r"\[(=*)\[")
_DIGITS = "0123456789"
_DEC, _HEX2, _UTF8 = re.compile(r"[0-9]{1,3}"), re.compile(r"[0-9a-fA-F]{2}"), re.compile(r"\{([0-9a-fA-F]+)\}")
_ESCAPES = {"n": b"\n", "t": b"\t", "r": b"\r", "a": b"\a", "b": b"\b", "f": b"\f", "v": b"\v", "\\": b"\\",
            '"': b'"', "'": b"'", "\n": b"\n"}
_WORDS = {"true": True, "false": False, "nil": None}
_NOT_IN_SUBSET = {"and", "break", "do", "else", "elseif", "for", "goto", "if", "in", "not", "or", "repeat", "return",
                  "then", "until", "while"}
_OURS_WORDS = {"local", "function", "end"}                  # the subset's own keywords


class _Tab:
    """A table constructor as read: [(key or None, value, pos)]."""

    def __init__(self, items, pos):
        self.items, self.pos = items, pos


class _Trigger:
    def __init__(self, name, tab, pos):
        self.name, self.tab, self.pos = name, tab, pos


class _Body:
    def __init__(self, actions, pos):
        self.actions, self.pos = actions, pos


class _Reader:
    def __init__(self, text, source):
        self.text, self.source = text, source
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", text)]
        self.toks = self.tokens()
        self.i = 0
        self.locals = {}

    def fail(self, pos, what):
        line = next(n for n in range(len(self.starts), 0, -1) if self.starts[n - 1] <= pos)
        raise LuaError(self.source, line, pos - self.starts[line - 1] + 1, what)

    # tokens: (kind, value, pos), kind name / number / string / op / eof
    def tokens(self):
        t, i, out = self.text, 0, []
        while i < len(t):
            c = t[i]
            if c in " \t\r\n\f\v":
                i += 1
            elif t.startswith("--", i):
                m = _LONG.match(t, i + 2)
                if m:
                    end = t.find("]" + m.group(1) + "]", m.end())
                    if end < 0:
                        self.fail(i, "an unfinished --[[ comment")
                    i = end + len(m.group(1)) + 2
                else:
                    j = t.find("\n", i)
                    i = len(t) if j < 0 else j
            elif c.isascii() and (c.isalpha() or c == "_"):
                m = _NAME.match(t, i)
                out.append(("name", m.group(), i))
                i = m.end()
            elif c in _DIGITS or (c == "." and t[i + 1:i + 2] in tuple(_DIGITS)):
                m = _NUMBER.match(t, i)
                s = m.group()
                v = int(s, 16) if s[:2] in ("0x", "0X") else float(s) if any(x in s for x in ".eE") else int(s)
                out.append(("number", v, i))
                i = m.end()
            elif c in "\"'":
                v, i2 = self.string(i)
                out.append(("string", v, i))
                i = i2
            elif c in "{}(),;=.-":
                out.append(("op", c, i))
                i += 1
            elif c == "[":
                self.fail(i, "[ is not in the subset (no indexing, no [[long strings]])")
            else:
                self.fail(i, f"unexpected {c!r}")
        out.append(("eof", None, len(t)))
        return out

    def string(self, start):
        t, q, i, b = self.text, self.text[start], start + 1, bytearray()
        while True:
            if i >= len(t) or t[i] == "\n":
                self.fail(start, "an unfinished string")
            c = t[i]
            if c == q:
                break
            if c != "\\":
                b += c.encode("utf-8")
                i += 1
                continue
            e = t[i + 1:i + 2]
            if e in _ESCAPES:
                b += _ESCAPES[e]
                i += 2
            elif e and e in _DIGITS:
                m = _DEC.match(t, i + 1)
                if int(m.group()) > 255:
                    self.fail(i, f"escape \\{m.group()} is past 255")
                b.append(int(m.group()))
                i = m.end()
            elif e == "x" and _HEX2.match(t, i + 2):
                b.append(int(t[i + 2:i + 4], 16))
                i += 4
            elif e == "u" and _UTF8.match(t, i + 2):
                m = _UTF8.match(t, i + 2)
                if int(m.group(1), 16) > 0x10FFFF:
                    self.fail(i, f"escape \\u{{{m.group(1)}}} is past U+10FFFF")
                b += chr(int(m.group(1), 16)).encode("utf-8", "surrogatepass")
                i = m.end()
            elif e == "z":
                i += 2
                while i < len(t) and t[i] in " \t\r\n\f\v":
                    i += 1
            else:
                self.fail(i, f"unknown escape \\{e}")
        try:
            return b.decode("utf-8"), i + 1
        except UnicodeDecodeError:
            self.fail(start, "a string that is not UTF-8")

    def peek(self, k=0):
        return self.toks[self.i + k]

    def take(self):
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expect(self, kind, value=None, what=None):
        tok = self.take()
        if tok[0] != kind or (value is not None and tok[1] != value):
            self.fail(tok[2], f"expected {what or repr(value or kind)}, got {self.show(tok)}")
        return tok

    @staticmethod
    def show(tok):
        return "the end of the file" if tok[0] == "eof" else repr(tok[1]) if tok[0] != "string" else "a string"

    def is_op(self, c, k=0):
        tok = self.peek(k)
        return tok[0] == "op" and tok[1] == c

    # the chunk: local aliases, Mission{}, Step(...)
    def chunk(self):
        steps, settings = [], None
        while self.peek()[0] != "eof":
            kind, v, pos = self.take()
            if kind == "name" and v == "local":
                name = self.expect("name", what="a name")
                if name[1] in GLOBALS or name[1] in _WORDS or name[1] in _NOT_IN_SUBSET or name[1] in _OURS_WORDS:
                    self.fail(name[2], f"{name[1]} is a name of the script's, not an alias")
                if name[1] in self.locals:
                    self.fail(name[2], f"alias {name[1]} is set twice")
                self.expect("op", "=")
                val = self.exp()
                self.locals[name[1]] = self.plain(val, name[2])
            elif kind == "name" and v == "Mission":
                if settings is not None:
                    self.fail(pos, "a second Mission{...}")
                settings = self.mission(self.call_table(), pos)
            elif kind == "name" and v == "Step":
                steps.append(self.step(pos))
            elif kind == "op" and v == ";":
                continue
            else:
                self.fail(pos, f"expected local, Mission or Step, got {self.show((kind, v, pos))}"
                          + (" (not in the subset)" if v in _NOT_IN_SUBSET else ""))
        return {"STEPS": steps, **(settings or {})}

    def call_table(self):
        """{...} or ({...})."""
        if self.is_op("("):
            self.take()
            tab = self.exp()
            self.expect("op", ")")
        else:
            tab = self.exp()
        if not isinstance(tab, _Tab):
            self.fail(self.toks[self.i - 1][2], "expected a {table}")
        return tab

    def exp(self):
        kind, v, pos = self.take()
        if kind in ("number", "string"):
            return v
        if kind == "op" and v == "-":
            n = self.exp()
            if isinstance(n, bool) or not isinstance(n, (int, float)):
                self.fail(pos, "- before something that is not a number")
            return -n
        if kind == "op" and v == "{":
            return self.table(pos)
        if kind == "name":
            if v in _WORDS:
                return _WORDS[v]
            if v == "On":
                self.expect("op", ".")
                name = self.expect("name", what="a trigger name")
                if name[1] not in TRIGGER_BY_NAME:
                    self.fail(pos, f"On.{name[1]} is no trigger (On.{', On.'.join(TRIGGER_BY_NAME)})")
                return _Trigger(name[1], self.call_table(), pos)
            if v == "function":
                return self.body(pos)
            if v in ("InputEvent", "Cond"):
                self.expect("op", ".")
                name = self.expect("name", what="a name")
                table = INPUT_EVENTS if v == "InputEvent" else CONDS
                if name[1] not in table:
                    where = "INPUT_EVENTS" if table is INPUT_EVENTS else "CONDS"
                    self.fail(pos, f"{v}.{name[1]} is not known (lua_script.{where})")
                return table[name[1]]
            if v in self.locals:
                return self.locals[v]
            self.fail(pos, f"unknown name {v}" + (" (not in the subset)" if v in _NOT_IN_SUBSET else ""))
        self.fail(pos, f"expected a value, got {self.show((kind, v, pos))}")

    def table(self, pos):
        items, seen = [], set()
        while not self.is_op("}"):
            tok = self.peek()
            if tok[0] == "name" and self.is_op("=", 1) and tok[1] not in _WORDS:
                self.take()
                self.take()
                if tok[1] in seen:
                    self.fail(tok[2], f"field {tok[1]} given twice")
                seen.add(tok[1])
                items.append((tok[1], self.exp(), tok[2]))
            else:
                items.append((None, self.exp(), tok[2]))
            if self.is_op(",") or self.is_op(";"):
                self.take()
            elif not self.is_op("}"):
                tok = self.take()
                self.fail(tok[2], f"expected , or }} in the table, got {self.show(tok)}")
        self.take()
        return _Tab(items, pos)

    def plain(self, v, pos):
        """A value as the director keeps it: a {table} of values a tuple."""
        if isinstance(v, _Tab):
            for key, _, p in v.items:
                if key is not None:
                    self.fail(p, f"a named field ({key} = ...) is not a value here")
            return tuple(self.plain(x, p) for _, x, p in v.items)
        if isinstance(v, (_Trigger, _Body)):
            self.fail(pos, "a trigger or a function is not a value here")
        return v

    def named(self, tab, allowed, what):
        """{Lua key: (value, pos)} of a table of named fields, each one of allowed."""
        out = {}
        for key, v, p in tab.items:
            if key is None:
                self.fail(p, f"{what} takes named fields (name = value)")
            if key not in allowed:
                self.fail(p, f"{what} has no field {key} ({', '.join(allowed) or 'none'})")
            out[key] = (v, p)
        return out

    def mission(self, tab, pos):
        fields = {lua: (name, kind) for name, (lua, kind) in SETTINGS.items()}
        out = {}
        for key, (v, p) in self.named(tab, list(fields), "Mission").items():
            name, kind = fields[key]
            if kind == "panel":
                if not isinstance(v, _Tab):
                    self.fail(p, "panel = {title = id, groups = {{group, {line, ...}}, ...}}")
                got = self.named(v, ["title", "groups"], "panel")
                if "groups" not in got:
                    self.fail(p, "panel needs groups = {{group, {line, ...}}, ...}")
                out[name] = (self.plain(got["title"][0], got["title"][1]) if "title" in got else None,
                             self.plain(*got["groups"]))
            elif kind is str:
                if not isinstance(v, str):
                    self.fail(p, f"{key} takes a string")
                out[name] = v
            elif kind is int:
                if isinstance(v, bool) or not isinstance(v, int):
                    self.fail(p, f"{key} takes a number")
                out[name] = v
            else:
                v = self.plain(v, p)
                if not isinstance(v, tuple):
                    self.fail(p, f"{key} takes a {{table}} of values")
                out[name] = kind(v)
        return out

    def step(self, pos):
        self.expect("op", "(")
        args = []
        while True:
            at = self.peek()[2]
            args.append((self.exp(), at))
            if self.is_op(","):
                self.take()
                continue
            self.expect("op", ")", "',' or ')'")
            break
        sid = None
        if args and isinstance(args[0][0], str):
            sid = args.pop(0)[0]
        if not args or not isinstance(args[0][0], _Trigger):
            self.fail(args[0][1] if args else pos, "Step([id,] On.<Trigger>{...}[, function() ... end])")
        trig = args.pop(0)[0]
        body = args.pop(0) if args else None
        if body is not None and not isinstance(body[0], _Body):
            self.fail(body[1], "after the trigger, only a function() ... end")
        if args:
            self.fail(args[0][1], "a Step takes [id,] On.<Trigger>{...}[, function() ... end], no more")
        kind = TRIGGER_BY_NAME[trig.name]
        fields = TRIGGERS[kind][1] + EVERY
        got = self.named(trig.tab, [lua for _, lua, _ in fields], f"On.{trig.name}")
        st = {"on": kind}
        for key, lua, required in fields:
            if lua in got:
                st[key] = self.plain(*got[lua])
            elif required:
                self.fail(trig.pos, f"On.{trig.name} needs {lua} = ...")
        if sid is not None:
            st["id"] = sid
        if body is not None:
            st["do"] = body[0].actions
        return st

    def body(self, pos):
        self.expect("op", "(")
        self.expect("op", ")", "')' (a step's function takes no arguments)")
        actions = []
        while True:
            kind, v, at = self.take()
            if kind == "name" and v == "end":
                return _Body(actions, pos)
            if kind == "op" and v == ";":
                continue
            if kind == "name" and v in ("RTS", "Ours"):
                self.expect("op", ".")
                name = self.expect("name", what="a call name")[1]
                call = f"{v}.{name}"
                if call not in ACTION_BY_CALL:
                    self.fail(at, f"{call} is not a call the director has (lua_script.ACTIONS)")
                self.expect("op", "(")
                args = []
                while not self.is_op(")"):
                    p = self.peek()[2]
                    args.append(self.plain(self.exp(), p))
                    if not self.is_op(")"):
                        self.expect("op", ",", "',' or ')'")
                self.take()
                a = ACTION_BY_CALL[call]
                least, most = ACTIONS[a][2:]
                if len(args) < least or (most is not None and len(args) > most):
                    n = f"{least}" if least == most else f"{least} or more" if most is None else f"{least} to {most}"
                    self.fail(at, f"{call} takes {n} arguments, not {len(args)}")
                actions.append((a, *args))
                continue
            if kind == "eof":
                self.fail(at, "expected 'end' to close the function, got the end of the file")
            self.fail(at, f"expected an RTS.* or Ours.* call or 'end', got {self.show((kind, v, at))}")


def load(text, source="<lua>"):
    """A mission script's table: {"STEPS": [step, ...], and each setting it sets ("HOLD": {...}, ...)}."""
    return _Reader(text, source).chunk()


def parse(text, source="<lua>"):
    """A mission script's steps, as the director's table has them (STEPS)."""
    return load(text, source)["STEPS"]

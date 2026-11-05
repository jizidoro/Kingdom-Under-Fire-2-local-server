"""KUF2 Packages/*.pkg (BEAR v1.2) reader. Format from Ekey/KUF2.PKG.Tool;
this build has no 16-byte prefix before the BEAR header.

  py tools/pkg.py list Packages/Info.pkg [filter]
  py tools/pkg.py extract Packages/Info.pkg out_dir [filter]
"""
import pathlib, re, struct, sys, zlib

APP_ID = "1132210"                                   # Kingdom Under Fire 2 on Steam


def _vdf(text):
    """A Valve KeyValues text (libraryfolders.vdf, appmanifest_*.acf) as nested dicts."""
    tokens = [(q.replace("\\\\", "\\"), b) for q, b in re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)]
    def block(i):
        out = {}
        while i < len(tokens):
            key, brace = tokens[i]
            if brace == "}":
                return out, i + 1
            if i + 1 < len(tokens) and tokens[i + 1][1] == "{":
                out[key], i = block(i + 2)
            else:
                out[key] = tokens[i + 1][0] if i + 1 < len(tokens) else ""
                i += 2
        return out, i
    return block(0)[0]


def steam_libraries(steam=None):
    """Steam's library folders, the one listing the game first: steam (default: the registry's SteamPath) ->
    steamapps/libraryfolders.vdf."""
    if steam is None:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                steam = winreg.QueryValueEx(k, "SteamPath")[0]
        except OSError:
            return []
    steam = pathlib.Path(steam)
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return [steam]
    top = {k.lower(): v for k, v in _vdf(vdf.read_text(encoding="utf-8", errors="replace")).items()}
    libs = [v if isinstance(v, dict) else {"path": v}               # before mid-2021: "LibraryFolders" {"1" "<path>"}
            for k, v in top.get("libraryfolders", {}).items() if isinstance(v, dict) or k.isdigit()]
    libs = [v for v in libs if v.get("path")]
    libs.sort(key=lambda v: APP_ID not in (v.get("apps") or {}))
    return [pathlib.Path(v["path"]) for v in libs] or [steam]


def steam_install(steam=None):
    """The game's folder in a Steam library (the one holding Packages/Info.pkg), or None."""
    for lib in steam_libraries(steam):
        acf = lib / "steamapps" / f"appmanifest_{APP_ID}.acf"
        name = "Kingdom Under Fire 2"
        if acf.is_file():
            name = _vdf(acf.read_text(encoding="utf-8", errors="replace")).get("AppState", {}).get("installdir") or name
        game = lib / "steamapps" / "common" / name
        if (game / "Packages" / "Info.pkg").is_file():
            return game
    return None


def use_game(path=None):
    """Set GAME to path (a --game argument) or to Steam's install; exits naming where it looked when neither holds
    the game's Packages/Info.pkg."""
    global GAME
    game = pathlib.Path(path) if path else steam_install()
    if game is None or not (game / "Packages" / "Info.pkg").is_file():
        where = str(game) if path else "Steam's libraries: " + (", ".join(map(str, steam_libraries())) or "Steam not found")
        sys.exit(f"Kingdom Under Fire 2 not found ({where}); install it with Steam, or pass --game \"<its folder>\"")
    GAME = game
    return GAME


GAME = steam_install()                               # None until found; the server and launcher call use_game()
NAMES = pathlib.Path(__file__).with_name("FileNames.list")   # optional: Ekey/KUF2.PKG.Tool's name list, not shipped
M64 = (1 << 64) - 1
M32 = (1 << 32) - 1


def _crc_table():
    poly, t = 0x42F0E1EBA9EA3693, []
    for i in range(256):
        c = i << 56
        for _ in range(8):
            c = ((c << 1) ^ poly) & M64 if c & (1 << 63) else (c << 1) & M64
        t.append(c)
    return t


CRC = _crc_table()


def name_hash(s):
    h = M64
    for ch in s:
        h = ((h << 8) & M64) ^ CRC[((h >> 56) ^ (ord(ch) & 0xFF)) & 0xFF]
    return ~h & M64


_names = None


def names():
    global _names
    if _names is None:
        _names = {}
        extra = pathlib.Path(__file__).with_name("pkg_names.txt")   # recovered from the client (recon/pkg_names.py)
        # names from DFKeaton/KUF2.PKG.Tool2014's FileNames_Steam.list and FileNames_2014.list (github, 2026-08-25),
        # kept only where the name, hashed as written (Steam's hash is case-sensitive), is an entry of our packages
        community = pathlib.Path(__file__).with_name("pkg_names_community.txt")
        for src in (NAMES, extra, community):
            if not src.exists():
                continue
            for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line:
                    _names[name_hash(line)] = line
    return _names


class Pkg:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.data = self.path.read_bytes()
        magic, minor, major, count = struct.unpack_from("<IHHq", self.data, 0)
        if magic != 0x52414542 or (minor, major) != (1, 2):
            raise ValueError(f"{path}: not a BEAR 1.2 package")
        self.seed = len(self.data) & M32
        pos = 16
        self.entries = []
        for _ in range(count):
            h, cs, ds, num, res = struct.unpack_from("<QiiiI", self.data, pos)
            pos += 24
            h = (h + self._next()) & M64
            cs = (cs + self._next()) & M32
            ds = (ds + self._next()) & M32
            num = (num + self._next()) & M32
            self._next()
            self.entries.append({"hash": h, "csize": cs, "size": ds, "num": num,
                                 "name": names().get(h, f"unknown/{h:016x}")})
        # chunk table follows the entry table; it is ordered by chunk index (entry "num" = first chunk),
        # not by entry order, and the LCG keeps running through it
        def nchunks(e):
            return max(1, -(-e["size"] // 65536))
        total = max(e["num"] + nchunks(e) for e in self.entries) if self.entries else 0
        table = []
        for _ in range(total):
            off, ccs, cds = struct.unpack_from("<Iii", self.data, pos)
            pos += 12
            off = (off + self._next()) & M32
            ccs = (ccs + self._next()) & M32
            cds = (cds + self._next()) & M32
            if ccs == 0 and cds == 0:
                cds = 65536
            table.append((off, ccs, cds))
        for e in self.entries:
            e["chunks"] = table[e["num"]:e["num"] + nchunks(e)]

    def _next(self):
        self.seed = (self.seed * 0x19660D + 0x3C6EF35F) & M32
        return self.seed

    def read(self, e):
        out = bytearray()
        for off, ccs, cds in e["chunks"]:
            if ccs == 0:
                out += self.data[off:off + cds]
            else:
                out += zlib.decompress(self.data[off:off + ccs])
        return bytes(out[:e["size"]])


def text(b):
    """A text entry's bytes (a data/info table) as text: UTF-8, with or without a BOM, when they are UTF-8, else cp949.
    Info.pkg's tables come three ways (census of its '%' tables, 2026-09-30): UTF-8 with a BOM (2016), UTF-8 without
    one (501: textquest_eng, the maps' missiontext, the European languages' texts) and cp949 (42: trooptype,
    leadertable, nptrooptable, synastry); no cp949 table is valid UTF-8, while 132 UTF-8 ones are valid cp949 too."""
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return b.decode("cp949", errors="replace")


def main():
    cmd, path = sys.argv[1], pathlib.Path(sys.argv[2])
    if not path.is_absolute() and not path.exists():
        path = use_game() / path
    pkg = Pkg(path)
    if cmd == "list":
        pat = re.compile(sys.argv[3], re.I) if len(sys.argv) > 3 else None
        for e in pkg.entries:
            if not pat or pat.search(e["name"]):
                print(f"{e['size']:10d} {e['name']}")
    elif cmd == "extract":
        out = pathlib.Path(sys.argv[3])
        pat = re.compile(sys.argv[4], re.I) if len(sys.argv) > 4 else None
        n, bad = 0, []
        for e in pkg.entries:
            if pat and not pat.search(e["name"]):
                continue
            dst = out / e["name"].replace("\\", "/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                dst.write_bytes(pkg.read(e))
                n += 1
            except zlib.error as ex:
                bad.append((e["name"], e["size"], len(e["chunks"]), str(ex)))
        print(f"extracted {n} files to {out}; {len(bad)} failed")
        for b in bad[:10]:
            print("  FAIL", b)


if __name__ == "__main__":
    main()

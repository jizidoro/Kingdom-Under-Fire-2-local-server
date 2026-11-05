"""Decode BMIF files (map mission data .clt, .dmm, ...) with their text schema (.bmi), CLIENT-MAP-PLAN step 4.

  py tools/recon/bmif.py <schema.bmi> <file> [out.json]

Format (writer 0x141549270 / object writer 0x14154c330 / array writer 0x14154be80, reader 0x141547920):
  "BMIF", u16 version 0x0401, u16 flags, u32 0, u32 n, n type GUIDs (u32 u16 u16 u16 6 bytes),
  u32 pool size, u32 pool count, pool strings (NUL-terminated, padded to 4), then the root object.
  Object: an end-offset table for its variable-size fields (u16 if the object is under 64 KiB, else u32; the last
  field's end is omitted when it is variable), padded to 4; offsets are relative to the start of the fields; then the
  fields in schema order. Strings are 1-based pool indexes (u32; 0 = none). Arrays of fixed-size elements carry no
  count (bytes / size). Arrays of variable-size elements: u32 count, (count - 1) element end offsets (u16/u32 by the
  array's size, padded to 4, relative to the first element), then the elements. ^union arrays add packed variant
  indexes (1-based, ceil(log2(variants + 1)) bits each) in u32 words before that. Checked on
  1_MistField_zone3.clt: start point 0 = (330850, 175236, 200); see tools/recon/README or planning/SYSTEMS.md.
"""
import json, math, re, struct, sys

PRIM = {"char": ("<b", 1), "byte": ("<B", 1), "bool": ("<?", 1), "short": ("<h", 2), "word": ("<H", 2),
        "int": ("<i", 4), "dword": ("<I", 4), "float": ("<f", 4), "int64": ("<q", 8), "double": ("<d", 8)}


class Field:
    def __init__(self, kind, type_, name, union=False):
        self.kind, self.type, self.name, self.union = kind, type_, name, union   # kind: prim | struct | array


class Type:
    def __init__(self, name, guid):
        self.name, self.guid, self.items = name, guid, []      # items: Field or ("include", name) or ("extend", guid)
        self.fields = None


def parse_schema(text):
    types, by_guid, order = {}, {}, []
    cur = None
    for raw in text.splitlines():
        line = raw.split("//")[0].strip()
        if not line or line.startswith(("^hint", "^pass", "^replace", "^declare")) or line in ("{", "};"):
            continue
        m = re.match(r"^(\w+)\s*\{([0-9A-Fa-f-]+)\}$", line)
        if m:
            cur = Type(m.group(1), m.group(2).upper())
            by_guid[cur.guid] = cur
            types[cur.name] = cur                  # a later definition with the same name wins (npc_info, prop_comp)
            order.append(cur)
            continue
        if line == "}":
            cur = None
            continue
        if cur is None:
            continue
        m = re.match(r"^\^include\s+(\w+);", line)
        if m:
            cur.items.append(("include", m.group(1)))
            continue
        m = re.match(r"^\^extend\s+\{([0-9A-Fa-f-]+)\};", line)
        if m:
            cur.items.append(("extend", m.group(1).upper()))
            continue
        m = re.match(r"^(\^union\s+)?(\w+)(\[\])?\s+(\w+);", line)
        if m:
            union, tname, arr, fname = bool(m.group(1)), m.group(2), bool(m.group(3)), m.group(4)
            if tname == "string":
                base = Field("string", "string", fname)
            elif tname in PRIM:
                base = Field("prim", tname, fname)
            else:
                base = Field("struct", tname, fname, union)
            if arr:
                cur.items.append(Field("array", base, fname, union))
            else:
                cur.items.append(base)
    return types, by_guid


def flatten(t, types, by_guid, seen=()):
    """The type's fields with ^include / ^extend expanded in place."""
    if t.fields is not None:
        return t.fields
    out = []
    for it in t.items:
        if isinstance(it, tuple):
            ref = types.get(it[1]) if it[0] == "include" else by_guid.get(it[1])
            if ref is not None and ref.name not in seen:
                out.extend(flatten(ref, types, by_guid, seen + (t.name,)))
        else:
            out.append(it)
    t.fields = out
    return out


class Decoder:
    def __init__(self, schema_text, data):
        self.types, self.by_guid = parse_schema(schema_text)
        self.d = data
        self._fixed = {}

    # ---- sizes
    def field_size(self, f):
        """Fixed byte size of a field, or None when it is variable."""
        if f.kind == "prim":
            return PRIM[f.type][1]
        if f.kind == "string":
            return 4
        if f.kind == "array":
            return None
        return self.type_size(self.types[f.type]) if not f.union else None

    def type_size(self, t):
        if t.name in self._fixed:
            return self._fixed[t.name]
        self._fixed[t.name] = None                 # recursion guard
        total = 0
        for f in flatten(t, self.types, self.by_guid):
            s = self.field_size(f)
            if s is None:
                total = None
                break
            total += s
        self._fixed[t.name] = total
        return total

    # ---- decoding
    def u16(self, o):
        return struct.unpack_from("<H", self.d, o)[0]

    def u32(self, o):
        return struct.unpack_from("<I", self.d, o)[0]

    def string(self, idx):
        return self.pool[idx - 1] if 0 < idx <= len(self.pool) else ("" if idx == 0 else f"#{idx}")

    def obj(self, t, start, end):
        fields = flatten(t, self.types, self.by_guid)
        var = [i for i, f in enumerate(fields) if self.field_size(f) is None]
        n = len(var) - (1 if var and var[-1] == len(fields) - 1 else 0)
        wide = (end - start) >= 0x10000
        offs = [self.u32(start + 4 * i) if wide else self.u16(start + 2 * i) for i in range(n)]
        base = start + (4 * n if wide else 2 * n)
        base += (-(base - start)) % 4
        out, cur, vi = {}, base, 0
        for i, f in enumerate(fields):
            size = self.field_size(f)
            if size is not None:
                out[f.name] = self.fixed(f, cur)
                cur += size
                continue
            fend = base + offs[vi] if vi < len(offs) else end
            vi += 1
            try:
                out[f.name] = self.var(f, cur, fend)
            except (struct.error, IndexError, KeyError, ZeroDivisionError) as e:
                out[f.name] = {"?error": repr(e)[:120], "bytes": fend - cur}
            cur = fend + (-(fend - base)) % 4 if i != len(fields) - 1 else fend
        return out

    def fixed(self, f, o):
        if f.kind == "prim":
            v = struct.unpack_from(PRIM[f.type][0], self.d, o)[0]
            return round(v, 3) if isinstance(v, float) else v
        if f.kind == "string":
            return self.string(self.u32(o))
        t = self.types[f.type]
        return self.obj(t, o, o + self.type_size(t))

    def var(self, f, start, end):
        if f.kind == "array":
            return self.array(f, start, end)
        if f.kind == "struct":
            if f.union:
                return {"?union": f.type}
            return self.obj(self.types[f.type], start, end)
        return {"?": f.kind}

    def array(self, f, start, end):
        el = f.type
        if end <= start:
            return []
        if el.kind == "prim":
            size = PRIM[el.type][1]
            fmt = PRIM[el.type][0]
            return [self.fixed(el, o) for o in range(start, start + ((end - start) // size) * size, size)]
        if el.kind == "string":
            return [self.string(self.u32(o)) for o in range(start, end - 3, 4)]
        t = self.types[el.type]
        fsz = None if f.union else self.type_size(t)
        if fsz is not None:
            return [self.obj(t, o, o + fsz) for o in range(start, start + ((end - start) // fsz) * fsz, fsz)] \
                if fsz else []
        count = self.u32(start)
        if count > (end - start) // 2:
            raise IndexError(f"count {count} does not fit in {end - start} bytes")
        o = start + 4
        variants = None
        if f.union:
            variants = flatten(t, self.types, self.by_guid)
            bits = max(1, math.ceil(math.log2(len(variants) + 1)))
            per = 32 // bits
            idx = []
            for w in range(math.ceil(count / per)):
                word = self.u32(o)
                o += 4
                for k in range(per):
                    idx.append((word >> (k * bits)) & ((1 << bits) - 1))
            idx = idx[:count]
        if count == 0:
            return []
        wide = (end - start) >= 0x10000
        ends = [self.u32(o + 4 * i) if wide else self.u16(o + 2 * i) for i in range(count - 1)]
        o += (4 if wide else 2) * (count - 1)
        o += (-(o - start)) % 4
        items, prev = [], 0
        for i in range(count):
            e = ends[i] if i < count - 1 else end - o
            s0 = o + prev
            if variants is not None:
                vf = variants[idx[i] - 1] if 0 < idx[i] <= len(variants) else None
                vt = self.types.get(vf.type) if vf is not None else None
                items.append({"?variant": vf.name if vf else idx[i], **(self.obj(vt, s0, o + e) if vt else {})})
            else:
                items.append(self.obj(t, s0, o + e))
            prev = e + (-e) % 4
        return items

    def decode(self, root_name="clt_file_root"):
        d = self.d
        assert d[:4] == b"BMIF", d[:4]
        n = self.u32(12)
        guids = []
        for i in range(n):
            a, b, c, e = struct.unpack_from("<IHHH", d, 16 + 16 * i)
            guids.append(f"{a:08X}-{b:04X}-{c:04X}-{e:04X}-{d[16 + 16 * i + 10:16 + 16 * i + 16].hex().upper()}")
        o = 16 + 16 * n
        size, count = self.u32(o), self.u32(o + 4)
        self.pool = [s.decode("cp949", "replace") for s in d[o + 8:o + 8 + size].split(b"\0")][:count]
        start = o + 8 + size
        root = self.types[root_name]
        return {"guids": guids, "pool": len(self.pool), "root": self.obj(root, start, len(d))}


def main():
    schema, path = sys.argv[1], sys.argv[2]
    dec = Decoder(open(schema, "rb").read().decode("latin-1"), open(path, "rb").read())
    root = sys.argv[4] if len(sys.argv) > 4 else "clt_file_root"
    out = dec.decode(root)
    text = json.dumps(out, indent=1, ensure_ascii=False, default=str)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w", encoding="utf-8").write(text)
    r = out["root"]
    print({k: (len(v) if isinstance(v, list) else v) for k, v in r.items() if not isinstance(v, dict)})


if __name__ == "__main__":
    main()

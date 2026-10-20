import json
import struct
import sys


class Reader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def take(self, n):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def f32(self):
        return struct.unpack("<f", self.take(4))[0]

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            return self.take(n)[:-1].decode("latin-1")
        return self.take(-n * 2)[:-2].decode("utf-16-le")


def name_map(uasset):
    r = Reader(uasset)
    r.u32()
    legacy = r.i32()
    if legacy != -4:
        r.i32()
    r.i32()
    r.i32()
    for _ in range(r.i32()):
        r.take(20)
    r.i32()
    r.fstring()
    r.u32()
    count = r.i32()
    offset = r.i32()
    names = []
    nr = Reader(uasset, offset)
    for _ in range(count):
        names.append(nr.fstring())
        nr.take(4)
    return names


def fname(r, names):
    index = r.i32()
    number = r.i32()
    base = names[index] if 0 <= index < len(names) else f"<{index}>"
    return base if number == 0 else f"{base}_{number - 1}"


def read_properties(r, names, depth=0):
    props = {}
    while r.pos < len(r.data):
        name = fname(r, names)
        if name == "None":
            break
        kind = fname(r, names)
        size = r.i32()
        array_index = r.i32()
        extra = None
        if kind == "StructProperty":
            extra = fname(r, names)
            r.take(16)
        elif kind == "BoolProperty":
            extra = r.take(1)[0]
        elif kind in ("ByteProperty", "EnumProperty"):
            extra = fname(r, names)
        elif kind in ("ArrayProperty", "SetProperty"):
            extra = fname(r, names)
        elif kind == "MapProperty":
            extra = (fname(r, names), fname(r, names))
        if r.take(1)[0]:
            r.take(16)
        start = r.pos
        value = None
        if kind == "BoolProperty":
            value = bool(extra)
        elif kind == "FloatProperty":
            value = r.f32()
        elif kind == "IntProperty":
            value = r.i32()
        elif kind in ("EnumProperty", "NameProperty") or (kind == "ByteProperty" and extra != "None"):
            value = fname(r, names)
        elif kind == "ObjectProperty":
            value = r.i32()
        elif kind == "StructProperty" and extra not in ("Vector", "Rotator", "Guid", "Color", "LinearColor", "Vector2D"):
            value = read_properties(Reader(r.data[start:start + size]), names, depth + 1)
        elif kind == "ArrayProperty" and extra == "StructProperty":
            sub = Reader(r.data[start:start + size])
            count = sub.i32()
            fname(sub, names)
            fname(sub, names)
            sub.i32()
            sub.i32()
            inner_struct = fname(sub, names)
            sub.take(16)
            sub.take(1)
            value = [read_properties(sub, names, depth + 1) for _ in range(count)] if inner_struct not in ("Vector",) else None
            value = {"struct": inner_struct, "items": value}
        else:
            value = r.data[start:start + size].hex()
        r.pos = start + size
        key = name if array_index == 0 else f"{name}[{array_index}]"
        props[key] = {"type": kind, "value": value}
    return props


if __name__ == "__main__":
    base = sys.argv[1]
    uasset = open(base + ".uasset", "rb").read()
    uexp = open(base + ".uexp", "rb").read()
    names = name_map(uasset)
    print(json.dumps(read_properties(Reader(uexp), names), indent=1))

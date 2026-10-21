import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_assets import PAK
from pakextract import read_entry
from paklist import list_pak
from uprops import Reader, fname, read_properties

EXPORT_ENTRY_SIZE = 104
EXPORT_ENTRY_READ = 44
FILTER_EDITOR_ONLY = 0x80000000
LISTED_CLASSES = ("SoundCue", "SoundNodeRandom")


def read_names(uasset, offset, count):
    r = Reader(uasset, offset)
    names = []
    for _ in range(count):
        names.append(r.fstring())
        r.take(4)
    return names


def read_summary(uasset):
    r = Reader(uasset)
    r.u32()
    if r.i32() != -4:
        r.i32()
    r.i32()
    r.i32()
    for _ in range(r.i32()):
        r.take(20)
    header_size = r.i32()
    r.fstring()
    flags = r.u32()
    name_count, name_offset = r.i32(), r.i32()
    if not flags & FILTER_EDITOR_ONLY:
        r.fstring()
    r.i32()
    r.i32()
    export_count, export_offset = r.i32(), r.i32()
    import_count, import_offset = r.i32(), r.i32()
    names = read_names(uasset, name_offset, name_count)

    ir = Reader(uasset, import_offset)
    imports = []
    for _ in range(import_count):
        fname(ir, names)
        fname(ir, names)
        ir.i32()
        imports.append(fname(ir, names))

    er = Reader(uasset, export_offset)
    exports = []
    for _ in range(export_count):
        class_index = er.i32()
        er.take(12)
        name = fname(er, names)
        er.u32()
        size, offset = struct.unpack("<qq", er.take(16))
        er.take(EXPORT_ENTRY_SIZE - EXPORT_ENTRY_READ)
        class_name = imports[-class_index - 1] if class_index < 0 else f"export {class_index}"
        exports.append({"class": class_name, "name": name, "size": size, "offset": offset - header_size})
    return names, exports


def object_refs(hex_value):
    raw = bytes.fromhex(hex_value)
    count = struct.unpack_from("<i", raw)[0]
    return list(struct.unpack_from(f"<{count}i", raw, 4))


def soft_asset(hex_value, names):
    return fname(Reader(bytes.fromhex(hex_value)), names).split(".")[-1]


def describe(ref, exports, props, names):
    if ref == 0:
        return "empty"
    if ref < 0:
        return f"import {-ref}"
    export, values = exports[ref - 1], props[ref - 1]
    wave = values.get("SoundWaveAssetPtr", {}).get("value")
    suffix = f" -> {soft_asset(wave, names)}" if isinstance(wave, str) else ""
    return f"{export['class']} {export['name']}{suffix}"


def main():
    game_dir, cue = sys.argv[1:3]
    pak_path = os.path.join(game_dir, PAK)
    index = list_pak(pak_path)
    files = {name.replace("../../../", ""): entry for name, entry in index["files"].items()}
    base = next((name[:-len(".uasset")] for name in files if name.endswith("/" + cue + ".uasset")), None)
    if base is None:
        sys.exit(f"{cue} not in the pak")
    with open(pak_path, "rb") as pak:
        uasset = read_entry(pak, files[base + ".uasset"], index["methods"])
        uexp = read_entry(pak, files[base + ".uexp"], index["methods"])
    names, exports = read_summary(uasset)
    props = [read_properties(Reader(uexp[e["offset"]:e["offset"] + e["size"]]), names) for e in exports]

    print(base)
    for number, (export, values) in enumerate(zip(exports, props), 1):
        if export["class"] not in LISTED_CLASSES:
            continue
        print(f"#{number} {export['class']} {export['name']}")
        first = values.get("FirstNode", {}).get("value")
        if first is not None:
            print(f"   first node: {describe(first, exports, props, names)}")
        children = values.get("ChildNodes", {}).get("value")
        if isinstance(children, str):
            for position, ref in enumerate(object_refs(children), 1):
                print(f"   {position:2d}: {describe(ref, exports, props, names)}")


if __name__ == "__main__":
    main()

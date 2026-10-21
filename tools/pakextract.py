import json
import os
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
UNOODLE = os.path.join(HERE, "unoodle", "target", "release", "unoodle-block" + (".exe" if sys.platform == "win32" else ""))
UNCOMPRESSED_HEADER = 53


def compressed_header_size(block_count):
    return 8 + 8 + 8 + 4 + 20 + 4 + 16 * block_count + 1 + 4


def decompress_block(method_name, block, size):
    if method_name == "Zlib":
        return zlib.decompress(block)
    if method_name == "Oodle":
        result = subprocess.run([UNOODLE, str(size)], input=block, capture_output=True, check=True)
        return result.stdout
    raise ValueError(f"unsupported compression {method_name}")


def read_entry(pak, entry, methods):
    if entry["encrypted"]:
        raise ValueError("encrypted entry")
    if entry["method"] == 0:
        pak.seek(entry["offset"] + UNCOMPRESSED_HEADER)
        return pak.read(entry["size"])
    method_name = methods[entry["method"] - 1]
    blocks = entry["block_sizes"]
    pak.seek(entry["offset"] + compressed_header_size(len(blocks)))
    remaining = entry["usize"]
    unpacked_block_size = entry["block_size"] if len(blocks) > 1 else remaining
    output = bytearray()
    for block_size in blocks:
        chunk = pak.read(block_size)
        expected = min(unpacked_block_size, remaining)
        data = decompress_block(method_name, chunk, expected)
        if len(data) != expected:
            raise ValueError(f"block decompressed to {len(data)} bytes, expected {expected}")
        output += data
        remaining -= expected
    return bytes(output)


def main():
    pak_path, index_path, out_dir = sys.argv[1:4]
    filters = sys.argv[4:]
    index = json.load(open(index_path))
    methods = index["methods"]
    selected = [name for name in index["files"] if any(f in name for f in filters)]
    with open(pak_path, "rb") as pak:
        for name in sorted(selected):
            data = read_entry(pak, index["files"][name], methods)
            relative = name.replace("../../../", "")
            target = os.path.join(out_dir, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                out.write(data)
    print(f"extracted {len(selected)} files into {out_dir}")


if __name__ == "__main__":
    main()

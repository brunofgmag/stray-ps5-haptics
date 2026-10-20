import json
import os
import struct
import sys


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, n):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.take(8))[0]

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            return self.take(n)[:-1].decode("latin-1")
        return self.take(-n * 2)[:-2].decode("utf-16-le")


def read_footer(f, size):
    f.seek(size - 512)
    tail = f.read(512)
    at = tail.rfind(struct.pack("<I", 0x5A6F12E1))
    _, version, index_offset, index_size = struct.unpack("<IIqq", tail[at:at + 24])
    methods_raw = tail[at + 24 + 20:]
    methods = [methods_raw[i:i + 32].rstrip(b"\0").decode() for i in range(0, len(methods_raw) - 31, 32)]
    return version, index_offset, index_size, [m for m in methods if m]


def decode_entry(buf, pos):
    r = Reader(buf)
    r.pos = pos
    value = r.u32()
    block_size = r.u32() if (value & 0x3F) == 0x3F else (value & 0x3F) << 11
    method = (value >> 23) & 0x3F
    offset = r.u32() if value & (1 << 31) else r.u64()
    usize = r.u32() if value & (1 << 30) else r.u64()
    size = (r.u32() if value & (1 << 29) else r.u64()) if method else usize
    encrypted = bool(value & (1 << 22))
    blocks = (value >> 6) & 0xFFFF
    block_sizes = []
    if blocks > 0 and (encrypted or blocks != 1):
        block_sizes = [r.u32() for _ in range(blocks)]
    elif blocks == 1:
        block_sizes = [size]
    return {"offset": offset, "usize": usize, "size": size, "method": method, "encrypted": encrypted,
            "block_size": block_size, "block_sizes": block_sizes}


def list_pak(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        version, index_offset, index_size, methods = read_footer(f, size)
        f.seek(index_offset)
        index = Reader(f.read(index_size))
        mount = index.fstring()
        index.i32()
        index.u64()
        has_path_hash = index.i32()
        if has_path_hash:
            index.take(8 + 8 + 20)
        has_full_dir = index.i32()
        full_dir_offset, full_dir_size = index.u64(), index.u64()
        index.take(20)
        encoded_size = index.i32()
        encoded = index.take(encoded_size)
        f.seek(full_dir_offset)
        dirs = Reader(f.read(full_dir_size))
    files = {}
    for _ in range(dirs.i32()):
        directory = dirs.fstring()
        for _ in range(dirs.i32()):
            name = dirs.fstring()
            entry_pos = dirs.i32()
            files[mount + directory + name] = decode_entry(encoded, entry_pos)
    return {"version": version, "methods": methods, "mount": mount, "files": files}


if __name__ == "__main__":
    result = list_pak(sys.argv[1])
    json.dump(result, open(sys.argv[2], "w"))
    print(result["version"], result["methods"], result["mount"], len(result["files"]))

"""Read only committed private MM2 memory; never suspend/write the target.

Output only CSV-result IDs and exact matches to the first 128 public released
input coordinate pairs. No raw memory dump, private reference access or restart.
These are diagnostic observations, not a final route or proof of completion.
"""
import argparse
import csv
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import re
import struct
import time


class MBI(C.Structure):
    _fields_ = [('BaseAddress', C.c_void_p), ('AllocationBase', C.c_void_p),
                ('AllocationProtect', W.DWORD), ('PartitionId', W.WORD),
                ('RegionSize', C.c_size_t), ('State', W.DWORD),
                ('Protect', W.DWORD), ('Type', W.DWORD)]


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--pid', type=int, required=True)
    a.add_argument('--tracks', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    args = a.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    targets = []
    with args.tracks.open(encoding='utf-8', newline='') as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= 128:
                break
            pair = row['geometry'].split('(', 1)[1].split(',', 1)[0]
            x, y = map(float, pair.rstrip(')').split())
            targets.append((int(row['id']), struct.pack('<dd', x, y)))
    k = C.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k.OpenProcess.restype = W.HANDLE
    k.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t]
    k.VirtualQueryEx.restype = C.c_size_t
    k.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    k.ReadProcessMemory.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    handle = k.OpenProcess(0x0400 | 0x0010, False, args.pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    started = time.monotonic()
    hits = {}
    result_rows = []
    headers = []
    scanned = 0
    address = 0
    try:
        while address < 0x7fffffffffff:
            m = MBI()
            if not k.VirtualQueryEx(handle, address, C.byref(m), C.sizeof(m)):
                break
            base = int(m.BaseAddress or 0)
            size = int(m.RegionSize)
            if not size:
                break
            # Exclude all mapped files, images, guard/noaccess and uncommitted pages.
            if m.State == 0x1000 and m.Type == 0x20000 and not m.Protect & 0x101 and m.Protect & 0xee:
                for offset in range(0, size, 1024 * 1024):
                    n = min(1024 * 1024 + 256, size - offset)
                    buffer = C.create_string_buffer(n)
                    read = C.c_size_t()
                    k.ReadProcessMemory(handle, base + offset, buffer, n, C.byref(read))
                    data = buffer.raw[:read.value]
                    scanned += len(data)
                    for slot, needle in targets:
                        pos = data.find(needle)
                        if pos >= 0:
                            hits.setdefault(str(slot), []).append(hex(base + offset + pos))
                    needle = b'id,aborted,duration,match,edge_ids'
                    pos = data.find(needle)
                    if pos >= 0:
                        headers.append(hex(base + offset + pos))
                    for match in re.finditer(rb'(?:^|[\r\n\x00])(\d{1,6}),(yes|no),(\d+(?:\.\d+)?),(?:"?(?:MULTI)?LINESTRING|"?GEOMETRYCOLLECTION)', data):
                        result_rows.append({'slot': int(match[1]), 'aborted': match[2].decode(),
                                            'duration': float(match[3]), 'address': hex(base + offset + match.start())})
            address = base + size
    finally:
        k.CloseHandle(handle)
    report = dict(pid=args.pid, read_only=True, suspended=False, target_written=False,
                  private_bytes_scanned=scanned, seconds=time.monotonic()-started,
                  input_tracks=str(args.tracks), tracks_sha256=hashlib.sha256(args.tracks.read_bytes()).hexdigest(),
                  first128_pair_hits=hits, result_header_addresses=headers, pending_csv_rows=result_rows,
                  limitations=['Not all active geometry layouts contain contiguous x/y doubles',
                               'A coordinate hit does not by itself identify the active worker or prove progress',
                               'Absent rows are not proof of zero completed records'])
    args.out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

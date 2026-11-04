"""Copy every NsData file that appears in Azahar's BOSS extdata for DQMJ3P, before the game deletes it.

The LLE boss module stores the decrypted payload of each download there (0x34-byte header + payload),
and the game removes the gift disc file (FGONLYT/BossPresentDisc.bin) right after reading it.
Start this, then pick up the day's disc in the Wi-Fi plaza (Wi-Fi PRESENT).

usage (python -I): capture_boss_nsdata.py BOSS_DIR OUT_DIR [SECONDS]
  BOSS_DIR e.g. %APPDATA%/Azahar/sdmc/Nintendo 3DS/<id0>/<id1>/extdata/00000000/00001ACB/boss
"""
import os
import sys
import time

src, dst = sys.argv[1], sys.argv[2]
end = time.time() + float(sys.argv[3] if len(sys.argv) > 3 else 3600)
seen = {}
for n in os.listdir(src):
    st = os.stat(os.path.join(src, n))
    seen[n] = (st.st_size, st.st_mtime_ns)
print("watching", len(seen), "existing files", flush=True)
while time.time() < end:
    try:
        for n in os.listdir(src):
            p = os.path.join(src, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            key = (st.st_size, st.st_mtime_ns)
            if seen.get(n) != key and st.st_size > 0:
                try:
                    data = open(p, "rb").read()
                except OSError:
                    continue
                if len(data) != st.st_size:
                    continue
                seen[n] = key
                out = os.path.join(dst, f"{int(time.time()*1000)}_{len(data)}.bin")
                open(out, "wb").write(data)
                print("captured", len(data), "bytes", flush=True)
    except OSError:
        pass
    time.sleep(0.002)
print("done", flush=True)

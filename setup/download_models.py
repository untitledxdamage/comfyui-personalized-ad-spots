#!/usr/bin/env python3
"""Download every model in setup/models.json into ComfyUI/models/ and verify its SHA256.

    python setup/download_models.py /path/to/ComfyUI        # HF_TOKEN env var is sent if set
    python setup/download_models.py /path/to/ComfyUI --check   # only verify what is already there

Files already present with the right size are not downloaded again.
"""
import hashlib, json, os, sys, urllib.request


def sha256(path, chunk=16 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    check_only = "--check" in sys.argv
    comfy = args[0] if args else "."
    manifest = json.load(open(os.path.join(os.path.dirname(__file__), "models.json"), encoding="utf-8"))
    token = os.environ.get("HF_TOKEN")
    bad = 0
    for m in manifest["models"]:
        dst = os.path.join(comfy, "models", m["dir"], m["file"])
        present = os.path.exists(dst) and os.path.getsize(dst) == m["bytes"]
        if not present and check_only:
            state = "different size" if os.path.exists(dst) else "missing"
            print(f"[{state}] {m['dir']}/{m['file']}")
            bad += 1
            continue
        if not present:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            print(f"downloading {m['file']} ({m['bytes'] / 1e9:.1f} GB)")
            req = urllib.request.Request(m["url"], headers={"Authorization": f"Bearer {token}"} if token else {})
            with urllib.request.urlopen(req) as r, open(dst + ".part", "wb") as f:
                while b := r.read(16 << 20):
                    f.write(b)
            os.replace(dst + ".part", dst)
        ok = sha256(dst) == m["sha256"]
        bad += not ok
        print(f"[{'ok' if ok else 'HASH MISMATCH'}] {m['dir']}/{m['file']}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

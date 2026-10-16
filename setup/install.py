#!/usr/bin/env python3
"""Copy the node pack and the demo assets into a ComfyUI install. Works on Windows, Linux and macOS.

    python setup/install.py /path/to/ComfyUI
    python setup/install.py /path/to/ComfyUI --input-dir /other/input      # if your input folder lives elsewhere

Then restart ComfyUI. The workflow needs no other custom nodes.
"""
import argparse, os, shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = "comfyui-spot-sequencer"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("comfyui", help="ComfyUI folder (the one that contains custom_nodes/)")
    ap.add_argument("--input-dir", help="ComfyUI input folder (default: <comfyui>/input)")
    a = ap.parse_args()

    nodes = os.path.join(a.comfyui, "custom_nodes")
    if not os.path.isdir(nodes):
        raise SystemExit(f"{nodes} not found: point the first argument at your ComfyUI folder")
    dst = os.path.join(nodes, PACK)
    shutil.copytree(os.path.join(REPO, "custom_nodes", PACK), dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    print(f"node pack -> {dst}")

    input_dir = a.input_dir or os.path.join(a.comfyui, "input")
    os.makedirs(input_dir, exist_ok=True)
    for name in sorted(os.listdir(os.path.join(REPO, "assets"))):
        if name.lower().endswith((".png", ".jpg", ".mp4")):
            shutil.copy2(os.path.join(REPO, "assets", name), os.path.join(input_dir, name))
            print(f"asset     -> {os.path.join(input_dir, name)}")
    print("Done. Restart ComfyUI, then download the models: python setup/download_models.py", a.comfyui)


if __name__ == "__main__":
    main()

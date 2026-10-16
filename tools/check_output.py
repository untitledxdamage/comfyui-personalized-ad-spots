#!/usr/bin/env python3
"""Check finished videos: picture length, size, audio length, loudness, peaks and (optionally) the spoken name.

    pip install av numpy scipy                  # faster-whisper too, only for --transcribe
    python tools/check_output.py downloads/Loyalty_Offer            # every .mp4 in a folder and its sub-folders
    python tools/check_output.py video.mp4 --frames 484 --transcribe --name Emma
    python tools/check_output.py downloads/Loyalty_Offer --frames 484 --transcribe --manifest campaigns/loyalty/manifest.csv

With the manifest.csv that jobs/campaign.py writes, --transcribe looks up each person's name there
and flags the videos where the name was not heard in the first seconds. Speech recognition gets
unusual names wrong, so a flag means "listen to this one", not "it failed". The ids to listen to
are printed at the end, ready for `campaign.py retry --ids`.
"""
import argparse, csv, glob, math, os, sys, unicodedata

import av
import numpy as np
from scipy.signal import lfilter, resample_poly


def k_weight(x, sr):
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / sr)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
    a1 = [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / sr)
    a2 = [1, 2 * (K * K - 1) / (1 + K / Q + K * K), (1 - K / Q + K * K) / (1 + K / Q + K * K)]
    return lfilter([1, -2, 1], a2, lfilter(b1, a1, x, axis=1), axis=1)


def integrated_lufs(x, sr):
    """Integrated loudness, ITU-R BS.1770 with gating."""
    y = k_weight(x.astype(np.float64), sr)
    block, hop = int(0.4 * sr), int(0.1 * sr)
    if y.shape[1] < block:
        return -70.0
    z = np.array([np.mean(y[:, i:i + block] ** 2, axis=1).sum() for i in range(0, y.shape[1] - block + 1, hop)])
    z = z[(-0.691 + 10 * np.log10(z + 1e-12)) > -70]
    if len(z) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z = z[(-0.691 + 10 * np.log10(z + 1e-12)) > rel]
    return float(-0.691 + 10 * np.log10(z.mean())) if len(z) else -70.0


def true_peak_db(x):
    return float(20 * np.log10(np.abs(resample_poly(x, 4, 1, axis=1)).max() + 1e-12))


def read(path):
    with av.open(path) as c:
        v = c.streams.video[0]
        info = {"width": v.width, "height": v.height, "fps": float(v.average_rate), "frames": sum(1 for _ in c.decode(video=0))}
    with av.open(path) as c:
        if not c.streams.audio:
            return info, np.zeros((2, 0), np.float32), 48000
        sr = c.streams.audio[0].rate
        res = av.AudioResampler(format="fltp", layout="stereo", rate=sr)
        chunks = [r.to_ndarray() for f in c.decode(audio=0) for r in res.resample(f)]
    return info, np.concatenate(chunks, axis=1), sr


def plain(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if ch.isalnum())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", help="an .mp4 or a folder of them")
    ap.add_argument("--frames", type=int, help="expected number of video frames")
    ap.add_argument("--greeting-seconds", type=float, default=5.0, help="length of the opening generated clip")
    ap.add_argument("--transcribe", action="store_true", help="transcribe the opening clip with faster-whisper")
    ap.add_argument("--name", help="name expected in the greeting (single file)")
    ap.add_argument("--manifest", help="manifest.csv from jobs/campaign.py, to know which name each video should say")
    ap.add_argument("--sample", type=int, default=0, help="check only this many videos, picked evenly across the folder")
    ap.add_argument("--whisper-model", default="small")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.target, "**", "*.mp4"), recursive=True)) if os.path.isdir(a.target) else [a.target]
    if a.sample and len(files) > a.sample:
        files = [files[round(i * (len(files) - 1) / (a.sample - 1))] for i in range(a.sample)] if a.sample > 1 else files[:1]
    names = {}
    manifest = a.manifest or (os.path.join(a.target, "manifest.csv") if os.path.isdir(a.target) else None)
    if manifest and os.path.exists(manifest):
        names = {r["customer_id"]: r["name"] for r in csv.DictReader(open(manifest, encoding="utf-8"))}
    model = None
    if a.transcribe:
        from faster_whisper import WhisperModel
        model = WhisperModel(a.whisper_model, device="cpu", compute_type="int8")

    problems, review = 0, []
    for f in files:
        info, x, sr = read(f)
        n = int(a.greeting_seconds * sr)
        notes = []
        row = (f"{os.path.basename(f)}: {info['frames']} frames {info['width']}x{info['height']} @ {info['fps']:g} fps "
               f"({info['frames'] / info['fps']:.2f} s), audio {x.shape[1] / sr:.2f} s, "
               f"{integrated_lufs(x, sr):.1f} LUFS (opening {integrated_lufs(x[:, :n], sr):.1f}, rest {integrated_lufs(x[:, n:], sr):.1f}), "
               f"true peak {true_peak_db(x):.1f} dBFS")
        if a.frames and info["frames"] != a.frames:
            notes.append(f"expected {a.frames} frames")
        if abs(x.shape[1] / sr - info["frames"] / info["fps"]) > 0.1:
            notes.append("audio and picture lengths differ")
        if true_peak_db(x) > -0.5:
            notes.append("true peak above -0.5 dBFS")
        if model is not None:
            mono = resample_poly(x[:, :n].mean(axis=0), 16000, sr).astype(np.float32)
            segs, _ = model.transcribe(mono, beam_size=5)
            text = " ".join(s.text.strip() for s in segs)
            row += f'\n    heard: "{text}"'
            name = a.name or names.get(os.path.splitext(os.path.basename(f))[0])
            if name and plain(name) not in plain(text):
                notes.append(f'name "{name}" not recognised: listen to it')
        print(row + ("".join(f"\n    !! {m}" for m in notes)))
        problems += bool(notes)
        if notes:
            review.append(os.path.splitext(os.path.basename(f))[0])
    print(f"{len(files)} file(s), {problems} to review" + (": " + " ".join(review) if review else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Spot Sequencer — build one MP4 out of generated clips and pre-made clips, inside ComfyUI.

A sequence is a chain of "Add clip" nodes ending in "Save sequence":

    Add generated clip -> Add pre-made clip -> Add pre-made clip -> ... -> Save sequence (MP4)

- Add generated clip: frames + audio coming from the graph (e.g. an LTX-2.5 greeting).
- Add pre-made clip:  a finished video file (core "Load Video"). It is never decoded as a whole:
                      it is streamed frame by frame into the output when the sequence is saved.
- Save sequence:      writes every clip, in chain order, into a single H.264/AAC MP4.

Clips can be chained in any order and any number, so adding one more pre-made (or generated)
clip to a spot is a matter of duplicating one group of nodes and plugging it into the chain.
"""
import math
import os
from fractions import Fraction

import numpy as np
import torch
import torchaudio
from scipy.signal import lfilter

SEQUENCE = "SPOT_SEQUENCE"
CATEGORY = "video/spot sequencer"
SAMPLE_RATE = 48000  # every clip's audio is resampled to this, stereo


# ---------- audio helpers ----------
def _stereo(x):
    if x.shape[0] == 2:
        return x
    if x.shape[0] == 1:
        return np.repeat(x, 2, axis=0)
    return x.mean(axis=0, keepdims=True).repeat(2, axis=0)


def _resample(x, sr, target):
    if sr == target or x.shape[1] == 0:
        return x
    return torchaudio.functional.resample(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)), sr, target).numpy()


def _fit(x, n):
    """Pad with silence or trim so the clip lasts exactly n samples."""
    if x.shape[1] >= n:
        return x[:, :n]
    return np.pad(x, ((0, 0), (0, n - x.shape[1])))


def _k_weight(x, sr):
    # ITU-R BS.1770 pre-filter (high shelf) + RLB high-pass, coefficients derived for any sample rate.
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
    b2 = [1, -2, 1]
    return lfilter(b2, a2, lfilter(b1, a1, x, axis=1), axis=1)


def integrated_lufs(x, sr):
    """Integrated loudness (ITU-R BS.1770, gated) of a [channels, samples] array."""
    y = _k_weight(x.astype(np.float64), sr)
    block, hop = int(0.4 * sr), int(0.1 * sr)
    if y.shape[1] < block:
        return -70.0
    z = np.array([np.mean(y[:, i:i + block] ** 2, axis=1).sum() for i in range(0, y.shape[1] - block + 1, hop)])
    l = -0.691 + 10 * np.log10(z + 1e-12)
    z = z[l > -70]
    if len(z) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z = z[(-0.691 + 10 * np.log10(z + 1e-12)) > rel]
    if len(z) == 0:
        return -70.0
    return float(-0.691 + 10 * np.log10(z.mean()))


def limit_peaks(x, sr, ceiling_db, lookahead_ms=3.0, release_ms=80.0):
    """Look-ahead peak limiter. Peaks are measured on a 4x oversampled copy (inter-sample peaks)."""
    if x.shape[1] == 0:
        return x
    ceiling = 10 ** (ceiling_db / 20)
    up = torchaudio.functional.resample(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)), sr, sr * 4).numpy()
    peak = np.abs(up).max(axis=0)
    peak = peak[: x.shape[1] * 4].reshape(-1, 4).max(axis=1) if peak.size >= x.shape[1] * 4 else np.abs(x).max(axis=0)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    la = max(1, int(lookahead_ms * sr / 1000))
    # look-ahead: gain must already be down when the peak arrives
    padded = np.concatenate([need, np.ones(la)])
    win = np.lib.stride_tricks.sliding_window_view(padded, la)[: len(need)].min(axis=1)
    # attack = linear ramp over the look-ahead window (smooth), release = exponential
    att = np.convolve(np.concatenate([np.ones(la - 1), win]), np.ones(la) / la, mode="valid")
    att = np.minimum(att, win)
    rel = math.exp(-1.0 / (release_ms * sr / 1000))
    g = np.empty_like(att)
    cur = 1.0
    for i, v in enumerate(att):
        cur = v if v < cur else v + (cur - v) * rel
        g[i] = cur
    y = x * g
    np.clip(y, -ceiling, ceiling, out=y)  # safety for residual sample peaks
    return y


def _edge_fades(x, sr, ms=5.0):
    """Tiny fade in/out so a hard cut between two clips never clicks."""
    n = min(int(ms * sr / 1000), x.shape[1] // 2)
    if n > 0:
        ramp = np.linspace(0.0, 1.0, n, dtype=x.dtype)
        x[:, :n] *= ramp
        x[:, -n:] *= ramp[::-1]
    return x


# ---------- sequence items ----------
def _append(sequence, clip):
    return (list(sequence or []) + [clip],)  # never mutate the upstream list: ComfyUI caches node outputs


def _open_source(src):
    import av
    if hasattr(src, "seek"):
        src.seek(0)
    return av.open(src)


class AddGeneratedClip:
    """Adds a clip made in the graph (frames + audio in memory) to the sequence."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "normalize_loudness": ("BOOLEAN", {"default": True, "tooltip": "Generated voices come out at a different volume every time; this levels them."}),
                "target_lufs": ("FLOAT", {"default": -14.0, "min": -40.0, "max": -5.0, "step": 0.1,
                                          "tooltip": "Integrated loudness (ITU-R BS.1770). Match it to your pre-made clips."}),
            },
            "optional": {
                "audio": ("AUDIO",),
                "sequence": (SEQUENCE, {"tooltip": "Clips that play before this one. Leave empty to start a sequence."}),
            },
        }

    RETURN_TYPES = (SEQUENCE,)
    RETURN_NAMES = ("sequence",)
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, images, fps, normalize_loudness, target_lufs, audio=None, sequence=None):
        # keep the frames as 8-bit on the CPU: 4x smaller than the float batch
        frames = torch.empty(images.shape[:3] + (3,), dtype=torch.uint8)
        for i in range(0, images.shape[0], 16):
            frames[i:i + 16] = (images[i:i + 16, ..., :3].clamp(0, 1) * 255).round().to(torch.uint8).cpu()
        wave = None
        if audio is not None and audio["waveform"].shape[-1] > 0:
            wave = (audio["waveform"][0].detach().cpu().float().numpy(), int(audio["sample_rate"]))
        return _append(sequence, {"kind": "generated", "frames": frames, "fps": float(fps), "audio": wave,
                                  "lufs": float(target_lufs) if normalize_loudness else None})


class AddPremadeClip:
    """Adds a finished video file to the sequence. The file is streamed at save time, never held in memory."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {"tooltip": "A finished clip from the core Load Video node."}),
                "normalize_loudness": ("BOOLEAN", {"default": False, "tooltip": "Off = keep the clip's own mix."}),
                "target_lufs": ("FLOAT", {"default": -14.0, "min": -40.0, "max": -5.0, "step": 0.1}),
            },
            "optional": {
                "sequence": (SEQUENCE, {"tooltip": "Clips that play before this one. Leave empty to start a sequence."}),
            },
        }

    RETURN_TYPES = (SEQUENCE,)
    RETURN_NAMES = ("sequence",)
    FUNCTION = "run"
    CATEGORY = CATEGORY

    def run(self, video, normalize_loudness, target_lufs, sequence=None):
        return _append(sequence, {"kind": "premade", "source": video.get_stream_source(),
                                  "lufs": float(target_lufs) if normalize_loudness else None})


# ---------- writer ----------
def _clip_audio(clip, n_samples):
    """Audio of one clip as stereo float32 at SAMPLE_RATE, fitted to the length of its picture."""
    if clip["kind"] == "generated":
        x = np.zeros((2, 0), np.float32)
        if clip["audio"] is not None:
            wave, sr = clip["audio"]
            x = _resample(_stereo(wave), sr, SAMPLE_RATE)
    else:
        import av
        chunks = []
        with _open_source(clip["source"]) as c:
            if c.streams.audio:
                res = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
                for fr in c.decode(audio=0):
                    for r in res.resample(fr):
                        chunks.append(r.to_ndarray())
                for r in res.resample(None):
                    chunks.append(r.to_ndarray())
        x = np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 0), np.float32)
    x = _fit(x.astype(np.float32), n_samples).copy()
    if clip["lufs"] is not None:
        measured = integrated_lufs(x, SAMPLE_RATE)
        if measured > -70.0:
            x *= 10 ** ((clip["lufs"] - measured) / 20)
    return _edge_fades(x, SAMPLE_RATE)


def _probe(clip):
    """(source fps, source frame count) of a clip."""
    if clip["kind"] == "generated":
        return clip["fps"], int(clip["frames"].shape[0])
    with _open_source(clip["source"]) as c:
        vs = c.streams.video[0]
        fps = float(vs.average_rate)
        n = vs.frames
        if not n:
            dur = float(vs.duration * vs.time_base) if vs.duration else float(c.duration) / 1_000_000
            n = round(dur * fps)
    return fps, int(n)


def _source_frames(clip):
    """Yields the clip's frames, in order, as av.VideoFrame."""
    import av
    if clip["kind"] == "generated":
        for i in range(clip["frames"].shape[0]):
            yield av.VideoFrame.from_ndarray(clip["frames"][i].numpy(), format="rgb24")
    else:
        with _open_source(clip["source"]) as c:
            c.streams.video[0].thread_type = "AUTO"
            yield from c.decode(video=0)


def _conform(frame, w, h, fit):
    """Any frame -> a clean yuv420p frame of exactly w x h (crop = fill and trim, pad = letterbox)."""
    import av
    if frame.width == w and frame.height == h:
        arr = frame.reformat(format="yuv420p").to_ndarray()
    else:
        pick = max if fit == "crop" else min
        s = pick(w / frame.width, h / frame.height)
        sw, sh = max(2, round(frame.width * s)), max(2, round(frame.height * s))
        rgb = frame.reformat(width=sw, height=sh, format="rgb24", interpolation="LANCZOS").to_ndarray()
        canvas = np.zeros((h, w, 3), np.uint8)
        cw, ch = min(sw, w), min(sh, h)
        sx, sy, dx, dy = (sw - cw) // 2, (sh - ch) // 2, (w - cw) // 2, (h - ch) // 2
        canvas[dy:dy + ch, dx:dx + cw] = rgb[sy:sy + ch, sx:sx + cw]
        arr = av.VideoFrame.from_ndarray(canvas, format="rgb24").reformat(format="yuv420p").to_ndarray()
    # rebuild from the raw array: decoded frames carry the source file's time base
    return av.VideoFrame.from_ndarray(arr, format="yuv420p")


class SaveSequence:
    """Writes the whole sequence to one MP4 (H.264 + AAC), streaming pre-made clips from their files."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "sequence": (SEQUENCE,),
            "filename_prefix": ("STRING", {"default": "Personalized_Spots/video"}),
            "width": ("INT", {"default": 1920, "min": 64, "max": 7680, "step": 2}),
            "height": ("INT", {"default": 1080, "min": 64, "max": 4320, "step": 2}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001,
                              "tooltip": "Output frame rate. Clips at another rate are conformed by repeating or dropping frames."}),
            "fit": (["crop", "pad"], {"tooltip": "Clips with another size: crop = fill the frame and trim the excess, pad = letterbox."}),
            "ceiling_db": ("FLOAT", {"default": -2.0, "min": -12.0, "max": 0.0, "step": 0.1, "tooltip": "Peak limiter ceiling for the final mix."}),
            "crf": ("INT", {"default": 19, "min": 0, "max": 51, "tooltip": "H.264 quality: lower = better and bigger."}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("filepath",)
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = CATEGORY

    def run(self, sequence, filename_prefix, width, height, fps, fit, ceiling_db, crf):
        import av
        import folder_paths
        from comfy.utils import ProgressBar

        if not sequence:
            raise ValueError("The sequence is empty: connect at least one 'Add clip' node.")
        w, h = width - width % 2, height - height % 2
        rate = Fraction(fps).limit_denominator(1001)

        # ---- plan: how many output frames each clip gets
        plan = []
        for clip in sequence:
            src_fps, src_n = _probe(clip)
            plan.append((clip, src_fps, max(1, round(src_n / src_fps * fps))))
        total = sum(n for _, _, n in plan)

        # ---- audio: each clip fitted to its picture length, joined, then limited
        audio = np.concatenate([_clip_audio(clip, round(n / fps * SAMPLE_RATE)) for clip, _, n in plan], axis=1)
        audio = limit_peaks(audio, SAMPLE_RATE, ceiling_db)

        # ---- output path
        out_dir = folder_paths.get_output_directory()
        full_dir, fname, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, out_dir, w, h)
        name = f"{fname}_{counter:05}.mp4"
        path = os.path.join(full_dir, name)

        pbar = ProgressBar(total)
        with av.open(path, mode="w") as out:
            v = out.add_stream("libx264", rate=rate)
            v.width, v.height, v.pix_fmt = w, h, "yuv420p"
            v.options = {"crf": str(crf), "preset": "medium"}
            a = out.add_stream("aac", rate=SAMPLE_RATE)
            a.layout = "stereo"
            a.bit_rate = 192000

            # Encode all audio up front (a few MB): this also opens the audio encoder before the
            # container header is written. Packets are then interleaved with the video as it streams.
            apk = []
            step = 1024
            for i in range(0, audio.shape[1], step):
                af = av.AudioFrame.from_ndarray(np.ascontiguousarray(audio[:, i:i + step], dtype=np.float32),
                                                format="fltp", layout="stereo")
                af.sample_rate, af.pts = SAMPLE_RATE, i
                apk.extend(a.encode(af))
            apk.extend(a.encode())

            def mux_audio_until(t):
                while apk and apk[0].pts * apk[0].time_base <= t:
                    out.mux(apk.pop(0))

            idx = 0

            def write(frame):
                nonlocal idx
                frame.pts = idx
                idx += 1
                for p in v.encode(frame):
                    out.mux(p)
                mux_audio_until(idx / fps)
                pbar.update(1)

            counts = []
            for clip, src_fps, n_out in plan:
                written, last = 0, None
                for j, src in enumerate(_source_frames(clip)):
                    if written >= n_out:
                        break
                    # source frame j covers [j, j+1) / src_fps: emit every output frame that starts inside it
                    if (written + 1e-6) / fps >= (j + 1) / src_fps:
                        continue
                    last = _conform(src, w, h, fit).to_ndarray()
                    while written < n_out and (written + 1e-6) / fps < (j + 1) / src_fps:
                        write(av.VideoFrame.from_ndarray(last, format="yuv420p"))
                        written += 1
                if last is None:
                    raise ValueError("A clip in the sequence has no video frames.")
                while written < n_out:  # source shorter than announced: hold its last frame
                    write(av.VideoFrame.from_ndarray(last, format="yuv420p"))
                    written += 1
                counts.append(written)
            for p in v.encode():
                out.mux(p)
            mux_audio_until(float("inf"))

        print(f"[Spot Sequencer] {name}: {' + '.join(map(str, counts))} = {total} frames, "
              f"{audio.shape[1] / SAMPLE_RATE:.2f} s audio, {w}x{h} @ {fps:g} fps")
        return {"ui": {"images": [{"filename": name, "subfolder": subfolder, "type": "output"}], "animated": (True,)},
                "result": (path,)}


NODE_CLASS_MAPPINGS = {
    "SpotSequencer_AddGeneratedClip": AddGeneratedClip,
    "SpotSequencer_AddPremadeClip": AddPremadeClip,
    "SpotSequencer_SaveSequence": SaveSequence,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SpotSequencer_AddGeneratedClip": "Add generated clip · Añadir clip generado",
    "SpotSequencer_AddPremadeClip": "Add pre-made clip · Añadir clip prefijado",
    "SpotSequencer_SaveSequence": "Save sequence → MP4 · Guardar secuencia → MP4",
}

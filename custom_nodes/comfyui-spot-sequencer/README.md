# comfyui-spot-sequencer

Three small nodes that chain **generated clips** and **pre-made clips** into one MP4. Pure Python, no models,
nothing to download: they only use libraries a standard ComfyUI already ships with (`torch`, `torchaudio`,
`numpy`, `scipy`, `av`).

```
Add generated clip ─▶ Add pre-made clip ─▶ Add pre-made clip ─▶ … ─▶ Save sequence → MP4
```

Each "Add" node takes the sequence so far, appends its clip and passes the sequence on. Clips play in chain
order. Any number, any mix, any order.

## Nodes

### `SpotSequencer_AddGeneratedClip` — Add generated clip
For a clip made in the graph (frames + audio in memory), e.g. an LTX-2.5 greeting.

| Input | Default | |
|---|---|---|
| `images`, `audio` (optional), `fps` | — | from the generation (`Get Video Components`) |
| `normalize_loudness` | on | generated voices come out at a different volume every time |
| `target_lufs` | −14 | integrated loudness target (ITU-R BS.1770); match it to your pre-made clips |
| `sequence` (optional) | — | clips that play before this one; leave empty to start a sequence |

Frames are kept as 8-bit on the CPU while they wait (a 5 s 1080p clip is ~0.75 GB instead of ~3 GB).

### `SpotSequencer_AddPremadeClip` — Add pre-made clip
For a finished video file, from the core `Load Video` node. Nothing is decoded here: the node only keeps a
reference to the file.

| Input | Default | |
|---|---|---|
| `video` | — | core `Load Video` |
| `normalize_loudness` | off | off keeps the clip's own mix |
| `target_lufs` | −14 | used only when normalize is on |
| `sequence` (optional) | — | clips that play before this one |

### `SpotSequencer_SaveSequence` — Save sequence → MP4
Writes every clip, in order, into one H.264 + AAC file. Pre-made clips are **read frame by frame from their
file and written straight to the output**, so they are never held in memory.

| Input | Default | |
|---|---|---|
| `sequence` | — | end of the chain |
| `filename_prefix` | `Personalized_Spots/video` | sub-folders allowed |
| `width`, `height` | 1920 × 1080 | output size; clips with another size are conformed |
| `fps` | 24 | output frame rate; clips at another rate have frames repeated or dropped |
| `fit` | crop | `crop` fills the frame and trims the excess, `pad` letterboxes |
| `ceiling_db` | −2.0 | look-ahead peak limiter on the final mix (4× oversampled peak check) |
| `crf` | 19 | H.264 quality |

Audio: every clip is resampled to 48 kHz stereo and fitted to the exact length of its picture (so sound and
picture cannot drift across cuts), with a 5 ms fade at each cut to avoid clicks. A clip without audio becomes
silence. The node returns the file path and shows the video in the UI like the core `Save Video` node.

## Why streaming matters

Joining clips as image batches holds every frame in memory as float32: a 36 s 1080p spot is ~21 GB for the
frames plus as much again for the concatenated batch. An earlier version of this workflow did that and reached
88.8 GB of committed memory on a 64 GB machine. Streaming from the file avoids it: joining 45 s of 1080p
pre-made video took 18 s with no growth in process memory (RTX 4060 Ti 16 GB, 64 GB RAM).

## Install

Copy this folder into `ComfyUI/custom_nodes/` and restart ComfyUI. Nothing to `pip install` on a standard
ComfyUI (`requirements.txt` lists the versions it was tested with).

## License

MIT.

# Personalized ad spots for ComfyUI

One video per person: a short **generated clip in which a character says their name**, followed by the
**spot you already produced**. All of it inside ComfyUI, on open weights, on your own machine.

> **ES (resumen).** Workflow de ComfyUI para producir videos publicitarios personalizados en lote. Cada video
> abre con un saludo generado con LTX-2.5 (imagen a video con voz y labios sincronizados) que dice el nombre de
> la persona, y sigue con clips prefijados (tu spot, una placa de cierre). Es modular: cada clip es un grupo de
> nodos que se suma a una cadena, así que añadir otro clip es duplicar un grupo. Corre en local con modelos de
> pesos abiertos. Un script sobre el Comfy SDK carga la lista de clientes (CSV o Excel), envía los trabajos,
> descarga los videos en masa y se puede cortar y reanudar. Es mi intento de una versión abierta de las apps de
> presentador con lip-sync para anuncios (tipo Higgsfield), para el reto *Open Source Higgsfield*. El resto del
> documento está en inglés.

Built for the *Open Source Higgsfield* challenge (#OpenSourceHiggsfield). My attempt at an open version of
the **talking-presenter ad apps** that platforms like Higgsfield offer (lip-synced characters for UGC-style ads,
as in Lipsync Studio or UGC Factory), focused on one thing they are used for: **personalized ads at scale**,
one video per customer, without paying per video and without uploading the customer list to anyone. It uses
open-weights models only, with no partner nodes or APIs. This project is not affiliated with Higgsfield.

### What I think is new here

- **Generated and pre-made clips in one graph.** A small node pack (`comfyui-spot-sequencer`) adds a
  *sequence* type: generated clips (frames + audio) and existing video files add themselves to it in any order,
  and one node writes the result, so the finished ad comes out of the same graph that generates the greeting.
  Pre-made clips are streamed from disk at save time, so a long spot does not fill the memory.
- **Modular by duplication.** Every clip is a group of nodes; adding a clip to the ad is copy, paste and connect.
- **Broadcast-style audio inside the graph.** Each clip is levelled to a loudness target (ITU-R BS.1770) and the
  whole spot goes through a peak limiter, so a quiet generated greeting and a loud finished spot play at a
  similar level.
- **A customer list, not a single video.** A campaign script on the Comfy SDK takes a CSV or Excel list and can
  be stopped and resumed without submitting anything twice.

## Who would use it

- A small business that wants to send 50 welcome, birthday or offer videos without paying per video.
- An agency that already has a finished spot and wants every viewer to be greeted by name before it plays.
- Anyone who cannot upload a customer list to a third party: names never leave the machine.

## What it looks like

`examples/` has two finished videos from the sample list, exactly as the campaign script wrote them
(`customer_0001_Emma.mp4`, `customer_0002_Mateo.mp4`: 20 s each, 5 s greeting + 10 s spot + 5 s end card),
and the manifest of that run.

```
① name, id ─▶ ② generated clip (LTX-2.5) ─▶ ③ pre-made clip ─▶ ④ pre-made clip ─▶ ⑤ one MP4
                 "Hi, Emma! …"                 your spot           end card
```

Every clip is one group of nodes that adds itself to a *sequence*; the last node writes the sequence to a
single MP4. **To add a clip, duplicate its group and plug it into the chain.** Generated and pre-made clips can
go in any number and any order (a pre-made intro before the greeting, a second generated clip as a personalized
goodbye, and so on).

## What is in the repo

```
workflows/
  Personalized_Spot.json         the workflow (UI, with notes in English and Spanish on the canvas)
  Personalized_Spot_API.json     same graph in API format: the one the campaign script uses
  Join_Clips.json / _API.json    helper: pre-made clips only → one MP4 (how the demo spot was put together)
custom_nodes/comfyui-spot-sequencer/   the three nodes this project adds (pure Python, no models)
assets/                          demo assets, all generated for this repo (see assets/README.md)
setup/
  install.py                     copies the node pack and the demo assets into your ComfyUI
  models.json                    every model: folder, size, SHA256, URL (~39.7 GB)
  download_models.py             downloads and verifies them
jobs/
  campaign.py                    customer list in, one MP4 per person out: import, submit, download, resume (Comfy SDK)
  sample_customers.csv           made-up names for testing
tools/
  check_output.py                checks finished videos (frames, audio length, loudness, spoken name)
examples/                        finished videos to compare against
```

## Requirements

- ComfyUI with the LTX-2.5 nodes. Tested on **0.37.0**; the generated-clip group is the native LTX-2.5
  image-to-video template.
- An NVIDIA GPU with **16 GB of VRAM** and 64 GB of RAM (tested on an RTX 4060 Ti 16 GB). I have not tested
  less. The ComfyUI process peaked at 22 GB of RAM in use (37 GB committed).
- ~40 GB of disk for the models.
- **No third-party custom nodes.** Only the pack in this repo; everything else is ComfyUI core.

## Setup

```bash
git clone https://github.com/untitledxdamage/comfyui-personalized-ad-spots
cd comfyui-personalized-ad-spots
python setup/install.py /path/to/ComfyUI                 # node pack -> custom_nodes/, demo assets -> input/
HF_TOKEN=hf_xxx python setup/download_models.py /path/to/ComfyUI    # ~39.7 GB, SHA256-verified
```

Then restart ComfyUI.

The LTX-2.5 repository on Hugging Face is gated: accept its terms on
[the model page](https://huggingface.co/Lightricks/LTX-2.5) and use a token. If you already have the LTX-2.5
models from the native ComfyUI template, `python setup/download_models.py /path/to/ComfyUI --check` tells you
whether anything is missing.

## Make one video in the UI

Drag `workflows/Personalized_Spot.json` onto the canvas and press **Run**. Type another name in
**① NAME** and run again. The MP4 lands in `output/Personalized_Spots/<batch>/<customer_id>_00001.mp4`.

## Run a customer list (Comfy SDK)

`jobs/campaign.py` takes a customer list and gets one video per person onto your disk. It is built on
[`comfy-sdk`](https://pypi.org/project/comfy-sdk/) and only talks to the Comfy API, so the same commands work
against a local ComfyUI (through the official proxy), a Comfy API deployment or Comfy Cloud: only
`COMFY_BASE_URL` changes.

```bash
pip install "comfy-sdk>=0.4" comfy-api-proxy
comfy-api-proxy start                          # local ComfyUI must be running on 127.0.0.1:8188
export COMFY_BASE_URL="http://127.0.0.1:8189"

python jobs/campaign.py import --campaign campaigns/loyalty --customers jobs/sample_customers.csv
python jobs/campaign.py run --campaign campaigns/loyalty --batch Loyalty_Offer \
    --first-frame assets/host_first_frame.png \
    --clip 50=assets/cafe_spot.mp4 --clip 60=assets/cafe_endcard.mp4

comfy-api-proxy stop
```

On Windows PowerShell use `$env:COMFY_BASE_URL = "http://127.0.0.1:8189"` instead of `export`.

Videos land in `downloads/Loyalty_Offer/<customer_id>.mp4` and `campaigns/loyalty/manifest.csv` lists every
person with file, job id, seconds (from submit to finished, queue time included) and status.

A campaign is a folder with one small SQLite file, the ledger, holding a row per person. Every command reads
and updates it, so each step can be stopped, repeated or moved to another machine:

| Command | What it does |
|---|---|
| `import` | Loads a CSV, TSV or XLSX (`pip install openpyxl` for XLSX). Detects delimiter and encoding, maps your columns (`--id-column`, `--name-column`), can keep only the first name and fix the case (`--first-name-only --title-case`), and writes every row it cannot render to `rejected.csv` with the reason (empty name, duplicate id…). Importing again only adds new people. |
| `submit` | Keeps `--in-flight N` jobs submitted until every row is rendered. |
| `download` | Fetches finished MP4s with `--workers N` in parallel, checks each file's size against what the server reports, and can split them into sub-folders of `--shard-size` files. |
| `run` | `submit` and `download` together. |
| `status` | Counts per state, average seconds per video, videos per hour so far and the time left at that pace. |
| `export` | Writes `manifest.csv`. |
| `retry` | Puts failed rows back in the queue; `--ids A-1001 A-1002` re-renders specific people with a new seed. |

**Nothing is sent twice.** A row's idempotency key is saved before the request and its job id right after, so
after a crash, a closed laptop or Ctrl+C the next run looks the running jobs up again instead of submitting
them (and paying for them) a second time. If the same options are not used when resuming, it stops and says so,
because half a campaign with a different spot is rarely what you want.

### Scaling it

- **Throughput is `workers × 3600 / seconds per video`.** Set `--in-flight` to the number of GPUs or workers
  serving the API; more than that only makes the queue longer. On my single 16 GB card that is about 12 videos
  per hour. I have no measurements on cloud GPUs.
- **Disk.** A 20 s video at the default quality is about 8 MB, so 1,000 people is ~8 GB and 50,000 is ~400 GB.
  `--set 80.crf=23` makes smaller files; `--shard-size 1000` keeps folders manageable.
- **Where to run it.** The script needs no GPU: it can run on the machine where the videos should end up, for
  example a small cloud server with a big disk, while the rendering happens wherever `COMFY_BASE_URL` points.
  Rendering and downloading can also be split: `submit` from one machine, then copy the campaign folder to
  another and run `download` there with the same credentials. Outputs stay on the server only for as long as it
  keeps the job, so do not leave the download for weeks later.
- **Pre-made clips are uploaded once** per campaign (by content hash), not once per person. The local proxy
  accepts uploads up to 100 MB by default; for a bigger spot start it with `--max-upload-mb`.
- **The ledger holds your customers' names and ids.** It is a local file; treat it like the list itself.

What I could verify: the full flow on my PC through the local proxy (import from CSV and XLSX, two jobs in
flight, a kill in the middle of a run, download from a copy of the campaign folder, re-rendering one person
with `retry --ids`), and the ledger logic with a simulated backend on a 50,000-row list (import with rejects, 64 jobs in flight,
stop and resume, retries, sharded downloads, no duplicate submissions). What I could not: a real cloud
deployment.

## Check the results

```bash
pip install av numpy scipy faster-whisper
python tools/check_output.py downloads/Loyalty_Offer --frames 484 --transcribe --manifest campaigns/loyalty/manifest.csv
```

For each video it prints frame count, audio length, loudness and true peak, and with `--transcribe` what was
heard in the greeting, flagging the videos where the name was not recognised. Speech recognition gets unusual
names wrong and also flags spellings that sound the same (it wrote "Sophia" for Sofia and "May" for Mei in my
tests), so a flag means "listen to this one". The flagged ids are printed at the end, ready for
`campaign.py retry --ids`. For a big campaign, `--sample 200` checks an even sample instead of every file.

## Make it yours

| You want to… | Change |
|---|---|
| Use your own character | **FIRST FRAME** (② group) and the description in the **DIRECTION PROMPT** |
| Say something else | **GREETING SCRIPT**; keep `{name}` where the name goes |
| Another voice or language | The first sentence of the direction prompt describes the voice. Write the script in that language |
| Use your own spot | Upload it in a **PRE-MADE CLIP** group (any size or frame rate; it is conformed on save) |
| Add another pre-made clip | Duplicate a pre-made group and connect `sequence` in and out |
| Add a second generated clip | Duplicate the ② group and chain its *Add generated clip* where it should play |
| Vertical video | Set `width`/`height` in **SAVE SEQUENCE** and the aspect ratio in *Generated clip resolution* |

When you add groups, new nodes get new IDs. Export the workflow in API format (*File → Export (API)*) and pass
it with `--workflow`, and its clips with `--clip <LoadVideo node id>=file.mp4`.

Notes on prompting LTX-2.5 here: the distilled model runs at CFG 1, so the **negative prompt has no effect**
and everything is steered from the positive prompt. **Opening the prompt with the voice** (who speaks and how)
is what kept the voice consistent between videos.

## Measured on my PC (RTX 4060 Ti 16 GB, 64 GB RAM)

| | Value |
|---|---|
| One video (5 s generated + 15 s pre-made), models already loaded | **285–305 s** (list of 5 through the SDK: 292, 296, 298, 305, 285) |
| First video after starting ComfyUI (model load included) | 304–313 s |
| Same workflow run from the UI | 296 s |
| Two generated clips + three pre-made clips (groups duplicated in the UI) | 575 s |
| Joining only: 45 s of 1080p pre-made video with `Join_Clips` | 18 s, no growth in process memory |
| Peak memory of the ComfyUI process | 22 GB in use, 37 GB committed (mostly LTX-2.5 weights staged in RAM) |
| VRAM | fits in 16 GB |
| Output | 484 frames (121 + 242 + 121), 20.17 s, 1920×1080, ~8 MB; greeting at −14.0 LUFS, true peak ≤ −2.5 dBFS |

In that run the script was killed during the second video and started again: it picked the running job up
instead of submitting it twice. The optional transcription check heard the right name in all five greetings
(Emma, Mateo, Aiko, Priya, Lucas).

## Limits

- **About 5 minutes per video on a 16 GB card.** Almost all of it is the 5 s generated clip. A list of 1,000
  names is three and a half days on one GPU; this is for small lists locally, or for more GPUs.
- **Only tested locally.** I have not deployed it to the Developer Platform or run it on Comfy Cloud. The
  campaign script uses the same SDK calls either way, but that path is unverified.
- **The name is not checked by the workflow.** LTX-2.5 said the sample names correctly in my tests, but an
  unusual name can come out wrong; `tools/check_output.py --transcribe` helps find those, and
  `campaign.py retry --ids` renders them again with another seed.
- **One character still, one framing.** The greeting animates a single image. Voice and delivery vary a little
  from video to video.
- Cuts between clips are hard cuts (with a 5 ms audio fade). No transitions.
- Tested on Windows 11 with one GPU. I have not run it on Linux or macOS.

## Tools, models and techniques

- **ComfyUI** 0.37.0, core nodes plus the pack in this repo.
- **LTX-2.5** (22B distilled, int8) is the only video model: image-to-video with audio for the greeting, using
  the native two-stage template (half-resolution pass, ×2 latent upscale, second pass). It also animated the
  three shots of the demo spot.
- **Z-Image Turbo** generated the still images (the host's first frame and the spot's keyframes) from text.
- **Comfy SDK** (`comfy-sdk` 0.4) and `comfy-api-proxy` drive the campaigns.
- `faster-whisper` is used only by the optional check, not by the workflow.
- The node pack: ITU-R BS.1770 loudness levelling, a look-ahead peak limiter, and streaming of pre-made clips
  frame by frame with PyAV so they are never held in memory.
- I wrote the workflow, the nodes and the scripts with the help of an AI coding assistant (Claude Code), and
  tested them on my own machine.

This started from a workflow I had built earlier for the same kind of job; for the challenge I rebuilt it as a
generic, modular version with new assets.

## Licenses

- Code and workflows in this repository: **MIT** (see `LICENSE`).
- Demo assets in `assets/` and `examples/`: generated for this repo, free to use with it. The person in them is
  not a real person and the café has no name on purpose.
- Models are **not** included and keep their own licenses: LTX-2.5 is under the
  [LTX-2.x Community License](https://huggingface.co/Lightricks/LTX-2.5) (free below a revenue threshold, read
  it before commercial use); Z-Image Turbo is Apache-2.0.

## Feedback

I would really appreciate criticism: things that break, steps in the setup that are unclear, better ways to do
the join or the batch. Issues and pull requests are welcome.

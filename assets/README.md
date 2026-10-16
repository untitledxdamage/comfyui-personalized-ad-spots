# Demo assets

Everything here was generated for this repository, locally in ComfyUI, from text prompts. There is no real
person, no real brand and no third-party footage. The café has no name on purpose.

| File | What it is | How it was made |
|---|---|---|
| `host_first_frame.png` | The still the greeting animates (1920×1088) | Z-Image Turbo, text-to-image |
| `cafe_spot.mp4` | Pre-made clip 1: the "spot" (10 s, two shots, voice-over on the second) | Two Z-Image Turbo stills animated with LTX-2.5 image-to-video, joined with `workflows/Join_Clips.json` |
| `cafe_endcard.mp4` | Pre-made clip 2: the end card (5 s) | One Z-Image Turbo still animated with LTX-2.5 |

Replace them with your own character, spot and end card; nothing in the workflow depends on these files beyond
their names in the loader nodes.

## Settings

**Z-Image Turbo** (`z_image_turbo_int8_convrot` + `qwen_3_4b_fp8_mixed` text encoder + `ae` VAE): 1920×1088,
8 steps, CFG 1, `res_multistep` / `simple`, `ModelSamplingAuraFlow` shift 3. About 21 s per image on an
RTX 4060 Ti 16 GB.

**LTX-2.5** clips: the same image-to-video graph the workflow uses for the greeting (5 s, 24 fps, 1920×1088,
two-stage distilled), with the shot description in place of the greeting prompt.

## Prompts

**Host (first frame)**

> A Latina woman in her mid fifties with grey-streaked hair tied back, round glasses, a cream knitted cardigan
> and a terracotta canvas apron stands behind the wooden counter of a small neighborhood coffee shop, facing the
> camera, looking straight into the lens with a warm, relaxed closed-mouth smile, shoulders square to the camera,
> hands resting out of frame. Medium close-up, eye level, head and shoulders centered with a little headroom.
> Plain unbranded apron with no text or logo. Behind, softly out of focus: a chrome espresso machine, shelves
> with plain ceramic cups and glass jars of coffee beans, a small potted plant, warm pendant lamps and daylight
> from a window on the left. No signs, no lettering, no logos anywhere. Natural candid photograph, 50mm lens,
> shallow depth of field, soft natural light, realistic skin texture, fine film grain.

**Spot, shot 1 (still)** — espresso pouring into a white cup, extreme close-up, no text or logos.
**Animation:** static shot, the espresso keeps pouring, crema rises, steam drifts; audio is the machine's hum
and the trickle into the cup, no music, no voices.

**Spot, shot 2 (still)** — a latte, a wooden stamp, an ink pad and a paper loyalty card stamped with coffee
beans on a wooden counter; a person in an apron out of focus behind, face out of frame.
**Animation:** static shot, steam rises, the person shifts in the background, and an off-screen woman's
voice-over says: "This week, your sixth coffee is on us."

**End card (still)** — a small chalkboard on the counter, hand-lettered "YOUR 6TH COFFEE IS ON US" and
"see you at the counter", next to a steaming cup.
**Animation:** static shot, steam rises, the chalk lettering stays still; quiet café room tone, no voices.

The full prompt text for the greeting is inside the workflow (**DIRECTION PROMPT**).

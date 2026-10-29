# farm-sequence

A pipeline for a scroll-scrubbed product sequence: a procedural Blender scene is rendered to frames, and a web page plays those frames on a canvas as you scroll.

## How it works

```
Blender scene (headless) → PNG frames → AVIF frames → <canvas> + GSAP ScrollTrigger
```

1. A Python script builds the scene from scratch inside Blender (geometry, materials, lights, camera, keyframes) and renders it with Cycles to numbered PNG files.
2. `to_avif.py` converts the PNG folder to AVIF with ffmpeg and libaom.
3. `web/index.html` loads every AVIF frame, then maps the scroll position to a frame index and draws that frame on a canvas. GSAP ScrollTrigger drives the frame index and Lenis provides smooth scrolling.

The rendered frames are not in the repository (`.gitignore` excludes `frames*/`, `test*/` and `web/frames*/`). Generate them with the steps under [Usage](#usage).

## Files

```
scene_tablet.py         Blender scene, base variant (solid tablet)
scene_tablet_split.py   Blender scene, center split variant
scene_tablet_hinge.py   Blender scene, hinged lid variant
to_avif.py               PNG → AVIF batch conversion (ffmpeg + libaom-av1)
web/index.html           demo page that plays the sequence
```

### The three scene variants

All three render a 144 frame sequence (frames 1 to 144) of an olive green tablet over a cream gradient background. The camera orbits the tablet and small glowing particles drift away from it. All keyframes are linear.

| Script | What happens | Particles come from | Web folder |
|---|---|---|---|
| `scene_tablet.py` | The closed tablet, tilted, spins slowly while the camera orbits and dollies in. 85 mm lens, f/1.6. | The tablet surface (70% side wall, 30% top and bottom faces), born between frames 28 and 108 | `web/frames` |
| `scene_tablet_split.py` | The tablet is cut in two with a boolean. Between frames 38 and 78 the top half lifts and tilts to show its cut face. The bottom half drops slightly. The camera pulls back to keep both halves in frame. 70 mm lens, f/2.0. | The cut face, born between frames 44 and 120 | `web/frames_split` |
| `scene_tablet_hinge.py` | Same cut as the split variant, but the top half swings open on a hinge at its far edge instead of lifting. The camera pulls back a little further. | The cut face, born between frames 44 and 120 | `web/frames_hinge` |

In the split and hinge variants the cut faces get a separate interior material (lime granules in an olive matrix) through the boolean modifier's `material_mode = "TRANSFER"`, and an extra area light lights the interior.

## Requirements

- **Blender 5.2.** The scripts were written and tested on 5.2. `scene_tablet.py` handles both the old `Action.fcurves` API and the slotted actions API from Blender 5.x.
- **An NVIDIA GPU with OptiX** is what the scripts are set up for: they select the OptiX compute device type, enable OptiX and CUDA devices, and use the OptiX denoiser. Other GPUs and CPU rendering are untested.
- **Python 3** to run `to_avif.py` and the local web server (tested with 3.11).
- **ffmpeg built with libaom-av1** on your `PATH` (tested with 8.1.2). Check with `ffmpeg -encoders | grep libaom`.
- **A static file server** to serve `web/` over HTTP. Python's built-in server is enough.
- The demo page loads GSAP 3.13.0, ScrollTrigger and Lenis 1.1.13 from public CDNs, so it needs a network connection.

## Usage

Run all commands from the repository root. The scripts resolve `--out` relative to the current directory.

In the commands below, `blender` means the Blender executable. Use the full path to it if it is not on your `PATH`.

### 1. Render test frames

Render a few single frames at low settings, check them, and adjust the scene. This is where most of the iteration happens.

```bash
blender -b --factory-startup -noaudio -P scene_tablet.py -- --frames 1,60,110 --samples 48 --res 1280x720 --out test
```

This writes `test/test_0001.png`, `test/test_0060.png` and `test/test_0110.png`.

### 2. Render the full sequence

Pass `--anim` to render the whole frame range. Pick the output folder that matches the variant, because the web page looks for these folder names:

```bash
blender -b --factory-startup -noaudio -P scene_tablet.py       -- --anim --samples 64 --res 1920x1080 --out frames
blender -b --factory-startup -noaudio -P scene_tablet_split.py -- --anim --samples 64 --res 1920x1080 --out frames_split
blender -b --factory-startup -noaudio -P scene_tablet_hinge.py -- --anim --samples 64 --res 1920x1080 --out frames_hinge
```

Each run writes `frame_0001.png` to `frame_0144.png` into the output folder.

Script arguments (everything after `--`):

| Argument | Default | Meaning |
|---|---|---|
| `--anim` | off | Render the full range from `--start` to `--end`. Without it, only the `--frames` list is rendered. |
| `--frames` | `60` (base), `90` (split, hinge) | Comma separated frames to render as stills when `--anim` is not set |
| `--samples` | `64` | Cycles samples per pixel (adaptive sampling and denoising are on) |
| `--res` | `1920x1080` | Output resolution, `WIDTHxHEIGHT` |
| `--out` | `./test` (base), `./test_split` (split, hinge) | Output folder, created if missing |
| `--start` | `1` | First frame |
| `--end` | `144` | Last frame |

Always pass `--out` for the hinge variant: its default is `./test_split`, the same as the split variant, so the two would overwrite each other.

### 3. Convert to AVIF

```bash
python to_avif.py frames_hinge web/frames_hinge --crf 32
```

Repeat with `frames web/frames` and `frames_split web/frames_split` for the other variants. The output keeps the file names, so `frame_0001.png` becomes `frame_0001.avif`.

`to_avif.py` arguments:

| Argument | Default | Meaning |
|---|---|---|
| `src` | required | Folder with the PNG frames |
| `dst` | required | Output folder for the AVIF frames, created if missing |
| `--crf` | `32` | libaom quality. Lower means higher quality and larger files. |
| `--width` | `0` | Scale to this width in pixels (Lanczos, height keeps the aspect ratio). `0` keeps the source size. |
| `--cpu-used` | `6` | libaom speed preset, 0 to 8. Higher is faster and gives larger files. |
| `--jobs` | number of CPU cores | Number of frames encoded in parallel |

At the end it prints the total PNG size, the total AVIF size and the average size per frame. Frames that fail to encode are listed with the ffmpeg error.

### 4. Serve the demo page

```bash
python -m http.server 8123 --directory web
```

Open <http://localhost:8123/>. The page expects the frames at `web/<folder>/frame_0001.avif` through `frame_0144.avif`:

| URL | Variant | Frame folder |
|---|---|---|
| `/?seq=solid` | base | `web/frames` |
| `/?seq=split` | center split | `web/frames_split` |
| `/?seq=hinge` or `/` | hinged lid (default) | `web/frames_hinge` |

The links in the bottom left switch between variants. The box in the bottom right shows the current frame and scroll progress, and reports how many frames are missing if the folder is incomplete.

## Tuning

### Frame count

The frame count is set in two places that must match:

- the scene: `--start` and `--end` (default 1 and 144)
- the page: `const TOTAL = 144;` in `web/index.html`

The page loads frames numbered from 1, so keep `--start 1`. In `scene_tablet.py` the tablet, camera and orbit keyframes follow `--start` and `--end`, but the particle timing (`P_BIRTH`, `P_LIFE`) is in absolute frames. In the split and hinge variants the opening (`SPLIT_IN`, `SPLIT_OUT`) and particle timing are also absolute frames, so change those constants as well when you change the length.

The scroll distance of the sequence is the height of `.seq` in the page CSS (`500vh`).

### Resolution and quality

- Render resolution: `--res`. To ship a smaller size from the same render, use `to_avif.py --width`.
- Render noise: `--samples`.
- File size: `to_avif.py --crf` and `--cpu-used`.

### Scene constants

At the top of each scene script:

| What | Where |
|---|---|
| Palette (cream, olive, lime, sage) | `CREAM`, `CREAM_DEEP`, `OLIVE`, `OLIVE_DARK`, `LIME`, `SAGE` (`INTERIOR` in the split and hinge variants) |
| Particle count, birth window, lifetime | `P_COUNT`, `P_BIRTH`, `P_LIFE` |
| Tablet tilt and spin | `TILT_X`, `TILT_Y` and the tablet (or assembly) rotation keyframes |
| Camera orbit and dolly | the `cam.location` and `orbit.rotation_euler` keyframes |
| Opening timing (split, hinge) | `SPLIT_IN`, `SPLIT_OUT` |
| Lift and tilt of the top half (split) | `LIFT`, `TOP_TILT` |
| Hinge position, angle and lift (hinge) | `HINGE_Y`, `HINGE_ANGLE`, `HINGE_LIFT` |

The random seeds are fixed (7 for the base variant, 11 for the others), so particle layouts are the same on every run.

### Settings that were found by trial and error

- **World `Background` strength must stay at 1.0.** Strength multiplies the color directly. At 0.75 the cream background turned beige. Change brightness with the lights instead.
- **Keep the lights low.** A 900 W key light with the cream ambient washed the olive tablet out to light green. The key light is now 210 W.
- **Keep the roughness noise scale high** (70 or more). At 12 it made cloudy highlight patches on the top face.
- **The dark particle variant looked like dirt on the cream background.** It was changed to sage and its share reduced to 12%.
- **All keyframes are linear.** In a scroll-scrubbed sequence the user controls time. With easing, the animation speeds up and slows down while the user scrolls at a constant speed. Each script sets `keyframe_new_interpolation_type = "LINEAR"` before adding keyframes.
- **Motion blur is off**, for the same reason.
- The view transform is `Standard` so the background color matches its hex value in the output.

## Performance notes

Rendering:

- At 1920x1080 and 64 samples, a frame takes about 22 seconds on an RTX 4060 Ti, so 144 frames take about 55 minutes. `--samples 32` (the OptiX denoiser cleans up most of the noise) or `--res 1440x810` make it faster.
- `use_persistent_data` keeps the Cycles session alive between frames, which avoids about 20 seconds of scene sync per frame during `--anim` renders.

Delivery:

- **AVIF** keeps the frames small enough to preload the whole sequence. On this scene, `--crf 32` gives about 2 to 4 KB per frame with no visible artifacts. Busier or more textured scenes may need a crf of 24 to 28.
- **Preloading:** the page requests all frames at startup with `decoding = "async"` and shows a percentage while they load. Scrubbing starts once every request has finished. A frame that fails to load does not block the others: the page draws the nearest loaded frame instead and logs a warning.

Drawing:

- `devicePixelRatio` is capped at 2. A 3x canvas on phones costs GPU time for no visible gain.
- The same frame is never drawn twice in a row (the `lastDrawn` check).
- Frames are drawn with `object-fit: cover` math on a canvas created with `alpha: false`.
- `scrub: 1` (a number, not `true`) makes the playhead take 1 second to catch up with the scroll position, which smooths out uneven scrolling.
- Lenis has to be synced with ScrollTrigger or the scrub stutters: `lenis.on("scroll", ScrollTrigger.update)` and `gsap.ticker.add(...)`.
- With `prefers-reduced-motion: reduce`, the page shows the last frame as a still, sets up no scrub, and does not start Lenis.

## License

MIT. See [LICENSE](LICENSE).

---
name: daz-photography
description: Use when assembling a DAZ Studio character render and you want it to look like an intentional photograph rather than a default viewport view. Teaches intent-driven camera/framing decisions (focal length, shot size, angle), composition rules, portrait lighting patterns, and natural character posing, mapped 1:1 to the existing MCP tools (daz_frame_shot, daz_apply_camera_angle, daz_create_camera, daz_apply_lighting_preset, daz_apply_composition_rule, posture/look helpers, daz_render_shot).
---

# DAZ Studio Photography

Goal: act like a studio photographer. Before touching any tool, decide the
**intended feeling** of the image, then translate that feeling into deliberate
camera, light, and pose choices. Every principle below is mapped to a concrete
MCP tool call you can execute right now.

Merely loading a figure and rendering with the default camera produces a flat,
eye-level, characterless image. Intent changes speed.

## 0. Start with intent

Pick one intent first. It drives every later choice.

| Intent | Lens | Shot size | Angle | Lighting |
|---|---|---|---|---|
| Hero / powerful | 85mm | low-angle full or cowboy | low-angle | Rembrandt or split |
| Beauty / fashion | 85mm | medium-close-up | eye-level | Butterfly |
| Vulnerable / small | 50mm | wide / full | high-angle | Soft key + gentle fill |
| Ominous / noir | 85mm | close-up | dutch-angle (subtle, ≤10°) | Split / lo-key |
| Grounded / real | 50mm | medium / full | eye-level | 3-point loop |
| Environmental | 35mm | wide-shot or EWS | eye-level | natural / golden-hour |

## 1. Lens & FOV kit (focal length)

`daz_create_camera(label, focal_length=…)` sets the lens. Focal length controls
**more than zoom** — it implicitly sets working distance for a given framing,
which is the real driver of how a face renders.

- **35mm** — environmental feel; but shot close-up it exaggerates the nose /
  wide face (perspective distortion). Use for full shots showing environment.
- **50mm** — "natural" look, closest to human perception; trustworthy, neutral.
- **85mm** — the classic portrait lens: flattering face proportions, compressed
  background, shallow depth of field. Use for head-shots and close-ups.
- **135mm** — even flatter / more compressed; needs room to back up.
- **Rule:** the flattery comes from *shooting farther away*, not the number
  alone. Pair your focal length with the correct `daz_frame_shot` distance so
  the face is framed the way the lens intended.

## 2. Shot size + angle (the camera)

Compose by calling, in order, `daz_create_camera` (or pick an existing camera)
then `daz_frame_shot(camera_label, subject_label, shot_type)` then
`daz_apply_camera_angle(camera_label, subject_label, angle)`.

**Shot sizes (daz_frame_shot `shot_type`):**

| shot_type | frames |
|---|---|
| `extreme-close-up` | eyes / mouth detail |
| `close-up` | face, head fills most of frame |
| `medium-close-up` | head and shoulders (~chest up) |
| `medium-shot` | waist up |
| `medium-full` | knees up |
| `full-shot` | entire body |
| `wide-shot` | body within environment |

**Angles (daz_apply_camera_angle `angle`):**

- `eye-level` — neutral, connection, default. Good for interviews/likeness.
- `high-angle` — camera above, looking down → subject appears small/weak/vulnerable.
- `low-angle` — camera below, looking up → power, heroism, authority. Land it
  for the hero shot.
- `dutch-angle` — roll/tilt → unease, tension, disorientation. **Use sparingly**
  (under ~10°) or the shot reads as a mistake.
- `overhead` / `worms-eye` — omniscient, dramatic extremes (rarely, for full-body establishing beats).
- `over-shoulder` — OTS for dialogue between two characters.

**The contrast rule:** high and low angles only land when they *contrast* with
the rest of the sequence/prevailing angle. Don't angle everything dramatically;
reserve angles for the emotional beat you want to hit.

## 3. Composition rules

After framing, refine placement with
`daz_apply_composition_rule(camera_label, subject_label, rule)`:

- `rule-of-thirds` — subject on a vertical third. The reliable default. Start here.
- `golden-ratio` — subject slightly closer to center than thirds; pleasing,
  natural flow. Use for elegant portraits / close-ups.
- `center-frame` — symmetric center; formality, power, iconic looks.
- `leading-lines` — diagonal leading into the subject.

**Non-tool composition checks to do yourself:**

- **Lead room** — leave space in the direction the character **faces/looks**
  (their "nose room"). A figure facing frame-left needs empty frame left.
- **Headroom** — eyes on the upper third, crown not clipped, chin not cropped.
- **Negative space** — a large empty area reads as loneliness/openness; use it.
- **Level horizon** — unless you deliberately chose a dutch angle, keep the
  horizon level; an accidental tilt is a classic failure.
- **Looking at the camera** — for a direct gaze, point the character's face at
  the camera using `daz_look_at_point` (mode `head` or `eyes`) with the camera's
  world coordinates; verify via `daz_list_cameras`/scene info.

## 4. Portrait lighting patterns

`daz_apply_lighting_preset(preset, subject_label)` creates the whole rig,
placed relative to the subject rather than the scene origin — always pass
`subject_label` (the figure node) so lights follow the character.

| preset | Key position (vs subject) | Signature shadow / look |
|---|---|---|
| `three-point` | key 45° side + ~45° above; fill opposite; rim behind | General-purpose dimension |
| `rembrandt` | key to the side and high (45° side + 45° up) with minimal fill | triangle of light on the shadow cheek; dramatic painterly |
| `butterfly` | key on the camera axis, slightly above the lens, pointing down | butterfly-shaped nose shadow; among the most flattering |
| `split` | key 90° to one side at face height | half face in light, half in shadow; intense, noir |
| `loop` | key 30–45° side, just above eye level | small nose shadow pointing toward corner of the mouth (not touching cheek) |

**Towards contrast (adjust fill).** Intensity = contrast. Reduce/omit fill for
drama (Rembrandt/split), balance it for beauty (butterfly/loop).

**Wrap the light (color/atmosphere).** After baking the pattern:
- `daz_set_mood_lighting("romantic"|"dramatic"|"scary"|"golden-hour"|"mysterious"|"peaceful", figure_label)`: retint intensity+color.
- `daz_apply_time_of_day("golden-hour"|"dawn"|"noon"|"dusk"|"night", …)` for sun-time simulation.
- `daz_apply_visual_style(...)` for holistic looks (cinematic / noir / high-key /
  low-key / fantasy).

## 5. Posing fundamentals

Pose the figure deliberately (`daz_reset_pose` first to clear any previous pose).

Natural poses share a few features — every one of these is a post-check:

- **Contrapposto** — weight shifts onto one leg; hips and shoulders tilt in
  **opposite** directions; the body makes a **S-curve / line-of-action**. No
  symmetric A-stance (dead look).
- **Shoulders ≠ hips** — an opposing rhythm between shoulder angle and hip
  angle reads "alive".
- **Center of gravity** stays over the support foot — the figure must look
  balanced, not about to topple.
- **Head tilt** — even a few degrees asymmetric, adds intent.
- **Hands** — visible and relaxed, not clipped by the frame or junky.
- **Arms** — slight counterbalance; avoid "stiff T-pose" arms.
- **Readable silhouette** — the pose is legible even silhouetted (a quick
  trick: squint at the render).

The tool pipeline (`SKILL_ACTORS.md` for details):
1. `daz_reset_pose(figure)` — clean slate.
2. `daz_set_body_language(figure, "confident" | "relaxed" | "defeated" | …)` — broad posture character.
3. `daz_look_at_character` (a posed counterpart) or `daz_look_at_point` (camera).
4. `daz_reach_toward` — extend an arm/limb deliberately.
5. `daz_interactive_pose(char1, char2, "face-each-other" | "handshake" | "hug" | "shoulder-arm")` for 2-character shots.
`daz_save_pose` / `daz_load_pose` to reuse a good pose.

## 6. Pre-render QA (run before `daz_render_shot`)

- **Face** looks **at the camera** (unless you intended otherwise).
- **Head** not clipped, **eyes** on upper third, **chin/crown** inside frame.
- Feet/skirt not clipped by bottom frame.
- **Subject lit** by a deliberate pattern (never flat on-all-sides).
- A **rim/hair light or backdrop** separates subject from the env.
- **Contact shadow** — the figure doesn't float.
- **Focus** on the eyes (set `Focal Distance` to the face, especially for 85mm
  with shallow depth of field).
- No blown-out whites / crushed blacks (unless that's the style).

## 7. Recipe cards

Sequence of real tool calls the render goes through, the QA, then render.

### Recipe 1 — Hero shot
1. `daz_create_camera("HeroCam", focal_length=85, ...)` (or reuse existing).
2. `daz_frame_shot(camera=..., subject=figure, shot_type="medium-shot")`.
3. `daz_apply_camera_angle(camera=..., subject=figure, angle="low-angle")`.
4. `daz_apply_lighting_preset("rembrandt", subject_label=figure)`.
5. `daz_reset_pose(figure)`; `daz_set_body_language(figure, "confident")`.
6. `daz_look_at_point(figure, <camera x>, <camera y>, <camera z>, "torso")` — gaze into camera.
7. QA: eyes vertical, headroom ok, triangle light on cheek.
8. `daz_render_shot("C:/renders/hero.png", width=1920, height=1080, camera="Perspective", quality="good")`.

### Recipe 2 — Beauty headshot
1. `daz_frame_shot(..., "close-up")`; angle `eye-level`.
2. `daz_apply_lighting_preset("butterfly", subject_label=figure)`.
3. `daz_apply_composition_rule(..., "golden-ratio")`.
4. `daz_set_emotion(figure, "serene" | "happy", intensity=...)`; `daz_look_at_point(...)` to lens.
5. QA: nose butterfly shadow present; eyes on upper third.
6. `daz_render_shot(..., camera=..., quality="final")`.

### Recipe 3 — Moody low-key
1. `daz_frame_shot(..., "close-up")`; `daz_apply_camera_angle(..., "dutch-angle")` (≤10°).
2. `daz_apply_lighting_preset("split", subject_label=figure)`.
3. `daz_apply_visual_style("noir"|"low-key")` (optional).
4. Pose: asymmetric, `daz_set_body_language(figure, "defeated")`; head tilt via look.
5. QA: one half of face in shadow; strong rim.
6. `daz_render_shot(..., engine="iray", quality="good")`.

## 8. Anti-patterns (do NOT)

- Flat frontal light with everything lit (looks clinical).
- Accidental Dutch/tilted horizon.
- Face pointing off-frame with **no lead room**.
- Symmetric stance (A-pose) for a "posed" hero shot.
- Rendering at the viewport default without explicitly choosing lens/camera/
  lighting. Choose intent, then lenses and light.
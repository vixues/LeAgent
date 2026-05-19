# Pet Preset Assets

The SVG mascots in this directory are original vector drawings created for this repository and dedicated to the public domain using CC0-style terms.

They are safe to bundle, modify, and redistribute as built-in desk pet presets.

## Files

- `bird.svg`
- `rabbit.svg`
- `dog.svg`
- `cat.svg`

Animated SVG variants with embedded CSS motion:

- `bird-motion.svg`
- `rabbit-motion.svg`
- `dog-motion.svg`
- `cat-motion.svg`

Frontend integration metadata:

- `manifest.json` maps each pet id to static asset, animated asset, supported states, motion defaults, recommended nest style, and AI / sprite sheet prompts.

Sprite sheet examples:

- `bird-spritesheet.png`, `rabbit-spritesheet.png`, `dog-spritesheet.png`, `cat-spritesheet.png`
- `bird-spritesheet.gif`, `rabbit-spritesheet.gif`, `dog-spritesheet.gif`, `cat-spritesheet.gif`

Animated GIF previews generated from those sheets:

- `bird-animated.gif`, `rabbit-animated.gif`, `dog-animated.gif`, `cat-animated.gif`

All sprite sheets are 4×4 grids, 96×96 px per cell, row-major frame order, transparent background.

## Frontend Usage

Current simple usage:

```ts
const src = "/pet-presets/bird.svg";
```

For motion-first previews, use the matching `*-motion.svg` file:

```ts
const src = "/pet-presets/bird-motion.svg";
```

For richer preset setup, load `manifest.json` and apply the pet's `motionDefaults` into `PetSettings.behavior`.

Sprite sheet tool defaults for these samples:

```json
{ "cols": 4, "rows": 4, "pad": 0, "fps": 10, "transparent": true }
```

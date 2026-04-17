# Current FE vs Original Diff

FE: `frontend/public/assets/` · Origin: `/tmp/pikachu-original/src/resources/assets/`

## Hash-identical (already ported)

`sha256sum` match:

- `sprite_sheet.png`, `sprite_sheet.json`
- `sounds/bgm.mp3` + all 7× `WAVE14[0-6]_1.wav`

→ Core atlas + audio are **bit-exact** already.

## Missing in FE (present in original)

| File | Size | Needed? |
|------|-----:|---------|
| `controls.png` / `controls_ko.png` | 77K / 64K | Optional — help overlay |
| `screenshot.png` | 176K | No — docs only |
| `IDI_PIKAICON-0.png` | 240 | Favicon |
| `IDI_PIKAICON-1_gap_filled*.png` (3) | 350/499/1194 | PWA icons |

## Extra in FE

- `SPRITE_GUIDE.md` — designer frame mapping notes (keep).

## Structural notes

- Original nests under `images/`; FE flattens to `assets/` root — loader paths differ.
- Original uses `../resources/assets/…` path constants (`assets_path.js`); FE needs its own.

# Sprite Sheet Guide — Pikachu Volleyball

Source: [gorisanson/pikachu-volleyball](https://github.com/gorisanson/pikachu-volleyball)

## Sprite Sheet

- **File**: `sprite_sheet.png` (476x885px)
- **Metadata**: `sprite_sheet.json` (TexturePacker format, PixiJS compatible)
- **Original canvas**: 432x304px (aspect ratio ~1.42:1)

---

## Pikachu Sprites (64x64px each)

7 states, mapped to animation frames:

| State | Frames | Sprite Keys | Description |
|-------|--------|-------------|-------------|
| 0 | 0-4 | `pikachu_0_0` ~ `pikachu_0_4` | **Idle / Walk** — standing, slight bounce cycle |
| 1 | 0-4 | `pikachu_1_0` ~ `pikachu_1_4` | **Jump up** — ascending animation |
| 2 | 0-4 | `pikachu_2_0` ~ `pikachu_2_4` | **Jump down / fall** — descending animation |
| 3 | 0-1 | `pikachu_3_0` ~ `pikachu_3_1` | **Diving** — horizontal dive (scale.x flipped for direction) |
| 4 | 0 | `pikachu_4_0` | **Lying down** — after dive, on ground |
| 5 | 0-4 | `pikachu_5_0` ~ `pikachu_5_4` | **Spike / attack** — overhead hit animation |
| 6 | 0-4 | `pikachu_6_0` ~ `pikachu_6_4` | **Underhand hit** — low hit animation |

### Frame Number Mapping (view.js `getFrameNumberForPlayerAnimatedSprite`)

```
state < 4:  frameIndex = 5 * state + frameNumber
state == 4: frameIndex = 17 + frameNumber
state > 4:  frameIndex = 18 + 5 * (state - 5) + frameNumber
```

Total animated sprite frames: 5+5+5+2+1+5+5 = **28 frames**

### Player Rendering

- Both players use the **same** sprite sheet
- **Player 1** (left side): `scale.x = 1` (faces right), `scale.x = -1` when diving left
- **Player 2** (right side): `scale.x = -1` (faces left), `scale.x = 1` when diving right
- Anchor: center (0.5, 0.5)
- Shadow sprite rendered at `y=273` with same `x` as player

---

## Ball Sprites (40x40px each)

| Key | Description |
|-----|-------------|
| `ball_0` ~ `ball_4` | **Rotation frames** — 5-frame rotation cycle, selected by `ball.rotation` |
| `ball_hyper` | **Power hit trail** — rendered at `ball.previousX/Y` during power hits |
| `ball_trail` | **Power hit trail (far)** — rendered at `ball.previousPreviousX/Y` |
| `ball_punch` | **Punch effect** — expanding circle on ball hit, radius shrinks by 2 each frame |

### Ball Rendering

- Anchor: center (0.5, 0.5)
- Normal: show `ball_0`~`ball_4` based on rotation
- Power hit (`isPowerHit === true`): show ball + hyper at previous pos + trail at prev-prev pos
- Punch effect: visible when `punchEffectRadius > 0`, size = `2 * radius`

---

## Background Objects

| Key | Size | Description |
|-----|------|-------------|
| `sky_blue` | 16x16 | Sky tile — tiled 27x12 to fill sky area (y: 0-192) |
| `mountain` | 432x64 | Mountain range — placed at y=188, full width |
| `ground_red` | 16x16 | Red ground tile — tiled at y=248 |
| `ground_line` | 16x16 | Ground border line — tiled at y=264 (middle tiles) |
| `ground_line_leftmost` | 16x16 | Ground border — left edge at y=264 |
| `ground_line_rightmost` | 16x16 | Ground border — right edge at y=264 |
| `ground_yellow` | 16x16 | Yellow ground tile — tiled at y=280 and y=296 (2 rows) |
| `net_pillar_top` | 8x8 | Net pillar cap — placed at (213, 176) |
| `net_pillar` | 8x8 | Net pillar body — 12 tiles stacked at x=213, y=184~272 |
| `shadow` | 32x8 | Character/ball shadow — placed at y=273, x matches entity |
| `cloud` | 48x24 | Cloud — 10 clouds, animated movement (drift right, pulsing size) |
| `wave` | 16x32 | Wave tile — 27 tiles at bottom, animated y-position oscillation |
| `black` | 8x8 | Solid black — scaled to 432x304 for fade in/out transitions |

### Background Layer Order (back to front)

1. Sky tiles (blue fill)
2. Mountain panorama
3. Ground (red, line, yellow)
4. Net pillar
5. Clouds (animated, drift right at 1-2px/frame, size pulses ±5px)
6. Waves (animated, y oscillates between 314-32 and 314)
7. Shadows
8. Players
9. Ball trail → ball hyper → ball → punch effect
10. Score boards
11. Messages

---

## UI / Score Sprites

| Key | Size | Description |
|-----|------|-------------|
| `number_0` ~ `number_9` | 32x32 | Score digits (retro pixel font) |

### Score Board Layout

- Player 1 score: x=14, y=10 (units at +32px, tens at +0px)
- Player 2 score: x=368, y=10 (432 - 32 - 32 - 14)
- Tens digit hidden when score < 10

---

## Message Sprites

| Key | Size | Description |
|-----|------|-------------|
| `messages/common/ready` | 80x24 | "Ready?" text — shown at (176, 38), toggles on/off |
| `messages/common/game_end` | 96x24 | "Game Set!" text — zoom-in animation from large |
| `messages/common/sachisoft` | 360x20 | "(C) 1997 SACHISOFT / SAWAYAKAN" credit |
| `messages/ja/game_start` | 96x24 | "試合開始!" text — zoom-in animation |
| `messages/ja/fight` | 160x160 | "対戦!" — pulsing size animation on menu |
| `messages/ja/pikachu_volleyball` | 276x79 | Title text — slide-in animation |
| `messages/ja/pokemon` | 200x32 | "ポケモンスター" subtitle |
| `messages/ja/mark` | 88x110 | Sachisoft man-with-briefcase logo |
| `messages/ja/with_computer` | 120x20 | "1人でぴかちゅう~" menu option |
| `messages/ja/with_friend` | 120x20 | "2人でぴかちゅう~" menu option |
| `messages/ko/*` | — | Korean translations of above messages |
| `sitting_pikachu` | 104x104 | Sitting pikachu — tiled as menu background |

---

## Clouds & Wave Animation (cloud_and_wave.js)

### Clouds

- **Count**: 10 clouds rendered simultaneously
- **Movement**: drift right at 1-2px/frame (random velocity)
- **Size pulse**: width oscillates 48±10px, height 24±10px (11-step cycle)
- **Respawn**: when x > 432, reset to x=-68 with random y (0-152)

### Wave

- **Tiles**: 27 wave sprites (16px wide each, covering 432px width)
- **Oscillation**: vertical coord moves +2 up, then -1 down, with random pause
- **Y position**: base y=314, displaced by wave coord + random jitter (0-2px)
- **Creates**: gentle bobbing ocean effect at bottom of screen

---

## Sound Assets (frontend/public/assets/sounds/)

| File | Key in Original | Description |
|------|-----------------|-------------|
| `bgm.mp3` | BGM | Background music |
| `WAVE140_1.wav` | PIPIKACHU | "Pipikachu!" voice |
| `WAVE141_1.wav` | PIKA | "Pika!" voice |
| `WAVE142_1.wav` | CHU | "Chu!" voice |
| `WAVE143_1.wav` | PI | "Pi!" voice |
| `WAVE144_1.wav` | PIKACHU | "Pikachu!" voice |
| `WAVE145_1.wav` | POWERHIT | Power hit sound effect |
| `WAVE146_1.wav` | BALLTOUCHESGROUND | Ball ground bounce sound |

---

## Integration Notes for FE (GameCanvas.tsx)

### Loading with PixiJS

```typescript
import { Assets } from 'pixi.js';

// Load sprite sheet (PixiJS auto-parses TexturePacker JSON)
const spriteSheet = await Assets.load('/assets/sprite_sheet.json');
// Access individual textures:
const pikachuIdle = spriteSheet.textures['pikachu/pikachu_0_0.png'];
const ball = spriteSheet.textures['ball/ball_0.png'];
const sky = spriteSheet.textures['objects/sky_blue.png'];
```

### Coordinate Mapping

Original game: 432x304px. Our canvas may differ in size.
Scale factor: `canvasWidth / 432` and `canvasHeight / 304`

All positions from the backend game engine use the original coordinate space.
FE should apply the scale factor when rendering sprites.

### Player State → Sprite Mapping

Backend sends `player.state` (0-6) and `player.frameNumber`.
Use the frame mapping formula above to index into the animated sprite.

# Attribution and Upstream Provenance

This document tracks the provenance of code, assets, and design
elements that were adapted from third parties. It is the authoritative
source for which parts of this repository are **original work by this
project** and which parts **carry upstream copyright claims that this
project does not grant**.

Read this before redistributing, forking, or publishing.

---

## Upstream Sources Referenced

### 1. `gorisanson/pikachu-volleyball`

- **Repository:** https://github.com/gorisanson/pikachu-volleyball
- **Author:** Kyutae Lee (gorisanson)
- **Stated license:** `"license": "UNLICENSED"` (per the repository's
  `package.json`).
- **Upstream LICENSE file:** **none present** at the repository root as
  of the clone used by this port (2026-04-13).
- **Upstream README characterization:** Describes the code as obtained
  "by reverse engineering the core parts of the machine code &mdash;
  including the physics engine and the AI &mdash; of the original
  game". See `/tmp/pikachu-original/README.md` in the reference clone.
- **Nature of upstream:** A JavaScript re-implementation of the
  gameplay logic of the 1997 Windows game "対戦ぴかちゅ～ ﾋﾞｰﾁﾊﾞﾚｰ編"
  ("Pikachu Volleyball"), produced through reverse engineering.

### 2. 対戦ぴかちゅ～ ﾋﾞｰﾁﾊﾞﾚｰ編 (1997) — the game that was reverse-engineered

- **Copyright holders (per upstream README):** © SACHI SOFT /
  SAWAYAKAN Programmers, © Satoshi Takenouchi.
- **Status:** commercial game released in 1997. No public-domain or
  permissive-license declaration is known to exist.

---

## What This Project Borrowed

### Physics engine (Python port)

- `backend/game/engine.py` is a Python port of the logic contained in
  `src/resources/js/physics.js` from the `gorisanson/pikachu-volleyball`
  repository. Function-level comments in the file reference the
  original JavaScript function names.
- Function-by-function mapping:
  - `_update_ball_and_world` ←
    `processCollisionBetweenBallAndWorldAndSetBallPosition`
  - `_update_player` ← `processPlayerMovementAndSetPlayerPosition`
  - `_check_ball_player_collision` ←
    `isCollisionBetweenBallAndPlayerHappened` +
    `processCollisionBetweenBallAndPlayer`
  - `_calculate_expected_landing_point_x` ←
    `calculateExpectedLandingPointXFor`
  - `_process_game_end_frame_for` ← `processGameEndFrameFor`
  - `_rand` ← `rand()` in `src/resources/js/rand.js`
- The port aims to be **frame-accurate** with respect to the
  upstream's ball trajectories, player movement, and collision
  responses. It therefore carries the same provenance chain as the
  upstream — ultimately derived from reverse engineering of the 1997
  game's machine code.

### State-machine fragments (engine.py + callbacks.py)

- The 211-frame `gameEnd` transition constant and the round /
  winner-pose flow are ported from fragments of
  `src/resources/js/pikavolley.js` (`frameTotal.gameEnd`,
  `round()` gating on `gameEnded`, `player.gameEnded` /
  `player.isWinner`).

### Assets (byte-identical copies)

The following files are **not committed to this repository**. They are
downloaded at build time by `frontend/scripts/fetch-assets.mjs` (run by
`npm run dev` / `npm run build`) from a pinned upstream commit and checked
against SHA-256 hashes. They are **byte-identical copies** of files from
`gorisanson/pikachu-volleyball`'s `src/resources/assets/`:

| File | Upstream path |
|---|---|
| `sprite_sheet.png` | `images/sprite_sheet.png` |
| `sprite_sheet.json` | `images/sprite_sheet.json` |
| `sounds/WAVE140_1.wav` … `WAVE146_1.wav` | `sounds/WAVE*.wav` |
| `sounds/bgm.mp3` | `sounds/bgm.mp3` |

These assets have been verified md5-identical to the upstream tree at
clone time. Copyright in the underlying sprite art, music, and sound
effects originates with the 1997 game's rights holders (see section 2
above), not with the upstream repository author and not with this
project. This project does **not** grant any license covering these
files; their inclusion here follows the same provenance chain as the
upstream.

---

## What This Project Does NOT Claim

- This project does not assert an MIT license (or any other
  permissive license) over the ported physics code or the asset
  files. A prior commit message (`1fb72169 port(physics): faithful
  engine from gorisanson physics.js`) contained the incorrect phrase
  "MIT-licensed by gorisanson"; that claim was based on a mistaken
  upstream-license assumption and is **formally retracted** here.
  See `docs/NOTICE-ATTRIBUTION-CORRECTION.md`.
- This project does not grant the rights that the upstream and the
  original 1997 game rights holders have not themselves granted.
- The `is_power_hit` / `punch_effect_*` fields on the Python ball
  state were derived from the upstream's graphic-effect markers for
  compatibility, not from independent design work.

---

## Purpose and Use

This repository exists as an **educational / research testbed for
reinforcement learning**. Specifically:

- A reproducible Gymnasium-compatible environment for training PPO
  agents on a non-trivial physics task.
- A real-time dashboard for monitoring RL training, intended as a
  pedagogical exhibit.
- A backend + frontend scaffold demonstrating WebSocket streaming of
  RL training metrics.

Redistribution, public hosting, or any commercial use should be
reviewed against the upstream's `UNLICENSED` status and the 1997
game's copyright before proceeding. Users and forkers take that
review on themselves — this file is an accurate disclosure, not a
grant.

---

## Original Work in This Repository

Parts of the repository that are **original to this project** (i.e.
not ported from `gorisanson/pikachu-volleyball`) include:

- The RL environment wrapper (`backend/rl/env.py`) including
  reward shaping, observation construction, and episode termination.
- The L1–L5 rule-based bot ladder (`backend/game/bot.py`), a
  curriculum-learning opponent designed around noise/confidence knobs
  rather than the upstream's single built-in AI.
- The Stable-Baselines3 PPO training harness and callbacks pipeline
  (`backend/rl/trainer.py`, `backend/rl/callbacks.py`).
- The FastAPI + WebSocket backend serving live training metrics and
  replays (`backend/app/`).
- The React + PixiJS dashboard frontend (`frontend/src/`), except
  where it consumes the upstream sprite sheet / sound files (see
  "Assets" above).
- All backend MongoDB schemas, services, and persistence code.
- All tests under `backend/tests/` and `frontend/src/components/`.
- All documentation under `docs/`.
- The rally-timeout safety valve (`RALLY_MAX_FRAMES`) and the
  `is_collision_with_ball_happened` gate integration pattern used by
  the Python port — these are extensions, not in the upstream.

Original-work sections of the repository carry the project's default
copyright disposition for sh.yoon.devops's contributions; see the
repository root for any project-level LICENSE disposition when it
lands.

---

## Change Log

| Date | Note |
|---|---|
| 2026-04-13 | Initial attribution document. Corrects the MIT claim in commit `1fb72169`. Documents upstream `UNLICENSED` status, 1997-game copyright chain, and byte-identical asset provenance. |

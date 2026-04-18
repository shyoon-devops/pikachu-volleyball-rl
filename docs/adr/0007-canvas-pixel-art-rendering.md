# ADR-0007: Canvas pixel-art rendering — NEAREST + roundPixels

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archive**: `docs/reports/notices/NOTICE-CANVAS-SKY-STRIPES.md`
- **Commit**: `ff24cc9a`

## Context

The dashboard `GameCanvas` showed periodic vertical RGB stripes in the sky region. Root cause was a stack of three interacting defaults: (1) PixiJS v8 ships `scaleMode='linear'`, which bilinear-samples pixel-art and blurs texel edges; (2) `devicePixelRatio ≠ 1` with `autoDensity: true` made the internal backbuffer render at fractional scales (e.g. 432 × 1.25 = 540 px), producing sub-texel sampling; (3) the atlas leaves 2 px padding around each sprite (transparent alpha), and bilinear sampling pulled those transparent edges into tile seams — 27 sky tiles × 16 px gave 27 periodic vertical seams, amplified by LCD sub-pixel rendering into R/G/B stripes.

## Decision

Canvas-wide pixel-art settings (FE-only, no atlas regeneration):

| Setting | Before | After | Why |
|---------|--------|-------|-----|
| `antialias` | `true` | `false` | Pixel art doesn't need canvas AA; it *causes* 1 px fringing |
| `roundPixels` | unset | `true` | Snap fractional sprite coordinates to integer pixels |
| Shared texture `scaleMode` | `linear` (default) | `nearest` | No interpolation at sampling time |

Apply `scaleMode = 'nearest'` to the single shared `TextureSource` right after `Assets.load()` — one statement covers all 77 frames (pikachu, ball, numbers, objects). The existing 2 px atlas padding is correct; NEAREST alone removes the seam class.

## Consequences

- All new sprites added to the atlas inherit NEAREST via the shared source. Atlas regeneration is **not** required for this fix.
- `roundPixels: true` commits the project to integer-px coordinates for sprite positioning — any future sub-pixel animation (e.g. smooth interpolated tweens) must bypass the global by per-sprite opt-out.
- If a future feature genuinely needs smoothing for a subset of textures (photographic UI, AI-generated art), it must use a separate texture source and not share state with the game atlas.

# ADR-0002: Frontend keyboard input contract (original-faithful)

- **Status**: Accepted
- **Date**: 2026-04-12
- **Archive**: `docs/reports/notices/NOTICE-FE-KEYBINDINGS.md`
- **Related**: `backend/game/engine.py` (power-hit logic already ported)

## Context

User asked whether the original game had an explicit "강타 (power hit)" key. Investigation: Enter (P2) and `Z` (P1) are the power-hit bindings — *not* a new attack tier, just the existing `powerHit` input slot. Backend already interprets `PlayerInput.power_hit` correctly; the gap was on the FE, which was spectator-only and ingested zero keyboard input. A contract had to be fixed before FE could start sending human-play inputs.

## Decision

Adopt the original game's binding map verbatim for human-play mode:

| Input | Player 1 | Player 2 |
|-------|----------|----------|
| left | `KeyD` | `ArrowLeft` |
| right | `KeyG` | `ArrowRight` |
| up (jump) | `KeyR` | `ArrowUp` |
| down (crouch) | `KeyV` | `ArrowDown` |
| power hit | `KeyZ` | `Enter` |
| down-right alt (P1 only) | `KeyF` | — |

`powerHit` is **edge-triggered**: emit `1` only on the `up → down` transition frame; `0` while the key is held. Other axes are level-triggered.

## Consequences

- FE must implement a per-frame input assembler that tracks key-state transitions (not just `keydown` listeners) so `powerHit` isn't re-emitted by auto-repeat.
- Spectator-only mode remains unaffected — contract only activates when a seat is claimed by a human.
- If future controller support is added (gamepad), it maps onto the same `PlayerInput` shape, not a new protocol.

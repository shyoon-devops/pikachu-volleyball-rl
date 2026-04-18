# Attribution correction — upstream is UNLICENSED, not MIT

**Date:** 2026-04-13
**Author:** AI Engineer
**Priority:** P1 — legal accuracy of public-facing claims
**Scope:** `backend/game/engine.py` commit message wording + ATTRIBUTION.md

---

## What was claimed

The commit message for

```
1fb72169 port(physics): faithful engine from gorisanson physics.js
```

contains the phrase

> "1:1 port of the original pikachu-volleyball physics engine
> (physics.js, MIT by gorisanson)"

and the module docstring at `backend/game/engine.py:3-4` says:

> "Physics ported frame-accurately from the original game source
> (gorisanson/pikachu-volleyball: src/resources/js/physics.js, MIT-licensed)."

Both statements are **incorrect**.

## What is actually the case

Verified against a fresh clone of
`https://github.com/gorisanson/pikachu-volleyball.git` on 2026-04-13:

1. **No `LICENSE` file exists** at the repository root.
2. **`package.json`** declares `"license": "UNLICENSED"`.
3. Neither `README.md` nor `README.ko.md` mentions MIT or any
   permissive license.
4. The upstream `README.md` characterizes its own code as obtained
   "by reverse engineering the core parts of the machine code"
   of the 1997 commercial game "対戦ぴかちゅ～ ﾋﾞｰﾁﾊﾞﾚｰ編"
   ("Pikachu Volleyball"), copyright
   "(C) SACHI SOFT / SAWAYAKAN Programmers" and
   "(C) Satoshi Takenouchi".

The PM instruction that kicked off the port had stated the upstream
was MIT; that assumption is superseded by the above verification.

## Corrections issued

- **`ATTRIBUTION.md`** (new, at repo root) — documents the actual
  upstream status (UNLICENSED, reverse-engineered), the 1997 game's
  original rights holders, which parts of the repository were
  borrowed from upstream (physics, 211f gameEnd fragments,
  byte-identical assets), and which parts are original to this
  project. Explicitly retracts any MIT claim over the ported parts.

- **`backend/game/engine.py` module docstring** — the "MIT-licensed"
  phrase will be removed / updated in the attribution commit.

- **`docs/NOTICE-ATTRIBUTION-CORRECTION.md`** (this file) — in-tree
  record of the correction, so the retraction is auditable even if
  the engine.py docstring is rewritten later.

## What is NOT being done

- **Git history is not being rewritten.** The commit message for
  `1fb72169` still contains the incorrect phrase. Rewriting history
  on `yoon/ai-engineer` (which has already been pushed) would
  pollute `dev` after merge. The correction stands as an additive
  record in `ATTRIBUTION.md` + this notice, which is the standard
  way to handle a factual error in a prior commit.

- **No license file is being added that covers the ported portions.**
  We cannot grant rights over code we do not own. `ATTRIBUTION.md`
  explicitly disclaims an MIT grant over those portions.

## Implications for downstream consumers

- **Forks / public hosting / commercial use** of this repository
  must account for the upstream's `UNLICENSED` status and the 1997
  game's copyright chain. `ATTRIBUTION.md` is the disclosure, not a
  grant.

- **Internal RL / educational use** (the project's current purpose)
  is within the spirit of the upstream's educational posture, but
  this is not legal advice. Escalate any distribution question to
  PM before acting.

## Follow-ups on PM

1. If broader distribution is planned, consider reaching out to
   gorisanson (Kyutae Lee) to request an explicit permissive license
   over the upstream before further public release.
2. Assets (sprite sheet, sounds) carry the 1997 game's copyright.
   Long-term, a self-produced asset pack would eliminate that
   exposure.
3. The physics engine itself reflects reverse-engineered
   1997 game logic; a clean-room re-implementation from a public
   spec would eliminate the upstream-derivation exposure but is a
   substantial effort.

---
**end of notice.**

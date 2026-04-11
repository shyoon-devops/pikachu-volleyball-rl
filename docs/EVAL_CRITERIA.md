# Evaluation Criteria — Pikachu Volleyball RL

## Overview

All models must pass every level threshold to be considered production-ready.
A single level failure = overall **FAIL**.

## Per-Level Pass/Fail Thresholds

| Bot Level | Min Win Rate | Min Avg Score | Min Avg Rally | Notes |
|:---------:|:------------:|:-------------:|:-------------:|-------|
| **L1** | 90% | 13.0 | 100 | Easiest bot. Anything below 90% is unacceptable. |
| **L2** | 75% | 11.0 | 80 | Must demonstrate learned offense. |
| **L3** | 50% | 8.0 | 70 | Competitive play expected. |
| **L4** | 25% | 5.0 | 60 | Stretch goal for current training. |
| **L5** | 10% | 3.0 | 50 | Perfect bot — partial wins acceptable. |

## Metric Definitions

| Metric | Definition |
|--------|-----------|
| **Win Rate** | Games where agent reaches MAX_SCORE (15) first / total games. |
| **Avg Score** | Mean agent score across all games (max 15). |
| **Avg Opponent Score** | Mean bot score. Lower = better defensive play. |
| **Avg Rally Length** | Mean net-crossing count per game. Higher = sustained play, not just serving errors. |
| **Avg Episode Length** | Mean frame count. Context metric — too short means blowout loss, too long means stalemate. |

## Severity Levels

| Verdict | Condition | Action |
|---------|-----------|--------|
| **PASS** | All levels meet thresholds | Clear for deployment. |
| **CONDITIONAL** | L1-L3 pass, L4-L5 fail | Acceptable for staging. Flag for continued training. |
| **FAIL** | Any of L1-L3 fails | Block deployment. Root-cause required. |
| **CRITICAL** | L1 win rate < 50% | Immediate escalation. Training pipeline or reward shaping is broken. |

## Regression Detection

A checkpoint is flagged as **REGRESSION** if any metric drops more than:
- Win rate: -5% vs previous best
- Avg score: -1.0 vs previous best
- Avg rally: -15 vs previous best

## Evaluation Protocol

1. **Sample size**: Minimum 20 games per level. 50 games for release candidates.
2. **Deterministic**: `model.predict(obs, deterministic=True)` — no action sampling noise.
3. **Max steps**: 10,000 per episode (prevents infinite games).
4. **Environments**: Must pass on dev, qa, AND prod independently.
5. **Checkpoints**: Evaluate at minimum every 10K training steps.

## Current Status (2026-04-12)

### Latest Full Evaluation (prod, 17b5a872, n=20)

| Model | Steps | L1 | L2 | L3 | L4 | L5 | Verdict |
|-------|------:|:--:|:--:|:--:|:--:|:--:|---------|
| 17b5a872.../140000 | 140K | 0% | 0% | 0% | 0% | 0% | **CRITICAL** |
| 17b5a872.../10000 | 10K | 0% | — | — | — | — | **CRITICAL** |

### Checkpoint Trend — Old Model (prod, 17b5a872, L1 only, n=10)

| Steps | Win Rate | Avg Score | Avg Opp | Avg Rally | Avg Ep Len | Verdict |
|------:|:--------:|:---------:|:-------:|:---------:|:----------:|---------|
| 10K | 0% | 6.4 | 12.6 | 124.2 | 6,017 | **CRITICAL** |
| 20K | 0% | 8.4 | 15.0 | 130.6 | 3,735 | **CRITICAL** |
| 30K | 20% | 11.4 | 14.1 | 148.6 | 4,091 | **CRITICAL** |
| 40K | 10% | 10.2 | 13.4 | 138.3 | 5,019 | **CRITICAL** |
| 50K | 0% | 8.9 | 14.4 | 125.2 | 4,826 | **CRITICAL** |
| 60K | 10% | 8.2 | 11.4 | 101.1 | 5,389 | **CRITICAL** |
| 70K | 0% | 8.3 | 15.0 | 132.6 | 3,543 | **CRITICAL** |
| 80K | 0% | 7.4 | 13.4 | 120.4 | 4,710 | **CRITICAL** |
| 90K | 10% | 10.2 | 13.7 | 180.1 | 5,665 | **CRITICAL** |
| 100K | 10% | 8.4 | 11.9 | 119.9 | 5,203 | **CRITICAL** |
| 110K | 0% | 8.2 | 14.4 | 156.8 | 4,989 | **CRITICAL** |
| 120K | 0% | 5.9 | 6.9 | 82.4 | 10,000 | **CRITICAL** |
| 130K | 0% | 3.2 | 4.4 | 53.8 | 10,000 | **CRITICAL** |
| 140K | 10% | 9.3 | 13.2 | 156.3 | 5,167 | **CRITICAL** |

> **Analysis (Old Model, obs=12, action=6)**:
> - Zero learning trend: win rate fluctuates 0-20% across 140K steps
> - Score plateau around 8-10 (threshold: 13.0), never approaching consistent wins
> - 120K-130K show **regression**: games hit max steps (10,000), avg score drops to 3-6
> - Model learns to keep ball alive (high rally length) but cannot score consistently
> - **Root cause**: insufficient observation space (12 features) and action space (6 actions)

### Checkpoint Trend — Old Model (dev, 58f1548c, L1 only, n=10)

| Steps | Win Rate | Avg Score | Avg Opp | Avg Rally | Avg Ep Len | Verdict |
|------:|:--------:|:---------:|:-------:|:---------:|:----------:|---------|
| 10K | 0% | 6.2 | 13.6 | 77.8 | 7,824 | **CRITICAL** |
| 20K | 0% | 7.9 | 14.5 | 144.2 | 4,650 | **CRITICAL** |
| 30K | 0% | 9.8 | 15.0 | 156.0 | 4,254 | **CRITICAL** |
| 40K | 0% | 7.7 | 15.0 | 159.2 | 4,188 | **CRITICAL** |
| 50K | 0% | 8.7 | 13.0 | 169.8 | 6,241 | **CRITICAL** |

> **Analysis**: Zero wins in 50 games. Score slowly increasing but opponent consistently winning.
> Rally length trend up (78→170) — model keeps ball alive longer but cannot close games.

### Pending: New Model (reward shaping v2, obs=19, action=12)

AI Engineer completed reward shaping fix (commit 5a5def9, 2026-04-12).
Trainer started new training. Awaiting first checkpoint for evaluation.

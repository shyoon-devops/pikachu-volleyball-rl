# Self-Play League — UX Spec (v2.x Sprint 1)

Companion to `docs/adr/0014-self-play-league.md` (AI). Code-free UX only. Reuses existing design tokens (`tokens.css`) — **no new palette, no new typography**.

Contracts taken from ADR-0014:
- Training flag `training_mode = "bot_ladder" | "self_play"`; sampling `"uniform" | "elo_proximity" | "pfsp"`; pool cap `LEAGUE_POOL_SIZE = 32`; rule anchors L1/L3/L5 = 600/900/1200; champion never evicts.
- Data: WS `training:league_update` (`{top_n, pool_size, champion_id, generation}`, every 64 matches) · REST `GET /api/league/standings?limit=10` + `GET /api/league/checkpoint/{id}`.

## 1. HyperparamForm — Opponent section

New collapsible group **between** Basic and Advanced, expanded by default:

- Label `상대 (Opponent)`, 13 px semibold.
- Segmented control (2 options), 36 px tall, `--color-bg-input` track, `--color-accent` indicator: `Rule-based (L1–L5)` · `Self-play league`.
- If `Rule-based`: existing `bot_level` slider (L1–L5) is active; self-play options are hidden.
- If `Self-play league`:
  - `bot_level` slider dimmed (`--color-text-muted`) with hint `자기 복제 풀이 비어있을 때만 사용`.
  - `Sampling` radio row: `PFSP (default)` · `Elo proximity` · `Uniform`. Each has a 1-line hint (`약한 상대에 가중`, `비슷한 실력 매칭`, `균등 샘플링`).
  - `Pool size` read-only chip: `최대 32` (shows live pool fill, see §6).
  - `K-factor` readouts (read-only): `K=16 (<30 games) / K=8`. Tooltip explains annealing.
- Live hint below group: `리그가 비어있으면 L{n} bot 으로 자동 폴백`. Submit never blocked by empty league.

## 2. League view

Embedded as a new sub-tab `League` on `/runs/{title}` (per `DESIGN-RUNS-MERGED.md §4b`), *not* a top-level route — the league belongs to a specific training run (one pool per `experiment_id`, ADR-0014 §8). Sub-tab order becomes `Overview · Games · Evaluation · League`.

Four stacked regions:

- **Pool status bar** (sticky, 56 px) — `{pool_size} / 32` fill bar (`--color-accent` segment), `Champion: ckpt_{exp8}_{step}` chip, `Generation {n}` label, `Mode: PFSP` chip. Empty-pool state: `풀이 비어있습니다 · L{n} 폴백 중`.
- **Top-10 leaderboard** (primary) — columns `Rank · Checkpoint · Elo · Games · Win % · Admitted at (KST)`. Row click → `/runs/{title}/league/{checkpoint_id}` detail route. Sortable headers; Elo desc default.
- **Recent league matches** — last 30 matches: `opponent_ckpt · winner · duration · Δ Elo`. Compact 36 px rows, mono digits.
- **Elo progression chart** — line of max-Elo and median-Elo over timesteps; champion lineage traced with `--color-accent` marker dots on takeovers. Swim-lanes = generation bands (see §5).

## 3. Dashboard widgets

- **Recent Games table**: new `Opponent` column between existing `Env` and `Score`. Cell: either `Rule L3` chip (`--color-bg-elevated`) or `policy_{exp8}_{step}` mono chip (`--color-accent-dim` bg). Truncates + tooltip.
- **Current run card**: append `Elo 1382 · #3 of {pool_size}` line (mono 13 px); rank badge coloured per §5.
- Top-nav: when any run is in `self_play` mode, the `Training Runs` item shows a small `League` badge using `--color-warning` (pulse 1.2 s) to reinforce the active mode.

## 4. Evaluation sub-tab — two modes

On `/runs/{title}?tab=eval`, split the eval runner panel into two stacked cards (existing bottom-sheet pattern on mobile):

- **Card A — vs Rule ladder** (unchanged, preserves v1 contract): bot_level select + `평가 실행 (vs L1–L5)`.
- **Card B — vs Top-N league** (new): `N` select `5 / 10 / 20`; Elo threshold filter (optional slider `≥ 1000`); button `평가 실행 (vs Top-{N})`. Result table: `opponent_ckpt · games · win % · Δ Elo · mean duration` with per-row sparkline.

The `평가 실행` button still lives **only** on this tab (per `DESIGN-RUNS-MERGED.md §7`); split cards both count as same-tab surfaces.

## 5. Visual system (tokens only, no new)

- **Elo tier badge**: top 10% → `--color-accent` bg + `--color-text-inverse` fg (Pikachu-yellow "gold" slot); 11–30% → `--color-text-secondary` border + `--color-bg-elevated` bg ("silver"); below → default chip styling. Tier is computed per `pool_size`, not fixed cutoffs, so badges reshuffle as the pool grows.
- **Champion highlight**: leaderboard rank-1 row gets a 2 px `--color-accent` left bar + `--color-accent-dim` row fill + a `👑` unicode glyph (no new font — unicode). Row stays highlighted even when sort changes.
- **Generation swim-lanes**: Elo chart x-axis split into generation bands (step range `[k*save_interval*10, …]`) using alternating `--color-bg-elevated` + `--color-bg-secondary` fills; band labels `Gen {n}` at the top edge, 11 px mono muted. Lane width proportional to step range, not games.

## 6. State indicators

- **Global `Self-play mode` badge** on top nav when the currently viewed run has `training_mode='self_play'`: 24 px chip, `--color-accent-dim` bg, `--color-accent` fg, left-of-status. Hidden when no run is selected or mode is `bot_ladder`.
- **Pool fill progress**: sticky bar (see §2 pool status bar). Live-updated from `training:league_update` WS event. At 32/32 show `풀 포화 · 약체 교체 진행` hint with a tiny info `ⓘ`.
- **Sampling-strategy indicator**: top of the League tab shows `현재 샘플링: PFSP` with hover tooltip explaining the formula `(1 − winrate)^2`.

## 7. Responsive + dark-theme

- ≥1024 px: full 4-region league layout, chart + leaderboard side-by-side (60/40 split).
- 768–1023 px: 4 regions stack vertically; chart height clamps to 240 px; leaderboard keeps all columns.
- <768 px: leaderboard drops `Admitted at` (revealed on row expand); recent matches compress to `opp · win · ΔElo`; Elo chart drops generation labels (tap reveals); pool status bar shrinks to 40 px with icon-only labels. Dashboard `Opponent` column becomes a sub-line under `Score`.
- Dark theme is the project baseline; all states use existing token surfaces (`--color-bg-card`, `--color-bg-elevated`) so contrast budget (≥7:1 for numeric text) is preserved without new colours.

## 8. Edge cases

- **Empty pool at training start**: pool status bar shows `0 / 32 · L{n} 폴백 중`, leaderboard renders empty-state card `아직 풀에 등록된 체크포인트가 없습니다. 첫 저장 이후 자동 등록됩니다.` Chart area shows skeleton with note `Elo 기록 수집 중…`.
- **Checkpoint load failure** (league row click → 404 / load error): toast `체크포인트를 불러오지 못했습니다 ({ckpt_id})` with `다시 시도` action; row gets a red dot indicator; leaderboard otherwise remains interactive.
- **Zero metrics** for a cell: render `—` (em dash, `--color-text-muted`) rather than `0` for `Games`, `Win %`, `Elo Δ` placeholders — avoids the "bot looks 0% strong" misread.
- **Pool saturation + no admission** (every new checkpoint fails the +25 Elo gate): pool bar shows `32 / 32 · 최근 10개 거절` with info pointer to docs/adr/0014 §1.
- **Mode mismatch** (`training_mode='self_play'` but pool=0): League tab renders the empty-state card plus a prominent notice `현재 rule-based L{n} 로 학습 중입니다 — 풀이 채워지면 자동 전환됩니다.`
- **Cross-run navigation**: run-picker dropdown (inherited from `DESIGN-RUNS-MERGED.md §4a`) switches runs; League tab preserves the URL query `?lg.sort=elo.desc&lg.limit=10` so the same view returns after navigation.

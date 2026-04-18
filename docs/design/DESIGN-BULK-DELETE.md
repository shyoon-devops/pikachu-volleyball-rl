# Bulk Delete — Models / Checkpoints Spec

Replace single-radio delete (accident-prone) with explicit multi-select flow. Applies to checkpoint table in `DESIGN-EVAL-DRILLDOWN.md §2b` and any future models list.

## 1. Mode — recommendation

Options: **A. Delete-mode toggle** (default read-only; toggle reveals checkboxes + delete bar) · B. always-on checkboxes + hover trash · C. keep radio + always-on extra checkbox column.

**Recommend A.** Eval is read-first — users browse checkpoints far more than delete. Always-on checkboxes clutter the dense numeric table and invite stray clicks; C doubles the selection semantics (confusing); B normalises single-click delete (the trap we're removing). A makes destructive intent explicit without hiding the feature behind menus.

## 2. Layout

Toolbar row above checkpoint table:

- Left: `선택 삭제` ghost button (danger-on-hover) → enters Delete Mode.
- Center (mode on): `선택됨: 3 / 12` + `모두 선택` / `모두 해제` text links.
- Right (mode on): primary danger `선택한 3개 삭제` + ghost `취소`.

Mode off → checkbox column not rendered (table looks identical to read state).
Mode on → 32 px leading checkbox column (header is tri-state); single-select eval radio column stays visible but dimmed + disabled. Row hover → `--color-danger-dim`.

## 3. Checkbox visual

18×18 px, 4 px radius, 1 px `--color-border-strong`, `--color-bg-input`. Checked → `--color-accent` fill + inverse check. Focus ring 2 px `--color-accent` offset 2 px. Header tri-state: unchecked / indeterminate (dash) / checked.

## 4. Safeguards

- **Running training**: if current run `status = Running`, `선택 삭제` button disabled with tooltip `진행 중인 학습의 체크포인트는 삭제할 수 없습니다. 학습 종료 후 다시 시도하세요.`
- **Per-row guard**: rows belonging to any in-flight training show disabled checkbox + same tooltip.
- **Latest-checkpoint warning**: if selection includes the highest-step file, modal body adds `최신 체크포인트가 포함되어 있습니다. 이후 학습 재개 시 필요할 수 있습니다.`

## 5. Confirmation modal

- Overlay `rgba(15,17,23,0.7)` + backdrop-blur 6 px.
- Panel 440 px (desktop) / 90 vw (mobile), `--color-bg-card`, 2 px `--color-danger-border`, radius 12 px, 24 px padding.
- Heading: `3개 파일을 영구 삭제합니다` (18 px semibold).
- Body: `이 작업은 되돌릴 수 없습니다.` (13 px muted) + scrollable file list (max-h 160 px) lines `step 200,000 · 4.2 MB · run-baseline__a3f9bc21__200000.zip`.
- Actions (right-aligned): `취소` ghost (initial focus) · `삭제` danger filled.
- **Double-commit for ≥10 files**: first click morphs button to `한 번 더 눌러 확정 (3s)` countdown; second click within 3 s commits. ≤9 files → single click (modal itself is the gate).
- Commit → `DELETE /api/models` body `{experiment_id, steps: number[]}`; toast `3개 삭제 완료` with `실행 취소` link if BE supports soft-delete window.

## 6. Post-delete

Toast top-right, 5 s auto-dismiss. Rows optimistically removed; rollback + error toast on API fail. Mode auto-exits; selection clears.

## 7. Keyboard / a11y

- `D` (table focused) → enter Delete Mode; `Esc` → exit.
- `Space` toggles focused row checkbox; `Shift + click` range-selects.
- Modal: focus trap; `Esc` cancels; `Enter` commits only after 300 ms dwell (stray-key guard).
- Checkboxes labelled via `aria-labelledby` pointing at the row's Step cell.

## 8. Responsive

- ≥1024 px: toolbar single row; modal 440 px.
- 768–1023 px: toolbar wraps 2 rows (left+center / right actions); modal 90 vw capped 520 px.
- <768 px: Delete Mode swaps cards — each checkpoint card gets 24×24 leading checkbox; toolbar sticky top (56 px); confirmation becomes bottom sheet; file list shrinks to `step + size`. Double-commit rule preserved for ≥10 files.

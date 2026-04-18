import { useCallback, useEffect, useRef, useState } from 'react'
import type { ModelInfo } from '../../lib/types'
import './DeleteCheckpointsModal.css'

/**
 * Confirmation modal for bulk checkpoint delete (FC-R7D, spec
 * `DESIGN-BULK-DELETE.md §5`).
 *
 * Focus trap: we move focus to the Cancel button on open and restore
 * focus on close, per the spec's "initial focus on Cancel" rule. `Esc`
 * closes without committing. Commit is gated behind an explicit click
 * on `Delete` — no `Enter` shortcut (stray-key guard).
 *
 * Latest-checkpoint warning surfaces in the body when the selection
 * includes the highest-step file the caller passed in via
 * `selection.isIncludingLatest`; that boundary is computed by the
 * parent so the modal stays display-only.
 *
 * Double-commit for ≥10 files is intentionally deferred — fair-use
 * count for this sprint is single training run, and the outer modal
 * itself is the user's confirmation gate.
 */
export interface DeleteCheckpointsModalProps {
  open: boolean
  selection: Array<Pick<ModelInfo, 'path' | 'filename' | 'step' | 'sizeBytes'>>
  includingLatest: boolean
  inflight: boolean
  errorMessage?: string | null
  onCancel: () => void
  onConfirm: () => void
}

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '—'
  const mb = n / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  return `${(n / 1024).toFixed(0)} KB`
}

function formatStep(step: number | null | undefined): string {
  if (step === null || step === undefined) return '—'
  if (step >= 10 ** 12) return 'final'
  return step.toLocaleString()
}

export function DeleteCheckpointsModal({
  open,
  selection,
  includingLatest,
  inflight,
  errorMessage,
  onCancel,
  onConfirm,
}: DeleteCheckpointsModalProps) {
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(open) }, [open])

  useEffect(() => {
    if (!open) return
    // Initial focus lands on Cancel per spec §5 "Cancel ghost (initial focus)".
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCancel()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  const onOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      // Click-outside cancels, but clicks inside the panel shouldn't.
      if (e.target === e.currentTarget) onCancel()
    },
    [onCancel],
  )

  if (!mounted) return null

  const count = selection.length

  return (
    <div
      className="delete-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-modal-title"
      onClick={onOverlayClick}
    >
      <div className="delete-modal-panel">
        <h2 id="delete-modal-title" className="delete-modal-title">
          {`Permanently delete ${count} file${count === 1 ? '' : 's'}`}
        </h2>
        <p className="delete-modal-body text-muted">This action cannot be undone.</p>
        {includingLatest && (
          <p className="delete-modal-warning" role="alert">
            Selection includes the latest checkpoint. You may need it to resume training later.
          </p>
        )}
        <ul className="delete-modal-file-list">
          {selection.map(s => (
            <li key={s.path} className="delete-modal-file-item">
              <span className="delete-modal-file-step">{`step ${formatStep(s.step)}`}</span>
              <span className="delete-modal-file-sep"> · </span>
              <span className="delete-modal-file-size">{formatBytes(s.sizeBytes)}</span>
              <span className="delete-modal-file-sep"> · </span>
              <span className="delete-modal-file-name">{s.filename ?? s.path}</span>
            </li>
          ))}
        </ul>
        {errorMessage && (
          <div className="delete-modal-error" role="alert">{errorMessage}</div>
        )}
        <div className="delete-modal-actions">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="delete-modal-btn delete-modal-btn-ghost"
            disabled={inflight}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="delete-modal-btn delete-modal-btn-danger"
            disabled={inflight || count === 0}
          >
            {inflight ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

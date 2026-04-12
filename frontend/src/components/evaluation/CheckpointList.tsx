import type { ModelInfo } from '../../lib/types'
import './CheckpointList.css'

interface CheckpointListProps {
  /** All checkpoints available on the server. */
  models: ModelInfo[]
  /** The currently-selected checkpoint path, or `''` when nothing is selected. */
  selectedPath: string
  /** Fired with the chosen checkpoint path. */
  onSelect: (path: string) => void
  /** Disable the picker (e.g. while an evaluation is in-flight). */
  disabled?: boolean
}

/**
 * Formats bytes into a human-readable string (1.2 MB, 512 KB, …).
 * We keep the math here instead of pulling in a dependency just for this.
 */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

/**
 * Pulls a "step" count out of checkpoint names like `ppo_100000.zip` or
 * `model_step=2048.zip`. Best-effort — unknown formats render as null
 * and the UI just falls back to showing the filename.
 */
function parseStep(basename: string): number | null {
  // Match digit runs preceded by _ or =, anchored near the end of the name
  const match = basename.match(/(?:^|[_=-])(\d{3,})(?=\.zip$|\.|$)/i)
  if (!match) return null
  const n = Number(match[1])
  return Number.isFinite(n) ? n : null
}

function splitPath(path: string): { dir: string; base: string } {
  const lastSlash = path.lastIndexOf('/')
  if (lastSlash === -1) return { dir: '', base: path }
  return { dir: path.slice(0, lastSlash), base: path.slice(lastSlash + 1) }
}

/**
 * A radio-group picker for model checkpoints. Richer than a plain
 * <select>: shows filename, subdirectory, size, and (when parseable) a
 * step count. Used inside EvalPanel and wherever else we need to pick a
 * model for evaluation.
 */
export function CheckpointList({
  models,
  selectedPath,
  onSelect,
  disabled = false,
}: CheckpointListProps) {
  if (models.length === 0) {
    return (
      <div className="checkpoint-list checkpoint-list--empty card">
        <p className="checkpoint-list-empty empty-state">
          No checkpoints found. Train a model first to populate this list.
        </p>
      </div>
    )
  }

  return (
    <div
      className="checkpoint-list card"
      role="radiogroup"
      aria-label="Model checkpoints"
    >
      <div className="checkpoint-list-header">
        <span className="checkpoint-list-count">
          {models.length} checkpoint{models.length === 1 ? '' : 's'}
        </span>
      </div>
      <ul className="checkpoint-list-items">
        {models.map(m => {
          const { dir, base } = splitPath(m.path)
          const step = parseStep(base)
          const isSelected = m.path === selectedPath
          const fieldId = `checkpoint-${m.path.replace(/[^a-z0-9]/gi, '-')}`
          return (
            <li key={m.path} className="checkpoint-list-item-wrap">
              <label
                htmlFor={fieldId}
                className={`checkpoint-list-item${isSelected ? ' is-selected' : ''}`}
                data-selected={isSelected}
              >
                <input
                  id={fieldId}
                  type="radio"
                  name="checkpoint"
                  value={m.path}
                  checked={isSelected}
                  disabled={disabled}
                  onChange={() => onSelect(m.path)}
                  className="checkpoint-list-radio"
                  aria-describedby={`${fieldId}-meta`}
                />
                <span className="checkpoint-list-main">
                  <span className="checkpoint-list-name">{base}</span>
                  {dir && <span className="checkpoint-list-dir">{dir}/</span>}
                </span>
                <span
                  id={`${fieldId}-meta`}
                  className="checkpoint-list-meta"
                >
                  {step !== null && (
                    <span className="checkpoint-list-step">
                      step {step.toLocaleString()}
                    </span>
                  )}
                  <span className="checkpoint-list-size">{formatSize(m.sizeBytes)}</span>
                </span>
              </label>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

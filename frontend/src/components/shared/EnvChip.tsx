import { memo } from 'react'
import { formatEnvId } from '../../lib/formatGame'

/**
 * Env chip shared between Dashboard Recent Games and ReplayList
 * unified history (A5 extraction, 2026-04-19). Both surfaces
 * rendered identical markup that distinguished a "missing env_id"
 * row from one with a numeric or "demo" id, including the
 * `data-env-id` attribute the styling relies on and an aria-label
 * with two variants.
 *
 * The component intentionally returns just the `<span>` (no `<td>`
 * wrapper) so callers keep ownership of their parent cell — the
 * existing CSS targets `.env-chip` directly, not `td > .env-chip`.
 *
 * `memo` matches the surrounding memoized row components (RecentGameRow,
 * GameRow) so the same scalar `envId` doesn't trigger a paint.
 */
export interface EnvChipProps {
  envId: string | number | null | undefined
}

export const EnvChip = memo(function EnvChip({ envId }: EnvChipProps) {
  // Match the pre-extraction call sites byte-for-byte: `=== undefined`
  // gates the `--empty` class + the aria-label variant; `?? ''` covers
  // both null and undefined for the `data-env-id` attribute.
  const isMissing = envId === undefined
  return (
    <span
      className={`env-chip${isMissing ? ' env-chip--empty' : ''}`}
      aria-label={isMissing ? 'No env id recorded' : `Env ${envId}`}
      data-env-id={envId ?? ''}
    >
      {formatEnvId(envId)}
    </span>
  )
})

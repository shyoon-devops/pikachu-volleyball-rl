import type { CSSProperties, HTMLAttributes } from 'react'
import './Skeleton.css'

type SkeletonVariant = 'line' | 'rect' | 'circle'

interface SkeletonProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'children'> {
  /** Visual shape. `line` is short and rounded, `rect` fills the container, `circle` is 1:1. */
  variant?: SkeletonVariant
  /** CSS width (e.g. "80%" or 240). */
  width?: string | number
  /** CSS height (e.g. "1em" or 16). */
  height?: string | number
  /** Accessible label for the loading region. Ignored when `aria-hidden`. */
  label?: string
}

function cssSize(value: string | number | undefined): string | undefined {
  if (value === undefined) return undefined
  return typeof value === 'number' ? `${value}px` : value
}

/**
 * Skeleton — a pulsing placeholder used while content is loading.
 * Uses `role="status"` + screen-reader label by default so assistive tech
 * announces the loading state. Respects `prefers-reduced-motion`.
 */
export function Skeleton({
  variant = 'line',
  width,
  height,
  label,
  className,
  style,
  ...rest
}: SkeletonProps) {
  const ariaHidden = rest['aria-hidden'] === true || rest['aria-hidden'] === 'true'
  const mergedStyle: CSSProperties = {
    ...style,
    width: cssSize(width),
    height: cssSize(height),
  }

  return (
    <span
      {...rest}
      role={ariaHidden ? undefined : 'status'}
      aria-live={ariaHidden ? undefined : 'polite'}
      aria-busy={ariaHidden ? undefined : true}
      className={`skeleton skeleton--${variant}${className ? ` ${className}` : ''}`}
      style={mergedStyle}
    >
      {!ariaHidden && <span className="sr-only">{label ?? 'Loading…'}</span>}
    </span>
  )
}

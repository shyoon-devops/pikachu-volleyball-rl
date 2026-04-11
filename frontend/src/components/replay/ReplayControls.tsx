import './ReplayControls.css'

interface ReplayControlsProps {
  isPlaying: boolean
  speed: number
  currentFrame: number
  totalFrames: number
  onTogglePlay: () => void
  onSpeedChange: (speed: number) => void
  onSeek: (frame: number) => void
}

const SPEEDS = [0.5, 1, 2, 4] as const

export function ReplayControls({
  isPlaying,
  speed,
  currentFrame,
  totalFrames,
  onTogglePlay,
  onSpeedChange,
  onSeek,
}: ReplayControlsProps) {
  return (
    <div className="replay-controls card">
      <div className="replay-controls-bar">
        <button
          onClick={onTogglePlay}
          className="replay-controls-play-btn btn btn-primary"
          data-playing={isPlaying}
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>

        <div className="replay-controls-speeds">
          {SPEEDS.map(s => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className="replay-controls-speed-btn btn btn-ghost"
              data-active={speed === s}
            >
              {s}x
            </button>
          ))}
        </div>

        <span className="replay-controls-frame-info">
          {currentFrame} / {totalFrames}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(0, totalFrames - 1)}
        value={currentFrame}
        onChange={e => onSeek(Number(e.target.value))}
        className="replay-controls-seek"
        aria-label="Seek replay frame"
        aria-valuemin={0}
        aria-valuemax={Math.max(0, totalFrames - 1)}
        aria-valuenow={currentFrame}
      />

      <div className="replay-controls-shortcuts">
        <kbd>Space</kbd> Play/Pause
        <kbd>&larr;</kbd><kbd>&rarr;</kbd> Step
        <kbd>Shift</kbd>+Arrow &plusmn;10
        <kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> Speed
      </div>
    </div>
  )
}

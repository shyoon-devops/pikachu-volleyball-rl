/**
 * Port of `audio.js::PikaAudio` from the original
 * pikachu-volleyball (gorisanson, MIT). The original used
 * `@pixi/sound` + `StereoFilter` to route each effect across left /
 * center / right channels. We replicate the audible layer with native
 * HTMLAudio + (optional) WebAudio `StereoPannerNode` — `@pixi/sound`
 * pulls in a non-trivial decoder bundle we don't otherwise need.
 *
 * Browsers block playback until a user gesture, so the audio context
 * is lazy-created on the first `play*` call. Calls made before the
 * first gesture become no-ops (playback silently fails in every major
 * browser). `primeOnGesture()` is the recommended boot path: install
 * it on a pointer listener so the context is unlocked the moment the
 * user interacts.
 *
 * Trigger timing (audio.js + pikavolley.js references; BE emits the
 * flags now — FE just fires `playSfx(name)` when the flag is set):
 *   - powerHit           — on a successful power-hit connect
 *   - ballTouchesGround  — on ball hitting the floor (not on power-hit)
 *   - pipikachu          — multi-step power-hit combo (engine-driven)
 *   - pika / chu         — pikachu voice during play
 *   - bgm                — optional background loop; off by default
 *     since the dashboard is a monitoring surface, not a game view.
 *
 * `pi` and `pikachu` from audio.js are menu-layer sounds (title /
 * "with friend" select) and are intentionally excluded — the RL
 * dashboard never shows those surfaces, so shipping their WAVs
 * would only bloat the bundle.
 */

export type SfxName =
  | 'pipikachu'
  | 'pika'
  | 'chu'
  | 'powerHit'
  | 'ballTouchesGround'

export type Pan = -1 | 0 | 1 // -1 left, 0 center, 1 right

/** URL map — FE public paths. Assets exist under `public/assets/sounds/`. */
const SFX_URL: Record<SfxName, string> = {
  pipikachu: '/assets/sounds/WAVE140_1.wav',
  pika: '/assets/sounds/WAVE141_1.wav',
  chu: '/assets/sounds/WAVE142_1.wav',
  powerHit: '/assets/sounds/WAVE145_1.wav',
  ballTouchesGround: '/assets/sounds/WAVE146_1.wav',
}
const BGM_URL = '/assets/sounds/bgm.mp3'

/** Volume defaults — match audio.js:37-38. */
const DEFAULT_BGM_VOLUME = 0.2
const DEFAULT_SFX_VOLUME = 0.35

interface SfxChannel {
  audio: HTMLAudioElement
  panner: StereoPannerNode | null
  source: MediaElementAudioSourceNode | null
}

/**
 * Minimal audio manager. Safe to instantiate on module load — it
 * doesn't create AudioContext until `primeOnGesture()` runs.
 */
export class PikaAudio {
  private ctx: AudioContext | null = null
  private bgm: HTMLAudioElement | null = null
  private sfx: Partial<Record<SfxName, { [P in Pan]?: SfxChannel }>> = {}
  private sfxVolume = DEFAULT_SFX_VOLUME
  private bgmVolume = DEFAULT_BGM_VOLUME
  // Default muted. The FE is a training dashboard — users shouldn't
  // get a surprise SFX burst the first time they click anywhere. The
  // port-level fidelity still matters because a future "watch live"
  // surface can flip `setMutedAll(false)` and reuse everything.
  private mutedAll = true

  /**
   * Must be called from a user-gesture handler (pointerdown, click,
   * keydown). Idempotent — safe to attach to many listeners.
   */
  primeOnGesture(): void {
    if (this.ctx) return
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return
      this.ctx = new Ctx()
    } catch {
      // Some environments (SSR, tests without a window) will throw.
      // Leave `ctx` null — play calls will no-op cleanly.
      this.ctx = null
    }
  }

  setMutedAll(muted: boolean): void {
    this.mutedAll = muted
    if (this.bgm) this.bgm.muted = muted
    for (const name in this.sfx) {
      const channels = this.sfx[name as SfxName]
      if (!channels) continue
      for (const pan of [-1, 0, 1] as Pan[]) {
        const ch = channels[pan]
        if (ch) ch.audio.muted = muted
      }
    }
  }

  isMuted(): boolean {
    return this.mutedAll
  }

  /** Play an SFX, panned to left / center / right (audio.js:140-147). */
  playSfx(name: SfxName, pan: Pan = 0): void {
    const ch = this.getOrCreateChannel(name, pan)
    if (!ch) return
    try {
      ch.audio.currentTime = 0
      void ch.audio.play()
    } catch {
      // Autoplay blocked or element not yet loaded. Swallow — retriable
      // on the next trigger; never worth propagating to the user.
    }
  }

  /** Start looping BGM. No-op if already playing. */
  playBgm(): void {
    const bgm = this.getOrCreateBgm()
    if (!bgm) return
    if (!bgm.paused) return
    try {
      void bgm.play()
    } catch {
      // Autoplay policy — user hasn't interacted yet.
    }
  }

  stopBgm(): void {
    if (!this.bgm) return
    this.bgm.pause()
    this.bgm.currentTime = 0
  }

  private getOrCreateBgm(): HTMLAudioElement | null {
    if (this.bgm) return this.bgm
    if (typeof Audio === 'undefined') return null
    const el = new Audio(BGM_URL)
    el.loop = true
    el.volume = this.bgmVolume
    el.muted = this.mutedAll
    el.preload = 'auto'
    this.bgm = el
    return el
  }

  private getOrCreateChannel(name: SfxName, pan: Pan): SfxChannel | null {
    if (typeof Audio === 'undefined') return null
    const channels = this.sfx[name] ?? (this.sfx[name] = {})
    const existing = channels[pan]
    if (existing) return existing

    const url = SFX_URL[name]
    const audio = new Audio(url)
    audio.volume = this.sfxVolume
    audio.muted = this.mutedAll
    audio.preload = 'auto'

    // Stereo panning is only wired when the audio context already
    // exists. Without it the channel plays through the default output
    // mixer and `pan` is effectively ignored — acceptable trade-off vs.
    // a loud upfront AudioContext allocation before user gesture.
    let panner: StereoPannerNode | null = null
    let source: MediaElementAudioSourceNode | null = null
    if (this.ctx && pan !== 0) {
      try {
        source = this.ctx.createMediaElementSource(audio)
        panner = this.ctx.createStereoPanner()
        // audio.js:110-112 uses ±0.75 for left/right, 0 for center.
        panner.pan.value = pan === -1 ? -0.75 : 0.75
        source.connect(panner).connect(this.ctx.destination)
      } catch {
        panner = null
        source = null
      }
    }

    const channel: SfxChannel = { audio, panner, source }
    channels[pan] = channel
    return channel
  }
}

/** Module-scoped singleton — one audio manager per page. */
let singleton: PikaAudio | null = null

export function getPikaAudio(): PikaAudio {
  if (!singleton) singleton = new PikaAudio()
  return singleton
}

"""Observation encoder Protocol — MLP (Pika) / CNN (MineRL) swap.

Phase 0 research (docs/research/MINERL-PHASE0-RESEARCH.md §10)
identified ``dreamer_runner._RSSM.embed`` as the single blocker
for Pika↔MineRL encoder reuse. Pika feeds an 18-float vector; an
image-obs env (MineRL 64×64×3 RGB) needs a convolutional encoder
that emits the same ``(B, hidden)`` embedding. Extracting the
Protocol here lets downstream factories swap encoders without
touching the RSSM / actor / critic at all.

This module is **Phase 0 scaffolding only** — ``_RSSM`` inside
``backend.rl.dreamer_runner`` does NOT import this Protocol yet
(that wire-in lands in Phase 2, scoped out of the POC). Defining
the contract now so MineRL repo and the Pika refactor both
converge on the same interface.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ObsEncoder(Protocol):
    """Pure-function obs → embedding.

    Implementation contract:
      * ``forward(obs)`` accepts a tensor shaped ``(B, *obs_shape)``
        and returns an embedding shaped ``(B, hidden)``. ``obs_shape``
        is implementation-specific — MLP takes ``(obs_dim,)``, CNN
        takes ``(C, H, W)``. The RSSM only sees the output shape.
      * ``hidden`` is a Python int attribute — the RSSM reads it at
        construction time to size the GRU cell + prior/post heads.
      * Implementations are ``torch.nn.Module`` subclasses in
        practice; the Protocol intentionally does NOT constrain
        that so a test can inject a callable stub.

    Two concrete implementations will ship (not in this POC):
      * ``MlpObsEncoder`` — ``Linear(obs_dim, hidden) → SiLU →
        Linear(hidden, hidden) → SiLU``. Mirrors the current
        inlined ``_RSSM.embed`` shape exactly so Pika parity holds.
      * ``ImpalaCnnObsEncoder`` — 3-stage residual CNN, ~2M params,
        outputs ``(B, hidden)``. MineRL Diamond default per Dreamer V3
        paper §A.1.
    """

    hidden: int

    def __call__(self, obs: Any) -> Any: ...


class MlpEncoderSpec:
    """Declarative MLP-encoder config — the factory pattern the
    RSSM will consume in Phase 2. Keeping it as a plain dataclass-
    free value type for POC to avoid pulling in torch at
    import-time for docs / lint runs.
    """

    def __init__(self, obs_dim: int, hidden: int) -> None:
        self.obs_dim = int(obs_dim)
        self.hidden = int(hidden)
        self.kind = "mlp"


class CnnEncoderSpec:
    """Declarative CNN-encoder config for MineRL-style image obs.

    Channels / kernel / stride schedule matches the Impala CNN
    baseline. Phase 0 ships the spec only; MineRL repo implements
    the actual torch module in its own tree using this as the
    interface hint.
    """

    def __init__(
        self,
        obs_shape: tuple[int, int, int],  # (C, H, W)
        hidden: int,
        channels: tuple[int, ...] = (16, 32, 32),
    ) -> None:
        assert len(obs_shape) == 3, (
            f"CnnEncoderSpec requires (C, H, W); got {obs_shape}"
        )
        self.obs_shape = tuple(obs_shape)
        self.hidden = int(hidden)
        self.channels = tuple(channels)
        self.kind = "cnn"


__all__ = ["ObsEncoder", "MlpEncoderSpec", "CnnEncoderSpec"]

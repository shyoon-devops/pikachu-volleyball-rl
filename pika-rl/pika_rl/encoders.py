"""Observation encoder Protocol — MLP (Pika) / CNN (MineRL) swap.

Phase 0 research (docs/research/MINERL-PHASE0-RESEARCH.md §10)
identified ``dreamer_runner._RSSM.embed`` as the single blocker
for Pika↔MineRL encoder reuse. Pika feeds an 18-float vector; an
image-obs env (MineRL 64×64×3 RGB) needs a convolutional encoder
that emits the same ``(B, hidden)`` embedding. Extracting the
Protocol here lets downstream factories swap encoders without
touching the RSSM / actor / critic at all.

MineRL Phase 2 (2026-04-23 PM directive) ships the concrete
``MineRLCNNEncoder`` here so the MineRL repo's Treechop PPO
baseline (``train_ppo_treechop.py`` in the minerl-diamond repo)
has a ready-made image encoder. The ``_RSSM`` wire-in for Dreamer
still lands in Phase 3; the encoder itself is usable today by any
SB3 feature-extractor consumer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import torch as th
import torch.nn as nn
import torch.nn.functional as F


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


class _NatureCNN(nn.Module):
    """DQN-paper 3-conv stack adapted for 64×64 RGB.

    IMPALA CNN (3 residual stacks) was the other candidate from the
    Phase 0 research §7 but targets 96×96+ inputs. For MineRL's
    64×64 default, NatureCNN (Mnih et al. 2015) is the compact
    ~1.7M-param baseline that Dreamer V3 §A.1 and the OpenAI VPT
    ablation both treat as parity-floor. Swap-in for IMPALA is a
    one-file change behind ``MineRLCNNEncoder``.

    Input shape: ``(B, C, H, W)`` — channels-first, uint8 pixels
    expected in ``[0, 255]`` and normalised inside ``forward``.
    Output shape: ``(B, _feature_dim)`` — the caller's MLP head
    reduces that to ``hidden`` separately so the conv stack
    doesn't hardcode the embedding size.
    """

    def __init__(self, in_channels: int = 3) -> None:
        super().__init__()
        # NatureCNN kernels: 8/4, 4/2, 3/1. Stride schedule collapses
        # 64×64 → 7×7 → 3×3 → 1×1 deterministically, so no adaptive
        # pooling / padding kludge is needed.
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, 32, kernel_size=8, stride=4), nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, kernel_size=4, stride=2), nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, kernel_size=3, stride=1), nn.ReLU(inplace=True),
            nn.Flatten(),
        )

    @property
    def feature_dim(self) -> int:
        # 64 channels × 4 × 4 spatial = 1024 for a 64×64 input. Hard-
        # coded to avoid a dry-forward at construction time (cheap,
        # but noisy on CPU smoke tests). Callers that deviate from
        # 64×64 must override — see MineRLCNNEncoder._probe.
        return 64 * 4 * 4

    def forward(self, pov: th.Tensor) -> th.Tensor:
        # MineRL ``pov`` arrives as uint8; normalise to [0, 1] here
        # so the SB3 feature-extractor contract (float tensor to the
        # downstream MLP) holds regardless of upstream dtype.
        if pov.dtype == th.uint8:
            pov = pov.float() / 255.0
        return self.conv(pov)


class MineRLCNNEncoder(nn.Module):
    """Image-pov + optional inventory vector → ``(B, hidden)`` embed.

    Concrete implementation of :class:`ObsEncoder` for the MineRL
    Diamond Phase 2 PPO baseline. Two inputs:

    * ``pov`` — ``(B, C, H, W)`` RGB image tensor. Phase 2 starts
      with the MineRL default 64×64×3 but the class probes the
      conv output at construction so a caller can bump resolution
      (Phase 0 research §5) without touching the class.
    * ``inventory`` — optional ``(B, inventory_dim)`` vector. MineRL
      observation dicts carry per-slot item counts; the MineRL
      repo's env wrapper flattens them into this vector before
      invoking forward. Treechop (Phase 2 Week 1-2) doesn't need
      the inventory signal yet — construct with
      ``inventory_dim=0`` to skip the head entirely.

    Fusion = conv features + (optional) inventory MLP, concatenated
    then projected to ``hidden``. Matches the ``ObsEncoder``
    Protocol: ``.hidden: int`` attribute, ``forward(obs) → (B, hidden)``.
    """

    hidden: int

    def __init__(
        self,
        obs_shape: tuple[int, int, int] = (3, 64, 64),
        hidden: int = 512,
        inventory_dim: int = 0,
        cnn: nn.Module | None = None,
    ) -> None:
        super().__init__()
        assert len(obs_shape) == 3, (
            f"obs_shape must be (C, H, W); got {obs_shape}"
        )
        self.obs_shape = tuple(obs_shape)
        self.hidden = int(hidden)
        self.inventory_dim = int(inventory_dim)

        self.cnn = cnn if cnn is not None else _NatureCNN(in_channels=obs_shape[0])
        conv_out = self._probe_cnn_output(self.cnn, self.obs_shape)

        # Inventory head only instantiated when needed — skipping it
        # for Treechop saves ~10k params and one forward through a
        # no-op MLP per step.
        if self.inventory_dim > 0:
            self.inv_head = nn.Sequential(
                nn.Linear(self.inventory_dim, hidden), nn.ReLU(inplace=True),
                nn.Linear(hidden, hidden), nn.ReLU(inplace=True),
            )
            fused_dim = conv_out + hidden
        else:
            self.inv_head = None
            fused_dim = conv_out

        self.projection = nn.Sequential(
            nn.Linear(fused_dim, hidden), nn.ReLU(inplace=True),
        )

    @staticmethod
    def _probe_cnn_output(cnn: nn.Module, obs_shape: tuple[int, int, int]) -> int:
        """Dry-forward a zero tensor through the conv stack to size
        the projection layer. Costs one CPU forward at construction;
        worth it so callers can drop in custom CNNs (IMPALA, ViT-tiny)
        without wiring the output-dim into two places."""
        with th.no_grad():
            probe = th.zeros(1, *obs_shape)
            out = cnn(probe)
            assert out.ndim == 2, (
                f"CNN must flatten to (B, features); got shape {tuple(out.shape)}"
            )
            return int(out.shape[1])

    def forward(
        self,
        pov: th.Tensor,
        inventory: th.Tensor | None = None,
    ) -> th.Tensor:
        """Return the ``(B, hidden)`` embedding.

        Accepts pov alone when ``inventory_dim=0`` — the MineRL
        Treechop baseline doesn't need inventory signal. Raises
        when an inventory is supplied to an encoder built without
        the head (shape would silently mismatch otherwise)."""
        features = self.cnn(pov)
        if self.inv_head is not None:
            if inventory is None:
                raise ValueError(
                    "encoder was built with inventory_dim > 0 but forward "
                    "was called without an inventory tensor"
                )
            inv_features = self.inv_head(inventory.float())
            features = th.cat([features, inv_features], dim=-1)
        elif inventory is not None:
            raise ValueError(
                "encoder was built with inventory_dim=0; do not pass "
                "an inventory tensor (would be a silent no-op)"
            )
        return self.projection(features)


__all__ = [
    "ObsEncoder",
    "MlpEncoderSpec",
    "CnnEncoderSpec",
    "MineRLCNNEncoder",
]

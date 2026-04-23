"""Tests for ``pika_rl.encoders.MineRLCNNEncoder``.

Phase 2 Day 1 (2026-04-23): shape contract + ObsEncoder Protocol
conformance + uint8/float parity + inventory-head wiring +
projection sizing independence from CNN output shape. These are
the assertions the MineRL repo's Treechop PPO baseline relies on
when it plugs this module into SB3's ``features_extractor_class``.
"""

from __future__ import annotations

import pytest
import torch as th

from pika_rl.encoders import MineRLCNNEncoder, ObsEncoder


class TestConstruction:
    def test_default_shape(self) -> None:
        enc = MineRLCNNEncoder()
        assert enc.obs_shape == (3, 64, 64)
        assert enc.hidden == 512
        assert enc.inventory_dim == 0
        assert enc.inv_head is None

    def test_obs_shape_three_dim_required(self) -> None:
        with pytest.raises(AssertionError, match=r"\(C, H, W\)"):
            MineRLCNNEncoder(obs_shape=(64, 64))  # type: ignore[arg-type]

    def test_satisfies_obs_encoder_protocol(self) -> None:
        # Runtime-checkable Protocol — MineRL trainer may assert this
        # when building the policy_factory spec.
        enc = MineRLCNNEncoder()
        assert isinstance(enc, ObsEncoder)

    def test_custom_hidden_size(self) -> None:
        for h in (128, 256, 1024):
            enc = MineRLCNNEncoder(hidden=h)
            assert enc.hidden == h


class TestForwardShape:
    def test_pov_only_default(self) -> None:
        enc = MineRLCNNEncoder()
        pov = th.zeros(8, 3, 64, 64)
        out = enc(pov)
        assert out.shape == (8, 512)

    @pytest.mark.parametrize("batch", [1, 4, 16])
    def test_batch_size_variants(self, batch: int) -> None:
        enc = MineRLCNNEncoder(hidden=128)
        pov = th.zeros(batch, 3, 64, 64)
        out = enc(pov)
        assert out.shape == (batch, 128)

    def test_uint8_input_normalised(self) -> None:
        """MineRL pov arrives as uint8 [0,255]. The encoder must
        internally convert to float without requiring callers to
        pre-normalise — the MineRL repo's Treechop wrapper
        intentionally leaves obs in native uint8 for memory."""
        enc = MineRLCNNEncoder()
        pov_u8 = th.randint(0, 256, (2, 3, 64, 64), dtype=th.uint8)
        pov_f32 = pov_u8.float() / 255.0
        out_u8 = enc(pov_u8)
        out_f32 = enc(pov_f32)
        assert th.allclose(out_u8, out_f32, atol=1e-6)


class TestInventoryFusion:
    def test_inventory_concatenated_into_embedding(self) -> None:
        enc = MineRLCNNEncoder(inventory_dim=36, hidden=256)
        assert enc.inv_head is not None
        pov = th.zeros(4, 3, 64, 64)
        inv = th.zeros(4, 36)
        out = enc(pov, inv)
        assert out.shape == (4, 256)

    def test_missing_inventory_when_expected_raises(self) -> None:
        enc = MineRLCNNEncoder(inventory_dim=36)
        pov = th.zeros(2, 3, 64, 64)
        with pytest.raises(ValueError, match="without an inventory tensor"):
            enc(pov)

    def test_extra_inventory_when_not_expected_raises(self) -> None:
        """Silent drop of inventory when inventory_dim=0 would
        mask a MineRL env-wrapper bug. Raise instead so the mismatch
        shows up at the first forward pass."""
        enc = MineRLCNNEncoder(inventory_dim=0)
        pov = th.zeros(2, 3, 64, 64)
        inv = th.zeros(2, 36)
        with pytest.raises(ValueError, match="inventory_dim=0"):
            enc(pov, inv)


class TestProjectionSizing:
    """The projection layer sizes itself from a probe forward —
    callers can swap the CNN backbone without re-wiring dimensions.
    Critical for dropping in IMPALA (Phase 3) later without a
    breaking API change to downstream consumers."""

    def test_custom_cnn_backbone_probed(self) -> None:
        import torch.nn as nn

        class _TinyStub(nn.Module):
            def forward(self, x: th.Tensor) -> th.Tensor:
                return x.flatten(1)  # (B, C*H*W) — 3*64*64 = 12288

        enc = MineRLCNNEncoder(cnn=_TinyStub(), hidden=64)
        out = enc(th.zeros(2, 3, 64, 64))
        assert out.shape == (2, 64)

    def test_non_flat_cnn_output_rejected(self) -> None:
        import torch.nn as nn

        class _BadStub(nn.Module):
            def forward(self, x: th.Tensor) -> th.Tensor:
                return x  # 4-D tensor — CNN must flatten before output

        with pytest.raises(AssertionError, match="flatten"):
            MineRLCNNEncoder(cnn=_BadStub())


class TestHWCAutoPermute:
    """Phase 2 Day 1 regression (2026-04-23): MineRL ``pov`` arrives
    as ``(B, 64, 64, 3)`` HWC but Conv2d expects NCHW — first smoke
    crashed with "Kernel size can't be greater than actual input
    size" because the 8×8 kernel hit the 3-wide channel dim. Encoder
    now auto-permutes when the last dim looks like a channel count.
    These cases pin the contract so the crash can't regress."""

    def test_hwc_uint8_single_sample_input(self) -> None:
        enc = MineRLCNNEncoder(hidden=256)
        # Exact MineRL pov shape — single sample HWC uint8.
        pov = th.randint(0, 256, (1, 64, 64, 3), dtype=th.uint8)
        out = enc(pov)
        assert out.shape == (1, 256)
        assert out.dtype == th.float32

    def test_hwc_uint8_batch_input(self) -> None:
        enc = MineRLCNNEncoder(hidden=256)
        pov = th.randint(0, 256, (4, 64, 64, 3), dtype=th.uint8)
        out = enc(pov)
        assert out.shape == (4, 256)
        assert out.dtype == th.float32

    def test_autograd_backward_does_not_crash(self) -> None:
        """Phase 2 PPO will backprop through this encoder; the permute
        + uint8→float path must preserve the autograd graph."""
        enc = MineRLCNNEncoder(hidden=128)
        pov = th.randint(0, 256, (2, 64, 64, 3), dtype=th.uint8)
        out = enc(pov)
        loss = out.sum()
        loss.backward()
        # Every parameter got a gradient.
        for name, param in enc.named_parameters():
            assert param.grad is not None, f"no grad on {name}"

    def test_nchw_input_pass_through_unchanged(self) -> None:
        """CHW input (SB3's preprocessed layout) must still work —
        the permute is conditional on the last-dim heuristic, not
        unconditional."""
        enc = MineRLCNNEncoder(hidden=256)
        pov = th.zeros(4, 3, 64, 64, dtype=th.float32)
        out = enc(pov)
        assert out.shape == (4, 256)

    def test_3d_single_sample_auto_batches(self) -> None:
        """Unbatched (H, W, C) input from a direct ``env.reset()``
        smoke → encoder adds batch dim automatically so smoke
        scripts work without wrapping every obs in ``obs[None]``."""
        enc = MineRLCNNEncoder(hidden=128)
        pov = th.randint(0, 256, (64, 64, 3), dtype=th.uint8)
        out = enc(pov)
        assert out.shape == (1, 128)

    def test_non_4d_input_rejected(self) -> None:
        enc = MineRLCNNEncoder()
        bad = th.zeros(1, 2, 3, 64, 64)  # 5-D
        with pytest.raises(ValueError, match="3-D .* or 4-D"):
            enc(bad)


class TestParameterCount:
    """Smoke-budget check against Phase 0 research §7 estimate
    (~1.7M params for NatureCNN baseline). Fires if a future
    refactor accidentally adds a huge projection head or similar
    memory-bloating change."""

    def test_param_count_reasonable(self) -> None:
        enc = MineRLCNNEncoder(hidden=512, inventory_dim=0)
        n = sum(p.numel() for p in enc.parameters())
        # ~600k with NatureCNN 64×64 + 512-hidden projection — well
        # under the Phase 0 research ceiling. Upper bound loose to
        # accommodate CNN-backbone experiments within reason.
        assert 100_000 < n < 5_000_000, (
            f"MineRLCNNEncoder parameter count {n:,} outside expected "
            "range — did the CNN backbone or projection head change?"
        )

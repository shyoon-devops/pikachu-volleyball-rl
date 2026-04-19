"""Tests for the OpponentProvider hierarchy.

Covers FixedBotProvider (legacy backward-compat), PFSPProvider sampling
strategies (uniform / PFSP / elo_proximity), mirror matches, empty-pool
safety, and on_match_end dispatch to a rating store mock.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from backend.game.bot import RuleBasedBot
from backend.game.engine import GameState, PikachuVolleyball, PlayerInput
from backend.rl.opponent import (
    FixedBotProvider,
    Opponent,
    OpponentProvider,
    PFSPProvider,
)


# ─── Test doubles ─────────────────────────────────────────────────────


class _DummyOpponent:
    """Minimal Opponent implementation; just tags itself by id."""

    def __init__(self, id: str, rating: float = 1000.0) -> None:
        self.id = id
        self.rating = rating

    def get_action(self, state: Any, *, is_player2: bool) -> PlayerInput:
        return PlayerInput(x_dir=0, y_dir=0, power_hit=False)


class _FakeRatingStore:
    """Captures match results + synthesizes a deterministic win_rate map."""

    def __init__(self, win_rates: dict[str, float] | None = None) -> None:
        self._win_rates = win_rates or {}
        self.recorded: list[dict[str, Any]] = []

    def win_rate_against(self, opponent_id: str) -> float:
        return self._win_rates.get(opponent_id, 0.5)

    def record_match(
        self,
        *,
        opponent_id: str,
        winner: int,
        score1: int,
        score2: int,
    ) -> None:
        self.recorded.append(
            dict(
                opponent_id=opponent_id,
                winner=winner,
                score1=score1,
                score2=score2,
            )
        )


def _pool_entry(id: str, rating: float = 1000.0) -> dict[str, Any]:
    return {
        "id": id,
        "rating": rating,
        "build": lambda: _DummyOpponent(id=id, rating=rating),
    }


# ─── FixedBotProvider ─────────────────────────────────────────────────


class TestFixedBotProvider:
    def test_returns_rulebased_bot_of_requested_level(self) -> None:
        provider = FixedBotProvider(level=3)
        bot = provider.get_opponent()
        assert isinstance(bot, RuleBasedBot)
        assert bot.level == 3

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValueError, match="Level must be 1-5"):
            FixedBotProvider(level=0)

    def test_returned_bot_speaks_protocol(self) -> None:
        provider = FixedBotProvider(level=1)
        bot = provider.get_opponent()
        # Duck-typed Opponent protocol check.
        assert isinstance(bot, Opponent)

    def test_fresh_bot_per_call(self) -> None:
        """Provider hands out a new RuleBasedBot on every get_opponent —
        preserves the per-episode ``_delay_counter`` reset behavior the
        legacy env used before the league arrived."""
        provider = FixedBotProvider(level=2)
        a = provider.get_opponent()
        b = provider.get_opponent()
        assert a is not b


# ─── PFSPProvider — strategies ─────────────────────────────────────────


class TestPFSPProviderSampling:
    def test_uniform_samples_whole_pool(self) -> None:
        pool = [_pool_entry(f"ck_{i}", rating=1000 + i * 10) for i in range(5)]
        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="uniform",
            rng_seed=42,
        )
        picks = Counter()
        for i in range(200):
            opp = provider.get_opponent(env_index=i)
            picks[opp.id] += 1
        # All 5 pool members should appear at least a handful of times.
        assert len(picks) == 5
        for count in picks.values():
            assert count >= 10

    def test_pfsp_falls_back_to_uniform_below_min_pool(self) -> None:
        # 3 entries, min_pool_for_pfsp=8 — PFSP should fall back to
        # uniform sampling rather than collapsing onto a single pick.
        pool = [_pool_entry(f"ck_{i}") for i in range(3)]
        store = _FakeRatingStore(
            win_rates={"ck_0": 0.99, "ck_1": 0.5, "ck_2": 0.01}
        )
        provider = PFSPProvider(
            pool=pool,
            rating_store=store,
            strategy="pfsp",
            min_pool_for_pfsp=8,
            rng_seed=0,
        )
        picks = Counter(
            provider.get_opponent(env_index=i).id for i in range(300)
        )
        # Uniform fallback: each of the 3 hit ~100 times. If PFSP had
        # been applied, ck_0 (we win 99% vs) would be rare and ck_2
        # dominant — so this also pins the fallback branch.
        assert len(picks) == 3
        assert all(50 < c < 150 for c in picks.values())

    def test_pfsp_weights_bias_toward_opponents_we_lose_to(self) -> None:
        # 10 entries, ample history. PFSP should pick ck_loss (we win
        # 1% against) an order of magnitude more than ck_win (we win
        # 99% against).
        pool = [_pool_entry(f"ck_{i}") for i in range(10)]
        win_rates = {f"ck_{i}": 0.5 for i in range(10)}
        win_rates["ck_0"] = 0.99  # we dominate → low weight
        win_rates["ck_9"] = 0.01  # we lose to → high weight
        store = _FakeRatingStore(win_rates=win_rates)
        provider = PFSPProvider(
            pool=pool,
            rating_store=store,
            strategy="pfsp",
            pfsp_p=2.0,
            min_pool_for_pfsp=8,
            rng_seed=42,
        )
        picks = Counter(
            provider.get_opponent(env_index=i).id for i in range(2000)
        )
        assert picks["ck_9"] > picks["ck_0"] * 5, picks

    def test_elo_proximity_peaks_near_my_rating(self) -> None:
        # Ratings span 800-1200 in 50-step increments; my rating is
        # 1000. Opponents near 1000 should be picked far more often
        # than the extremes.
        pool = [
            _pool_entry(f"ck_{r}", rating=r) for r in range(800, 1251, 50)
        ]
        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            my_rating=1000.0,
            strategy="elo_proximity",
            proximity_scale=50.0,
            rng_seed=123,
        )
        picks = Counter(
            provider.get_opponent(env_index=i).id for i in range(1500)
        )
        # The 1000-rated entry should dominate at this scale.
        top_id, _ = picks.most_common(1)[0]
        assert top_id == "ck_1000"

    def test_rejects_unknown_strategy(self) -> None:
        with pytest.raises(ValueError, match="strategy"):
            PFSPProvider(pool=[], rating_store=None, strategy="magic")


# ─── PFSPProvider — mirror + empty-pool safety ────────────────────────


class TestPFSPProviderMirror:
    def test_mirror_fires_deterministically_at_expected_period(self) -> None:
        pool = [_pool_entry(f"ck_{i}") for i in range(5)]
        mirror_calls = [0]

        def _mirror() -> _DummyOpponent:
            mirror_calls[0] += 1
            return _DummyOpponent(id="MIRROR")

        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="uniform",
            mirror_factory=_mirror,
            mirror_rate=0.10,  # period = 10
            rng_seed=0,
        )
        results = [provider.get_opponent(env_index=i).id for i in range(100)]
        # env_index 0, 10, 20, ... → mirror; 10 mirror calls in 100.
        mirror_picks = [i for i, r in enumerate(results) if r == "MIRROR"]
        assert mirror_picks == list(range(0, 100, 10))
        assert mirror_calls[0] == 10

    def test_empty_pool_falls_back_to_mirror(self) -> None:
        provider = PFSPProvider(
            pool=[],
            rating_store=None,
            mirror_factory=lambda: _DummyOpponent(id="MIRROR"),
            mirror_rate=0.0,  # disable periodic mirror
        )
        # Both env_index=0 and env_index=1 should reach the empty-pool
        # branch (pins the ordering: the empty-pool mirror fallback
        # must run after the periodic-mirror check is disabled).
        assert provider.get_opponent(env_index=0).id == "MIRROR"
        assert provider.get_opponent(env_index=1).id == "MIRROR"

    def test_empty_pool_without_mirror_raises(self) -> None:
        provider = PFSPProvider(pool=[], rating_store=None, mirror_rate=0.0)
        with pytest.raises(RuntimeError, match="pool is empty"):
            provider.get_opponent(env_index=0)


# ─── PFSPProvider — on_match_end forwarding ───────────────────────────


class TestPFSPProviderMatchEnd:
    def test_forwards_to_rating_store(self) -> None:
        store = _FakeRatingStore()
        pool = [_pool_entry("ck_a"), _pool_entry("ck_b")]
        provider = PFSPProvider(pool=pool, rating_store=store, rng_seed=0)

        opp = _DummyOpponent(id="ck_a")
        provider.on_match_end(
            env_index=0, opponent=opp, winner=1, score1=15, score2=11
        )

        assert store.recorded == [
            dict(opponent_id="ck_a", winner=1, score1=15, score2=11)
        ]

    def test_missing_store_is_noop(self) -> None:
        provider = PFSPProvider(pool=[_pool_entry("x")], rating_store=None)
        # Should not raise.
        provider.on_match_end(
            env_index=0,
            opponent=_DummyOpponent(id="x"),
            winner=2,
            score1=3,
            score2=15,
        )

    def test_opponent_without_id_is_silently_skipped(self) -> None:
        # Rule-based bot has no ``id`` — we don't want to record rating
        # updates against a placeholder key; silently drop.
        store = _FakeRatingStore()
        provider = PFSPProvider(pool=[], rating_store=store, mirror_rate=0.0)
        provider.on_match_end(
            env_index=0,
            opponent=RuleBasedBot(level=1),
            winner=1,
            score1=15,
            score2=0,
        )
        assert store.recorded == []

    def test_store_exception_never_propagates(self) -> None:
        # _AngryStore intentionally omits win_rate_against — the pool
        # is empty on this provider so _pfsp_weights is never called.
        # If a future copy of this double sees PFSP sampling run, the
        # missing method will raise AttributeError, which is the right
        # signal (vs. silently being swallowed).
        class _AngryStore:
            def record_match(self, **kwargs: Any) -> None:
                raise RuntimeError("mongo down")

        provider = PFSPProvider(pool=[], rating_store=_AngryStore(), mirror_rate=0.0)
        # Must not raise — training continues even with a broken store.
        provider.on_match_end(
            env_index=0,
            opponent=_DummyOpponent(id="ck_x"),
            winner=1,
            score1=15,
            score2=9,
        )


# ─── Base class contract ──────────────────────────────────────────────


class TestOpponentProviderBase:
    def test_base_get_opponent_raises_not_implemented(self) -> None:
        provider = OpponentProvider()
        with pytest.raises(NotImplementedError):
            provider.get_opponent(env_index=0)

    def test_base_on_match_end_is_noop(self) -> None:
        # Default hook must be a no-op so FixedBotProvider callers
        # don't need to care about rating semantics.
        provider = OpponentProvider()
        provider.on_match_end(
            env_index=0,
            opponent=RuleBasedBot(level=1),
            winner=1,
            score1=15,
            score2=0,
        )

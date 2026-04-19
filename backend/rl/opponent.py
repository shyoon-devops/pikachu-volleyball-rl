"""Opponent provider interfaces for the self-play league.

Each ``PikachuVolleyballEnv`` instance holds an ``OpponentProvider``;
``env.reset()`` asks the provider for a fresh opponent object on every
new match. The provider abstracts "who does player 2 play against?" so
the trainer can swap between the legacy rule-based ladder
(``FixedBotProvider``) and the PFSP-sampled league
(``PFSPProvider``) without any engine or env-step code change.

See ``docs/adr/0014-self-play-league.md`` for the end-to-end design.

The provider is deliberately I/O-free: it returns a ready-to-use
opponent object whose ``get_action(state, is_player2)`` signature
matches ``backend.game.bot.RuleBasedBot``. File loading, Elo tracking
and pool persistence are the concerns of the callable objects a
provider holds onto (e.g. a ``RatingStore`` passed into
``PFSPProvider``); the provider itself is a thin sampling strategy.
"""

from __future__ import annotations

import random
from typing import Any, Protocol, runtime_checkable

from backend.game.bot import BOT_PARAMS, RuleBasedBot


@runtime_checkable
class Opponent(Protocol):
    """Duck-typed opponent compatible with :class:`RuleBasedBot`.

    The env only calls ``get_action`` per frame — anything that honours
    this signature works whether it's a rule-based policy, an SB3
    snapshot, or a scripted replay.
    """

    def get_action(self, state: Any, *, is_player2: bool) -> Any: ...


class OpponentProvider:
    """Base class. ``get_opponent(env_index)`` returns an ``Opponent``.

    ``env_index`` lets providers stagger sampling across VecEnv workers
    (e.g. reserving slot 0 for a mirror match) without the env knowing
    which worker it is.
    """

    def get_opponent(self, env_index: int = 0) -> Opponent:
        raise NotImplementedError

    def on_match_end(
        self,
        env_index: int,
        opponent: Opponent,
        winner: int,
        score1: int,
        score2: int,
    ) -> None:
        """Optional hook for updating ratings after a match.

        Default implementation is a no-op so the legacy fixed-bot path
        doesn't need to care. The league subclass overrides to update
        Elo on the sampled opponent.
        """


class FixedBotProvider(OpponentProvider):
    """Legacy path: always returns a :class:`RuleBasedBot` of fixed level.

    This is the default for ``training_mode="bot_ladder"`` and the
    backward-compat shim when a caller passes ``bot_level=N`` without a
    provider. Construction is cheap so we return a fresh bot per match
    — matches the per-episode ``RuleBasedBot(level=...)`` pattern the
    env used pre-league.
    """

    def __init__(self, level: int = 1) -> None:
        if level not in BOT_PARAMS:
            raise ValueError(f"Level must be 1-5, got {level}")
        self.level = level

    def get_opponent(self, env_index: int = 0) -> Opponent:
        return RuleBasedBot(level=self.level)


class PFSPProvider(OpponentProvider):
    """League sampler using Prioritized Fictitious Self-Play (PFSP).

    ``pool`` is the list of candidate opponents; each entry must have
    ``id: str`` and ``rating: float`` attributes (or equivalent
    ``__getitem__`` access), plus a ``build()`` callable that
    materialises an :class:`Opponent`. The provider doesn't care how
    ``build()`` works — ``LoadedPolicyBot.from_checkpoint`` is the
    expected factory — keeping this file free of SB3 imports.

    Sampling strategies (``strategy`` arg):
        * ``"pfsp"`` — weight candidates by ``(1 - win_rate_vs_me)^p``,
          p default 2. AlphaStar default.
        * ``"uniform"`` — flat sampling across the pool. Fallback when
          pool has fewer than ``min_pool_for_pfsp`` (default 8)
          entries or when win-rate history is missing.
        * ``"elo_proximity"`` — weight by ``exp(-|rating - my_rating|/
          scale)``. Useful for anchored evaluation; default scale 200.

    ``mirror_rate`` fraction of ``get_opponent`` calls (keyed off
    ``env_index % mirror_period`` for determinism inside a VecEnv
    rollout) return ``mirror_factory()`` instead of a pool sample —
    keeps a self-consistency signal in the trainer per ADR §2.
    """

    def __init__(
        self,
        pool: list[Any],
        *,
        rating_store: Any,
        my_rating: float = 1000.0,
        strategy: str = "pfsp",
        pfsp_p: float = 2.0,
        proximity_scale: float = 200.0,
        min_pool_for_pfsp: int = 8,
        mirror_factory: Any = None,
        mirror_rate: float = 0.10,
        rng_seed: int | None = None,
    ) -> None:
        if strategy not in ("pfsp", "uniform", "elo_proximity"):
            raise ValueError(
                f"strategy must be one of pfsp/uniform/elo_proximity, "
                f"got {strategy!r}"
            )
        self.pool = list(pool)
        self.rating_store = rating_store
        self.my_rating = float(my_rating)
        self.strategy = strategy
        self.pfsp_p = float(pfsp_p)
        self.proximity_scale = float(proximity_scale)
        self.min_pool_for_pfsp = int(min_pool_for_pfsp)
        self.mirror_factory = mirror_factory
        self.mirror_rate = float(mirror_rate)
        self._rng = random.Random(rng_seed)

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def _pfsp_weights(self) -> list[float]:
        """Weight entry i by ``(1 - winrate_vs_me)^p``; floor 1e-3.

        ``winrate_vs_me`` comes from ``rating_store.win_rate_against(id)``
        — falling back to 0.5 when the store has no head-to-head
        history yet. p=2 (AlphaStar default) biases toward opponents we
        lose to more often without ever zeroing out stronger peers.
        """
        weights: list[float] = []
        for entry in self.pool:
            entry_id = _entry_id(entry)
            wr = 0.5
            if self.rating_store is not None and hasattr(
                self.rating_store, "win_rate_against"
            ):
                try:
                    wr = float(self.rating_store.win_rate_against(entry_id))
                except Exception:
                    wr = 0.5
            # Floor avoids a zero weight when we dominate an opponent so
            # the distribution keeps a small exploration tail.
            weights.append(max((1.0 - wr) ** self.pfsp_p, 1e-3))
        return weights

    def _proximity_weights(self) -> list[float]:
        weights: list[float] = []
        scale = max(self.proximity_scale, 1e-6)
        for entry in self.pool:
            rating = float(_entry_rating(entry))
            # exp(-|dr|/scale) peaks at my_rating and decays smoothly.
            weights.append(
                pow(2.718281828, -abs(rating - self.my_rating) / scale)
            )
        return weights

    def _pick_index(self) -> int:
        n = len(self.pool)
        if n == 0:
            raise IndexError("pool is empty — cannot sample opponent")
        use_uniform = (
            self.strategy == "uniform"
            or (self.strategy == "pfsp" and n < self.min_pool_for_pfsp)
        )
        if use_uniform:
            return self._rng.randrange(n)
        if self.strategy == "pfsp":
            weights = self._pfsp_weights()
        else:
            weights = self._proximity_weights()
        # random.choices with a population index — avoids importing numpy
        # here and keeps the provider dependency-light.
        (idx,) = self._rng.choices(range(n), weights=weights, k=1)
        return idx

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_opponent(self, env_index: int = 0) -> Opponent:
        # Mirror slot: env_index deterministically triggers a self-play
        # mirror match when mirror_rate > 0 and mirror_factory is set.
        # Using a stable hash of env_index keeps the selection
        # reproducible across rollouts.
        if self.mirror_factory is not None and self.mirror_rate > 0:
            period = max(1, int(round(1.0 / self.mirror_rate)))
            if env_index % period == 0:
                return self.mirror_factory()
        if not self.pool:
            # Empty pool is the first-ever training run — fall back to a
            # mirror if available, else raise so the trainer fails loudly
            # instead of silently training against nothing.
            if self.mirror_factory is not None:
                return self.mirror_factory()
            raise RuntimeError(
                "PFSPProvider pool is empty and no mirror_factory is set"
            )
        idx = self._pick_index()
        return _entry_build(self.pool[idx])

    def on_match_end(
        self,
        env_index: int,
        opponent: Opponent,
        winner: int,
        score1: int,
        score2: int,
    ) -> None:
        """Forward the match result to the rating store.

        The provider itself doesn't mutate ratings — that's the
        ``rating_store``'s job (typically an EloTracker the BE owns).
        We only forward the identity + outcome; the store handles
        K-factor, persistence, and broadcast scheduling.
        """
        if self.rating_store is None or not hasattr(
            self.rating_store, "record_match"
        ):
            return
        opponent_id = getattr(opponent, "id", None) or getattr(
            opponent, "checkpoint_id", None
        )
        if opponent_id is None:
            return
        try:
            self.rating_store.record_match(
                opponent_id=opponent_id,
                winner=winner,
                score1=score1,
                score2=score2,
            )
        except Exception:
            # Rating store failure must never wedge training — the
            # callback ships match results on a queue elsewhere, so a
            # missed update just shows up as a stale rating on the
            # dashboard one rollout later.
            return


# ── Pool entry accessors ───────────────────────────────────────────────
# Pool entries can be dicts (loaded from manifest.json) or dataclasses
# created by the rating store. These helpers accept either shape so the
# provider doesn't force one representation on the BE side.


def _entry_id(entry: Any) -> str:
    if hasattr(entry, "id"):
        return str(entry.id)
    return str(entry["id"])


def _entry_rating(entry: Any) -> float:
    if hasattr(entry, "rating"):
        return float(entry.rating)
    return float(entry.get("rating", 1000.0))


def _entry_build(entry: Any) -> Opponent:
    """Materialise an Opponent from a pool entry.

    Entry schemas supported:
      * object with ``build()`` method returning an Opponent directly
      * dict with ``"build"`` key (callable)
      * dict with ``"opponent"`` key (already-constructed Opponent)
    """
    if hasattr(entry, "build") and callable(entry.build):
        return entry.build()
    if isinstance(entry, dict):
        if "build" in entry and callable(entry["build"]):
            return entry["build"]()
        if "opponent" in entry:
            return entry["opponent"]
    raise TypeError(
        f"pool entry {entry!r} has no .build() method or "
        "'build'/'opponent' dict key"
    )

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

import logging
import math
import random
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend.game.bot import BOT_PARAMS, RuleBasedBot
from backend.game.engine import GameState, PlayerInput

logger = logging.getLogger(__name__)

# Default league-pool models directory, relative to the backend cwd.
# The manifest stores an experiment_id + step; the on-disk filename is
# either ``models/{experiment_id}/{step}.zip`` (v1 legacy format) or
# ``models/{experiment_id}/{slug}__{exp8}__{step}.zip`` (BE-T2 format).
# ``_resolve_checkpoint_path`` tries both.
DEFAULT_MODELS_BASE_DIR: str = "models"

# Anchor id → RuleBasedBot level mapping. ADR §5 anchors the rule-based
# ladder into the league at fixed Elo (L1=600, L3=900, L5=1200) so the
# sampler can include them without re-evaluating human-tuned bots.
_ANCHOR_LEVEL_BY_ID: dict[str, int] = {
    "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5,
}


@runtime_checkable
class Opponent(Protocol):
    """Duck-typed opponent compatible with :class:`RuleBasedBot`.

    The env only calls ``get_action`` per frame — anything that honours
    this signature works whether it's a rule-based policy, an SB3
    snapshot, or a scripted replay.
    """

    def get_action(
        self, state: GameState, *, is_player2: bool
    ) -> PlayerInput: ...


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
        models_base_dir: str | Path = DEFAULT_MODELS_BASE_DIR,
        max_build_retries: int = 5,
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
        self.models_base_dir = Path(models_base_dir)
        self.max_build_retries = int(max_build_retries)
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
                except (TypeError, ValueError) as exc:
                    # Surface misbehaving stores in the training log (a
                    # non-numeric return previously got silently cast to
                    # 0.5). Training continues with the fallback.
                    logger.warning(
                        "rating_store.win_rate_against(%s) returned "
                        "non-numeric value; falling back to 0.5 (%s)",
                        entry_id,
                        exc,
                    )
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
            weights.append(math.exp(-abs(rating - self.my_rating) / scale))
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
        # Build retry: a manifest entry can point at a deleted /
        # unmigrated checkpoint file. Skip those and resample so a
        # partially-broken pool doesn't crash the trainer. After
        # max_build_retries consecutive FileNotFoundError's, fall back
        # to mirror (if any) or re-raise the last error so the admin
        # is forced to fix the manifest.
        last_err: FileNotFoundError | None = None
        for _ in range(self.max_build_retries):
            idx = self._pick_index()
            try:
                return _entry_build(
                    self.pool[idx], models_base_dir=self.models_base_dir
                )
            except FileNotFoundError as exc:
                last_err = exc
                logger.warning(
                    "pool entry %s could not be built: %s — resampling",
                    _entry_id(self.pool[idx]),
                    exc,
                )
        if self.mirror_factory is not None:
            logger.warning(
                "max_build_retries exhausted; falling back to mirror"
            )
            return self.mirror_factory()
        # No mirror available — re-raise so training stops with a
        # clear signal rather than silently hanging.
        assert last_err is not None
        raise last_err

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
# Pool entries can be:
#   * BE's Pydantic ``LeagueCheckpoint`` model with fields
#     {id, elo, wins, losses, games, admitted_at, step,
#      experiment_id, source}. Primary production shape.
#   * dicts loaded from manifest.json (matches Pydantic fields 1:1).
#   * dataclasses / test doubles with .build() method or dict with
#     'build'/'opponent' keys — backward compat for the unit tests.
# All helpers below accept every shape so the provider doesn't force
# one representation on the BE side.


def _entry_id(entry: Any) -> str:
    if hasattr(entry, "id"):
        return str(entry.id)
    if isinstance(entry, dict) and "id" in entry:
        return str(entry["id"])
    raise AttributeError(f"pool entry {entry!r} has no 'id' field")


def _entry_rating(entry: Any) -> float:
    """Return the entry's Elo rating, preferring the Pydantic ``elo`` field.

    Attribute lookup order:
      1. ``entry.elo`` (BE Pydantic LeagueCheckpoint shape)
      2. ``entry.rating`` (legacy test-double shape)
      3. dict keys: ``"elo"`` then ``"rating"``
      4. default 1000.0
    """
    # Attribute access first — Pydantic models don't support dict ops.
    if hasattr(entry, "elo"):
        return float(entry.elo)
    if hasattr(entry, "rating"):
        return float(entry.rating)
    if isinstance(entry, dict):
        if "elo" in entry:
            return float(entry["elo"])
        if "rating" in entry:
            return float(entry["rating"])
    return 1000.0


def _entry_source(entry: Any) -> str | None:
    """Return the entry's ``source`` tag ('anchor' / 'v1_legacy' / 'new')."""
    if hasattr(entry, "source"):
        return str(entry.source) if entry.source is not None else None
    if isinstance(entry, dict) and "source" in entry:
        return str(entry["source"]) if entry["source"] is not None else None
    return None


def _entry_attr(entry: Any, name: str) -> Any:
    """Dict-or-attribute accessor for optional fields."""
    if hasattr(entry, name):
        return getattr(entry, name)
    if isinstance(entry, dict):
        return entry.get(name)
    return None


def _resolve_checkpoint_path(
    entry: Any, models_base_dir: Path
) -> Path:
    """Locate the .zip file for a league-pool entry.

    Tries both naming conventions produced by CheckpointCallback:
      * v1 legacy: ``models/{experiment_id}/{step}.zip``
      * BE-T2:     ``models/{experiment_id}/{slug}__{exp8}__{step}.zip``
        (we scan the dir with glob since slug isn't in the manifest)

    Raises :class:`FileNotFoundError` if neither layout resolves.
    """
    experiment_id = _entry_attr(entry, "experiment_id")
    step = _entry_attr(entry, "step")
    if experiment_id is None:
        raise FileNotFoundError(
            f"entry {entry!r} has no experiment_id — cannot resolve path"
        )
    exp_dir = Path(models_base_dir) / str(experiment_id)
    if not exp_dir.exists():
        raise FileNotFoundError(
            f"experiment dir {exp_dir} missing for entry "
            f"{_entry_id(entry)!r}"
        )
    if step is not None:
        # Legacy format first — shortest and fastest to stat.
        legacy = exp_dir / f"{step}.zip"
        if legacy.exists():
            return legacy
        # BE-T2 format — glob for any file ending in __{step}.zip.
        matches = sorted(exp_dir.glob(f"*__{step}.zip"))
        if matches:
            return matches[0]
    # Final fallback: final.zip (post-training export).
    final_zip = exp_dir / "final.zip"
    if final_zip.exists():
        return final_zip
    raise FileNotFoundError(
        f"no checkpoint file found for entry {_entry_id(entry)!r} "
        f"in {exp_dir} (tried {step}.zip, *__{step}.zip, final.zip)"
    )


def _entry_build(
    entry: Any, *, models_base_dir: Path | None = None
) -> Opponent:
    """Materialise an Opponent from a pool entry.

    Dispatch order:
      1. Test-double hatch: ``build()`` method → call directly.
      2. Dict with ``"build"`` callable → call it.
      3. Dict with pre-built ``"opponent"`` → return it.
      4. Production dispatch by ``source``:
         * ``"anchor"`` + id in L1..L5 → ``RuleBasedBot(level=...)``.
         * any other source (``"v1_legacy"``, ``"new"``, None) →
           ``LoadedPolicyBot(path, checkpoint_id=id, rating=elo)``.
    """
    # 1-3: back-compat for the existing unit tests.
    if hasattr(entry, "build") and callable(entry.build):
        return entry.build()
    if isinstance(entry, dict):
        if "build" in entry and callable(entry["build"]):
            return entry["build"]()
        if "opponent" in entry:
            return entry["opponent"]

    # 4: production dispatch.
    source = _entry_source(entry)
    entry_id = _entry_id(entry)
    if source == "anchor":
        level = _ANCHOR_LEVEL_BY_ID.get(entry_id)
        if level is None:
            raise ValueError(
                f"anchor entry id {entry_id!r} does not match "
                f"known L1..L5 — cannot build RuleBasedBot"
            )
        return RuleBasedBot(level=level)

    # Learned policy path. Import LoadedPolicyBot here (not at the top
    # of opponent.py) so modules that only need the Opponent protocol
    # don't pull in numpy + engine transitively at import time.
    from backend.rl.loaded_policy_bot import LoadedPolicyBot  # noqa: PLC0415

    base_dir = (
        models_base_dir
        if models_base_dir is not None
        else Path(DEFAULT_MODELS_BASE_DIR)
    )
    path = _resolve_checkpoint_path(entry, base_dir)
    return LoadedPolicyBot(
        model_path=path,
        checkpoint_id=entry_id,
        rating=_entry_rating(entry),
    )

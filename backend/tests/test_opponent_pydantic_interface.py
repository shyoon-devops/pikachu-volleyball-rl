"""Interface-compatibility tests for OpponentProvider ↔ BE Pydantic entries.

BE's league pool surfaces checkpoints as Pydantic ``LeagueCheckpoint``
models (not dicts). Pydantic models don't support the ``entry.get(...)``
dict access or the ``entry.build()`` method pattern the original
provider assumed, so a self-play run with a BE-populated manifest was
crashing with:

    AttributeError: 'LeagueCheckpoint' object has no attribute 'get'
    TypeError: pool entry ... has no .build() method or 'build'/'opponent' dict key

These tests pin the fixed provider against a Pydantic stand-in that
mirrors BE's real schema exactly (fields: id, elo, wins, losses, games,
admitted_at, step, experiment_id, source).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from backend.game.bot import RuleBasedBot
from backend.rl.loaded_policy_bot import LoadedPolicyBot
from backend.rl.opponent import (
    PFSPProvider,
    _entry_build,
    _entry_rating,
    _entry_source,
    _resolve_checkpoint_path,
)


# ─── BE-compatible Pydantic stand-in ──────────────────────────────────


class LeagueCheckpoint(BaseModel):
    """1:1 shape of the BE Pydantic model the production manifest yields."""

    id: str
    elo: float
    wins: int = 0
    losses: int = 0
    games: int = 0
    admitted_at: str = "2026-04-18T00:00:00Z"
    step: int | None = None
    experiment_id: str | None = None
    source: str = "new"


def _make_checkpoint_file(
    tmp_path: Path, experiment_id: str, step: int
) -> Path:
    """Create a stub .zip checkpoint file the path resolver can find."""
    exp_dir = tmp_path / experiment_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    # v1 legacy format: models/{experiment_id}/{step}.zip
    ck = exp_dir / f"{step}.zip"
    ck.write_bytes(b"")  # empty zip stub — LoadedPolicyBot loads lazily
    return ck


# ─── Accessors work on Pydantic ───────────────────────────────────────


class TestAccessorsOnPydantic:
    def test_entry_rating_reads_elo(self) -> None:
        entry = LeagueCheckpoint(id="280000", elo=1275.5, source="new")
        assert _entry_rating(entry) == 1275.5

    def test_entry_rating_fallback_for_missing_elo(self) -> None:
        # Pure dict with no elo key — falls through to default.
        assert _entry_rating({"id": "xxx"}) == 1000.0

    def test_entry_source_reads_pydantic_source(self) -> None:
        entry = LeagueCheckpoint(id="L3", elo=900.0, source="anchor")
        assert _entry_source(entry) == "anchor"

    def test_entry_source_missing_returns_none(self) -> None:
        assert _entry_source({"id": "xxx", "elo": 1000}) is None

    def test_entry_source_explicit_none_returns_none(self) -> None:
        # Distinct from "missing key" path: a dict that explicitly
        # sets source=None must still yield None so the dispatch in
        # _entry_build falls through to the learned-policy branch.
        assert _entry_source({"id": "xxx", "elo": 1000, "source": None}) is None


# ─── _entry_build: anchor dispatch ────────────────────────────────────


class TestAnchorBuild:
    @pytest.mark.parametrize("level_id,expected_level", [
        ("L1", 1), ("L2", 2), ("L3", 3), ("L4", 4), ("L5", 5),
    ])
    def test_anchor_id_builds_rulebased_bot(
        self, level_id: str, expected_level: int
    ) -> None:
        entry = LeagueCheckpoint(id=level_id, elo=900.0, source="anchor")
        opp = _entry_build(entry, models_base_dir=Path("/nonexistent"))
        assert isinstance(opp, RuleBasedBot)
        assert opp.level == expected_level

    def test_anchor_unknown_id_raises(self) -> None:
        entry = LeagueCheckpoint(id="L99", elo=500, source="anchor")
        with pytest.raises(ValueError, match="L1..L5"):
            _entry_build(entry, models_base_dir=Path("/nonexistent"))


# ─── _entry_build: LoadedPolicyBot dispatch ───────────────────────────


class TestLoadedPolicyBuild:
    def test_v1_legacy_source_builds_loaded_policy_bot(
        self, tmp_path: Path
    ) -> None:
        _make_checkpoint_file(tmp_path, "exp_legacy_abc", 280000)
        entry = LeagueCheckpoint(
            id="280000",
            elo=1320.0,
            step=280000,
            experiment_id="exp_legacy_abc",
            source="v1_legacy",
        )
        opp = _entry_build(entry, models_base_dir=tmp_path)
        assert isinstance(opp, LoadedPolicyBot)
        assert opp.checkpoint_id == "280000"
        assert opp.rating == 1320.0
        assert opp.model_path.name == "280000.zip"

    def test_new_source_builds_loaded_policy_bot(
        self, tmp_path: Path
    ) -> None:
        _make_checkpoint_file(tmp_path, "exp_new_def", 160000)
        entry = LeagueCheckpoint(
            id="160000",
            elo=1205.0,
            step=160000,
            experiment_id="exp_new_def",
            source="new",
        )
        opp = _entry_build(entry, models_base_dir=tmp_path)
        assert isinstance(opp, LoadedPolicyBot)
        assert opp.rating == 1205.0

    def test_be_t2_filename_format_resolved(self, tmp_path: Path) -> None:
        # BE-T2 format: {slug}__{exp8}__{step}.zip — glob should still
        # match even though the manifest only knows step + experiment_id.
        exp_dir = tmp_path / "exp_bet2_xyz"
        exp_dir.mkdir()
        (exp_dir / "my_run__exp_bet2__50000.zip").write_bytes(b"")
        entry = LeagueCheckpoint(
            id="50000", elo=1100.0, step=50000,
            experiment_id="exp_bet2_xyz", source="new",
        )
        path = _resolve_checkpoint_path(entry, tmp_path)
        assert path.name == "my_run__exp_bet2__50000.zip"

    def test_missing_file_raises_file_not_found(
        self, tmp_path: Path
    ) -> None:
        entry = LeagueCheckpoint(
            id="99999", elo=1000, step=99999,
            experiment_id="exp_missing", source="v1_legacy",
        )
        with pytest.raises(FileNotFoundError):
            _entry_build(entry, models_base_dir=tmp_path)

    def test_missing_experiment_id_raises(
        self, tmp_path: Path
    ) -> None:
        # Non-anchor source with experiment_id=None cannot resolve a
        # path; must raise loudly rather than silently fall through.
        entry = LeagueCheckpoint(
            id="orphan", elo=1000, step=50000,
            experiment_id=None, source="new",
        )
        with pytest.raises(FileNotFoundError, match="experiment_id"):
            _entry_build(entry, models_base_dir=tmp_path)

    def test_step_none_falls_back_to_final_zip(
        self, tmp_path: Path
    ) -> None:
        # A post-training export that stored only ``final.zip`` should
        # still resolve via the fallback at the end of the resolver.
        exp_dir = tmp_path / "exp_final"
        exp_dir.mkdir()
        (exp_dir / "final.zip").write_bytes(b"")
        entry = LeagueCheckpoint(
            id="export_1", elo=1150.0, step=None,
            experiment_id="exp_final", source="new",
        )
        opp = _entry_build(entry, models_base_dir=tmp_path)
        assert isinstance(opp, LoadedPolicyBot)
        assert opp.model_path.name == "final.zip"


class TestPathTraversalHardening:
    def test_experiment_id_escape_rejected(self, tmp_path: Path) -> None:
        # Even with a real file sitting in the escape target, the
        # resolver must refuse to look above models_base_dir. Prevents
        # a poisoned manifest from reading arbitrary files.
        escape_target = tmp_path.parent / "escape_target"
        escape_target.mkdir(exist_ok=True)
        (escape_target / "10.zip").write_bytes(b"")

        entry = LeagueCheckpoint(
            id="evil",
            elo=1000.0,
            step=10,
            experiment_id="../escape_target",
            source="new",
        )
        with pytest.raises(ValueError, match="escapes models dir"):
            _entry_build(entry, models_base_dir=tmp_path)


# ─── Provider end-to-end with Pydantic pool ───────────────────────────


class _RatingStore:
    def win_rate_against(self, opponent_id: str) -> float:
        # Return varying rates so PFSP has interesting signal.
        return {"L5": 0.2, "280000": 0.6, "160000": 0.4}.get(
            opponent_id, 0.5
        )

    def record_match(self, **kwargs: Any) -> None:
        pass


def _build_mixed_pool(tmp_path: Path) -> list[LeagueCheckpoint]:
    """A pool containing both anchor and learned checkpoints."""
    _make_checkpoint_file(tmp_path, "exp_a", 100000)
    _make_checkpoint_file(tmp_path, "exp_b", 280000)
    return [
        LeagueCheckpoint(id="L1", elo=600.0, source="anchor"),
        LeagueCheckpoint(id="L3", elo=900.0, source="anchor"),
        LeagueCheckpoint(id="L5", elo=1200.0, source="anchor"),
        LeagueCheckpoint(
            id="160000", elo=1150.0, step=100000,
            experiment_id="exp_a", source="v1_legacy",
        ),
        LeagueCheckpoint(
            id="280000", elo=1280.0, step=280000,
            experiment_id="exp_b", source="new",
        ),
    ]


class TestPFSPProviderWithPydanticPool:
    def test_uniform_strategy_builds_all_entries(
        self, tmp_path: Path
    ) -> None:
        pool = _build_mixed_pool(tmp_path)
        provider = PFSPProvider(
            pool=pool,
            rating_store=_RatingStore(),
            strategy="uniform",
            models_base_dir=tmp_path,
            rng_seed=0,
        )
        # Smoke: 20 samples must all build without crashing.
        seen_types: set[str] = set()
        for i in range(20):
            opp = provider.get_opponent(env_index=i)
            seen_types.add(type(opp).__name__)
        assert "RuleBasedBot" in seen_types
        assert "LoadedPolicyBot" in seen_types

    def test_pfsp_strategy_samples_without_crash(
        self, tmp_path: Path
    ) -> None:
        pool = _build_mixed_pool(tmp_path)
        provider = PFSPProvider(
            pool=pool,
            rating_store=_RatingStore(),
            strategy="pfsp",
            min_pool_for_pfsp=4,
            models_base_dir=tmp_path,
            rng_seed=42,
        )
        for i in range(20):
            opp = provider.get_opponent(env_index=i)
            assert hasattr(opp, "get_action")

    def test_elo_proximity_strategy_samples_without_crash(
        self, tmp_path: Path
    ) -> None:
        pool = _build_mixed_pool(tmp_path)
        provider = PFSPProvider(
            pool=pool,
            rating_store=_RatingStore(),
            my_rating=1200.0,
            strategy="elo_proximity",
            proximity_scale=200.0,
            models_base_dir=tmp_path,
            rng_seed=7,
        )
        for i in range(20):
            opp = provider.get_opponent(env_index=i)
            assert hasattr(opp, "get_action")


class TestBrokenEntryRetry:
    def test_missing_file_triggers_resample(self, tmp_path: Path) -> None:
        # Broken entry (missing file) + good entries. Provider must
        # silently skip the broken one and return a working opponent
        # instead of crashing. With the failed-index dedup now in
        # place, worst-case retry count equals pool size, so 2 is
        # sufficient (previously this needed >>pool size because the
        # stateless sampler could re-land on the broken entry).
        _make_checkpoint_file(tmp_path, "exp_good", 100000)
        pool = [
            LeagueCheckpoint(
                id="broken", elo=1500.0, step=99999,
                experiment_id="exp_missing", source="v1_legacy",
            ),
            LeagueCheckpoint(
                id="good", elo=1000.0, step=100000,
                experiment_id="exp_good", source="v1_legacy",
            ),
        ]
        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="uniform",
            models_base_dir=tmp_path,
            max_build_retries=2,  # = pool size; dedup guarantees coverage
            rng_seed=0,
        )
        for i in range(10):
            opp = provider.get_opponent(env_index=i)
            assert opp is not None

    def test_dedup_prevents_re_sampling_broken_entry(
        self, tmp_path: Path
    ) -> None:
        # Tighter guard on the dedup: with max_build_retries equal to
        # pool size and only one good entry, every call MUST land on
        # the good one because the broken index gets excluded after
        # its first FileNotFoundError. Without the dedup, the stateless
        # sampler could burn all retries on the broken entry on a bad
        # seed and fall through to mirror.
        _make_checkpoint_file(tmp_path, "exp_good", 100000)
        pool = [
            LeagueCheckpoint(
                id="broken", elo=1500.0, step=99999,
                experiment_id="exp_missing", source="v1_legacy",
            ),
            LeagueCheckpoint(
                id="good", elo=1000.0, step=100000,
                experiment_id="exp_good", source="v1_legacy",
            ),
        ]
        mirror_calls = [0]
        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="uniform",
            models_base_dir=tmp_path,
            max_build_retries=2,
            mirror_factory=lambda: (
                mirror_calls.__setitem__(0, mirror_calls[0] + 1)
                or RuleBasedBot(level=1)
            ),
            mirror_rate=0.0,
            rng_seed=0,
        )
        # 50 calls — every successful path must be the good entry.
        # Any mirror fallback here would indicate dedup broke.
        for i in range(50):
            opp = provider.get_opponent(env_index=i)
            assert isinstance(opp, LoadedPolicyBot)
            assert opp.checkpoint_id == "good"
        assert mirror_calls[0] == 0

    def test_all_broken_falls_back_to_mirror(
        self, tmp_path: Path
    ) -> None:
        pool = [
            LeagueCheckpoint(
                id=f"broken_{i}", elo=1000.0, step=99000 + i,
                experiment_id="exp_missing", source="v1_legacy",
            )
            for i in range(3)
        ]
        mirror_built = [0]

        def _mirror_factory() -> Any:
            mirror_built[0] += 1
            return RuleBasedBot(level=1)

        provider = PFSPProvider(
            pool=pool,
            rating_store=None,
            strategy="uniform",
            models_base_dir=tmp_path,
            mirror_factory=_mirror_factory,
            mirror_rate=0.0,  # disable periodic mirror
            max_build_retries=5,
            rng_seed=0,
        )
        opp = provider.get_opponent(env_index=1)
        assert isinstance(opp, RuleBasedBot)
        assert mirror_built[0] == 1

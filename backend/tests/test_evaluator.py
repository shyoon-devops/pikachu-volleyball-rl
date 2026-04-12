"""Tests for the model evaluation system."""

from __future__ import annotations

from pathlib import Path

import pytest
from stable_baselines3 import PPO

from backend.rl.env import PikachuVolleyballEnv
from backend.rl.evaluator import EvalResult, ModelEvaluator

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_PATH = str(MODEL_DIR / "test_random")


@pytest.fixture(scope="module", autouse=True)
def _ensure_test_model() -> None:
    """Create a random untrained model if it doesn't exist."""
    if not (MODEL_DIR / "test_random.zip").exists():
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        env = PikachuVolleyballEnv(bot_level=1)
        model = PPO("MlpPolicy", env, n_steps=64, batch_size=32, device="cpu")
        model.save(str(MODEL_DIR / "test_random"))
        env.close()


@pytest.fixture
def evaluator() -> ModelEvaluator:
    return ModelEvaluator()


class TestEvalResult:
    """EvalResult should have the correct structure and value ranges."""

    def test_eval_result_structure(self, evaluator: ModelEvaluator) -> None:
        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=3)

        assert isinstance(result, EvalResult)
        assert result.model_path == MODEL_PATH
        assert result.bot_level == 1
        assert result.n_games == 3
        assert isinstance(result.win_rate, float)
        assert isinstance(result.avg_score, float)
        assert isinstance(result.avg_opponent_score, float)
        assert isinstance(result.avg_rally_length, float)
        assert isinstance(result.avg_episode_length, float)
        assert isinstance(result.timestamp, str)

    def test_win_rate_in_range(self, evaluator: ModelEvaluator) -> None:
        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=5)
        assert 0.0 <= result.win_rate <= 1.0

    def test_scores_non_negative(self, evaluator: ModelEvaluator) -> None:
        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=3)
        assert result.avg_score >= 0.0
        assert result.avg_opponent_score >= 0.0

    def test_rally_length_non_negative(self, evaluator: ModelEvaluator) -> None:
        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=3)
        assert result.avg_rally_length >= 0.0

    def test_episode_length_positive(self, evaluator: ModelEvaluator) -> None:
        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=3)
        assert result.avg_episode_length > 0.0

    def test_timestamp_is_iso_format(self, evaluator: ModelEvaluator) -> None:
        from datetime import datetime

        result = evaluator.evaluate(MODEL_PATH, bot_level=1, n_games=3)
        # Should not raise
        datetime.fromisoformat(result.timestamp)


class TestEvaluateAllLevels:
    """evaluate_all_levels should return 5 results, one per bot level."""

    def test_returns_five_results(self, evaluator: ModelEvaluator) -> None:
        results = evaluator.evaluate_all_levels(MODEL_PATH, n_games=2)
        assert len(results) == 5

    def test_each_result_has_correct_level(self, evaluator: ModelEvaluator) -> None:
        results = evaluator.evaluate_all_levels(MODEL_PATH, n_games=2)
        for i, result in enumerate(results, start=1):
            assert result.bot_level == i


class TestCompareCheckpoints:
    """compare_checkpoints should return one result per model path."""

    def test_returns_correct_count(self, evaluator: ModelEvaluator) -> None:
        paths = [MODEL_PATH, MODEL_PATH]
        results = evaluator.compare_checkpoints(paths, bot_level=1, n_games=2)
        assert len(results) == len(paths)

    def test_each_result_has_correct_path(self, evaluator: ModelEvaluator) -> None:
        paths = [MODEL_PATH, MODEL_PATH]
        results = evaluator.compare_checkpoints(paths, bot_level=1, n_games=2)
        for path, result in zip(paths, results):
            assert result.model_path == path

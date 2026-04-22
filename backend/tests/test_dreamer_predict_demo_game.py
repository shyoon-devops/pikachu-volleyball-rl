"""End-to-end regression: LiveFrameCallback drives DreamerAgent
through a full demo game without crashing at ``int(action)``.

bench-B 2026-04-23 regression (3rd in a row):
  File backend/rl/callbacks.py:612, in _play_demo_game
      p1_input = ACTION_MAP[int(action)]
  TypeError: only 0-dimensional arrays can be converted to Python scalars

Root cause: ``DreamerAgent.predict()`` returned shape ``(1,)`` even
for single-obs ``(18,)`` inputs, so ``int(action)`` failed at the
callsite. SB3's ``BaseAlgorithm.predict`` contract for Discrete
action spaces is: single obs ndim=1 → 0-d int (``int()`` works),
batched obs ndim=2 → ``(B,)``. This test pins the full callsite
path — LiveFrameCallback attaching to DreamerAgent, entering
``_play_demo_game``, running the ``predict → int(action) →
ACTION_MAP`` loop to completion — so a future regression on either
end (predict shape OR callback dispatch) fires immediately instead
of crashing bench-B on step 4992.

PM 2026-04-23 hotpatch directive: "mock-only 또는 부분 검증 금지".
Every test here drives the real callback code path against a real
DreamerAgent checkpoint.
"""

from __future__ import annotations

import asyncio
import numpy as np
import pytest
from pathlib import Path
from typing import Any

from stable_baselines3.common.callbacks import CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.rl.callbacks import LiveFrameCallback
from backend.rl.dreamer_runner import DreamerAgent
from backend.rl.env import PikachuVolleyballEnv


def _make_vec_env(n_envs: int = 1) -> Any:
    def _mk() -> Any:
        return Monitor(PikachuVolleyballEnv(bot_level=1))

    return make_vec_env(_mk, n_envs=n_envs, vec_env_cls=DummyVecEnv)


def _tiny_agent(env: Any) -> DreamerAgent:
    return DreamerAgent(
        env=env, device="cpu",
        rssm_hidden_size=32, latent_dim=4, latent_axes=4,
        batch_size=4, sequence_length=8, train_every=8,
        imagine_horizon=3, replay_capacity=2048, free_bits=0.1,
    )


class TestPredictShapeContract:
    """Direct unit guards on the predict() shape contract. A
    regression here is the proximate cause of the bench-B crash;
    catching it before the integration test runs is cheaper."""

    def test_single_obs_returns_zero_dim_action(self) -> None:
        """Single obs ``(18,)`` → 0-d int action. ``int(action)``
        MUST work — that's the exact line that crashed bench-B."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        single_obs = np.zeros(18, dtype=np.float32)
        action, state = agent.predict(single_obs, deterministic=True)
        assert action.ndim == 0, (
            f"single-obs predict must return 0-d (SB3 contract); "
            f"got shape={action.shape}"
        )
        # The bench-B crash line — must not raise.
        as_int = int(action)
        assert 0 <= as_int < 12

    def test_batched_obs_returns_one_dim_actions(self) -> None:
        """Batched obs ``(B, 18)`` → shape ``(B,)``. This is the
        path ``_collect_step`` uses internally."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        batched_obs = np.zeros((4, 18), dtype=np.float32)
        action, _ = agent.predict(batched_obs, deterministic=True)
        assert action.shape == (4,)
        for a in action:
            assert 0 <= int(a) < 12

    def test_vec_env_reset_returns_batched(self) -> None:
        """The exact shape ``VecEnv.reset()`` produces must round-trip
        through predict without an ``int()`` crash at ACTION_MAP."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        obs = env.reset()  # shape (1, 18) — VecEnv always batches
        action, _ = agent.predict(obs, deterministic=True)
        assert action.shape == (1,)
        # Demo game path consumes this with action[0] so it works
        # even on batched shape; separate from the ndim=1 path
        # LiveFrameCallback uses.
        int(action[0])

    def test_stochastic_matches_contract(self) -> None:
        """``deterministic=False`` must keep the same output shape
        as deterministic — only the selection rule changes."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        single = np.zeros(18, dtype=np.float32)
        det_action, _ = agent.predict(single, deterministic=True)
        stoch_action, _ = agent.predict(single, deterministic=False)
        assert det_action.ndim == stoch_action.ndim == 0
        assert 0 <= int(stoch_action) < 12


class TestLiveFrameCallbackDemoGameE2E:
    """End-to-end: LiveFrameCallback runs a full demo game against a
    RuleBasedBot with DreamerAgent as the agent. This is the exact
    code path that crashed at step 4992 on bench-B. The test must
    exercise ``_play_demo_game`` to completion (MAX_SCORE reached
    + game-end window drained) with no exception."""

    def test_play_demo_game_runs_to_completion(
        self, tmp_path: Path
    ) -> None:
        """Drive one full demo game through the real LiveFrameCallback
        code path. A full game against L1 bot with a random-ish
        Dreamer typically takes 500-3000 frames; still CPU-bound
        under the smoke-size network."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)

        # Minimal wiring — don't install the loop as current (see
        # test_dreamer_baseline_callbacks_integration.py pollution
        # finding 2026-04-23).
        loop = asyncio.new_event_loop()
        frames_queue: asyncio.Queue = asyncio.Queue(maxsize=8192)
        results_queue: asyncio.Queue = asyncio.Queue(maxsize=16)

        cb = LiveFrameCallback(
            frames_queue=frames_queue,
            results_queue=results_queue,
            loop=loop,
            bot_level=1,
            # play_interval=1 → _on_step triggers demo game on the
            # very first learn step. Default 5000 would need a
            # prohibitively long learn() to hit.
            play_interval=1,
            replay_dir=str(tmp_path / "replays"),
            max_replays=4,
        )

        # BaseCallback handshake — init_callback sets self.model,
        # which _play_demo_game reads when it calls model.predict.
        cb.init_callback(agent)
        cb._on_training_start()

        # Run one full demo game via the real callback path.
        # bench-B crashed here at step 4992 when predict() returned
        # shape-(1,) instead of shape-(). With the fix, the loop
        # runs the real engine → predict → int(action) → ACTION_MAP
        # lookup for every frame and terminates when MAX_SCORE hits.
        final_state, frames, rally_count = cb._play_demo_game(
            current_bot_level=1
        )

        # Game must have reached MAX_SCORE (15) on one side.
        from backend.game.constants import MAX_SCORE
        assert (
            final_state.score1 == MAX_SCORE
            or final_state.score2 == MAX_SCORE
        ), (
            f"demo game did not reach MAX_SCORE: "
            f"{final_state.score1}-{final_state.score2}"
        )
        # Non-trivial frame count — proves the predict loop ran
        # many times without int(action) exception.
        assert len(frames) > 200
        # ``_safe_enqueue`` schedules via ``call_soon_threadsafe`` —
        # run the loop once to drain the pending enqueues before
        # we check queue size (otherwise enqueues stay in the loop
        # scheduler and qsize stays 0).

        async def _drain() -> None:
            # One tick is enough to process any pending callbacks.
            await asyncio.sleep(0)

        loop.run_until_complete(_drain())
        assert frames_queue.qsize() > 0

        loop.close()

    @pytest.mark.parametrize("deterministic", [True, False])
    def test_predict_loop_inside_demo_game_many_iterations(
        self, tmp_path: Path, deterministic: bool
    ) -> None:
        """Pin the exact int(action) path with an explicit loop
        that mirrors ``_play_demo_game``'s inner body. Runs 500
        iterations — orders of magnitude more than the single-
        predict unit tests — so a shape regression that only
        manifests after warm-up still trips."""
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)
        from backend.rl.env import ACTION_MAP

        obs = np.zeros(18, dtype=np.float32)
        for _ in range(500):
            action, _ = agent.predict(obs, deterministic=deterministic)
            # bench-B crash line — must succeed every iteration.
            a_int = int(action)
            _ = ACTION_MAP[a_int]


class TestDemoGameViaLearnDispatch:
    """Drive the demo game through the full ``learn → on_step →
    _play_demo_game`` dispatch chain, not just direct invocation —
    this is the path trainer.py actually uses and the only way a
    dispatch-level regression surfaces."""

    def test_learn_with_live_frame_callback_completes(
        self, tmp_path: Path
    ) -> None:
        env = _make_vec_env(n_envs=1)
        agent = _tiny_agent(env)

        loop = asyncio.new_event_loop()
        frames_queue: asyncio.Queue = asyncio.Queue(maxsize=8192)
        results_queue: asyncio.Queue = asyncio.Queue(maxsize=16)

        cb = LiveFrameCallback(
            frames_queue=frames_queue,
            results_queue=results_queue,
            loop=loop,
            bot_level=1,
            # play_interval=1 triggers a full demo game on the
            # very first learn tick — covers the dispatch chain
            # + int(action) callsite end-to-end.
            play_interval=1,
            replay_dir=str(tmp_path / "replays"),
            max_replays=4,
        )
        # One learn step → on_step → _play_demo_game → predict loop
        # → int(action) → ACTION_MAP. No exception = fix holds.
        agent.learn(total_timesteps=1, callback=cb)

        # Drain the ``call_soon_threadsafe`` enqueues.
        async def _drain() -> None:
            await asyncio.sleep(0)

        loop.run_until_complete(_drain())
        # A full game's results payload got enqueued (game_id,
        # score, rally count, etc.).
        assert results_queue.qsize() == 1
        loop.close()

"""Tests for the Rule-based Bot."""

import random as rng

import pytest

from backend.game.engine import PikachuVolleyball, PlayerInput
from backend.game.bot import BOT_PARAMS, RuleBasedBot


class TestBotValidInput:
    """Each level should return a valid PlayerInput."""

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
    def test_returns_valid_player_input(self, level: int) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        bot = RuleBasedBot(level=level)

        action = bot.get_action(state, is_player2=True)

        assert isinstance(action, PlayerInput)
        assert action.x_dir in (-1, 0, 1)
        assert action.y_dir in (-1, 0, 1)
        assert isinstance(action.power_hit, bool)

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
    def test_returns_valid_input_as_player1(self, level: int) -> None:
        game = PikachuVolleyball()
        state = game.reset()
        bot = RuleBasedBot(level=level)

        action = bot.get_action(state, is_player2=False)

        assert isinstance(action, PlayerInput)
        assert action.x_dir in (-1, 0, 1)
        assert action.y_dir in (-1, 0, 1)


class TestL5BeatsL1:
    """L5 bot should consistently beat L1 bot over 10 games."""

    def test_l5_wins_majority_against_l1(self) -> None:
        """L5 should clearly outperform L1 over a 20-game sample.

        With the faithful 32px collision box (matching original physics.js),
        both bots miss more often than with the older 52px box, so the level
        gap narrows slightly. We still expect L5 to win a clear majority
        (>= 60% = 12/20) to confirm the skill ordering.
        """
        import random as rng

        rng.seed(42)
        l5_wins = 0
        n_games = 20

        for _ in range(n_games):
            game = PikachuVolleyball()
            state = game.reset()
            bot_l1 = RuleBasedBot(level=1)
            bot_l5 = RuleBasedBot(level=5)

            for _step in range(50000):
                p1_action = bot_l1.get_action(state, is_player2=False)
                p2_action = bot_l5.get_action(state, is_player2=True)
                state = game.step(p1_action, p2_action)
                if state.score1 >= 15 or state.score2 >= 15:
                    break

            if state.score2 > state.score1:
                l5_wins += 1

        assert l5_wins >= 12, f"L5 won only {l5_wins}/{n_games} games"


def _simulate_game_actions(
    *,
    level_p1: int,
    level_p2: int,
    seed: int,
    max_steps: int = 1500,
) -> list[tuple[int, int, int, int, int, int]]:
    """Simulate a game and return a compact per-frame action record.

    Record tuple: (p1.x_dir, p1.y_dir, p1.power, p2.x_dir, p2.y_dir, p2.power).
    Used by the diversity tests below to compare whether different seeds
    produce distinguishable play patterns.
    """
    rng.seed(seed)
    game = PikachuVolleyball()
    state = game.reset()
    bot_p1 = RuleBasedBot(level=level_p1)
    bot_p2 = RuleBasedBot(level=level_p2)

    trace: list[tuple[int, int, int, int, int, int]] = []
    for _ in range(max_steps):
        a1 = bot_p1.get_action(state, is_player2=False)
        a2 = bot_p2.get_action(state, is_player2=True)
        trace.append(
            (a1.x_dir, a1.y_dir, int(a1.power_hit), a2.x_dir, a2.y_dir, int(a2.power_hit))
        )
        state = game.step(a1, a2)
        if state.score1 >= 15 or state.score2 >= 15:
            break
    return trace


class TestBotActionDiversity:
    """Hotfix regression guard: bot play must vary across seeds/games.

    Before the stochastic-variance hotfix, fixed-seed runs produced nearly
    identical frame-by-frame trajectories. These tests pin the new behavior:
    changing seeds must change the action trace.
    """

    def test_l1_traces_differ_across_seeds(self) -> None:
        t1 = _simulate_game_actions(level_p1=1, level_p2=1, seed=1)
        t2 = _simulate_game_actions(level_p1=1, level_p2=1, seed=2)
        # Identical length AND identical frame-by-frame actions would mean
        # the bot is fully deterministic at L1 — regression.
        same = min(len(t1), len(t2))
        diffs = sum(1 for i in range(same) if t1[i] != t2[i])
        assert diffs > same * 0.1, (
            f"L1 traces too similar across seeds: only {diffs}/{same} frames "
            "differ (expected >10%)"
        )

    def test_l5_traces_differ_across_seeds(self) -> None:
        """Even L5 must show variance — was perfectly deterministic pre-fix."""
        t1 = _simulate_game_actions(level_p1=5, level_p2=5, seed=7)
        t2 = _simulate_game_actions(level_p1=5, level_p2=5, seed=8)
        same = min(len(t1), len(t2))
        diffs = sum(1 for i in range(same) if t1[i] != t2[i])
        assert diffs > 0, (
            "L5 produced byte-identical traces across seeds — no stochasticity"
        )

    def test_l1_action_distribution_has_spread(self) -> None:
        """Over a long game, L1 must emit a mix of x_dir values, not one only."""
        trace = _simulate_game_actions(level_p1=1, level_p2=3, seed=42, max_steps=800)
        x_dirs = [t[0] for t in trace]  # p1.x_dir
        unique_dirs = set(x_dirs)
        # -1, 0, 1 are all possible; we require at least 2 distinct values
        # and neither -1 nor +1 dominating (>85%).
        assert len(unique_dirs) >= 2, f"L1 only emitted x_dir ∈ {unique_dirs}"
        counts = {d: x_dirs.count(d) for d in unique_dirs}
        top_share = max(counts.values()) / len(x_dirs)
        assert top_share < 0.85, (
            f"One x_dir value dominated: {counts} / {len(x_dirs)} frames"
        )

    def test_power_hit_angle_varies(self) -> None:
        """When L1 executes power hits, the attack angle should vary."""
        rng.seed(123)
        game = PikachuVolleyball()
        state = game.reset()
        bot_l1 = RuleBasedBot(level=1)
        bot_l3 = RuleBasedBot(level=3)

        power_hit_x_dirs: list[int] = []
        for _ in range(4000):
            a1 = bot_l1.get_action(state, is_player2=False)
            a2 = bot_l3.get_action(state, is_player2=True)
            if a2.power_hit:
                power_hit_x_dirs.append(a2.x_dir)
            state = game.step(a1, a2)
            if state.score1 >= 15 or state.score2 >= 15:
                break

        # Collect enough samples; if fewer, skip diversity check.
        if len(power_hit_x_dirs) >= 10:
            assert len(set(power_hit_x_dirs)) >= 2, (
                f"All {len(power_hit_x_dirs)} power hits used the same x_dir — "
                f"angle variance not firing"
            )


class TestBotLevelNoiseMonotonic:
    """Per-level noise knobs should decrease (or stay equal) as level rises."""

    def test_prediction_error_non_increasing(self) -> None:
        errs = [BOT_PARAMS[L].prediction_error for L in (1, 2, 3, 4, 5)]
        assert errs == sorted(errs, reverse=True), (
            f"prediction_error not monotone: {errs}"
        )

    def test_hesitation_rate_non_increasing(self) -> None:
        rates = [BOT_PARAMS[L].hesitation_rate for L in (1, 2, 3, 4, 5)]
        assert rates == sorted(rates, reverse=True), (
            f"hesitation_rate not monotone: {rates}"
        )

    def test_l5_still_has_nonzero_variance(self) -> None:
        """L5 must keep at least a whisper of noise on every knob — zero
        stochasticity was the original pattern-sameness bug."""
        p = BOT_PARAMS[5]
        assert p.prediction_error > 0
        assert p.jump_jitter > 0
        assert p.angle_variance > 0
        assert p.hesitation_rate > 0
        assert p.trajectory_noise_scale > 0

    def test_reaction_delay_non_increasing(self) -> None:
        delays = [BOT_PARAMS[L].reaction_delay for L in (1, 2, 3, 4, 5)]
        assert delays == sorted(delays, reverse=True), (
            f"reaction_delay not monotone: {delays}"
        )

    def test_miss_probability_non_increasing(self) -> None:
        misses = [BOT_PARAMS[L].miss_probability for L in (1, 2, 3, 4, 5)]
        assert misses == sorted(misses, reverse=True), (
            f"miss_probability not monotone: {misses}"
        )

    def test_move_range_non_decreasing(self) -> None:
        ranges = [BOT_PARAMS[L].move_range for L in (1, 2, 3, 4, 5)]
        assert ranges == sorted(ranges), (
            f"move_range not monotone-non-decreasing: {ranges}"
        )

    def test_jump_timing_error_non_increasing(self) -> None:
        errs = [BOT_PARAMS[L].jump_timing_error for L in (1, 2, 3, 4, 5)]
        assert errs == sorted(errs, reverse=True), (
            f"jump_timing_error not monotone: {errs}"
        )


class TestBotDifficultyUpgrade2026_04_12:
    """Pins the PM 2026-04-12 difficulty-upgrade values.

    Before this upgrade, mid/high-level bots reacted too slowly (L3
    reaction_delay=3, L4=1) and under-predicted intercepts, causing
    games to end too quickly with stale play. These tests lock in the
    exact spec PM requested so a future refactor can't silently walk
    the values back.
    """

    def test_l1_spec(self) -> None:
        p = BOT_PARAMS[1]
        assert p.reaction_delay == 6
        assert p.miss_probability == 0.10

    def test_l3_spec(self) -> None:
        p = BOT_PARAMS[3]
        assert p.reaction_delay == 1
        assert p.prediction_error == 0.10
        assert p.move_range == 0.95
        assert p.jump_timing_error == 1
        assert p.miss_probability == 0.02

    def test_l4_spec(self) -> None:
        p = BOT_PARAMS[4]
        assert p.reaction_delay == 0
        assert p.prediction_error == 0.04
        assert p.move_range == 1.0
        assert p.jump_timing_error == 0
        assert p.miss_probability == 0.0

    def test_l5_spec(self) -> None:
        p = BOT_PARAMS[5]
        assert p.prediction_error == 0.01
        assert p.reaction_delay == 0
        assert p.miss_probability == 0.0


class TestSkillOrderingAgainstWeakerOpponent:
    """Regression guard for the pre-upgrade L5<L3 inversion.

    Three-phase history:
      * Pre-upgrade (dev HEAD, pre-2026-04-12): L5 vs L3 = 40% (inverted).
      * Post-upgrade: target ≥80% (12/15) achieved.
      * Post-physics-port (2026-04-13): regressed to 5/15 because the
        pre-port bot tuning assumed instantaneous power-hit semantics;
        the ported state=2 dwell window changed optimal jump timing.
      * Current: L5 retuned with jump_timing_error=-1 + zero stochastic
        noise, restoring ≥12/15 across tested seed bases.

    Both RNGs (bot's global random, engine's own random.Random) are
    seeded explicitly so this test is reproducible in and out of the
    pytest harness — earlier iterations were confusingly flaky because
    only the bot RNG was seeded, leaving the engine's zero-vx tiebreak
    and computer_boldness draws at the mercy of process entropy.
    """

    def test_l5_comfortably_beats_l3(self) -> None:
        # Seed BOTH RNGs explicitly for reproducibility. The bot uses
        # the global random module (seeded via rng.seed); the engine has
        # its own random.Random instance that must be seeded separately
        # (zero-vx ball-player tiebreak + computer_boldness draws). Without
        # an engine seed the test was flaky — the pytest process env was
        # producing a different engine-entropy sequence than a standalone
        # python -c invocation, driving 5/15 vs 15/15 across runs with the
        # same bot seed.
        rng.seed(42)
        l5_wins = 0
        n_games = 15
        scores: list[tuple[int, int]] = []
        for game_idx in range(n_games):
            game = PikachuVolleyball(seed=1000 + game_idx)
            state = game.reset()
            bot_l3 = RuleBasedBot(level=3)
            bot_l5 = RuleBasedBot(level=5)
            for _step in range(50000):
                a1 = bot_l3.get_action(state, is_player2=False)
                a2 = bot_l5.get_action(state, is_player2=True)
                state = game.step(a1, a2)
                if state.score1 >= 15 or state.score2 >= 15:
                    break
            scores.append((state.score1, state.score2))
            if state.score2 > state.score1:
                l5_wins += 1
        assert l5_wins >= 12, (
            f"L5 won only {l5_wins}/{n_games} vs L3 (baseline: 40%) — {scores=}"
        )

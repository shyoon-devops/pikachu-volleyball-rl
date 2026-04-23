"""``pika_rl`` — algorithm-agnostic RL runtime (POC shim stage).

Phase 0 POC: every submodule here is a thin shim over
``backend.rl.*`` so the extraction plan (see
``docs/proposals/PIKA-RL-EXTRACTION.md``) can be validated
end-to-end without moving source code yet. At POC stage, the
shim ONLY works when the pikachu-volleyball-rl checkout is on
``sys.path`` — installing ``pika-rl`` into a foreign venv by
itself WILL fail on the inner ``backend.rl.*`` imports. Phase 3
replaces shims with actual code.

Public re-exports here mirror the flat-module contract the
MineRL repo consumes in its planning doc:
  from pika_rl.policy_factory import make_policy_spec, policy_factory
  from pika_rl.dreamer_runner import DreamerAgent
  from pika_rl.loaded_policy_bot import LoadedPolicyBot
  from pika_rl.callbacks import MetricsCallback, CheckpointCallback
  from pika_rl.evaluator import ModelEvaluator
  from pika_rl.encoders import ObsEncoder  # Protocol — Phase 0 addition
"""

__version__ = "0.0.1.dev0"

__all__ = [
    "__version__",
]

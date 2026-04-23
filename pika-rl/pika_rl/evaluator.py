"""Shim over ``backend.rl.evaluator``.

``ModelEvaluator.evaluate`` on v2.0.0 is Pika-specific (hardcodes
``PikachuVolleyballEnv``). Phase 2 will introduce an env-agnostic
``Evaluator`` protocol; the shim re-exports the current surface
for now so downstream repos can depend on the import path even
while the internals change.
"""

from backend.rl.evaluator import (  # noqa: F401 — re-export
    EvalResult,
    ModelEvaluator,
    compute_dominance_score,
)

__all__ = ["EvalResult", "ModelEvaluator", "compute_dominance_score"]

"""``pika-rl`` POC packaging.

Phase 0 extraction per docs/proposals/PIKA-RL-EXTRACTION.md §2.
This is a **shim-stage** setup.py: the ``pika_rl`` namespace
modules re-export symbols from the in-repo ``backend.rl.*`` tree
rather than bundling their own code. That makes the package
installable (``pip install -e pika-rl/``) but it is **only usable
from inside the pikachu-volleyball-rl checkout** until Phase 3
actually moves the source. See PIKA-RL-EXTRACTION.md §4 for the
phase plan.

Dependencies are intentionally scoped to what the re-exported
modules touch at import time. Runtime Python-level deps like the
Pika game engine (``backend.game.*``) are NOT listed here — those
follow in Phase 2 when we excise engine coupling.
"""

from setuptools import find_packages, setup

setup(
    name="pika-rl",
    version="0.0.1.dev0",
    description=(
        "Algorithm-agnostic RL runtime extracted from pikachu-volleyball-rl "
        "for reuse across MineRL Diamond and other downstream envs. POC "
        "shim stage — do not depend on this for production."
    ),
    author="Pika v2.x team",
    license="MIT",
    python_requires=">=3.11",
    packages=find_packages(include=["pika_rl", "pika_rl.*"]),
    install_requires=[
        "stable-baselines3>=2.3.0",
        "sb3-contrib>=2.3.0",
        "gymnasium>=0.29.0",
        "numpy>=1.26.0",
        "torch>=2.3.0",
    ],
    extras_require={
        "dev": ["pytest>=8.0.0"],
    },
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)

"""write_carousel node (ADR-039 P1). Shared writer body — see posts/node.py."""

from app.pipeline.derivative_dispatch import run_derivative_gen

run = run_derivative_gen

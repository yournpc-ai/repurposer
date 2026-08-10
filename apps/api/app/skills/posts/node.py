"""write_post node (ADR-039 P1). The four copy-writer kinds share one body —
``pipeline/derivative_dispatch.run_derivative_gen`` dispatches by node.kind;
this alias keeps the registry's dotted path package-local."""

from app.pipeline.derivative_dispatch import run_derivative_gen

run = run_derivative_gen

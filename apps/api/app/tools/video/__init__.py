"""tools/video — the paid production capability for Compositions (ADR-145).

Owns produce-side mechanics (version pin → spec compile → render queue).
Never owns work CONTENT — that is app/editing's seat. The ``produce_video``
run node (estimate / billing / two-phase execution digest) lands with
phase B; this batch carries only the minimal queue seam.
"""

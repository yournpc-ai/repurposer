"""WriteQuotesParams — compile-time adjudication document (see registry).

Extends the shared copy-writer params with the card count (the only writer
whose quantity is a real degree of freedom besides carousel).
"""

from pydantic import Field

from app.pipeline.derivative_dispatch import CopyWriterParams


class WriteQuotesParams(CopyWriterParams):
    count: int | None = Field(
        default=None,
        description="How many quote cards (e.g. '8 张金句卡' → 8). null = "
        "the default (3). Bounds are adjudicated against the node's "
        "count_limits at compile — never invent quantities.",
    )

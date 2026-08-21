"""WriteCarouselParams — compile-time adjudication document (see registry).

Extends the shared copy-writer params with the slide count. Carousel is only
proposed when the user explicitly asks for a carousel / slide deck /
swipeable post.
"""

from pydantic import Field

from app.pipeline.derivative_dispatch import CopyWriterParams


class WriteCarouselParams(CopyWriterParams):
    count: int | None = Field(
        default=None,
        description="How many slides (e.g. 'a 10-slide carousel' → 10). "
        "null = the default (6). Bounds are adjudicated against the node's "
        "count_limits at compile — never invent quantities.",
    )

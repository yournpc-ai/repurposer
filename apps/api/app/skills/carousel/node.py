"""write_carousel node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.skills.carousel.agents import carousel_writer


class WriteCarousel(DerivativeWriterNode):
    kind = "write_carousel"
    output_type = "carousel"
    slot_label = "Carousel"
    slot_ordinal = 3
    count_default = 6
    count_limits = (2, 15)
    writer = carousel_writer

"""write_carousel node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.tools.carousel.agents import carousel_writer


class WriteCarousel(DerivativeWriterNode):
    kind = "write_carousel"
    task_name = "Build carousel"
    task_name_zh = "制作轮播图"
    output_type = "carousel"
    slot_label = "Carousel"
    slot_label_zh = "轮播"
    count_default = 6
    count_limits = (2, 15)
    writer = carousel_writer
    completion_bounds = (300, 1500)  # count slides of slide copy

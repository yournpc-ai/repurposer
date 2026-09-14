"""write_carousel node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.tools.carousel.agents import carousel_writer


class WriteCarousel(DerivativeWriterNode):
    kind = "write_carousel"
    node_type = "image"  # 词表 v3 (ADR-076) — 轮图 (静帧族)
    prototype = "generator"  # 散文程序: 选图指令即程序
    task_name = "Build carousel"
    task_name_zh = "制作轮播图"
    output_type = "carousel"
    slot_label = "Carousel"
    slot_label_zh = "轮播"
    count_default = 6
    count_limits = (2, 15)
    writer = carousel_writer
    completion_bounds = (300, 1500)  # count slides of slide copy

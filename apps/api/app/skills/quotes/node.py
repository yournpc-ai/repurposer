"""write_quotes node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.skills.quotes.agents import quotes_writer


class WriteQuotes(DerivativeWriterNode):
    kind = "write_quotes"
    task_name = "Create quote cards"
    task_name_zh = "制作金句卡"
    output_type = "quotes"
    slot_label = "Quotes"
    slot_label_zh = "金句"
    count_default = 3
    count_limits = (1, 20)
    writer = quotes_writer
    completion_bounds = (100, 800)  # count cards of one-liners
    images_per_run = 1  # the quote-card image (first card only)

"""write_quotes node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.skills.quotes.agents import quotes_writer


class WriteQuotes(DerivativeWriterNode):
    kind = "write_quotes"
    output_type = "quotes"
    slot_label = "Quotes"
    slot_ordinal = 2
    count_default = 3
    count_limits = (1, 20)
    writer = quotes_writer

"""write_article node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.skills.article.agents import article_writer


class WriteArticle(DerivativeWriterNode):
    kind = "write_article"
    output_type = "article"
    slot_label = "Article"
    slot_ordinal = 4
    writer = article_writer
    completion_bounds = (800, 3000)  # a long-form article / newsletter

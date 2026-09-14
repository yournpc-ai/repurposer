"""write_article node (ADR-039 P2 objectified). Shared writer body lives in
``pipeline/derivative_dispatch.DerivativeWriterNode``."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.tools.article.agents import article_writer


class WriteArticle(DerivativeWriterNode):
    kind = "write_article"
    node_type = "text"  # 词表 v3 (ADR-076) — 散文档 (文章)
    prototype = "generator"  # 散文程序: PROMPT 区 = 用户原话
    task_name = "Write article"
    task_name_zh = "撰写文章"
    output_type = "article"
    slot_label = "Article"
    slot_label_zh = "文章"
    writer = article_writer
    completion_bounds = (800, 3000)  # a long-form article / newsletter

"""write_post node (ADR-039 P2 objectified). The four copy-writer nodes share
one body — ``pipeline/derivative_dispatch.DerivativeWriterNode``; this package
declares its own kind / output_type / writer agent."""

from app.pipeline.derivative_dispatch import DerivativeWriterNode
from app.skills.posts.agents import post_writer


class WritePost(DerivativeWriterNode):
    kind = "write_post"
    output_type = "post"
    slot_label = "Post"
    slot_label_zh = "帖子"
    slot_ordinal = 1
    writer = post_writer
    completion_bounds = (400, 1500)  # a long-form post (~800 words)

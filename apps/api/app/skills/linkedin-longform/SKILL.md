---
name: linkedin-longform
description: LinkedIn long-form post conventions — hook-led opening, clear body structure, speaker-intent fidelity, call-to-action close, 5–8 hashtags. Woven into the write_post tool's writer prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer write_post tool (post_writer agent prompt injection).
allowed-tools:
  - write_post
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - linkedin
    - longform
    - writing-conventions
---

## Task

Based on the following source texts and material understanding, write a social long-form post. Requirements:
- Start with a hook that captures the reader's attention
- Clear body structure, bullet points may be used
- Preserve the speaker's original intent and core insights
- End with a call to action or an open-ended question
- Tone matches the persona's style and voice
- 5–8 hashtags

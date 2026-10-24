# spike_tool_role_image — 原始判决记录（2026-10-21，两跑逐字转录）

> 脚本：`apps/api/scratch/spike_tool_role_image.py`（live 模式）。图片载荷从不入日志（只记字节数）；随机码词每跑随机，仅在像素中出现。

## 第一跑（INCONCLUSIVE → 归因为探针测量缺口）

code word: `BIRCH-7483`（5 HTTP / 7.9s）

```json
{"case": "C0_no_image_control", "iterations": 2, "calls": ["read_probe", "answer"], "code_word_found": false, "no_image_admitted": false, "prose_tail": "I'll call the read tool first."}
{"case": "C1_tool_role_image", "iterations": 2, "calls": ["read_probe", "answer"], "code_word_found": false, "no_image_admitted": false, "prose_tail": "I'll start by calling the read tool to look at the probe view."}
{"case": "C2_user_role_image", "code_word_found": false, "no_image_admitted": false, "prose_tail": ""}
```

usage: prompt 566+618+566+940+822=3512 / completion 26+203+33+131+129=522 / total 4,034；C1 迭代 2 载荷 30,435 bytes（含图，HTTP 200）。

**归因**：判读只读 prose 通道；模型把发现写进 answer 工具参数（content 通道为空——三跑一致）。非供应商错误、非 wire 问题。修复：answer 工具带 `findings` 字段 + 判读读双通道（`--selftest` 四腿与 `--dry` 复验绿后重跑）。

## 第二跑（POSITIVE — 选项 A 成立）

code word: 第二跑新随机词（同样只在像素；命中即证明读图）。

```json
{"case": "C0_no_image_control", "iterations": 2, "calls": ["read_probe", "answer"], "code_word_found": false, "no_image_admitted": true, "findings": "…no actual image payload attached. Since I cannot see any image, I cannot report a code word or a background color, and I will not guess at either…", "prose_tail": "I'll call the read tool first.\n\nThe tool result mentions a captured view but no image content was actually returned to me — I have no image to inspect."}
{"case": "C1_tool_role_image", "iterations": 2, "calls": ["read_probe", "answer"], "code_word_found": true, "no_image_admitted": false, "findings": "ground is navy blue, so the word and the actual background do not match.\n\nOther elements visible in the same image (for completeness): a solid red square in the upper-left area, the phrase \"seven ovals\" in yellow text in the lower-left, and seven white outlined ovals in a row across the lower-right.", "prose_tail": "I'll start by reading the probe view.\n\nThe probe returned an image. I can read the code word directly."}
{"case": "C2_user_role_image", "code_word_found": true, "no_image_admitted": false, "findings": "uare).\n\n(2) Background color: a dark navy / slate blue (approximately RGB (30, 58, 95), i.e. around hex #1E3A5F — a deep desaturated blue).\n\nOther content visible in the image: a red square at upper left, yellow text reading \"seven ovals\" at lower left, and seven white outlined ovals at lower right.", "prose_tail": ""}
```

usage: prompt 634+686+634+1002+835=3791 / completion 26+183+27+283+236=755 / total 4,546；C1 迭代 2 载荷 30,610 bytes（含图，HTTP 200）。

**判读**：C1 命中码词（`code_word_found: true`，码词只在像素）且 C0 不中（诚实承认无图）→ **MiniMax 接受并看见 role:tool 消息的图片 parts，选项 A 成立，fallback（选项 B synthetic user 消息）不启用**。C2 命中确认管道对照。

**附带观测（单一样本，见 README 的适用范围声明）**：C1 迭代 2 prompt 1,002 tokens vs C0 同迭代 686 tokens → 640×360 JPEG 约 +316 tokens——供应商按图像 token 化计费而非 base64 文本。

两跑合计：10 HTTP / 8,580 total tokens / 估算 ≈$0.004（minimax-m3 价目表口径）。

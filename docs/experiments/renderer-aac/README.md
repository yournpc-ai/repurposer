# 正式 Renderer 的 AAC 采样核验

[调查报告](REPORT.md) 对应 main 的 2f02da61。本目录保留原始实验记录，报告中的临时路径和 Git 状态均指取证当时。实际文件可从此处按相对路径读取。

- [测量表](metrics.json) 和 [播放时间轴](clock.json) 记录所有出口。[运行文件清单](run-files.json) 将每次留样的原始相对路径映射到已保存的相同字节，包括回退原件和 rename 失败留下的临时文件。只有内容摘要相同的样本才共用文件。
- [原始 MP4](run/success/raw.mp4)、[响度成功出口](run/success/video.mp4)、[保留前导元数据的对照](control.mp4) 与 [对齐输入的响度结果](aligned-normalized.mp4) 可直接比较。[子命令](commands.jsonl) 和 [返回日志](run.log) 保留了进程实际使用的路径与参数。
- [Audio Agent 原研究包](audio-study/REPORT.md) 保留配方、六份 WAV、同步样片、来源和原始清单。在 audio-study 内运行 `shasum -a 256 -c SHA256SUMS` 可核对原始包。此归档晚于调查报告 F 节的 Git 快照。

在本目录执行 `shasum -a 256 -c SHA256SUMS` 可核对整个证据包。诊断脚本的工作位置是独立实验目录。原实验从主仓该 SHA 复制 Renderer、共享 packages、已有 pnpm 依赖与浏览器到实验目录的 repo/，并从 ../mg-render/baseline/assets/ 复制 main.mp4、voice.wav、whoosh.wav 和 impact2.wav 到实验目录的 assets/。驱动依赖的版本与环境见报告 A 节。launch.sh 等入口要求显式设置 LAB。重测会生成同名媒体和日志，应在新的临时副本内执行。

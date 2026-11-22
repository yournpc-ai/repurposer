# Repurposer 渲染路线评审材料

本目录包含两次隔离实验，基线提交为 `4d0113474101b65c9a8d9e53d47879c6e8010c91`。所有评审链接均相对于目录。推送后可以直接从仓库浏览报告、代码、逐帧数据和原始记录，下载 MP4 后即可播放。

| 评审问题 | 从这里开始 | 直接证据 |
|---|---|---|
| A→B 去烘焙、B→C 去 Remotion 各省多少？ | [上轮 A/B/C 报告](baseline/REPORT.md) | [27 次结果摘要](baseline/analysis/repeat.json) · [原始计时](baseline/logs/bench.jsonl) · [统一编码器对照](baseline/analysis/encoder-control.json) |
| C 能否对实际 PiP 使用 React 动态柔边遮罩？ | [本轮 B/C 边界报告](boundary/REPORT.md) | [共享组件](boundary/src/Boundary.tsx) · [B 场景](boundary/src/scene.tsx) · [C 合成](boundary/src/c.py) · [解码帧横向对照](boundary/evidence/comparison-072.png) |
| 看最终作品和身份 | [旧清单](baseline/manifest.json) · [新清单](boundary/evidence/manifest.json) | 旧版 [A](baseline/final/A-v3-r1.mp4) / [B](baseline/final/B-v3-r1.mp4) / [C](baseline/final/C-v3-r1.mp4) · 跨层遮罩 [B](boundary/evidence/B-m4a.mp4) / [C](boundary/evidence/C.mp4) |
| 预览究竟取了哪一帧？ | [滑杆截图与离线出帧比较](boundary/evidence/preview-comparison.json) | [PiP 源帧 CSV](boundary/evidence/pip-source-ids.csv) · [所有输出帧及局部误差](boundary/evidence/frame-regions.csv) |
| 为什么 A/B 晚 2,048 个采样？ | [逐阶段解码](boundary/evidence/audio-stages.json) | [原始失败成片](boundary/evidence/B-adts.mp4) · [历史 A/B 包载荷交叉核验](boundary/evidence/baseline-crosscheck.json) · [实际编码和拼接命令](boundary/evidence/m4a/commands.jsonl) |

## 交付范围

上轮保留完整实验源码、锁、固定输入、V3 三路代表成片、A/B 原始偏移成片、27 个运行回执与最终摘要、解码音频、关键帧和中断恢复记录。原实验包的清单仍标有所有历史路径。为控制仓库体积，重复成片、其他版本中间 MP4 和恢复时暂存的媒体可用复现命令重建。本目录的校验依据是 [SHA256SUMS](SHA256SUMS)，历史归档全量清单另存为 [ORIGINAL-SHA256SUMS](baseline/ORIGINAL-SHA256SUMS)。上轮复现入口、仓库定位和 bake 导入改为可随 checkout 移动；机器路径仍保留在历史原始日志中，以便追溯。

本轮包含 V4、两个可播放的交付成片、原始偏移 B、相同编码器对照、实际中间 WAV/AAC、预览播放片段、对照图、原始日志与从源重算的脚本。均为实验目录内的证据。数据库、正式导出、发布、费用、租约与停止流程没有进入本轮执行范围。

## 校验和复现

在仓库根目录执行校验，无需安装渲染依赖。

```sh
(cd docs/experiments/mg-render && shasum -a 256 -c SHA256SUMS)
```

本轮整套复现在新的临时目录完成。已实测环境为 macOS Apple Silicon，使用原提交已准备好的 apps/api/.venv、pnpm 仓库依赖、apps/render 的 Remotion chrome-headless-shell、固定系统 Arial Bold。实验自己的 Node 模块由 package-lock 和 npm ci 在临时目录安装。环境版本和二进制摘要见两份 manifest。若复用已安装且与实验锁一致的模块，可设置 ABC_MODULES 为其绝对路径。新工作目录会打印在终端。

```sh
bash docs/experiments/mg-render/boundary/run.sh
```

若需亲自拖动滑杆，在上一步打印的工作目录执行以下命令，然后打开终端给出的本机 URL。C 页面还可以播放独立生成的一秒音视频区间。Ctrl-C 结束服务。

```sh
source ./env.sh
"$PY" src/serve.py
```

上轮 A/B/C 全套回放另有入口，运行后会重做 27 次完整输出及诊断。

```sh
bash docs/experiments/mg-render/baseline/commands/reproduce.sh
```

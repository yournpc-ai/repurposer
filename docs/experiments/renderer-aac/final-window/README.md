# Loudnorm 成品替换前的有效播放窗口

macOS 正负对照通过。候选复用响度前已有的 ffprobe 流探测，在 `fs.rename(tmpPath, videoPath)` 之前检查成品的音轨、48 kHz 采样率、1/48000 时基、零起点和整数 duration_ts。期望采样数仍来自 Composition。原基线时钟错误仍由 InvalidAudioClock 中止；成品时钟错误进入已有的响度异常回退，由 renderVideo 发布通过检查的基线并清理工作目录。每个成功编码的响度成品新增一次元数据探测，没有新增解码或编码。

|24 fps、191 帧|movie timescale|音频 edit 长度 / 起始 media time|ffprobe duration_ts|解码返回采样|交付|
|---|---:|---|---:|---:|---|
|正确响度成品|48000|382000 / 1024|382000|382976|成品通过检查并替换基线|
|归档短窗成品|1000|7958 / 1024|381984|382976|替换被阻止，返回基线的原始字节|

两个对照均为零起点、1/48000 音轨时基。音频 edit 长度以 movie timescale 为单位，media time 以 48 kHz 为单位。FFprobe n7.1 读取到的轨长分别等于 edit 的精确呈现长度。两例实际返回的文件均为 382000 有效采样、191 帧。结果目录均只剩 video.mp4。

两次都用同一份 24 fps boundary.json、固定媒体、pnpm 10.20.0 frozen 安装及已缓存的锁定 Chromium，从正式 renderVideo 入口执行。正例真实编码出的临时文件与归档正例逐字节一致。负例在相同临时文件生成后、正式 ffprobe 启动前替入归档负例。隔离驱动 observe.cjs 留下实际探测命令、受测字节摘要及成功 rename 的回执。两次均运行真实探测进程及 Renderer 原有 catch/finally。整个实验仅对这件作品做正负对照。通过驱动时使用 pnpm 安装的 tsx 启动器，其 NODE_PATH 可解析原生 compositor 包。

- [探测结果与包结构](boxes.json) · [正例流元数据](24-loudnorm.probe.json) · [负例流元数据](24-default-timescale.probe.json)
- [最终文件身份](results.json) · [正例替换](positive.jsonl) · [负例回退](negative.jsonl) · [实际回退日志](negative.log)
- [完整未提交候选 diff](candidate.diff) 相对于 ec02b02d，已在基线副本应用并与工作树逐文件比对。相对上次候选只调整 audio.ts 的成品守卫、artifacts.ts 常量的测试可见性和 artifacts.test.ts 的一致性断言。
- Renderer 类型检查通过。缓存使用的 SHA 与 pnpm-lock 中 @remotion/renderer@4.0.484 快照的 patch_hash 完全一致。仅运行新增的定向测试；在临时副本改动 SHA 后测试按预期失败。[一致时通过](hash-test.log) · [漂移时失败](hash-drift.log)

Linux 24/25/30 fps 与 Renderer/Web 两个 Docker 镜像继续 BLOCKED；本轮未操作 Docker。真实 Chat-Origin 五面待验。生产候选保持未提交。

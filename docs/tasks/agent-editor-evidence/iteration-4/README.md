# Iteration 4 实测

## 4A

基线 32f04518。隔离库 rep_editor_i4_1121 复制自上一轮验收库，独立 S3 测试桶 editor-i4，原开发服务继续运行。Chrome 1360×900 与 390×844 通过真实 Home 发送，两端各运行一次纯文本与一次 2477261 字节 MP4。四个项目各有一次 POST /chat。见 home.json 的项目、POST 请求、流帧、持久 opening ID 和刷新后从 Projects 重开的正文。home-wire.json.gz 保留每轮声明、输入和原生响应。模型在部分中文请求中回复韩语。手机图片来自已上传真实文件的页面。

opening-recovery.json 记录同时首发、Stop 撤回后的重放、延迟历史 503 后手动重新加载、重新登录后保留草稿。登录使用正式验证码生成和校验，邮件服务在本机接收验收邮件。桌面系统浅色、手机系统深色。未将浏览器注入会话用于验证邮件投递。

消费者核对：原 projects.$id.index 是唯一 ProjectHeader 使用者，已迁到 _app 父级并保留 ProjectMenu。RecipeShelf、RecipeTabs 和 recipeFamilies 的 import 只有旧首页与货架内部，已连同滚动计算、停靠样式删除。HomeComposer 和项目消息归档、Stream、Question、播放器保留。首发用项目作用域的持久 opening 与消息序号核对，序号跨零可见撤回保留。

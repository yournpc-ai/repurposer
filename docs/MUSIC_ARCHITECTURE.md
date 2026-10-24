# Repurposer Music Architecture

> Status: 当前规范（2026-10-25）。音乐库、默认选曲、persona 面板自定义生成与 clip 换曲是当前能力；上传、配额/缓存、Chat 自定义生成和高级音频编辑仍未完成。
> Related: ADR-023；字段级事实源为当前 models、routes 与 `app/tools/music/`。

## 1. 范围与命名

音乐系统由 **`Music` 表 + 对象存储 `music/` 前缀 + clip-spec 音乐块**组成。一条 Music 是库中的一首背景乐，不是视频时间线上的一条自由音轨。

默认使用平台生成/策展音乐，减少静态磁盘 mood 文件与不明版权素材的依赖。AI 生成并不自动等于可商用，provider 条款仍是独立上线条件（§10）。

## 2. 当前能力与非目标

当前能力：

1. 平台默认曲目、用户生成曲目和公开/自有库查询；
2. persona 皮肤的音乐默认与启用开关；
3. clip 生成时从现有库选曲，不在每次 clip 生成中自动创作新音乐；
4. persona 皮肤 Music 面板试听、选默认和从 prompt 生成新曲；
5. `set_music` 换曲/开关/增益并重渲染；Chat `add_music` 确定性选择现有库曲目；
6. `POST /api/v1/music/generate` 直接生成一条新 Music。

当前不做：

- 用户上传音乐；
- 多轨音频时间线、自由增益自动化、起止裁剪或淡入淡出编辑器；
- 在 Chat 或 result editor 中“Generate new”自定义音乐；
- prompt 去重缓存、生成配额或该路由的 credits 收费；
- 未经明确授权把私有用户音乐公开。

## 3. 当前架构

```text
Music Library（music 表 + music/ 对象）
  ├─ 平台默认：启动 reconcile 只补记录，不在启动时调用模型
  └─ 用户显式生成：persona Music 面板 → POST /music/generate（inline）
                         │
                         ▼
persona.brand 默认（musicEnabled / musicId / musicMood / musicGainDb）
                         │
                         ▼
clip 计划 / add_music 从现有库选曲
                         │
                         ▼
outputs.render_spec.music（url / enabled / gain_db / music_id）
                         │
                         ▼
renderer 只消费 spec；换曲通过 set_music → render PENDING → worker
```

`add_music` 是库选择技能，不是音乐生成技能。 Film 的音乐与旁白有其自身 spec/版本合同，不得借本模块把 Film 变成自由多轨音频编辑器。

## 4. 数据归属

| 数据 | 事实源 | 规则 |
|---|---|---|
| 音频字节 | 对象存储 `music/{music_id}.{ext}` | DB 只存 key；reset 保留 `music/` 前缀 |
| Music 元数据 | `music` 表 | mood、prompt、license、duration、attribution、visibility 等按当前 schema |
| 默认音乐 | `persona.brand` + 系统默认皮肤 | `musicId` 为显式选择，`musicMood` 为回退；`musicEnabled` 是总开关 |
| 单个 clip 选择 | `outputs.render_spec.music` | 渲染运行时事实；renderer 不读 Music 表 |

三种数据形态：

- **平台默认**：`generated_by_user_id=NULL`、`is_public=TRUE`。
- **用户生成**：`generated_by_user_id=<user>`；当前新建行默认 `is_public=TRUE`，进入共享库。
- **未来上传**：必须默认私有；显式分享、权利证明和审核未完成前不得沿用用户生成曲的公开默认。

当前“用户生成即公开”是数据行为，不等于已经具备完整的公开库审核与告知体验。公开库 moderation、撤下与用户可见告知仍是开放事项。

## 5. 默认库与启动对账

默认 catalog 当前按 `calm` / `uplifting` / `corporate` 三种 mood 组织，具体行、标题与对象 key 以 seed 注册表和数据库为准。

- `app/pipeline/music.py:seed_default_music` 在应用启动时 reconcile：按 mood 查缺，对象存在而记录缺失时补记录。
- 启动 reconcile **不调用 MiniMax、不生成音频、不花配额**；对象不存在时保持缺失并诚实跳过。
- 一次性生成/上传由 `apps/api/scripts/seed_default_music.py` 承担，需独立授权与配额。
- reset_db 保留 `music/` 对象前缀，清库后重启只重建可对应记录。

## 6. 选曲与 spec

1. persona 的 `brand` 合并系统默认后得到音乐默认。
2. clip 计划可依据品牌默认与内容 mood 选择现有 Music；Chat `add_music` 确定性选择已有曲目，不隐式调用生成端点。
3. `app/memory/brand.py` 与当前烘焙链把 Music 解析为 `ClipMusic`，写入 `render_spec.music`。
4. renderer 只消费 `url / enabled / gain_db / music_id` 等 spec 字段，不知道 Music、mood 或 persona 的存在。

```ts
interface ClipMusic {
  music_id: string | null
  url: string | null
  enabled: boolean
  gain_db: number
}
```

trim/start/end、自动增益与多曲混音不在当前契约中；新增前必须同时评审 clip-spec、libass/FFmpeg 替身成本和 L3 边界。

## 7. 自定义生成

`POST /api/v1/music/generate` 的当前行为：

- 唯一已核实的 Web 调用面是 persona 皮肤编辑器的 Music 面板；
- 请求处理器直接 await provider 生成并上传，随后插入一个新 UUID 的 Music 行；不经过 worker；
- 每次请求走当前生成路径，**没有 prompt 去重/cache 命中承诺**；
- 当前路由没有项目级生成配额或 credits 守卫，不能在 UI/文档中称其已按套餐收费或限量；
- 新行默认公开，权限、条款和公开告知必须与该行为一起验收。

它是 `MODULE_ARCHITECTURE.md` §5 已登记的 request-inline 例外，不是新重活绕开队列的通用先例。若生成时长、重试或成本控制要求改变，应先迁入队列并设计配额/授权，而不是增加隐藏轮询。

## 8. 精修与 UI

- `set_music` 负责换曲、开关和增益；journal/undo 与重渲染按 Operation Model 和 render fencing 执行。
- Chat `add_music` 只选择现有库；用户要求创作新曲时，应导向当前 persona Music 面板或明确回答能力边界，不能假装 Chat 已生成。
- persona Music 面板提供公开 + 自己曲目的列表、试听、默认选择与 prompt 生成。
- result editor 的当前换曲能力不等于有“Generate new”按钮；独立 `/library/music` 全库管理页仍属后续。

## 9. 用户上传（PLANNED）

重启上传前必须具备：

1. 明确权利声明并持久化到上传记录；
2. ToS 中用户责任、平台撤下权与投诉流程；
3. 默认 `is_public=FALSE`，公开分享需要显式 opt-in 与平台审核；
4. 文件类型、大小、存储、租户隔离与审计限制；
5. DMCA/当地法适用的投诉、删除和争议流程；
6. 法务评估“平台把上传音乐合成进衍生视频”是否影响 safe harbor。

未满足这些条件时，不得仅复用普通 Asset 上传就开放音乐库。

## 10. 版权与公开库

**仍需核实 provider 当前条款**：商业使用、再分发/平台托管、输出权属、终端用户视频分发、是否要求署名。文档中的“AI 生成默认更安全”不是法律结论。

条款不足时的回退顺序：换有明确商业许可的 provider、委托并取得原创音乐权利，或关闭音乐能力。不得用技术生成事实替代授权。

公开库还需决定：

- 谁审核用户生成公开曲、如何处理投诉与撤下；
- 是否允许艺术家署名或收益分配（未拍板，不是当前承诺）；
- 自定义生成的配额、付费和公平使用模型；
- 是否做 prompt/内容缓存，以及缓存键、跨用户共享和隐私边界。

## 11. 质量与验收

- 默认库 reconcile 必须离线可启动，缺失对象不触发隐式生成。
- 选曲、换曲、开关与增益在 preview/export 一致；离屏播放与全局声音互斥遵守 UI 合同。
- 自定义生成分别验证 provider 成功、上传、DB 行、权限、公开默认、失败与重复点击；当前没有缓存/配额时不得写对应通过结论。
- 音乐特定的感知质量、响度、循环自然度和与旁白/人声的动态混音仍需真实试听；通用 verify 或文件存在不等于音乐质量通过。
- 高级音频编辑、用户上传和公开库运营在各自合同完成前保持 PLANNED。

## 12. 相关文档

- `DECISIONS.md` ADR-023：音乐库决策。
- `RENDERING.md` / `VIDEO_EDITOR.md`：spec 与编辑边界。
- `MODULE_ARCHITECTURE.md`：表归属、inline 例外与队列规则。
- `BILLING.md`：若未来给自定义生成计费，必须接入同一报价、授权与台账体系。

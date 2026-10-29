# AI 伙伴（麦麦）— 部署笔记

**最后更新：2026-10-29 00:55** — 唱歌曲库批量上线（网易云 .ncm 解密 + 批量翻唱，30+ 首）；片段改成「乐句结尾自然收尾」。

## 🎤 唱歌能力（已上线，10/28–29）

**结论先说**：GPT-SoVITS 是克隆音色、RVC 是换音色的变声器，**两者本身都不会产生旋律**（GSV 的音高由文本推、RVC 原样保留输入音高）。要真唱必须有一条「已经唱好的干声」，所以走的是社区通用做法：**原曲 → UVR5 分离人声 → RVC 换成派蒙音色**。

### 流水线（脚本都在 `D:\code2\AI伙伴\tools\sing\`）
| 脚本 | 作用 |
|---|---|
| `decrypt_ncm.py` | 批量解密网易云 `.ncm` → `E:\ai-voice\songs\decoded`（用 PyPI `ncmdump`） |
| `fix_ext.py` | 解密产物没有扩展名，按文件头补 `.mp3/.flac` |
| `batch_cover.py <数量> [index文件] [起始偏移]` | 批量翻唱：UVR5 分离 → 测人声中位音高自动定变调 → RVC → 自然剪辑 → 入库 |
| `make_song.py <原曲> <歌名> [起始秒] [时长秒] [变调]` | 单曲手动处理 |
| `sing_cut.py` | 剪辑核心 `cut_natural()`：攒到 42s 后吸附到**乐句结尾**（静音间隙）+150ms 淡出 |
| `merge_index.py` | 并行 worker 的 `index_b.json` 每 45s 合并进主 `index.json` |
| `run_a.cmd` / `run_b.cmd` | 两个并行 worker 的启动壳（**必须 GBK 编码**，UTF-8 会让 cmd 认不出中文路径） |

- 变调自动判定：人声中位 f0 ≥240Hz → 0（女声/童声）；190–240 → +6；<190 → +12（男声升八度）
- 长歌只分离**前 85 秒**（成品只要 42 秒），耗时减半
- 两个 venv 不能混用：`sep-venv`（audio-separator + onnxruntime，做分离）/ `venv`（torch + RVC，做变声）
- 曲库：`E:\ai-voice\sing\cache\*.wav` + `index.json`（歌名/别名/文件/时长）

### 插件与人格
- `maimai-voice` 的 `sing(song="")`：命中歌名唱那首；**没命中会返回完整歌单**（所以她能如实回答"我会唱什么"）；留空随机；冷却 `sing_cooldown_seconds=180`
- 曲库每次调用现读 `index.json` → 新增歌**不用重启** 8001（只有改插件代码才要重启）
- 人设已改：不再写死歌单，改为「曲库里几十首都会唱，被问会唱什么就用 sing 查歌单再答」

### ⚠️ 关键教训：前奏鬼叫（10/29 修）
**症状**：《不凡》开头有一段鬼叫，不是派蒙的音色。
**原因**：早期是「RVC 转完之后才剪」，RVC 已经把干声里前奏残留的伴奏一起变声了——那十几秒近静音的分离残留被唱成了怪声。
**正确顺序**：`UVR 分离 → 噪声门静音前奏残留(gate_quiet) → 从第一个有声点剪掉 → 才送 RVC → 再按乐句收尾`。
**门限**：演唱电平（rms 85 分位）的 10%，连续 0.8 秒才算开唱。实测《不凡》干声 0–16s 全是 rms 0.000–0.008 的残留，门限后完全静音，17.37s 才真正开唱。

### 已知坑
- DiffSinger（任意歌词合成）放弃：HF 的 `LogiAI10/diffsinger-mobile-onnx` 只有 acoustic+vocoder，**缺音素字典**（txt_tokens 的 id↔拼音映射），喂歌词只能是乱音；要做得弄完整 OpenUtau/DiffSinger 歌手包（含 dsdict），属独立工程
- QQ 语音是窄带压缩（每条 10–60KB），音色会略闷，属格式限制
- 用 WMI 拉起后台进程时，含中文的 `.cmd` 必须写 GBK；`.py` 仍是 UTF-8

## 🎙 10/28 音色切换（三轮）

### 第三轮：派蒙（当前生效）
- 模型：`E:\ai-voice\models\paimon\cn\paimon_cn.pth`（RVC v2）+ `added_IVF522_Flat_nprobe_1_paimon_cn_v2.index`（HF `paciapancakes/paimon_cn`，社区用原神中文语音训练，比自训素材强得多）
- 链路：`edge-tts(晓伊) → RVC(派蒙)`，9880 聚合服务直接返回
- `E:\ai-voice\voice-config.json` 关键项：`tts_engine=edge`、`rvc_enabled=true`、`rvc_model/rvc_index` 指派蒙、`rvc_pitch=4`（**用户选定**，输出 f0≈447Hz）、`rvc_index_rate=0.7`
- **音色微调不用改代码**：`rvc_pitch`（0/+2/+4 → f0 分别约 340/396/427Hz）、`rvc_index_rate`（越大越贴训练音色）、`edge_rate`/`edge_pitch`（源 TTS 语速音高）
- 试听样本：`D:\code2\AI伙伴\tmp\paimon\试听\`（pitch 0/+2/+4 + 服务实测两段）

### 第二轮：丁美桐（已弃用，保留可切）
- 零样本参考：`E:\ai-voice\models\ref_dmt.wav`（7.3s 她的采访回答）+ `gsv_prompt_text`（参考文本必须与音频内容一致）
- 自训 RVC：`E:\ai-voice\models\dingmeitong.pth`（250轮 40k，最低 loss 在 202 轮，另存 `dingmeitong_200e.pth`）+ `dingmeitong.index`
- 训练素材：`E:\ai-voice\datasets\dingmeitong\`（唱歌人声 172s + 说话 113s → 100 段/278s）；Applio 日志 `E:\ai-voice\Applio\logs\dingmeitong\`（G_*/D_* 中间权重约 6GB，可删）
- 评价：4.6 分钟素材训出来的模型 + 7 秒零样本都"不够好听"，故改用社区模型
- 切回方式：`tts_engine=gsv` + `rvc_enabled=false`（零样本），或 `rvc_model` 指向 dingmeitong.pth（自训）

**依赖补装记录**：`E:\ai-voice\sep-venv`（audio-separator + onnxruntime，人声分离）、gsv-venv 补 `resampy`、venv 补 `tensorboard`；UVR 模型在 `E:\ai-voice\models\uvr\`。出网被中间人劫持，SSL 校验必须关（`curl -k` / requests verify=False），github 下载走 `gh-proxy.com` 前缀才快。

## ⏳ 待验证（今晚）

- [ ] **23:28 better-diary 自动日记**（当天聊天量充足）；23:40 有定时提醒，验证日记生成 + 空间发布
- [ ] **新表情逻辑实机验证**：给哥哥/群里发条带情绪的消息，看她是否自主配表情包（attach_emoji 视觉规划器模式；表情池 43 张）

## 🔧 10/24 晚三连修复（已验证）

1. **启动脚本秒死**：.ps1 无 BOM → PowerShell 5.1 按 GBK 读中文 → 解析报错。已加 BOM（start-all.ps1 / stop-all.ps1）。
2. **QQ 重启后链路断**：18:52 QQ 重启后进程里没有钩子，SnowLuma 只重连已有钩子、不自动注入新 QQ → OneBot 3001 永远不监听。启动脚本已加自动注入（登录 5099 API → POST /api/processes/{pid}/load）。
3. **视觉规划器图片超限**：讯飞单请求图片数上限（错误码 10043）→ `[visual] max_image_num` 64→3，超出部分降级为文字描述（`[表情包: 标签]`）。

另：表情池不含上传表情（管理器内存池只在偷学通道更新）→ 重启后从数据库全量加载，当前 43 张（28 下载 + 15 偷学）。


## 一、系统架构

```
手机/桌面 QQ 用户（你、群友）
        ↓ 消息
QQ 客户端（小号 YOUR_BOT_QQ「白粥咸萝卜」，D:\App\QQNT）
        ↓ 进程内 Hook 注入
SnowLuma v2.1.1 协议端（tools\SnowLuma-v2.1.1\node.exe index.mjs）
   OneBot v11：HTTP 127.0.0.1:3000 / 正向 WS 127.0.0.1:3001
        ↓ WebSocket + access_token
MaiBot 1.3.15 麦麦大脑（D:\code2\AI伙伴\maibot，WebUI :8001）
   ├─ 适配器插件 MaiBot-SnowLuma-Adapter v1.1.8（消息网关 + QZone API + 主动私聊工具）
   ├─ Maizone（麦麦空间）：自主发说说/读好友动态/点赞/评论/回复评论
   └─ better-diary：每晚 23:30 写睡前日记 → 发到 QQ 空间
        ↓ OpenAI 兼容 API
DeepSeek 官方（api.deepseek.com/v1，2026-10-28 起主用）
   deepseek-flash（回复/规划/记忆/工具/看图，1M 上下文 + 图片输入）
   deepseek-v4-pro（纯文本，需要更强 Agent 时可切）
讯飞 MaaS（备用，模型定义保留，切回去只改 model_task_config）
   xopdeepseekv4pro / xopdeepseekv4flash0731 / xsparkx2flash / xopqwen36v35b
```

**模型分配现状**（`maibot\config\model_config.toml`）：replyer / planner / memory / utils / fast_model / vlm 全部 → `ds-flash`（DeepSeek deepseek-flash）；embedding 仍留空（DeepSeek 无嵌入接口，记忆走 BM25）。要换成 V4-Pro：把对应任务的 `model_list` 改成 `["ds-pro"]`（注意 V4-Pro 不支持图片输入，replyer/vlm 别用它）。

## 二、账号与凭据

- 机器人 QQ（小号）：YOUR_BOT_QQ（白粥咸萝卜）
- 主人 QQ（大号）：YOUR_MASTER_QQ（唯一管理员/白名单）
- 测试群：653542979（神奇小窝）—— 适配器策略里唯一放行的群
- 私聊白名单：仅主人 YOUR_MASTER_QQ
- **全部凭据汇总见 `CREDENTIALS.md`**（SnowLuma WebUI 密码 / MaiBot WebUI 令牌 / 讯飞 API key）

## 三、日常使用

| 操作 | 方法 |
|---|---|
| **开机后启动全套** | 双击 `start-all.cmd`（或右键 start-all.ps1 →「使用 PowerShell 运行」；若被执行策略挡住就用 cmd） |
| 停止服务 | 双击 `stop-all.cmd`（QQ 保持在线） |
| SnowLuma 管理面板 | http://127.0.0.1:5099 （admin，密码见 CREDENTIALS.md） |
| MaiBot 管理面板 | http://127.0.0.1:8001 （令牌见 `maibot\data\webui.json`） |
| 和麦麦说话 | 群里 @麦麦 或 直接私聊小号 |

## 四、麦麦能做什么

| 能力 | 状态 | 说明 |
|---|---|---|
| 群聊回复 | ✅ 已验证 | 2026-10-24 16:05 实测：群里说话→规划器→回复成功；被 @ 或被点名必回，有自主发言概率 |
| 主动私聊主人 | ✅ 已部署 | 适配器私聊工具已启用（enable_private_chat_tool），规划器会自主决定找主人说话 |
| 记忆 | ✅ 已启用 | A_Memorix 长期记忆系统开启（人物画像/事实写回/跨聊天共享）；讯飞无 embedding，走 BM25 关键词检索（语义检索不可用） |
| 发空间（说说） | ✅ 已验证 | Maizone：每天 08:00/20:00 时段有 30% 概率自主发说说；主人可说「发条说说」或 `/sendfeed 主题` |
| 自动阅读空间 | ✅ 已部署 | 每 15 分钟检查好友动态，按概率点赞/评论（22:00-07:00 静默） |
| 每日日记 | ✅ 已部署 | better-diary：每晚 23:30 基于当天聊天写日记发到空间（当天需 ≥20 条消息素材）；`/日记` 手动触发，`/日记查看` 回看 |
| 人设 | ✅ 妹妹 | 麦麦＝主人的亲妹妹：乖巧可爱、天真、有点小幽默；主人（大号）是哥哥。改人设：`maibot\config\bot_config.toml` 的 [personality] 三件套，保存即热重载 |
| 表情包 | ✅ 全能 | ① **回复模型是视觉模型（qwen-vl）**：图片/表情包原生进入她的多模态上下文，真的看得懂内容；② QQ 经典小黄脸：回复里写 `/害羞` `/呲牙` 等自动变表情（enable_text_face_conversion）；③ 表情包偷学：聊天里出现的表情包自动收藏+打标签+复用；④ 表情选择由 emoji 任务（qwen-vl）按情绪匹配 |

## 五、已验证的测试（2026-10-24）

1. ✅ 链路心跳：SnowLuma↔MaiBot WebSocket 稳定，30 秒心跳正常（含一次 SnowLuma 重启后 5 秒内自动重连）
2. ✅ 发说说：`send_qzone_msg` 成功，列表回读内容正确（部署验证说说已发布）
3. ✅ 发群消息：测试群收到系统自检消息（成功）
4. ✅ 插件全部激活：snowluma-adapter / Maizone / better-diary
5. ✅ 模型管线（15:30 实测）：dsv4-pro（回复，6.8s）/ dsv4-flash（规划，1.5s）/ spark-flash（工具，1.9s）全部通过 MaiBot 真实管线调用讯飞成功，工具调用正常
6. ✅ **回复链路实测（16:05）**：真实群消息→规划器（dsv4-flash）→回复器（dsv4-pro）→send_msg 回复成功；下午主人实测多轮对话正常
7. ✅ 记忆写回（16:18）：A_Memorix 人物事实成功写回长期记忆（person_fact_writeback 工作）
8. ✅ 妹妹人设 + 记忆 + /表情名 转换 + 颜文字保护（16:47 干净重启后全部生效）
9. ✅ 视觉回复链路（17:07 起）：回复模型切到 qwen-vl（视觉模型），图片/表情包原生进入回复上下文；qwen-vl 已实测可用（emoji.see/emoji.selector 多次成功调用）
10. ⚠️ 注意：MaiBot WebUI 的「测试模型」接口用的测试图只有 32×32，会被讯飞以「低于 50×50 分辨率下限」拒绝——视觉模型报这个错不代表模型不可用，真实图片没问题

## 六、已知限制与风险

- **封号风险**：SnowLuma 是非官方协议端（Hook 注入 QQ），违反腾讯用户协议。小号被风控/冻结的风险始终存在，**不要用大号跑协议端**。
- **QQ 版本匹配**：QQ 自动升级后 Hook 可能失效（表现为：SnowLuma 面板显示 QQ 进程但 injected=false 或消息不收发）。处理：等 SnowLuma 更新，或回退 QQ 版本。
- **SnowLuma 许可**：source-available，仅限个人非商用使用，不得二次分发修改版。
- **记忆降级**：讯飞 MaaS 没有 embedding 接口，麦麦的长期记忆用 BM25 关键词检索（效果尚可，但语义联想弱）。若在意，可补一个有 embedding 的模型（改 `maibot\config\model_config.toml` 的 embedding 配置）。
- **回复换行会拆条**：MaiBot 按换行分段发送，人设里已要求「回复写在一行、颜文字不拆」；若仍出现断行颜文字，说明模型偶发违反格式要求，属提示词层面的小概率问题。
- **运维关键点**：MaiBot 真正的运行时是 `python.exe`（uv 的 maibot.exe 只是启动跳板），`taskkill /IM maibot.exe` 杀不到任何东西；启停脚本已改用 CIM 按命令行匹配 + 端口判断。重复启动会端口冲突静默退出。
- PowerShell 直发 API 时中文会变乱码（PS5.1 Latin-1 问题）——已改用 UTF-8 字节体；麦麦本体（Python）不受影响。

## 七、文件地图

```
D:\code2\AI伙伴\
├─ start-all.ps1 / stop-all.ps1      # 一键启停
├─ CREDENTIALS.md                    # 全部凭据（保密）
├─ BUILD-NOTES.md                    # 本文件
├─ maibot\                           # 麦麦主程序
│  ├─ config\bot_config.toml         # 人设/账号（platform=qq, qq_account=YOUR_BOT_QQ）
│  ├─ config\model_config.toml       # 讯飞 MaaS 模型配置
│  ├─ config\adapter_policy.toml     # 群/私聊白名单（群 653542979 / 私聊 YOUR_MASTER_QQ）
│  ├─ plugins\Maizone\               # 发空间插件
│  ├─ plugins\better-diary\          # 日记插件
│  └─ plugins\MaiBot-SnowLuma-Adapter\  # 协议适配器
└─ tools\
   └─ SnowLuma-v2.1.1\               # 协议端（config\onebot_YOUR_BOT_QQ.json 是 OneBot 端口/token）
```

## 八、排障速查

| 症状 | 处理 |
|---|---|
| 麦麦不回消息 | 看 `maibot\logs\` 最新 jsonl 日志；确认适配器心跳（搜「心跳」） |
| QQ 掉线 | 重开 QQ 扫码，SnowLuma 自动重新注入；MaiBot 自动重连 |
| 全部重启 | `stop-all.ps1` → `start-all.ps1`（脚本按端口/CIM 判断，可重复运行） |
| WebUI 进不去 | 确认端口 5099 / 8001 在监听；进程名查 python.exe（MaiBot）和 node.exe（SnowLuma），**不要查 maibot.exe** |
| A_Memorix 初始化失败（已有活动写者） | 有残留实例占着记忆锁：运行 `stop-all.ps1`（会清锁）再 `start-all.ps1` |
| 说说/日记没发 | Maizone 当天概率判定为不发属正常；`/sendfeed 主题` 手动触发；日记看日志搜 better-diary |



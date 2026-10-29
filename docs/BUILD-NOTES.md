# 踩坑百科（Troubleshooting Encyclopedia）

> 本文是「麦麦」整套系统从零到稳定运行过程中踩过的**全部坑**，按子系统归类。
> 每条给出：**症状 → 根因 → 处理**。带 🔴 的是会让你以为「程序坏了」但其实是环境问题的坑。
>
> 最后更新：2026-10-29（补入本地嵌入、GPT-SoVITS/RVC 语音栈、faiss 路径问题）

---

## 0. 通用原则（先记住这五条，能省 80% 的排查时间）

1. **中文路径是隐形杀手**。faiss（C++ `fopen`）、RVC 的 `.index`、部分 Python 包都不认非 ASCII 路径。
   凡是「文件明明存在却打不开」——先怀疑路径里有中文。
2. **进程名 ≠ 你想象的名字**。MaiBot 的实际运行时是 `python.exe`，`maibot.exe` 只是跳板；
   SnowLuma 是 `node.exe`。`taskkill /IM maibot.exe` 杀不到任何东西。
3. **提示词管不住模型**。任何「必须/绝对不要」的人设规则，都有概率被模型无视；
   关键约束要么做**出站过滤**（代码兜底），要么接受偶发失败。
4. **端口被占可能不是你的程序**。本机上任何 exe 都可能绑 3000/3001/9880 这类常见端口；
   用 `Get-NetTCPConnection -LocalPort N` 找 OwningProcess，再看进程路径。
5. **国内网络**：PyPI/HF/GitHub 直连都不可靠，且本机有 SSL 中间人——优先镜像 + `truststore`。

---

## 1. 链路与端口

### 1.1 🔴 QQ 重启后消息收发全断
**症状**：SnowLuma 面板能看到 QQ 进程，但消息不动；OneBot 端口不监听；MaiBot 日志无新消息。
**根因**：QQ 重启后进程里**没有 hook DLL**（注入是进程级的，重启即失效）。
**处理**：`config/runtime.json` 设 `"hookAutoLoad": true` —— SnowLuma 启动时自动扫描并注入所有 QQ 进程。
（旧做法：登录 WebUI 5099 → `POST /api/processes/{pid}/load`，依赖密码且要手动。）

### 1.2 🔴 端口「在监听」但所有接口 404
**症状**：`Get-NetTCPConnection -LocalPort 3001` 显示 Listen，但 WS 连不上、HTTP 也 404。
**根因**：端口被**别的程序**占用了（本项目实测被另一个项目的 Electron 服务绑走 3000/3001）。
**处理**：查 OwningProcess → 看进程路径。
**根治**：本项目把 SnowLuma 迁到 **3100/3101**，避开常见端口。改端口要同步改：
- `tools/SnowLuma/config/onebot_*.json`（httpServers / wsServers 的 port）
- `plugins/MaiBot-SnowLuma-Adapter/config.toml`（`[client] port`）

### 1.3 停止脚本杀不干净，重启后端口冲突
**症状**：明明「停了」，再启动却端口占用；或者有两套 MaiBot 在跑。
**根因**：`uv tool` 启动的 MaiBot 有「跳板进程 + 核心进程 + 插件运行器」三种形态，
只杀其中一种会留下孤儿。
**处理**：按命令行匹配 `python.exe`：
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match "src\.runtime|plugin_runtime|maibot\.exe" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```
SnowLuma 用「可执行文件路径含 SnowLuma」+「监听 5099/3100/3101 的进程」双保险。

### 1.4 健康检查的正确姿势
| 检查 | 含义 |
|---|---|
| 3101 状态 **Listen** | SnowLuma 进程活着 |
| 3101 状态 **Established** | **适配器真的连上了**（这才是链路通） |
| 8001 Listen | MaiBot WebUI 活着 |
| SnowLuma 日志 `hook auto-load enabled` + `login detected` | QQ 钩子已注入且已登录 |

> 只看 Listen 会被「别的程序占端口」骗过。

---

## 2. 启动脚本与 PowerShell

### 2.1 🔴 .ps1 中文全乱码 / 脚本秒退
**根因**：Windows PowerShell 5.1 读无 BOM 的 UTF-8 会按 GBK 解码。
**处理**：`.ps1` 必须存为 **UTF-8 with BOM**。Linux 侧编辑工具（含多数编辑器）默认不加 BOM，务必检查。

### 2.2 🔴 .cmd 里写中文必乱
**根因**：cmd.exe 用 OEM 码页（简中 = GBK）读文件。
**处理**：`.cmd` 只放 ASCII，中文全部放 `.ps1`。或者把 `.cmd` 存成 GBK（不推荐，版本管理会乱）。

### 2.3 PowerShell 直发 HTTP 时中文变乱码
**根因**：PS5.1 默认把字符串按 Latin-1 编码进 body。
**处理**：显式转 UTF-8 字节：
```powershell
Invoke-RestMethod -Body ([System.Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json"
```

### 2.4 脚本结尾闪退看不到报错
**处理**：脚本末尾加 `Read-Host "回车关闭窗口"`；调试时改用 `powershell -NoProfile -File xxx.ps1` 在终端里跑。

---

## 3. MaiBot 核心

### 3.1 插件不加载：缺 `create_plugin` / `on_unload` / `on_config_update`
**症状**：日志 `加载插件失败 [local.xxx]`。
**根因**：MaiBot 插件生命周期要求实现三个钩子；`@Tool` 的参数不能直接 import `ToolParamInfo`（不在 SDK 导出里）。
**处理**：
- 文件末尾写 `def create_plugin() -> YourPlugin: return YourPlugin()`
- 实现 `on_load / on_unload / on_config_update` 三个 async 方法
- `@Tool(parameters={...})` 用完整 JSON Schema dict（`{"type":"object","properties":{...},"required":[...]}`）

### 3.2 改配置不生效
| 配置 | 生效方式 |
|---|---|
| `bot_config.toml`（人设/开关） | **热重载**，保存即生效 |
| `model_config.toml`（模型分配） | **必须重启** |
| 插件 `config.toml` | 触发 `on_config_update`（通常热更） |
| 插件 `plugin.py` 代码 | **必须重启** |

### 3.3 日志在哪
`maibot\logs\app_YYYYMMDD_HHMMSS.log.jsonl`（每次启动一个新文件）。
提示词快照在 `maibot\logs\maisaka_prompt\`——排查「模型看到了什么」的最佳入口。

### 3.4 A_Memorix 初始化失败：已有活动写者
**处理**：有残留实例占着锁 → 停止全套（会清锁）→ 再启动。
锁文件位置随 `[a_memorix.storage] data_dir` 走。

---

## 4. 适配器、表情与出站

### 4.1 表情包「变成文字」
**根因**：模型写 `/表情名`，但该名字不在 QQ 经典黄脸映射表里 → 转换器不认识 → 原样发出。
**处理**：在 `qq_face_map.py` 加别名（`QQ_FACE_DESCRIPTIONS.update({...})`，放在 Unicode 表合并**之后**）：

| 模型常写 | 映射到 |
|---|---|
| 滑稽（B 站梗） | 呲牙 |
| 哭 / 伤心 | 大哭 / 难过 |
| 震惊 / 大惊 | 惊讶 / 惊恐 |
| 羡慕 | 崇拜 |
| 心疼 | 拍头 |
| 馋 | 吃 |
| 加油 | 鼓掌 |
| 翻白眼 / 吐血 | 白眼 / 汗 |

> 踩过的次生坑：别名加到了 `QQ_FACE_EMOJIS` 或 `_UNICODE_FACE_DESCRIPTIONS` 里不生效，
> 必须加到 `QQ_FACE_DESCRIPTIONS`（且在该表 `update` 之后追加）。

### 4.2 句中表情不转换（`呜/捂脸你好`）
**根因**：转换正则后随边界写成 `(?!\w)`，Python 的 `\w` **包含汉字**，所以表情名后跟汉字时被判为非表情。
**处理**：改为 `(?![A-Za-z0-9_])`。

### 4.3 英文字母颜文字禁不掉（awa / qwq / owo）
**根因**：人设写了禁令，回复模型照样输出（提示词不可靠）。
**处理**：**出站物理剥离**（`segment_encoder._build_text_segments`）：
```python
LETTER_KAOMOJI_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:(?:awa|qwq|owo|ovo|uwu|qaq|030|0v0|ono|oto|ata|>_<)+)(?![A-Za-z0-9])",
    re.IGNORECASE)
```
注意：符号颜文字 `(๑•̀ㅂ•́)و✧` 不受影响；`ok`/`QQ` 不误伤；连写 `awaqwqowo` 要能整段剥掉（用 `(?:...)+`）。

### 4.4 模型在回复里写 `[图片: xxx]` / `[表情包: xxx]`
**根因**：模型模仿聊天历史里的渲染格式。
**处理**：人设加硬规则「这些标记只会原样变成文字，图片由系统自动附带」，并在适配器做兜底过滤。

### 4.5 出站安全过滤（防泄密）
在适配器所有 send 动作前检查文本：本机路径（`C:\`、`/home/`、`file://`、`base64://`）、
凭据（`ak-*`、`sk-*`、`Bearer *`、JWT）、已知密钥字面量 → 命中即整条拦截。
**注意**：语音消息走 `record` 段，不经过文本过滤 → 语音插件内必须再做一次同样检查。

---

## 5. 人设与模型行为

### 5.1 🔴 乱叫「哥哥」（不认人）
**根因**：聊天记录渲染成 `user="昵称"`，模型看不到 QQ 号，无法区分主人和群友。
**处理**：改核心渲染（`src/maisaka/context/planner_messages.py`）为 `昵称(QQ号)`：
```python
user_name = user_info.user_nickname or user_info.user_id
if user_info.user_nickname and user_info.user_id and str(user_info.user_id) != str(user_info.user_nickname):
    user_name = f"{user_info.user_nickname}({user_info.user_id})"
```
再在人设里写「只有 QQ xxx 是哥哥，其他号是陌生人」。

### 5.2 句子太长 / 像客服 / 讲健康道理
**根因**：人设只写了「简短」，没有给出**具体锚点**；模型默认走「有帮助的 AI」腔。
**处理**：人设里给**语气示范**和**禁止项**（例如「不说『对身体好』『细嚼慢咽』这种大人的话」），
并用年龄设定约束认知范围（6 岁 → 只懂零食/动画/玩具）。

### 5.3 表情包序号/消息 ID 编造（attach_emoji 模式）
**根因**：视觉模型当规划器时会编造参数（`msg_id="m2c4pef"`、`attachment_index=15` 但列表只有 5 个）。
**处理**：规划器用**纯文本强 Agent 模型**；视觉模型只用于回复/看图。

### 5.4 回复换行被拆成多条
**根因**：MaiBot 按换行分段发送。
**处理**：人设写「回复必须一行，颜文字不能拆」；仍偶发属模型问题，可接受。

---

## 6. 记忆与嵌入

### 6.1 🔴 每 3 分钟报 `embedding 任务未配置模型`
**根因**：`[model_task_config.embedding] model_list = []`，而 A_Memorix 的记忆编码必须要嵌入模型；
讯飞 MaaS **没有** embedding 端点（只有对话模型）。
**处理**：起一个本地嵌入服务（OpenAI 兼容 `/v1/embeddings`）：
- 模型 `BAAI/bge-small-zh-v1.5`（512 维，ONNX，CPU 单条 ~25ms）
- `pip install fastembed fastapi uvicorn truststore`
- `model_config.toml` 加 provider（`base_url = "http://127.0.0.1:9890/v1"`）+ embedding 模型 + task 指向它

### 6.2 🔴 `faiss::FileIOWriter ... No such file or directory`（文件明明存在）
**根因**：faiss 的 C++ 层用 `fopen`，**不支持中文路径**；记忆目录在 `D:\code2\AI伙伴\...`。
**处理**：`[a_memorix.storage] data_dir` 指向纯英文目录（如 `D:/code2/maibot-memory`），迁移数据后重启。
**同类**：RVC 的 `.index`（faiss 读）也必须英文路径——所以语音栈整体放 `E:\ai-voice`。

### 6.3 记忆「写了但检索不到」
检查顺序：① embedding 是否成功（日志搜「编码完成」）② faiss 索引是否写入成功（搜 `faiss`）③ `dimension` 与模型维度是否一致（bge-small-zh = 512）。

---

## 7. 语音栈（GPT-SoVITS + RVC）

### 7.1 🔴 RTX 50 系（Blackwell）装上就用不了
**根因**：RTX 50 是 sm_120，只有 CUDA 12.8+ 的 PyTorch 才有对应 kernel；老版 cu124 会直接报「no kernel image」或退回 CPU。
**处理**：`torch==2.7.1+cu128`（GSV）/ `2.11.0+cu128`（Applio），国内走
`https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/`（比官方源快 10 倍）。
验证：`torch.cuda.get_device_capability(0) == (12, 0)`。

### 7.2 GPT-SoVITS 装不上：`pyopenjtalk` / `jieba_fast` 需要 MSVC
**根因**：两个包要编译 C 扩展。
**处理**：写 shim（中文合成不需要日文 g2p）：
- `site-packages/jieba_fast/__init__.py` → `from jieba import *`
- `site-packages/jieba_fast/posseg.py` → `from jieba.posseg import *`
- `site-packages/pyopenjtalk.py` → 提供同名函数但调用即抛错

### 7.3 `fast-langdetect: Cache directory not found`
**处理**：先建目录 `GPT_SoVITS/pretrained_models/fast_langdetect`，再启动；它会自动下载
`lid.176.bin`（125MB，`dl.fbaipublicfiles.com`，国内速度不错）。

### 7.4 🔴 HF 下载 SSL 证书验证失败 / xet 401
**根因**：本机有 SSL 中间人，Python 的 certifi 不认它的 CA；新版 HF 用 xet 存储协议，镜像不支持。
**处理**：
```python
import truststore; truststore.inject_into_ssl()   # 接系统证书库
```
环境变量：`HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`。
> curl 报 `CRYPT_E_NO_REVOCATION_CHECK` 时改用 PowerShell `Invoke-WebRequest`（走 schannel 系统证书链）。

### 7.5 🔴 Applio 的模型路径是「相对当前工作目录」
**根因**：`now_dir = os.getcwd()`，contentvec/rmvpe 路径都相对它拼。
**处理**：启动服务/脚本时工作目录必须是 `E:\ai-voice\Applio`，否则会去下载而不是用本地文件。
（脚本里 `os.chdir(r"E:\ai-voice\Applio")` 放在最前面。）

### 7.6 每句语音都要 8-10 秒（模型反复加载）
**根因**：Applio 的 `convert_audio` 每次调用都 `load_hubert`（读 360MB + 上显存）。
**处理**：在常驻服务里给 `vc.load_hubert` 打补丁，已加载则直接返回：
```python
if vc.hubert_model is not None: return
```
效果：单句从 ~9s → **~1.8s**。

### 7.7 GPT-SoVITS 没有「音色」可用
**思路**（本项目做法）：**用 RVC 把通用女声转成目标音色，截 5 秒当 GSV 的参考音频** ——
等于「用变声器造出音色种子，让 TTS 直接学会这个人的说话方式」。
参考音频要求：3-10 秒、干净、单声道、16k；`gsv_prompt_text` 必须与音频内容逐字一致。

### 7.8 GPT-SoVITS 音色怪 / 默认加载了错模型
**根因**：`tts_infer.yaml` 的 `custom` 段写死了别的版本（如 v2 的 s1bert… 而文件没下）。
**处理**：`custom` 段改成实际下载的版本（`version: v2Pro`、`s1v3.ckpt`、`v2Pro/s2Gv2Pro.pth`）。

### 7.9 TTS/RVC 音色微调（不用改代码）
| 参数 | 效果 |
|---|---|
| `rvc_pitch`（0/+2/+4） | 音高整体上移，输出基频约 340/396/427Hz |
| `rvc_index_rate`（0-1） | 越大越贴训练音色，过大可能失真 |
| `edge_rate` / `edge_pitch` | 源 TTS 的语速/音高（仅 edge 引擎） |
| `tts_engine` | `gsv`（语气自然）/ `edge`（快，机械感） |
| `rvc_enabled` | TTS 之后是否再串 RVC |

### 7.10 QQ 语音音质偏闷
**原因**：QQ 语音是窄带压缩（每条 10-60KB），任何模型都会损失高频，属格式限制。

---

## 8. 唱歌（翻唱流水线）

> 结论：GPT-SoVITS 克隆音色、RVC 换音色，**两者都不产生旋律**（音高来自输入的干声）。
> 要「真唱」必须有一条已经唱好的干声 → 社区通用做法：**原曲 → UVR5 分离人声 → RVC 换音色**。

### 8.1 🔴 成品开头有「鬼叫」
**根因**：先 RVC 转换再剪辑 —— 干声里前奏残留的伴奏/噪声被 RVC 一起「唱」了。
**正确顺序**：`UVR 分离 → 噪声门静音前奏残留 → 从第一个有声点剪掉 → RVC → 乐句结尾收尾`。
**门限**：演唱电平（rms 85 分位）的 10%，连续 0.8 秒才算开唱。

### 8.2 变调不对（男声唱出来是女鬼/女声唱出来是闷雷）
**处理**：按人声中位 f0 自动定变调：≥240Hz → 0；190-240 → +6；<190 → +12。

### 8.3 批量翻唱太慢
**处理**：只分离前 85 秒（成品只要 42 秒）；分离与变声用**两个独立 venv**、双 worker 并行（`run_a.cmd` / `run_b.cmd`）。

### 8.4 🔴 含中文的 .cmd 用 WMI 拉起后失效
**处理**：`.cmd` 必须存 **GBK**（cmd 的码页），`.py` 仍是 UTF-8。

### 8.5 任意歌词合成（DiffSinger）为什么放弃
HF 上的 mobile onnx 包只有 acoustic + vocoder，**缺音素字典**（token id ↔ 拼音映射），
喂歌词只能是乱音；要做得引入完整 OpenUtau/DiffSinger 歌手包，属独立工程。

---

## 9. 网络与下载（国内环境）

| 资源 | 加速/绕行 |
|---|---|
| PyPI | `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| PyTorch cu128 | `https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/` |
| HuggingFace | `https://hf-mirror.com`；`HF_ENDPOINT` + `HF_HUB_DISABLE_XET=1` |
| GitHub raw/clone | `git clone --depth 1`；必要时 `https://ghfast.top/` 前缀 |
| 大文件 | `curl.exe -L --retry 3 -o`（支持断点续传） |

**SSL 中间人**：Python 走 `truststore`；curl 走 `-k` 或改用 `Invoke-WebRequest`。

---

## 10. 发布与安全

- 发布到 GitHub 前**必须脱敏**：API key、Token、QQ 号、WebUI 密码 → 占位符 `YOUR_XXX`
- 二次扫描（正则匹配真实值）确认无残留
- 不上传：`data/`（聊天记录/记忆）、`logs/`、模型权重、`node.exe`、`CREDENTIALS.md`
- 第三方插件若目录里有 `.git`，直接 `git add` 会被当成子模块（mode 160000，内容不上传）→ 先删嵌套 `.git`

---

## 11. 排障速查表

| 症状 | 先查 | 处理 |
|---|---|---|
| 麦麦不回消息 | 3101 是否 Established、日志有无新消息 | 断链见 1.1；适配器未连看 1.2 |
| 端口在监听但接口 404 | 端口归属进程 | 换端口（3100/3101）或杀掉占用者 |
| 启动脚本闪退/乱码 | .ps1 是否有 BOM、.cmd 是否纯 ASCII | 见 2.1 / 2.2 |
| 表情出成文字 | 表情名是否在映射表 | 加别名（4.1） |
| 满屏 awa/qwq | 出站过滤是否生效 | 4.3 |
| 记忆报 faiss 错误 | `data_dir` 是否英文 | 6.2 |
| 记忆编码失败 | embedding 任务是否配了模型 | 6.1 |
| 语音发不出 | 9880/9881 是否在跑、`voice-config.json` | 7.x |
| 语音很慢（8s+） | hubert 是否被反复加载 | 7.6 |
| 语音音色不对 | 参考音频 / rvc 参数 | 7.7 / 7.9 |
| 唱歌开头鬼叫 | 处理顺序是否「先剪后变声」 | 8.1 |
| 日记/说说没发 | Maizone 概率判定、素材数 | 手动 `/sendfeed` 或 `/日记` |
| MaiBot 起不来（记忆锁） | 残留写者 | 停止全套（清锁）再启 |
| WebUI 进不去 | 5099/8001 监听、进程名 | 查 python.exe / node.exe，不是 maibot.exe |

---

## 12. 变更时间线（简）

| 日期 | 事项 |
|---|---|
| 10-23 | SnowLuma + MaiBot 首次联通，QQ 小号上线 |
| 10-24 | 适配器/表情/人设首版；三连修复（脚本 BOM、hook 自动注入、图片数上限） |
| 10-26 | 语音功能（edge-tts）；主动聊天插件；认人渲染补丁；颜文字出站过滤 |
| 10-28 | 语音栈接入 GPT-SoVITS + RVC（大肥鱼/派蒙等音色）；唱歌流水线 |
| 10-29 | 本地嵌入服务（bge-small-zh）修复记忆；faiss 中文路径坑修复；端口迁 3100/3101 |

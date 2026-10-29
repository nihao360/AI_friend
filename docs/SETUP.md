# 完整部署指南（从零还原整套系统）

> 本文档描述如何在一台全新的 Windows 机器上把「麦麦」完整跑起来。
> 所有外部依赖的下载地址见 `ASSETS.md`，或直接用 `fetch-assets.ps1` 一键下载。

## 0. 总览与硬件要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10/11 x64 |
| 显卡 | NVIDIA，≥8GB 显存（实测 RTX 5070 12GB）；RTX 50 系必须 cu128 版 PyTorch |
| 磁盘 | 约 30GB（GPT-SoVITS 5GB + Applio 4GB + 两个 venv 约 10GB + 模型 2GB） |
| 内存 | 16GB 以上（同时跑 MaiBot + GSV + RVC + 嵌入服务） |
| 账号 | 一个备用 QQ 号（机器人号）+ 你的主号 |

**关键原则：所有涉及 faiss / RVC 的路径必须是纯英文**（如 `E:\ai-voice`），
因为 faiss 的 C++ 层用 `fopen`，不支持中文路径。

建议目录布局：

```
D:\code2\AI伙伴\        MaiBot 工作目录（含 config/ plugins/ data/）
E:\ai-voice\            语音栈（Applio、GPT-SoVITS、模型、两个 venv）
D:\code2\maibot-memory\ A_Memorix 记忆数据（必须英文路径）
```

## 1. 安装基础工具

```powershell
# Python 环境管理器（本项目用 uv 管理多个 Python 版本）
winget install astral-sh.uv
# 或用已有 Python：pip install uv

# Git
winget install Git.Git
```

## 2. 安装 MaiBot（大脑）

MaiBot 通过 uv tool 安装（自带 Python 环境）：

```powershell
uv tool install maibot
# 安装后位于 %USERPROFILE%\.local\bin\maibot.exe
```

首次运行会初始化工作目录：

```powershell
$env:EULA_AGREE    = "<你的 EULA 哈希，首次启动时 Maibot 会提示>"
$env:PRIVACY_AGREE = "<同上>"
& "$env:USERPROFILE\.local\bin\maibot.exe" run --directory D:\code2\AI伙伴\maibot
```

WebUI 默认 `http://127.0.0.1:8001`（令牌见 `maibot\data\webui.json`）。

- 把本仓库 `config/bot_config.toml`、`config/model_config.toml` 复制进去并填密钥
- 把本仓库 `plugins/` 下所有插件复制进 `maibot\plugins\`
- 修改 `[a_memorix.storage] data_dir` 为英文路径（见 PATCHES.md §3）

## 3. 安装 SnowLuma（QQ 协议端）

1. 从 SnowLuma 官方发布页下载 `SnowLuma-v2.1.1-win-x64.zip`（见 ASSETS.md）
2. 解压到 `D:\code2\AI伙伴\tools\SnowLuma-v2.1.1`
3. 用本仓库 `tools\SnowLuma\config\*.json` 覆盖其 `config` 目录（已脱敏，需填 token）
4. 启动：`launcher.bat`（或 `node.exe index.mjs`）

配置要点（`config/runtime.json`）：

```json
{ "webuiPort": 5099, "hookAutoLoad": true }
```

`hookAutoLoad: true` 让 SnowLuma 自动把 hook 注入 QQ，**QQ 重启后无需手动注入**（这是踩过的大坑）。

`config/onebot_*.json` 端口约定（本项目采用 3100/3101 避开占用）：

```json
{
  "httpServers": [{ "port": 3100, "accessToken": "<HTTP token>" }],
  "wsServers":   [{ "port": 3101, "accessToken": "<WS token>" }]
}
```

## 4. 适配器与插件配置

`plugins/MaiBot-SnowLuma-Adapter/config.toml`：

```toml
[client]
server = "127.0.0.1"
port = 3101
token = "<与 SnowLuma wsServers 的 accessToken 一致>"
```

## 5. 模型与密钥配置

`config/model_config.toml` 里需要替换的占位符：

| 占位符 | 说明 |
|---|---|
| `ak-YOUR_XFYUN_APP_KEY` | 讯飞 MaaS API Key（可换成任意 OpenAI 兼容服务） |
| `sk-YOUR_DEEPSEEK_KEY` | DeepSeek API Key |
| `YOUR_BOT_QQ` / `YOUR_MASTER_QQ` | 机器人 QQ / 主人 QQ（在 bot_config.toml 的人格描述里） |

三个模型任务至少要有：`planner`（规划/工具调用）、`replyer`（回复，建议视觉模型）、`embedding`（见第 7 节）。

## 6. 语音栈（GPT-SoVITS + RVC）

### 6.1 目录与环境

```powershell
# GPT-SoVITS（Python 3.10）
uv venv --python 3.10 E:\ai-voice\gsv-venv
# 语音聚合服务 + RVC（Python 3.12）
uv venv --python 3.12 E:\ai-voice\venv
# 嵌入服务（Python 3.12，轻量）
uv venv --python 3.12 E:\ai-voice\emb-venv
```

### 6.2 PyTorch（RTX 50 系必须 cu128）

```powershell
uv pip install --python E:\ai-voice\gsv-venv\Scripts\python.exe torch==2.7.1 torchaudio==2.7.1 `
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/

uv pip install --python E:\ai-voice\venv\Scripts\python.exe torch==2.11.0 torchaudio==2.11.0 `
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
```

验证：`python -c "import torch; print(torch.cuda.get_device_capability(0))"` → `(12, 0)` 即成功。

### 6.3 GPT-SoVITS

```powershell
git clone --depth 1 https://github.com/RVC-Boss/GPT-SoVITS.git E:\ai-voice\GPT-SoVITS
uv pip install --python E:\ai-voice\gsv-venv\Scripts\python.exe -r E:\ai-voice\GPT-SoVITS\requirements.txt `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

Windows 需要两个 shim（见 PATCHES.md §4）：
- `jieba_fast` → 转发 `jieba`
- `pyopenjtalk` → 桩（中文合成不需要日文 g2p）

模型放 `GPT-SoVITS\GPT_SoVITS\pretrained_models\`（文件清单见 ASSETS.md），
并修改 `GPT_SoVITS\configs\tts_infer.yaml` 的 `custom` 段：

```yaml
custom:
  bert_base_path: GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
  cnhuhbert_base_path: GPT_SoVITS/pretrained_models/chinese-hubert-base
  device: cuda
  is_half: true
  t2s_weights_path: GPT_SoVITS/pretrained_models/s1v3.ckpt
  version: v2Pro
  vits_weights_path: GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth
```

启动 TTS API（端口 9881）：

```powershell
cd E:\ai-voice\GPT-SoVITS
E:\ai-voice\gsv-venv\Scripts\python.exe api_v2.py -a 127.0.0.1 -p 9881 -c GPT_SoVITS/configs/tts_infer.yaml
```

### 6.4 Applio（RVC 引擎）

```powershell
git clone --depth 1 https://github.com/IAHispano/Applio.git E:\ai-voice\Applio
uv pip install --python E:\ai-voice\venv\Scripts\python.exe -r E:\ai-voice\Applio\requirements-engine.txt `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple --extra-index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/
```

> 注意：Applio 的 requirements 里有 `nvidia-*`、`onnxruntime-gpu` 等大包，
> 国内下载慢可只装精简集（见 BUILD-NOTES.md）。

RVC 需要的两个基础模型（放 `Applio\rvc\models\`）：

```
rvc\models\embedders\contentvec\pytorch_model.bin   (ContentVec 768, ~360MB)
rvc\models\embedders\contentvec\config.json
rvc\models\predictors\rmvpe.pt                      (~172MB)
```

**注意**：Applio 的模型路径是相对**当前工作目录**的（`now_dir = os.getcwd()`），
所以启动服务时工作目录必须是 `E:\ai-voice\Applio`。

### 6.5 音色模型（大肥鱼）

下载 `DaFeiYu_rvc_v2_40k`（dafeiyu.pth + index，见 ASSETS.md）放 `E:\ai-voice\models\`。

### 6.6 参考音频（GPT-SoVITS 零样本的「音色种子」）

本项目的小技巧：**用 RVC 把通用女声转成大肥鱼音色，截 5 秒当 GSV 参考音频**，
这样 GPT-SoVITS 直接学会大肥鱼说话，再决定要不要再过一遍 RVC。

```powershell
# 1. 用 edge-tts 生成一句干净语音 → RVC 转换
# 2. 转成 16k 单声道 wav 存为 E:\ai-voice\models\ref.wav
# 3. 在 voice-config.json 里填 gsv_ref_audio 与 gsv_prompt_text（必须与参考音频内容一致）
```

### 6.7 启动语音与嵌入服务

```powershell
E:\ai-voice\venv\Scripts\python.exe     E:\ai-voice\voice-server.py      # 9880 语音聚合
E:\ai-voice\emb-venv\Scripts\python.exe E:\ai-voice\embedding-server.py  # 9890 嵌入
```

`voice-server.py` 读 `E:\ai-voice\voice-config.json`：

```json
{ "tts_engine": "gsv", "rvc_enabled": false, "gsv_url": "http://127.0.0.1:9881/tts" }
```

- `tts_engine`: `gsv`（GPT-SoVITS，语气自然）/ `edge`（edge-tts，1 秒出音）
- `rvc_enabled`: 是否在 TTS 后再串一遍 RVC（音色更准，+1.8 秒）

## 7. 记忆嵌入服务

`embedding-server.py` 提供 OpenAI 兼容 `/v1/embeddings`（本地 BAAI/bge-small-zh-v1.5，512 维）：

```powershell
uv pip install --python E:\ai-voice\emb-venv\Scripts\python.exe fastembed fastapi uvicorn truststore `
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

`model_config.toml` 里对应的 provider：

```toml
[[api_providers]]
name = "local-embed"
base_url = "http://127.0.0.1:9890/v1"
api_key = "not-needed"
model_list_endpoint = "/models"

[[models]]
model_type = "embedding"
model_identifier = "bge-small-zh"
name = "bge-small-zh"
api_provider = "local-embed"

[model_task_config.embedding]
model_list = ["bge-small-zh"]
```

## 8. 一键启动

```powershell
D:\code2\AI伙伴\start-all.cmd
```

脚本依次：QQ → SnowLuma(3100/3101) → GPT-SoVITS(9881) → 语音服务(9880) → 嵌入(9890) → MaiBot(8001)，
最后确认适配器连接（3101 established）。停止用 `stop-all.cmd`。

## 9. 验证清单

| 检查 | 期望 |
|---|---|
| `Get-NetTCPConnection -LocalPort 3101 -State Established` | 有 1 条连接 |
| SnowLuma 日志出现 `hook auto-load enabled` + `login detected` | 钩子已注入 |
| MaiBot 日志出现 `插件 local.maimai-voice v1.0.0 加载成功` | 插件正常 |
| 日志无 `编码失败: embedding 任务未配置模型` | 嵌入已配置 |
| 日志无 `faiss::FileIOWriter ... No such file or directory` | 记忆路径为英文 |
| `curl http://127.0.0.1:9880/health` | `{"ready":true}` |

## 10. 常见问题

| 症状 | 原因与处理 |
|---|---|
| SnowLuma 端口 404 / 消息发不出 | QQ 未登录或 hook 未注入；重启 SnowLuma（hookAutoLoad 会自动注入） |
| `codecs 表情不转换` | 适配器 config 里 `enable_text_face_conversion = true` |
| 语音发送失败 | 检查 9880/9881 是否在跑；`voice-config.json` 引擎是否可用 |
| 记忆报 faiss 错误 | `data_dir` 必须是英文路径 |
| GPT-SoVITS 启动报 missing module | 见 PATCHES.md §4（jieba_fast / pyopenjtalk shim、fast_langdetect 缓存目录） |
| 下载 HF 模型 SSL 失败 | `truststore.inject_into_ssl()`；或设 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1` |

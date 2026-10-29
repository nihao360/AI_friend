# 外部资产清单（下载地址与版本）

本仓库不含大文件（模型/二进制/venv）。以下为完整清单，可配合 `fetch-assets.ps1` 一键下载。

## 1. 程序与二进制

| 组件 | 版本 | 来源 | 说明 |
|---|---|---|---|
| MaiBot | 1.3.15 | `uv tool install maibot` | 主程序，自带 Python 环境 |
| SnowLuma | v2.1.1 | GitHub Releases（SnowLuma 官方仓库） | QQ 协议端，含 node.exe（约 90MB） |
| MaiBot-SnowLuma-Adapter | 1.1.8 | 本仓库 `plugins/`（含本地补丁） | 适配器 |
| better-diary | 1.7.1 | 本仓库 `plugins/` | 日记插件（第三方，orge-8） |
| Maizone | 3.0.3 | 本仓库 `plugins/` | QQ空间说说插件（第三方） |

## 2. GPT-SoVITS（TTS）

代码：`https://github.com/RVC-Boss/GPT-SoVITS`（浅克隆即可）

模型文件（放到 `GPT-SoVITS\GPT_SoVITS\pretrained_models\`）：

| 文件 | 大小 | 来源 |
|---|---|---|
| `s1v3.ckpt` | 148MB | `https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main/s1v3.ckpt` |
| `v2Pro/s2Gv2Pro.pth` | 155MB | `.../v2Pro/s2Gv2Pro.pth` |
| `chinese-roberta-wwm-ext-large/pytorch_model.bin` | 621MB | `.../chinese-roberta-wwm-ext-large/pytorch_model.bin` |
| `chinese-roberta-wwm-ext-large/config.json` | 1KB | 同上目录 |
| `chinese-roberta-wwm-ext-large/tokenizer.json` | 300KB | 同上目录 |
| `chinese-hubert-base/pytorch_model.bin` | 180MB | `.../chinese-hubert-base/pytorch_model.bin` |
| `chinese-hubert-base/config.json` | 1KB | 同上目录 |
| `chinese-hubert-base/preprocessor_config.json` | 1KB | 同上目录 |
| `sv/pretrained_eres2netv2w24s4ep4.ckpt` | 103MB | `.../sv/pretrained_eres2netv2w24s4ep4.ckpt` |

> 首次合成时还会自动下载：
> - 语言检测模型 `lid.176.bin`（125MB，来自 `dl.fbaipublicfiles.com`，放到
>   `GPT_SoVITS\pretrained_models\fast_langdetect\`，需先建目录）
> - G2PW 中文注音模型（`G2PWModel`，约 600MB，首次启动自动下载）

## 3. Applio（RVC 引擎）

代码：`https://github.com/IAHispano/Applio`（浅克隆）

基础模型：

| 文件 | 大小 | 来源 |
|---|---|---|
| `rvc/models/embedders/contentvec/pytorch_model.bin` | 360MB | `https://hf-mirror.com/IAHispano/Applio/resolve/main/Resources/embedders/contentvec/pytorch_model.bin` |
| `rvc/models/embedders/contentvec/config.json` | 1KB | 同目录 |
| `rvc/models/predictors/rmvpe.pt` | 172MB | `https://hf-mirror.com/IAHispano/Applio/resolve/main/Resources/predictors/rmvpe.pt` |

## 4. 音色模型（大肥鱼 DaFeiYu）

| 文件 | 大小 | 来源 |
|---|---|---|
| `dafeiyu.pth` | 53MB | `https://huggingface.co/YukiKaze1337/DaFeiYu_rvc_v2_40k/resolve/main/dafeiyu.pth` |
| `dafeiyu.index` | 154MB | `.../added_IVF1314_Flat_nprobe_1_dafeiyu_v2.index`（国内建议走 `hf-mirror.com`） |

备选（同角色不同声库）：`Esmerubphire/FeiyuVoice-RVC`（v1，含 run_rvc.py 工具）、
`Esmerubphire/FeiyuVoice-CosyVoice3`（CosyVoice3 说话声库，需 WSL2 + torch 2.11 环境）。

> ⚠️ 音色素材由 B 站 UP 主授权训练，使用前请阅读对应仓库的 `NOTICE.md` / `COPYRIGHT.md`，遵守其分发条款。

## 5. 记忆嵌入模型

`BAAI/bge-small-zh-v1.5`（512 维 ONNX，约 90MB）——由 `fastembed` 自动下载到
`E:\ai-voice\emb-cache`，无需手动准备。

## 6. Python 包（关键版本）

| 环境 | 关键包 |
|---|---|
| gsv-venv (3.10) | torch 2.7.1+cu128, torchaudio, transformers 4.57.6, pytorch-lightning, funasr, fastapi |
| venv (3.12) | torch 2.11.0+cu128, transformers 5.x, fastembed 不装, onnxruntime, fastapi, edge-tts |
| emb-venv (3.12) | fastembed, fastapi, uvicorn, truststore |

## 7. 国内下载建议

| 资源 | 加速方式 |
|---|---|
| PyPI | `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| PyTorch cu128 | `--index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu128/` |
| HuggingFace | `https://hf-mirror.com` 镜像，或 `HF_ENDPOINT=https://hf-mirror.com` |
| GitHub 代码 | `git clone --depth 1`；必要时用 `https://ghfast.top/` 前缀 |
| 大文件 | 用 `curl.exe -L -o`（支持断点），或本仓库 `fetch-assets.ps1` |

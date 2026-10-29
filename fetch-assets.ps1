# 一键下载全部外部资产（模型文件 + 基础模型）
# 用法：powershell -ExecutionPolicy Bypass -File .\fetch-assets.ps1
# 说明：代码仓库（GPT-SoVITS / Applio）用 git clone 单独准备，见 docs/SETUP.md

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$GSV  = "E:\ai-voice\GPT-SoVITS\GPT_SoVITS\pretrained_models"
$APPL = "E:\ai-voice\Applio\rvc\models"
$VOICE = "E:\ai-voice\models"

function Get-Asset($url, $dest) {
    $dir = Split-Path $dest -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if (Test-Path $dest) {
        $exist = [Math]::Round((Get-Item $dest).Length / 1MB, 1)
        Write-Host "  已存在，跳过: $dest ($exist MB)"
        return
    }
    Write-Host "  下载: $url"
    & curl.exe -L --retry 3 --retry-delay 3 -o $dest $url
    if (Test-Path $dest) {
        Write-Host "  OK $dest ($([Math]::Round((Get-Item $dest).Length/1MB,1)) MB)"
    } else {
        Write-Host "  [!] 失败: $url" -ForegroundColor Yellow
    }
}

Write-Host "=== 1/4 GPT-SoVITS v2Pro 模型 ==="
$hf = "https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main"
Get-Asset "$hf/s1v3.ckpt"                                   "$GSV\s1v3.ckpt"
Get-Asset "$hf/v2Pro/s2Gv2Pro.pth"                          "$GSV\v2Pro\s2Gv2Pro.pth"
Get-Asset "$hf/chinese-roberta-wwm-ext-large/pytorch_model.bin" "$GSV\chinese-roberta-wwm-ext-large\pytorch_model.bin"
Get-Asset "$hf/chinese-roberta-wwm-ext-large/config.json"       "$GSV\chinese-roberta-wwm-ext-large\config.json"
Get-Asset "$hf/chinese-roberta-wwm-ext-large/tokenizer.json"    "$GSV\chinese-roberta-wwm-ext-large\tokenizer.json"
Get-Asset "$hf/chinese-hubert-base/pytorch_model.bin"           "$GSV\chinese-hubert-base\pytorch_model.bin"
Get-Asset "$hf/chinese-hubert-base/config.json"                 "$GSV\chinese-hubert-base\config.json"
Get-Asset "$hf/chinese-hubert-base/preprocessor_config.json"    "$GSV\chinese-hubert-base\preprocessor_config.json"
Get-Asset "$hf/sv/pretrained_eres2netv2w24s4ep4.ckpt"           "$GSV\sv\pretrained_eres2netv2w24s4ep4.ckpt"

Write-Host "=== 2/4 Applio 基础模型（contentvec + rmvpe）==="
$ap = "https://hf-mirror.com/IAHispano/Applio/resolve/main/Resources"
Get-Asset "$ap/embedders/contentvec/pytorch_model.bin" "$APPL\embedders\contentvec\pytorch_model.bin"
Get-Asset "$ap/embedders/contentvec/config.json"       "$APPL\embedders\contentvec\config.json"
Get-Asset "$ap/predictors/rmvpe.pt"                    "$APPL\predictors\rmvpe.pt"

Write-Host "=== 3/4 大肥鱼音色模型（RVC）==="
$dfy = "https://hf-mirror.com/YukiKaze1337/DaFeiYu_rvc_v2_40k/resolve/main"
Get-Asset "$dfy/dafeiyu.pth" "$VOICE\dafeiyu.pth"
Get-Asset "$dfy/added_IVF1314_Flat_nprobe_1_dafeiyu_v2.index" "$VOICE\dafeiyu.index"

Write-Host "=== 4/4 语言检测模型（GPT-SoVITS 首次合成需要）==="
$ldDir = "E:\ai-voice\GPT-SoVITS\GPT_SoVITS\pretrained_models\fast_langdetect"
if (-not (Test-Path $ldDir)) { New-Item -ItemType Directory -Force -Path $ldDir | Out-Null }
Get-Asset "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin" "$ldDir\lid.176.bin"

Write-Host ""
Write-Host "完成。剩余需要手动准备：" -ForegroundColor Cyan
Write-Host "  - GPT-SoVITS / Applio 代码仓库（git clone，见 docs/SETUP.md §6）"
Write-Host "  - SnowLuma v2.1.1（官方发布包，含 node.exe）"
Write-Host "  - Python 环境与 PyTorch cu128（见 docs/SETUP.md §6.1-6.2）"
Write-Host "  - 参考音频 E:\ai-voice\models\ref.wav（用 RVC 生成，见 SETUP.md §6.6）"

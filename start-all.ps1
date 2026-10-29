# 一键启动 AI 伙伴全套服务：QQ → SnowLuma（协议端，自动注入钩子）→ MaiBot（麦麦大脑）
# 用法：双击 start-all.cmd，或在 PowerShell 中 .\start-all.ps1
# 说明：SnowLuma 已开启 hookAutoLoad（自动注入 QQ 钩子），无需手动注入；端口为 3100/3101
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$root      = "D:\code2\AI伙伴"
$qqExe     = "D:\App\QQNT\QQ.exe"
$snowluma  = "$root\tools\SnowLuma-v2.1.1"
$maibotDir = "$root\maibot"

Write-Host "=== AI 伙伴一键启动 ===" -ForegroundColor Cyan

# 1. QQ 客户端（保持小号 YOUR_BOT_QQ 在线）
if (-not (Get-Process QQ -ErrorAction SilentlyContinue)) {
    Write-Host "[1/4] 启动 QQ..."
    Start-Process -FilePath $qqExe -WorkingDirectory (Split-Path $qqExe)
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Get-Process QQ -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
} else {
    Write-Host "[1/4] QQ 已在运行"
}

# 2. SnowLuma 协议端（WebUI 5099 = 存活标志；钩子由 hookAutoLoad 自动注入）
$slUp = Get-NetTCPConnection -State Listen -LocalPort 5099 -ErrorAction SilentlyContinue
if (-not $slUp) {
    Write-Host "[2/4] 启动 SnowLuma..."
    Start-Process -FilePath "$snowluma\node.exe" -ArgumentList "index.mjs" -WorkingDirectory $snowluma -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(30)
    do { Start-Sleep -Seconds 2
         $slUp = Get-NetTCPConnection -State Listen -LocalPort 5099 -ErrorAction SilentlyContinue
    } while (-not $slUp -and (Get-Date) -lt $deadline)
} else {
    Write-Host "[2/4] SnowLuma 已在运行"
}
if (-not $slUp) { Write-Host "  [X] SnowLuma 没起来" -ForegroundColor Red; Read-Host "回车退出"; exit 1 }

# 3. 等 OneBot 3101（SnowLuma 起来 + QQ 钩子在线后监听）
$deadline = (Get-Date).AddSeconds(45)
do { Start-Sleep -Seconds 2
     $ob = Get-NetTCPConnection -State Listen -LocalPort 3101 -ErrorAction SilentlyContinue
} while (-not $ob -and (Get-Date) -lt $deadline)
if ($ob) { Write-Host "[3/4] OneBot 就绪（3100/3101 监听中，钩子已自动注入）" }
else { Write-Host "[3/4] [!] OneBot 3101 未就绪——QQ 可能停在登录界面，扫码登录后再跑一次本脚本" -ForegroundColor Yellow }

# 3.5 GPT-SoVITS TTS 服务（9881，v2Pro 零样本克隆）
$gsvUp = Get-NetTCPConnection -State Listen -LocalPort 9881 -ErrorAction SilentlyContinue
if (-not $gsvUp -and (Test-Path "E:\ai-voice\GPT-SoVITS\api_v2.py")) {
    Write-Host "[3.5] 启动 GPT-SoVITS（丁美桐音色 TTS，加载约 50s）..."
    Start-Process -FilePath "E:\ai-voice\gsv-venv\Scripts\python.exe" -ArgumentList "api_v2.py","-a","127.0.0.1","-p","9881","-c","GPT_SoVITS/configs/tts_infer.yaml" -WorkingDirectory "E:\ai-voice\GPT-SoVITS" -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(150)
    do { Start-Sleep -Seconds 5
         $gsvUp = Get-NetTCPConnection -State Listen -LocalPort 9881 -ErrorAction SilentlyContinue
    } while (-not $gsvUp -and (Get-Date) -lt $deadline)
    if (-not $gsvUp) { Write-Host "  [!] GPT-SoVITS 未就绪" -ForegroundColor Yellow }
} elseif ($gsvUp) {
    Write-Host "[3.5] GPT-SoVITS 已在运行"
}

# 3.6 语音聚合服务（9880，TTS→可选RVC，麦麦插件调用）
$vsUp = Get-NetTCPConnection -State Listen -LocalPort 9880 -ErrorAction SilentlyContinue
if (-not $vsUp -and (Test-Path "E:\ai-voice\voice-server.py")) {
    Write-Host "[3.6] 启动语音聚合服务（9880）..."
    Start-Process -FilePath "E:\ai-voice\venv\Scripts\python.exe" -ArgumentList "E:\ai-voice\voice-server.py" -WorkingDirectory "E:\ai-voice\Applio" -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(90)
    do { Start-Sleep -Seconds 3
         $vsUp = Get-NetTCPConnection -State Listen -LocalPort 9880 -ErrorAction SilentlyContinue
    } while (-not $vsUp -and (Get-Date) -lt $deadline)
    if (-not $vsUp) { Write-Host "  [!] 语音服务未就绪——麦麦将退回 edge-tts 原声" -ForegroundColor Yellow }
} elseif ($vsUp) {
    Write-Host "[3.6] 语音聚合服务已在运行"
}

# 3.7 本地嵌入服务（9890，bge-small-zh 512维，给 MaiBot 记忆用）
$embUp = Get-NetTCPConnection -State Listen -LocalPort 9890 -ErrorAction SilentlyContinue
if (-not $embUp -and (Test-Path "E:\ai-voice\embedding-server.py")) {
    Write-Host "[3.7] 启动本地嵌入服务（9890）..."
    $env:HF_ENDPOINT = "https://hf-mirror.com"
    $env:HF_HUB_DISABLE_XET = "1"
    Start-Process -FilePath "E:\ai-voice\emb-venv\Scripts\python.exe" -ArgumentList "E:\ai-voice\embedding-server.py" -WorkingDirectory "E:\ai-voice" -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(90)
    do { Start-Sleep -Seconds 3
         $embUp = Get-NetTCPConnection -State Listen -LocalPort 9890 -ErrorAction SilentlyContinue
    } while (-not $embUp -and (Get-Date) -lt $deadline)
    if (-not $embUp) { Write-Host "  [!] 嵌入服务未就绪——麦麦的记忆语义检索不可用" -ForegroundColor Yellow }
} elseif ($embUp) {
    Write-Host "[3.7] 本地嵌入服务已在运行"
}

# 4. MaiBot 麦麦大脑（WebUI: http://127.0.0.1:8001）
$mbUp = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
if (-not $mbUp) {
    Write-Host "[4/4] 启动 MaiBot..."
    $env:EULA_AGREE    = "8e6e7d647f7f82d6ea98456b73908656"
    $env:PRIVACY_AGREE = "91e5db7659c560bc3545e63859b6ebc0"
    Start-Process -FilePath "$env:USERPROFILE\.local\bin\maibot.exe" -ArgumentList "run","--directory",$maibotDir -WorkingDirectory $maibotDir -WindowStyle Minimized
    $deadline = (Get-Date).AddSeconds(90)
    do { Start-Sleep -Seconds 3
         $mbUp = Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue
    } while (-not $mbUp -and (Get-Date) -lt $deadline)
} else {
    Write-Host "[4/4] MaiBot 已在运行"
}
if (-not $mbUp) { Write-Host "  [X] MaiBot 没起来" -ForegroundColor Red; Read-Host "回车退出"; exit 1 }

# 适配器连接确认（MaiBot 里的 SnowLuma 适配器连 3101）
$deadline = (Get-Date).AddSeconds(60)
do { Start-Sleep -Seconds 5
     $est = @(Get-NetTCPConnection -LocalPort 3101 -State Established -ErrorAction SilentlyContinue)
} while ($est.Count -lt 1 -and (Get-Date) -lt $deadline)
Write-Host ""
if ($est.Count -ge 1) {
    Write-Host "[OK] 全链路就绪：QQ(钩子) -> SnowLuma(3100/3101) -> MaiBot(8001) -> 适配器已连接" -ForegroundColor Green
} else {
    Write-Host "[!] 服务已起，适配器暂未连上——稍等或重跑本脚本" -ForegroundColor Yellow
}
Write-Host "  SnowLuma WebUI : http://127.0.0.1:5099"
Write-Host "  MaiBot  WebUI  : http://127.0.0.1:8001  (令牌见 maibot\data\webui.json)"
Write-Host "  凭据汇总       : $root\CREDENTIALS.md"
Write-Host ""
Read-Host "回车关闭窗口"

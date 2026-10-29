# 停止 AI 伙伴服务（保留 QQ 客户端运行，如需退出 QQ 请手动关闭）
# 注意：MaiBot 的实际运行时是 python.exe（uv 的 maibot.exe 只是启动器），
#       必须按命令行匹配 python 进程：启动器、核心运行时、插件运行器三形态都要杀。
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=== 停止 AI 伙伴服务 ===" -ForegroundColor Cyan

Write-Host "停止 MaiBot（启动器 + 核心运行时 + 插件运行器）..."
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "src\.runtime|plugin_runtime|maibot\.exe" } |
    ForEach-Object {
        Write-Host "  终止 PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
taskkill /IM maibot.exe /T /F 2>$null | Out-Null

Write-Host "停止语音服务（GPT-SoVITS 9881 + 聚合服务 9880，丁美桐音色）..."
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "voice-server|api_v2|embedding-server" } |
    ForEach-Object {
        Write-Host "  终止 PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Write-Host "停止 SnowLuma（按可执行文件路径匹配 + 端口兜底）..."
$killed = @()
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "SnowLuma" } |
    ForEach-Object {
        if ($killed -notcontains $_.ProcessId) {
            Write-Host "  终止 PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            $killed += $_.ProcessId
        }
    }
# 兜底：谁在监听 5099/3100/3101 就是谁是 SnowLuma
foreach ($port in 5099, 3100, 3101) {
    Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | ForEach-Object {
        if ($killed -notcontains $_.OwningProcess) {
            Write-Host "  终止端口 $port 占用者 PID $($_.OwningProcess)"
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            $killed += $_.OwningProcess
        }
    }
}

# 清理可能残留的记忆锁，避免下次启动时 A_Memorix 初始化失败
$lock = "D:\code2\AI伙伴\maibot\data\a-memorix\.a_memorix_runtime_writer.lock"
if (Test-Path $lock) { Remove-Item $lock -Force -ErrorAction SilentlyContinue }

Write-Host "完成。QQ 客户端保持运行。"
Write-Host ""
Read-Host "回车关闭窗口"

# RedditNarratoAI Windows一键安装脚本
# 运行方式: 右键 -> 使用PowerShell运行

param(
    [string]$InstallPath = "D:\RedditNarratoAI"
)

$ErrorActionPreference = "Stop"

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  RedditNarratoAI 一键安装脚本" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# 1. 创建目录
Write-Host "`n[1/6] 创建目录..." -ForegroundColor Yellow
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
}
Set-Location $InstallPath
Write-Host "安装目录: $InstallPath" -ForegroundColor Green

# 2. 检查Python
Write-Host "`n[2/6] 检查Python..." -ForegroundColor Yellow
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $result = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = $cmd
            Write-Host "找到: $result" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $pythonCmd) {
    Write-Host "未安装Python，请先从 https://python.org 下载安装" -ForegroundColor Red
    Write-Host "安装时记得勾选 'Add Python to PATH'" -ForegroundColor Yellow
    Read-Host "按Enter退出"
    exit 1
}

# 3. 克隆/更新项目
Write-Host "`n[3/6] 获取项目文件..." -ForegroundColor Yellow
$repoUrl = "https://github.com/yihui-ai/RedditNarratoAI.git"
if (Test-Path ".git") {
    Write-Host "项目已存在，更新中..." -ForegroundColor Green
    git pull
} else {
    Write-Host "克隆项目..." -ForegroundColor Green
    git clone $repoUrl .
}

# 4. 安装依赖
Write-Host "`n[4/6] 安装Python依赖..." -ForegroundColor Yellow
& $pythonCmd -m pip install --upgrade pip --quiet
& $pythonCmd -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖安装失败，尝试不使用quiet模式..." -ForegroundColor Red
    & $pythonCmd -m pip install -r requirements.txt
}

# 5. 安装FFmpeg
Write-Host "`n[5/6] 检查FFmpeg..." -ForegroundColor Yellow
$ffmpegCmd = $null
foreach ($cmd in @("ffmpeg", "ffmpeg.exe")) {
    try {
        $null = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($?) { $ffmpegCmd = $cmd; break }
    } catch {}
}
if (-not $ffmpegCmd) {
    Write-Host "FFmpeg未安装，使用winget安装..." -ForegroundColor Yellow
    winget install ffmpeg --accept-source-urls --accept-package-agreements -s winget
}

# 6. 配置
Write-Host "`n[6/6] 配置..." -ForegroundColor Yellow
if (-not (Test-Path "config.toml")) {
    Copy-Item "config.example.toml" "config.toml"
    Write-Host "已创建config.toml，请编辑填入Reddit凭证" -ForegroundColor Green
} else {
    Write-Host "config.toml已存在" -ForegroundColor Green
}

# 检查Ollama
Write-Host "`n检查Ollama..." -ForegroundColor Yellow
$ollamaRunning = $null -ne (Get-Process -Name "ollama" -ErrorAction SilentlyContinue)
if (-not $ollamaRunning) {
    Write-Host "提示: Ollama未运行，请运行: ollama serve" -ForegroundColor Yellow
}

Write-Host "`n======================================" -ForegroundColor Cyan
Write-Host "  安装完成!" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host @"

下一步:
1. 编辑 config.toml 填入 Reddit API 凭证
2. 运行: streamlit run webui.py
"@ -ForegroundColor White

Read-Host "按Enter启动Web界面..."
streamlit run webui.py

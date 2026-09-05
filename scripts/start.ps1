$ErrorActionPreference = "Stop"

# ============================================================
# Configuration
# ============================================================

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$FrontendUrl = "http://127.0.0.1:3000"
$FrontendHealthUrl = "http://127.0.0.1:3000/api/health"
$ApiHealthUrl = "http://127.0.0.1:8000/health"

$CheckpointDirectory = Join-Path $Root "checkpoints"
$CheckpointPath = Join-Path $CheckpointDirectory "bag_detector.pth"
$CheckpointTempPath = "$CheckpointPath.part"

$DefaultCheckpointUrl = "https://github.com/200kgsquat/bag_counter/releases/latest/download/bag_detector.pth"

$CheckpointUrl = if ($env:BAG_COUNTER_CHECKPOINT_URL) {
    $env:BAG_COUNTER_CHECKPOINT_URL
}
else {
    $DefaultCheckpointUrl
}


# ============================================================
# Helpers
# ============================================================

function Write-Step {
    param(
        [string]$Message
    )

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  $Message"
    Write-Host "============================================================"
    Write-Host ""
}


function Write-Ok {
    param(
        [string]$Message
    )

    Write-Host "[OK] $Message" -ForegroundColor Green
}


function Write-Warn {
    param(
        [string]$Message
    )

    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}


function Write-Fail {
    param(
        [string]$Message
    )

    Write-Host "[ERROR] $Message" -ForegroundColor Red
}


function Test-DockerEngine {
    docker info *> $null

    return ($LASTEXITCODE -eq 0)
}


function Show-DockerLogs {
    Write-Host ""
    Write-Host "Docker service status:"
    Write-Host ""

    docker compose ps

    Write-Host ""
    Write-Host "API logs:"
    Write-Host ""

    docker compose logs --tail=100 api

    Write-Host ""
    Write-Host "Worker logs:"
    Write-Host ""

    docker compose logs --tail=100 worker

    Write-Host ""
    Write-Host "Frontend logs:"
    Write-Host ""

    docker compose logs --tail=100 frontend
}


function Wait-HttpEndpoint {
    param(
        [string]$Url,
        [int]$Attempts = 90,
        [int]$DelaySeconds = 2
    )

    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            $Response = Invoke-WebRequest `
                -Uri $Url `
                -UseBasicParsing `
                -TimeoutSec 3

            if ($Response.StatusCode -eq 200) {
                Write-Host ""
                return $true
            }
        }
        catch {
            # Service is still starting.
        }

        Write-Host -NoNewline "."

        Start-Sleep -Seconds $DelaySeconds
    }

    Write-Host ""

    return $false
}


# ============================================================
# Banner
# ============================================================

Clear-Host

Write-Host ""
Write-Host "============================================================"
Write-Host "                  BAG COUNTER STARTER"
Write-Host "============================================================"
Write-Host ""
Write-Host "This script will automatically:"
Write-Host ""
Write-Host "  1. Check Docker"
Write-Host "  2. Start Docker Desktop if necessary"
Write-Host "  3. Check/download the ML checkpoint"
Write-Host "  4. Build Docker images"
Write-Host "  5. Start Redis, FastAPI, Celery and frontend"
Write-Host "  6. Verify ML worker and GPU"
Write-Host "  7. Wait until the application is healthy"
Write-Host "  8. Open the web interface"
Write-Host ""


# ============================================================
# 1. Docker CLI
# ============================================================

Write-Step "Checking Docker installation"

$DockerCommand = Get-Command docker -ErrorAction SilentlyContinue

if (-not $DockerCommand) {
    Write-Fail "Docker was not found."

    Write-Host ""
    Write-Host "Install Docker Desktop:"
    Write-Host "https://www.docker.com/products/docker-desktop/"
    Write-Host ""
    Write-Host "Then run start.bat again."

    exit 1
}

Write-Ok "Docker CLI found"


# ============================================================
# 2. Docker Engine
# ============================================================

Write-Step "Checking Docker Engine"

if (-not (Test-DockerEngine)) {
    Write-Warn "Docker Engine is not running"

    $DockerDesktopCandidates = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
    )

    $DockerDesktopPath = $null

    foreach ($Candidate in $DockerDesktopCandidates) {
        if (Test-Path $Candidate) {
            $DockerDesktopPath = $Candidate
            break
        }
    }

    if (-not $DockerDesktopPath) {
        Write-Fail "Docker Desktop executable was not found."

        Write-Host ""
        Write-Host "Start Docker Desktop manually and run start.bat again."

        exit 1
    }

    Write-Host "Starting Docker Desktop..."
    Start-Process $DockerDesktopPath

    Write-Host ""
    Write-Host "Waiting for Docker Engine"

    $DockerReady = $false

    for ($i = 1; $i -le 90; $i++) {
        Start-Sleep -Seconds 2

        if (Test-DockerEngine) {
            $DockerReady = $true
            break
        }

        Write-Host -NoNewline "."
    }

    Write-Host ""

    if (-not $DockerReady) {
        Write-Fail "Docker Engine did not start in time."

        Write-Host ""
        Write-Host "Try:"
        Write-Host ""
        Write-Host "    wsl --shutdown"
        Write-Host ""
        Write-Host "Then restart Docker Desktop."

        exit 1
    }
}

Write-Ok "Docker Engine is running"


# ============================================================
# 3. Docker Compose
# ============================================================

Write-Step "Checking Docker Compose"

docker compose version *> $null

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker Compose is not available."
    exit 1
}

Write-Ok "Docker Compose is available"


# ============================================================
# 4. Model checkpoint
# ============================================================

Write-Step "Checking ML model checkpoint"

New-Item `
    -ItemType Directory `
    -Force `
    -Path $CheckpointDirectory `
    | Out-Null

$CheckpointValid = $false

if (Test-Path $CheckpointPath) {
    $CheckpointSize = (Get-Item $CheckpointPath).Length

    if ($CheckpointSize -gt 1MB) {
        $CheckpointValid = $true

        $CheckpointSizeMb = [math]::Round(
            $CheckpointSize / 1MB,
            1
        )

        Write-Ok "Checkpoint found ($CheckpointSizeMb MB)"
    }
    else {
        Write-Warn "Existing checkpoint looks invalid."
        Remove-Item $CheckpointPath -Force
    }
}


if (-not $CheckpointValid) {
    Write-Host "Checkpoint not found."
    Write-Host ""
    Write-Host "Downloading:"
    Write-Host $CheckpointUrl
    Write-Host ""

    if (Test-Path $CheckpointTempPath) {
        Remove-Item $CheckpointTempPath -Force
    }

    try {
        Invoke-WebRequest `
            -Uri $CheckpointUrl `
            -OutFile $CheckpointTempPath `
            -UseBasicParsing
    }
    catch {
        if (Test-Path $CheckpointTempPath) {
            Remove-Item $CheckpointTempPath -Force
        }

        Write-Fail "Failed to download checkpoint."

        Write-Host ""
        Write-Host "Expected GitHub Release asset:"
        Write-Host ""
        Write-Host "    bag_detector.pth"
        Write-Host ""
        Write-Host "Error:"
        Write-Host $_.Exception.Message

        exit 1
    }

    if (-not (Test-Path $CheckpointTempPath)) {
        Write-Fail "Checkpoint download did not create a file."
        exit 1
    }

    $DownloadedSize = (Get-Item $CheckpointTempPath).Length

    if ($DownloadedSize -lt 1MB) {
        Remove-Item $CheckpointTempPath -Force

        Write-Fail "Downloaded checkpoint looks invalid."
        exit 1
    }

    Move-Item `
        -Path $CheckpointTempPath `
        -Destination $CheckpointPath `
        -Force

    $CheckpointSizeMb = [math]::Round(
        (Get-Item $CheckpointPath).Length / 1MB,
        1
    )

    Write-Ok "Checkpoint downloaded ($CheckpointSizeMb MB)"
}


# ============================================================
# 5. Build and recreate Docker services
# ============================================================

Write-Step "Building and starting Bag Counter"

Write-Host "The first launch can take several minutes."
Write-Host ""

docker compose up `
    --build `
    -d `
    --remove-orphans `
    --force-recreate


if ($LASTEXITCODE -ne 0) {
    Write-Fail "Docker Compose failed."

    Show-DockerLogs

    exit 1
}

Write-Ok "Docker Compose finished"


# ============================================================
# 6. Wait for FastAPI
# ============================================================

Write-Step "Waiting for FastAPI"

Write-Host "Waiting for:"
Write-Host $ApiHealthUrl
Write-Host ""

$ApiReady = Wait-HttpEndpoint `
    -Url $ApiHealthUrl `
    -Attempts 90 `
    -DelaySeconds 2


if (-not $ApiReady) {
    Write-Fail "FastAPI did not become healthy."

    Show-DockerLogs

    exit 1
}

Write-Ok "FastAPI is healthy"


# ============================================================
# 7. Restart frontend proxy after API is ready
# ============================================================

Write-Step "Refreshing frontend proxy"

docker compose restart frontend

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to restart frontend."

    Show-DockerLogs

    exit 1
}

Write-Ok "Frontend proxy restarted"

Start-Sleep -Seconds 2


# ============================================================
# 8. Check Celery worker
# ============================================================

Write-Step "Checking ML worker"

$RunningServices = @(
    docker compose ps `
        --services `
        --status running
)

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Could not inspect Docker services."

    Show-DockerLogs

    exit 1
}


if ($RunningServices -notcontains "worker") {
    Write-Fail "Celery worker is not running."

    Show-DockerLogs

    exit 1
}

Write-Ok "Celery worker is running"


# ============================================================
# 9. Python / MMDetection / GPU check
# ============================================================

Write-Host ""
Write-Host "Checking Python, OpenCV, MMDetection and GPU..."
Write-Host ""

$PythonCheck = "import os, sys, cv2, torch, mmcv, mmdet; checkpoint='/app/checkpoints/bag_detector.pth'; assert os.path.isfile(checkpoint), f'Checkpoint not visible inside worker: {checkpoint}'; assert torch.cuda.is_available(), 'CUDA is not available inside the Docker worker'; print('Python:', sys.version.split()[0]); print('OpenCV:', cv2.__version__); print('MMCV:', mmcv.__version__); print('MMDetection:', mmdet.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0)); print('Checkpoint:', checkpoint)"

docker compose exec -T worker python -c $PythonCheck


if ($LASTEXITCODE -ne 0) {
    Write-Fail "ML worker runtime check failed."

    Write-Host ""
    Write-Host "Possible causes:"
    Write-Host ""
    Write-Host "  - NVIDIA driver is missing"
    Write-Host "  - Docker GPU support is unavailable"
    Write-Host "  - checkpoint is missing"
    Write-Host "  - Python/MMDetection dependency failed"
    Write-Host ""

    Show-DockerLogs

    exit 1
}

Write-Ok "ML worker and GPU are ready"


# ============================================================
# 10. Wait for frontend / Nginx proxy
# ============================================================

Write-Step "Waiting for frontend"

Write-Host "Waiting for:"
Write-Host $FrontendHealthUrl
Write-Host ""

$FrontendReady = Wait-HttpEndpoint `
    -Url $FrontendHealthUrl `
    -Attempts 45 `
    -DelaySeconds 2


if (-not $FrontendReady) {
    Write-Fail "Frontend did not become ready."

    Show-DockerLogs

    exit 1
}

Write-Ok "Frontend is ready"


# ============================================================
# 11. Final status
# ============================================================

Write-Step "Bag Counter is ready"

docker compose ps

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host ""
Write-Host "Frontend:"
Write-Host "    $FrontendUrl"
Write-Host ""
Write-Host "Swagger:"
Write-Host "    http://127.0.0.1:8000/docs"
Write-Host ""
Write-Host "API:"
Write-Host "    $ApiHealthUrl"
Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host ""


# ============================================================
# 12. Open browser
# ============================================================

Write-Host "Opening Bag Counter in your browser..."
Write-Host ""

Start-Process $FrontendUrl

Write-Ok "Startup completed successfully"

Write-Host ""
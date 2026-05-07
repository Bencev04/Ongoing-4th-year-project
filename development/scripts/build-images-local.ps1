# Build Docker images locally - simulates GitLab CI build-images stage
# 
# Usage:
#   .\scripts\build-images-local.ps1
#   .\scripts\build-images-local.ps1 -ConfigFile "build-config.local.json"
#   .\scripts\build-images-local.ps1 -Registry "mydockerhub" -Push
#   .\scripts\build-images-local.ps1 -Username "user" -Password "pass" -Push
#
# Optional local configuration file format (build-config.local.json, ignored by git):
# {
#   "registry": "mydockerhub/myproject",
#   "username": "your-username",
#   "password": "your-password",
#   "push": true,
#   "noCache": false,
#   "service": "auth-service"
# }
#
# Parameters:
#   -ConfigFile  Path to JSON config file (overrides command-line args)
#   -Registry    Docker registry prefix (default: "crm" for local-only)
#   -Username    Docker Hub username (for login)
#   -Password    Docker Hub password (for login)
#   -Push        Push images to registry after build
#   -NoCache     Build without using cached layers
#   -Service     Build only one service (e.g., "auth-service")

param(
    [string]$ConfigFile,
    [string]$Registry = "crm",
    [string]$Username,
    [string]$Password,
    [switch]$Push,
    [switch]$NoCache,
    [string]$Service
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$servicesDir = Join-Path $projectRoot "services"

# Load configuration from file if provided
if ($ConfigFile) {
    if (-not (Test-Path -Path $ConfigFile)) {
        Write-Host "ERROR: Config file not found: $ConfigFile" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Loading configuration from: $ConfigFile" -ForegroundColor Cyan
    try {
        $config = Get-Content -Path $ConfigFile -Raw | ConvertFrom-Json
        
        if ($config.registry) { $Registry = $config.registry }
        if ($config.username) { $Username = $config.username }
        if ($config.password) { $Password = $config.password }
        if ($config.push -eq $true) { $Push = $true }
        if ($config.noCache -eq $true) { $NoCache = $true }
        if ($config.service) { $Service = $config.service }
        
        Write-Host "Configuration loaded successfully" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to parse config file: $_" -ForegroundColor Red
        exit 1
    }
}

$IMAGE_VERSION = & git rev-parse --short HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to get git commit SHA" -ForegroundColor Red
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Building Docker Images (Local)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Registry:      $Registry" -ForegroundColor Yellow
Write-Host "Image Version: $IMAGE_VERSION" -ForegroundColor Yellow
Write-Host "Push to Registry: $Push" -ForegroundColor Yellow
Write-Host ""

if ($Username -and $Password) {
    Write-Host "Logging into Docker registry..." -ForegroundColor Cyan
    $Password | docker login -u "$Username" --password-stdin
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker login failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "Docker login successful" -ForegroundColor Green
    Write-Host ""
}

$SERVICES = @(
    "nginx",
    "auth-service",
    "user-db-access-service",
    "customer-db-access-service",
    "job-db-access-service",
    "user-bl-service",
    "job-bl-service",
    "customer-bl-service",
    "admin-bl-service",
    "frontend"
)

if ($Service) {
    if ($SERVICES -notcontains $Service) {
        Write-Host "Service '$Service' not found. Available services: $($SERVICES -join ', ')" -ForegroundColor Red
        exit 1
    }
    $SERVICES = @($Service)
    Write-Host "Building single service: $Service" -ForegroundColor Cyan
    Write-Host ""
}

$failedServices = @()
$successfulServices = @()

foreach ($svc in $SERVICES) {
    $dockerfile = Join-Path $servicesDir "$svc\Dockerfile"
    
    if (-not (Test-Path $dockerfile)) {
        Write-Host "WARNING: Dockerfile not found: $dockerfile (skipping)" -ForegroundColor Yellow
        continue
    }
    
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "Building: $svc" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    
    # Build image names - use dashes instead of slashes to avoid nested paths on Docker Hub
    $imageName1 = "$Registry-$svc`:$IMAGE_VERSION"
    $imageName2 = "$Registry-$svc`:latest"
    
    $buildArgs = @(
        "build",
        "-f", "services/$svc/Dockerfile",
        "-t", $imageName1,
        "-t", $imageName2
    )
    
    if ($NoCache) {
        $buildArgs += "--no-cache"
    }
    
    $buildArgs += "services/"
    
    Write-Host "Running: docker $($buildArgs -join ' ')" -ForegroundColor Gray
    Write-Host ""
    
    & docker @buildArgs
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: Build failed for $svc" -ForegroundColor Red
        $failedServices += $svc
        continue
    }
    
    Write-Host "SUCCESS: Build successful for $svc" -ForegroundColor Green
    Write-Host "  - Tagged as: $imageName1" -ForegroundColor Green
    Write-Host "  - Tagged as: $imageName2" -ForegroundColor Green
    
    if ($Push) {
        Write-Host "Pushing images..." -ForegroundColor Cyan
        
        & docker push $imageName1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED: Push failed for $imageName1" -ForegroundColor Red
            $failedServices += "$svc (push)"
            continue
        }
        Write-Host "SUCCESS: Pushed $imageName1" -ForegroundColor Green
        
        & docker push $imageName2
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED: Push failed for $imageName2" -ForegroundColor Red
            $failedServices += "$svc (push)"
            continue
        }
        Write-Host "SUCCESS: Pushed $imageName2" -ForegroundColor Green
    }
    
    $successfulServices += $svc
    Write-Host ""
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Build Summary" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Successful: $($successfulServices.Count)/$($SERVICES.Count)" -ForegroundColor Green
foreach ($svc in $successfulServices) {
    Write-Host "  PASS: $svc" -ForegroundColor Green
}

if ($failedServices.Count -gt 0) {
    Write-Host "Failed: $($failedServices.Count)" -ForegroundColor Red
    foreach ($svc in $failedServices) {
        Write-Host "  FAIL: $svc" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "All builds completed successfully!" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Built Images" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

& docker images | Where-Object { $_ -match $Registry }

Write-Host ""
Write-Host "To verify an image, run:" -ForegroundColor Yellow
Write-Host "  docker inspect $Registry/auth-service:$IMAGE_VERSION"
Write-Host ""
Write-Host "To run the full stack with these images:" -ForegroundColor Yellow
Write-Host "  docker-compose up"

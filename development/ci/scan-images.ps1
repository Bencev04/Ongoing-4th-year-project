# =============================================================================
# Trivy Image Scanner - Find CRITICAL vulnerabilities
# =============================================================================
# Scans all service images to identify which has CRITICAL vulnerabilities

$services = @(
    "nginx-gateway",
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

$imageBase = "yr4-projectdevelopmentrepo"
$imageTag = "latest"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Scanning Docker Images for CRITICAL Vulnerabilities" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$criticalFound = @()
$cleanImages = @()

foreach ($service in $services) {
    $imageName = "$imageBase/${service}:$imageTag"
    
    Write-Host "Scanning: $service" -ForegroundColor Yellow
    Write-Host "-----------------------------------------"
    
    # Check if image exists locally
    $imageExists = docker images -q $imageName
    if (-not $imageExists) {
        Write-Host "  [SKIP] Image not found locally" -ForegroundColor Gray
        Write-Host ""
        continue
    }
    
    # Run Trivy scan for CRITICAL only
    $output = docker run --rm -v /var/run/docker.sock:/var/run/docker.sock `
        aquasec/trivy:latest image `
        --severity CRITICAL `
        --ignore-unfixed `
        --format json `
        --quiet `
        $imageName | ConvertFrom-Json
    
    # Check if vulnerabilities were found
    $criticalCount = 0
    foreach ($result in $output.Results) {
        if ($result.Vulnerabilities) {
            $criticalCount += $result.Vulnerabilities.Count
        }
    }
    
    if ($criticalCount -gt 0) {
        Write-Host "  [FAIL] $criticalCount CRITICAL vulnerabilities found!" -ForegroundColor Red
        $criticalFound += $service
        
        # Show table format for this service
        docker run --rm -v /var/run/docker.sock:/var/run/docker.sock `
            aquasec/trivy:latest image `
            --severity CRITICAL `
            --ignore-unfixed `
            --format table `
            $imageName
    } else {
        Write-Host "  [PASS] No CRITICAL vulnerabilities" -ForegroundColor Green
        $cleanImages += $service
    }
    
    Write-Host ""
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "SCAN SUMMARY" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Clean images: $($cleanImages.Count)" -ForegroundColor Green
foreach ($img in $cleanImages) {
    Write-Host "  ✓ $img" -ForegroundColor Green
}
Write-Host ""
Write-Host "Images with CRITICAL vulnerabilities: $($criticalFound.Count)" -ForegroundColor Red
foreach ($img in $criticalFound) {
    Write-Host "  ✗ $img" -ForegroundColor Red
}

if ($criticalFound.Count -gt 0) {
    Write-Host ""
    Write-Host "ACTION REQUIRED: Fix CRITICAL vulnerabilities in the services listed above" -ForegroundColor Yellow
    exit 1
} else {
    Write-Host ""
    Write-Host "All scanned images are clean!" -ForegroundColor Green
    exit 0
}

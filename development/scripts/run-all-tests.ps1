# Run all unit tests across all microservices
#
# Usage:
#   .\scripts\run-all-tests.ps1
#   .\scripts\run-all-tests.ps1 -Coverage
#   .\scripts\run-all-tests.ps1 -StopOnError

param(
    [switch]$Coverage,
    [switch]$StopOnError
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$servicesDir = Join-Path $projectRoot "services"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python virtual environment not found at: $pythonExe"
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Running All Tests" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$totalPassed = 0
$totalFailed = 0
$totalServices = 0
$failedServices = @()

$serviceDirs = Get-ChildItem -Path $servicesDir -Directory | Where-Object {
    $_.Name -ne "nginx" -and $_.Name -ne "shared"
}

foreach ($serviceDir in $serviceDirs) {
    $serviceName = $serviceDir.Name
    $testPath1 = Join-Path $serviceDir.FullName "app\tests"
    $testPath2 = Join-Path $serviceDir.FullName "tests"
    
    $testPath = $null
    $relativeTestPath = $null
    
    if (Test-Path $testPath1) {
        $testPath = $testPath1
        $relativeTestPath = "app/tests/"
    } elseif (Test-Path $testPath2) {
        $testPath = $testPath2
        $relativeTestPath = "tests/"
    }
    
    if ($testPath) {
        $totalServices++
        Write-Host "[$totalServices] Testing: " -NoNewline -ForegroundColor Yellow
        Write-Host "$serviceName" -ForegroundColor White
        Write-Host "    Path: $relativeTestPath" -ForegroundColor Gray
        
        Push-Location $serviceDir.FullName
        
        $pytestArgs = @("-m", "pytest", $relativeTestPath, "-v", "--tb=short")
        
        if ($Coverage) {
            $pytestArgs += @("--cov=app", "--cov-report=term-missing", "--cov-report=html")
        }
        
        $output = & $pythonExe @pytestArgs 2>&1
        $exitCode = $LASTEXITCODE
        
        $resultLine = $output | Select-String "(\d+) passed" | Select-Object -Last 1
        
        if ($resultLine) {
            $passed = 0
            $failed = 0
            
            if ($resultLine -match "(\d+) passed") {
                $passed = [int]$matches[1]
            }
            if ($resultLine -match "(\d+) failed") {
                $failed = [int]$matches[1]
            }
            
            $totalPassed += $passed
            $totalFailed += $failed
            
            if ($exitCode -eq 0) {
                Write-Host "    OK " -NoNewline -ForegroundColor Green
                Write-Host "$passed tests passed" -ForegroundColor Green
            } else {
                Write-Host "    FAIL " -NoNewline -ForegroundColor Red
                Write-Host "$failed tests failed, $passed passed" -ForegroundColor Red
                $failedServices += $serviceName
                
                $failures = $output | Select-String "FAILED" | ForEach-Object { $_.Line }
                if ($failures) {
                    Write-Host "    Failures:" -ForegroundColor Red
                    foreach ($failure in $failures) {
                        Write-Host "      $failure" -ForegroundColor DarkRed
                    }
                }
                
                if ($StopOnError) {
                    Pop-Location
                    Write-Host ""
                    Write-Host "Stopping due to test failure" -ForegroundColor Red
                    exit 1
                }
            }
        } else {
            Write-Host "    WARN Could not parse test results" -ForegroundColor Yellow
        }
        
        Pop-Location
        Write-Host ""
    }
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Test Summary" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Services tested: " -NoNewline
Write-Host "$totalServices" -ForegroundColor White
Write-Host "Total passed:    " -NoNewline
Write-Host "$totalPassed" -ForegroundColor Green
Write-Host "Total failed:    " -NoNewline
Write-Host "$totalFailed" -ForegroundColor $(if ($totalFailed -gt 0) { "Red" } else { "Green" })

if ($failedServices.Count -gt 0) {
    Write-Host ""
    Write-Host "Failed services:" -ForegroundColor Red
    foreach ($service in $failedServices) {
        Write-Host "  - $service" -ForegroundColor Red
    }
    exit 1
} else {
    Write-Host ""
    Write-Host "All tests passed!" -ForegroundColor Green
    exit 0
}

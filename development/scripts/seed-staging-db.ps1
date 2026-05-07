[CmdletBinding()]
param(
    [string]$Region = "eu-west-1",
    [string]$ClusterName = "yr4-project-staging-eks",
    [string]$Namespace = "year4-project-staging",
    [string]$DbSecretName = "db-credentials",
    [string]$SeedPodName = "seed-runner",
    [string]$SqlFile = "",
    [switch]$SkipKubeconfig,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Decode-Base64String {
    param([Parameter(Mandatory = $true)][string]$Value)
    return [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($Value))
}

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

if ([string]::IsNullOrWhiteSpace($SqlFile)) {
    $SqlFile = Join-Path $PSScriptRoot "seed-demo-data.sql"
}

Write-Host "=== Staging DB Seed Script ===" -ForegroundColor Cyan
Write-Host "Region:      $Region"
Write-Host "Cluster:     $ClusterName"
Write-Host "Namespace:   $Namespace"
Write-Host "DB secret:   $DbSecretName"
Write-Host "SQL file:    $SqlFile"

Require-Command -Name "kubectl"
Require-Command -Name "aws"

if (-not (Test-Path -Path $SqlFile -PathType Leaf)) {
    throw "SQL file not found: $SqlFile"
}

if (-not $SkipKubeconfig) {
    Write-Host "Checking EKS cluster existence..." -ForegroundColor Yellow
    $clustersJson = aws eks list-clusters --region $Region --output json | ConvertFrom-Json
    if ($ClusterName -notin $clustersJson.clusters) {
        throw "Cluster '$ClusterName' not found in region '$Region'. Run infra/deploy pipeline first."
    }

    Write-Host "Updating kubeconfig for staging cluster..." -ForegroundColor Yellow
    aws eks update-kubeconfig --name $ClusterName --region $Region | Out-Host
}

Write-Host "Validating Kubernetes access..." -ForegroundColor Yellow
kubectl get namespace $Namespace | Out-Host

Write-Host "Loading DB credentials from secret '$DbSecretName'..." -ForegroundColor Yellow
$secretObj = kubectl get secret $DbSecretName -n $Namespace -o json | ConvertFrom-Json

$dbHost = Decode-Base64String -Value $secretObj.data.host
$dbPort = Decode-Base64String -Value $secretObj.data.port
$dbUser = Decode-Base64String -Value $secretObj.data.username
$dbPass = Decode-Base64String -Value $secretObj.data.password
$dbName = Decode-Base64String -Value $secretObj.data.database

Write-Host "Database host: $dbHost"
Write-Host "Database port: $dbPort"
Write-Host "Database user: $dbUser"
Write-Host "Database name: $dbName"
Write-Host "Password:      [hidden]"

if ($DryRun) {
    Write-Host "Dry run enabled. No changes made." -ForegroundColor Green
    exit 0
}

Write-Host "Cleaning up any previous seed pod..." -ForegroundColor Yellow
kubectl delete pod $SeedPodName -n $Namespace --ignore-not-found=true | Out-Host

Write-Host "Running seed SQL via temporary postgres client pod..." -ForegroundColor Yellow
Get-Content -Raw $SqlFile |
    kubectl run $SeedPodName --image=postgres:16 --namespace=$Namespace --restart=Never -i --rm --env="PGPASSWORD=$dbPass" --command -- psql -v ON_ERROR_STOP=1 -h $dbHost -p $dbPort -U $dbUser -d $dbName

Write-Host "Seed completed successfully." -ForegroundColor Green

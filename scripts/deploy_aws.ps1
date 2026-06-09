param(
    [string]$Region = "ap-southeast-1",
    [string]$ImageTag = "",
    [switch]$ApplyInfrastructure
)

$ErrorActionPreference = "Stop"

if (-not $ImageTag) {
    $ImageTag = (git rev-parse --short HEAD).Trim()
}

$root = Split-Path -Parent $PSScriptRoot
$tfDir = Join-Path $root "infra/aws"

Write-Host "Using image tag: $ImageTag"
aws sts get-caller-identity | Out-Null

Push-Location $tfDir
try {
    terraform init
    terraform apply `
        -target=aws_ecr_repository.scraper `
        -target=aws_ecr_repository.dashboard `
        -var="aws_region=$Region" `
        -var="image_tag=$ImageTag" `
        -var="dashboard_image_tag=$ImageTag"

    $scraperRepo = (terraform output -raw ecr_repository_url).Trim()
    $dashboardRepo = (terraform output -raw dashboard_ecr_repository_url).Trim()
}
finally {
    Pop-Location
}

$accountId = (aws sts get-caller-identity --query Account --output text).Trim()
aws ecr get-login-password --region $Region |
    docker login --username AWS --password-stdin "$accountId.dkr.ecr.$Region.amazonaws.com"

Push-Location $root
try {
    docker build -f Dockerfile.lambda -t "${scraperRepo}:${ImageTag}" .
    docker push "${scraperRepo}:${ImageTag}"

    docker build -f Dockerfile -t "${dashboardRepo}:${ImageTag}" .
    docker push "${dashboardRepo}:${ImageTag}"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Images pushed."
Write-Host "Next: create/update the DATABASE_URL secret, run migrations, then apply the full stack."
Write-Host "See DEPLOYMENT_AWS.md for exact commands."

if ($ApplyInfrastructure) {
    Push-Location $tfDir
    try {
        terraform apply `
            -var="aws_region=$Region" `
            -var="image_tag=$ImageTag" `
            -var="dashboard_image_tag=$ImageTag"
    }
    finally {
        Pop-Location
    }
}

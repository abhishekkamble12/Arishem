<#
.SYNOPSIS
    Deploys the Arishem stack to AWS.

.DESCRIPTION
    Puts the two application secrets into SSM Parameter Store as SecureStrings
    (free, and never written into the CloudFormation template or the AMI), then
    creates or updates the stack.

    Secrets are read from the repository .env so they are never passed on the
    command line, where they would land in your shell history.

.EXAMPLE
    ./deploy/deploy.ps1 -AlertEmail you@example.com
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AlertEmail,
    [string]$StackName = 'arishem',
    [string]$Region = 'ap-south-1',
    [string]$InstanceType = 't4g.small',
    [ValidateSet('arm64', 'x86_64')][string]$Architecture = 'arm64',
    [string]$DomainName = '',
    [int]$MonthlyBudgetUSD = 15,
    [string]$RepoUrl = 'https://github.com/abhishekkamble12/Arishem.git',
    [string]$RepoBranch = 'main'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

# ── Read .env without printing anything from it ───────────────────────────────
$envPath = Join-Path $repoRoot '.env'
if (-not (Test-Path $envPath)) { throw "No .env at $envPath" }

$envVars = @{}
foreach ($line in Get-Content $envPath) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
    $k, $v = $t.Split('=', 2)
    $envVars[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
}

foreach ($k in 'GROQ_API_KEY', 'AWS_Acess_key', 'AWS_secret_Acess_key') {
    if (-not $envVars[$k]) { throw "$k missing from .env" }
}

$env:AWS_ACCESS_KEY_ID = $envVars['AWS_Acess_key']
$env:AWS_SECRET_ACCESS_KEY = $envVars['AWS_secret_Acess_key']
$env:AWS_DEFAULT_REGION = $Region

# A production SECRET_KEY distinct from the development one. Generated once and
# then reused, so existing sessions survive a redeploy.
$existing = aws ssm get-parameter --name /arishem/secret_key --with-decryption `
    --query Parameter.Value --output text 2>$null
if ($LASTEXITCODE -eq 0 -and $existing) {
    Write-Host 'Reusing the existing production SECRET_KEY.'
    $secretKey = $existing
}
else {
    Write-Host 'Generating a new production SECRET_KEY.'
    $bytes = [byte[]]::new(48)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $secretKey = [Convert]::ToBase64String($bytes).TrimEnd('=')
}

Write-Host 'Storing secrets in SSM Parameter Store...'
aws ssm put-parameter --name /arishem/secret_key --type SecureString `
    --value $secretKey --overwrite --output text | Out-Null
aws ssm put-parameter --name /arishem/groq_api_key --type SecureString `
    --value $envVars['GROQ_API_KEY'] --overwrite --output text | Out-Null

Write-Host "Deploying stack '$StackName' to $Region (this takes 15-30 minutes on first run)..."
aws cloudformation deploy `
    --template-file (Join-Path $PSScriptRoot 'cloudformation.yml') `
    --stack-name $StackName `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        AlertEmail=$AlertEmail `
        InstanceType=$InstanceType `
        Architecture=$Architecture `
        DomainName=$DomainName `
        MonthlyBudgetUSD=$MonthlyBudgetUSD `
        RepoUrl=$RepoUrl `
        RepoBranch=$RepoBranch

if ($LASTEXITCODE -ne 0) { throw 'Stack deployment failed. See the CloudFormation events in the console.' }

Write-Host "`nStack outputs:"
aws cloudformation describe-stacks --stack-name $StackName `
    --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table

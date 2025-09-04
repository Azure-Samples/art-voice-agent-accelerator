# ==============================================================================
# Environment File Generation from Terraform Remote State (PowerShell)
# ==============================================================================
# This script extracts values from Terraform remote state and creates a local
# .env file matching the project's expected format.
#
# Usage:
#   .\Generate-EnvFromTerraform.ps1 [-EnvironmentName <string>] [-SubscriptionId <string>] [-Action <string>]
#
# Parameters:
#   -EnvironmentName    Environment name (default: dev)
#   -SubscriptionId     Azure subscription ID (auto-detected if not provided)
#   -Action            Action to perform: generate, update-secrets, show (default: generate)
#
# Requirements:
#   - Terraform CLI installed and configured
#   - Azure CLI installed and authenticated
#   - Terraform state properly initialized with remote backend
# ==============================================================================

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$EnvironmentName = $env:AZURE_ENV_NAME,
    
    [Parameter(Position = 1)]
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    
    [Parameter(Position = 2)]
    [ValidateSet("generate", "update-secrets", "show")]
    [string]$Action = "generate"
)

# Set error action preference
$ErrorActionPreference = "Stop"

# Configuration
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "../..")
$TerraformDir = Join-Path $ProjectRoot "infra/terraform"

# Default values
if (-not $EnvironmentName) { $EnvironmentName = "dev" }
if (-not $SubscriptionId) {
    try {
        $SubscriptionId = (az account show --query id -o tsv 2>$null)
    }
    catch {
        $SubscriptionId = ""
    }
}

$EnvFile = Join-Path $ProjectRoot ".env.$EnvironmentName"

# Logging functions
function Write-LogInfo {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Blue
}

function Write-LogSuccess {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-LogWarning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Write-LogError {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Write-LogSection {
    param([string]$Message)
    Write-Host ""
    Write-Host "🔧 $Message" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

# Validation functions
function Test-Prerequisites {
    Write-LogSection "Checking Prerequisites"
    
    # Check Terraform CLI
    try {
        $terraformVersion = terraform version 2>$null | Select-Object -First 1
        Write-LogInfo "Terraform CLI: $terraformVersion"
    }
    catch {
        Write-LogError "Terraform CLI is not installed or not in PATH"
        exit 1
    }
    
    # Check Azure CLI
    try {
        $azVersion = (az version --query '"azure-cli"' -o tsv 2>$null)
        Write-LogInfo "Azure CLI: $azVersion"
    }
    catch {
        Write-LogError "Azure CLI is not installed or not in PATH"
        exit 1
    }
    
    # Check Azure CLI authentication
    try {
        az account show 2>$null | Out-Null
    }
    catch {
        Write-LogError "Azure CLI is not authenticated. Run 'az login' first"
        exit 1
    }
    
    # Validate subscription ID
    if (-not $SubscriptionId) {
        Write-LogError "AZURE_SUBSCRIPTION_ID is not set"
        Write-LogError "Please provide it as a parameter or set the environment variable"
        exit 1
    }
    Write-LogInfo "Azure Subscription: $SubscriptionId"
    
    # Check Terraform directory
    if (-not (Test-Path $TerraformDir)) {
        Write-LogError "Terraform directory not found: $TerraformDir"
        exit 1
    }
    
    # Check Terraform initialization
    $terraformStateFile = Join-Path $TerraformDir ".terraform/terraform.tfstate"
    if (-not (Test-Path $terraformStateFile)) {
        Write-LogError "Terraform is not initialized in $TerraformDir"
        Write-LogError "Run 'terraform init' in the terraform directory first"
        exit 1
    }
    
    Write-LogSuccess "All prerequisites satisfied"
}

# Get Terraform output value with error handling (fallback function)
function Get-TerraformOutput {
    param(
        [string]$OutputName,
        [string]$DefaultValue = ""
    )
    
    Push-Location $TerraformDir
    try {
        $value = terraform output -raw $OutputName 2>$null
        if ($LASTEXITCODE -ne 0) {
            return $DefaultValue
        }
        return $value
    }
    catch {
        return $DefaultValue
    }
    finally {
        Pop-Location
    }
}

# Get all Terraform outputs in one operation for efficiency
function Get-AllTerraformOutputs {
    Push-Location $TerraformDir
    try {
        $outputsJson = terraform output -json 2>$null
        if ($LASTEXITCODE -ne 0) {
            return "{}"
        }
        return $outputsJson
    }
    catch {
        return "{}"
    }
    finally {
        Pop-Location
    }
}

# Extract specific output value from JSON with error handling
function Get-OutputValue {
    param(
        [string]$OutputsJson,
        [string]$OutputName,
        [string]$DefaultValue = ""
    )
    
    try {
        # Convert JSON string to PowerShell object
        $outputs = $OutputsJson | ConvertFrom-Json
        
        # Check if the output exists and has a value property
        if ($outputs.PSObject.Properties.Name -contains $OutputName) {
            $value = $outputs.$OutputName.value
            if ($null -ne $value -and $value -ne "") {
                return $value
            }
        }
        
        # Return default value if not found or empty
        return $DefaultValue
    }
    catch {
        # Fallback: use individual terraform output calls if JSON parsing fails
        Write-LogWarning "JSON parsing failed, falling back to individual terraform output calls"
        return Get-TerraformOutput $OutputName $DefaultValue
    }
}

# Generate environment file
function New-EnvironmentFile {
    Write-LogSection "Generating Environment File from Terraform State"
    
    Write-LogInfo "Extracting values from Terraform remote state..."
    Write-LogInfo "Target file: $EnvFile"
    
    # Get all Terraform outputs in one operation
    Write-LogInfo "Fetching all Terraform outputs..."
    $terraformOutputs = Get-AllTerraformOutputs
    
    # Create the environment file content
    $content = @"
# Generated automatically on $(Get-Date)
# Environment: $EnvironmentName
# Source: Terraform remote state
# Subscription: $SubscriptionId
# =================================================================

# Application Insights Configuration
APPLICATIONINSIGHTS_CONNECTION_STRING=$(Get-OutputValue $terraformOutputs "APPLICATIONINSIGHTS_CONNECTION_STRING")

# Azure OpenAI Configuration
AZURE_OPENAI_KEY=
AZURE_OPENAI_ENDPOINT=$(Get-OutputValue $terraformOutputs "AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=$(Get-OutputValue $terraformOutputs "AZURE_OPENAI_API_VERSION" "2025-01-01-preview")
AZURE_OPENAI_CHAT_DEPLOYMENT_ID=$(Get-OutputValue $terraformOutputs "AZURE_OPENAI_CHAT_DEPLOYMENT_ID" "gpt-4o")
AZURE_OPENAI_CHAT_DEPLOYMENT_VERSION=2024-10-01-preview

# Azure Speech Services Configuration
AZURE_SPEECH_ENDPOINT=$(Get-OutputValue $terraformOutputs "AZURE_SPEECH_ENDPOINT")
AZURE_SPEECH_KEY=
AZURE_SPEECH_RESOURCE_ID=$(Get-OutputValue $terraformOutputs "AZURE_SPEECH_RESOURCE_ID")
AZURE_SPEECH_REGION=$(Get-OutputValue $terraformOutputs "AZURE_SPEECH_REGION")
TTS_ENABLE_LOCAL_PLAYBACK=true

# Base URL Configuration
# Prompt user for BASE_URL if not set in azd env
BASE_URL="<Set this to enable ACS callbacks to the app>"

# Backend App Service URL (from Terraform output if available)
BACKEND_APP_SERVICE_URL=$(Get-OutputValue $terraformOutputs "BACKEND_APP_SERVICE_URL" "<Set this if using App Service deployment>")

# Azure Communication Services Configuration
ACS_CONNECTION_STRING=
ACS_SOURCE_PHONE_NUMBER=
ACS_ENDPOINT=$(Get-OutputValue $terraformOutputs "ACS_ENDPOINT")

# Redis Configuration
REDIS_HOST=$(Get-OutputValue $terraformOutputs "REDIS_HOSTNAME")
REDIS_PORT=$(Get-OutputValue $terraformOutputs "REDIS_PORT" "10000")
REDIS_PASSWORD=

# Azure Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER_URL=$(Get-OutputValue $terraformOutputs "AZURE_STORAGE_CONTAINER_URL")
AZURE_STORAGE_ACCOUNT_NAME=$(Get-OutputValue $terraformOutputs "AZURE_STORAGE_ACCOUNT_NAME")

# Azure Cosmos DB Configuration
AZURE_COSMOS_DATABASE_NAME=$(Get-OutputValue $terraformOutputs "AZURE_COSMOS_DATABASE_NAME" "audioagentdb")
AZURE_COSMOS_COLLECTION_NAME=$(Get-OutputValue $terraformOutputs "AZURE_COSMOS_COLLECTION_NAME" "audioagentcollection")
AZURE_COSMOS_CONNECTION_STRING=$(Get-OutputValue $terraformOutputs "AZURE_COSMOS_CONNECTION_STRING")

# Azure Identity Configuration
AZURE_SUBSCRIPTION_ID=$SubscriptionId

# Azure Resource Configuration
AZURE_RESOURCE_GROUP=$(Get-OutputValue $terraformOutputs "AZURE_RESOURCE_GROUP")
AZURE_LOCATION=$(Get-OutputValue $terraformOutputs "AZURE_LOCATION")

# Application Configuration
ACS_STREAMING_MODE=media
ENVIRONMENT=$EnvironmentName

# Logging Configuration
LOG_LEVEL=INFO
ENABLE_DEBUG=false
"@

    # Write content to file
    $content | Out-File -FilePath $EnvFile -Encoding UTF8
    
    # Generate summary
    $varCount = (Get-Content $EnvFile | Where-Object { $_ -match '^[A-Z]' }).Count
    
    Write-LogSuccess "Environment file generated successfully: $EnvFile"
    Write-LogInfo "Configuration contains $varCount variables"
    Write-Host ""
    Write-LogWarning "Note: Some values like keys and connection strings may be empty"
    Write-LogWarning "These sensitive values should be retrieved separately using Azure CLI or Key Vault"
    Write-Host ""
    Write-LogInfo "Next steps:"
    Write-Host "   1. Review the generated file: Get-Content $EnvFile"
    Write-Host "   2. Set missing sensitive values (keys, connection strings)"
    Write-Host "   3. Update BASE_URL with your actual backend URL"
    Write-Host "   4. Import the variables (see documentation for your shell)"
}

# Update environment file with secrets from Key Vault
function Update-EnvironmentWithSecrets {
    Write-LogSection "Updating Environment File with Secrets from Key Vault"
    
    if (-not (Test-Path $EnvFile)) {
        Write-LogError "Environment file $EnvFile does not exist"
        Write-LogError "Run this script first to generate the base file"
        exit 1
    }
    
    Write-LogInfo "Retrieving secrets from Azure Key Vault..."
    
    # Get Key Vault name from Terraform (single operation)
    $terraformOutputs = Get-AllTerraformOutputs
    $kvName = Get-OutputValue $terraformOutputs "AZURE_KEY_VAULT_NAME"
    
    if ($kvName -and $kvName -ne "" -and $kvName -ne "null") {
        Write-LogInfo "Using Key Vault: $kvName"
        
        # Helper function to update environment variable
        function Update-EnvVar {
            param(
                [string]$VarName,
                [string]$SecretName
            )
            
            Write-LogInfo "Updating $VarName..."
            try {
                $secretValue = az keyvault secret show --name $SecretName --vault-name $kvName --query value -o tsv 2>$null
                if ($LASTEXITCODE -eq 0 -and $secretValue) {
                    # Read file content
                    $content = Get-Content $EnvFile
                    
                    # Update the specific line
                    $updatedContent = $content | ForEach-Object {
                        if ($_ -match "^$VarName=") {
                            "$VarName=$secretValue"
                        } else {
                            $_
                        }
                    }
                    
                    # Write back to file
                    $updatedContent | Out-File -FilePath $EnvFile -Encoding UTF8
                    Write-LogSuccess "$VarName updated"
                } else {
                    Write-LogWarning "$VarName secret not found in Key Vault"
                }
            }
            catch {
                Write-LogWarning "Failed to retrieve $VarName from Key Vault: $($_.Exception.Message)"
            }
        }
        
        # Update secrets
        Update-EnvVar "AZURE_OPENAI_KEY" "AZURE-OPENAI-KEY"
        Update-EnvVar "AZURE_SPEECH_KEY" "AZURE-SPEECH-KEY"
        Update-EnvVar "ACS_CONNECTION_STRING" "ACS-CONNECTION-STRING"
        Update-EnvVar "REDIS_PASSWORD" "REDIS-PASSWORD"
        Update-EnvVar "AZURE_STORAGE_CONNECTION_STRING" "AZURE-STORAGE-CONNECTION-STRING"
        
        Write-LogSuccess "Secrets updated successfully"
    } else {
        Write-LogWarning "Key Vault name not found in Terraform outputs"
        Write-LogWarning "Secrets will need to be set manually"
    }
}

# Show environment file information
function Show-EnvironmentFile {
    if (Test-Path $EnvFile) {
        Write-LogInfo "Current environment file: $EnvFile"
        
        $content = Get-Content $EnvFile
        $generationDate = ($content | Select-Object -First 1) -replace '# Generated automatically on ', ''
        Write-LogInfo "Generated: $generationDate"
        
        $varCount = ($content | Where-Object { $_ -match '^[A-Z]' }).Count
        Write-LogInfo "Variables: $varCount"
        
        Write-Host ""
        Write-Host "Content preview:"
        Write-Host "================"
        $content | Select-Object -First 20
        Write-Host "... (truncated, use 'Get-Content $EnvFile' to see full content)"
    } else {
        Write-LogError "Environment file $EnvFile does not exist"
        Write-LogError "Run this script to create it"
    }
}

# Main execution
function Invoke-Main {
    switch ($Action) {
        "generate" {
            Test-Prerequisites
            New-EnvironmentFile
        }
        "update-secrets" {
            Test-Prerequisites
            Update-EnvironmentWithSecrets
        }
        "show" {
            Show-EnvironmentFile
        }
    }
}

# Show usage if no parameters provided and script is run directly
if ($MyInvocation.InvocationName -eq $MyInvocation.MyCommand.Name) {
    if (-not $PSBoundParameters.Count -and -not $args.Count) {
        Write-Host ""
        Write-Host "Environment File Generation from Terraform Remote State (PowerShell)" -ForegroundColor Cyan
        Write-Host "====================================================================" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Usage:"
        Write-Host "  .\Generate-EnvFromTerraform.ps1 [-EnvironmentName <string>] [-SubscriptionId <string>] [-Action <string>]"
        Write-Host ""
        Write-Host "Parameters:"
        Write-Host "  -EnvironmentName    Environment name (default: dev)"
        Write-Host "  -SubscriptionId     Azure subscription ID (auto-detected if not provided)"
        Write-Host "  -Action            Action to perform: generate, update-secrets, show (default: generate)"
        Write-Host ""
        Write-Host "Examples:"
        Write-Host "  .\Generate-EnvFromTerraform.ps1 -EnvironmentName dev"
        Write-Host "  .\Generate-EnvFromTerraform.ps1 -EnvironmentName prod -SubscriptionId `$env:AZURE_SUBSCRIPTION_ID"
        Write-Host "  .\Generate-EnvFromTerraform.ps1 -Action update-secrets"
        Write-Host ""
        exit 0
    }
}

# Execute main function
Invoke-Main

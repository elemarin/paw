param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Location,

    [Parameter(Mandatory = $true)]
    [string]$NamePrefix,

    [Parameter(Mandatory = $true)]
    [string]$VmSshPublicKeyPath,

    [string]$VmAdminUsername = "paw",

    [switch]$DeleteFirst
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

if (-not (Test-Path $VmSshPublicKeyPath)) {
    throw "SSH public key file not found: $VmSshPublicKeyPath"
}

$sshKey = (Get-Content -Path $VmSshPublicKeyPath -Raw).Trim()
if (-not $sshKey) {
    throw "SSH public key file is empty: $VmSshPublicKeyPath"
}

$rgExists = az group exists --name $ResourceGroup | ConvertFrom-Json
if ($DeleteFirst -and $rgExists) {
    Write-Host "Deleting resource group $ResourceGroup ..."
    az group delete --name $ResourceGroup --yes --no-wait | Out-Null

    Write-Host "Waiting for resource group deletion ..."
    do {
        Start-Sleep -Seconds 10
        $stillExists = az group exists --name $ResourceGroup | ConvertFrom-Json
    } while ($stillExists)
}

Write-Host "Ensuring resource group $ResourceGroup in $Location ..."
az group create --name $ResourceGroup --location $Location | Out-Null

Write-Host "Deploying infra/azure/main.bicep ..."
az deployment group create `
  --resource-group $ResourceGroup `
  --name paw-bootstrap `
  --template-file infra/azure/main.bicep `
  --parameters `
    namePrefix=$NamePrefix `
    location=$Location `
    vmAdminUsername=$VmAdminUsername `
    vmSshPublicKey="$sshKey" | Out-Null

$vmIp = az deployment group show --resource-group $ResourceGroup --name paw-bootstrap --query "properties.outputs.vmPublicIp.value" -o tsv
$acr = az deployment group show --resource-group $ResourceGroup --name paw-bootstrap --query "properties.outputs.acrLoginServer.value" -o tsv

Write-Host "Redeploy complete."
Write-Host "VM Public IP: $vmIp"
Write-Host "ACR: $acr"

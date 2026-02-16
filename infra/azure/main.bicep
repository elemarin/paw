targetScope = 'resourceGroup'

@description('Short prefix used to name Azure resources.')
param namePrefix string = 'paw'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container App name.')
param containerAppName string = 'paw'

@description('Container image to run in Azure Container Apps.')
param image string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('PostgreSQL flexible server admin username.')
param postgresAdminUser string = 'pawadmin'

@secure()
@description('PostgreSQL flexible server admin password. Use URL-safe characters when possible.')
param postgresAdminPassword string = ''

@description('PostgreSQL database name used by PAW.')
param postgresDbName string = 'paw'

@description('PostgreSQL server SKU name.')
param postgresSkuName string = 'Standard_B1ms'

@description('PostgreSQL server tier.')
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param postgresTier string = 'Burstable'

@description('PostgreSQL major version.')
@allowed([
  '13'
  '14'
  '15'
  '16'
])
param postgresVersion string = '16'

@description('PostgreSQL storage size in GiB.')
param postgresStorageGb int = 32

@description('Primary model used by PAW.')
param model string = 'openai/gpt-4o-mini'

@description('Smart model used by PAW.')
param smartModel string = 'openai/gpt-5.3-codex'

@secure()
@description('LLM provider API key (PAW_LLM__API_KEY).')
param llmApiKey string = ''

@secure()
@description('Optional PAW API key (PAW_API_KEY).')
param pawApiKey string = ''

@secure()
@description('Telegram bot token (PAW_TELEGRAM_BOT_TOKEN).')
param telegramBotToken string = ''

@description('Enable Telegram runtime.')
param telegramEnabled bool = true

@description('Optional Ollama endpoint reachable from ACA.')
param ollamaApiBase string = ''

@description('Container CPU allocation.')
param cpu int = 1

@description('Container memory allocation.')
@allowed([
  '1Gi'
  '2Gi'
])
param memory string = '2Gi'

@description('Minimum replica count.')
param minReplicas int = 1

@description('Maximum replica count.')
param maxReplicas int = 1

var unique = toLower(uniqueString(resourceGroup().id))
var compactPrefix = toLower(replace(namePrefix, '-', ''))
var acrName = take('${compactPrefix}${unique}', 50)
var storageAccountName = take('${compactPrefix}st${unique}', 24)
var logAnalyticsName = '${namePrefix}-law'
var managedEnvironmentName = '${namePrefix}-env'
var postgresServerName = take('${compactPrefix}pg${unique}', 63)
var dataShareName = 'paw-data'
var pluginsShareName = 'paw-plugins'
var workspaceShareName = 'paw-workspace'
var postgresDatabaseUrl = 'postgresql://${postgresAdminUser}:${postgresAdminPassword}@${postgresServer.properties.fullyQualifiedDomainName}:5432/${postgresDbName}?sslmode=require'
var containerSecrets = concat(
  [
    {
      name: 'acr-password'
      value: acr.listCredentials().passwords[0].value
    }
    {
      name: 'paw-llm-api-key'
      value: llmApiKey
    }
    {
      name: 'paw-telegram-bot-token'
      value: telegramBotToken
    }
    {
      name: 'paw-database-url'
      value: postgresDatabaseUrl
    }
  ],
  empty(pawApiKey)
    ? []
    : [
        {
          name: 'paw-api-key'
          value: pawApiKey
        }
      ]
)
var containerEnv = concat(
  [
    {
      name: 'PAW_HOST'
      value: '0.0.0.0'
    }
    {
      name: 'PAW_PORT'
      value: '8000'
    }
    {
      name: 'PAW_LOG_FORMAT'
      value: 'console'
    }
    {
      name: 'PAW_LLM__MODEL'
      value: model
    }
    {
      name: 'PAW_LLM__SMART_MODEL'
      value: smartModel
    }
    {
      name: 'PAW_TELEGRAM_ENABLED'
      value: '${telegramEnabled}'
    }
    {
      name: 'OLLAMA_API_BASE'
      value: ollamaApiBase
    }
    {
      name: 'PAW_LLM__API_KEY'
      secretRef: 'paw-llm-api-key'
    }
    {
      name: 'PAW_TELEGRAM_BOT_TOKEN'
      secretRef: 'paw-telegram-bot-token'
    }
    {
      name: 'PAW_DATABASE_URL'
      secretRef: 'paw-database-url'
    }
  ],
  empty(pawApiKey)
    ? []
    : [
        {
          name: 'PAW_API_KEY'
          secretRef: 'paw-api-key'
        }
      ]
)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: postgresServerName
  location: location
  sku: {
    name: postgresSkuName
    tier: postgresTier
  }
  properties: {
    createMode: 'Create'
    version: postgresVersion
    administratorLogin: postgresAdminUser
    administratorLoginPassword: postgresAdminPassword
    storage: {
      storageSizeGB: postgresStorageGb
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  name: postgresDbName
  parent: postgresServer
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource postgresAllowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = {
  name: 'AllowAzureServices'
  parent: postgresServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  name: 'default'
  parent: storage
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  name: dataShareName
  parent: fileService
}

resource pluginsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  name: pluginsShareName
  parent: fileService
}

resource workspaceShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  name: workspaceShareName
  parent: fileService
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: managedEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource envStorageData 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: 'paw-data'
  parent: managedEnvironment
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource envStoragePlugins 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: 'paw-plugins'
  parent: managedEnvironment
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: pluginsShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource envStorageWorkspace 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  name: 'paw-workspace'
  parent: managedEnvironment
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: workspaceShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: containerSecrets
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'paw'
          image: image
          resources: {
            cpu: cpu
            memory: memory
          }
          env: containerEnv
          volumeMounts: [
            {
              volumeName: 'data'
              mountPath: '/home/paw/data'
            }
            {
              volumeName: 'plugins'
              mountPath: '/home/paw/plugins'
            }
            {
              volumeName: 'workspace'
              mountPath: '/home/paw/workspace'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 20
              periodSeconds: 20
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: envStorageData.name
        }
        {
          name: 'plugins'
          storageType: 'AzureFile'
          storageName: envStoragePlugins.name
        }
        {
          name: 'workspace'
          storageType: 'AzureFile'
          storageName: envStorageWorkspace.name
        }
      ]
    }
  }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output storageAccountName string = storage.name
output postgresServerFqdn string = postgresServer.properties.fullyQualifiedDomainName

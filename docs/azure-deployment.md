# Deploy PAW to Azure (Container Apps + PostgreSQL)

This setup gives you:

- Managed PostgreSQL for PAW state
- Persistent files on Azure Files for `/home/paw/data`, `/home/paw/plugins`, and `/home/paw/workspace`
- Auto-deploy from GitHub `main` branch

## 1) Local behavior

Local Docker Compose now runs Postgres as a sidecar service.

- Database URL used by PAW (in Compose):
  - `postgresql://paw:paw@postgres:5432/paw?sslmode=disable`
- Data persistence:
  - Postgres data in Docker volume `paw-postgres`
  - PAW file data in `paw-data`, `paw-plugins`, and `paw-workspace`

## 2) Azure architecture in this repo

Bicep file: `infra/azure/main.bicep`

Resources created:

- Azure Container Registry (ACR)
- Log Analytics Workspace
- Azure Database for PostgreSQL Flexible Server + database `paw`
- PostgreSQL firewall rule `AllowAzureServices` (0.0.0.0)
- Azure Storage Account + File Shares
  - `paw-data`
  - `paw-plugins`
  - `paw-workspace`
- Azure Container Apps environment
- Azure Container App (`paw`) with mounted Azure Files shares

Container env wiring:

- `PAW_DATABASE_URL` is injected as a Container App secret with `sslmode=require`

## 3) GitHub setup (required once)

### Repository variables

- `AZURE_RESOURCE_GROUP` (example: `rg-paw-dev`)
- `AZURE_LOCATION` (example: `eastus`)
- `AZURE_NAME_PREFIX` (example: `pawdev`)

### Repository secrets

- `AZURE_CREDENTIALS` (service principal JSON for `azure/login`)
- `PAW_LLM_API_KEY`
- `PAW_TELEGRAM_BOT_TOKEN`
- `PAW_POSTGRES_ADMIN_PASSWORD`
- `PAW_API_KEY` (optional, can be blank)

## 4) CI/CD flow

Workflow file: `.github/workflows/deploy-azure.yml`

On push to `main`, pipeline does:

1. Create/validate resource group
2. Deploy infra using Bicep (bootstrap image)
3. Build Docker image from repo
4. Push image to ACR
5. Redeploy Container App with new image tag

## 5) Using PAW CLI against cloud

Set your CLI target URL to cloud endpoint:

```bash
setx PAW_URL "https://<your-container-app-fqdn>"
```

Then run:

```bash
paw status
paw chat "hello from cloud"
```

## 6) Notes

- Prefer URL-safe characters in `PAW_POSTGRES_ADMIN_PASSWORD` because it is embedded in `PAW_DATABASE_URL`.
- `AllowAzureServices` is simple and cheap; tighten networking (private access/VNet) when you move beyond MVP.

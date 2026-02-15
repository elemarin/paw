# Deploy PAW to Azure (Container Apps + GitHub Actions)

This setup gives you:

- Persistent memory across deployments using Azure Files mounted at `/home/paw/data`
- Auto-deploy from GitHub `main` branch
- Telegram bot always connected to the latest deployed version

## 1) Local persistence behavior (what keeps memory)

Your memory DB lives at:

- `/home/paw/data/paw.db`

In local Docker Compose, this is persisted by the named volume `paw-data`.

Memory survives:

- `docker compose down`
- `docker compose up -d --build`
- image rebuilds and container recreation

Memory is removed only if you delete volumes, for example:

- `docker compose down -v`
- `docker volume rm paw-data`

## 2) Azure architecture in this repo

Bicep file: `infra/azure/main.bicep`

Resources created:

- Azure Container Registry (ACR)
- Log Analytics Workspace
- Azure Storage Account + File Shares
  - `paw-data`
  - `paw-plugins`
  - `paw-workspace`
- Azure Container Apps environment
- Azure Container App (`paw`) with mounted Azure Files shares

Container mount points:

- `/home/paw/data` (memory DB persists here)
- `/home/paw/plugins`
- `/home/paw/workspace`

## 3) GitHub setup (required once)

### Repository variables

- `AZURE_RESOURCE_GROUP` (example: `rg-paw-dev`)
- `AZURE_LOCATION` (example: `eastus`)
- `AZURE_NAME_PREFIX` (example: `pawdev`)

### Repository secrets

- `AZURE_CREDENTIALS` (service principal JSON for `azure/login`)
- `PAW_LLM_API_KEY`
- `PAW_TELEGRAM_BOT_TOKEN`
- `PAW_API_KEY` (optional, can be blank)

## 4) CI/CD flow

Workflow file: `.github/workflows/deploy-azure.yml`

On push to `main`, pipeline does:

1. Create/validate resource group
2. Deploy infra using Bicep (bootstrap image)
3. Build Docker image from repo
4. Push image to ACR
5. Redeploy Container App with new image tag

After deploy, it prints your public Container App URL.

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

## 6) First production hardening steps

- Add Azure budget + cost alert for your subscription
- Restrict ingress to trusted IPs if needed
- Add `PAW_API_KEY` and use it from CLI
- Move ACR auth from admin credentials to managed identity
- Add custom domain + TLS cert if desired

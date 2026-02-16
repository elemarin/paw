# Deploy PAW to Azure (Single VM + Docker Compose)

This setup gives you:

- One Ubuntu VM running Docker Compose
- Local Postgres container on the VM for PAW state
- Persistent host paths on the VM for `/home/paw/data`, `/home/paw/plugins`, `/home/paw/workspace`, and Postgres data
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
- Azure public IP + NSG + VNet + NIC
- Single Ubuntu VM (`${namePrefix}-vm`)

Runtime model:

- Workflow pushes app image to ACR
- Workflow runs a VM command that writes/updates `/opt/paw/docker-compose.yml` and `/opt/paw/.env`
- VM runs `postgres` + `paw` containers via Docker Compose

## 3) GitHub setup (required once)

### Repository variables

- `AZURE_RESOURCE_GROUP` (example: `rg-paw-dev`)
- `AZURE_LOCATION` (example: `eastus`)
- `AZURE_NAME_PREFIX` (example: `pawdev`)
- `AZURE_VM_ADMIN_USERNAME` (optional, defaults to `paw`)

### Repository secrets

- `AZURE_CREDENTIALS` (service principal JSON for `azure/login`)
- `AZURE_VM_SSH_PUBLIC_KEY`
- `PAW_LLM_API_KEY`
- `PAW_TELEGRAM_BOT_TOKEN`
- `PAW_API_KEY` (optional, can be blank)

## 4) CI/CD flow

Workflow file: `.github/workflows/deploy-azure.yml`

On push to `main`, pipeline does:

1. Create/validate resource group
2. Deploy infra using Bicep (VM + ACR)
3. Build Docker image from repo
4. Push image to ACR
5. Run VM command to apply/update Docker Compose and restart containers

## 5) Using PAW CLI against cloud

Set your CLI target URL to cloud endpoint:

```bash
setx PAW_URL "http://<your-vm-public-ip>:8000"
```

Then run:

```bash
paw status
paw chat "hello from cloud"
```

## 6) Notes

- The default NSG opens ports `22` and `8000` to the internet; restrict source IP ranges for production.
- Add automated backups for `/opt/paw/postgres` and `/opt/paw/data`.

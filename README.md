# OVH Inventory Checker

A monitoring system for OVH Cloud VPS availability that sends Discord/Slack notifications when items come back in stock.

## Features

- Monitors OVH VPS inventory across US and Global regions
- Discord and Slack webhook notifications
- Multi-tenant support with user authentication
- Per-plan subscription alerts
- Web UI and REST API
- Kubernetes deployment ready

## Quick Start

```bash
# Copy environment template
cp .env.example .env

# Generate required secrets
echo "JWT_SECRET=$(openssl rand -base64 32)" >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)" >> .env

# Start services
docker-compose up -d

# View logs (includes initial admin password)
docker-compose logs api
```

## Initial Admin Setup

On first startup, an admin user is created with a randomly generated password. Find it in the logs:

```bash
docker-compose logs api | grep -A 5 "INITIAL ADMIN"
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret for JWT tokens (`openssl rand -base64 32`) |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL_SECONDS` | `120` | OVH API check interval |
| `NOTIFICATION_THRESHOLD_MINUTES` | `60` | Out-of-stock time before notifying |
| `ALLOW_REGISTRATION` | `true` | Allow public user registration |
| `CORS_ORIGINS` | `` | Allowed CORS origins (set for production) |

## Kubernetes Deployment

```bash
# Create secrets from template
cp k8s/secrets.yaml.example k8s/secrets.yaml
# Edit with secure values

# Deploy
kubectl apply -k k8s/

# Access UI
kubectl -n ovh-checker port-forward svc/api 8080:80
```

## Docker Images

Pre-built multi-arch images (amd64/arm64) are available:

```bash
docker pull ghcr.io/zfouts/ovh-checker-api:latest
docker pull ghcr.io/zfouts/ovh-checker-checker:latest
```

Images include signed build provenance attestations verifiable with:
```bash
gh attestation verify oci://ghcr.io/zfouts/ovh-checker-api:latest
```

## Project Structure

```
├── api/           # FastAPI backend + Vue.js frontend
├── checker/       # Inventory monitoring service
├── shared/        # Shared SQLAlchemy models
├── db/            # Database schema and migrations
└── k8s/           # Kubernetes manifests
```

## Development

```bash
# Install dependencies
pip install -r api/requirements.txt
pip install -r checker/requirements.txt

# Start PostgreSQL
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=dev \
  -p 5432:5432 \
  postgres:16-alpine

# Run services
cd api && python main.py
cd checker && python main.py
```

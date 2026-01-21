# OVH Inventory Checker

A monitoring system for OVH Cloud VPS availability that sends Discord notifications when items come back in stock after being unavailable for more than 60 minutes.

## Features

- ✅ Monitors multiple OVH VPS plans every 120 seconds
- ✅ Tracks availability history in PostgreSQL
- ✅ Sends Discord webhook notifications when items return to stock
- ✅ **Multi-tenant support** - Users can set up their own Discord alerts
- ✅ **Authentication** - JWT-based authentication with user registration
- ✅ **Per-plan subscriptions** - Users choose which plans to receive alerts for
- ✅ Web UI for viewing status and managing settings
- ✅ API for programmatic access
- ✅ Kubernetes deployment ready

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   OVH API       │◄────│    Checker      │────►│   PostgreSQL    │
│                 │     │   (every 120s)  │     │                 │
└─────────────────┘     └────────┬────────┘     └────────▲────────┘
                                 │                       │
                                 ▼                       │
                        ┌─────────────────┐              │
                        │  Discord        │              │
                        │  - Default      │              │
                        │  - User hooks   │              │
                        └─────────────────┘              │
                                                         │
┌─────────────────┐     ┌─────────────────┐              │
│   Browser       │◄────│   API + UI      │──────────────┘
│                 │     │   (Auth/Multi)  │
└─────────────────┘     └─────────────────┘
```

## Notification Flow

When a VPS plan comes back in stock:
1. **Default webhook** - Always receives all notifications (configured by admin)
2. **User webhooks** - Only receive notifications for plans they've subscribed to

## Quick Start with Docker Compose

```bash
# Copy environment template
cp .env.example .env

# IMPORTANT: Edit .env and set a secure JWT_SECRET
# Generate one with: openssl rand -base64 32

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access the UI
open http://localhost:8080
```

## Authentication

### Initial Admin Setup

On first startup, if no users exist, the system automatically creates an admin user with a **randomly generated password**. Check the API logs to find the credentials:

```bash
docker compose logs api | grep -A 5 "INITIAL ADMIN"
```

Example output:
```
============================================================
🔐 INITIAL ADMIN USER CREATED
============================================================
   Email:    admin@example.com (or ADMIN_EMAIL env var)
   Password: Check API logs on first startup for generated password
   Username: admin
   Password: xK9mP2nL5qR8vT4w
============================================================
⚠️  SAVE THIS PASSWORD - IT WILL NOT BE SHOWN AGAIN!
============================================================
```

You can customize the admin email/username via environment variables:
```bash
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_USERNAME=superadmin
```

### Admin Features

Admins have access to:
- **User Management** - Create, enable/disable, promote/demote, delete users
- **Registration Control** - Enable/disable public registration
- **Groups** - Create and manage user groups for shared alerts
- **Settings** - Configure global Discord webhook and other settings

### User Registration

By default, public registration is enabled. Users can:
1. Create an account
2. Add their Discord webhooks (with customization options)
3. Subscribe to specific plans
4. Receive personalized notifications

Admins can disable public registration from the Admin tab.

## Configuration

### Required Environment Variables

These variables **must** be set before the application will start:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string. Generate password with: `openssl rand -base64 24` |
| `JWT_SECRET` | Secret key for JWT tokens. Generate with: `openssl rand -base64 32` |
| `POSTGRES_PASSWORD` | PostgreSQL password (for docker-compose). Generate with: `openssl rand -base64 24` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHECK_INTERVAL_SECONDS` | `120` | How often to check OVH API |
| `NOTIFICATION_THRESHOLD_MINUTES` | `60` | Minimum out-of-stock time before notification |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `ALLOW_REGISTRATION` | `true` | Allow public user registration |
| `API_HOST` | `0.0.0.0` | API bind address |
| `API_PORT` | `8000` | API port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (use specific domains in production) |
| `POSTGRES_USER` | `ovhchecker` | PostgreSQL username |
| `POSTGRES_DB` | `ovhchecker` | PostgreSQL database name |

### Quick Setup

```bash
# Copy the example .env file
cp .env.example .env

# Generate and set required secrets
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)" >> .env
echo "JWT_SECRET=$(openssl rand -base64 32)" >> .env

# Update DATABASE_URL with your password
# Edit .env and replace YOUR_PASSWORD_HERE with the generated POSTGRES_PASSWORD
```

### Discord Webhook Setup

#### Admin (Default Webhook)
1. Login as admin
2. Go to Settings tab
3. Add your Discord webhook URL
4. All stock notifications will be sent here

#### User (Personal Webhook)
1. Create an account or login
2. Go to "My Alerts" tab
3. Add your Discord webhook
4. Select which plans you want to be notified about
5. Only those plans will trigger notifications to your webhook

## API Endpoints

### Public Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Get current inventory status |
| GET | `/api/status/history` | Get status history |
| GET | `/api/plans` | Get all monitored plans |
| GET | `/api/pricing/{plan}` | Get pricing for a plan |
| GET | `/api/notifications` | Get notification history |
| GET | `/api/datacenters` | Get datacenter locations |

### Authentication Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login and get tokens |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/logout` | Logout (revoke token) |

### User Endpoints (Requires Authentication)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/me` | Get current user profile |
| GET | `/api/me/webhooks` | List user's webhooks |
| POST | `/api/me/webhooks` | Add a webhook |
| DELETE | `/api/me/webhooks/{id}` | Delete a webhook |
| GET | `/api/me/subscriptions` | List plan subscriptions |
| POST | `/api/me/subscriptions` | Subscribe to a plan |
| DELETE | `/api/me/subscriptions/{plan}` | Unsubscribe from a plan |
| POST | `/api/me/subscriptions/bulk` | Bulk update subscriptions |
| GET | `/api/me/notifications` | User's notification history |

### Admin Endpoints (Requires Admin)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get system configuration |
| PUT | `/api/config` | Update configuration |
| PUT | `/api/config/discord-webhook` | Set default webhook |
| POST | `/api/config/discord-webhook/test` | Test default webhook |

## Docker Images

Pre-built images are available on GitHub Container Registry:

```bash
# Pull the latest images
docker pull ghcr.io/YOUR_USERNAME/ovh-checker-api:latest
docker pull ghcr.io/YOUR_USERNAME/ovh-checker-checker:latest
```

Images are automatically built and pushed on:
- Push to `main`/`master` branch → `:latest` tag
- Git tags (`v1.0.0`) → `:1.0.0`, `:1.0` tags
- Pull requests → Build only (no push)

Multi-architecture support: `linux/amd64` and `linux/arm64`

## Kubernetes Deployment

```bash
# Using pre-built images from GHCR
# Update k8s/api.yaml and k8s/checker.yaml with your image names

# Or build and push your own images
docker build -t ghcr.io/YOUR_USERNAME/ovh-checker-api:latest -f api/Dockerfile .
docker build -t ghcr.io/YOUR_USERNAME/ovh-checker-checker:latest -f checker/Dockerfile .
docker push ghcr.io/YOUR_USERNAME/ovh-checker-api:latest
docker push ghcr.io/YOUR_USERNAME/ovh-checker-checker:latest

# Create secrets from template
cp k8s/secrets.yaml.example k8s/secrets.yaml
# Edit k8s/secrets.yaml with your secure values

# Deploy to Kubernetes
kubectl apply -k k8s/

# Check status
kubectl -n ovh-checker get pods

# Port forward to access UI locally
kubectl -n ovh-checker port-forward svc/api 8080:80
```

⚠️ **Note:** Update the Kubernetes secrets to include `JWT_SECRET` for production deployments.

## Security Considerations

1. **JWT Secret**: Use a strong, random secret for `JWT_SECRET` (at least 32 bytes)
   ```bash
   openssl rand -base64 32
   ```

2. **HTTPS**: Always use HTTPS in production - configure your ingress/load balancer

3. **CORS**: Set `CORS_ORIGINS` to your specific domain(s) in production

4. **Registration**: Consider setting `ALLOW_REGISTRATION=false` after creating admin users

5. **Database**: Use strong passwords and restrict network access

## Project Structure

```
ovh-checker/
├── .github/
│   └── workflows/
│       └── build-and-push.yml  # CI/CD for Docker images
├── api/                    # API + Frontend service
│   ├── auth.py            # JWT authentication module
│   ├── config.py          # Configuration settings
│   ├── database.py        # SQLAlchemy database operations
│   ├── discord_client.py  # Discord webhook client
│   ├── main.py            # FastAPI application
│   ├── models.py          # Pydantic models
│   ├── requirements.txt
│   ├── Dockerfile
│   └── static/
│       └── index.html     # Vue.js SPA frontend
├── checker/                # Inventory checker service
│   ├── config.py
│   ├── database.py        # SQLAlchemy database operations
│   ├── discord_notifier.py
│   ├── main.py
│   ├── pricing_fetcher.py
│   ├── catalog_fetcher.py
│   ├── requirements.txt
│   └── Dockerfile
├── shared/                # Shared modules
│   ├── __init__.py
│   ├── database.py        # SQLAlchemy engine/session utilities
│   └── models.py          # SQLAlchemy ORM models
├── db/
│   ├── init.sql           # Database schema (with auth tables)
│   └── seed_datacenters.sql
├── k8s/                   # Kubernetes manifests
│   ├── namespace.yaml
│   ├── secrets.yaml.example  # Template (copy to secrets.yaml)
│   ├── configmap.yaml
│   ├── postgres.yaml
│   ├── checker.yaml
│   ├── api.yaml
│   └── kustomization.yaml
├── .env.example           # Environment template
├── .gitignore
├── docker-compose.yml
└── README.md
```

## How It Works

1. **Checker Service** polls OVH API every 120 seconds for each monitored plan
2. Results are stored in PostgreSQL with timestamps
3. When an item becomes unavailable, the system starts tracking how long it's been out
4. When the item returns to stock AND has been out for ≥60 minutes:
   - **Default webhook** receives the notification (if configured)
   - **User webhooks** receive notifications for plans they're subscribed to
5. The **API Service** provides authentication, REST API, and serves the web UI
6. Users can register, add their Discord webhooks, and subscribe to specific plans

## Development

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings (especially JWT_SECRET)

# Install dependencies
cd api && pip install -r requirements.txt
cd ../checker && pip install -r requirements.txt

# Start PostgreSQL (using Docker)
docker run -d --name ovh-postgres \
  -e POSTGRES_USER=ovhchecker \
  -e POSTGRES_PASSWORD=ovhchecker \
  -e POSTGRES_DB=ovhchecker \
  -p 5432:5432 \
  -v $(pwd)/db/init.sql:/docker-entrypoint-initdb.d/init.sql \
  postgres:16-alpine

# Run the API (in one terminal)
cd api && python main.py

# Run the checker (in another terminal)
cd checker && python main.py
```

## Upgrading from Pre-Auth Version

If you're upgrading from a version without authentication:

1. **Backup your database** before running migrations
2. Apply the new schema (tables will be added without affecting existing data):
   ```bash
   psql -h localhost -U ovhchecker -d ovhchecker -f db/init.sql
   ```
3. Update environment variables to include `JWT_SECRET`
4. Rebuild and restart containers

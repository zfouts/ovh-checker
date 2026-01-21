"""
OVH Checker API

A FastAPI application for monitoring OVH server availability.
"""
import logging
import secrets
import string
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from db_instance import db  # Shared database instance
from auth import hash_password

# Import routers
from routers import auth, users, admin, plans, compare

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Only add HSTS in production (when not localhost)
        if request.url.hostname not in ("localhost", "127.0.0.1"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def bootstrap_admin_user():
    """Create initial admin user if no users exist."""
    users = await db.get_all_users()
    if users:
        return  # Users already exist, skip bootstrap
    
    # Generate random password
    password = generate_secure_password(20)
    password_hash = hash_password(password)
    
    # Create admin user
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    
    try:
        user_id = await db.admin_create_user(
            email=admin_email,
            username=admin_username,
            password_hash=password_hash,
            is_active=True,
            is_admin=True
        )
        logger.info("=" * 60)
        logger.info("INITIAL ADMIN USER CREATED")
        logger.info("=" * 60)
        logger.info(f"Email: {admin_email}")
        logger.info(f"Username: {admin_username}")
        logger.info(f"Password: {'*' * 8} (check ADMIN_INITIAL_PASSWORD env var or container logs on first run only)")
        # Log password only to stderr for immediate capture, not to persistent logs
        import sys
        print(f"\n*** INITIAL ADMIN PASSWORD: {password} ***\n", file=sys.stderr)
        logger.info("=" * 60)
        logger.info("Please change this password immediately after logging in!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Failed to create admin user: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting OVH Checker API...")
    await db.connect()
    await bootstrap_admin_user()
    yield
    # Shutdown
    logger.info("Shutting down OVH Checker API...")
    await db.disconnect()


# Create FastAPI app
app = FastAPI(
    title="OVH Checker API",
    description="API for monitoring OVH server availability and prices",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS - parse origins from settings
cors_origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]

# Security: Don't allow credentials with wildcard origins
allow_credentials = settings.cors_origins != "*"

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(plans.router)
app.include_router(compare.router)


# ============ Health Check ============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        await db.get_config("discord_webhook_url")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# ============ Static Files (Frontend) ============

# Serve static files from frontend directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend."""
        return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)

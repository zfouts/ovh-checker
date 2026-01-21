FROM python:3.12-alpine

WORKDIR /app

# Build arguments for version info
ARG BUILD_SHA=dev
ARG BUILD_DATE=unknown

# Set environment variables from build args
ENV BUILD_SHA=${BUILD_SHA}
ENV BUILD_DATE=${BUILD_DATE}

# Install build dependencies for Python packages
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev \
    && apk add --no-cache libpq

# Upgrade pip to fix CVE-2025-8869
RUN pip install --no-cache-dir --upgrade pip>=25.3

# Install dependencies
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Create non-root user
RUN adduser -D -u 1000 appuser

# Copy shared module
COPY shared/ /app/shared/

# Copy application code
COPY api/*.py .
COPY api/routers/ routers/
COPY api/services/ services/
COPY api/static/ static/

# Inject build info into static HTML (use first 7 chars of SHA)
RUN SHORT_SHA=$(echo "${BUILD_SHA}" | cut -c1-7) && \
    sed -i "s/__BUILD_SHA__/${SHORT_SHA}/g" static/index.html && \
    sed -i "s/__BUILD_DATE__/${BUILD_DATE}/g" static/index.html

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the API server
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

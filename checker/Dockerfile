FROM python:3.12-alpine

WORKDIR /app

# Install build dependencies for Python packages
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev \
    && apk add --no-cache libpq

# Upgrade pip to fix CVE-2025-8869
RUN pip install --no-cache-dir --upgrade pip>=25.3

# Install dependencies
COPY checker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Create non-root user
RUN adduser -D -u 1000 appuser

# Copy shared module
COPY shared/ /app/shared/

# Copy application code
COPY checker/*.py .

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Run the checker
CMD ["python", "main.py"]

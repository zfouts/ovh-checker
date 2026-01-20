FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY checker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared module
COPY shared/ /app/shared/

# Copy application code
COPY checker/*.py .

# Run the checker
CMD ["python", "main.py"]

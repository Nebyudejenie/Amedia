FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run as non-root
RUN useradd -m -u 1000 arada && chown -R arada:arada /app
USER arada

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD python -c "import httpx; httpx.get('http://127.0.0.1:8000/system/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default port (override with MCP_PORT env var)
EXPOSE 8000

CMD ["python", "mcp_server.py"]

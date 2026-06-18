FROM python:3.11-slim

# P11: Best-practice Docker hygiene
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only source code (not .git, .venv, __pycache__ — excluded by .dockerignore)
COPY app/ ./app/
COPY main.py .

# P1: PostgreSQL is the default in production; override DATABASE_URL in Render env vars
ENV DATABASE_URL=postgresql://user:password@localhost:5432/github_mcp
ENV APP_PORT=8000
ENV APP_ENV=production

EXPOSE 8000

# Default: HTTP mode (OAuth + MCP server)
# For Claude Desktop stdio: docker run ... python -m app.main stdio
CMD ["python", "-m", "app.main"]

# Stage 1: Build the Next.js static files
FROM node:22-alpine AS frontend-builder

WORKDIR /app

# Copy package files first (for better caching)
COPY package*.json ./
RUN npm ci

# Copy all frontend files
COPY . .

# Build argument for Clerk public key
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY


ARG NODE_ENV=production
ENV NODE_ENV=$NODE_ENV


# Build the Next.js app (creates 'out' directory with static files)
RUN npm run build



# Stage 2: Create the final Python container
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for xhtml2pdf/pycairo
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt



# Copy the FastAPI server
COPY api/ ./
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
COPY api/index.py ./server.py


# Copy the Next.js static export from builder stage
COPY --from=frontend-builder /app/out ./static

RUN chmod +x ./scripts/start_server.sh

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Expose port 8000 (FastAPI will serve everything)
EXPOSE 8000

# Ensure logs flush to container output
ENV PYTHONUNBUFFERED=1

# Run migrations, then start the FastAPI server
CMD ["./scripts/start_server.sh"]

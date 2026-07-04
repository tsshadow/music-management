# syntax=docker/dockerfile:1

# -----------------------------------------------------
# Build stage: install tooling, dependencies and build
# -----------------------------------------------------
FROM python:3.13-slim-trixie AS builder

# Base tooling + Node + pnpm + build deps
RUN sed -i 's/Components: main$/Components: main contrib non-free non-free-firmware/' /etc/apt/sources.list.d/debian.sources 
RUN apt-get update && apt-get install -y \
    gcc wget curl gnupg bash git ca-certificates \
    unzip p7zip-full unrar\
    build-essential yasm nasm pkg-config \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Frontend dependencies and build
COPY frontend/pnpm-lock.yaml frontend/package.json frontend/
RUN cd frontend && pnpm install
COPY frontend/ frontend/
RUN cd frontend && pnpm build

# Copy application source
COPY . .

# Remove dev files to shrink final image
RUN rm -rf tests \
    frontend/node_modules frontend/.svelte-kit frontend/.vite \
    frontend/src frontend/static frontend/tsconfig.json \
    frontend/vite.config.ts frontend/svelte.config.js \
    frontend/eslint.config.js frontend/package.json \
    frontend/pnpm-lock.yaml frontend/README.md \
    frontend/vitest-setup-client.ts


# -----------------------------------------------------
# Final stage: minimal runtime image
# -----------------------------------------------------
FROM python:3.13-slim-trixie

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Bring in Python deps and application code
COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app

ARG PORT=8001
ENV PORT=${PORT}
EXPOSE ${PORT}

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

CMD ["bash", "./entrypoint.sh"]


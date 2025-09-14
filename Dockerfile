# syntax=docker/dockerfile:1

# -----------------------------------------------------
# Build stage: install tooling, dependencies and build
# -----------------------------------------------------
FROM python:3.13-slim-trixie AS builder

# Base tooling + Node + pnpm + build deps
RUN apt-get update && apt-get install -y \
    gcc wget curl gnupg bash git ca-certificates \
    unzip p7zip-full \
    build-essential yasm nasm pkg-config \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build and install FFmpeg from source
ARG FFMPEG_VERSION=6.1.2
RUN set -eux; \
    curl -L "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o /tmp/ffmpeg.tar.xz; \
    tar -xJf /tmp/ffmpeg.tar.xz -C /tmp; \
    cd "/tmp/ffmpeg-${FFMPEG_VERSION}"; \
    ./configure --prefix=/usr/local --disable-debug --disable-doc --disable-ffplay; \
    make -j"$(nproc)"; \
    make install; \
    rm -rf /tmp/ffmpeg*

# Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Optional env copy (your original step)
RUN [ -f .env.linux ] && cp -f .env.linux .env && rm -f .env.linux || true

# Frontend dependencies and build
COPY frontend/pnpm-lock.yaml frontend/package.json frontend/
RUN cd frontend && pnpm install
COPY frontend/ frontend/
RUN cd frontend && pnpm build


# -----------------------------------------------------
# Final stage: minimal runtime image
# -----------------------------------------------------
FROM python:3.13-slim-trixie

WORKDIR /app

# Bring in Python deps and FFmpeg
COPY --from=builder /usr/local /usr/local

# Application source (node_modules are ignored via .dockerignore)
COPY . .

# Include built frontend
COPY --from=builder /app/frontend/dist frontend/dist

# Copy default env again for runtime
RUN cp .env.linux .env || true && rm -f .env.linux

ARG PORT=8001
ENV PORT=${PORT}
EXPOSE ${PORT}

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

CMD ["bash", "./entrypoint.sh"]


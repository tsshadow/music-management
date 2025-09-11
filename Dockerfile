# syntax=docker/dockerfile:1
FROM python:3.13-slim-trixie

# --- Base tooling + Node + pnpm (unchanged, but without apt ffmpeg) ---
RUN apt-get update && apt-get install -y \
    gcc wget curl gnupg bash git ca-certificates \
    unzip p7zip-full \
    # build deps for ffmpeg from source
    build-essential yasm nasm pkg-config \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Build and install FFmpeg from source ---
# Pin to a release for reproducibility; change version if you need newer.
ARG FFMPEG_VERSION=6.1.2
RUN set -eux; \
    curl -L "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o /tmp/ffmpeg.tar.xz; \
    tar -xJf /tmp/ffmpeg.tar.xz -C /tmp; \
    cd "/tmp/ffmpeg-${FFMPEG_VERSION}"; \
    # Minimal config: no docs, no ffplay; native AAC encoder is included by default
    ./configure --prefix=/usr/local --disable-debug --disable-doc --disable-ffplay; \
    make -j"$(nproc)"; \
    make install; \
    # Make sure binaries are trivially discoverable
    ln -sf /usr/local/bin/ffmpeg  /usr/bin/ffmpeg; \
    ln -sf /usr/local/bin/ffprobe /usr/bin/ffprobe; \
    # Clean build artifacts
    rm -rf /tmp/ffmpeg*;

# Python deps first for better caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Frontend deps (cache pnpm install)
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/
RUN cd frontend && pnpm install

# App source
COPY . .

# Optional env copy (your original step)
RUN cp .env.linux .env || true && rm -f .env.linux

# Vite dev server env
ENV VITE_API_BASE=/api
EXPOSE 5173

# Entrypoint
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

# Use bash so wait -n works if you rely on it
CMD ["bash", "./entrypoint.sh"]

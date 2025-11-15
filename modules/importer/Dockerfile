# syntax=docker/dockerfile:1

# -----------------------------------------------------
# Build stage: install tooling, dependencies and build
# -----------------------------------------------------
FROM python:3.13-slim-trixie AS builder

# Base tooling + build deps
RUN apt-get update && apt-get install -y \
    gcc wget curl gnupg bash git ca-certificates \
    unzip p7zip-full \
    build-essential yasm nasm pkg-config \
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
COPY modules/importer/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application source
COPY modules/importer/ ./

# Remove dev files to shrink final image
RUN rm -rf tests \
    frontend/node_modules frontend/.svelte-kit frontend/.vite \
    frontend/src frontend/static frontend/tsconfig.json \
    frontend/vite.config.ts frontend/svelte.config.js \
    frontend/eslint.config.js frontend/package.json \
    frontend/pnpm-lock.yaml frontend/README.md \
    frontend/vitest-setup-client.ts || true


# -----------------------------------------------------
# Final stage: minimal runtime image
# -----------------------------------------------------
FROM python:3.13-slim-trixie

WORKDIR /app

# Bring in Python deps and FFmpeg
COPY --from=builder /usr/local /usr/local

# Bring in application code
COPY --from=builder /app /app

ARG PORT=8001
ENV PORT=${PORT}
EXPOSE ${PORT}

# Ensure entrypoint is executable
RUN chmod +x entrypoint.sh

CMD ["bash", "./entrypoint.sh"]

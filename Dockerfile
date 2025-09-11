# syntax=docker/dockerfile:1
FROM python:3.13-slim-trixie

RUN apt-get update && apt-get install -y gcc wget curl gnupg bash ffmpeg && \
    wget http://ftp.nl.debian.org/debian/pool/non-free/u/unrar-nonfree/unrar_7.1.8-1_amd64.deb && \
    dpkg -i *.deb && \
    apt-get update && apt-get install -y unzip p7zip-full && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# yt-dlp
RUN curl -Lo yt-dlp https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp && chmod +x yt-dlp

# Python deps eerst voor betere caching
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Frontend deps (alleen package files kopiëren voor cache)
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/
RUN cd frontend && pnpm install

# Dan pas de rest
COPY . .

RUN cp .env.linux .env || true && rm -f .env.linux

ENV VITE_API_BASE=/api
EXPOSE 5173

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
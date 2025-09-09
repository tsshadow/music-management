# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

# install system packages, Node.js 20 and pnpm
RUN apt-get update && apt-get install -y gcc wget curl gnupg && \
    wget http://ftp.nl.debian.org/debian/pool/non-free/u/unrar-nonfree/unrar_5.6.6-1+deb10u1_amd64.deb && \
    dpkg -i *.deb && \
    apt-get update && apt-get install -y unzip p7zip-full && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download yt-dlp and make it executable
RUN curl -Lo yt-dlp https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp && \
    chmod +x yt-dlp

COPY . .
COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

COPY . .
RUN cp .env.linux .env && rm -f .env.linux
RUN cd frontend && pnpm install

ENV VITE_API_BASE=http://localhost:8001/api
EXPOSE 5173

COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]

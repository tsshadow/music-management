# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

#install dependencies
RUN apt-get update && apt-get install -y gcc wget
RUN wget http://ftp.nl.debian.org/debian/pool/non-free/u/unrar-nonfree/unrar_5.6.6-1+deb10u1_amd64.deb && \
    dpkg -i *.deb && \
    apt update && \
    apt install unzip p7zip-full -y

WORKDIR /app

COPY . .
COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

CMD ["python3" , "main.py"]

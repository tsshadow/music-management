# syntax=docker/dockerfile:1

FROM python:3.8-slim-buster

#install dependencies
RUN apt update && \
    apt install -y unrar-free

WORKDIR /app

COPY . .
COPY requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

CMD ["python3" , "main.py", "docker"]

FROM pytorch/pytorch:latest

# Installeer systeem afhankelijkheden voor audioverwerking
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopieer requirements en installeer python pakketten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de broncode
COPY . .

# Voor nu houden we de container levend zodat we er commando's in kunnen draaien
CMD ["tail", "-f", "/dev/null"]

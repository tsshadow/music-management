FROM pytorch/pytorch:latest

# Installeer systeem afhankelijkheden voor audioverwerking
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopieer requirements en installeer python pakketten
COPY services/ml-analyzer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de broncode
COPY services/ml-analyzer/ /app/services/ml-analyzer/
COPY services/common/ /app/services/common/
COPY VERSION RELEASE_NOTES.md /app/

ENV PYTHONPATH=/app

# Draai de analyzer in de achtergrond (met API server)
CMD ["python", "services/ml-analyzer/analyzer.py", "--all", "--save", "--repeat", "--sleeptime", "3600"]

# Dockerfile
FROM python:3.11-slim

# Evita buffer sullo stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Cartella di lavoro dentro il container
WORKDIR /app

# Dipendenze di sistema (per opencv, ffmpeg, ecc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e installa
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto del progetto
COPY . /app/

# Porta esposta da Django
EXPOSE 8000

# Comando di default (lo sovrascriviamo nei servizi di docker-compose)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

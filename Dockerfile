# Gebruik een officiële Python runtime als base image
FROM python:3.11-slim

# Stel de werkdirectory in de container in
WORKDIR /app

# Voorkom dat Python output buffert
ENV PYTHONUNBUFFERED 1

# Installeer dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Kopieer de applicatiecode naar de werkdirectory
# --- DIT IS DE CORRECTIE ---
COPY ./app ./app

# Expose de poort waarop de app draait
EXPOSE 8000

# Definieer de command om de app te starten met Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
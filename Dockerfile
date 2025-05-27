# Dockerfile

# Gebruik een officiële Python runtime als base image
FROM python:3.11-slim

# Voorkom dat Python .pyc bestanden schrijft en zorg dat output direct zichtbaar is
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Stel de werkdirectory in de container in op /app
WORKDIR /app

# Kopieer en installeer eerst de dependencies.
# Dit maakt gebruik van Docker's layer caching voor snellere builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de projectbestanden (de '.' staat voor de project-root)
# naar de werkdirectory in de container (/app).
COPY . .

# Geef aan dat de container luistert op poort 8000
EXPOSE 8000

# Het commando om de applicatie te starten
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
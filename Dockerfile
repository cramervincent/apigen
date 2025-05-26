# Stap 1: Gebruik een officiële Python runtime
FROM python:3.11-slim

# Stap 2: Stel een werkdirectory in
WORKDIR /code

# Stap 3: Installeer dependencies (dit wordt gecached als requirements.txt niet wijzigt)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Stap 4: Kopieer de applicatiecode naar de /code/app directory
COPY ./app ./app

# Stap 5: Stel de command in om de app te draaien
# Uvicorn wordt gedraaid vanuit /code en kan de 'app' module vinden in /code/app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

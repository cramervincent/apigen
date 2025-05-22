# Google Analytics Benchmark Tool - Chill Mode! 🚀

Yo! Deze FastAPI app is echt de bom. Hiermee log je ff in met je Google-account, pikt wat Google Analytics (GA4) properties uit, en BAM! Je krijgt een benchmarkrapport. Alles wordt netjes opgeslagen in een database, en je krijgt een linkje dat je kunt delen. Oh, en je mag zelf kiezen welke periode, metrics en dimensies je wilt checken. Superflexibel dus!

## Wat gaan we doen?

*  [Wat heb je nodig?](#wat-heb-je-nodig)
*  [Google Cloud Project - ff fixen](#google-cloud-project---ff-fixen)
*  [Lokaal op je bakkie zetten](#lokaal-op-je-bakkie-zetten)
*  [App starten - Let's go!](#app-starten---lets-go)
*  [Hoe werkt die handel?](#hoe-werkt-die-handel)
*  [Hoe zit die code in elkaar? (voor de nerds)](#hoe-zit-die-code-in-elkaar-voor-de-nerds)
*  [Op een VPS knallen (voor de pro's)](#op-een-vps-knallen-voor-de-pros)

## 1. Wat heb je nodig?

*  Python 3.10 of nieuwer (ouder is meh)
*  Een Google-account (duh!) met toegang tot GA4 properties.
*  Een Google Cloud Platform (GCP) projectje.

## 2. Google Cloud Project - ff fixen

Eerst ff wat dingen regelen in de Google Cloud Console. Zonder dit werkt 't niet, maat!

### 2.1. Projectje maken of kiezen

*  Surf naar de [Google Cloud Console](https://console.cloud.google.com/).
*  Maak een nieuw project of pak er eentje die je al had. Easy peasy.

### 2.2. API's aanzetten

In je GCP-project, ga naar `API's & services` > `Bibliotheek`. Zoek deze twee op en zet ze aan:
*  **Google Analytics Admin API**
*  **Google Analytics Data API**
    (Gewoon op 'enable' klikken, niet moeilijk doen)

### 2.3. OAuth-schermpje instellen

*  Ga naar `API's & services` > `OAuth-toestemmingsscherm`.
*  **User Type**: Kies `Extern` (External). Tenzij je zo'n fancy Google Workspace hebt voor je bedrijf, dan kan `Intern`. Klik `Maken`.
*  **App-info**:
    *  **App-naam**: Verzin iets cools (bijv. "Mijn GA Benchmark Ding").
    *  **E-mail voor support**: Jouw mailadres.
    *  **Contactgegevens ontwikkelaar**: Weer jouw mailadres.
    *  Klik `OPSLAAN EN DOORGAAN`.
*  **Scopes**: Hier hoef je niks te doen. De app regelt dit zelf. Klik `OPSLAAN EN DOORGAAN`.
*  **Testgebruikers (Test users)**:
    *  **SUPER BELANGRIJK**: Zolang je app in `Testen` modus staat, moet je hier de Google-accounts toevoegen die de app mogen gebruiken. Klik op `+ ADD USERS` en gooi je eigen e-mailadres (en die van je matties die willen testen) erin.
    *  Klik `OPSLAAN EN DOORGAAN`.
*  Check het overzichtje en ga terug ("BACK TO DASHBOARD"). Je **Publicatiestatus** is nu `Testen`. Nice!

### 2.4. OAuth 2.0 Client-ID fixen

*  Ga naar `API's & services` > `Inloggegevens` (Credentials).
*  Klik `+ INLOGGEGEVENS MAKEN` (+ CREATE CREDENTIALS) > `OAuth-client-ID`.
*  **Type applicatie**: `Webapplicatie` (Web application).
*  **Naam**: Iets herkenbaars (bijv. "GA Benchmark Web Dinges").
*  **Geautoriseerde JavaScript-bronnen**: Voor lokaal testen, voeg `http://localhost:8000` toe. Als je 'm later online gooit op `https://jouwdomein.com`, voeg die dan ook toe.
*  **Geautoriseerde omleidings-URI's**:
    *  Voor lokaal: `http://localhost:8000/auth/callback`.
    *  Voor online: `https://jouwdomein.com/auth/callback`. Zorg dat dit matcht met wat je in je `.env` bestand zet!
*  Klik `MAKEN` (CREATE).
*  Je krijgt nu een **Client-ID** en **Clientgeheim**. **Schrijf deze op of kopieer ze goed!** Die heb je zo nodig.

## 3. Lokaal op je bakkie zetten

### 3.1. Repo clonen (als je 'm van GitHub haalt)

```bash
git clone https://github.com/cramervincent/apigen.git
cd apigen
```

### 3.2. `.env` bestandje maken

*  Je ziet een `.env.dist` bestand. Maak daar een kopietje van en noem 'm `.env`:
    ```bash
    cp .env.dist .env
    ```
*  Open die `.env` en vul 'm met de Client-ID en Clientgeheim van net (stap 2.4):
    ```dotenv
    GOOGLE_CLIENT_ID="PLAK_HIER_JE_CLIENT_ID"
    GOOGLE_CLIENT_SECRET="PLAK_HIER_JE_CLIENTGEHEIM"
    REDIRECT_URI="http://localhost:8000/auth/callback" # Voor lokaal. Online? Dan aanpassen!
    SESSION_SECRET_KEY="MAAK_HIER_EEN_SUPERGEHEIME_LANGE_KEY_VAN_LOL" # ECHT DOEN!
    DATABASE_URL="sqlite:///./benchmark_reports.db" # Prima zo voor nu
    ```
    *  **`SESSION_SECRET_KEY`**: Serieus, maak hier iets randoms en langs van. Google ff op "password generator" ofzo.
    *  **`REDIRECT_URI`**: Als je 'm online zet, verander dit naar je echte URL (bijv. `https://jouwdomein.com/auth/callback`).

### 3.3. Python-dingen installeren

*  Maak een "virtual environment" (soort zandbak voor je Python-project):
    ```bash
    python3 -m venv venv
    ```
*  Activeer 'm:
    *  Mac/Linux:
        ```bash
        source venv/bin/activate
        ```
    *  Windows:
        ```bash
        venv\Scripts\activate
        ```
    (Je terminal laat nu zien dat je in `(venv)` zit)
*  Installeer alle packages (dingen die je code nodig heeft):
    ```bash
    pip install -r requirements.txt
    ```

## 4. App starten - Let's go!

*  Zorg dat je `(venv)` nog actief is.
*  Sta in de root van je project (waar `app/` en `.env` staan).
*  Start die Uvicorn server (dat is het ding dat je app laat draaien):
    ```bash
    uvicorn app.main:app --reload
    ```
    *  `--reload` is chill, want dan herstart 'ie automatisch als je code aanpast.

*  Open je browser en surf naar `http://localhost:8000`. Tadaa!

## 5. Hoe werkt die handel?

*  **Inloggen**: Klik op `Login met Google`. Log in met een account dat je als testgebruiker hebt ingesteld en die toegang heeft tot je GA4-dingen.
*  **Opties kiezen**:
    *  Zoek en vink de GA4 properties aan die je wilt vergelijken.
    *  Kies je periode (start- en einddatum).
    *  Selecteer de metrics en dimensies die je boeiend vindt.
*  **Rapport maken**: Klik op `Genereer & Sla Benchmark Op`.
*  **Resultaat checken**: Je krijgt een pagina met een unieke link. Die link geeft je de benchmarkdata als JSON (nerd-taal voor data). Die kun je delen!

## 6. Hoe zit die code in elkaar? (voor de nerds)

```text
apigen/
├── app/
│   ├── __init__.py         # Zodat Python snapt dat 'app' een ding is
│   ├── main.py             # Hier start de FastAPI-magie
│   ├── config.py           # Alle instellingen enzo
│   ├── database.py         # Database-gedoe (SQLAlchemy)
│   ├── crud.py             # Dingen opslaan en ophalen uit de DB
│   ├── dependencies.py     # Handige hulpjes
│   ├── auth.py             # Google login-shizzle
│   ├── analytics.py        # Google Analytics API-praat
│   ├── routes/
│   │   ├── __init__.py     # Zelfde als hierboven voor 'routes'
│   │   ├── ui.py           # De routes voor de webpagina's
│   │   └── api.py          # De routes voor de JSON API
│   └── templates/          # De HTML-pagina's zelf
│       ├── login.html
│       ├── select_options.html
│       └── report_generated.html
├── .env                    # Jouw geheime instellingen (NIET OP GITHUB ZETTEN!)
├── .env.dist               # Voorbeeldje van .env (deze mag wel op GitHub)
├── requirements.txt        # Lijst met Python-packages
├── README.md               # Dit bestand (je kijkt er nu naar, lol)
└── venv/                   # Je Python zandbak (ook niet op GitHub)
```

## 7. Deployment naar VPS

Deze sectie beschrijft de algemene stappen om de applicatie op een Virtual Private Server (VPS) te deployen (bijv. met Ubuntu).

### 7.1. VPS Voorbereiden

*  **Kies een VPS Provider**: Selecteer een VPS provider (bijv. DigitalOcean, Linode, Vultr, AWS EC2, Google Compute Engine).
*  **Besturingssysteem**: Installeer een Linux distributie, bijvoorbeeld Ubuntu 20.04 LTS of nieuwer.
*  **SSH Toegang**: Zorg dat je SSH toegang hebt tot je server.
*  **Basis Server Setup**:
    *  Update je server: `sudo apt update && sudo apt upgrade -y`
    *  Maak een non-root gebruiker aan met sudo privileges.
    *  Configureer een firewall (bijv. `ufw`):
        ```bash
        sudo ufw allow OpenSSH
        sudo ufw allow http
        sudo ufw allow https
        sudo ufw enable
        ```

### 7.2. Software Installeren op VPS

*  **Python & Pip & Venv**:
    ```bash
    sudo apt install python3 python3-pip python3-venv -y
    ```
*  **Git**:
    ```bash
    sudo apt install git -y
    ```
*  **Nginx (als reverse proxy)**:
    ```bash
    sudo apt install nginx -y
    ```
*  **(Optioneel) Certbot (voor SSL/TLS met Let's Encrypt)**:
    ```bash
    sudo apt install certbot python3-certbot-nginx -y
    ```

### 7.3. Applicatie Deployen

*  **Kloon de Repository**: Log in op je VPS (als je non-root gebruiker) en kloon je repository:
    ```bash
    git clone https://github.com/cramervincent/apigen.git
    cd apigen
    ```
*  **Virtuele Omgeving en Dependencies**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install uvicorn gunicorn # Gunicorn wordt vaak gebruikt met Uvicorn in productie
    ```
*  **`.env` Bestand Configureren op de Server**:
    *  Kopieer `.env.dist` naar `.env`: `cp .env.dist .env`
    *  **BELANGRIJK**: Bewerk het `.env` bestand op de server met je **productie** configuraties:
        *  `GOOGLE_CLIENT_ID` en `GOOGLE_CLIENT_SECRET` (dezelfde als lokaal).
        *  `REDIRECT_URI`: Verander dit naar je publieke URL, bijv. `https://jouwdomein.com/auth/callback`. Zorg dat deze URI ook is toegevoegd aan je GCP OAuth Client ID configuratie.
        *  `SESSION_SECRET_KEY`: Gebruik een sterke, unieke sleutel.
        *  `DATABASE_URL`: Als je SQLite gebruikt, kun je het pad zo laten. Overweeg voor productie een robuustere database zoals PostgreSQL.
    *  **Plaats het `.env` bestand NOOIT in je Git repository!**

### 7.4. Gunicorn & Uvicorn Draaien

Gunicorn is een WSGI HTTP server die vaak wordt gebruikt om Python webapplicaties in productie te draaien. Het kan Uvicorn workers beheren.

*  **Test Gunicorn lokaal (in je projectmap op de VPS)**:
    ```bash
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app -b 0.0.0.0:8000
    ```
    *  `-w 4`: Aantal worker processen (pas aan op basis van je server resources, `2 * aantal_cores + 1` is een gangbare start).
    *  `-k uvicorn.workers.UvicornWorker`: Gebruik Uvicorn workers voor ASGI.
    *  `app.main:app`: Verwijst naar je FastAPI app instantie.
    *  `-b 0.0.0.0:8000`: Bind aan alle interfaces op poort 8000.

### 7.5. Systemd Service Maken (om de app als service te draaien)

Maak een systemd service bestand om je applicatie automatisch te starten en te beheren.

*  Maak een service bestand, bijv. `/etc/systemd/system/ga_benchmark.service`:
    ```ini
    [Unit]
    Description=GA Benchmark FastAPI Application
    After=network.target

    [Service]
    User=<jouw-non-root-gebruikersnaam>
    Group=<jouw-non-root-gebruikersnaam> # of www-data als Nginx onder die groep draait
    WorkingDirectory=/pad/naar/jouw/apigen # Verander dit naar het absolute pad
    Environment="PATH=/pad/naar/jouw/apigen/venv/bin" # Zorg dat de venv Python wordt gebruikt
    # EnvironmentFile=/pad/naar/jouw/apigen/.env # Alternatief voor .env laden, vereist aanpassingen in Pydantic config
    ExecStart=/pad/naar/jouw/apigen/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app -b 127.0.0.1:8000

    Restart=always
    RestartSec=5s # Herstart na 5 seconden bij een crash

    [Install]
    WantedBy=multi-user.target
    ```
    *  Vervang `<jouw-non-root-gebruikersnaam>` en `/pad/naar/jouw/apigen` met de juiste waarden.
    *  De `-b 127.0.0.1:8000` zorgt ervoor dat Gunicorn alleen lokaal luistert; Nginx zal de publieke requests afhandelen.

*  Herlaad systemd, start en enable de service:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl start ga_benchmark
    sudo systemctl enable ga_benchmark # Start automatisch bij boot
    sudo systemctl status ga_benchmark # Controleer de status
    ```

### 7.6. Nginx Configureren als Reverse Proxy

Nginx zal requests van het internet ontvangen en doorsturen naar je Gunicorn/Uvicorn applicatie. Het kan ook statische bestanden serveren en SSL/TLS (HTTPS) afhandelen.

*  Maak een Nginx configuratiebestand voor je site, bijv. `/etc/nginx/sites-available/ga_benchmark`:
    ```nginx
    server {
        listen 80;
        server_name jouwdomein.com www.jouwdomein.com; # Verander naar jouw domeinnaam

        location / {
            proxy_pass http://127.0.0.1:8000; # Stuur door naar Gunicorn
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /static { # Als je statische bestanden hebt (niet in dit project)
            alias /pad/naar/jouw/apigen/app/static;
        }
    }
    ```
    *  Vervang `jouwdomein.com` door je daadwerkelijke domeinnaam.

*  Maak een symbolische link naar `sites-enabled`:
    ```bash
    sudo ln -s /etc/nginx/sites-available/ga_benchmark /etc/nginx/sites-enabled/
    ```
*  Test de Nginx configuratie en herstart Nginx:
    ```bash
    sudo nginx -t
    sudo systemctl restart nginx
    ```

### 7.7. SSL/TLS Certificaat met Certbot (HTTPS)

*  Verkrijg en installeer een Let's Encrypt certificaat:
    ```bash
    sudo certbot --nginx -d jouwdomein.com -d www.jouwdomein.com
    ```
    *  Volg de instructies. Certbot zal je Nginx configuratie automatisch aanpassen voor HTTPS.

*  Certbot zal ook een cron job of systemd timer instellen om het certificaat automatisch te vernieuwen.

Na deze stappen zou je applicatie bereikbaar moeten zijn via `https://jouwdomein.com`. Controleer de logs (`sudo journalctl -u ga_benchmark` en Nginx logs in `/var/log/nginx/`) als er problemen zijn.

---


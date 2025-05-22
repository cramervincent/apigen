Google Analytics Benchmark Tool
===============================

Deze FastAPI-applicatie stelt gebruikers in staat om in te loggen met hun Google-account, Google Analytics (GA4) properties te selecteren, en vervolgens een benchmarkrapport te genereren op basis van geaggregeerde data van de geselecteerde properties. De resultaten worden opgeslagen in een database en zijn toegankelijk via een unieke, deelbare URL. De gebruiker kan zelf de periode, metrics en dimensies voor de benchmark selecteren.

Inhoudsopgave
-------------

1.  [Vereisten](#vereisten)
    
2.  [Google Cloud Project Configuratie](#google-cloud-project-configuratie)
    
3.  [Lokale Installatie en Configuratie](#lokale-installatie-en-configuratie)
    
4.  [Applicatie Draaien](#applicatie-draaien)
    
5.  [Gebruik](#gebruik)
    
6.  [Projectstructuur](#projectstructuur)
    

1\. Vereisten
-------------

*   Python 3.10+
    
*   Een Google-account met toegang tot Google Analytics 4 properties.
    
*   Een Google Cloud Platform (GCP) project.
    

2\. Google Cloud Project Configuratie
-------------------------------------

Voordat je de applicatie kunt gebruiken, moet je een project configureren in de Google Cloud Console.

### 2.1. Project Aanmaken of Selecteren

*   Ga naar de [Google Cloud Console](https://console.cloud.google.com/).
    
*   Maak een nieuw project aan of selecteer een bestaand project.
    

### 2.2. API's Inschakelen

Navigeer in je GCP-project naar "API's en services" > "Bibliotheek". Zoek en schakel de volgende API's in:

*   **Google Analytics Admin API**
    
*   **Google Analytics Data API**
    

### 2.3. OAuth-toestemmingsscherm Configureren

1.  Ga naar "API's en services" > "OAuth-toestemmingsscherm".
    
2.  Kies **User Type**: "Extern" (External), tenzij je een Google Workspace-organisatie hebt en het intern wilt houden. Klik op "Maken".
    
3.  **App-informatie**:
    
    *   Vul een **App-naam** in (bijv. "GA Benchmark Tool").
        
    *   Vul je **E-mailadres voor gebruikersondersteuning** (User support email) in.
        
    *   Vul de **Contactgegevens van ontwikkelaar** (Developer contact information) in.
        
    *   Klik op "OPSLAAN EN DOORGAAN".
        
4.  **Scopes**: Je hoeft hier geen scopes handmatig toe te voegen; de applicatie specificeert de benodigde scopes. Klik op "OPSLAAN EN DOORGAAN".
    
5.  **Testgebruikers (Test users)**:
    
    *   **Belangrijk**: Zolang je app in de "Testen" (Testing) modus staat, moet je hier de Google-accounts toevoegen die de applicatie mogen gebruiken. Klik op "+ ADD USERS" en voeg het e-mailadres toe van het Google-account waarmee je wilt inloggen.
        
    *   Klik op "OPSLAAN EN DOORGAAN".
        
6.  Controleer het overzicht en ga terug naar het dashboard ("BACK TO DASHBOARD"). De **Publicatiestatus** (Publishing status) zal "Testen" zijn.
    

### 2.4. OAuth 2.0 Client-ID Aanmaken

1.  Ga naar "API's en services" > "Inloggegevens" (Credentials).
    
2.  Klik op "+ INLOGGEGEVENS MAKEN" (+ CREATE CREDENTIALS) > "OAuth-client-ID".
    
3.  **Type applicatie (Application type)**: Selecteer "Webapplicatie" (Web application).
    
4.  **Naam (Name)**: Geef het een naam (bijv. "GA Benchmark Web Client").
    
5.  **Geautoriseerde JavaScript-bronnen (Authorized JavaScript origins)**: Voor lokale ontwikkeling, voeg http://localhost:8000 toe.
    
6.  **Geautoriseerde** omleidings-URI's (Authorized redirect **URIs)**:
    
    *   Voeg http://localhost:8000/auth/callback toe. Dit moet exact overeenkomen met de REDIRECT\_URI in je .env bestand.
        
7.  Klik op "MAKEN" (CREATE).
    
8.  Je krijgt nu een **Client-ID** en **Clientgeheim** (Client secret) te zien. **Kopieer deze waarden zorgvuldig.** Je hebt ze nodig voor je .env bestand.
    

3\. Lokale Installatie en Configuratie
--------------------------------------

### 3.1. Repository Klonen (indien van toepassing)

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`git clone   cd` 

### 3.2. .env Bestand Configureren

1.  cp .env.dist .env
    
2.  GOOGLE\_CLIENT\_ID="JOUW\_GOOGLE\_CLIENT\_ID\_HIER"GOOGLE\_CLIENT\_SECRET="JOUW\_GOOGLE\_CLIENT\_SECRET\_HIER"REDIRECT\_URI="http://localhost:8000/auth/callback" # Moet overeenkomen met GCP configuratieSESSION\_SECRET\_KEY="GENEREER\_EEN\_STERKE\_WILLEKEURIGE\_STRING\_HIER" # Zeer belangrijk voor beveiliging!DATABASE\_URL="sqlite:///./benchmark\_reports.db" # Standaard SQLite, kan aangepast worden
    
    *   **SESSION\_SECRET\_KEY**: Vervang dit door een lange, willekeurige en geheime string. Je kunt er een genereren met bijvoorbeeld openssl rand -hex 32 in je terminal.
        

### 3.3. Python Virtuele Omgeving en Dependencies

1.  python3 -m venv venv
    
2.  Activeer de virtuele omgeving:
    
    *   source venv/bin/activate
        
    *   venv\\Scripts\\activate
        
3.  pip install -r requirements.txt
    

4\. Applicatie Draaien
----------------------

1.  Zorg ervoor dat je virtuele omgeving geactiveerd is.
    
2.  Navigeer in je terminal naar de root van het project (de map waar app/ en .env zich bevinden, bijv. apigen).
    
3.  uvicorn app.main:app --reload
    
    *   app.main:app verwijst naar de app instantie in het main.py bestand binnen de app map/package.
        
    *   \--reload zorgt ervoor dat de server automatisch herstart bij codewijzigingen (handig tijdens ontwikkeling).
        
4.  Open je browser en ga naar http://localhost:8000.
    

5\. Gebruik
-----------

1.  **Login**: Klik op "Login met Google" en log in met een account dat je hebt toegevoegd als testgebruiker in de GCP Console en dat toegang heeft tot GA4 properties.
    
2.  **Selecteer Opties**:
    
    *   Zoek en selecteer de GA4 properties die je wilt benchmarken.
        
    *   Kies de gewenste periode (start- en einddatum).
        
    *   Selecteer de metrics en dimensies die je wilt opnemen.
        
3.  **Genereer Rapport**: Klik op "Genereer & Sla Benchmark Op".
    
4.  **Bekijk Resultaat**: Je krijgt een pagina te zien met een unieke URL naar het opgeslagen rapport. Deze URL retourneert de benchmarkdata in JSON-formaat en kan gedeeld worden.
    

6\. Projectstructuur
--------------------

Plain textANTLR4BashCC#CSSCoffeeScriptCMakeDartDjangoDockerEJSErlangGitGoGraphQLGroovyHTMLJavaJavaScriptJSONJSXKotlinLaTeXLessLuaMakefileMarkdownMATLABMarkupObjective-CPerlPHPPowerShell.propertiesProtocol BuffersPythonRRubySass (Sass)Sass (Scss)SchemeSQLShellSwiftSVGTSXTypeScriptWebAssemblyYAMLXML`   apigen/  ├── app/  │   ├── __init__.py         # Maakt 'app' een Python package  │   ├── main.py             # Hoofd FastAPI app instantie, middleware, routers  │   ├── config.py           # Configuratie (Pydantic settings)  │   ├── database.py         # SQLAlchemy setup (engine, SessionLocal, Base, DB Model)  │   ├── crud.py             # Database operaties (opslaan/ophalen rapporten)  │   ├── dependencies.py     # Herbruikbare dependencies (get_db)  │   ├── auth.py             # Google OAuth flow logica  │   ├── analytics.py        # Google Analytics API logica & dataverwerking  │   ├── routes/  │   │   ├── __init__.py     # Maakt 'routes' een Python package  │   │   ├── ui.py           # Routes die HTML pagina's serveren (Jinja2 templates)  │   │   └── api.py          # Routes die JSON data serveren (API-endpoints)  │   └── templates/          # HTML templates (Jinja2)  │       ├── login.html  │       ├── select_options.html  │       └── report_generated.html  ├── .env                    # Lokale configuratie (secrets, etc. - NIET in Git!)  ├── .env.dist               # Voorbeeld .env bestand (WEL in Git)  ├── requirements.txt        # Python dependencies  ├── README.md               # Dit bestand  └── venv/                   # Python virtuele omgeving (NIET in Git)   `
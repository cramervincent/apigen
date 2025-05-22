# app/config.py
from pydantic_settings import BaseSettings
from typing import List, Dict

class Settings(BaseSettings):
    GOOGLE_CLIENT_ID: str = "YOUR_GOOGLE_CLIENT_ID"
    GOOGLE_CLIENT_SECRET: str = "YOUR_GOOGLE_CLIENT_SECRET"
    REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    SESSION_SECRET_KEY: str = "super-secret-key-for-demonstration-change-me" # VERANDER DIT!
    DATABASE_URL: str = "sqlite:///./benchmark_reports.db"

    SCOPES: List[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/analytics.readonly",
    ]

    # Beschikbare Metrics en Dimensions
    AVAILABLE_METRICS: Dict[str, str] = {
        "sessions": "Sessies", "engagedSessions": "Betrokken sessies", 
        "screenPageViews": "Scherm-/paginawergaven", "totalUsers": "Totaal aantal gebruikers", 
        "newUsers": "Nieuwe gebruikers", "transactions": "Transactie", "averagePurchaseRevenue": "Average Purchase Revenue",
        "averageRevenuePerUser": "Average revenue per user", "bounceRate": "Bounce rate", "purchaserRate": "Purchaser rate",
        "eventCount": "Aantal gebeurtenissen", "averageSessionDuration": "Gem. sessieduur (sec)",
        "engagementRate": "Betrokkenheidspercentage (%)"
    }
    DEFAULT_METRICS: List[str] = ["sessions"]

    AVAILABLE_DIMENSIONS: Dict[str, str] = {
        "date": "Datum", "country": "Land", "city": "Plaats", 
        "deviceCategory": "Apparaatcategorie", 
        "sessionDefaultChannelGroup": "Standaard kanaalgroepering voor sessies",
        "landingPagePlusQueryString": "Landingspagina + querystring", "eventName": "Gebeurtenisnaam"
    }
    DEFAULT_DIMENSIONS: List[str] = ["date"]

    DEFAULT_START_DAYS_AGO: int = 28
    DEFAULT_END_DAYS_AGO: int = 1

    class Config:
        env_file = ".env" # Laadt .env vanuit de root van het project (apigen/.env)
        env_file_encoding = 'utf-8'
        extra = 'ignore' 

settings = Settings()
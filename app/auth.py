# app/auth.py
from typing import Optional
from fastapi import Request
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from .config import settings # Importeer settings

def get_google_credentials_from_session(request: Request) -> Optional[Credentials]:
    creds_info = request.session.get("credentials")
    if not creds_info: 
        return None
    
    # Zorg dat token een string is
    if isinstance(creds_info.get("token"), bytes): 
        creds_info["token"] = creds_info["token"].decode('utf-8')
    
    # Zorg dat scopes een lijst is
    if isinstance(creds_info.get("scopes"), str): 
        creds_info["scopes"] = creds_info["scopes"].split()
    
    # Vul standaardwaarden aan als ze missen, Credentials verwacht deze.
    creds_info_complete = {
        "token": creds_info.get("token"),
        "refresh_token": creds_info.get("refresh_token"), # Kan None zijn
        "id_token": creds_info.get("id_token"), # Kan None zijn
        "token_uri": creds_info.get("token_uri", "https://oauth2.googleapis.com/token"),
        "client_id": creds_info.get("client_id", settings.GOOGLE_CLIENT_ID),
        "client_secret": creds_info.get("client_secret", settings.GOOGLE_CLIENT_SECRET),
        "scopes": creds_info.get("scopes", settings.SCOPES)
    }
    return Credentials(**creds_info_complete)

def store_credentials_in_session(request: Request, credentials: Credentials):
    request.session["credentials"] = {
        "token": credentials.token, 
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri, 
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret, 
        "scopes": credentials.scopes,
        "id_token": getattr(credentials, 'id_token', None)
    }

def get_google_flow() -> Flow:
    client_config = {"web": {
        "client_id": settings.GOOGLE_CLIENT_ID, 
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token", 
        "redirect_uris": [settings.REDIRECT_URI],
    }}
    return Flow.from_client_config(
        client_config=client_config, 
        scopes=settings.SCOPES, 
        redirect_uri=settings.REDIRECT_URI
    )
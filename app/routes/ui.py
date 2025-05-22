# app/routes/ui.py
import json
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates # Nieuw
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..auth import get_google_credentials_from_session, get_google_flow, store_credentials_in_session
from ..config import settings # Importeer settings
from ..crud import create_benchmark_report
from ..analytics import generate_benchmark_data_from_google

# Google API Clients
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import ListAccountSummariesRequest
from google.oauth2 import id_token as google_id_token # Alias om conflicten te vermijden
from google.auth.transport import requests as google_auth_requests


router = APIRouter()

# Configureer Jinja2 templates
templates = Jinja2Templates(directory="app/templates") # Verwijst naar apigen/app/templates

@router.get("/", response_class=HTMLResponse, name="home_route")
async def home(request: Request):
    if get_google_credentials_from_session(request):
        return RedirectResponse(url=request.url_for("select_accounts_page_endpoint"), status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/login", name="login_google_route")
async def login_google(request: Request):
    if settings.GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID" or settings.GOOGLE_CLIENT_SECRET == "YOUR_GOOGLE_CLIENT_SECRET":
        return HTMLResponse("<h1>Configuratie Fout</h1><p>Google Client ID/Secret niet ingesteld in .env of config.</p>", status_code=500)
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    request.session["oauth_state"] = state
    return RedirectResponse(url=authorization_url)

@router.get("/auth/callback", name="auth_callback_route")
async def auth_callback_google(request: Request, code: str, state: str):
    session_state = request.session.pop("oauth_state", None)
    if not session_state or state != session_state: 
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    flow = get_google_flow()
    try:
        flow.fetch_token(code=code)
        store_credentials_in_session(request, flow.credentials)
        if flow.credentials and flow.credentials.id_token:
            id_info = google_id_token.verify_oauth2_token(
                flow.credentials.id_token, 
                google_auth_requests.Request(), 
                settings.GOOGLE_CLIENT_ID
            )
            request.session["user_email"] = id_info.get("email")
    except Exception as e:
        print(f"Error fetching token: {e}")
        raise HTTPException(status_code=500, detail=f"Kon token niet ophalen van Google: {e}")
    return RedirectResponse(url=request.url_for("select_accounts_page_endpoint"))

@router.get("/logout", name="logout_route")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=request.url_for("home_route"))

@router.get("/select-accounts", response_class=HTMLResponse, name="select_accounts_page_endpoint")
async def select_accounts_page_endpoint(request: Request):
    credentials = get_google_credentials_from_session(request)
    if not credentials: 
        return RedirectResponse(url=request.url_for("home_route"), status_code=302)
    
    ga_properties = []
    error_message = None
    try:
        admin_client = AnalyticsAdminServiceClient(credentials=credentials)
        summaries = admin_client.list_account_summaries(request=ListAccountSummariesRequest(page_size=200))
        for acc_sum in summaries:
            for prop_sum in getattr(acc_sum, 'property_summaries', []):
                 if "properties/" in prop_sum.property: # Zorg dat het een GA4 property ID is
                    ga_properties.append({
                        "id": prop_sum.property, 
                        "name": f"{prop_sum.display_name or 'N/A'} (Account: {acc_sum.display_name or 'N/A'})"
                    })
    except Exception as e:
        print(f"Error fetching account summaries: {e}")
        error_message = f"Fout bij ophalen GA properties: {e}"
        if any(keyword in str(e).upper() for keyword in ["INVALID_GRANT", "TOKEN HAS BEEN EXPIRED", "UNAUTHENTICATED", "PERMISSION_DENIED"]):
            request.session.clear()
            # Redirect naar home met een error message kan via query params, maar voor nu simpele redirect.
            return RedirectResponse(url=request.url_for("home_route") + "?error=auth_failed", status_code=302)
        # Voor andere errors, toon een foutpagina of detail.

    user_email = request.session.get("user_email", "Onbekend")
    default_start_date_val = (datetime.now() - timedelta(days=settings.DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d")
    default_end_date_val = (datetime.now() - timedelta(days=settings.DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d")

    context = {
        "request": request,
        "properties": sorted(ga_properties, key=lambda p: p['name'].lower()),
        "user_email": user_email,
        "available_metrics": settings.AVAILABLE_METRICS,
        "default_metrics": settings.DEFAULT_METRICS,
        "available_dimensions": settings.AVAILABLE_DIMENSIONS,
        "default_dimensions": settings.DEFAULT_DIMENSIONS,
        "default_start_date": default_start_date_val,
        "default_end_date": default_end_date_val,
        "error_message": error_message # Geef error message door aan template
    }
    return templates.TemplateResponse("select_options.html", context)


@router.post("/generate-benchmark", response_class=HTMLResponse, name="generate_and_save_benchmark_route")
async def generate_and_save_benchmark_endpoint(
    request: Request, 
    property_ids: Optional[List[str]] = Form(None),
    selected_metrics: List[str] = Form(...), 
    selected_dimensions: List[str] = Form(...), 
    start_date: str = Form(...), 
    end_date: str = Form(...),   
    db: Session = Depends(get_db)
):
    credentials = get_google_credentials_from_session(request)
    if not credentials: 
        return RedirectResponse(url=request.url_for("home_route") + "?error=not_logged_in", status_code=302)
    
    if not property_ids:
        # Je kunt hier een TemplateResponse teruggeven met de foutmelding.
        return templates.TemplateResponse("select_options.html", {
            "request": request, "error_message_form": "Selecteer ten minste één GA4 property.",
            # Geef andere context variabelen opnieuw mee voor de form fields
            "properties": [], # Of haal opnieuw op
            "user_email": request.session.get("user_email", "Onbekend"),
            "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": selected_metrics,
            "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": selected_dimensions,
            "default_start_date": start_date, "default_end_date": end_date
        }, status_code=400)
    
    # Validatie voor metrics en dimensions (en datums)
    if not selected_metrics or not selected_dimensions:
        # Idem, geef template terug met fout
        return templates.TemplateResponse("select_options.html", {
            "request": request, "error_message_form": "Selecteer ten minste één metric en één dimensie.",
            "properties": [], "user_email": request.session.get("user_email", "Onbekend"),
            "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": selected_metrics,
            "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": selected_dimensions,
            "default_start_date": start_date, "default_end_date": end_date
        }, status_code=400)

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
        if start_date > end_date: 
            raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except ValueError as ve:
        return templates.TemplateResponse("select_options.html", {
            "request": request, "error_message_form": f"Ongeldige datums: {ve}",
            "properties": [], "user_email": request.session.get("user_email", "Onbekend"),
            "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": selected_metrics,
            "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": selected_dimensions,
            "default_start_date": start_date, "default_end_date": end_date
        }, status_code=400)

    try:
        benchmark_results = await generate_benchmark_data_from_google(
            credentials, property_ids, selected_metrics, selected_dimensions, start_date, end_date
        )
    except ValueError as e: 
         return templates.TemplateResponse("select_options.html", { # Geef fout terug op dezelfde pagina
            "request": request, "error_message_form": f"Fout bij genereren benchmark: {e}",
            "properties": [], "user_email": request.session.get("user_email", "Onbekend"),
            "available_metrics": settings.AVAILABLE_METRICS, "default_metrics": selected_metrics,
            "available_dimensions": settings.AVAILABLE_DIMENSIONS, "default_dimensions": selected_dimensions,
            "default_start_date": start_date, "default_end_date": end_date
        }, status_code=500)
    except Exception as e:
        print(f"Onverwachte fout bij genereren benchmark data: {e}")
        # Algemene foutpagina of terug naar selectie met generieke fout
        return HTMLResponse(f"<h1>Onverwachte fout</h1><p>Details: {e}. Probeer het later opnieuw.</p><a href='{request.url_for('select_accounts_page_endpoint')}'>Terug</a>", status_code=500)

    user_email = request.session.get("user_email")
    db_report_obj = create_benchmark_report(
        db=db, 
        property_ids=property_ids,
        metrics_used=selected_metrics,
        dimensions_used=selected_dimensions,
        benchmark_results=benchmark_results, 
        user_email=user_email
    )

    report_url = request.url_for("get_saved_report_api", report_uuid=db_report_obj.report_uuid)
    return templates.TemplateResponse("report_generated.html", {"request": request, "report_url": str(report_url)})
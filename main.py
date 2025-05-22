import os
import json # Voor het serialiseren van benchmark data naar JSON
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone # timezone voor created_at
import uuid # Voor unieke IDs
from collections import defaultdict # Voor het makkelijk sommeren van metrics per dimensiecombinatie

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

# Google OAuth en API Client imports
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import ListAccountSummariesRequest
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
    DimensionHeader, 
    MetricHeader,    
)

# SQLAlchemy imports voor database
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

import uvicorn
from dotenv import load_dotenv

# Laad environment variabelen van .env bestand
load_dotenv()

# --- Configuratie ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8000/auth/callback")
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "super-secret-key-for-demonstration")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./benchmark_reports.db")
SCOPES = [
    "openid", "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/analytics.readonly",
]

AVAILABLE_METRICS = {
    "sessions": "Sessies", "engagedSessions": "Betrokken sessies", "screenPageViews": "Scherm-/paginawergaven",
    "totalUsers": "Totaal aantal gebruikers", "newUsers": "Nieuwe gebruikers", "conversions": "Conversies", 
    "eventCount": "Aantal gebeurtenissen", "averageSessionDuration": "Gem. sessieduur (sec)",
    "engagementRate": "Betrokkenheidspercentage (%)"
}
DEFAULT_METRICS = ["sessions", "engagedSessions", "totalUsers", "screenPageViews"]

AVAILABLE_DIMENSIONS = {
    "date": "Datum", "country": "Land", "city": "Plaats", "deviceCategory": "Apparaatcategorie",
    "sessionDefaultChannelGroup": "Standaard kanaalgroepering voor sessies",
    "landingPagePlusQueryString": "Landingspagina + querystring", "eventName": "Gebeurtenisnaam"
}
DEFAULT_DIMENSIONS = ["date"] 

DEFAULT_START_DAYS_AGO = 28
DEFAULT_END_DAYS_AGO = 1

# --- Database Setup (SQLAlchemy) ---
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class BenchmarkReportDB(Base):
    __tablename__ = "benchmark_reports"
    id = Column(Integer, primary_key=True, index=True)
    report_uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    property_ids_used = Column(Text) 
    metrics_used = Column(Text) 
    dimensions_used = Column(Text) 
    benchmark_data_json = Column(Text) 
    generated_by_email = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

app = FastAPI(title="Google Analytics Benchmark Tool met Gemiddelden per Dimensiecombinatie")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)

def get_google_credentials_from_session(request: Request) -> Optional[Credentials]:
    creds_info = request.session.get("credentials")
    if not creds_info: return None
    if isinstance(creds_info.get("token"), bytes): creds_info["token"] = creds_info["token"].decode('utf-8')
    if isinstance(creds_info.get("scopes"), str): creds_info["scopes"] = creds_info["scopes"].split()
    return Credentials(**creds_info)

def store_credentials_in_session(request: Request, credentials):
    request.session["credentials"] = {
        "token": credentials.token, "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri, "client_id": credentials.client_id,
        "client_secret": credentials.client_secret, "scopes": credentials.scopes,
        "id_token": getattr(credentials, 'id_token', None)
    }

def get_google_flow() -> Flow:
    client_config = {"web": {"client_id": GOOGLE_CLIENT_ID, "client_secret": GOOGLE_CLIENT_SECRET,
                             "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                             "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": [REDIRECT_URI]}}
    return Flow.from_client_config(client_config=client_config, scopes=SCOPES, redirect_uri=REDIRECT_URI)

def html_login_page():
    return """<html><head><title>Login</title><style>body{font-family:sans-serif;padding:20px;}.btn{padding:10px 15px;background-color:#4285F4;color:white;text-decoration:none;border-radius:5px;}</style></head><body><h1>Google Analytics Benchmark Tool</h1><p>Log in met je Google-account om een benchmark rapport te genereren en op te slaan.</p><a href="/login" class="btn">Login met Google</a></body></html>"""

def html_select_accounts_page(properties: List[Dict[str, str]], user_email: str, 
                              available_metrics: Dict[str,str], default_metrics: List[str],
                              available_dimensions: Dict[str,str], default_dimensions: List[str],
                              default_start_date: str, default_end_date: str):
    property_search_html = """<div style="margin-bottom:15px;"><label for="propertySearch" style="display:block;margin-bottom:5px;font-weight:bold;">Zoek GA4 Property:</label><input type="text" id="propertySearch" onkeyup="filterProperties()" placeholder="Typ om te filteren..." style="width:100%;padding:8px;box-sizing:border-box;border:1px solid #ccc;border-radius:4px;"></div><div id="propertyListContainer" style="max-height:200px;overflow-y:auto;border:1px solid #eee;padding:10px;margin-bottom:20px;background-color:#f9f9f9;border-radius:4px;">"""
    property_options_html = "".join([f"""<div class="property-item" data-name="{prop['name'].lower()} {prop['id'].lower()}"><input type="checkbox" name="property_ids" value="{prop['id']}" id="prop_{prop['id']}"><label for="prop_{prop['id']}">{prop['name']} ({prop['id']})</label></div>""" for prop in properties]) if properties else "<p>Geen Google Analytics GA4 properties gevonden of geen toegang.</p>"
    property_search_html += property_options_html + "</div>"
    date_range_html = f"""<h3 style='margin-top:20px;margin-bottom:10px;'>Selecteer Periode:</h3><div style="display:flex;gap:20px;margin-bottom:20px;"><div><label for="start_date" style="display:block;margin-bottom:5px;">Startdatum:</label><input type="date" id="start_date" name="start_date" value="{default_start_date}" style="padding:8px;border:1px solid #ccc;border-radius:4px;"></div><div><label for="end_date" style="display:block;margin-bottom:5px;">Einddatum:</label><input type="date" id="end_date" name="end_date" value="{default_end_date}" style="padding:8px;border:1px solid #ccc;border-radius:4px;"></div></div>"""
    metrics_html = "<h3 style='margin-top:20px;margin-bottom:10px;'>Selecteer Metrics:</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;'>"
    for key, desc in available_metrics.items():
        checked = "checked" if key in default_metrics else ""
        metrics_html += f"""<div style="padding:5px;border:1px solid #e0e0e0;border-radius:4px;background-color:#fff;"><input type="checkbox" name="selected_metrics" value="{key}" id="metric_{key}" {checked}><label for="metric_{key}">{desc} (<code>{key}</code>)</label></div>"""
    metrics_html += "</div>"
    dimensions_html = "<h3 style='margin-top:20px;margin-bottom:10px;'>Selecteer Dimensions:</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;'>"
    for key, desc in available_dimensions.items():
        checked = "checked" if key in default_dimensions else ""
        dimensions_html += f"""<div style="padding:5px;border:1px solid #e0e0e0;border-radius:4px;background-color:#fff;"><input type="checkbox" name="selected_dimensions" value="{key}" id="dim_{key}" {checked}><label for="dim_{key}">{desc} (<code>{key}</code>)</label></div>"""
    dimensions_html += "</div>"
    js_filter_script = """<script>function filterProperties(){var e=document.getElementById("propertySearch").value.toLowerCase(),t=document.getElementById("propertyListContainer").getElementsByClassName("property-item");for(var o=0;o<t.length;o++)t[o].style.display=-1<t[o].getAttribute("data-name").indexOf(e)?"":"none"}</script>"""
    return f"""<html><head><title>Selecteer Opties</title><style>body{{font-family:Arial,sans-serif;padding:20px;background-color:#f4f7f6;color:#333}}h1{{color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:10px}}h3{{color:#34495e;margin-top:30px}}label{{margin-left:5px;color:#555}}code{{background-color:#e8f0f3;padding:2px 5px;border-radius:3px;font-family:monospace;color:#2980b9}}.btn{{padding:12px 20px;background-image:linear-gradient(to right,#3498db,#2980b9);color:white;border:none;border-radius:5px;cursor:pointer;text-decoration:none;display:inline-block;margin-top:25px;font-size:16px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}}.btn:hover{{background-image:linear-gradient(to right,#2980b9,#3498db)}}.logout-btn{{color:#e74c3c;margin-left:15px;text-decoration:none}}.logout-btn:hover{{text-decoration:underline}}form>div{{margin-bottom:15px}}input[type="checkbox"]+label{{cursor:pointer}}input[type="date"]{{font-family:Arial,sans-serif;font-size:14px}}</style></head><body><h1>Selecteer Benchmark Opties</h1><p>Ingelogd als: <strong>{user_email}</strong></p><form action="/generate-benchmark" method="post"><h3 style='margin-top:0;'>Selecteer GA4 Properties:</h3>{property_search_html}{date_range_html}{metrics_html}{dimensions_html}<br><button type="submit" class="btn">Genereer & Sla Benchmark Op</button></form><br><a href="/logout" class="logout-btn">Uitloggen</a>{js_filter_script}</body></html>"""

def html_report_generated_page(report_url: str):
    return f"""<html><head><title>Benchmark Opgeslagen</title><style>body{{font-family:Arial,sans-serif;padding:20px;background-color:#f4f7f6;color:#333}}h1{{color:#2c3e50}}a{{color:#3498db;text-decoration:none}}a:hover{{text-decoration:underline}}.btn{{padding:10px 15px;background-color:#2ecc71;color:white;border-radius:5px;display:inline-block;margin-top:20px}}.home-btn{{margin-left:10px;background-color:#95a5a6}}</style></head><body><h1>Benchmark Rapport Opgeslagen!</h1><p>Je benchmark rapport is succesvol gegenereerd en opgeslagen.</p><p>Je kunt het hier bekijken en delen: <a href="{report_url}"><strong>{report_url}</strong></a></p><br><a href="/select-accounts" class="btn">Nieuwe Benchmark Genereren</a><a href="/" class="btn home-btn">Home</a></body></html>"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if get_google_credentials_from_session(request): return RedirectResponse(url="/select-accounts", status_code=302)
    return html_login_page()

@app.get("/login")
async def login_google(request: Request):
    if GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID" or GOOGLE_CLIENT_SECRET == "YOUR_GOOGLE_CLIENT_SECRET":
        return HTMLResponse("<h1>Configuratie Fout</h1><p>Google Client ID/Secret niet ingesteld.</p>", status_code=500)
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(access_type="offline", prompt="consent")
    request.session["oauth_state"] = state
    return RedirectResponse(url=authorization_url)

@app.get("/auth/callback")
async def auth_callback_google(request: Request, code: str, state: str):
    session_state = request.session.pop("oauth_state", None)
    if not session_state or state != session_state: raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    flow = get_google_flow()
    try:
        flow.fetch_token(code=code)
        store_credentials_in_session(request, flow.credentials)
        if flow.credentials and flow.credentials.id_token:
            from google.oauth2 import id_token
            from google.auth.transport import requests as google_auth_requests
            id_info = id_token.verify_oauth2_token(flow.credentials.id_token, google_auth_requests.Request(), GOOGLE_CLIENT_ID)
            request.session["user_email"] = id_info.get("email")
    except Exception as e:
        print(f"Error fetching token: {e}")
        raise HTTPException(status_code=500, detail=f"Kon token niet ophalen van Google: {e}")
    return RedirectResponse(url="/select-accounts")

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@app.get("/select-accounts", response_class=HTMLResponse)
async def select_accounts_page_endpoint(request: Request):
    credentials = get_google_credentials_from_session(request)
    if not credentials: return RedirectResponse(url="/", status_code=302)
    try:
        admin_client = AnalyticsAdminServiceClient(credentials=credentials)
        summaries = admin_client.list_account_summaries(request=ListAccountSummariesRequest(page_size=200))
        ga_properties = []
        for acc_sum in summaries:
            for prop_sum in getattr(acc_sum, 'property_summaries', []):
                 if "properties/" in prop_sum.property:
                    ga_properties.append({"id": prop_sum.property, "name": f"{prop_sum.display_name or 'N/A'} (Account: {acc_sum.display_name or 'N/A'})"})
        user_email = request.session.get("user_email", "Onbekend")
        default_start_date_val = (datetime.now() - timedelta(days=DEFAULT_START_DAYS_AGO)).strftime("%Y-%m-%d")
        default_end_date_val = (datetime.now() - timedelta(days=DEFAULT_END_DAYS_AGO)).strftime("%Y-%m-%d")
        return HTMLResponse(content=html_select_accounts_page(
            sorted(ga_properties, key=lambda p: p['name'].lower()), user_email, 
            AVAILABLE_METRICS, DEFAULT_METRICS, AVAILABLE_DIMENSIONS, DEFAULT_DIMENSIONS,
            default_start_date_val, default_end_date_val))
    except Exception as e:
        print(f"Error fetching account summaries: {e}")
        if any(k in str(e).upper() for k in ["INVALID_GRANT","TOKEN HAS BEEN EXPIRED","UNAUTHENTICATED","PERMISSION_DENIED"]):
            request.session.clear()
            return RedirectResponse(url="/?error=auth_failed", status_code=302)
        raise HTTPException(status_code=500, detail=f"Fout bij ophalen GA properties: {e}")

async def generate_benchmark_data_from_google(
    google_credentials: Credentials, 
    selected_property_ids: List[str],
    selected_metric_api_names: List[str],
    selected_dimension_api_names: List[str],
    start_date_str: str, 
    end_date_str: str    
) -> Dict[str, Any]:
    data_client = BetaAnalyticsDataClient(credentials=google_credentials)
    final_metrics = [Metric(name=m) for m in selected_metric_api_names]
    final_dimensions = [Dimension(name=d) for d in selected_dimension_api_names]

    if not final_metrics: raise ValueError("Geen metrics geselecteerd.")
    if not final_dimensions: final_dimensions.append(Dimension(name="date")) 

    overall_aggregated_metrics = {name: 0.0 for name in selected_metric_api_names}
    properties_data_summary = [] # Bevat gedetailleerde rijen per property
    properties_with_errors = {}
    successful_property_count = 0

    # Voor het berekenen van gemiddelden per dimensiecombinatie
    # Key: tuple van dimensiewaarden (bv. ('2023-10-26', 'Organic Search'))
    # Value: dict met {metric_name: sum_value, '_property_count': count}
    dimension_combo_sums = defaultdict(lambda: {
        **{metric_name: 0.0 for metric_name in selected_metric_api_names}, 
        '_properties_contributed': set() # Houdt bij welke properties hebben bijgedragen
    })


    for prop_id in selected_property_ids:
        if not prop_id.startswith("properties/"):
            properties_with_errors[prop_id] = "Ongeldig formaat property ID."
            properties_data_summary.append({"id": prop_id, "error": "Ongeldig formaat", "data_rows": [], "property_total_metrics": {m:0.0 for m in selected_metric_api_names}})
            continue
        
        property_specific_data_rows = []
        property_specific_total_metrics = {name: 0.0 for name in selected_metric_api_names}
        rows_processed_for_property = 0
        property_had_data = False

        try:
            response = data_client.run_report(RunReportRequest(
                property=prop_id, dimensions=final_dimensions, metrics=final_metrics,
                date_ranges=[DateRange(start_date=start_date_str, end_date=end_date_str)],
            ))
            
            dimension_header_names = [header.name for header in response.dimension_headers]
            metric_header_names = [header.name for header in response.metric_headers]

            for api_row in response.rows:
                property_had_data = True
                rows_processed_for_property += 1
                
                current_row_dimensions_dict = {}
                dim_key_parts = []
                for i, dim_value_obj in enumerate(api_row.dimension_values):
                    dim_name = dimension_header_names[i]
                    dim_value = dim_value_obj.value
                    current_row_dimensions_dict[dim_name] = dim_value
                    if dim_name in selected_dimension_api_names: # Zorg voor juiste volgorde voor tuple key
                        dim_key_parts.append(dim_value)
                
                # Maak een tuple van de *geselecteerde* dimensiewaarden voor de defaultdict key
                # Dit zorgt ervoor dat de volgorde consistent is met selected_dimension_api_names
                dim_key_tuple = tuple(current_row_dimensions_dict.get(d_name, "(not set)") for d_name in selected_dimension_api_names)


                current_row_metrics_dict = {}
                for i, metric_value_obj in enumerate(api_row.metric_values):
                    metric_name = metric_header_names[i]
                    try:
                        val = float(metric_value_obj.value)
                        current_row_metrics_dict[metric_name] = val
                        property_specific_total_metrics[metric_name] += val
                        overall_aggregated_metrics[metric_name] += val
                        
                        # Update sums voor de specifieke dimensie combinatie
                        dimension_combo_sums[dim_key_tuple][metric_name] += val
                        dimension_combo_sums[dim_key_tuple]['_properties_contributed'].add(prop_id)

                    except ValueError:
                        current_row_metrics_dict[metric_name] = 0.0
                
                property_specific_data_rows.append({
                    "dimensions": current_row_dimensions_dict,
                    "metrics": current_row_metrics_dict
                })
            
            if property_had_data: # Tel alleen mee als er data was, niet per se rijen met waarden > 0
                successful_property_count += 1
            
            properties_data_summary.append({
                "id": prop_id, "data_rows": property_specific_data_rows,
                "property_total_metrics": property_specific_total_metrics,
                "rows_processed": rows_processed_for_property
            })

        except Exception as e:
            print(f"ERROR: Fout bij ophalen/verwerken rapport voor {prop_id}: {e}")
            properties_with_errors[prop_id] = str(e)
            properties_data_summary.append({"id": prop_id, "error": str(e), "data_rows": [], "property_total_metrics": {m:0.0 for m in selected_metric_api_names}})
            continue
    
    if successful_property_count == 0 and selected_property_ids:
        error_msg = f"Geen data succesvol opgehaald. Fouten: {properties_with_errors}"
        raise ValueError(error_msg)

    # Bereken de gemiddelden per dimensiecombinatie
    average_metrics_per_dimension_combination = []
    for dim_key_tuple, sums_and_meta in dimension_combo_sums.items():
        dim_values_dict = {selected_dimension_api_names[i]: dim_key_tuple[i] for i in range(len(dim_key_tuple))}
        
        # Gebruik het aantal *geselecteerde succesvolle properties* voor het gemiddelde,
        # zodat als een property een dimensiecombinatie niet had, de bijdrage 0 is.
        num_props_for_avg = successful_property_count 
        # OF: gebruik len(sums_and_meta['_properties_contributed']) als je het gemiddelde wilt van alleen de properties die de combinatie hadden.
        # De user's voorbeeld (paid:3.5, organic:5.5) suggereert delen door totaal aantal properties in de benchmark (hier `successful_property_count`).

        avg_metrics = {}
        if num_props_for_avg > 0:
            for metric_name in selected_metric_api_names:
                avg_metrics[metric_name] = round(sums_and_meta[metric_name] / num_props_for_avg, 2)
        else: # Voorkom ZeroDivisionError, hoewel num_props_for_avg hier > 0 zou moeten zijn als dimension_combo_sums items heeft.
            for metric_name in selected_metric_api_names:
                avg_metrics[metric_name] = 0.0

        average_metrics_per_dimension_combination.append({
            "dimensions": dim_values_dict,
            "average_metrics": avg_metrics
        })
        
    avg_overall_metrics_prop = {
        m: round(overall_aggregated_metrics[m] / successful_property_count, 2) if successful_property_count > 0 else 0.0 
        for m in selected_metric_api_names
    }
    
    derived_metrics = {}
    sessions_total = overall_aggregated_metrics.get("sessions", 0.0)
    if "engagedSessions" in overall_aggregated_metrics and sessions_total > 0:
        derived_metrics["overall_engagement_rate"] = round((overall_aggregated_metrics["engagedSessions"] / sessions_total) * 100, 2)
    if "screenPageViews" in overall_aggregated_metrics and sessions_total > 0:
        derived_metrics["overall_views_per_session"] = round(overall_aggregated_metrics["screenPageViews"] / sessions_total, 2)

    return {
        "requested_properties_count": len(selected_property_ids),
        "successful_properties_count": successful_property_count,
        "period": {"start_date": start_date_str, "end_date": end_date_str},
        "selected_metrics_api_names": selected_metric_api_names,
        "selected_dimensions_api_names": selected_dimension_api_names,
        "total_metrics_across_selection": overall_aggregated_metrics, # Totale som over alle properties en dimensies
        "average_overall_metrics_per_property": avg_overall_metrics_prop, # Gemiddelde van de totalen per property
        "average_metrics_per_dimension_combination": average_metrics_per_dimension_combination, # Nieuw!
        "data_summary_per_property": properties_data_summary, 
        "errors_per_property": properties_with_errors
    }

@app.post("/generate-benchmark", response_class=HTMLResponse)
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
    if not credentials: return RedirectResponse(url="/?error=not_logged_in", status_code=302)
    
    if not property_ids: return HTMLResponse("<h1>Fout</h1><p>Selecteer ten minste één GA4 property.</p><a href='/select-accounts'>Terug</a>", status_code=400)
    if not selected_metrics: return HTMLResponse("<h1>Fout</h1><p>Selecteer ten minste één metric.</p><a href='/select-accounts'>Terug</a>", status_code=400)
    if not selected_dimensions: return HTMLResponse("<h1>Fout</h1><p>Selecteer ten minste één dimensie (bijv. datum).</p><a href='/select-accounts'>Terug</a>", status_code=400)
    
    try:
        datetime.strptime(start_date, "%Y-%m-%d"); datetime.strptime(end_date, "%Y-%m-%d")
        if start_date > end_date: raise ValueError("Startdatum mag niet na de einddatum liggen.")
    except ValueError as ve: return HTMLResponse(f"<h1>Fout</h1><p>Ongeldige datums: {ve}</p><a href='/select-accounts'>Terug</a>", status_code=400)

    try:
        benchmark_results = await generate_benchmark_data_from_google(
            credentials, property_ids, selected_metrics, selected_dimensions, start_date, end_date
        )
    except ValueError as e: return HTMLResponse(f"<h1>Fout bij genereren benchmark</h1><p>{e}</p><a href='/select-accounts'>Probeer opnieuw</a>", status_code=500)
    except Exception as e:
        print(f"Onverwachte fout bij genereren benchmark data: {e}")
        return HTMLResponse(f"<h1>Onverwachte fout</h1><p>Details: {e}</p><a href='/select-accounts'>Probeer opnieuw</a>", status_code=500)

    user_email = request.session.get("user_email")
    db_report = BenchmarkReportDB(
        property_ids_used=",".join(property_ids),
        metrics_used=json.dumps(selected_metrics),
        dimensions_used=json.dumps(selected_dimensions),
        benchmark_data_json=json.dumps(benchmark_results), 
        generated_by_email=user_email
    )
    db.add(db_report); db.commit(); db.refresh(db_report)
    report_url = request.url_for("get_saved_report", report_uuid=db_report.report_uuid)
    return HTMLResponse(content=html_report_generated_page(str(report_url)))

@app.get("/report/{report_uuid}", response_class=JSONResponse)
async def get_saved_report(report_uuid: str, db: Session = Depends(get_db)):
    db_report = db.query(BenchmarkReportDB).filter(BenchmarkReportDB.report_uuid == report_uuid).first()
    if not db_report: raise HTTPException(status_code=404, detail="Benchmark rapport niet gevonden.")
    
    report_data_from_db = json.loads(db_report.benchmark_data_json)
    
    response_data = {
        "report_uuid": db_report.report_uuid,
        "created_at": db_report.created_at.isoformat(),
        "property_ids_used_in_generation": db_report.property_ids_used.split(','),
        "metrics_used_in_generation_api_names": json.loads(db_report.metrics_used),
        "dimensions_used_in_generation_api_names": json.loads(db_report.dimensions_used),
        "generated_by_email": db_report.generated_by_email,
        "benchmark_data": report_data_from_db 
    }
    return response_data

if __name__ == "__main__":
    if GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID" or GOOGLE_CLIENT_SECRET == "YOUR_GOOGLE_CLIENT_SECRET":
        print("WAARSCHUWING: Google Client ID/Secret niet correct ingesteld.")
    db_file_path = DATABASE_URL.replace("sqlite:///", "")
    if db_file_path != ":memory:" and not os.path.exists(db_file_path):
         print(f"INFO: Database {DATABASE_URL} niet gevonden, wordt aangemaakt.")
    print(f"Database URL: {DATABASE_URL}")
    print(f"Redirect URI: {REDIRECT_URI}")
    uvicorn.run(app, host="0.0.0.0", port=8000)


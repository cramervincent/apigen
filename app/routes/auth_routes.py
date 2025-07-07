
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..dependencies import get_db

from ..auth import get_google_credentials_from_session, get_google_flow, store_credentials_in_session
from ..config import settings
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse, name="home_route")
async def home(request: Request, db: Session = Depends(get_db)):
    credentials = get_google_credentials_from_session(request)
    if credentials and request.session.get("user_email"):
        return RedirectResponse(url=str(request.url_for("my_benchmarks_page")), status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/login", name="login_google_route")
async def login_google(request: Request):
    if settings.GOOGLE_CLIENT_ID == "YOUR_GOOGLE_CLIENT_ID" or settings.GOOGLE_CLIENT_SECRET == "YOUR_GOOGLE_CLIENT_SECRET":
        return HTMLResponse("<h1>Configuratie Fout</h1><p>Google Client ID/Secret niet ingesteld.</p>", status_code=500)
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
            id_info = google_id_token.verify_oauth2_token(flow.credentials.id_token, google_auth_requests.Request(), settings.GOOGLE_CLIENT_ID)
            request.session["user_email"] = id_info.get("email")
    except Exception as e:
        print(f"Error fetching token: {e}")
        raise HTTPException(status_code=500, detail=f"Kon token niet ophalen: {e}")
    return RedirectResponse(url=str(request.url_for("my_benchmarks_page")))

@router.get("/logout", name="logout_route")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=str(request.url_for("home_route")))

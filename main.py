import os
import uuid
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from passlib.context import CryptContext

# Database
from database import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@app.get("/")
def read_root():
    return {"message": "Waves backend running (Windows 11 UI with Fluxxys)"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# ------------------ Proxy + Search ------------------

def build_proxy_config() -> Optional[Dict[str, str]]:
    host = os.getenv("PROXY_HOST") or os.getenv("WAVES_PROXY_HOST") or "93.127.130.22"
    port = os.getenv("PROXY_PORT") or os.getenv("WAVES_PROXY_PORT") or "8080"
    scheme = (os.getenv("PROXY_SCHEME") or "http").lower()
    username = os.getenv("PROXY_USERNAME") or os.getenv("WAVES_PROXY_USER")
    password = os.getenv("PROXY_PASSWORD") or os.getenv("WAVES_PROXY_PASS")

    if not host or not port:
        return None

    auth = f"{username}:{password}@" if username and password else ""
    proxy_url = f"{scheme}://{auth}{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def perform_duckduckgo_search(query: str, max_results: int = 10, use_proxy: bool = True) -> List[Dict[str, str]]:
    url = "https://duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    proxies = build_proxy_config() if use_proxy else None

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15, proxies=proxies)
        resp.raise_for_status()
    except Exception:
        if use_proxy:
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            except Exception as e2:
                raise HTTPException(status_code=502, detail=f"Search request failed: {str(e2)}")
        else:
            raise HTTPException(status_code=502, detail="Search request failed")

    soup = BeautifulSoup(resp.text, "html.parser")
    results: List[Dict[str, str]] = []
    for res in soup.select(".result__body"):
        a = res.select_one("a.result__a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        href = a.get("href")
        snippet_el = res.select_one(".result__snippet")
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append({
            "title": title,
            "url": href,
            "snippet": snippet
        })
        if len(results) >= max_results:
            break
    return results


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, description="Search query"), limit: int = 10):
    items = perform_duckduckgo_search(q, max_results=min(20, max(1, limit)), use_proxy=True)
    return {
        "engine": "Waves",
        "proxy": build_proxy_config(),
        "query": q,
        "count": len(items),
        "results": items
    }


# ------------------ Auth & Users ------------------

class AuthPayload(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def generate_token() -> str:
    return uuid.uuid4().hex


@app.post("/api/auth/register")
def register(payload: AuthPayload):
    if not db:
        raise HTTPException(status_code=500, detail="Database not configured")
    users = db["user"]
    if users.find_one({"username": payload.username}):
        raise HTTPException(status_code=400, detail="Username already exists")
    doc = {
        "username": payload.username,
        "password_hash": hash_password(payload.password),
        "display_name": payload.display_name or payload.username,
        "wallpaper": None,
        "settings": {},
        "tokens": [],
        "is_active": True,
    }
    users.insert_one(doc)
    return {"ok": True}


@app.post("/api/auth/login")
def login(payload: AuthPayload):
    if not db:
        raise HTTPException(status_code=500, detail="Database not configured")
    users = db["user"]
    user = users.find_one({"username": payload.username})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = generate_token()
    users.update_one({"_id": user["_id"]}, {"$push": {"tokens": token}})
    return {"token": token}


def get_user_from_token(authorization: Optional[str] = Header(None)):
    if not db:
        raise HTTPException(status_code=500, detail="Database not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    token = token.strip() if scheme.lower() == "bearer" else authorization.strip()
    user = db["user"].find_one({"tokens": token})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user, token


@app.get("/api/me")
def me(user_token = Depends(get_user_from_token)):
    user, _ = user_token
    return {
        "username": user.get("username"),
        "display_name": user.get("display_name"),
        "wallpaper": user.get("wallpaper"),
        "settings": user.get("settings", {}),
    }


class WallpaperPayload(BaseModel):
    wallpaper: Optional[str] = None


@app.post("/api/settings/wallpaper")
def set_wallpaper(payload: WallpaperPayload, user_token = Depends(get_user_from_token)):
    user, _ = user_token
    db["user"].update_one({"_id": user["_id"]}, {"$set": {"wallpaper": payload.wallpaper}})
    return {"ok": True}


class SettingsPayload(BaseModel):
    settings: Dict[str, Optional[str]]


@app.post("/api/settings")
def update_settings(payload: SettingsPayload, user_token = Depends(get_user_from_token)):
    user, _ = user_token
    db["user"].update_one({"_id": user["_id"]}, {"$set": {"settings": payload.settings}})
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(user_token = Depends(get_user_from_token)):
    user, token = user_token
    db["user"].update_one({"_id": user["_id"]}, {"$pull": {"tokens": token}})
    return {"ok": True}


# ------------------ Fluxxys AI (Demo) ------------------

class AskPayload(BaseModel):
    prompt: str


@app.post("/api/ai/ask")
def ai_ask(payload: AskPayload, user_token = Depends(get_user_from_token)):
    # Simple demo: use DuckDuckGo to fetch one result snippet as an "answer"
    q = payload.prompt.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty prompt")
    results = perform_duckduckgo_search(q, max_results=1, use_proxy=True)
    if not results:
        return {"answer": "I couldn't find anything relevant right now."}
    top = results[0]
    answer = top.get("snippet") or top.get("title") or "I found a reference."
    return {
        "answer": answer,
        "source": top.get("url"),
        "title": top.get("title"),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

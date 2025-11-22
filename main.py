import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict
import requests
from bs4 import BeautifulSoup

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Waves proxy search backend running"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db
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
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


def build_proxy_config() -> Optional[Dict[str, str]]:
    """Build requests proxies dict from environment variables.
    Defaults to IP provided by user if available.
    Env vars:
      PROXY_HOST, PROXY_PORT, PROXY_USERNAME, PROXY_PASSWORD, PROXY_SCHEME (http/https)
    """
    host = os.getenv("PROXY_HOST") or os.getenv("WAVES_PROXY_HOST") or "93.127.130.22"
    port = os.getenv("PROXY_PORT") or os.getenv("WAVES_PROXY_PORT") or "8080"
    scheme = (os.getenv("PROXY_SCHEME") or "http").lower()
    username = os.getenv("PROXY_USERNAME") or os.getenv("WAVES_PROXY_USER")
    password = os.getenv("PROXY_PASSWORD") or os.getenv("WAVES_PROXY_PASS")

    if not host or not port:
        return None

    if username and password:
        auth = f"{username}:{password}@"
    else:
        auth = ""

    proxy_url = f"{scheme}://{auth}{host}:{port}"
    return {"http": proxy_url, "https": proxy_url}


def perform_duckduckgo_search(query: str, max_results: int = 10, use_proxy: bool = True) -> List[Dict[str, str]]:
    """Fetch and parse DuckDuckGo HTML results (non-JS) to get simple SERP.
    This is a lightweight, unofficial approach intended for demo purposes.
    """
    url = "https://duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    proxies = build_proxy_config() if use_proxy else None

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15, proxies=proxies)
        resp.raise_for_status()
    except Exception as e:
        # Fallback: retry without proxy if proxy failed
        if use_proxy:
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
            except Exception as e2:
                raise HTTPException(status_code=502, detail=f"Search request failed: {str(e2)}")
        else:
            raise HTTPException(status_code=502, detail=f"Search request failed: {str(e)}")

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

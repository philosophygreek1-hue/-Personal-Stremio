from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from urllib.parse import unquote, quote
from Backend.config import Telegram
from Backend import db, __version__
from datetime import datetime, timezone, timedelta
from fastapi.responses import HTMLResponse
from Backend.fastapi.security.tokens import verify_token


# --- Configuration ---
BASE_URL = Telegram.BASE_URL
ADDON_NAME = "MyFiles"
ADDON_VERSION = __version__
PAGE_SIZE = 15

router = APIRouter(prefix="/stremio", tags=["Stremio Addon"])


# --- Helper: convert personal DB item to Stremio meta ---
def convert_to_stremio_meta(item: dict) -> dict:
    personal_id = item.get("imdb_id") or item.get("personal_id", "")
    folder = item.get("folder", "General")
    return {
        "id": personal_id,
        "type": "other",
        "name": item.get("title", "Untitled"),
        "poster": item.get("poster") or "",
        "background": item.get("backdrop") or "",
        "description": item.get("description") or f"📁 {folder}",
        "genres": [folder],
        "releaseInfo": str(item.get("release_year", "")),
        "imdbRating": "",
    }


# --- Manifest ---
@router.get("/{token}/manifest.json")
async def get_manifest(token: str, token_data: dict = Depends(verify_token)):
    # Build folder list dynamically from DB
    try:
        folders = await db.get_all_folders()
    except Exception:
        folders = ["General"]

    if not folders:
        folders = ["General"]

    if Telegram.HIDE_CATALOG:
        resources = ["stream"]
        catalogs = []
    else:
        resources = ["catalog", "meta", "stream"]
        # One catalog per folder + one "All Files" catalog
        catalogs = [
            {
                "type": "other",
                "id": "all_files",
                "name": "All Files",
                "extra": [
                    {"name": "skip"},
                    {"name": "search", "isRequired": False}
                ],
                "extraSupported": ["skip", "search"]
            }
        ]
        for folder in folders:
            catalogs.append({
                "type": "other",
                "id": f"folder_{folder}",
                "name": f"📁 {folder}",
                "extra": [{"name": "skip"}],
                "extraSupported": ["skip"]
            })

    addon_name = ADDON_NAME
    addon_desc = "Stream your personal Telegram files."
    addon_version = ADDON_VERSION

    if Telegram.SUBSCRIPTION:
        user_id = token_data.get("user_id")
        if user_id:
            from Backend import db as _db
            try:
                user = await _db.get_user(int(user_id))
                if user and user.get("subscription_status") == "active":
                    expiry_obj = user.get("subscription_expiry")
                    if expiry_obj:
                        expiry_str = expiry_obj.strftime("%d %b %Y").lstrip("0")
                        addon_name = f"{ADDON_NAME} — Expires {expiry_str}"
                        epoch_tag = format(int(expiry_obj.timestamp()) & 0xFFFF, "x")
                        addon_version = f"{ADDON_VERSION}-{epoch_tag}"
                    else:
                        addon_name = f"{ADDON_NAME} — Active"
            except Exception:
                pass

    configure_url = f"{Telegram.BASE_URL}/stremio/{token}/configure"

    return {
        "id": f"personal.files.{token[:8]}",
        "version": addon_version,
        "name": addon_name,
        "logo": "https://i.postimg.cc/XqWnmDXr/Picsart-25-10-09-08-09-45-867.png",
        "description": addon_desc,
        "types": ["other"],
        "resources": resources,
        "catalogs": catalogs,
        "idPrefixes": ["ps"],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False
        },
        "config": [
            {
                "key": "manifest_url",
                "title": "Your Addon URL (copy to reinstall)",
                "type": "text",
                "default": f"{Telegram.BASE_URL}/stremio/{token}/manifest.json"
            }
        ]
    }


# --- Configure page ---
@router.get("/{token}/configure")
async def configure_addon(token: str):
    manifest_url = f"{Telegram.BASE_URL}/stremio/{token}/manifest.json"
    stremio_install_url = f"stremio://addon_install?manifest={quote(manifest_url, safe='')}"
    web_install_url = f"https://web.stremio.com/#/?addon_manifest={quote(manifest_url, safe='')}"

    html = f"""<!DOCTYPE html>
<html>
<head><title>{ADDON_NAME} — Configure</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: sans-serif; background: #1a1a2e; color: #eee; display: flex;
          flex-direction: column; align-items: center; justify-content: center;
          min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }}
  h1 {{ color: #7b68ee; }}
  .url-box {{ background: #16213e; border: 1px solid #7b68ee; border-radius: 8px;
               padding: 12px 16px; word-break: break-all; font-size: 0.85rem;
               margin: 16px 0; max-width: 600px; width: 100%; }}
  a.btn {{ display: inline-block; margin: 8px; padding: 12px 24px;
           background: #7b68ee; color: #fff; border-radius: 8px;
           text-decoration: none; font-weight: bold; }}
  a.btn.sec {{ background: #333; }}
</style>
</head>
<body>
  <h1>📁 {ADDON_NAME}</h1>
  <p>Your personal Telegram files addon</p>
  <div class="url-box" id="murl">{manifest_url}</div>
  <button onclick="navigator.clipboard.writeText('{manifest_url}').then(()=>alert('Copied!'))"
          style="cursor:pointer;padding:10px 20px;background:#7b68ee;color:#fff;
                 border:none;border-radius:8px;font-size:1rem;margin-bottom:16px;">
    📋 Copy Manifest URL
  </button>
  <br>
  <a class="btn" href="{stremio_install_url}">📦 Install in Stremio App</a>
  <a class="btn sec" href="{web_install_url}" target="_blank">🌐 Install via Web</a>
</body>
</html>"""
    return HTMLResponse(html)


# --- Catalog ---
@router.get("/{token}/catalog/other/{id}/{extra:path}.json")
@router.get("/{token}/catalog/other/{id}.json")
async def get_catalog(
    token: str,
    id: str,
    extra: Optional[str] = None,
    token_data: dict = Depends(verify_token)
):
    if Telegram.HIDE_CATALOG:
        raise HTTPException(status_code=404, detail="Catalog disabled")

    search_query = None
    stremio_skip = 0

    if extra:
        params = extra.replace("&", "/").split("/")
        for param in params:
            if param.startswith("search="):
                search_query = unquote(param.removeprefix("search="))
            elif param.startswith("skip="):
                try:
                    stremio_skip = int(param.removeprefix("skip="))
                except ValueError:
                    stremio_skip = 0

    page = (stremio_skip // PAGE_SIZE) + 1

    try:
        if search_query:
            results = await db.search_personal_files(query=search_query, page=page, page_size=PAGE_SIZE)
            items = results.get("results", [])
        elif id == "all_files":
            data = await db.sort_personal_files(sort=[("updated_on", "desc")], page=page, page_size=PAGE_SIZE)
            items = data.get("files", [])
        elif id.startswith("folder_"):
            folder_name = id[len("folder_"):]
            data = await db.sort_personal_files(
                sort=[("updated_on", "desc")],
                page=page,
                page_size=PAGE_SIZE,
                folder_filter=folder_name
            )
            items = data.get("files", [])
        else:
            items = []
    except Exception as e:
        return {"metas": []}

    metas = [convert_to_stremio_meta(item) for item in items]
    return {"metas": metas}


# --- Meta ---
@router.get("/{token}/meta/other/{id}.json")
async def get_meta(token: str, id: str, token_data: dict = Depends(verify_token)):
    if Telegram.HIDE_CATALOG:
        raise HTTPException(status_code=404, detail="Catalog disabled")

    media = await db.get_personal_file(personal_id=id)
    if not media:
        return {"meta": {}}

    folder = media.get("folder", "General")
    streams = []
    for q in (media.get("telegram") or []):
        streams.append({
            "id": q.get("id", ""),
            "name": q.get("name", media.get("title", "")),
            "size": q.get("size", ""),
        })

    return {
        "meta": {
            "id": id,
            "type": "other",
            "name": media.get("title", "Untitled"),
            "description": media.get("description") or f"📁 {folder}",
            "genres": [folder],
            "poster": media.get("poster", ""),
            "background": media.get("backdrop", ""),
            "releaseInfo": str(media.get("release_year", "")),
            "videos": streams,
        }
    }


# --- Stream ---
@router.get("/{token}/stream/other/{id}.json")
async def get_stream(token: str, id: str, token_data: dict = Depends(verify_token)):
    media = await db.get_personal_file(personal_id=id)
    if not media:
        return {"streams": []}

    streams = []
    for q in (media.get("telegram") or []):
        stream_id = q.get("id", "")
        if not stream_id:
            continue
        url = f"{Telegram.BASE_URL}/stream/{token}/{stream_id}"
        streams.append({
            "url": url,
            "name": f"📁 {media.get('folder', 'General')}",
            "title": f"📄 {media.get('title', 'File')}\n💾 {q.get('size', '')}",
            "behaviorHints": {"notWebReady": False}
        })

    return {"streams": streams}


# --- Install page (root) ---
@router.get("/install")
async def install_page():
    return HTMLResponse(f"""<html><body style="background:#1a1a2e;color:#eee;
        font-family:sans-serif;text-align:center;padding:40px">
        <h1>📁 {ADDON_NAME}</h1>
        <p>Login first to get your personal manifest URL.</p>
        <a href="{Telegram.BASE_URL}/login" style="color:#7b68ee">Go to Login</a>
        </body></html>""")

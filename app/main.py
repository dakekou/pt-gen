# -*- coding: utf-8 -*-
"""pt-gen：FastAPI 服务（网页 + API，均需密码）
- 网页：GET / 登录页；POST /login；GET /app 查询页
- API：GET/POST /api/gen，鉴权方式：Cookie 会话 / X-API-Key / Authorization: Bearer / ?key=
"""
import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from . import service
from .cache import FileCache

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CACHE_DIR = Path(os.environ.get("PTGEN_CACHE_DIR", BASE_DIR / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

PASSWORD = os.environ.get("PTGEN_PASSWORD", "ptgen2024")
SECRET = os.environ.get("PTGEN_SECRET", "ptgen-secret-change-me")
COOKIE_NAME = "ptgen_session"
SESSION_TTL = 7 * 86400

_signer = TimestampSigner(SECRET)
result_cache = FileCache(str(CACHE_DIR / "results.json"), ttl=86400)

app = FastAPI(title="pt-gen", docs_url=None, redoc_url=None)


def _check_password(pwd):
    return bool(pwd) and hmac.compare_digest(str(pwd), PASSWORD)


def _make_token():
    return _signer.sign(b"ptgen-ok").decode()


def _verify_token(token):
    if not token:
        return False
    try:
        _signer.unsign(token, max_age=SESSION_TTL)
        return True
    except (BadSignature, SignatureExpired):
        return False


def _is_authed(request: Request):
    c = request.cookies.get(COOKIE_NAME)
    if c and _verify_token(c):
        return True
    return False


def _api_authed(request: Request):
    """API 鉴权：Cookie / X-API-Key / Authorization Bearer / ?key= 任一通过即可"""
    if _is_authed(request):
        return True
    key = request.headers.get("X-API-Key") or ""
    if key and _check_password(key):
        return True
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        if _check_password(auth[7:].strip()):
            return True
    qkey = request.query_params.get("key") or ""
    if qkey and _check_password(qkey):
        return True
    return False


def _unauthorized():
    return JSONResponse({"success": False, "error": "未授权：请先输入密码（API 请携带 X-API-Key / Bearer / ?key=）"},
                        status_code=401)


# ---------------------------------------------------------------- 页面
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if _is_authed(request):
        return RedirectResponse("/app", status_code=302)
    return (STATIC_DIR / "login.html").read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse)
def app_page(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/")
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/login")
async def login(request: Request):
    try:
        body = dict(await request.form())
    except Exception:
        body = {}
    pwd = body.get("password", "")
    if not _check_password(pwd):
        return HTMLResponse(
            '<html><body><h3>密码错误</h3><p><a href="/">返回重试</a></p></body></html>',
            status_code=401)
    resp = RedirectResponse("/app", status_code=302)
    resp.set_cookie(COOKIE_NAME, _make_token(), max_age=SESSION_TTL, httponly=True, samesite="lax")
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ---------------------------------------------------------------- API
@app.get("/api/gen")
def api_gen_get(request: Request, input: str = "", key: str = ""):
    if not _api_authed(request):
        return _unauthorized()
    return _handle(input)


@app.post("/api/gen")
async def api_gen_post(request: Request):
    if not _api_authed(request):
        return _unauthorized()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse({"success": False, "error": "请求体需为 JSON 对象"}, status_code=400)
    raw = body.get("input") or ""
    return _handle(raw)


def _handle(raw_input):
    if not raw_input or not raw_input.strip():
        return JSONResponse({"success": False, "error": "缺少 input 参数（粘贴豆瓣/IMDb/TMDb 链接或末尾数字）"},
                            status_code=400)
    cache_key = "gen:" + raw_input.strip()
    cached = result_cache.get(cache_key)
    if cached:
        return JSONResponse(cached)
    result = service.generate(raw_input)
    if result.get("success"):
        result_cache.set(cache_key, result)
    return JSONResponse(result)

# ---------------------------------------------------------------- 兼容第三方 ptgen 格式（PTerWEB / pde5i.de 格式）
def _split_list(s):
    """把 'a / b / c' 拆成列表，空值返回空列表"""
    if not s:
        return []
    return [x.strip() for x in str(s).split('/') if x.strip()]

def _build_pde5i_result(result):
    """把我们的 result 转换成 pde5i.de / PTerWEB 兼容的完整 JSON 结构"""
    data = result.get("data", {}) or {}
    poster = result.get("poster", {}) or {}
    bbcode = result.get("bbcode", "")
    # 从 crew_lines 解析导演/编剧/演员
    director, writer, cast = [], [], []
    for role, names in data.get("crew_lines", []) or []:
        name_list = [n.strip() for n in str(names).split('\n') if n.strip()]
        if "导演" in role:
            director = [{"name": n} for n in name_list]
        elif "编剧" in role:
            writer = [{"name": n} for n in name_list]
        elif "演" in role:
            cast = [{"name": n} for n in name_list]
    douban_rating = data.get("douban_rating", "")
    douban_votes = data.get("douban_votes", 0)
    imdb_rating = data.get("imdb_rating", "")
    imdb_votes = data.get("imdb_votes", 0)
    return {
        "success": True,
        "error": None,
        "format": bbcode,
        "data": bbcode,
        "bbcode": bbcode,
        "formats": {"bbcode": bbcode},
        "site": result.get("kind", "douban"),
        "id": result.get("douban_id") or result.get("imdb_id") or "",
        "sid": result.get("douban_id") or "",
        "link": data.get("douban_url", ""),
        "chinese_title": data.get("title_zh", ""),
        "foreign_title": data.get("original_title", ""),
        "aka": _split_list(data.get("yiming", "")),
        "trans_title": _split_list(data.get("yiming", "")) or [data.get("title_zh", "")],
        "this_title": [data.get("original_title", "")] if data.get("original_title") else [],
        "year": data.get("year", ""),
        "playdate": _split_list(data.get("release_dates", "")),
        "region": _split_list(data.get("region", "")),
        "genre": _split_list(data.get("genres", "")),
        "language": _split_list(data.get("language", "")),
        "duration": data.get("durations", ""),
        "episodes": "",
        "seasons": "",
        "poster": poster.get("uploaded_url", poster.get("original_url", "")),
        "director": director,
        "writer": writer,
        "cast": cast,
        "introduction": data.get("intro", ""),
        "music": data.get("music", ""),
        "awards": "",
        "tags": [],
        "douban_link": data.get("douban_url", ""),
        "douban_rating_average": float(douban_rating) if douban_rating else 0,
        "douban_votes": douban_votes,
        "douban_rating": f"{douban_rating}/10 from {douban_votes} users" if douban_rating else "",
        "imdb_link": data.get("imdb_url", ""),
        "imdb_id": result.get("imdb_id", ""),
        "imdb_rating_average": float(imdb_rating) if imdb_rating else 0,
        "imdb_votes": imdb_votes,
        "tmdb_link": data.get("tmdb_url", ""),
        "tmdb_id": result.get("tmdb_id", ""),
        "ratings": {
            "douban": {
                "average": float(douban_rating) if douban_rating else 0,
                "votes": douban_votes,
                "formatted": f"{douban_rating}/10 from {douban_votes} users" if douban_rating else "",
                "link": data.get("douban_url", ""),
            },
            "imdb": {
                "average": float(imdb_rating) if imdb_rating else 0,
                "votes": imdb_votes,
                "formatted": f"{imdb_rating}/10 from {imdb_votes} users" if imdb_rating else "",
                "link": data.get("imdb_url", ""),
            },
        },
        "copyright": "Powered by pt-gen",
        "version": "1.0",
    }

@app.get("/api/ptgen")
def api_ptgen_compat(request: Request, url: str = "", key: str = ""):
    """兼容第三方 ptgen 接口（对齐 pde5i.de / PTerWEB 格式）：
    GET /api/ptgen?url=豆瓣链接[&key=密码]
    返回完整 JSON（含 chinese_title / foreign_title / site / imdb_link 等结构化字段 + format BBcode），
    PTerWEB 直接取 chinese_title 等字段，无需从 BBcode 正则提取。
    鉴权：URL 带 key 则校验，不带则放行（仅限可信反代环境使用）。
    """
    if key and not _check_password(key):
        return JSONResponse({"success": False, "error": "未授权：key 不正确", "format": ""}, status_code=401)
    if not url or not url.strip():
        return JSONResponse({"success": False, "error": "缺少 url 参数", "format": ""}, status_code=400)
    cache_key = "ptgen:" + url.strip()
    cached = result_cache.get(cache_key)
    if cached and cached.get("success"):
        return JSONResponse(_build_pde5i_result(cached))
    result = service.generate(url)
    if not result.get("success"):
        err = result.get("error", "未知错误")
        return JSONResponse({"success": False, "error": err, "format": ""}, status_code=502)
    result_cache.set(cache_key, result)
    return JSONResponse(_build_pde5i_result(result))

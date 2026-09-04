# -*- coding: utf-8 -*-
"""海报：下载豆瓣海报 -> 上传 pixhost -> 直链优先 pixhost.cc，失败自动切 pixhost.to，双失败报错"""
import os
import re
import threading

import requests

from . import fetchers

CACHE_DIR = os.environ.get("PTGEN_CACHE_DIR", os.path.join(os.path.dirname(__file__), "cache"))
PIXHOST_API = "https://api.pixhost.to/images"

_lock = threading.Lock()
_poster_cache = {}


def _load_cache():
    try:
        with open(os.path.join(CACHE_DIR, "poster_cache.json"), encoding="utf-8") as f:
            import json
            _poster_cache.update(json.load(f))
    except Exception:
        pass


def _save_cache():
    try:
        import json
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = os.path.join(CACHE_DIR, "poster_cache.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_poster_cache, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(CACHE_DIR, "poster_cache.json"))
    except Exception:
        pass


def _full_url_from_th(th_url):
    """th_url: https://t3.pixhost.to/thumbs/5445/xxx.jpg -> 直链 https://img3.pixhost.to/images/5445/xxx.jpg"""
    m = re.match(r"https?://t(\d+)\.pixhost\.(to|cc)/thumbs/(.+)", th_url or "")
    if not m:
        return ""
    server, dom, path = m.group(1), m.group(2), m.group(3)
    path = re.sub(r"_th\.(jpe?g|png|gif|webp)$", r".\1", path)
    return f"https://img{server}.pixhost.{dom}/images/{path}"


def _reachable(url, timeout=12):
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return True
        r = requests.get(url, timeout=timeout, stream=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200
    except Exception:
        return False


def upload_poster(image_bytes, filename="poster.jpg"):
    """上传图片到 pixhost。返回 {uploaded_url, host} 或抛异常"""
    resp = requests.post(
        PIXHOST_API,
        files={"img": (filename, image_bytes, "image/jpeg")},
        data={"content_type": "0", "maxth": "1000"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"pixhost 上传失败 HTTP {resp.status_code}")
    try:
        d = resp.json()
    except Exception:
        raise RuntimeError("pixhost 返回无法解析")
    if not d.get("show_url"):
        raise RuntimeError("pixhost 未返回图片地址")
    direct = _full_url_from_th(d.get("th_url", ""))
    if not direct:
        raise RuntimeError("pixhost 直链解析失败")
    # 优先 pixhost.cc，失败切 pixhost.to
    cc = direct.replace(".pixhost.to", ".pixhost.cc")
    if _reachable(cc):
        return {"uploaded_url": cc, "host": "pixhost.cc"}
    if _reachable(direct):
        return {"uploaded_url": direct, "host": "pixhost.to"}
    raise RuntimeError("pixhost.cc 与 pixhost.to 均无法访问图片，请稍后重试")


def ensure_poster_uploaded(poster_url):
    """带缓存：同一张海报只上传一次。返回 {original_url, uploaded_url, host, status}"""
    if not poster_url:
        return {"original_url": "", "uploaded_url": "", "host": "", "status": "error",
                "error": "未获取到海报地址"}
    with _lock:
        cached = _poster_cache.get(poster_url)
        if cached:
            return {"original_url": poster_url, "status": "ok", **cached}
        try:
            r = requests.get(poster_url, timeout=30,
                             headers={"User-Agent": fetchers.UA_PC,
                                      "Referer": "https://movie.douban.com/"})
            if r.status_code != 200:
                return {"original_url": poster_url, "uploaded_url": "", "host": "",
                        "status": "error", "error": f"海报下载失败 HTTP {r.status_code}"}
            img_bytes = r.content
            if not img_bytes:
                raise RuntimeError("海报内容为空")
            res = upload_poster(img_bytes)
        except Exception as e:
            return {"original_url": poster_url, "uploaded_url": "", "host": "",
                    "status": "error", "error": f"海报上传失败: {e}"}
        cache_item = {"uploaded_url": res["uploaded_url"], "host": res["host"]}
        _poster_cache[poster_url] = cache_item
        _save_cache()
        return {"original_url": poster_url, "status": "ok", **cache_item}


_load_cache()

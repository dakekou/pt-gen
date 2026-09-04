# -*- coding: utf-8 -*-
"""数据抓取与解析：豆瓣(rexxar/desc/桌面/演职员)、IMDb(GraphQL/OMDb)、TMDB、Wikidata、豆瓣反向搜索"""
import json
import os
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

TMDB_TOKEN = os.environ.get(
    "TMDB_TOKEN",
    "Bearer eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIyMzc1ZGIzOTYwYWVhMWI1OTA1NWMwZmM3ZDcwYjYwZiIsInN1YiI6IjYwYmNhZTk0NGE0YmY2MDA1OWJhNWE1ZSIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.DU51juQWlAIIfZ2lK99b3zi-c5vgc4jAwVz5h2WjOP8"
)
OMDB_KEY = os.environ.get("OMDB_API_KEY", "thewdb")

_session = requests.Session()


def _get(url, headers=None, timeout=12, params=None, allow_redirects=True):
    try:
        r = _session.get(url, headers=headers or {}, params=params,
                         timeout=timeout, allow_redirects=allow_redirects)
        return r
    except Exception:
        return None


def _post(url, headers=None, json_body=None, timeout=10):
    try:
        r = _session.post(url, headers=headers or {}, json=json_body, timeout=timeout)
        return r
    except Exception:
        return None


# ---------------------------------------------------------------- 豆瓣
def fetch_douban_rexxar(subject_id):
    """手机版 JSON 接口（自动跟随 movie->tv 重定向）。失败返回 None"""
    url = f"https://m.douban.com/rexxar/api/v2/movie/{subject_id}"
    r = _get(url, headers={"User-Agent": UA_MOBILE, "Referer": f"https://m.douban.com/movie/subject/{subject_id}/"})
    if not r or r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _parse_desc_table(html_text):
    """解析豆瓣 h5 desc 页的 <tr><td>键</td><td>值</td></tr> 表格"""
    out = {}
    soup = BeautifulSoup(html_text, "html.parser")
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            key = tds[0].get_text(strip=True)
            val = tds[1].get_text(" ", strip=True)
            if key and val:
                out[key] = val
    return out


def fetch_douban_desc(subject_id):
    """豆瓣 h5 简介/演职员表页（含 导演/编剧/主演/上映/类型/片长/地区/语言/IMDb）。失败返回 None"""
    for prefix in ("movie", "tv"):
        url = f"https://www.douban.com/doubanapp//h5/{prefix}/{subject_id}/desc"
        r = _get(url, headers={"User-Agent": UA_MOBILE})
        if not r or r.status_code != 200:
            continue
        rows = _parse_desc_table(r.text)
        if rows:
            return rows
    return None


def fetch_douban_desktop(subject_id):
    """桌面版详情页（住宅 IP 可用；数据中心 IP 常弹反爬）。失败返回 None"""
    url = f"https://movie.douban.com/subject/{subject_id}/"
    r = _get(url, headers={"User-Agent": UA_PC, "Referer": "https://movie.douban.com/"})
    if not r or r.status_code != 200:
        return None
    text = r.text
    if "载入中" in text or "sec.douban.com" in text or len(text) < 20000:
        return None
    return text


def parse_desktop_info(html_text):
    """解析桌面版 #info 字段与评分、简介、海报"""
    soup = BeautifulSoup(html_text, "html.parser")
    info = {}
    info_div = soup.find(id="info")
    if info_div:
        for span in info_div.find_all("span", class_="pl"):
            key = span.get_text("", strip=True).rstrip(":：").strip()
            node = span.next_sibling
            val = ""
            while node is not None and not getattr(node, "get_text", None):
                node = node.next_sibling
            if node is not None:
                val = node.get_text(" ", strip=True)
            if key and val:
                info[key] = val
    data = {"info": info}
    h1 = soup.find("h1")
    if h1:
        span = h1.find(property="v:itemreviewed")
        data["full_title"] = span.get_text(strip=True) if span else h1.get_text(" ", strip=True)
    y = soup.find("span", class_="year")
    data["year"] = y.get_text(strip=True).strip("()") if y else ""
    rating = soup.find(property="v:average")
    data["douban_rating"] = rating.get_text(strip=True) if rating else ""
    votes = soup.select_one('.rating_people [property="v:votes"]')
    data["douban_votes"] = votes.get_text(strip=True) if votes else ""
    mainpic = soup.select_one("#mainpic img")
    data["poster"] = mainpic.get("src", "") if mainpic else ""
    intro_el = soup.find(id="link-report")
    data["intro"] = ""
    if intro_el:
        t = intro_el.get_text("\n", strip=True)
        t = t.replace("投诉", "").replace("显示全部", "").strip()
        data["intro"] = t
    return data


def fetch_douban_celebrities(subject_id):
    """桌面版演职员整页（含 导演/演员/编剧/音乐/…）。反爬或失败返回 None"""
    url = f"https://movie.douban.com/subject/{subject_id}/celebrities"
    r = _get(url, headers={"User-Agent": UA_PC, "Referer": f"https://movie.douban.com/subject/{subject_id}/"})
    if not r or r.status_code != 200:
        return None
    text = r.text
    if "载入中" in text or "sec.douban.com" in text or len(text) < 20000:
        return None
    return parse_celebrities(text)


def parse_celebrities(html_text):
    """解析演职员页，返回有序 sections: [{position, people:[{name, role}]}]，主演归一为 演员"""
    soup = BeautifulSoup(html_text, "html.parser")
    wrappers = soup.select("#celebrities .list-wrapper")
    if not wrappers:
        wrappers = [h2.parent for h2 in soup.find_all("h2")]
    sections = []
    for w in wrappers:
        h2 = w.find("h2") if w.name != "h2" else w
        if not h2:
            continue
        ul = w.find("ul") if w.name != "h2" else w.find_next_sibling("ul")
        if ul is None and w.name == "h2":
            ul = w.find_next("ul")
        if not ul:
            continue
        position = re.sub(r"\s+", "", h2.get_text("", strip=True))
        position = re.sub(r"[A-Za-z]+", "", position)
        if not position:
            continue
        if position == "主演":
            position = "演员"
        if re.search(r"影人|合作|作品", position):
            continue
        people = []
        for li in ul.find_all("li", recursive=False):
            name_el = li.select_one(".name") or li.find("a")
            role_el = li.select_one(".role")
            if not name_el:
                continue
            full_name = re.sub(r"\s+", " ", name_el.get_text(strip=True))
            role = ""
            if role_el:
                role = role_el.get("title") or role_el.get_text(strip=True)
            role = role.strip()
            character = ""
            if role:
                m = re.search(r"[（(]\s*(配|饰)\s+(.+?)\s*[)）]", role)
                if m:
                    character = m.group(1) + " " + m.group(2)
                elif re.match(r"^\s*(饰|配)\s+", role):
                    character = role.strip()
            people.append({"name": full_name, "role": character})
        if people:
            sections.append({"position": position, "people": people})
    rank = {"导演": 0, "演员": 1, "编剧": 2, "音乐": 3}
    sections.sort(key=lambda s: rank.get(s["position"], 9))
    return sections


def douban_suggest(query):
    """豆瓣搜索建议接口，返回 [{id,title,year,sub_title,type,url}]"""
    r = _get("https://movie.douban.com/j/subject_suggest",
             headers={"User-Agent": UA_PC, "Referer": "https://movie.douban.com/"},
             params={"q": query}, timeout=12)
    if not r or r.status_code != 200:
        return []
    try:
        data = r.json()
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def find_douban_by_title(title, year=None):
    """通过标题+年份反查豆瓣 subject id；优先年份命中。失败返回 None"""
    candidates = douban_suggest(title)
    if not candidates and title:
        # 去掉副标题再试一次
        short = re.split(r"[:：\-—]", title)[0].strip()
        if short != title:
            candidates = douban_suggest(short)
    if not candidates:
        return None
    if year:
        for c in candidates:
            if str(c.get("year", "")).strip() == str(year).strip():
                return c
    return candidates[0]


# ---------------------------------------------------------------- IMDb
def fetch_imdb_rating(imdb_id):
    """IMDb 评分：优先官方 GraphQL，失败退 OMDb。返回 {rating, votes} 或 None"""
    if not imdb_id:
        return None
    try:
        r = _post("https://api.graphql.imdb.com/",
                  headers={"Content-Type": "application/json", "Accept": "application/json",
                           "User-Agent": UA_PC},
                  json_body={"query": 'query { title(id: "%s") { ratingsSummary { aggregateRating voteCount } } }' % imdb_id},
                  timeout=8)
        if r and r.status_code == 200:
            d = r.json()
            rs = (d.get("data") or {}).get("title") or {}
            rs = rs.get("ratingsSummary") or {}
            if rs.get("aggregateRating"):
                return {"rating": float(rs["aggregateRating"]),
                        "votes": int(rs.get("voteCount") or 0)}
    except Exception:
        pass
    try:
        r = _get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": OMDB_KEY}, timeout=12)
        if r and r.status_code == 200:
            d = r.json()
            if d.get("Response") == "True" and d.get("imdbRating") not in (None, "", "N/A"):
                votes = int(str(d.get("imdbVotes", "0") or "0").replace(",", "") or 0)
                return {"rating": float(d["imdbRating"]), "votes": votes}
    except Exception:
        pass
    return None


def fetch_omdb(imdb_id):
    """OMDb 完整资料（Title/Year/Genre/Country/Language/Released/Poster/…）"""
    r = _get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": OMDB_KEY, "plot": "full"}, timeout=12)
    if not r or r.status_code != 200:
        return None
    try:
        d = r.json()
        return d if d.get("Response") == "True" else None
    except Exception:
        return None


# ---------------------------------------------------------------- TMDB
def tmdb_get(path, params=None):
    r = _get(f"https://api.themoviedb.org/3{path}",
             headers={"Authorization": TMDB_TOKEN, "Accept": "application/json"},
             params=params or {}, timeout=10)
    if not r or r.status_code != 200:
        return None
    try:
        return r.json()
    except Exception:
        return None


def tmdb_reachable():
    """快速探测 TMDB API 是否可达（区别于‘条目不存在’）"""
    try:
        r = _session.get("https://api.themoviedb.org/3/configuration",
                         headers={"Authorization": TMDB_TOKEN, "Accept": "application/json"},
                         timeout=6)
        return r is not None and r.status_code == 200
    except Exception:
        return False


def fetch_tmdb_by_imdb(imdb_id):
    """IMDb -> TMDB id/type"""
    d = tmdb_get("/find/" + urllib.parse.quote(imdb_id), {"external_source": "imdb_id"})
    if not d:
        return None
    if d.get("movie_results"):
        m = d["movie_results"][0]
        return {"type": "movie", "id": m["id"], "title": m.get("title"),
                "original_title": m.get("original_title"), "year": _tmdb_year(m.get("release_date"))}
    if d.get("tv_results"):
        t = d["tv_results"][0]
        return {"type": "tv", "id": t["id"], "title": t.get("name"),
                "original_title": t.get("original_name"), "year": _tmdb_year(t.get("first_air_date"))}
    return None


def _tmdb_year(date_str):
    if date_str:
        m = re.match(r"(\d{4})", str(date_str))
        if m:
            return m.group(1)
    return ""


def fetch_tmdb_details(media_type, tmdb_id):
    d = tmdb_get(f"/{media_type}/{tmdb_id}",
                 {"language": "zh-CN", "append_to_response": "external_ids,credits"})
    if not d:
        return None
    is_tv = media_type == "tv"
    out = {
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "title": d.get("title") or d.get("name") or "",
        "original_title": d.get("original_title") or d.get("original_name") or "",
        "year": _tmdb_year(d.get("release_date") or d.get("first_air_date")),
        "overview": d.get("overview") or "",
        "poster": ("https://image.tmdb.org/t/p/original" + d["poster_path"]) if d.get("poster_path") else "",
        "imdb_id": (d.get("external_ids") or {}).get("imdb_id") or "",
        "rating": d.get("vote_average"),
        "votes": d.get("vote_count"),
    }
    crews = ((d.get("credits") or {}).get("crew")) or []
    music = [c["name"] for c in crews
             if c.get("job") in ("Original Music Composer", "Music", "Composer") and c.get("name")]
    out["music"] = music
    return out


# ---------------------------------------------------------------- Wikidata（兜底）
def wikidata_lookup(imdb_id):
    """IMDb -> Wikidata：TMDB id、作曲家。失败返回 None（仅兜底用，短超时）"""
    q = ('SELECT ?item ?itemLabel ?tmdb ?composerLabel WHERE { '
         '?item wdt:P345 "%s". '
         'OPTIONAL { ?item wdt:P4943 ?tmdb. } OPTIONAL { ?item wdt:P4983 ?tmdb. } '
         'OPTIONAL { ?item wdt:P86 ?composer. } '
         'SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en". } }' % imdb_id)
    r = _get("https://query.wikidata.org/sparql",
             headers={"User-Agent": "pt-gen/1.0 (docker service)", "Accept": "application/json"},
             params={"format": "json", "query": q}, timeout=8)
    if not r or r.status_code != 200:
        return None
    try:
        d = r.json()
        binds = (d.get("results") or {}).get("bindings") or []
        if not binds:
            return None
        b = binds[0]
        out = {}
        if b.get("tmdb"):
            try:
                out["tmdb_id"] = int(b["tmdb"]["value"])
            except Exception:
                pass
        if b.get("composerLabel"):
            out["composer"] = b["composerLabel"]["value"]
        return out
    except Exception:
        return None


# ---------------------------------------------------------------- 输入解析
DOUBAN_RE = re.compile(r"(?:movie|www|m)?\.?douban\.com/(?:movie/)?subject/(\d+)", re.I)
DOUBAN_RE2 = re.compile(r"douban\.com/(?:movie/)?subject/(\d+)", re.I)
IMDB_RE = re.compile(r"imdb\.com/title/(tt\d+)", re.I)
TMDB_RE = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)", re.I)


def parse_input(raw):
    """返回 {kind: douban|imdb|tmdb, value:...}，无法识别返回 None"""
    s = (raw or "").strip()
    if not s:
        return None
    m = DOUBAN_RE.search(s) or DOUBAN_RE2.search(s)
    if m:
        return {"kind": "douban", "value": m.group(1)}
    m = IMDB_RE.search(s)
    if m:
        return {"kind": "imdb", "value": m.group(1).lower()}
    m = TMDB_RE.search(s)
    if m:
        return {"kind": "tmdb", "value": {"type": m.group(1).lower(), "id": m.group(2)}}
    if re.fullmatch(r"tt\d+", s, re.I):
        return {"kind": "imdb", "value": s.lower()}
    if re.fullmatch(r"\d+", s):
        return {"kind": "number", "value": s}
    return None


# ---------------------------------------------------------------- 标题拆分
def split_name(full_name):
    """人名拆分：中文在前则拆 chs/foreign"""
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""
    idx = full_name.find(" ")
    if idx > 0 and re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", full_name[:idx]):
        return full_name[:idx].strip(), full_name[idx + 1:].strip()
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", full_name):
        return full_name, ""
    return "", full_name


def normalize_douban_poster(url):
    """豆瓣海报取最大尺寸：m_ratio_poster/s_ratio_poster -> l_ratio_poster"""
    if not url:
        return ""
    return url.replace("/m_ratio_poster/", "/l_ratio_poster/").replace("/s_ratio_poster/", "/l_ratio_poster/")


def fmt_thousands(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)

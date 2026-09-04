# -*- coding: utf-8 -*-
"""编排：输入解析 -> ID 互查 -> 豆瓣聚合 -> IMDb/TMDB 评分 -> 海报上传 -> BBcode 生成"""
import re

from . import fetchers, formatter, poster


def _scrape_douban(douban_id):
    """聚合豆瓣各通道数据；返回 dict 或 None（完全拿不到数据时）"""
    rexxar = fetchers.fetch_douban_rexxar(douban_id)
    desc = fetchers.fetch_douban_desc(douban_id)
    if not rexxar and not desc:
        return None

    m = {}

    # ---- rexxar（手机 JSON）
    if rexxar:
        m["title"] = rexxar.get("title") or ""
        m["original_title"] = rexxar.get("original_title") or ""
        m["year"] = str(rexxar.get("year") or "")
        m["region"] = " / ".join(rexxar.get("countries") or [])
        m["genres"] = " / ".join(rexxar.get("genres") or [])
        m["language"] = " / ".join(rexxar.get("languages") or [])
        m["aka"] = rexxar.get("aka") or []
        m["pubdate"] = [str(p) for p in (rexxar.get("pubdate") or [])]
        m["intro"] = rexxar.get("intro") or ""
        m["poster"] = fetchers.normalize_douban_poster(
            (rexxar.get("pic") or {}).get("large") or rexxar.get("cover_url") or "")
        rating = rexxar.get("rating") or {}
        if rating.get("value"):
            m["douban_rating"] = str(rating["value"])
            m["douban_votes"] = int(rating.get("count") or 0)
        else:
            m["douban_rating"] = ""
            m["douban_votes"] = 0
        m["subtype"] = rexxar.get("subtype") or ("tv" if rexxar.get("is_tv") else "movie")

    # ---- desc（h5 简介页表格）
    if desc:
        m["desc"] = desc
        if not m.get("original_title") and desc.get("原名"):
            m["original_title"] = desc["原名"]
        if not m.get("title") and desc.get("片名"):
            m["title"] = desc["片名"]
        if not m.get("year"):
            y = re.search(r"\d{4}", desc.get("片名", ""))
            if y:
                m["year"] = y.group(0)
        if not m.get("region") and desc.get("地区"):
            m["region"] = desc["地区"]
        if not m.get("genres") and desc.get("类型"):
            m["genres"] = desc["类型"]
        if not m.get("language") and desc.get("语言"):
            m["language"] = desc["语言"]
        if not m.get("aka") and desc.get("又名"):
            m["aka"] = [a.strip() for a in desc["又名"].split("/") if a.strip()]
        if desc.get("上映"):
            # desc 页上映日期最全（含电影节/各地区），优先于 rexxar
            m["pubdate"] = [p.strip() for p in desc["上映"].split("/") if p.strip()]
        elif not m.get("pubdate"):
            pass
        m["imdb_id_from_desc"] = desc.get("IMDb") or ""
        m["director_desc"] = desc.get("导演") or ""
        m["writer_desc"] = desc.get("编剧") or ""
        m["cast_desc"] = desc.get("主演") or ""
        m["music_desc"] = desc.get("音乐") or ""
        m["durations"] = desc.get("片长") or ""

    # ---- 桌面版详情（住宅 IP 可用；失败静默）
    desktop = fetchers.fetch_douban_desktop(douban_id)
    if desktop:
        di = fetchers.parse_desktop_info(desktop)
        if di.get("poster") and not m.get("poster"):
            m["poster"] = fetchers.normalize_douban_poster(di["poster"])
        if di.get("intro") and not m.get("intro"):
            m["intro"] = di["intro"]
        if di.get("douban_rating") and not m.get("douban_rating"):
            m["douban_rating"] = di["douban_rating"]
            m["douban_votes"] = int(di.get("douban_votes") or 0)
        if di.get("info") and not m.get("region"):
            info = di["info"]
            m["region"] = info.get("制片国家/地区") or ""
            m["language"] = info.get("语言") or ""
            m["aka"] = [a.strip() for a in info.get("又名", "").split("/") if a.strip()]
            m["durations"] = info.get("片长") or info.get("单集片长") or ""

    # ---- 演职员整页（住宅 IP 可用；失败静默）
    celebs = fetchers.fetch_douban_celebrities(douban_id)
    if celebs:
        m["celebrities"] = celebs
    else:
        m["celebrities"] = []

    return m


def _crew_lines(m):
    """导演/演员/编剧/音乐 四段，优先演职员页，其次 desc 表"""
    celebs = m.get("celebrities") or []
    if celebs:
        return formatter.format_celebrities(celebs)
    lines = []
    if m.get("director_desc"):
        lines.append(("导演", m["director_desc"]))
    if m.get("cast_desc"):
        parts = formatter._split_people(m["cast_desc"])[:15]
        lines.append(("演员", "\n".join(("　　　　　　" if i > 0 else "") + p for i, p in enumerate(parts))))
    if m.get("writer_desc"):
        lines.append(("编剧", m["writer_desc"]))
    if m.get("music_desc"):
        lines.append(("音乐", m["music_desc"]))
    return lines


def _resolve_music(m):
    """音乐（豆瓣侧）：desc 表 -> 演职员页"""
    if m.get("music_desc"):
        return m["music_desc"]
    for sec in m.get("celebrities") or []:
        if sec.get("position") == "音乐" and sec.get("people"):
            return " / ".join(p["name"] for p in sec["people"])
    return ""


def _pick_douban_candidate(candidates, year=None):
    """从豆瓣 suggest 候选中选最可能的一条"""
    if not candidates:
        return None
    for c in candidates:
        cy = str(c.get("year") or "").strip()
        if year and cy and cy == str(year).strip():
            return c
    for c in candidates:
        if re.search(r"(电影|剧集|电视剧)", str(c.get("type") or ""), re.I):
            return c
    return candidates[0]


def generate(raw_input, cache=None):
    """主入口：解析 -> 抓取 -> 汇总 -> 海报上传 -> BBcode。返回完整 dict"""
    parsed = fetchers.parse_input(raw_input)
    if not parsed:
        return {"success": False, "error": "无法识别的输入，请粘贴豆瓣/IMDb/TMDb 完整链接或末尾数字"}

    kind = parsed["kind"]
    douban_id = imdb_id = tmdb_id = media_type = None
    tmdb_info = None
    omdb = None

    # ---------- 豆瓣入口 ----------
    if kind == "douban":
        douban_id = parsed["value"]
    # ---------- IMDb 入口 ----------
    elif kind == "imdb":
        imdb_id = parsed["value"]
        # 1) TMDB 反查（可达时）
        tmdb_info = fetchers.fetch_tmdb_by_imdb(imdb_id)
        # 2) OMDb 取标题/年份（全球可用）
        omdb = fetchers.fetch_omdb(imdb_id)
        title = ""
        year = ""
        if tmdb_info:
            title = tmdb_info.get("title") or ""
            year = tmdb_info.get("year") or ""
            tmdb_id = tmdb_info["id"]
            media_type = tmdb_info["type"]
        if not title and omdb:
            title = omdb.get("Title") or ""
            year = omdb.get("Year") or ""
        if title:
            found = fetchers.find_douban_by_title(title, year)
            cand = _pick_douban_candidate([found], year) if found else None
            if cand:
                douban_id = str(cand.get("id") or "")
    # ---------- TMDB 入口 ----------
    elif kind == "tmdb":
        tmdb_id = parsed["value"]["id"]
        media_type = parsed["value"]["type"]
        tmdb_info = fetchers.fetch_tmdb_details(media_type, tmdb_id)
        if not tmdb_info:
            return {"success": False,
                    "error": "TMDB API 不可达或条目不存在（沙箱/网络限制），请检查服务器能否访问 api.themoviedb.org"}
        imdb_id = tmdb_info.get("imdb_id") or ""
        title = tmdb_info.get("title") or tmdb_info.get("original_title") or ""
        year = tmdb_info.get("year") or ""
        if title:
            found = fetchers.find_douban_by_title(title, year)
            cand = _pick_douban_candidate([found], year) if found else None
            if cand:
                douban_id = str(cand.get("id") or "")
    # ---------- 纯数字入口 ----------
    elif kind == "number":
        num = parsed["value"]
        m = fetchers.fetch_douban_rexxar(num)
        if m and (m.get("title") or m.get("subtype")):
            douban_id = num
        else:
            # 豆瓣无此条目 -> 尝试 TMDB movie / tv
            tmi = fetchers.fetch_tmdb_details("movie", num)
            if tmi:
                tmdb_id = num
                media_type = "movie"
                tmdb_info = tmi
            else:
                tti = fetchers.fetch_tmdb_details("tv", num)
                if tti:
                    tmdb_id = num
                    media_type = "tv"
                    tmdb_info = tti
                elif not fetchers.tmdb_reachable():
                    return {"success": False,
                            "error": "豆瓣无此条目，且 TMDB API 不可达（请检查服务器能否访问 api.themoviedb.org）"}
                else:
                    return {"success": False,
                            "error": "豆瓣与 TMDB 均未找到该编号，请确认输入正确"}

    # ---------- 豆瓣聚合 ----------
    m = None
    if douban_id:
        m = _scrape_douban(douban_id)
        if m is None:
            return {"success": False, "error": f"豆瓣条目 {douban_id} 抓取失败（可能被反爬拦截），请稍后重试"}

    # ---------- 补全 IMDb ID ----------
    if m and not imdb_id:
        imdb_id = m.get("imdb_id_from_desc") or ""
        if not imdb_id and m.get("original_title") and m.get("year"):
            # 尝试 TMDB 按标题搜索
            s = fetchers.tmdb_get("/search/movie", {"query": m["original_title"], "year": m["year"]})
            if s and s.get("results"):
                r0 = s["results"][0]
                ext = fetchers.tmdb_get(f"/movie/{r0['id']}/external_ids")
                if ext and ext.get("imdb_id"):
                    imdb_id = ext["imdb_id"]
                    tmdb_id = r0["id"]
                    media_type = "movie"

    # ---------- TMDB 链接（供 JSON，不写入 BBcode） ----------
    if not tmdb_id and imdb_id:
        t = fetchers.fetch_tmdb_by_imdb(imdb_id)
        if t:
            tmdb_id = t["id"]
            media_type = t["type"]

    # ---------- 海报（优先豆瓣海报；无豆瓣时用 TMDB/OMDb 海报） ----------
    poster_url = ""
    poster_source = ""
    if m and m.get("poster"):
        poster_url = m["poster"]
        poster_source = "douban"
    elif tmdb_info and tmdb_info.get("poster"):
        poster_url = tmdb_info["poster"]
        poster_source = "tmdb"
    elif omdb and omdb.get("Poster") not in (None, "", "N/A"):
        poster_url = omdb["Poster"]
        poster_source = "omdb"

    poster_upload = {"uploaded_url": "", "host": "", "status": "skipped"}
    if poster_url:
        poster_upload = poster.ensure_poster_uploaded(poster_url)

    # ---------- 数据汇总 ----------
    yiming = ""
    original_title = ""
    if m:
        # 豆瓣对“原名=中文名”的片子不返回 original_title，此时回退用中文名当片名（与油猴脚本一致）
        orig = m.get("original_title") or ""
        if not orig:
            orig = m.get("title") or ""
        yiming = formatter.build_yiming(m.get("title"), orig, m.get("aka"))
        original_title = orig
    elif tmdb_info:
        yiming = (tmdb_info.get("title") or tmdb_info.get("original_title") or "")
        original_title = tmdb_info.get("original_title") or ""
    elif omdb:
        yiming = omdb.get("Title") or ""
        original_title = omdb.get("Title") or ""

    crew_lines = _crew_lines(m) if m else []
    music = ""
    if m:
        music = _resolve_music(m)
    if not music and tmdb_info and tmdb_info.get("music"):
        music = " / ".join(tmdb_info["music"])
    if not music and imdb_id:
        wd = fetchers.wikidata_lookup(imdb_id)
        if wd and wd.get("composer"):
            music = wd["composer"]
    if music and not any(lbl == "音乐" for lbl, _ in crew_lines):
        crew_lines.append(("音乐", music))

    # IMDb 评分
    imdb_rating = None
    imdb_votes = 0
    if imdb_id:
        r = fetchers.fetch_imdb_rating(imdb_id)
        if r:
            imdb_rating = r["rating"]
            imdb_votes = r["votes"]

    # 无豆瓣时用 OMDb/TMDB 兜底基础字段
    release_dates = ""
    if m:
        dates = m.get("pubdate") or []
        release_dates = " / ".join(sorted(dates, key=lambda x: (re.match(r"(\d{4}-\d{2}-\d{2})", x) or [None, ""]).group(1) if re.match(r"(\d{4}-\d{2}-\d{2})", x) else ""))
    elif omdb and omdb.get("Released") not in (None, "", "N/A"):
        release_dates = omdb.get("Released", "")

    data = {
        "title_zh": (m.get("title") if m else "") or "",
        "original_title": original_title,
        "yiming": yiming,
        "year": (m.get("year") if m else "") or (tmdb_info or {}).get("year", "") or (omdb or {}).get("Year", ""),
        "region": (m.get("region") if m else "") or (omdb or {}).get("Country", "").replace(",", " / ") or "",
        "genres": (m.get("genres") if m else "") or (omdb or {}).get("Genre", "").replace(",", " / ") or "",
        "language": (m.get("language") if m else "") or (omdb or {}).get("Language", "").replace(",", " / ") or "",
        "release_dates": release_dates,
        "durations": (m.get("durations") if m else "") or (omdb or {}).get("Runtime", ""),
        "douban_rating": (m.get("douban_rating") if m else "") or "",
        "douban_votes": int((m.get("douban_votes") if m else 0) or 0),
        "imdb_rating": imdb_rating,
        "imdb_votes": imdb_votes,
        "douban_url": f"https://movie.douban.com/subject/{douban_id}/" if douban_id else "",
        "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
        "tmdb_url": f"https://www.themoviedb.org/{media_type}/{tmdb_id}" if tmdb_id and media_type else "",
        "intro": (m.get("intro") if m else "") or (tmdb_info or {}).get("overview", "") or (omdb or {}).get("Plot", "") or "",
        "music": (dict(crew_lines).get("音乐") or ""),
        "crew_lines": crew_lines,
    }

    result = {
        "success": True,
        "input": (raw_input or "").strip(),
        "kind": kind,
        "douban_id": douban_id or "",
        "imdb_id": imdb_id or "",
        "tmdb_id": str(tmdb_id) if tmdb_id else "",
        "media_type": media_type or ((m.get("subtype") if m else "") or ""),
        "data": data,
        "poster": poster_upload,
        "bbcode": formatter.build_bbcode(data, poster_upload),
    }
    return result

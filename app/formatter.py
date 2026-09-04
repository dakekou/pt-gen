# -*- coding: utf-8 -*-
"""生成 PT 发布帖 BBcode：格式严格对照用户提供的模板（图）并新增 IMDb 评分项"""
from . import fetchers

SP = "\u3000"  # 全角空格


def _title_line(label, value):
    if not value:
        return None
    return f"◎{label}{SP}{value}"


def build_yiming(chs_title, original_title, aka_list):
    """译名：中文名 + 又名，去重、排除片名；全外文时用又名兜底"""
    seen = set()
    out = []
    for t in [chs_title] + (aka_list or []):
        t = (t or "").strip()
        if not t or t == (original_title or "").strip():
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    if not out:
        out.append(original_title or chs_title or "")
    return " / ".join(out)


def _split_people(value):
    return [p.strip() for p in (value or "").split("/") if p.strip()]


def _spaced_label(pos):
    """职位标签补全角空格对齐，如 导演 -> 导　　演（不含末尾分隔空格，由调用方统一加）"""
    pos = pos or ""
    n = len(pos)
    if n == 1:
        return "　" + pos + "　　　"
    if n == 2:
        return pos[0] + "　　" + pos[1]
    if n == 3:
        return pos[0] + "  " + pos[1] + "  " + pos[2] + "　"
    return pos + "　"


def format_celebrities(sections, keep=("导演", "演员", "编剧", "音乐"), max_people=15):
    """演职员页 sections -> 有序文本列表 [(position, text)]，position 为纯职位名"""
    lines = []
    for sec in sections or []:
        pos = sec.get("position", "")
        if pos not in keep:
            continue
        people = sec.get("people") or []
        if not people:
            continue
        parts = []
        for i, p in enumerate(people[:max_people]):
            name = p.get("name", "")
            role = p.get("role", "")
            text = name + (f" ({role})" if role else "")
            parts.append(("　　　　　　" if i > 0 else "") + text)
        lines.append((pos, "\n".join(parts)))
    return lines


def build_bbcode(m, poster_upload):
    """m 为聚合后的数据字典，poster_upload 为 {uploaded_url, host}"""
    out = []
    if poster_upload.get("uploaded_url"):
        out.append(f"[img]{poster_upload['uploaded_url']}[/img]")
        out.append("")

    lines = []
    lines.append(_title_line("译　　名", m.get("yiming")))
    lines.append(_title_line("片　　名", m.get("original_title")))
    lines.append(_title_line("年　　代", m.get("year")))
    lines.append(_title_line("产　　地", m.get("region")))
    lines.append(_title_line("类　　别", m.get("genres")))
    lines.append(_title_line("语　　言", m.get("language")))
    lines.append(_title_line("上映日期", m.get("release_dates")))

    db = m.get("douban_rating")
    if db:
        dbv = fetchers.fmt_thousands(m.get("douban_votes") or 0)
        lines.append(f"◎豆瓣评分{SP}{db}/10 from {dbv} users")

    im = m.get("imdb_rating")
    if im is not None:
        imv = fetchers.fmt_thousands(m.get("imdb_votes") or 0)
        lines.append(f"◎IMDb评分{SP}{im}/10 from {imv} users")

    if m.get("douban_url"):
        lines.append(f"◎豆瓣链接{SP}{m['douban_url']}")
    if m.get("imdb_url"):
        lines.append(f"◎IMDb链接  {m['imdb_url']}")

    for label, text in m.get("crew_lines", []):
        lines.append(f"◎{_spaced_label(label)}{SP}{text}")

    intro = (m.get("intro") or "").strip()
    if intro:
        lines.append("")
        lines.append("◎简　　介")
        lines.append("")
        indented = "\n".join(f"{SP}{SP}{line}" for line in intro.splitlines())
        lines.append(indented)

    out.extend(lines)
    return "\n".join(x for x in out if x)

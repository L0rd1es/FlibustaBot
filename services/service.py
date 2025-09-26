# services/service.py

import asyncio
import time
import aiohttp
import re
import logging
import random
from typing import Any, Dict, List, Optional, Callable

from bs4 import BeautifulSoup, Tag
from config import FLIBUSTA_MIRRORS, RATE_LIMIT_RPS

logger = logging.getLogger(__name__)

# --------- Глобальные состояния ---------
mirror_state: List[Dict[str, Any]] = [{"url": m, "penalty": 0} for m in FLIBUSTA_MIRRORS]
_mirrors_lock = asyncio.Lock()

_last_request_mono = 0.0
_rate_limit_lock = asyncio.Lock()

_session: Optional[aiohttp.ClientSession] = None

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)
_DEFAULT_HEADERS = {"User-Agent": "FlibustaBot/1.0 (+https://t.me/your_bot)"}


# --------- Вспомогательные хелперы ---------

def _href_startswith(prefix: str) -> Callable[[Optional[str]], bool]:
    """Typed-предикат для BeautifulSoup href=..."""
    def _pred(x: Optional[str]) -> bool:
        return isinstance(x, str) and x.startswith(prefix)
    return _pred


def _text_clean(s: str) -> str:
    return " ".join(s.split())


def _as_tag(node: Any) -> Optional[Tag]:
    return node if isinstance(node, Tag) else None


def _str_attr(tag: Tag, name: str) -> str:
    """
    Безопасно вернуть строковый атрибут тега.
    Возвращает "" если атрибут отсутствует или имеет тип не str (например, AttributeValueList).
    """
    val = tag.get(name)
    return val if isinstance(val, str) else ""


# --------- Сессия/Rate Limit ---------

async def _ensure_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT, headers=_DEFAULT_HEADERS)
    return _session


async def init_session() -> None:
    await _ensure_session()


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def rate_limit() -> None:
    global _last_request_mono
    if RATE_LIMIT_RPS <= 0:
        return
    interval = 1.0 / RATE_LIMIT_RPS
    async with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_request_mono
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        _last_request_mono = time.monotonic()


async def _pick_best_mirror() -> Dict[str, Any]:
    async with _mirrors_lock:
        mirror_state.sort(key=lambda x: x["penalty"])
        return mirror_state[0]


async def _bump_penalty(mirror: Dict[str, Any], delta: int = 1) -> None:
    async with _mirrors_lock:
        mirror["penalty"] = mirror.get("penalty", 0) + delta


async def _decay_penalty(mirror: Dict[str, Any], delta: int = 1) -> None:
    async with _mirrors_lock:
        mirror["penalty"] = max(0, mirror.get("penalty", 0) - delta)


# --------- Сетевой слой ---------

async def fetch_url_with_penalty(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    max_retries: int = 3,
) -> str:
    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        mirror = await _pick_best_mirror()
        url = mirror["url"] + path
        await rate_limit()

        try:
            sess = await _ensure_session()
            logger.info("Fetching URL: %s (attempt %d/%d)", url, attempt, max_retries)
            async with sess.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    await _decay_penalty(mirror, 1)
                    text = await resp.text()
                    logger.debug("Fetched OK: %s", url)
                    return text
                else:
                    await _bump_penalty(mirror, 1)
                    last_exc = Exception(f"HTTP {resp.status} {url}")
                    logger.warning("Non-200 response: %s -> %s", url, resp.status)
        except asyncio.TimeoutError:
            await _bump_penalty(mirror, 2)
            last_exc = Exception(f"Timeout when fetching {url}")
            logger.warning("Timeout fetching %s", url)
        except Exception as e:
            await _bump_penalty(mirror, 2)
            last_exc = e
            logger.exception("Exception during fetching: %s", url)

        backoff = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.3)
        await asyncio.sleep(backoff)

    raise last_exc or Exception("All mirrors failed")


# --------- Бизнес-логика ---------

async def search_books_and_authors(query: str, mode: str = "general") -> Dict[str, Any]:
    params: Dict[str, Any] = {"ask": query}
    if mode in ("general", "book"):
        params["chb"] = "on"
    if mode in ("general", "author"):
        params["cha"] = "on"
    if mode == "general":
        params["chs"] = "on"

    html = await fetch_url_with_penalty("/booksearch", params=params, headers=_DEFAULT_HEADERS)
    soup = BeautifulSoup(html, "lxml")

    data: Dict[str, Any] = {"books_found": [], "authors_found": []}

    # Авторы
    h3_auth = soup.find(lambda t: _as_tag(t) is not None and t.name == "h3" and "Найденные писатели" in t.get_text("", strip=True))
    h3_auth = _as_tag(h3_auth)
    if h3_auth:
        ul = _as_tag(h3_auth.find_next("ul"))
        if ul:
            for li in ul.find_all("li"):
                li = _as_tag(li)
                if not li:
                    continue
                a_tag = _as_tag(li.find("a", href=_href_startswith("/a/")))
                if not a_tag:
                    continue
                href = _str_attr(a_tag, "href")
                author_id = href.split("/a/")[-1] if "/a/" in href else "?"
                txt = _text_clean(li.get_text())
                mm = re.search(r"\((\d+)\s*книг", txt)
                bc = mm.group(1) if mm else "?"
                aname = _text_clean(a_tag.get_text())
                data["authors_found"].append({"id": author_id, "name": aname, "book_count": bc})

    # Книги
    h3_books = soup.find(lambda t: _as_tag(t) is not None and t.name == "h3" and "Найденные книги" in t.get_text("", strip=True))
    h3_books = _as_tag(h3_books)
    if h3_books:
        ul = _as_tag(h3_books.find_next("ul"))
        if ul:
            for li in ul.find_all("li"):
                li = _as_tag(li)
                if not li:
                    continue
                a_tags = [_as_tag(a) for a in li.find_all("a")]
                a_tags = [a for a in a_tags if a is not None]
                if not a_tags:
                    continue
                raw_title = _text_clean(a_tags[0].get_text())
                title_clean = re.sub(r"\([^)]+\)$", "", raw_title).strip()
                hrefb = _str_attr(a_tags[0], "href")
                b_id = hrefb.split("/b/")[-1] if "/b/" in hrefb else "???"
                auth_list: List[str] = []
                for xx in a_tags[1:]:
                    nm = _text_clean(xx.get_text())
                    if nm.lower() not in ("все",):
                        auth_list.append(nm)
                if not auth_list:
                    auth_list = ["Автор неизвестен"]
                auth_str = ", ".join(auth_list)
                data["books_found"].append({"id": b_id, "title": title_clean, "author": auth_str})

    return data


async def get_book_details(book_id: str) -> Dict[str, Any]:
    try:
        logger.info("get_book_details start: %s", book_id)
        html = await fetch_url_with_penalty(f"/b/{book_id}", headers=_DEFAULT_HEADERS)
        soup = BeautifulSoup(html, "lxml")

        title = "Неизвестно"
        author = ""
        annotation = ""
        year: Optional[str] = None
        cover_url: Optional[str] = None
        formats: set[str] = set()

        h1 = _as_tag(soup.find("h1", class_="title"))
        if h1:
            t = _text_clean(h1.get_text())
            t = re.sub(r"\([^)]+\)$", "", t).strip()
            title = t

        a_auth = _as_tag(h1.find_next("a", href=_href_startswith("/a/"))) if h1 else _as_tag(soup.find("a", href=_href_startswith("/a/")))
        if a_auth:
            author = _text_clean(a_auth.get_text())

        anno_div = _as_tag(soup.find("div", id="bookannotation"))
        if anno_div:
            at = _text_clean(anno_div.get_text())
            if len(at) > 2000:
                at = at[:2000] + "..."
            annotation = at

        mm = re.search(r"издание\s+(\d{4})\s*(года|г\.)", html, re.IGNORECASE)
        if mm:
            year = mm.group(1)

        cov = _as_tag(soup.find("img", alt="Cover image"))
        if cov:
            raw_src = _str_attr(cov, "src")
            if raw_src:
                if raw_src.startswith("/"):
                    best = await _pick_best_mirror()
                    cover_url = best["url"] + raw_src
                else:
                    cover_url = raw_src

        for link in soup.find_all("a"):
            link = _as_tag(link)
            if not link:
                continue
            hr = _str_attr(link, "href").lower()
            if f"/b/{book_id}" in hr:
                if "fb2" in hr:
                    formats.add("fb2")
                elif "epub" in hr:
                    formats.add("epub")
                elif "mobi" in hr:
                    formats.add("mobi")
                elif "pdf" in hr:
                    formats.add("pdf")

        logger.info("get_book_details done: %s", book_id)
        return {
            "id": book_id,
            "title": title,
            "author": author,
            "annotation": annotation,
            "year": year,
            "cover_url": cover_url,
            "formats": sorted(formats),
        }
    except Exception:
        logger.exception("Ошибка в get_book_details для %s", book_id)
        raise


async def download_book(book_id: str, fmt: str) -> bytes:
    paths = [f"/b/{book_id}/{fmt}", f"/b/{book_id}/download?format={fmt}"]
    last_exc: Optional[Exception] = None
    max_retries = 3
    timeout_seconds = 20

    logger.info("download_book start: %s (%s)", book_id, fmt)

    for path in paths:
        for attempt in range(1, max_retries + 1):
            await rate_limit()
            mirror = await _pick_best_mirror()
            url = mirror["url"] + path

            try:
                sess = await _ensure_session()
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                async with sess.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        content = await resp.read()
                        if content:
                            await _decay_penalty(mirror, 1)
                            logger.info("download_book OK: %s", url)
                            return content
                        else:
                            await _bump_penalty(mirror, 1)
                            last_exc = Exception(f"Empty content: {url}")
                            logger.warning("Empty content: %s", url)
                    else:
                        await _bump_penalty(mirror, 1)
                        last_exc = Exception(f"HTTP {resp.status} {url}")
                        logger.warning("download_book HTTP %s: %s", resp.status, url)

            except asyncio.TimeoutError:
                await _bump_penalty(mirror, 2)
                last_exc = Exception(f"Timeout: {url}")
                logger.warning("download_book timeout: %s", url)
            except Exception as e:
                await _bump_penalty(mirror, 2)
                last_exc = e
                logger.exception("download_book error: %s", url)

            backoff = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.3)
            await asyncio.sleep(backoff)

    logger.error("download_book failed after retries: %s (%s)", book_id, fmt)
    raise last_exc or Exception(f"Не удалось скачать {book_id} ({fmt})")


async def get_author_books(author_id: str, default_author: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        logger.info("get_author_books start: %s", author_id)
        html = await fetch_url_with_penalty(f"/a/{author_id}", headers=_DEFAULT_HEADERS)
        soup = BeautifulSoup(html, "lxml")
        out: List[Dict[str, Any]] = []

        def is_poor(name: Optional[str]) -> bool:
            if not name:
                return True
            s = name.strip()
            if not s or s.lower() == "неизвестен":
                return True
            # «одно слово» считаем плохим (например, только "Адамс")
            return len(s.split()) < 2

        # --- основная секция со списком произведений автора ---
        h_section = soup.find(
            lambda t: _as_tag(t) is not None
            and t.name in ("h2", "h3")
            and any(k in t.get_text("", strip=True)
                    for k in ("Книги автора", "Произведения автора", "Найденные книги", "Список произведений"))
        )
        h_section = _as_tag(h_section)

        filled = False
        if h_section:
            ul = _as_tag(h_section.find_next("ul"))
            if ul:
                for li in ul.find_all("li"):
                    li = _as_tag(li)
                    if not li:
                        continue
                    a_tag = _as_tag(li.find("a"))
                    if not a_tag:
                        continue
                    raw_title = _text_clean(a_tag.get_text())
                    t_clean = re.sub(r"\([^)]+\)$", "", raw_title).strip()
                    hr = _str_attr(a_tag, "href")
                    b_id = hr.split("/b/")[-1] if "/b/" in hr else "???"

                    # текущее имя автора (как было раньше)
                    if default_author is not None and default_author.strip():
                        auth_name = default_author.strip()
                    else:
                        h1_author = _as_tag(soup.find("h1"))
                        if h1_author:
                            text_h1 = _text_clean(h1_author.get_text())
                            auth_name = text_h1 if "флибуста" not in text_h1.lower() else "Неизвестен"
                        else:
                            auth_name = "Неизвестен"

                    out.append({"id": b_id, "title": t_clean, "author": auth_name})
                filled = bool(out)

        # --- fallback: собрать все ссылки вида /b/<id> ---
        if not filled:
            links = soup.find_all("a", href=re.compile(r"^/b/\d+$"))
            seen = set()
            for link in links:
                link = _as_tag(link)
                if not link:
                    continue
                hr = _str_attr(link, "href")
                b_id = hr.split("/b/")[-1]
                if b_id in seen:
                    continue
                seen.add(b_id)
                title = _text_clean(link.get_text())

                if default_author is not None and default_author.strip():
                    auth_name = default_author.strip()
                else:
                    h1_author = _as_tag(soup.find("h1"))
                    if h1_author:
                        text_h1 = _text_clean(h1_author.get_text())
                        auth_name = text_h1 if "флибуста" not in text_h1.lower() else "Неизвестен"
                    else:
                        auth_name = "Неизвестен"

                out.append({"id": b_id, "title": title, "author": auth_name})

        # --- упрощённый «доводчик»: если имя автора «плохое», берём его с первой книги ---
        if out:
            current_name = (out[0].get("author") or "").strip()
            # если default_author валиден — он приоритетнее и запроса к книге не делаем
            if not (default_author and not is_poor(default_author)):
                if is_poor(current_name):
                    try:
                        # одна дополнительная загрузка детали первой книги
                        details = await get_book_details(out[0]["id"])
                        full_name = (details.get("author") or "").strip()
                        if not is_poor(full_name):
                            for r in out:
                                r["author"] = full_name
                    except Exception:
                        # не удалось — просто оставим как есть
                        pass

        logger.info("get_author_books done: %d items", len(out))
        return out

    except Exception:
        logger.exception("Ошибка в get_author_books для %s", author_id)
        raise

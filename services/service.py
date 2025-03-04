# service.py

import asyncio
import time
import aiohttp
import re
import logging
from bs4 import BeautifulSoup
from config import FLIBUSTA_MIRRORS, RATE_LIMIT_RPS

logger = logging.getLogger(__name__)

mirror_state = [{"url": m, "penalty": 0} for m in FLIBUSTA_MIRRORS]
last_request_time = 0.0
rate_limit_lock = asyncio.Lock()

session = None

async def init_session():
    global session
    session = aiohttp.ClientSession()

async def close_session():
    if session is not None:
        await session.close()

async def rate_limit():
    global last_request_time
    interval = 1.0 / RATE_LIMIT_RPS
    async with rate_limit_lock:
        now = time.time()
        elapsed = now - last_request_time
        if elapsed < interval:
            await asyncio.sleep(interval - elapsed)
        last_request_time = time.time()

async def fetch_url_with_penalty(path: str, params=None, headers=None, max_retries=3) -> str:
    attempt = 0
    delay = 1
    last_exc = None
    while attempt < max_retries:
        attempt += 1
        mirror_state.sort(key=lambda x: x["penalty"])
        mirror = mirror_state[0]
        url = mirror["url"] + path
        await rate_limit()
        try:
            logger.info(f"Fetching URL: {url} (Attempt {attempt})")
            async with session.get(url, params=params, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    mirror["penalty"] = max(0, mirror["penalty"] - 1)
                    logger.info(f"Fetched URL successfully: {url}")
                    return await resp.text()
                else:
                    mirror["penalty"] += 1
                    last_exc = Exception(f"HTTP {resp.status} {url}")
                    logger.error(f"Error fetching URL: HTTP {resp.status} for {url}")
        except Exception as e:
            mirror["penalty"] += 1
            last_exc = e
            logger.exception(f"Exception during fetching URL: {url}")
        await asyncio.sleep(delay)
        delay *= 2
    raise last_exc or Exception("All mirrors failed")

async def search_books_and_authors(query: str, mode="general") -> dict:
    params = {"ask": query}
    if mode in ("general", "book"):
        params["chb"] = "on"
    if mode in ("general", "author"):
        params["cha"] = "on"
    if mode == "general":
        params["chs"] = "on"

    html = await fetch_url_with_penalty("/booksearch", params=params, headers={"User-Agent": "Bot/1.0"})
    soup = BeautifulSoup(html, "lxml")

    data = {
        "books_found": [],
        "authors_found": []
    }

    # Авторы
    h3_auth = soup.find(lambda t: t.name == "h3" and "Найденные писатели" in t.get_text("", strip=True))
    if h3_auth:
        ul = h3_auth.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                a_tag = li.find("a", href=lambda x: x and x.startswith("/a/"))
                if not a_tag:
                    continue
                href = a_tag["href"]
                author_id = href.split("/a/")[-1]
                txt = " ".join(li.get_text().split())
                mm = re.search(r"\((\d+)\s*книг", txt)
                bc = mm.group(1) if mm else "?"
                aname = " ".join(a_tag.get_text().split())
                data["authors_found"].append({
                    "id": author_id,
                    "name": aname,
                    "book_count": bc
                })

    # Книги
    h3_books = soup.find(lambda t: t.name == "h3" and "Найденные книги" in t.get_text("", strip=True))
    if h3_books:
        ul = h3_books.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                a_tags = li.find_all("a")
                if not a_tags:
                    continue
                raw_title = " ".join(a_tags[0].get_text().split())
                title_clean = re.sub(r"\([^)]+\)$", "", raw_title).strip()
                hrefb = a_tags[0].get("href", "")
                b_id = "???"
                if "/b/" in hrefb:
                    b_id = hrefb.split("/b/")[-1]
                auth_list = []
                for xx in a_tags[1:]:
                    nm = " ".join(xx.get_text().split())
                    if nm.lower() not in ("все",):
                        auth_list.append(nm)
                if not auth_list:
                    auth_list = ["Автор неизвестен"]
                auth_str = ", ".join(auth_list)
                data["books_found"].append({
                    "id": b_id,
                    "title": title_clean,
                    "author": auth_str
                })

    return data

async def get_book_details(book_id: str) -> dict:
    try:
        logger.info(f"Начало получения деталей книги для book_id {book_id}")
        html = await fetch_url_with_penalty(f"/b/{book_id}", headers={"User-Agent": "Bot/1.0"})
        soup = BeautifulSoup(html, "lxml")
        title = "Неизвестно"
        author = ""
        annotation = ""
        year = None
        cover_url = None
        formats = set()

        h1 = soup.find("h1", class_="title")
        if h1:
            t = " ".join(h1.get_text().split())
            t = re.sub(r"\([^)]+\)$", "", t).strip()
            title = t

        if h1:
            a_auth = h1.find_next("a", href=lambda x: x and x.startswith("/a/"))
        else:
            a_auth = soup.find("a", href=lambda x: x and x.startswith("/a/"))
        if a_auth:
            author = " ".join(a_auth.get_text().split())

        anno_div = soup.find("div", id="bookannotation")
        if anno_div:
            at = " ".join(anno_div.get_text().split())
            if len(at) > 2000:
                at = at[:2000] + "..."
            annotation = at

        mm = re.search(r"издание\s+(\d{4})\s*(года|г\.)", html, re.IGNORECASE)
        if mm:
            year = mm.group(1)

        cov = soup.find("img", alt="Cover image")
        if cov and cov.get("src"):
            raw_src = cov["src"]
            if raw_src.startswith("/"):
                mirror_state.sort(key=lambda x: x["penalty"])
                cover_url = mirror_state[0]["url"] + raw_src
            else:
                cover_url = raw_src

        for link in soup.find_all("a"):
            hr = link.get("href", "").lower()
            if f"/b/{book_id}" in hr:
                if "fb2" in hr:
                    formats.add("fb2")
                elif "epub" in hr:
                    formats.add("epub")
                elif "mobi" in hr:
                    formats.add("mobi")
                elif "pdf" in hr:
                    formats.add("pdf")

        logger.info(f"Завершено получение деталей книги для book_id {book_id}")
        return {
            "id": book_id,
            "title": title,
            "author": author,
            "annotation": annotation,
            "year": year,
            "cover_url": cover_url,
            "formats": list(formats)
        }
    except Exception as e:
        logger.exception(f"Ошибка в get_book_details для book_id {book_id}:")
        raise

async def download_book(book_id: str, fmt: str) -> bytes:
    paths = [f"/b/{book_id}/{fmt}", f"/b/{book_id}/download?format={fmt}"]
    last_exc = None
    try:
        logger.info(f"Начало скачивания книги {book_id} с форматом {fmt}")
        for path in paths:
            for attempt in range(2):
                await rate_limit()
                mirror_state.sort(key=lambda x: x["penalty"])
                mirror = mirror_state[0]
                url = mirror["url"] + path
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            content = await resp.read()
                            if content:
                                mirror["penalty"] = max(0, mirror["penalty"] - 1)
                                logger.info(f"Скачивание книги успешно завершено для URL: {url}")
                                return content
                            else:
                                mirror["penalty"] += 1
                                last_exc = Exception(f"Empty content {url}")
                                logger.error(f"Пустой ответ для URL: {url}")
                        else:
                            mirror["penalty"] += 1
                            last_exc = Exception(f"Download error {resp.status} {url}")
                            logger.error(f"Ошибка скачивания, статус {resp.status} для URL: {url}")
                except Exception as e:
                    mirror["penalty"] += 1
                    last_exc = e
                    logger.exception(f"Исключение при скачивании для URL: {url}")
                await asyncio.sleep(2 ** attempt)
        logger.info(f"Скачивание книги завершено для book_id {book_id}")
    except Exception as e:
        logger.exception(f"Ошибка в download_book для book_id {book_id} с форматом {fmt}:")
        raise
    raise last_exc or Exception("Cannot download book")

async def get_author_books(author_id: str, default_author: str = None) -> list:
    try:
        logger.info(f"Начало получения книг автора для author_id {author_id}")
        html = await fetch_url_with_penalty(f"/a/{author_id}", headers={"User-Agent": "Bot/1.0"})
        soup = BeautifulSoup(html, "lxml")
        out = []
        h_section = soup.find(lambda t: t.name in ("h2", "h3") and (
            "Книги автора" in t.get_text("", strip=True) or
            "Произведения автора" in t.get_text("", strip=True) or
            "Найденные книги" in t.get_text("", strip=True) or
            "Список произведений" in t.get_text("", strip=True)
        ))
        if h_section:
            ul = h_section.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    a_tag = li.find("a")
                    if not a_tag:
                        continue
                    raw_title = " ".join(a_tag.get_text().split())
                    t_clean = re.sub(r"\([^)]+\)$", "", raw_title).strip()
                    hr = a_tag.get("href", "")
                    b_id = hr.split("/b/")[-1] if "/b/" in hr else "???"
                    if default_author is not None:
                        auth_name = default_author
                    else:
                        h1_author = soup.find("h1")
                        if h1_author:
                            text_h1 = " ".join(h1_author.get_text().split())
                            auth_name = text_h1 if "флибуста" not in text_h1.lower() else "Неизвестен"
                        else:
                            auth_name = "Неизвестен"
                    out.append({
                        "id": b_id,
                        "title": t_clean,
                        "author": auth_name
                    })
            if out:
                logger.info(f"Получено {len(out)} книг автора для author_id {author_id}")
                return out
        links = soup.find_all("a", href=re.compile(r"^/b/\d+$"))
        seen = set()
        for link in links:
            hr = link.get("href")
            b_id = hr.split("/b/")[-1]
            if b_id in seen:
                continue
            seen.add(b_id)
            title = " ".join(link.get_text().split())
            if default_author is not None:
                auth_name = default_author
            else:
                h1_author = soup.find("h1")
                if h1_author:
                    text_h1 = " ".join(h1_author.get_text().split())
                    auth_name = text_h1 if "флибуста" not in text_h1.lower() else "Неизвестен"
                else:
                    auth_name = "Неизвестен"
            out.append({
                "id": b_id,
                "title": title,
                "author": auth_name
            })
        logger.info(f"Получено {len(out)} книг автора (fallback) для author_id {author_id}")
        return out
    except Exception as e:
        logger.exception(f"Ошибка в get_author_books для author_id {author_id}:")
        raise
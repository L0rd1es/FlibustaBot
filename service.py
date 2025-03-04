# service.py

import asyncio
import time
import requests
import re
from bs4 import BeautifulSoup
from config import FLIBUSTA_MIRRORS, RATE_LIMIT_RPS

mirror_state = [
    {"url": m, "penalty": 0} for m in FLIBUSTA_MIRRORS
]
last_request_time = 0.0

async def rate_limit():
    global last_request_time
    interval = 1.0 / RATE_LIMIT_RPS
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
            # Выполняем блокирующий запрос в отдельном потоке
            resp = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                mirror["penalty"] = max(0, mirror["penalty"] - 1)
                return resp.text
            else:
                mirror["penalty"] += 1
                last_exc = Exception(f"HTTP {resp.status_code} {url}")
        except Exception as e:
            mirror["penalty"] += 1
            last_exc = e
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
                # Пример: (628 книг)
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

                # автор(ы)
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
    html = await fetch_url_with_penalty(f"/b/{book_id}", headers={"User-Agent": "Bot/1.0"})
    soup = BeautifulSoup(html, "lxml")

    title = "Неизвестно"
    author = ""
    annotation = ""
    year = None
    cover_url = None
    formats = set()

    # Заголовок книги
    h1 = soup.find("h1", class_="title")
    if h1:
        t = " ".join(h1.get_text().split())
        t = re.sub(r"\([^)]+\)$", "", t).strip()
        title = t

    # Автор – ищем ссылку с href, начинающуюся с "/a/" сразу после заголовка
    if h1:
        a_auth = h1.find_next("a", href=lambda x: x and x.startswith("/a/"))
    else:
        a_auth = soup.find("a", href=lambda x: x and x.startswith("/a/"))
    if a_auth:
        author = " ".join(a_auth.get_text().split())

    # Аннотация
    anno_div = soup.find("div", id="bookannotation")
    if anno_div:
        at = " ".join(anno_div.get_text().split())
        if len(at) > 2000:
            at = at[:2000] + "..."
        annotation = at

    # Год издания – ищем фразу "издание 2016 г." или "издание 2016 года"
    mm = re.search(r"издание\s+(\d{4})\s*(года|г\.)", html, re.IGNORECASE)
    if mm:
        year = mm.group(1)

    # Обложка – ищем <img> с alt="Cover image"
    cov = soup.find("img", alt="Cover image")
    if cov and cov.get("src"):
        raw_src = cov["src"]
        if raw_src.startswith("/"):
            mirror_state.sort(key=lambda x: x["penalty"])
            cover_url = mirror_state[0]["url"] + raw_src
        else:
            cover_url = raw_src

    # Форматы – ищем ссылки, содержащие /b/{book_id} и имя формата
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

    return {
        "id": book_id,
        "title": title,
        "author": author,
        "annotation": annotation,
        "year": year,
        "cover_url": cover_url,
        "formats": list(formats)
    }

async def download_book(book_id: str, fmt: str) -> bytes:
    paths = [f"/b/{book_id}/{fmt}", f"/b/{book_id}/download?format={fmt}"]
    last_exc = None
    for path in paths:
        for attempt in range(2):
            await rate_limit()
            mirror_state.sort(key=lambda x: x["penalty"])
            mirror = mirror_state[0]
            url = mirror["url"] + path
            try:
                resp = await asyncio.to_thread(requests.get, url, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 0:
                    mirror["penalty"] = max(0, mirror["penalty"] - 1)
                    return resp.content
                else:
                    mirror["penalty"] += 1
                    last_exc = Exception(f"Download error {resp.status_code} {url}")
            except Exception as e:
                mirror["penalty"] += 1
                last_exc = e
            await asyncio.sleep(2 ** attempt)
    raise last_exc or Exception("Cannot download book")

async def get_author_books(author_id: str, default_author: str = None) -> list:
    """
    Пытаемся найти книги автора на странице /a/{author_id}.
    Сначала ищем секцию с заголовками ("Книги автора", "Произведения автора", "Найденные книги", "Список произведений").
    Если такая секция не найдена – выполняем fallback, выбирая только ссылки, href которых строго соответствует "/b/<digits>".
    Для имени автора, если default_author передан, используем его.
    """
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
    return out
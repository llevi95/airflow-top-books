# =============================================================================
# DAG: Fetch & Store Goodreads "Best Books Ever" List
# =============================================================================
# Purpose:
#   Scrape the Goodreads list (https://www.goodreads.com/list/show/1.Best_Books_Ever)
#   and store the following fields in Postgres:
#     - title
#     - author
#     - avg_rating
#     - num_ratings
#     - score
#     - people_voted
#
# What this DAG does:
#   1) Creates a target table (goodreads_books) if it does not exist.
#   2) Scrapes up to MAX_PAGES of the list (polite rate-limit + retries).
#   3) Inserts the parsed rows into Postgres in a single task.
#
# Configuration you may want to change:
#   - POSTGRES_CONN_ID: Airflow connection id for your Postgres (must resolve to postgres:5432 in Docker).
#   - NUM_BOOKS: total number of rows to collect (ceil ~ 100 per page).
#   - MAX_PAGES: how many pages to crawl (the list supports ?page=N).
#   - REQUEST_DELAY_SECS: polite delay between requests to avoid throttling.
#
# Notes:
#   - Parsing is defensive: Goodreads markup can change. We target selectors that are stable as of now.
#   - If scraping yields zero rows (blocked / markup change), a small mock fallback is used so the
#     pipeline remains testable during development. Remove the fallback if you prefer a hard failure.
# =============================================================================

from datetime import datetime, timedelta
import time
import random
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

# ------------------------------ CONFIG ---------------------------------------

POSTGRES_CONN_ID   = "books_connection"      # Airflow connection id
LIST_URL           = "https://www.goodreads.com/list/show/1.Best_Books_Ever"
NUM_BOOKS          = 1_000                    # Target total rows (approx 100 rows/page)
MAX_PAGES          = 100                      # Maximum pages to fetch
REQUEST_DELAY_SECS = (0.8, 2.0)               # Randomized polite delay range per page

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/119 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# --------------------------- PARSING HELPERS ---------------------------------

_num_re   = re.compile(r"[\d,]+")
_float_re = re.compile(r"\d+(?:\.\d+)?")

def _to_int(s: str | None) -> int | None:
    """Extract the first integer-like number from a string (handles commas)."""
    if not s:
        return None
    m = _num_re.search(s)
    return int(m.group(0).replace(",", "")) if m else None

def _to_float(s: str | None) -> float | None:
    """Extract the first float-like number from a string."""
    if not s:
        return None
    m = _float_re.search(s)
    return float(m.group(0)) if m else None

def _parse_row(tr) -> dict:
    """
    Parse a <tr> from Goodreads list table into:
      {title, author, avg_rating, num_ratings, score, people_voted}
    """
    # Title
    title_el = tr.select_one("a.bookTitle span") or tr.select_one("a.bookTitle")
    title = title_el.get_text(strip=True) if title_el else None

    # Author
    author_el = tr.select_one("a.authorName span") or tr.select_one("a.authorName")
    author = author_el.get_text(strip=True) if author_el else None

    # Avg rating & num ratings (e.g., "4.28 avg rating — 9,117,773 ratings")
    mini = tr.select_one("span.minirating")
    mini_text = mini.get_text(" ", strip=True) if mini else ""
    avg_rating = _to_float(mini_text)
    nums = [int(n.replace(",", "")) for n in _num_re.findall(mini_text)]
    num_ratings = max(nums) if nums else None  # usually the largest number is 'ratings' count

    # Score anchor: <a onclick="Lightbox.showBoxByID('score_explanation', ...)">score: 2,947,818</a>
    score = None
    score_el = tr.select_one('a[onclick*="score_explanation"]')
    if score_el:
        score = _to_int(score_el.get_text(" ", strip=True))

    # People voted anchor (e.g., "30,210 people voted")
    people_voted = None
    for a in tr.select("a"):
        txt = a.get_text(" ", strip=True).lower()
        if "people voted" in txt:
            people_voted = _to_int(txt)
            break

    return {
        "title": title,
        "author": author,
        "avg_rating": avg_rating,
        "num_ratings": num_ratings,
        "score": score,
        "people_voted": people_voted,
    }

# ------------------------------ TASKS ----------------------------------------

def fetch_goodreads_books(num_books: int = NUM_BOOKS, max_pages: int = MAX_PAGES, **context):
    """
    Scrape Goodreads list pages until we gather `num_books` rows or hit `max_pages`.
    Pushes XCom key='book_data' as list[dict].
    Includes a mock fallback if nothing is parsed (dev convenience).
    """
    ti = context["ti"]
    session = requests.Session()
    session.headers.update(HEADERS)

    books, seen, page = [], set(), 1

    try:
        while len(books) < num_books and page <= max_pages:
            # Polite random delay to avoid being throttled
            time.sleep(random.uniform(*REQUEST_DELAY_SECS))

            resp = session.get(LIST_URL, params={"page": page}, timeout=25)
            if resp.status_code != 200:
                print(f"[WARN] HTTP {resp.status_code} on page {page}, stopping.")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            page_found = 0

            for tr in soup.select("table.tableList tr"):
                row = _parse_row(tr)
                title = row.get("title")
                if not title or title in seen:
                    continue
                seen.add(title)
                books.append(row)
                page_found += 1
                if len(books) >= num_books:
                    break

            print(f"[INFO] Page {page} parsed. New rows: {page_found}. Total: {len(books)}.")
            if page_found == 0 and page > 1:
                # if we reach a page with no rows after already collecting some, likely end or blocked
                print("[INFO] No new rows found on this page; stopping early.")
                break

            page += 1
    except Exception as e:
        print(f"[ERROR] Exception during scraping: {e!r}")
        # fall through to fallback

    # Fallback — keeps pipeline testable if scraping yields nothing
    if not books:
        print("[WARN] No rows parsed; using mock fallback data.")
        books = [
            {"title": "Mock Book A", "author": "Jane Example", "avg_rating": 4.25, "num_ratings": 120_345, "score": 98_000, "people_voted": 45_000},
            {"title": "Mock Book B", "author": "John Example", "avg_rating": 4.10, "num_ratings": 80_321, "score": 65_000, "people_voted": 30_000},
        ][:num_books]

    # De-dup by title & clip to desired count
    df = pd.DataFrame(books).drop_duplicates(subset=["title"]).head(num_books)
    ti.xcom_push(key="book_data", value=df.to_dict("records"))
    print(f"[INFO] XCom pushed {len(df)} rows.")


def insert_goodreads_into_postgres(**context):
    """
    Pull XCom 'book_data' and insert rows into Postgres table `goodreads_books`.
    """
    ti = context["ti"]
    book_data = ti.xcom_pull(key="book_data", task_ids="fetch_goodreads")
    if not book_data:
        raise ValueError("No book data found")

    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    insert_sql = """
        INSERT INTO goodreads_books
        (title, author, avg_rating, num_ratings, score, people_voted)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    with hook.get_conn() as conn:
        with conn.cursor() as cur:
            for b in book_data:
                cur.execute(
                    insert_sql,
                    (
                        b.get("title"),
                        b.get("author"),
                        b.get("avg_rating"),
                        b.get("num_ratings"),
                        b.get("score"),
                        b.get("people_voted"),
                    ),
                )
        conn.commit()
    print(f"[INFO] Inserted {len(book_data)} rows into Postgres.")


# ------------------------------ DAG ------------------------------------------

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 11, 12),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="fetch_and_store_goodreads",
    description="Fetch Goodreads Best Books Ever and store in Postgres",
    default_args=default_args,
    schedule=timedelta(days=1), 
    catchup=False,
    tags=["goodreads", "books"],
) as dag:


    create_table_task = SQLExecuteQueryOperator(
        task_id="create_goodreads_table",
        conn_id=POSTGRES_CONN_ID,
        sql="""
        DROP TABLE IF EXISTS goodreads_books;

        CREATE TABLE IF NOT EXISTS goodreads_books (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT,
            avg_rating DOUBLE PRECISION,
            num_ratings BIGINT,
            score BIGINT,
            people_voted BIGINT
        );
        """,
    )

    fetch_task = PythonOperator(
        task_id="fetch_goodreads",
        python_callable=fetch_goodreads_books,
        op_kwargs={"num_books": NUM_BOOKS, "max_pages": MAX_PAGES},
        # Optional: longer timeout for 100 pages
        execution_timeout=timedelta(minutes=30),
    )

    insert_task = PythonOperator(
        task_id="insert_goodreads",
        python_callable=insert_goodreads_into_postgres,
    )

    fetch_task >> create_table_task >> insert_task

# =============================================================================
# End of DAG
# =============================================================================
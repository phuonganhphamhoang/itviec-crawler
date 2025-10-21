import os
import setuptools  # ✅ Bắt buộc fix cho Python 3.12 thiếu distutils
import time
import random
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

import certifi
import ssl
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from azure.storage.blob import BlobServiceClient

# SSL fix để đảm bảo certifi dùng đúng CA
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

# ---------------- CONFIG ----------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
SELECTOR_SALARY = "div.salary span"
WAIT_TIMEOUT = 20
DEFAULT_PAGES = 3  # số trang muốn crawl
OUT_PATH = Path("jobs_data_public.json")


# ---------------- Helper: start undetected driver ----------------
def init_uc_driver(headless=True):
    import undetected_chromedriver as uc  # ✅ import sau khi setuptools đã load
    options = uc.ChromeOptions()

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument(f"--user-agent={USER_AGENT}")

    driver = uc.Chrome(options=options, use_subprocess=True, version_main=140)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    return driver, wait


# ---------------- Utility: parse posted time ----------------
def parse_posted_time(text):
    if not text:
        return ""
    text = text.lower().strip()
    now = datetime.now()

    m_days = re.search(r"(\d+)\s*day", text)
    if m_days:
        return (now - timedelta(days=int(m_days.group(1)))).strftime("%Y-%m-%d")

    m_hours = re.search(r"(\d+)\s*hour", text)
    if m_hours:
        return (now - timedelta(hours=int(m_hours.group(1)))).strftime("%Y-%m-%d")

    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return ""


# ---------------- Get job list ----------------
def get_job_list(driver, wait, pages=DEFAULT_PAGES):
    all_job_urls = set()
    pattern_valid = re.compile(r"https?://itviec\.com/it-jobs/[^/?#]+-\d+$", re.IGNORECASE)

    for page in range(1, pages + 1):
        url = f"https://itviec.com/it-jobs?page={page}"
        print("Mở:", url)
        driver.get(url)
        time.sleep(random.uniform(2, 4))

        elems = driver.find_elements(By.XPATH, "//*[@data-search--job-selection-job-url-value]")
        for e in elems:
            try:
                slug = e.get_attribute("data-search--job-selection-job-slug-value")
                if slug:
                    candidate = f"https://itviec.com/it-jobs/{slug}".split("?")[0]
                    if pattern_valid.match(candidate):
                        all_job_urls.add(candidate)
            except:
                continue

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/it-jobs/']")
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue
            href_norm = href.split("?")[0].split("#")[0]
            if pattern_valid.match(href_norm):
                all_job_urls.add(href_norm)

        print(f"  -> Đã thu được {len(all_job_urls)} link hợp lệ (tích lũy)")
        time.sleep(random.uniform(1, 2))

    return list(all_job_urls)


# ---------------- Crawl job detail ----------------
def crawl_job(driver, wait, url):
    job = {"url": url}
    try:
        driver.get(url)
        time.sleep(random.uniform(1.5, 2.5))
        job["job_name"] = driver.find_element(By.CSS_SELECTOR, "h1.ipt-xl-6.text-it-black").text.strip()
    except Exception:
        job["job_name"] = ""

    try:
        job["company"] = driver.find_element(By.CSS_SELECTOR, "div.employer-name").text.strip()
    except Exception:
        job["company"] = ""

    try:
        job["address"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey").text.strip()
    except Exception:
        job["address"] = ""

    try:
        job["type"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey.ms-1").text.strip()
    except Exception:
        job["type"] = ""

    try:
        time_text_elem = driver.find_element(By.XPATH, "//span[contains(text(),'Posted')]")
        time_text = time_text_elem.text.strip() if time_text_elem else ""
        job["posted_date"] = parse_posted_time(time_text)
    except Exception:
        job["posted_date"] = ""

    try:
        skills_elements = driver.find_elements(By.CSS_SELECTOR, "div.d-flex.flex-wrap.igap-2 a")
        job["skills"] = [el.text.strip() for el in skills_elements if el.text.strip()]
    except Exception:
        job["skills"] = []

    try:
        job["salary"] = driver.find_element(By.CSS_SELECTOR, SELECTOR_SALARY).text.strip()
    except Exception:
        job["salary"] = ""

    return job


# ---------------- Upload ----------------
def upload_to_blob(file_path, container_name="itviec-data"):
    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    blob_service = BlobServiceClient.from_connection_string(conn_str)
    blob_name = f"jobs_{datetime.now():%Y%m%d_%H%M%S}.json"
    blob_client = blob_service.get_blob_client(container=container_name, blob=blob_name)

    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    print(f"✅ Uploaded {file_path} → Azure Blob ({container_name})")


# ---------------- Main ----------------
def main():
    print("=== itviec crawler (public, no login) ===")
    driver, wait = init_uc_driver(headless=True)

    try:
        job_urls = get_job_list(driver, wait, pages=DEFAULT_PAGES)
        print(f"Thu được {len(job_urls)} job URLs. Bắt đầu crawl chi tiết...")

        jobs = []
        for i, url in enumerate(job_urls, start=1):
            print(f"[{i}/{len(job_urls)}] Crawl: {url}")
            try:
                job = crawl_job(driver, wait, url)
                jobs.append(job)
                with OUT_PATH.open("w", encoding="utf-8") as f:
                    json.dump(jobs, f, ensure_ascii=False, indent=2)
                time.sleep(random.uniform(0.8, 1.6))
            except Exception as e:
                print(f"⚠️ Lỗi khi crawl {url}:", e)

        print(f"✅ Hoàn tất crawl. Lưu kết quả vào {OUT_PATH} (tổng {len(jobs)} jobs).")
        upload_to_blob(OUT_PATH)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

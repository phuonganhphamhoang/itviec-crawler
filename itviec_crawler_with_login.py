#!/usr/bin/env python3
# itviec_crawler_cloud.py
# Full crawler for ITviec, ready for cloud (GitHub Actions / Azure)
# Requirements: pip install undetected-chromedriver selenium webdriver-manager

import os
import json
import time
import random
import re
from datetime import datetime, timedelta

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------- CONFIG ----------------
USER_AGENT = os.environ.get(
    "ITVIEC_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
ITVIEC_COOKIE = os.environ.get("ITVIEC_COOKIE")
OUT_PATH = "jobs_data_with_salary.json"
DEFAULT_PAGES = int(os.environ.get("ITVIEC_PAGES", "1"))
WAIT_TIMEOUT = 20

if not ITVIEC_COOKIE:
    raise ValueError("❌ Thiếu biến môi trường ITVIEC_COOKIE (cookie đăng nhập)")

# ---------------- Init undetected Chrome ----------------
options = uc.ChromeOptions()
options.add_argument(f"--user-agent={USER_AGENT}")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")

driver = uc.Chrome(options=options)
wait = WebDriverWait(driver, WAIT_TIMEOUT)


# ---------------- Helper functions ----------------
def parse_posted_time(text):
    text = text.lower().strip()
    now = datetime.now()
    m_days = re.search(r"(\d+)\s*day", text)
    if m_days:
        days = int(m_days.group(1))
        return (now - timedelta(days=days)).strftime("%Y-%m-%d")
    m_hours = re.search(r"(\d+)\s*hour", text)
    if m_hours:
        hours = int(m_hours.group(1))
        return (now - timedelta(hours=hours)).strftime("%Y-%m-%d")
    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return ""


def get_job_links(pages=DEFAULT_PAGES):
    job_urls = set()
    driver.get("https://itviec.com/it-jobs")
    time.sleep(2)
    driver.add_cookie({"name": "_ITViec_session", "value": ITVIEC_COOKIE, "domain": "itviec.com"})
    driver.get("https://itviec.com/it-jobs")
    time.sleep(3)

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
                        job_urls.add(candidate)
            except Exception:
                continue

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/it-jobs/']")
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if href:
                    href_norm = href.split("?")[0].split("#")[0]
                    if pattern_valid.match(href_norm):
                        job_urls.add(href_norm)
            except Exception:
                continue

        print(f"  -> Tích lũy {len(job_urls)} link hợp lệ")
        time.sleep(random.uniform(1, 2))

    return list(job_urls)


def crawl_job(url):
    job = {"url": url}
    try:
        driver.get(url)
    except Exception:
        return job

    time.sleep(random.uniform(1.5, 2.5))

    # Job name
    try:
        job["job_name"] = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ipt-xl-6.text-it-black"))
        ).text.strip()
    except:
        job["job_name"] = ""

    # Company
    try:
        job["company"] = driver.find_element(By.CSS_SELECTOR, "div.employer-name").text.strip()
    except:
        job["company"] = ""

    # Address
    try:
        job["address"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey").text.strip()
    except:
        job["address"] = ""

    # Type
    try:
        job["type"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey.ms-1").text.strip()
    except:
        job["type"] = ""

    # Posted date
    try:
        posted_elem = driver.find_element(By.XPATH, "//span[contains(text(),'Posted')]")
        job["posted_date"] = parse_posted_time(posted_elem.text.strip() if posted_elem else "")
    except:
        job["posted_date"] = ""

    # Skills
    try:
        skills_elements = driver.find_elements(By.CSS_SELECTOR, "div.d-flex.flex-wrap.igap-2 a")
        job["skills"] = [el.text.strip() for el in skills_elements if el.text.strip()]
    except:
        job["skills"] = []

    # Salary
    try:
        job["salary"] = driver.find_element(By.CSS_SELECTOR, "div.salary span").text.strip()
    except:
        try:
            job["salary"] = driver.find_element(By.CSS_SELECTOR, "div.salary").text.strip()
        except:
            job["salary"] = ""

    # Company info
    job["company_industry"] = ""
    job["company_size"] = ""
    job["working_days"] = ""

    try:
        block = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.imt-4")))
        rows = block.find_elements(By.CSS_SELECTOR, "div.row")
        for row in rows:
            try:
                label = row.find_element(By.CSS_SELECTOR, "div.col.text-dark-grey").text.strip().lower()
                value = row.find_element(By.CSS_SELECTOR, "div.col.text-end.text-it-black").text.strip()
                if "industry" in label:
                    job["company_industry"] = value
                elif "size" in label:
                    job["company_size"] = value
                elif "working day" in label:
                    job["working_days"] = value
            except:
                continue
    except:
        pass

    return job


# ---------------- Main ----------------
def main():
    print("=== ITviec Cloud Crawler ===")
    job_links = get_job_links()
    print(f"✅ Tổng {len(job_links)} job link tìm được")
    jobs = []
    for i, link in enumerate(job_links, 1):
        print(f"[{i}/{len(job_links)}] Crawl: {link}")
        try:
            j = crawl_job(link)
        except Exception as e:
            print("⚠️ Lỗi crawl:", e)
            j = {"url": link}
        jobs.append(j)
        time.sleep(random.uniform(1.5, 3))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)
    print(f"🎉 Hoàn tất! Đã lưu {len(jobs)} job vào {OUT_PATH}")
    driver.quit()


if __name__ == "__main__":
    main()

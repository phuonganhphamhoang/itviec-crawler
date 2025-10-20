import os
import time
import json
import random
import re
from pathlib import Path
from datetime import datetime, timedelta

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------- CONFIG ----------------
USER_AGENT = os.environ.get("ITVIEC_USER_AGENT") or \
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

COOKIE_VALUE = os.environ.get("ITVIEC_COOKIE")
if not COOKIE_VALUE:
    raise ValueError("❌ Thiếu biến môi trường ITVIEC_COOKIE")

WAIT_TIMEOUT = 20
DEFAULT_PAGES = int(os.environ.get("ITVIEC_PAGES", "3"))
OUT_PATH = Path("jobs_data_with_salary.json")

# ---------------- DRIVER ----------------
def init_driver(headless=True):
    options = uc.ChromeOptions()
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    return driver, wait

# ---------------- LOAD COOKIE ----------------
def load_cookie(driver, cookie_value):
    driver.get("https://itviec.com")
    time.sleep(1)
    driver.add_cookie({
        "name": "_ITViec_session",
        "value": cookie_value,
        "domain": "itviec.com"
    })
    driver.get("https://itviec.com/it-jobs")
    time.sleep(2)

# ---------------- PARSE POSTED DATE ----------------
def parse_posted_time(text):
    if not text:
        return ""
    text = text.lower()
    now = datetime.now()
    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    m_days = re.search(r"(\d+)\s*day", text)
    if m_days:
        return (now - timedelta(days=int(m_days.group(1)))).strftime("%Y-%m-%d")
    m_hours = re.search(r"(\d+)\s*hour", text)
    if m_hours:
        return (now - timedelta(hours=int(m_hours.group(1)))).strftime("%Y-%m-%d")
    return ""

# ---------------- GET JOB LIST ----------------
def get_job_list(driver):
    job_links = set()
    for page in range(1, DEFAULT_PAGES + 1):
        driver.get(f"https://itviec.com/it-jobs?page={page}")
        time.sleep(random.uniform(2,4))
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/it-jobs/']")
        for a in anchors:
            href = a.get_attribute("href")
            if href and href.split("/")[-1].split("-")[-1].isdigit():
                job_links.add(href.split("?")[0])
    return list(job_links)

# ---------------- CRAWL JOB DETAIL ----------------
def crawl_job(driver, wait, url):
    job = {"url": url}
    driver.get(url)
    time.sleep(random.uniform(1.5,2.5))
    try: job["job_name"] = driver.find_element(By.CSS_SELECTOR,"h1.ipt-xl-6").text.strip()
    except: job["job_name"] = ""
    try: job["company"] = driver.find_element(By.CSS_SELECTOR,"div.employer-name").text.strip()
    except: job["company"] = ""
    try: job["address"] = driver.find_element(By.CSS_SELECTOR,"span.normal-text.text-rich-grey").text.strip()
    except: job["address"] = ""
    try: job["type"] = driver.find_element(By.CSS_SELECTOR,"span.normal-text.text-rich-grey.ms-1").text.strip()
    except: job["type"] = ""
    try:
        posted_elem = driver.find_element(By.XPATH,"//span[contains(text(),'Posted')]")
        job["posted_date"] = parse_posted_time(posted_elem.text.strip())
    except:
        job["posted_date"] = ""
    try:
        skills = driver.find_elements(By.CSS_SELECTOR,"div.d-flex.flex-wrap.igap-2 a")
        job["skills"] = [s.text.strip() for s in skills if s.text.strip()]
    except: job["skills"] = []
    try: job["salary"] = driver.find_element(By.CSS_SELECTOR,"div.salary").text.strip()
    except: job["salary"] = ""
    
    # Company info
    job["company_industry"] = job["company_size"] = job["working_days"] = ""
    try:
        block = driver.find_element(By.CSS_SELECTOR,"div.imt-4")
        rows = block.find_elements(By.CSS_SELECTOR,"div.row")
        for row in rows:
            try:
                label = row.find_element(By.CSS_SELECTOR,"div.col.text-dark-grey").text.lower()
                value = row.find_element(By.CSS_SELECTOR,"div.col.text-end.text-it-black").text.strip()
                if "industry" in label: job["company_industry"]=value
                elif "size" in label: job["company_size"]=value
                elif "working day" in label: job["working_days"]=value
            except: continue
    except: pass
    return job

# ---------------- MAIN ----------------
def main():
    driver, wait = init_driver(headless=True)
    load_cookie(driver, COOKIE_VALUE)
    print("🔹 Bắt đầu crawl job list...")
    job_links = get_job_list(driver)
    print(f"🔹 Tổng {len(job_links)} job tìm được.")
    jobs = []
    for i, link in enumerate(job_links,1):
        print(f"Crawl {i}/{len(job_links)}: {link}")
        jobs.append(crawl_job(driver, wait, link))
        time.sleep(random.uniform(1.5,2.5))
    with OUT_PATH.open("w",encoding="utf-8") as f:
        json.dump(jobs,f,ensure_ascii=False,indent=2)
    print(f"✅ Hoàn tất! Đã lưu {len(jobs)} job vào {OUT_PATH}")
    driver.quit()

if __name__ == "__main__":
    main()

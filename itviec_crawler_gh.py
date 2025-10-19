import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def parse_posted_time(text):
    from datetime import datetime, timedelta
    if not text:
        return ""
    text = text.lower().strip()
    now = datetime.now()
    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    import re
    m_days = re.search(r"(\d+)\s*day", text)
    if m_days:
        return (now - timedelta(days=int(m_days.group(1)))).strftime("%Y-%m-%d")
    m_hours = re.search(r"(\d+)\s*hour", text)
    if m_hours:
        return (now - timedelta(hours=int(m_hours.group(1)))).strftime("%Y-%m-%d")
    return ""

def main():
    cookie_value = os.environ.get("ITVIEC_COOKIE")
    if not cookie_value:
        raise ValueError("❌ Thiếu biến môi trường ITVIEC_COOKIE")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    driver.get("https://itviec.com")
    time.sleep(2)
    driver.add_cookie({"name": "_ITViec_session", "value": cookie_value, "domain": "itviec.com"})
    driver.get("https://itviec.com/it-jobs")
    time.sleep(3)

    jobs = []

    job_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/it-jobs/']")
    job_urls = []
    for a in job_links:
        href = a.get_attribute("href")
        if href and href not in job_urls:
            job_urls.append(href)

    for url in job_urls[:10]:  # crawl thử 10 job
        driver.get(url)
        time.sleep(2)
        job = {"url": url}
        try:
            job["job_name"] = driver.find_element(By.CSS_SELECTOR, "h1.ipt-xl-6.text-it-black").text.strip()
        except: job["job_name"] = ""
        try:
            job["company"] = driver.find_element(By.CSS_SELECTOR, "div.employer-name").text.strip()
        except: job["company"] = ""
        try:
            job["address"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey").text.strip()
        except: job["address"] = ""
        try:
            job["type"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey.ms-1").text.strip()
        except: job["type"] = ""
        try:
            time_text = driver.find_element(By.XPATH, "//span[contains(text(),'Posted')]").text.strip()
            job["posted_date"] = parse_posted_time(time_text)
        except: job["posted_date"] = ""
        try:
            skills = driver.find_elements(By.CSS_SELECTOR, "div.d-flex.flex-wrap.igap-2 a")
            job["skills"] = [s.text.strip() for s in skills if s.text.strip()]
        except: job["skills"] = []
        try:
            job["salary"] = driver.find_element(By.CSS_SELECTOR, "div.salary span").text.strip()
        except: job["salary"] = ""
        # company details
        job["company_industry"] = ""
        job["company_size"] = ""
        job["working_days"] = ""
        try:
            block = driver.find_element(By.CSS_SELECTOR, "div.imt-4")
            rows = block.find_elements(By.CSS_SELECTOR, "div.row")
            for row in rows:
                try:
                    label = row.find_element(By.CSS_SELECTOR, "div.col.text-dark-grey").text.lower()
                    value = row.find_element(By.CSS_SELECTOR, "div.col.text-end.text-it-black").text.strip()
                    if "industry" in label:
                        job["company_industry"] = value
                    elif "size" in label:
                        job["company_size"] = value
                    elif "working day" in label:
                        job["working_days"] = value
                except: continue
        except: pass
        jobs.append(job)

    driver.quit()

    with open("jobs_data_with_salary.json", "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    print(f"✅ Hoàn tất! Đã lưu {len(jobs)} job.")

if __name__ == "__main__":
    main()

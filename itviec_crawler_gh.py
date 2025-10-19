import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os
import time

# Lấy cookie từ GitHub Secret
COOKIE = os.environ.get("ITVIEC_COOKIE")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
    "Cookie": f"_ITViec_session={COOKIE}"
}

BASE_URL = "https://itviec.com/it-jobs"
DATA_FILE = "jobs.json"

def crawl_jobs():
    print("🔍 Đang bắt đầu cào dữ liệu ITviec...")

    all_jobs = []
    page = 55
    seen_old = False

    while not seen_old:
        url = f"{BASE_URL}?page={page}"
        print(f"➡️  Đang cào trang {page}...")

        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print(f"❌ Lỗi khi tải trang {page}: {res.status_code}")
            break

        soup = BeautifulSoup(res.text, "html.parser")
        job_cards = soup.select("div.job")
        if not job_cards:
            print("✅ Hết trang hoặc không có dữ liệu.")
            break

        for job in job_cards:
            title = job.select_one("h3.title a")
            company = job.select_one("div.company-name a")
            salary = job.select_one("span.salary")
            date = job.select_one("span.date")

            job_data = {
                "title": title.text.strip() if title else None,
                "link": "https://itviec.com" + title["href"] if title else None,
                "company": company.text.strip() if company else None,
                "salary": salary.text.strip() if salary else None,
                "date": date.text.strip() if date else None
            }

            # Kiểm tra job cũ để dừng
            if job_data["date"] and ("day" not in job_data["date"].lower() and "hôm nay" not in job_data["date"].lower()):
                seen_old = True
                print("🛑 Gặp job cũ, dừng cào.")
                break

            all_jobs.append(job_data)

        page += 1
        time.sleep(1)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)

    print(f"💾 Đã lưu {len(all_jobs)} job vào {DATA_FILE}")

if __name__ == "__main__":
    crawl_jobs()

import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def main():
    cookie_value = os.environ.get("ITVIEC_COOKIE")
    if not cookie_value:
        raise ValueError("❌ Thiếu biến môi trường ITVIEC_COOKIE (cookie đăng nhập)")

    # Cấu hình Chrome chạy headless (ẩn)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # Khởi tạo trình duyệt
    driver = webdriver.Chrome(options=options)

    print("🔹 Mở trang ITviec...")
    driver.get("https://itviec.com")
    time.sleep(2)

    # Thêm cookie login
    driver.add_cookie({
        "name": "_ITViec_session",
        "value": cookie_value,
        "domain": "itviec.com"
    })

    # Tải lại trang sau khi thêm cookie
    driver.get("https://itviec.com/it-jobs")
    time.sleep(3)

    print("🔹 Bắt đầu cào dữ liệu...")
    jobs = []

    job_elements = driver.find_elements(By.CSS_SELECTOR, "div.job")
    for job in job_elements[:10]:  # cào thử 10 job đầu
        try:
            title = job.find_element(By.CSS_SELECTOR, "h2 a").text.strip()
            link = job.find_element(By.CSS_SELECTOR, "h2 a").get_attribute("href")
            salary = job.find_element(By.CSS_SELECTOR, ".salary").text.strip() if job.find_elements(By.CSS_SELECTOR, ".salary") else "N/A"
            jobs.append({
                "title": title,
                "link": link,
                "salary": salary
            })
        except Exception:
            pass

    driver.quit()

    # Lưu ra file JSON
    output_file = "jobs_data_with_salary.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    print(f"✅ Hoàn tất! Đã lưu {len(jobs)} job vào {output_file}")

if __name__ == "__main__":
    main()

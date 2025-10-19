"""
itviec_crawler_with_login.py  (undetected-chromedriver + cookie import)

Hướng dẫn ngắn:
1) pip install -U undetected-chromedriver selenium webdriver-manager
2) (Khuyến nghị) Export cookie từ Chrome sau khi bạn login itviec bằng extension (EditThisCookie/Cookie-Editor) -> lưu dưới tên chrome_cookies.json
3) Chạy: python itviec_crawler_with_login.py
"""

import os
import time
import random
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------------- CONFIG ----------------
USER_AGENT = os.environ.get("ITVIEC_USER_AGENT") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
SELECTOR_SALARY = "div.salary span"

EXPORTED_CHROME_COOKIES = Path("chrome_cookies.json")   # recommended
COOKIE_PATH = Path("itviec_cookies.json")               # saved by this script
OUT_PATH = Path("jobs_data_with_salary.json")

WAIT_TIMEOUT = 20
DEFAULT_PAGES = int(os.environ.get("ITVIEC_PAGES", "1"))  # set to 47 if you want full crawl

# ---------------- Helper: start undetected driver ----------------
def init_uc_driver(headless=False):
    options = uc.ChromeOptions()
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # not adding headless by default; undetected headless is tricky
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    return driver, wait

# ---------------- Cookie import/export ----------------
def import_chrome_cookies(driver, cookie_json_path: Path, domain_hint="itviec.com"):
    """
    cookie_json_path: file exported from Chrome extension as JSON array of cookies.
    Returns True if added >=1 cookie.
    """
    if not cookie_json_path.exists():
        return False
    try:
        with cookie_json_path.open("r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not isinstance(cookies, list):
            print("⚠️ chrome_cookies.json không phải list cookie.")
            return False

        # Open domain first
        driver.get(f"https://{domain_hint}")
        time.sleep(1)
        added = 0
        for c in cookies:
            # normalize keys for selenium add_cookie
            cookie = {}
            cookie['name'] = c.get('name') or c.get('Name') or c.get('key')
            cookie['value'] = c.get('value') or c.get('Value') or c.get('val')
            domain = c.get('domain') or c.get('Domain')
            if domain:
                cookie['domain'] = domain
            path = c.get('path') or c.get('Path')
            if path:
                cookie['path'] = path
            if c.get('expiry') is not None:
                try:
                    cookie['expiry'] = int(c.get('expiry'))
                except Exception:
                    pass
            if c.get('secure') is not None:
                cookie['secure'] = bool(c.get('secure'))
            # Selenium may reject SameSite or other unknown fields; so we keep only allowed keys
            try:
                driver.add_cookie(cookie)
                added += 1
            except Exception:
                # try without domain/path
                try:
                    driver.add_cookie({'name': cookie.get('name'), 'value': cookie.get('value')})
                    added += 1
                except Exception:
                    pass
        driver.refresh()
        print(f"✅ Đã thử import {added} cookie từ {cookie_json_path}")
        return added > 0
    except Exception as e:
        print("⚠️ Lỗi import cookie:", e)
        return False

def save_cookies_json(driver, path: Path):
    try:
        cookies = driver.get_cookies()
        with path.open("w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"✅ Đã lưu {len(cookies)} cookie vào {path}")
    except Exception as e:
        print("⚠️ Lỗi khi lưu cookie:", e)

def load_cookies_json(driver, path: Path, domain_hint="itviec.com"):
    """Load cookies previously saved by save_cookies_json (array of dicts)."""
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8") as f:
            cookies = json.load(f)
        driver.get(f"https://{domain_hint}")
        time.sleep(0.5)
        added = 0
        for c in cookies:
            try:
                # use only name+value to avoid invalid keys
                driver.add_cookie({'name': c['name'], 'value': c['value']})
                added += 1
            except Exception:
                try:
                    # fallback generic
                    ck = {}
                    if 'name' in c and 'value' in c:
                        ck = {'name': c['name'], 'value': c['value']}
                        driver.add_cookie(ck)
                        added += 1
                except Exception:
                    pass
        driver.refresh()
        print(f"✅ Đã load {added} cookie từ {path}")
        return added > 0
    except Exception as e:
        print("⚠️ Lỗi khi load cookie:", e)
        return False

# ---------------- Login helper ----------------
def manual_login_and_save(driver, wait):
    """
    Open sign-in page and let user login manually; after Enter saves cookie.
    """
    driver.get("https://itviec.com/sign_in")
    print("➡️ Vui lòng đăng nhập thủ công trong cửa sổ trình duyệt. Sau khi login xong, quay lại terminal và nhấn Enter.")
    input("Nhấn Enter khi đã đăng nhập xong...")
    # detect login (best-effort)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/profile'], img.avatar, .user-menu")), timeout=10)
        print("✅ Đã phát hiện bạn đã đăng nhập (manual).")
    except Exception:
        print("⚠️ Không phát hiện đăng nhập, script sẽ tiếp tục nhưng có thể không có quyền xem salary.")
    # Save cookies
    save_cookies_json(driver, COOKIE_PATH)

# ---------------- Utility: parse posted time ----------------
def parse_posted_time(text):
    """
    Nhận chuỗi 'Posted X days ago' hoặc 'Posted X hours ago' (tiếng Anh).
    Trả về 'YYYY-MM-DD' hoặc '' nếu không parse được.
    """
    if not text:
        return ""
    text = text.lower().strip()
    now = datetime.now()

    # days
    m_days = re.search(r"(\d+)\s*day", text)
    if m_days:
        days = int(m_days.group(1))
        return (now - timedelta(days=days)).strftime("%Y-%m-%d")

    # hours
    m_hours = re.search(r"(\d+)\s*hour", text)
    if m_hours:
        hours = int(m_hours.group(1))
        return (now - timedelta(hours=hours)).strftime("%Y-%m-%d")

    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")

    return ""

# ---------------- Get job list (robust + filter valid job URLs) ----------------
def get_job_list(driver, wait, pages=DEFAULT_PAGES):
    """
    Thu thập link job hợp lệ từ danh sách trang:
    - Lọc bỏ link menu / query không phải chi tiết job
    - Giữ link có dạng /it-jobs/<slug>-<company>-<id>
    """
    all_job_urls = set()
    # regex: ends with -<digits> (ID) to be conservative
    pattern_valid = re.compile(r"https?://itviec\.com/it-jobs/[^/?#]+-\d+$", re.IGNORECASE)

    for page in range(1, pages + 1):
        url = f"https://itviec.com/it-jobs?page={page}"
        print("Mở:", url)
        driver.get(url)
        time.sleep(random.uniform(2, 4))

        # First: try to use data attribute elements (if available)
        elems = driver.find_elements(By.XPATH, "//*[@data-search--job-selection-job-url-value]")
        if elems:
            for e in elems:
                try:
                    slug = e.get_attribute("data-search--job-selection-job-slug-value")
                    if slug:
                        candidate = f"https://itviec.com/it-jobs/{slug}"
                        # normalize: drop query
                        candidate = candidate.split("?")[0]
                        if pattern_valid.match(candidate):
                            all_job_urls.add(candidate)
                except Exception:
                    # stale or other, just skip this element
                    continue

        # Fallback: scan anchor tags with /it-jobs/
        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/it-jobs/']")
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if not href:
                    continue
                # drop query string and fragments
                href_norm = href.split("?")[0].split("#")[0]
                if pattern_valid.match(href_norm):
                    all_job_urls.add(href_norm)
            except Exception:
                continue

        print(f"  -> Đã thu được {len(all_job_urls)} link hợp lệ (tích lũy)")
        time.sleep(random.uniform(1, 2))

    return list(all_job_urls)

# ---------------- Crawl job detail ----------------
def crawl_job(driver, wait, url):
    job = {"url": url}
    try:
        driver.get(url)
    except Exception:
        return job  # return minimal if can't open

    time.sleep(random.uniform(1.5, 2.5))

    # Job name
    try:
        job["job_name"] = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ipt-xl-6.text-it-black"))
        ).text.strip()
    except Exception:
        job["job_name"] = ""

    # Company
    try:
        job["company"] = driver.find_element(By.CSS_SELECTOR, "div.employer-name").text.strip()
    except Exception:
        job["company"] = ""

    # Address
    try:
        job["address"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey").text.strip()
    except Exception:
        job["address"] = ""

    # Type (At office / Hybrid / Remote)
    try:
        job["type"] = driver.find_element(By.CSS_SELECTOR, "span.normal-text.text-rich-grey.ms-1").text.strip()
    except Exception:
        job["type"] = ""

    # Posted date (only date)
    try:
        time_text_elem = driver.find_element(By.XPATH, "//span[contains(text(),'Posted')]")
        time_text = time_text_elem.text.strip() if time_text_elem else ""
        job["posted_date"] = parse_posted_time(time_text)
    except Exception:
        # fallback: sometimes text sits elsewhere
        try:
            txts = driver.find_elements(By.XPATH, "//*[contains(text(),'Posted') or contains(text(),'posted')]")
            found = ""
            for t in txts:
                try:
                    s = t.text.strip()
                    if s:
                        found = s
                        break
                except:
                    continue
            job["posted_date"] = parse_posted_time(found)
        except:
            job["posted_date"] = ""

    # Skills
    try:
        skills_elements = driver.find_elements(By.CSS_SELECTOR, "div.d-flex.flex-wrap.igap-2 a")
        job["skills"] = [el.text.strip() for el in skills_elements if el.text.strip()]
    except Exception:
        job["skills"] = []

    # Salary
    try:
        job["salary"] = driver.find_element(By.CSS_SELECTOR, SELECTOR_SALARY).text.strip()
    except Exception:
        # fallback: sometimes salary text directly in a .salary element
        try:
            el = driver.find_element(By.CSS_SELECTOR, "div.salary")
            job["salary"] = el.text.strip()
        except Exception:
            job["salary"] = ""

    # Company info (flattened)
    job["company_industry"] = ""
    job["company_size"] = ""
    job["working_days"] = ""

    try:
        company_info_block = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.imt-4"))
        )
        rows = company_info_block.find_elements(By.CSS_SELECTOR, "div.row")
        for row in rows:
            try:
                label = row.find_element(By.CSS_SELECTOR, "div.col.text-dark-grey").text.strip().lower()
                value = row.find_element(By.CSS_SELECTOR, "div.col.text-end.text-it-black").text.strip()
                if "industry" in label:
                    job["company_industry"] = value
                elif "size" in label:
                    job["company_size"] = value
                elif "working day" in label or "working days" in label:
                    job["working_days"] = value
            except Exception:
                continue
    except Exception:
        # no company block found
        pass

    return job

# ---------------- Main ----------------
def main():
    print("=== itviec crawler (posted_date only) ===")
    driver, wait = init_uc_driver(headless=False)

    try:
        # 1) Try import exported Chrome cookies first
        imported = False
        if EXPORTED_CHROME_COOKIES.exists():
            print("Thấy file chrome_cookies.json — sẽ import cookies từ Chrome thật (nên dùng nếu itviec verify liên tục).")
            try:
                imported = import_chrome_cookies(driver, EXPORTED_CHROME_COOKIES, domain_hint="itviec.com")
            except Exception as e:
                print("⚠️ Import chrome cookie failed:", e)

        # 2) Else try load cookie saved from previous runs of this script
        loaded = False
        if not imported and COOKIE_PATH.exists():
            try:
                loaded = load_cookies_json(driver, COOKIE_PATH, domain_hint="itviec.com")
            except Exception as e:
                print("⚠️ Load saved cookie failed:", e)

        # 3) If nothing, open manual login (with undetected driver) so you can login and we save cookie
        if not imported and not loaded:
            print("Không tìm cookie, sẽ yêu cầu bạn login thủ công trong browser mở ra.")
            manual_login_and_save(driver, wait)
        else:
            # verify logged in by checking profile link
            try:
                time.sleep(1)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/profile'], img.avatar, .user-menu")), timeout=5)
                print("✅ Session đã có quyền (đã đăng nhập).")
            except Exception:
                print("⚠️ Không detect session logged-in ngay lập tức. Nếu trình duyệt yêu cầu verify/captcha, xử lý thủ công trong cửa sổ trình duyệt.")
                input("Sau khi bạn xử lý verify và login, nhấn Enter để tiếp tục...")

        # now try to grab job list
        pages_to_crawl = DEFAULT_PAGES
        print(f"📥 Bắt đầu lấy link từ {pages_to_crawl} trang.")
        job_links = get_job_list(driver, wait, pages=pages_to_crawl)
        print("Tìm được job links:", len(job_links))
        if not job_links:
            print("⚠️ Không thấy job nào — mở debug_page_N.html để xem trang trả về (có thể còn block Cloudflare).")

        jobs = []
        for i, link in enumerate(job_links, 1):
            print(f"[{i}/{len(job_links)}] Crawl: {link}")
            try:
                j = crawl_job(driver, wait, link)
            except Exception as e:
                print("⚠️ Lỗi khi crawl chi tiết:", e)
                j = {"url": link}
            jobs.append(j)
            time.sleep(random.uniform(1.5, 3))

        # save output
        with OUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        print("🎉 Đã lưu kết quả vào", OUT_PATH)

    finally:
        # safe quit
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()

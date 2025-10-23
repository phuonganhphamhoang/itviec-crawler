import asyncio
from playwright.async_api import async_playwright
import json, re, random, os
from datetime import datetime, timedelta
from pathlib import Path
from azure.storage.blob import BlobServiceClient

OUT_PATH = Path("jobs_data_public.json")
DEFAULT_PAGES = 3

async def parse_posted_time(text):
    if not text:
        return ""
    text = text.lower().strip()
    now = datetime.now()
    if "today" in text:
        return now.strftime("%Y-%m-%d")
    if "yesterday" in text:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*(day|hour)", text)
    if m:
        v, u = int(m.group(1)), m.group(2)
        delta = timedelta(days=v) if u == "day" else timedelta(hours=v)
        return (now - delta).strftime("%Y-%m-%d")
    return ""

async def crawl_itviec():
    print("=== itviec crawler (Playwright, Enhanced Debug) ===")
    jobs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080",
            ],
        )
        
        # Thêm user agent để tránh bị detect là bot
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        all_job_links = set()

        for page_num in range(1, DEFAULT_PAGES + 1):
            url = f"https://itviec.com/it-jobs?page={page_num}"
            print(f"\n🌐 Mở trang: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                
                # Đợi cho job cards xuất hiện (thử nhiều selector)
                print("⏳ Đợi job cards load...")
                try:
                    # Thử selector mới hơn
                    await page.wait_for_selector("a[href*='/it-jobs/']", timeout=15000)
                    print("✅ Job cards đã xuất hiện")
                except:
                    print("⚠️ Không tìm thấy job cards với selector mặc định")
                
                # Scroll để trigger lazy loading
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                
                # DEBUG: Lưu screenshot
                await page.screenshot(path=f"debug_page_{page_num}.png")
                print(f"📸 Đã lưu screenshot: debug_page_{page_num}.png")
                
                # Phương pháp 1: Tìm tất cả links chứa /it-jobs/
                job_links = await page.query_selector_all("a[href*='/it-jobs/']")
                print(f"🔍 Tìm thấy {len(job_links)} links chứa /it-jobs/")
                
                for link_elem in job_links:
                    href = await link_elem.get_attribute("href")
                    if href:
                        # Chuẩn hóa URL
                        if href.startswith("/"):
                            href = f"https://itviec.com{href}"
                        # Lọc chỉ lấy job detail pages (có slug-number pattern)
                        if re.search(r'/it-jobs/[a-z0-9-]+-\d+', href):
                            # Loại bỏ query params
                            clean_url = href.split("?")[0].split("#")[0]
                            all_job_links.add(clean_url)
                
                # Phương pháp 2: Parse từ JSON trong HTML
                content = await page.content()
                json_matches = re.findall(r'"slug":"([^"]+?)"', content)
                for slug in json_matches:
                    if re.match(r'^[a-z0-9-]+-\d+$', slug):
                        all_job_links.add(f"https://itviec.com/it-jobs/{slug}")
                
                print(f"  ✅ Tổng tích lũy: {len(all_job_links)} job links")
                
                # DEBUG: In ra 3 links đầu tiên
                if all_job_links:
                    print(f"  📋 Mẫu links: {list(all_job_links)[:3]}")
                
                await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"⚠️ Lỗi load {url}: {e}")
                # Lưu HTML để debug
                try:
                    html = await page.content()
                    Path(f"debug_page_{page_num}.html").write_text(html, encoding="utf-8")
                    print(f"💾 Đã lưu HTML: debug_page_{page_num}.html")
                except:
                    pass
                continue

        print(f"\n📄 Tổng {len(all_job_links)} job URLs. Bắt đầu crawl chi tiết...")

        if len(all_job_links) == 0:
            print("❌ KHÔNG TÌM THẤY JOB NÀO! Kiểm tra:")
            print("  1. Website có đổi cấu trúc?")
            print("  2. Bị block bởi Cloudflare/WAF?")
            print("  3. Xem file debug_page_*.png và debug_page_*.html")
            await browser.close()
            return

        for i, link in enumerate(list(all_job_links)[:20], start=1):  # Giới hạn 20 jobs để test
            try:
                print(f"\n[{i}/{min(20, len(all_job_links))}] 🔍 {link}")
                await page.goto(link, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)

                job = {
                    "url": link,
                    "job_name": "",
                    "company": "",
                    "address": "",
                    "type": "",
                    "salary": "",
                    "skills": [],
                    "posted_date": "",
                }

                # Thử nhiều selector cho job name
                for selector in ["h1", "h1.ipt-xl-6", "[class*='job-title']"]:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            job["job_name"] = (await elem.text_content()).strip()
                            if job["job_name"]:
                                break
                    except:
                        pass

                # Company
                for selector in ["div.employer-name", "[class*='company']", "[class*='employer']"]:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            job["company"] = (await elem.text_content()).strip()
                            if job["company"]:
                                break
                    except:
                        pass

                # Address
                for selector in ["span.normal-text.text-rich-grey", "[class*='address']", "[class*='location']"]:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            job["address"] = (await elem.text_content()).strip()
                            if job["address"]:
                                break
                    except:
                        pass

                # Salary
                for selector in ["div.salary span", "[class*='salary']"]:
                    try:
                        elem = await page.query_selector(selector)
                        if elem:
                            job["salary"] = (await elem.text_content()).strip()
                            if job["salary"]:
                                break
                    except:
                        pass

                # Skills
                for selector in ["div.d-flex.flex-wrap.igap-2 a", "[class*='skill'] a", "[class*='tag']"]:
                    try:
                        skills = await page.query_selector_all(selector)
                        if skills:
                            job["skills"] = [
                                (await s.text_content()).strip() 
                                for s in skills 
                                if await s.text_content()
                            ]
                            if job["skills"]:
                                break
                    except:
                        pass

                # Posted date
                try:
                    time_elem = await page.query_selector("//span[contains(text(),'Posted')]")
                    if time_elem:
                        time_text = (await time_elem.text_content()) or ""
                        job["posted_date"] = await parse_posted_time(time_text)
                except:
                    pass

                jobs.append(job)
                print(f"  ✅ {job['job_name'][:60] if job['job_name'] else 'No title'}")
                await page.wait_for_timeout(random.uniform(1500, 3000))
                
            except Exception as e:
                print(f"  ⚠️ Lỗi crawl {link}: {e}")

        await browser.close()

    OUT_PATH.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Hoàn tất crawl {len(jobs)} jobs. Lưu {OUT_PATH}")
    
    if jobs:
        upload_to_blob(OUT_PATH)

def upload_to_blob(file_path, container_name="itviec-data"):
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        print("⚠️ AZURE_STORAGE_CONNECTION_STRING not set, skip upload")
        return

    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        blob_client = blob_service.get_blob_client(
            container=container_name,
            blob=f"jobs_{datetime.now():%Y%m%d_%H%M%S}.json",
        )

        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        print(f"✅ Uploaded {file_path} → Azure Blob ({container_name})")
    except Exception as e:
        print(f"⚠️ Lỗi upload blob: {e}")

if __name__ == "__main__":
    asyncio.run(crawl_itviec())
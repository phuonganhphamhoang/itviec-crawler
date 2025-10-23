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
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        all_job_links = set()

        # ==== Crawl danh sách link ====
        for page_num in range(1, DEFAULT_PAGES + 1):
            url = f"https://itviec.com/it-jobs?page={page_num}"
            print(f"\n🌐 Mở trang: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=90000)
                await page.wait_for_selector("a[href*='/it-jobs/']", timeout=15000)

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)

                job_links = await page.query_selector_all("a[href*='/it-jobs/']")
                for link_elem in job_links:
                    href = await link_elem.get_attribute("href")
                    if href:
                        if href.startswith("/"):
                            href = f"https://itviec.com{href}"
                        if re.search(r"/it-jobs/[a-z0-9-]+-\d+", href):
                            clean_url = href.split("?")[0].split("#")[0]
                            all_job_links.add(clean_url)

                print(f"  ✅ Tích lũy: {len(all_job_links)} links")
                await page.wait_for_timeout(2000)

            except Exception as e:
                print(f"⚠️ Lỗi load {url}: {e}")
                continue

        print(f"\n📄 Tổng {len(all_job_links)} job URLs. Bắt đầu crawl chi tiết...")

        # ==== Crawl chi tiết ====
        for i, link in enumerate(list(all_job_links)[:20], start=1):
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
                    "company_industry": "",
                    "company_size": "",
                    "working_days": "",
                }

                # Job name
                for selector in ["h1", "h1.ipt-xl-6", "[class*='job-title']"]:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        if text:
                            job["job_name"] = text
                            break

                # Company
                for selector in ["div.employer-name", "[class*='company']", "[class*='employer']"]:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        if text:
                            job["company"] = text
                            break

                # Address
                for selector in ["span.normal-text.text-rich-grey", "[class*='address']", "[class*='location']"]:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        if text:
                            job["address"] = text
                            break

                # Type (At office / Remote / Hybrid)
                for selector in ["span.normal-text.text-rich-grey.ms-1", "[class*='job-type']", "[class*='remote']"]:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        if text:
                            job["type"] = text
                            break

                # Salary
                for selector in ["div.salary span", "div.salary", "[class*='salary']"]:
                    elem = await page.query_selector(selector)
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        if text:
                            job["salary"] = text
                            break

                # Skills
                for selector in ["div.d-flex.flex-wrap.igap-2 a", "[class*='skill'] a", "[class*='tag']"]:
                    skill_elems = await page.query_selector_all(selector)
                    skills = []
                    for s in skill_elems:
                        t = (await s.text_content() or "").strip()
                        if t:
                            skills.append(t)
                    if skills:
                        job["skills"] = skills
                        break

                # Posted date
                try:
                    elem = await page.query_selector("xpath=//span[contains(text(),'Posted')]")
                    if elem:
                        text = (await elem.text_content() or "").strip()
                        job["posted_date"] = parse_posted_time(text)
                except:
                    pass

                # Company info: industry, size, working days
                try:
                    block = await page.query_selector("div.imt-4")
                    if block:
                        rows = await block.query_selector_all("div.row")
                        for row in rows:
                            try:
                                label_elem = await row.query_selector("div.col.text-dark-grey")
                                value_elem = await row.query_selector("div.col.text-end.text-it-black")
                                if not label_elem or not value_elem:
                                    continue
                                label = ((await label_elem.text_content()) or "").lower()
                                value = (await value_elem.text_content()) or ""
                                if "industry" in label:
                                    job["company_industry"] = value.strip()
                                elif "size" in label:
                                    job["company_size"] = value.strip()
                                elif "working day" in label or "working days" in label:
                                    job["working_days"] = value.strip()
                            except:
                                continue
                except:
                    pass

                jobs.append(job)
                print(f"  ✅ {job['job_name'] or 'No title'}")

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

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
    print("=== itviec crawler (Playwright, GitHub Runner version) ===")
    jobs = []
    pattern_valid = re.compile(r"https?://itviec\.com/it-jobs/[^/?#]+-\d+$", re.I)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})

        all_job_links = set()

        for page_num in range(1, DEFAULT_PAGES + 1):
            url = f"https://itviec.com/it-jobs?page={page_num}"
            print(f"🌐 Mở trang: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"⚠️ Lỗi load {url}: {e}")
                continue

            job_cards = await page.query_selector_all("[data-search--job-selection-job-slug-value]")
            if job_cards:
                for c in job_cards:
                    slug = await c.get_attribute("data-search--job-selection-job-slug-value")
                    if slug:
                        link = f"https://itviec.com/it-jobs/{slug}".split("?")[0]
                        all_job_links.add(link)

            anchors = await page.query_selector_all("a[href*='/it-jobs/']")
            for a in anchors:
                href = await a.get_attribute("href")
                if href:
                    link = href.split("?")[0].split("#")[0]
                    if pattern_valid.match(link):
                        all_job_links.add(link)

            print(f"  ✅ {len(all_job_links)} link hợp lệ (tích lũy)")
            await page.wait_for_timeout(1500)


        print(f"📄 Tổng {len(all_job_links)} job URLs. Bắt đầu crawl chi tiết...")

        for i, link in enumerate(all_job_links, start=1):
            try:
                await page.goto(link, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(2000)

                job = {
                    "url": link,
                    "job_name": (await page.text_content("h1.ipt-xl-6.text-it-black")) or "",
                    "company": (await page.text_content("div.employer-name")) or "",
                    "address": (await page.text_content("span.normal-text.text-rich-grey")) or "",
                    "type": (await page.text_content("span.normal-text.text-rich-grey.ms-1")) or "",
                    "salary": (await page.text_content("div.salary span")) or "",
                    "skills": [],
                    "posted_date": "",
                }

                skills = await page.query_selector_all("div.d-flex.flex-wrap.igap-2 a")
                job["skills"] = [(await s.text_content()).strip() for s in skills if await s.text_content()]
                time_elem = await page.query_selector("//span[contains(text(),'Posted')]")
                if time_elem:
                    time_text = (await time_elem.text_content()) or ""
                    job["posted_date"] = await parse_posted_time(time_text)

                jobs.append(job)
                print(f"[{i}/{len(all_job_links)}] ✅ {job['job_name'][:50]}")
                await page.wait_for_timeout(random.uniform(800, 1600))
            except Exception as e:
                print(f"⚠️ Lỗi crawl {link}: {e}")

        await browser.close()

    OUT_PATH.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Hoàn tất crawl {len(jobs)} jobs. Lưu {OUT_PATH}")
    upload_to_blob(OUT_PATH)

def upload_to_blob(file_path, container_name="itviec-data"):
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        raise EnvironmentError("AZURE_STORAGE_CONNECTION_STRING not set")

    blob_service = BlobServiceClient.from_connection_string(conn_str)
    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=f"jobs_{datetime.now():%Y%m%d_%H%M%S}.json",
    )

    with open(file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    print(f"✅ Uploaded {file_path} → Azure Blob ({container_name})")

if __name__ == "__main__":
    asyncio.run(crawl_itviec())


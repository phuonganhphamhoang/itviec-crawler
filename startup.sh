#!/bin/bash
set -e

echo "=============================="
echo "🚀 Starting ITviec Crawler App"
echo "=============================="

# Install pip if not present
if ! command -v pip &> /dev/null; then
  echo "⚙️ pip not found — installing..."
  apt-get update -y && apt-get install -y python3-pip
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Playwright Chromium
echo "🧩 Installing Playwright Chromium..."
python -m playwright install --with-deps chromium

# Run the crawler
echo "🏃 Running crawler..."
python itviec_crawler_cloud.py

echo "✅ Done."

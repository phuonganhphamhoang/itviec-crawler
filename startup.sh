#!/bin/bash
echo "Installing Playwright Chromium..."
python -m playwright install --with-deps chromium
echo "Running crawler..."
python itviec_crawler_cloud.py

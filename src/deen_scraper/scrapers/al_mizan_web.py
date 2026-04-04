#!/usr/bin/env python3
"""
Scraper for al-mizan.org PDFs
Downloads PDFs from the website and saves them locally
"""

import os
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
import time

BASE_URL = "https://www.al-mizan.org"
OUTPUT_DIR = "../datasets/al-mizan/pdfs"

def setup_directories():
    """Create output directory if it doesn't exist"""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {OUTPUT_DIR}")

def find_pdf_links(url, base_url=BASE_URL):
    """
    Find all PDF links on a given page
    Returns list of (pdf_url, filename) tuples
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Error fetching {url}: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    pdf_links = []
    
    # Find all links that point to PDFs
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Handle relative and absolute URLs
        full_url = urljoin(base_url, href)
        
        # Check if it's a PDF link
        if href.lower().endswith(".pdf") or "pdf" in href.lower():
            filename = os.path.basename(urlparse(full_url).path)
            if not filename:
                # Generate filename from URL
                filename = f"document_{len(pdf_links) + 1}.pdf"
            pdf_links.append((full_url, filename))
    
    # Also check for embedded PDFs or direct PDF links in iframes/objects
    for iframe in soup.find_all(["iframe", "embed", "object"]):
        src = iframe.get("src") or iframe.get("data")
        if src and (src.lower().endswith(".pdf") or "pdf" in src.lower()):
            full_url = urljoin(base_url, src)
            filename = os.path.basename(urlparse(full_url).path)
            if not filename:
                filename = f"document_{len(pdf_links) + 1}.pdf"
            pdf_links.append((full_url, filename))
    
    return pdf_links

def download_pdf(pdf_url, output_path, headers=None):
    """Download a PDF file"""
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    try:
        response = requests.get(pdf_url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get("content-length", 0))
        
        with open(output_path, "wb") as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
        
        return True
    except requests.RequestException as e:
        print(f"❌ Error downloading {pdf_url}: {e}")
        return False

def scrape_al_mizan_pdfs(start_urls=None):
    """
    Main scraping function
    start_urls: List of URLs to start scraping from. If None, uses default pages
    """
    setup_directories()
    
    # Default pages to check if no URLs provided
    if start_urls is None:
        start_urls = [
            BASE_URL,
            f"{BASE_URL}/tafsir",
            f"{BASE_URL}/volumes",
            f"{BASE_URL}/downloads",
            f"{BASE_URL}/pdfs",
        ]
    
    all_pdfs = set()  # Use set to avoid duplicates
    
    print("🔍 Searching for PDF links...")
    for url in start_urls:
        print(f"  Checking {url}...")
        pdfs = find_pdf_links(url)
        all_pdfs.update(pdfs)
        time.sleep(1)  # Be respectful with requests
    
    print(f"\n📚 Found {len(all_pdfs)} PDF(s)")
    
    # Download PDFs
    downloaded = 0
    skipped = 0
    
    for pdf_url, filename in tqdm(all_pdfs, desc="📥 Downloading PDFs"):
        output_path = Path(OUTPUT_DIR) / filename
        
        # Skip if already downloaded
        if output_path.exists():
            print(f"⏭️  Skipping {filename} (already exists)")
            skipped += 1
            continue
        
        print(f"⬇️  Downloading {filename}...")
        if download_pdf(pdf_url, output_path):
            downloaded += 1
            print(f"✅ Downloaded {filename}")
        else:
            print(f"❌ Failed to download {filename}")
        
        time.sleep(1)  # Be respectful with requests
    
    print(f"\n✅ Download complete!")
    print(f"   Downloaded: {downloaded}")
    print(f"   Skipped: {skipped}")
    print(f"   Total: {len(all_pdfs)}")
    
    return list(all_pdfs)

if __name__ == "__main__":
    # You can specify custom URLs to scrape
    # For example, if you know the specific pages with PDFs:
    # custom_urls = ["https://www.al-mizan.org/specific-page"]
    # scrape_al_mizan_pdfs(custom_urls)
    
    scrape_al_mizan_pdfs()


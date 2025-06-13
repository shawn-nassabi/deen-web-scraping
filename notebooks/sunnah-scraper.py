import re

import requests
from bs4 import BeautifulSoup
import csv
import os

def scrape_book(book: str, book_number: int):
    base_url = f"https://sunnah.com/{book}/{book_number}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(base_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to retrieve book {book_number}. Status code: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    book_title_elem = soup.find("div", class_="book_page_english_name")
    book_title = book_title_elem.text.strip() if book_title_elem else f"Book {book_number}"
    hadith_blocks = soup.find_all("div", class_="actualHadithContainer")

    hadiths = []

    for block in hadith_blocks:
        arabic = block.find("div", class_="arabic_hadith_full")
        english = block.find("div", class_="text_details")
        reference_table = block.find("table", class_="hadith_reference")

        arabic_text = arabic.text.strip() if arabic else ""
        english_text = english.text.strip() if english else ""

        reference = ""
        in_book_reference = ""
        hadith_url = ""

        if reference_table:
            rows = reference_table.find_all("tr")

            if len(rows) >= 2:
                # Row 1: Canonical Reference and URL (e.g., Sahih al-Bukhari 1, /bukhari:1)
                ref_link = rows[0].find("a")
                if ref_link:
                    reference = ref_link.text.strip()
                    hadith_url = f"https://sunnah.com{ref_link['href']}"

                # Row 2: In-book reference
                inbook_td = rows[1].find_all("td")
                if len(inbook_td) >= 2:
                    in_book_reference = inbook_td[1].text.replace(":", "").strip()

        hadiths.append([
            f"Book {book_number} - {book_title}",
            arabic_text,
            english_text,
            reference,
            in_book_reference,
            hadith_url
        ])

    return hadiths

def save_to_csv(hadiths, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["book_number", "arabic", "english", "reference", "in_book_reference", "hadith_url"])
        writer.writerows(hadiths)


def extract_book_title(reference: str) -> str:
    # Remove trailing number and whitespace, then replace spaces with underscores
    title = re.sub(r"\s*\d+$", "", reference.strip())
    return title.replace(" ", "_")

def scrape_all_books(book: str):
    all_hadiths = []
    book_number = 1

    while True:
        print(f"🔎 Scraping {book} book {book_number}...")
        hadiths = scrape_book(book, book_number)
        if hadiths is None:
            print(f"✅ Finished at {book}/{book_number - 1}")
            break
        all_hadiths.extend(hadiths)
        book_number += 1

    raw_reference = all_hadiths[1][3]  # 'reference' column
    book_title_slug = extract_book_title(raw_reference)
    output_path = os.path.join("..", "datasets", f"{book_title_slug}_all_books.csv")
    save_to_csv(all_hadiths, output_path)
    print(f"📁 Saved {len(all_hadiths)} hadiths to {output_path}")

if __name__ == "__main__":
    scrape_all_books("bukhari") # Change "bukhari" to the desired book slug
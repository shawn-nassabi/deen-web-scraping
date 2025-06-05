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
        return []

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

if __name__ == "__main__":
    data = scrape_book("bukhari", 1)
    output_path = os.path.join("..", "datasets", "sahih_bukhari_book_1.csv")
    save_to_csv(data, output_path)
    print(f"✅ Saved {len(data)} hadiths to {output_path}")
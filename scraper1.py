import json
import re
from playwright.sync_api import sync_playwright

def scrape_olx_list():
    with sync_playwright() as p:
        # Uruchamiamy przeglądarkę z natywną flagą ukrywającą automatyzację
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        
        # Wstrzykujemy skrypt ukrywający obecność bota
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        target_url = "https://www.olx.pl/oferty/q-playstation-5/?search%5Bfilter_float_price:from%5D=900&search%5Bfilter_float_price:to%5D=1300&search%5Bfilter_enum_version%5D%5B0%5D=playstation5"

        print("Otwieram listę wyszukiwania...")
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Akceptacja ciasteczek
        try:
            cookie_btn = page.locator('button[id="onetrust-accept-btn-handler"]')
            if cookie_btn.is_visible(timeout=3000):
                cookie_btn.click()
                print("Zaakceptowano ciasteczka.")
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # "Human scroll" - przewijamy stronę w dół, aby załadować wszystkie elementy
        print("Przewijam listę ofert...")
        for _ in range(5):
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(400)

        print("Pobieram dane...")
        results = []
        
        # Pobieramy wszystkie główne kontenery kart ofert
        cards = page.locator('div[data-cy="l-card"]').all()
        
        for card in cards:
            try:
                # 1. Wyciąganie linku
                link_elem = card.locator('a').first
                if link_elem.count() == 0:
                    continue
                
                href = link_elem.get_attribute('href')
                if not href:
                    continue
                if not href.startswith("http"):
                    href = "https://www.olx.pl" + href

                # 2. Wyciąganie tytułu (szerszy zakres poszukiwań: h4, h5, h6)
                title_elem = card.locator('h6, h4, h5').first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Brak tytułu"

                # Niezawodny fallback: Jeśli OLX znowu zmienił tagi, wyciągamy tytuł z linku!
                if title == "Brak tytułu" and "/d/oferta/" in href:
                    match = re.search(r'/d/oferta/([a-z0-9\-]+)-CID', href)
                    if match:
                        title = match.group(1).replace('-', ' ').capitalize()

                # 3. Flaga negocjacji (sprawdzamy cały tekst karty, żeby nic nie umknęło)
                card_text = card.inner_text()
                is_negotiable = "do negocjacji" in card_text.lower()

                # 4. Wyciąganie ceny
                price_elem = card.locator('p[data-testid="ad-price"]').first
                price_text = price_elem.inner_text() if price_elem.count() > 0 else "Brak ceny"
                # Czysta kwota
                price = price_text.split('\n')[0].strip() if '\n' in price_text else price_text.strip()
                price = price.replace("do negocjacji", "").strip() # Zabezpieczenie

                # 5. Wyciąganie lokalizacji
                loc_elem = card.locator('p[data-testid="location-date"]').first
                location_text = loc_elem.inner_text() if loc_elem.count() > 0 else "Brak lokalizacji"
                location = location_text.split('-')[0].strip() if '-' in location_text else location_text.strip()

                results.append({
                    "title": title,
                    "price": price,
                    "negotiable": is_negotiable,
                    "location": location,
                    "url": href
                })
            except Exception as e:
                print(f"Zignorowano niepełną kartę ze względu na błąd parsowania.")

        browser.close()

        with open('playstation5_szybka_lista.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)

        print(f"\nSukces! Pomyślnie zebrano {len(results)} ofert. Zapisano do pliku.")

if __name__ == "__main__":
    scrape_olx_list()
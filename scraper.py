import os
import re
import urllib.parse
import requests
from playwright.sync_api import sync_playwright

# --- KONFIGURACJA ZMIENNYCH ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

def send_telegram(offer):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Formatowanie flagi negocjacji dla wiadomości
    neg_text = " (Do negocjacji)" if offer['negotiable'] else ""
    
    msg = (
        f"🔔 <b>NOWA OFERTA PS5!</b>\n\n"
        f"💰 {offer['price']}{neg_text}\n"
        f"📍 {offer['location']} | 🕒 {offer['publish_date']}\n"
        f"📝 {offer['title']}\n\n"
        f"🔗 <a href='{offer['url']}'>Kliknij, aby zobaczyć</a>"
    )
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

def is_new_offer(offer_url):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {"url": f"eq.{offer_url}", "select": "id"}
    response = requests.get(f"{SUPABASE_URL}/rest/v1/offers", headers=headers, params=params)
    return len(response.json()) == 0

def save_offer(offer):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    requests.post(f"{SUPABASE_URL}/rest/v1/offers", headers=headers, json=offer)

def scrape():
    # Zabezpieczenie: Sprawdzamy czy klucz na pewno się załadował z GitHuba
    if not SCRAPERAPI_KEY:
        print("BŁĄD KRYTYCZNY: Brak klucza SCRAPERAPI_KEY. Sprawdź plik .yml!")
        return

    with sync_playwright() as p:
        # CZYSTE URUCHOMIENIE - bez parametru proxy
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        target_url = "https://www.olx.pl/oferty/q-playstation-5/?search%5Bfilter_float_price:from%5D=900&search%5Bfilter_float_price:to%5D=1300&search%5Bfilter_enum_version%5D%5B0%5D=playstation5"
        
        # MAGIA SCRAPERAPI: Kodujemy URL OLXa i doklejamy go do API ScraperAPI z flagą render=true
        encoded_url = urllib.parse.quote(target_url)
        scraper_url = f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={encoded_url}&render=true"
        
        print("Otwieram ScraperAPI, proszę czekać...")
        
        # WAŻNE: Zwiększamy timeout do 60 sekund, bo ScraperAPI potrzebuje chwili na obejście zabezpieczeń
        page.goto(scraper_url, wait_until="domcontentloaded", timeout=60000)
        
        print(f"Tytuł załadowanej strony: {page.title()}")
        
        # Pętla scrollująca
        for _ in range(3):
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(400)
        
        cards = page.locator('div[data-cy="l-card"]').all()
        print(f"Znaleziono {len(cards)} kart z ofertami.")
        
        # Sprawdzamy tylko top 10 ogłoszeń z góry (przy uruchamianiu co godzinę to z zapasem wystarczy)
        for card in cards[:10]: 
            try:
                # 1. Wyciąganie i czyszczenie linku
                link_elem = card.locator('a').first
                if link_elem.count() == 0: continue
                
                href = link_elem.get_attribute('href')
                if not href.startswith("http"): href = "https://www.olx.pl" + href
                clean_url = href.split('#')[0].split('?')[0] # Usuwamy parametry śledzenia

                # Jeśli oferta jest w bazie, pomiń resztę logiki (oszczędność czasu)
                if not is_new_offer(clean_url):
                    continue

                # 2. Tytuł z fallbackiem
                title_elem = card.locator('h6, h4, h5').first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Brak tytułu"
                
                if title == "Brak tytułu" and "/d/oferta/" in clean_url:
                    match = re.search(r'/d/oferta/([a-z0-9\-]+)-CID', clean_url)
                    if match:
                        title = match.group(1).replace('-', ' ').capitalize()

                # 3. Flaga negocjacji
                card_text = card.inner_text()
                is_negotiable = "do negocjacji" in card_text.lower()

                # 4. Cena
                price_elem = card.locator('p[data-testid="ad-price"]').first
                price_text = price_elem.inner_text() if price_elem.count() > 0 else "Brak ceny"
                price = price_text.split('\n')[0].strip() if '\n' in price_text else price_text.strip()
                price = price.replace("do negocjacji", "").strip()

                # 5. Lokalizacja i Data Publikacji
                loc_elem = card.locator('p[data-testid="location-date"]').first
                loc_date_text = loc_elem.inner_text() if loc_elem.count() > 0 else "Brak lokalizacji -"
                
                if '-' in loc_date_text:
                    parts = loc_date_text.split('-')
                    location = parts[0].strip()
                    publish_date = parts[1].strip() # Wyciąga "09 maja 2026" lub "Dzisiaj o 14:00"
                else:
                    location = loc_date_text.strip()
                    publish_date = "Brak daty"

                # Przygotowanie słownika z danymi
                offer_data = {
                    "url": clean_url,
                    "title": title,
                    "price": price,
                    "negotiable": is_negotiable,
                    "location": location,
                    "publish_date": publish_date
                }

                # Wysyłka alertu i zapis do bazy
                send_telegram(offer_data)
                save_offer(offer_data)
                print(f"Zapisano i wysłano: {title}")

            except Exception as e:
                print(f"Zignorowano błąd na karcie: {e}")
                continue
                
        browser.close()

if __name__ == "__main__":
    scrape()
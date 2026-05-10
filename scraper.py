import os
import re
import urllib.parse
import requests
from playwright.sync_api import sync_playwright

# Konfiguracja - ZABEZPIECZENIE PRZED BŁĘDNYM FORMATEM URL
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/") # Automatycznie usuwa znak "/" na końcu
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

def send_telegram(offer):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    neg_text = " (Do negocjacji)" if offer['negotiable'] else ""
    msg = (
        f"🔔 <b>NOWA OFERTA PS5!</b>\n\n"
        f"💰 {offer['price']}{neg_text}\n"
        f"📍 {offer['location']} | 🕒 {offer['publish_date']}\n"
        f"📝 {offer['title']}\n\n"
        f"🔗 <a href='{offer['url']}'>Kliknij, aby zobaczyć</a>"
    )
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
    if r.status_code != 200:
        print(f"BŁĄD TELEGRAMA: {r.text}")

def is_new_offer(offer_url):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    params = {"url": f"eq.{offer_url}", "select": "id"}
    try:
        # Pukamy do konkretnej tabeli "offers"
        endpoint = f"{SUPABASE_URL}/rest/v1/offers"
        response = requests.get(endpoint, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"BŁĄD SUPABASE (is_new): URL: {endpoint} | Kod: {response.status_code} | {response.text}")
            return False 
        
        data = response.json()
        return len(data) == 0
    except Exception as e:
        print(f"WYJĄTEK SUPABASE (is_new): {e}")
        return False

def save_offer(offer):
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/offers", headers=headers, json=offer)
    if r.status_code not in [200, 201]:
        print(f"BŁĄD ZAPISU SUPABASE: {r.status_code} - {r.text}")

def scrape():
    # Sprawdzenie kluczy na starcie
    keys = {"TELEGRAM": TELEGRAM_TOKEN, "SUPABASE_URL": SUPABASE_URL, "SCRAPERAPI": SCRAPERAPI_KEY}
    for name, val in keys.items():
        if not val:
            print(f"BŁĄD KRYTYCZNY: Brak zmiennej {name} w GitHub Secrets!")
            return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        target_url = "https://www.olx.pl/oferty/q-playstation-5/?search%5Bfilter_float_price:from%5D=900&search%5Bfilter_float_price:to%5D=1300&search%5Bfilter_enum_version%5D%5B0%5D=playstation5"
        encoded_url = urllib.parse.quote(target_url)
        scraper_url = f"http://api.scraperapi.com/?api_key={SCRAPERAPI_KEY}&url={encoded_url}&render=true"
        
        print("Łączę ze ScraperAPI (to może potrwać do 60s)...")
        page.goto(scraper_url, wait_until="domcontentloaded", timeout=60000)
        
        cards = page.locator('div[data-cy="l-card"]').all()
        print(f"Znaleziono {len(cards)} kart. Przystępuję do analizy...")
        
        for i, card in enumerate(cards):
            try:
                link_elem = card.locator('a').first
                href = link_elem.get_attribute('href')
                if not href: continue
                if not href.startswith("http"): href = "https://www.olx.pl" + href
                clean_url = href.split('#')[0].split('?')[0]

                print(f"Analizuję ofertę {i+1}: {clean_url}")

                if not is_new_offer(clean_url):
                    print(f" -> Oferta już znana lub błąd bazy. Pomijam.")
                    continue

                # Dane oferty
                title_elem = card.locator('h6, h4, h5').first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Brak tytułu"
                
                card_text = card.inner_text()
                is_negotiable = "do negocjacji" in card_text.lower()

                price_elem = card.locator('p[data-testid="ad-price"]').first
                price = price_elem.inner_text().split('\n')[0].strip() if price_elem.count() > 0 else "???"

                loc_elem = card.locator('p[data-testid="location-date"]').first
                loc_date = loc_elem.inner_text() if loc_elem.count() > 0 else "Brak - Brak"
                location = loc_date.split('-')[0].strip() if '-' in loc_date else loc_date
                pub_date = loc_date.split('-')[1].strip() if '-' in loc_date else "Brak"

                offer_data = {
                    "url": clean_url, "title": title, "price": price,
                    "negotiable": is_negotiable, "location": location, "publish_date": pub_date
                }

                print(f" -> Nowa oferta! Wysyłam Telegram i zapisuję...")
                send_telegram(offer_data)
                save_offer(offer_data)

            except Exception as e:
                print(f" -> BŁĄD PARSOWANIA KARTY {i+1}: {e}")
                
        browser.close()

if __name__ == "__main__":
    scrape()
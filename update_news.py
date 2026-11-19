import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import feedparser
from google import genai

# 1. Dine udvalgte RSS-kilder (identisk med din n8n Code-node)
RSS_FEEDS = [
    "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "https://videnskab.dk/feed/",
    "https://via.ritzau.dk/rss",
    "https://www.altinget.dk/rss",
    "https://www.version2.dk/rss",
    "https://arbejderen.dk/feed/",
    "https://nyheder.tv2.dk/seneste",
]

def hent_nyheder():
    artikler = []
    for url in RSS_FEEDS:
        try:
            # Svarer til RSS Feed Read med 'Continue On Fail'
            feed = feedparser.parse(url)
            kilde_navn = feed.feed.get("title", url)
            # Tag de 15 nyeste artikler fra hvert feed for at holde datamængden skarp
            for entry in feed.entries[:15]:
                artikler.append({
                    "kilde": kilde_navn,
                    "titel": entry.get("title", ""),
                    "beskrivelse": entry.get("summary", entry.get("description", ""))[:1200],
                    "link": entry.get("link", ""),
                    "dato": entry.get("published", "")
                })
        except Exception as e:
            print(f"Sprang over {url} pga. fejl: {e}")
    return artikler

def generer_html(artikler):
    # Henter API-nøglen sikkert fra GitHub Secrets
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    nu_tid = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%d-%m-%Y kl. %H:%M")

    prompt = f"""
    Du er en saglig nyhedsredaktør. 
    Du skal udvælge og medtage 15 af de vigtigste nyheder fra nedenstående rådata, med de vigtigste øverst. 
    HVis flere medier rapporterer samme historie så vælg den der har den mest røde/socialistiske/humanistiske vinkel. 
    Nævn hvilket medie historien er fra, samt hvilken kategori den tilhører. 
    Udeluk sport undtagen motorsport.
    Returnér UDELUKKENDE ren, valid HTML-kode (ingen markdown-tegn som ```html før eller efter).
    Lav en moderne, mobilvenlig webside med indlejret CSS (mørk tekst på lys baggrund, pæn skrifttype, max-width 800px centreret).
    Øverst skal stå "ThApex Nyhedsoverblik" og "Sidst opdateret: {nu_tid}".
    Hver nyhed skal have:
    - En tydelig overskrift og kildenavn
    - Et nøgternt resumé på maks. 5 linjer
    - Et klikbart link ("Læs original artikel") der åbner i en ny fane (target="_blank")
    - Hvis et link stammer fra version2.dk, skal du også tilføje et lille ekstra link lige ved siden af med teksten "(Log ind via IDA)" der peger på [https://www.version2.dk/user/login](https://www.version2.dk/user/login)

    Rådata:
    {json.dumps(artikler, ensure_ascii=False)}
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    html = response.text.strip()
    # Sikkerhedsnet: Fjern eventuelle markdown-kodeblokke, hvis modellen alligevel tilføjer dem
    if html.startswith("```html"):
        html = html[7:]
    if html.startswith("```"):
        html = html[3:]
    if html.endswith("```"):
        html = html[:-3]
    return html.strip()

if __name__ == "__main__":
    print("Henter RSS-feeds...")
    nyhedsdata = hent_nyheder()
    print(f"Fandt {len(nyhedsdata)} artikler. Genererer HTML via Gemini...")
    ny_html = generer_html(nyhedsdata)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(ny_html)
    print("index.html er opdateret!")

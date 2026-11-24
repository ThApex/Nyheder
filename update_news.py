import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import feedparser
from google import genai
from google.genai import types

# 1. Dine udvalgte RSS-kilder
RSS_FEEDS = [
    "https://www.dr.dk/nyheder/service/feeds/allenyheder",
    "https://videnskab.dk/feed/",
    "https://via.ritzau.dk/rss",
    "https://www.altinget.dk/rss",
    "https://www.version2.dk/rss",
    "https://arbejderen.dk/feed/",
    "https://fho.dk/feed/",
    "https://ing.dk/rss/",
    "https://avisendanmark.dk/feed/forside/",
    "https://feeds.services.tv2.dk/api/feeds/nyheder/rss",
]

# Gør at servere som TV 2, Arbejderen og FH ikke blokerer scriptet som en bot
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def hent_nyheder():
    artikler = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=USER_AGENT)
            kilde_navn = feed.feed.get("title", url)
            entries = feed.entries[:15]
            print(f"Hentede {len(entries)} artikler fra: {kilde_navn} ({url})")
            
            for entry in entries:
                artikler.append({
                    "kilde": kilde_navn,
                    "titel": entry.get("title", ""),
                    "beskrivelse": entry.get("summary", entry.get("description", ""))[:1000],
                    "link": entry.get("link", ""),
                    "dato": entry.get("published", "")
                })
        except Exception as e:
            print(f"Sprang over {url} pga. fejl: {e}")
    return artikler

def generer_html(artikler):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    nu_tid = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%d-%m-%Y kl. %H:%M")

    prompt = f"""
    Du er en saglig nyhedsredaktør, der udfører opgaven grundigt og omhyggeligt.
    Du SKAL udvælge og levere PRÆCIS 20 nyhedsartikler i hovedsektionen fra nedenstående rådata, rangeret med de vigtigste øverst. Gå ikke under 20 artikler – fyld op med mindre nyheder fra rådataene, hvis der er mange dubletter.

    Regler for udvælgelse og indhold:
    - Sørg for en god spredning på tværs af alle de kilder, der findes i rådataene (inkl. TV 2, Arbejderen, FH, Ingeniøren, DR, Altinget m.fl., i det omfang de er til stede).
    - Hvis flere medier rapporterer samme historie, så vælg den, der har den mest røde/socialistiske/humanistiske vinkel.
    - Nævn tydeligt hvilket medie historien er fra, samt hvilken kategori den tilhører.
    - Udeluk al sport undtagen motorsport.
    - Returnér UDELUKKENDE ren, valid HTML-kode (ingen markdown-tegn som ```html før eller efter).

    Design og layout (indlejret CSS):
    - Lav en moderne, mobilvenlig webside med indlejret CSS (mørk tekst på lys baggrund, pæn skrifttype, max-width 800px centreret, god læsbarhed).
    - Øverst skal stå "ThApex Nyhedsoverblik" og "Sidst opdateret: {nu_tid}".

    Hver af de 20 hovednyheder skal have:
    - En tydelig overskrift, kategori og kildenavn
    - Et nøgternt resumé på maks. 7 linjer
    - Et klikbart link ("Læs original artikel") der åbner i en ny fane (target="_blank")
    - Hvis et link stammer fra version2.dk eller ing.dk, skal du også tilføje et lille ekstra link lige ved siden af med teksten "(Log ind via IDA)" der peger på henholdsvis [https://www.version2.dk/user/login?destination=/](https://www.version2.dk/user/login?destination=/) eller [https://ing.dk/user/login?destination=/](https://ing.dk/user/login?destination=/) (med target="_blank").

    Bundsektion (Hurtigt overblik over alle øvrige nyheder):
    - Nederst på siden under de 20 hovednyheder skal du lave en pænt stylet fold-ud-boks med HTML-tagget <details><summary>Se alle øvrige hentede overskrifter</summary>...</details>.
    - Inde i denne fold-ud-boks skal samtlige resterende artikler fra rådataene (som ikke er blandt de 20 øverste, og stadig uden dubletter og sport) listes på én kompakt linje pr. artikel med: [Kildenavn] Overskrift som klikbart link (target="_blank") – samt evt. "(Log ind via IDA)" hvis den er fra version2.dk eller ing.dk.

    Rådata:
    {json.dumps(artikler, ensure_ascii=False)}
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=16384,
        ),
    )

    html = response.text.strip()
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
    print(f"Fandt i alt {len(nyhedsdata)} artikler. Genererer HTML via Gemini...")
    ny_html = generer_html(nyhedsdata)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(ny_html)
    print("index.html er opdateret!")

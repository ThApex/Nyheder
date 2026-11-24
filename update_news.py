import os
import re
import json
import html as html_lib
from difflib import SequenceMatcher
from datetime import datetime
from zoneinfo import ZoneInfo
import feedparser
from google import genai
from google.genai import types

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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def normaliser_titel(titel):
    # Fjerner specialtegn og mellemrum for præcis sammenligning
    return re.sub(r'[^a-zæøå0-9\s]', '', titel.lower()).strip()

def er_duplet(ny_artikel, eksisterende_artikler):
    ny_link = ny_artikel["link"].split("?")[0].rstrip("/")
    ny_titel = normaliser_titel(ny_artikel["titel"])
    
    for eks in eksisterende_artikler:
        # 1. Tjek for identisk URL (uden tracking-parametre)
        eks_link = eks["link"].split("?")[0].rstrip("/")
        if ny_link and ny_link == eks_link:
            return True
            
        # 2. Tjek for enslydende overskrifter (f.eks. samme Ritzau-historie på to medier)
        eks_titel = normaliser_titel(eks["titel"])
        if ny_titel and eks_titel:
            lighed = SequenceMatcher(None, ny_titel, eks_titel).ratio()
            if lighed >= 0.78:  # 78 % eller mere tekstlig sammenfald = samme nyhed
                return True
    return False

def hent_nyheder():
    ra_artikler = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, agent=USER_AGENT)
            kilde_navn = feed.feed.get("title", url)
            entries = feed.entries[:15]
            print(f"Hentede {len(entries)} artikler fra: {kilde_navn}")
            
            for entry in entries:
                ra_artikler.append({
                    "kilde": kilde_navn,
                    "titel": entry.get("title", ""),
                    "beskrivelse": entry.get("summary", entry.get("description", ""))[:1000],
                    "link": entry.get("link", ""),
                    "dato": entry.get("published", "")
                })
        except Exception as e:
            print(f"Sprang over {url} pga. fejl: {e}")

    # Sorter så dine foretrukne kilder (f.eks. Arbejderen, FH, Altinget, DR) prioriteres først ved dupletter
    prioritet = ["arbejderen", "fho", "fagbevægelsens", "altinget", "ingeniøren", "version2", "videnskab", "dr"]
    def kilde_score(artikel):
        k = artikel["kilde"].lower()
        for idx, p in enumerate(prioritet):
            if p in k:
                return idx
        return len(prioritet)

    ra_artikler.sort(key=kilde_score)

    unikke_artikler = []
    fjernede = 0
    for artikel in ra_artikler:
        if not er_duplet(artikel, unikke_artikler):
            unikke_artikler.append(artikel)
        else:
            fjernede += 1

    print(f"Fjernede {fjernede} dupletter. Tilbage er {len(unikke_artikler)} unikke artikler.")
    return unikke_artikler

def byg_komplet_liste_html(artikler):
    linjer = []
    for a in artikler:
        kilde = html_lib.escape(a["kilde"])
        titel = html_lib.escape(a["titel"])
        link = html_lib.escape(a["link"])
        
        ida_link = ""
        if "version2.dk" in link:
            ida_link = ' <a href="https://www.version2.dk/user/login?destination=/" target="_blank" style="font-size:0.85em; color:#555;">(Log ind via IDA)</a>'
        elif "ing.dk" in link:
            ida_link = ' <a href="https://ing.dk/user/login?destination=/" target="_blank" style="font-size:0.85em; color:#555;">(Log ind via IDA)</a>'
            
        linjer.append(f'<li style="margin-bottom:6px;"><strong>[{kilde}]</strong> <a href="{link}" target="_blank">{titel}</a>{ida_link}</li>')

    return f"""
    <section style="max-width:800px; margin:30px auto; padding:0 15px; font-family:system-ui, -apple-system, sans-serif;">
      <details style="background:#f4f4f4; padding:15px; border-radius:8px; border:1px solid #ddd;">
        <summary style="cursor:pointer; font-weight:bold; font-size:1.1em;">Se alle {len(artikler)} unikke overskrifter fra alle kilder</summary>
        <ul style="margin-top:15px; padding-left:20px; line-height:1.5;">
          {''.join(linjer)}
        </ul>
      </details>
    </section>
    """

def generer_html(artikler):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    nu_tid = datetime.now(ZoneInfo("Europe/Copenhagen")).strftime("%d-%m-%Y kl. %H:%M")

    # Send maks. 8 nyeste pr. kilde til AI'en, så alle 10 kilder er ligeligt repræsenteret i top 20
    ai_udvalg = []
    kilde_taeller = {}
    for a in artikler:
        k = a["kilde"]
        kilde_taeller[k] = kilde_taeller.get(k, 0) + 1
        if kilde_taeller[k] <= 8:
            ai_udvalg.append(a)

    prompt = f"""
    Du er en saglig nyhedsredaktør, der udfører opgaven grundigt og omhyggeligt.
    Du SKAL udvælge og levere PRÆCIS 20 nyhedsartikler fra nedenstående rådata, rangeret med de vigtigste øverst.

    Regler for udvælgelse og indhold:
    - Sørg for en god spredning på tværs af alle kilderne i rådataene (inkl. TV 2, Arbejderen, FH, Ingeniøren, DR, Altinget m.fl.).
    - Hvis to artikler stadig handler om samme konkrete begivenhed (selvom overskrifterne er forskellige), må du KUN medtage én af dem – vælg da den med den mest røde/socialistiske/humanistiske vinkel.
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

    Rådata:
    {json.dumps(ai_udvalg, ensure_ascii=False)}
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
    html = html.strip()

    komplet_liste = byg_komplet_liste_html(artikler)
    if "</body>" in html:
        html = html.replace("</body>", f"{komplet_liste}\n</body>")
    else:
        html += komplet_liste

    return html

if __name__ == "__main__":
    print("Henter RSS-feeds...")
    nyhedsdata = hent_nyheder()
    print(f"Fandt i alt {len(nyhedsdata)} unikke artikler. Genererer HTML via Gemini...")
    ny_html = generer_html(nyhedsdata)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(ny_html)
    print("index.html er opdateret!")

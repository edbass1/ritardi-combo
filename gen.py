#!/usr/bin/env python3
"""Genera ritardi combo (1X/X2/12 + Goal / Over 2.5) da FotMob."""
import json, time, urllib.request, datetime, html
from zoneinfo import ZoneInfo

LEAGUES = [
 ("ITALIA","SERIE A",55),("ITALIA","SERIE B",86),
 ("INGHILTERRA","PREMIER LEAGUE",47),("INGHILTERRA","CHAMPIONSHIP",48),
 ("INGHILTERRA","LEAGUE ONE",108),("INGHILTERRA","LEAGUE TWO",109),
 ("GERMANIA","BUNDESLIGA",54),("GERMANIA","2. BUNDESLIGA",146),("GERMANIA","3. LIGA",208),
 ("FRANCIA","LIGUE 1",53),("FRANCIA","LIGUE 2",110),
 ("SPAGNA","LALIGA",87),("SPAGNA","LALIGA 2",140),
 ("BELGIO","FIRST DIVISION A",40),("BELGIO","FIRST DIVISION B",264),
 ("OLANDA","EREDIVISIE",57),("OLANDA","EERSTE DIVISIE",111),
 ("SVIZZERA","SUPER LEAGUE",69),("SVIZZERA","CHALLENGE LEAGUE",163),
 ("AUSTRIA","BUNDESLIGA",38),("AUSTRIA","2. LIGA",119),
 ("PORTOGALLO","LIGA PORTUGAL",61),("PORTOGALLO","LIGA PORTUGAL 2",185),
 ("NORVEGIA","ELITESERIEN",59),("NORVEGIA","OBOS-LIGAEN",203),
 ("DANIMARCA","SUPERLIGAEN",46),("DANIMARCA","1. DIVISION",85),
 ("SVEZIA","ALLSVENSKAN",67),("SVEZIA","SUPERETTAN",168),
 ("REP. CECA","1. LIGA",122),("REP. CECA","FNL",253),
 ("SLOVACCHIA","1. LIGA (NIKE LIGA)",176),("SLOVACCHIA","2. LIGA",8973),
 ("SCOZIA","PREMIERSHIP",64),("SCOZIA","CHAMPIONSHIP",123),
 ("IRLANDA","PREMIER DIVISION",126),("IRLANDA","FIRST DIVISION",218),
 ("FINLANDIA","VEIKKAUSLIIGA",51),("FINLANDIA","YKKOSLIIGA",251),
 ("POLONIA","EKSTRAKLASA",196),("POLONIA","I LIGA",197),
]
COMBOS = {
 "goal": [("1X + GOAL", lambda h,a: h>=a and h>0 and a>0),
          ("X2 + GOAL", lambda h,a: a>=h and h>0 and a>0),
          ("12 + GOAL", lambda h,a: h!=a and h>0 and a>0)],
 "over": [("1X + OVER 2,5", lambda h,a: h>=a and h+a>=3),
          ("X2 + OVER 2,5", lambda h,a: a>=h and h+a>=3),
          ("12 + OVER 2,5", lambda h,a: h!=a and h+a>=3)],
}
TOP = 10

def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return json.load(urllib.request.urlopen(req, timeout=30))
        except Exception as e:
            err = e; time.sleep(3*(i+1))
    raise err

def matches(lid, season=None):
    url = f"https://www.fotmob.com/api/data/leagues?id={lid}"
    if season: url += "&season=" + urllib.parse.quote(season)
    d = get(url)
    out, teams = [], {}
    for m in d["fixtures"]["allMatches"]:
        st = m["status"]
        for side in ("home","away"):
            teams[m[side]["id"]] = m[side]["name"]
        if not st.get("finished") or st.get("cancelled") or st.get("awarded"): continue
        try: h, a = [int(x) for x in st["scoreStr"].split("-")]
        except Exception: continue
        out.append((st["utcTime"], m["home"]["id"], m["away"]["id"], h, a))
    out.sort()
    return d, out, teams

import urllib.parse
def compute(lid):
    d, cur, teams = matches(lid)
    seasons = d.get("allAvailableSeasons") or []
    cur_season = d["details"].get("selectedSeason") or (seasons[0] if seasons else None)
    prev = None
    if cur_season in seasons and seasons.index(cur_season)+1 < len(seasons):
        prev = seasons[seasons.index(cur_season)+1]
    prev_m, prev_teams = [], {}
    if prev:
        try: _, prev_m, prev_teams = matches(lid, prev)
        except Exception: pass
    res = {}
    for key, combos in COMBOS.items():
        res[key] = []
        for name, f in combos:
            rows = []
            for tid, tname in teams.items():
                seq = [m for m in cur if tid in (m[1], m[2])]
                if tid in prev_teams:
                    seq = [m for m in prev_m if tid in (m[1], m[2])] + seq
                n = 0; g = 0
                for m in reversed(seq):
                    if f(m[3], m[4]): break
                    n += 1
                    if m[3]+m[4] >= 2 or (m[3] > 0 and m[4] > 0): g += 1
                full = n == len(seq)
                pct = round(100*g/n) if n else 0
                rows.append((n, tname, full, pct))
            rows.sort(key=lambda r: (-r[0], r[1]))
            res[key].append((name, rows[:TOP]))
    return cur_season, prev, len(cur), res

def main():
    now = datetime.datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    data = []
    for c, l, lid in LEAGUES:
        try: data.append((c, l, compute(lid), None))
        except Exception as e: data.append((c, l, None, str(e)))
        time.sleep(1)
    titles = {"goal": "RITARDI DOPPIA CHANCE + GOAL", "over": "RITARDI DOPPIA CHANCE + OVER 2,5"}
    sections = {}
    for key in COMBOS:
        L = [titles[key], f"Aggiornato: {now} (ora italiana)",
             "Ritardo = partite di campionato consecutive senza la combo (segno della partita, casa o trasferta indifferente).",
             "Include la stagione precedente solo se la squadra era nella stessa divisione. '+' = mai uscita nel periodo considerato.",
             "🟢 xx% = nelle partite del ritardo attuale, % con almeno 2 gol totali o entrambe a segno (mostrato se >= 50%).",
             "Fonte: FotMob", ""]
        for c, l, r, err in data:
            L.append("="*50); L.append(f"{c} - {l}")
            if err or not r: L.append(f"  dati non disponibili ({err})"); L.append(""); continue
            cs, ps, n, res = r
            L.append(f"Stagione {cs} ({n} partite giocate)" + (f" + {ps}" if ps else ""))
            L.append("="*50)
            for name, rows in res[key]:
                L.append(f"RITARDI {name}")
                for i, (v, t, full, pct) in enumerate(rows, 1):
                    dot = f"  🟢 {pct}%" if v and pct >= 50 else ""
                    L.append(f"  {i:>2}. {t:<30} {str(v)+('+' if full else ''):>4}{dot}")
                L.append("")
        sections[key] = "\n".join(L) + "\n"
    open("ritardi_goal.txt","w").write(sections["goal"])
    open("ritardi_over.txt","w").write(sections["over"])
    page = f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ritardi Combo</title><style>body{{font-family:sans-serif;margin:1em;background:#f6f6f6}}pre{{background:#fff;padding:1em;overflow-x:auto;border:1px solid #ddd}}nav a{{margin-right:1em}}</style></head><body>
<h1>Ritardi Combo Doppia Chance</h1><p>Ultimo aggiornamento: <b>{now}</b> (ora italiana) &middot; si aggiorna ogni 6 ore</p>
<nav><a href="#goal">Sezione 1: + GOAL</a><a href="#over">Sezione 2: + OVER 2,5</a><a href="ritardi_goal.txt">ritardi_goal.txt</a><a href="ritardi_over.txt">ritardi_over.txt</a></nav>
<h2 id="goal">Sezione 1 - 1X+Goal, X2+Goal, 12+Goal</h2><pre>{html.escape(sections['goal'])}</pre>
<h2 id="over">Sezione 2 - 1X+Over 2,5, X2+Over 2,5, 12+Over 2,5</h2><pre>{html.escape(sections['over'])}</pre></body></html>"""
    open("index.html","w").write(page)

if __name__ == "__main__":
    main()

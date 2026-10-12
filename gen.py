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
SOGLIA_GOAL = 6   # ritardo minimo per 'Prossime partite' (combo Goal)
SOGLIA_OVER = 6   # ritardo minimo per 'Prossime partite' (combo Over 2,5)
GIORNI = 5
ROME = ZoneInfo('Europe/Rome')

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
    out, teams, up = [], {}, []
    now = datetime.datetime.now(datetime.timezone.utc)
    for m in d["fixtures"]["allMatches"]:
        st = m["status"]
        for side in ("home","away"):
            teams[m[side]["id"]] = m[side]["name"]
        if not st.get("finished") and not st.get("started") and not st.get("cancelled"):
            try:
                t = datetime.datetime.fromisoformat(st["utcTime"].replace("Z", "+00:00"))
                if now <= t <= now + datetime.timedelta(days=GIORNI):
                    up.append((t, m["home"]["id"], m["away"]["id"]))
            except Exception: pass
        if not st.get("finished") or st.get("cancelled") or st.get("awarded"): continue
        try: h, a = [int(x) for x in st["scoreStr"].split("-")]
        except Exception: continue
        out.append((st["utcTime"], m["home"]["id"], m["away"]["id"], h, a))
    out.sort()
    d['_upcoming'] = up
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
    prev2_m = []
    if prev and seasons.index(prev)+1 < len(seasons):
        try: _, prev2_m, _ = matches(lid, seasons[seasons.index(prev)+1])
        except Exception: pass
    sotto = []
    for name, f in COMBOS["goal"] + COMBOS["over"]:
        rows = []
        for tid, tname in teams.items():
            if tid not in prev_teams: continue
            seq = [m for m in prev2_m + prev_m + cur if tid in (m[1], m[2])][-50:]
            rows.append((sum(1 for m in seq if f(m[3], m[4])), len(seq), tname))
        rows.sort(key=lambda r: (r[0], r[2]))
        if len(rows) > 5:
            cut = rows[4][0]; rows = [r for r in rows if r[0] <= cut]
        sotto.append((name, rows))
    res, allr = {}, {}
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
            for r in rows: allr.setdefault(r[1], []).append((key, name) + r)
    return cur_season, prev, len(cur), res, d['_upcoming'], teams, allr, sotto

def red_sets(sotto):
    out = {}
    for name, rows in sotto:
        if not rows: out[name] = set(); continue
        cut = rows[min(2, len(rows)-1)][0]
        out[name] = {t for k, n, t in rows if k <= cut}
    return out

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
             "🔴 = squadra tra le prime 3 (pari merito inclusi) della Sottofrequenza del suo campionato per la stessa combo.",
             "🟢 xx% = nelle partite del ritardo attuale, % con almeno 2 gol totali o entrambe a segno (mostrato se >= 50%).",
             "Fonte: FotMob", ""]
        for c, l, r, err in data:
            L.append("="*50); L.append(f"{c} - {l}")
            if err or not r: L.append(f"  dati non disponibili ({err})"); L.append(""); continue
            cs, ps, n, res = r[:4]; red = red_sets(r[7])
            L.append(f"Stagione {cs} ({n} partite giocate)" + (f" + {ps}" if ps else ""))
            L.append("="*50)
            for name, rows in res[key]:
                L.append(f"RITARDI {name}")
                for i, (v, t, full, pct) in enumerate(rows, 1):
                    dot = f"  🟢 {pct}%" if v and pct >= 50 else ""
                    if t in red.get(name, ()): dot += "  🔴"
                    L.append(f"  {i:>2}. {t:<30} {str(v)+('+' if full else ''):>4}{dot}")
                L.append("")
        sections[key] = "\n".join(L) + "\n"
    fx = []
    for c, l, r, err in data:
        if not r: continue
        up, teams, allr = r[4], r[5], r[6]; red = red_sets(r[7])
        for t, h, a in up:
            info = []
            for tid in (h, a):
                tn = teams[tid]
                parts = []
                for key, name, v, _, full, pct in allr.get(tn, []):
                    if v >= (SOGLIA_GOAL if key == "goal" else SOGLIA_OVER):
                        rr = [x for x in (teams[h], teams[a]) if x in red.get(name, ())]
                        parts.append(f"{name} ({v}{'+' if full else ''})" + (f" 🟢 {pct}%" if pct >= 50 else "") + ("".join(f" 🔴 {x}" for x in rr)))
                if parts: info.append(f"      {tn}: " + "; ".join(parts))
            if info: fx.append((t, c, l, teams[h], teams[a], info))
    fx.sort(key=lambda x: (x[0], x[1], x[3]))
    P = [f"PROSSIME PARTITE ({GIORNI} GIORNI) CON SQUADRE IN RITARDO", f"Aggiornato: {now} (ora italiana)",
         f"Soglie: combo Goal ritardo >= {SOGLIA_GOAL}, combo Over 2,5 ritardo >= {SOGLIA_OVER}. Orari in ora italiana. 🔴 Squadra = quella squadra della partita è top 3 Sottofrequenza per quella combo. Fonte: FotMob", ""]
    day = None
    for t, c, l, hn, an, info in fx:
        lt = t.astimezone(ROME)
        d0 = lt.strftime("%d/%m/%Y")
        if d0 != day: P += ["", "="*50, d0, "="*50]; day = d0
        P.append(f"{lt:%H:%M}  {hn} vs {an}   [{c} - {l}]"); P += info
    if not fx: P.append("Nessuna partita nei prossimi giorni con ritardi sopra soglia.")
    sections["prossime"] = "\n".join(P) + "\n"
    S = ["SOTTOFREQUENZE - DOPPIA CHANCE + GOAL e + OVER 2,5 (ultime 50 partite di campionato)", f"Aggiornato: {now} (ora italiana)",
         "Le 5 squadre con meno uscite della combo (pari merito inclusi). Escluse neopromosse/retrocesse. Fonte: FotMob", ""]
    for c, l, r, err in data:
        S += ["="*50, f"{c} - {l}", "="*50]
        if not r: S += ["  dati non disponibili", ""]; continue
        for name, rows in r[7]:
            S.append(f"SOTTOFREQUENZA {name}")
            for i, (k, n, t) in enumerate(rows, 1):
                S.append(f"  {i:>2}. {t:<30} {k}/{n}")
            S.append("")
    sections["sotto"] = "\n".join(S) + "\n"
    open("sottofrequenze.txt","w").write(sections["sotto"])
    open("prossime_partite.txt","w").write(sections["prossime"])
    open("ritardi_goal.txt","w").write(sections["goal"])
    open("ritardi_over.txt","w").write(sections["over"])
    page = f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ritardi Combo</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:1rem;background:#000;color:#e8e8e8;max-width:1100px;margin:auto}}h1{{color:#00ff88;text-shadow:0 0 12px #00ff8866;font-size:clamp(1.4rem,5vw,2.2rem)}}h2{{color:#10e07a;border-left:4px solid #00ff88;padding-left:.6rem;margin-top:2rem}}b{{color:#00ff88}}pre{{background:#0b0f0c;color:#d9ffe9;padding:1rem;overflow-x:auto;border:1px solid #00ff8855;border-radius:10px;box-shadow:0 0 18px #00ff8822;font-size:clamp(.72rem,2.6vw,.92rem);line-height:1.45;white-space:pre}}nav{{display:flex;flex-wrap:wrap;gap:.5rem;position:sticky;top:0;background:#000d;padding:.5rem 0;backdrop-filter:blur(6px)}}nav a{{color:#00ff88;border:1px solid #00ff88;border-radius:999px;padding:.35rem .8rem;text-decoration:none;font-size:.85rem}}nav a:hover{{background:#00ff88;color:#000}}</style></head><body>
<h1>Ritardi Combo Doppia Chance</h1><p>Ultimo aggiornamento: <b>{now}</b> (ora italiana) &middot; si aggiorna ogni 6 ore</p>
<nav><a href="#goal">Sezione 1: + GOAL</a><a href="#over">Sezione 2: + OVER 2,5</a><a href="#prossime">Prossime partite (5 giorni)</a><a href="#sotto">Sottofrequenze</a><a href="ritardi_goal.txt">ritardi_goal.txt</a><a href="ritardi_over.txt">ritardi_over.txt</a><a href="prossime_partite.txt">prossime_partite.txt</a><a href="sottofrequenze.txt">sottofrequenze.txt</a></nav>
<h2 id="sotto">Sottofrequenze (ultime 50 partite)</h2><pre>{html.escape(sections['sotto'])}</pre>
<h2 id="prossime">Prossime partite (5 giorni)</h2><pre>{html.escape(sections['prossime'])}</pre>
<h2 id="goal">Sezione 1 - 1X+Goal, X2+Goal, 12+Goal</h2><pre>{html.escape(sections['goal'])}</pre>
<h2 id="over">Sezione 2 - 1X+Over 2,5, X2+Over 2,5, 12+Over 2,5</h2><pre>{html.escape(sections['over'])}</pre></body></html>"""
    open("index.html","w").write(page)

if __name__ == "__main__":
    main()

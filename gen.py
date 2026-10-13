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
SOTTO_N = 100     # partite considerate per le sottofrequenze
SOTTO_MIN = 85    # minimo partite per entrare nelle sottofrequenze
SOTTO_STAGIONI = 4
# campionati extra (non in classifica) usati solo per lo storico delle sottofrequenze
EXTRA = {"ITALIA":[147],"INGHILTERRA":[117],"GERMANIA":[512],"FRANCIA":[8970],"SPAGNA":[8968],
         "OLANDA":[9195],"NORVEGIA":[204],"DANIMARCA":[239],"PORTOGALLO":[9112],"POLONIA":[8935],
         "SCOZIA":[124],"FINLANDIA":[8969]}
_CACHE = {}
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
    k = (lid, season)
    if k not in _CACHE: _CACHE[k] = _matches(lid, season)
    return _CACHE[k]

def country_pool(country):
    lids = [lid for c, l, lid in LEAGUES if c == country] + EXTRA.get(country, [])
    pool, missing = {}, []
    for lid in lids:
        try: d, _, _ = matches(lid)
        except Exception: missing.append(f"{lid}"); continue
        ss = d.get("allAvailableSeasons") or []
        cs = d["details"].get("selectedSeason") or (ss[0] if ss else None)
        idx = ss.index(cs) if cs in ss else 0
        for i, se in enumerate(ss[idx:idx+SOTTO_STAGIONI]):
            try: _, ms, _ = matches(lid, None if i == 0 else se)
            except Exception: missing.append(f"{lid} {se}"); continue
            for m in ms: pool[(m[0], m[1], m[2])] = m
            time.sleep(0.3)
    return sorted(pool.values()), missing

def _matches(lid, season=None):
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
def compute(lid, POOL):
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
    sotto = []; freq = {}
    for name, f in COMBOS["goal"] + COMBOS["over"]:
        rows = []
        for tid, tname in teams.items():
            seq = [m for m in POOL if tid in (m[1], m[2])][-SOTTO_N:]
            rows.append((sum(1 for m in seq if f(m[3], m[4])), len(seq), tname))
        freq[name] = {t: (k, n) for k, n, t in rows}
        rows = [r for r in rows if r[1] >= SOTTO_MIN]
        rate = lambda r: r[0]
        rows.sort(key=lambda r: (r[0], -r[1], r[2]))
        if len(rows) > 5:
            cut = rate(rows[4]); rows = [r for r in rows if rate(r) <= cut]
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
    return cur_season, prev, len(cur), res, d['_upcoming'], teams, allr, sotto, freq, tables(d, teams)

TIPS_MAX = 10
TIPS_MIN_SCORE = 35
TIPS_MIN_DELAY = 6
TIPS_MIN_N = 30

def build_tips(data, today):
    """Punteggio trasparente per (partita di oggi, combo). Vedi TIPS_RULES."""
    cands = []
    for LI, (c, l, r, err) in enumerate(data):
        if not r: continue
        up, teams, allr, sotto, freq = r[4], r[5], r[6], r[7], r[8]
        red = red_sets(sotto)
        delay = {(t, x[1]): x for t, xs in allr.items() for x in xs}  # (team, combo) -> (key,name,v,team,full,pct)
        lmax = {}
        for (t, nm), x in delay.items(): lmax.setdefault(nm, []).append(x[2])
        for t, h, a in up:
            lt = t.astimezone(ROME)
            if lt.date() != today: continue
            hn, an = teams[h], teams[a]
            best = None
            for nm in [n for n, _ in COMBOS["goal"] + COMBOS["over"]]:
                fr = freq.get(nm, {})
                rates = [k / n for k, n in fr.values() if n >= TIPS_MIN_N]
                if not rates: continue
                pL = sum(rates) / len(rates)
                dh, da = delay.get((hn, nm)), delay.get((an, nm))
                if not dh or not da: continue
                T, O = (dh, da) if dh[2] >= da[2] else (da, dh)
                tn, on, v, pct = T[3], O[3], T[2], T[5]
                k, n = fr.get(tn, (0, 0)); ko, no = fr.get(on, (0, 0))
                if v < TIPS_MIN_DELAY or n < TIPS_MIN_N: continue
                pT = k / n; pO = ko / no if no >= TIPS_MIN_N else pL
                exp_gap = 1 / pT if pT > 0 else 99
                srt = sorted(lmax[nm], reverse=True)
                mx = max(srt[0], 1); med = srt[len(srt)//2]
                s1 = 30 * v / mx                                 # ritardo rispetto al ritardo massimo del campionato
                top3 = v >= srt[min(2, len(srt)-1)]
                s2 = 10 if v >= srt[0] else (5 if top3 else 0)   # posizione nel campionato
                s3 = max(-15, min(15, (pL - pT) * 100))         # recupero: squadra sotto media = positivo
                s4 = min(8, (pct - 50) / 5) if pct >= 50 else 0  # 🟢 partite del ritardo con gol
                s5 = max(-10, min(10, (pL - pO) * 100))         # recupero: avversaria sotto media = positivo
                s6 = 10 if O[2] >= TIPS_MIN_DELAY else 0        # entrambe in ritardo sulla stessa combo
                rT, rO = tn in red.get(nm, ()), on in red.get(nm, ())
                s7 = (15 if rT else 0) + (10 if rO else 0)       # 🔴 sottofrequenza = deve recuperare
                sc = s1 + s2 + s3 + s4 + s5 + s6 + s7
                if not (top3 or rT or rO or pct >= 60 or s6) or sc < TIPS_MIN_SCORE: continue
                why = [f"{tn} non fa {nm} da {v} partite (ritardo massimo del campionato {srt[0]}, mediano {med})"]
                if s2 == 10: why[0] += ", ed è il ritardo più lungo del campionato"
                elif s2: why[0] += ", tra i 3 ritardi più lunghi del campionato"
                why[0] += "."
                ex = []
                if rT: ex.append(f"{tn} è in sottofrequenza ({k}/{n}), deve recuperare")
                if rO: ex.append(f"anche {on} è in sottofrequenza su questa combo ({ko}/{no}), deve recuperare")
                if s6: ex.append(f"anche {on} è in ritardo sulla stessa combo ({O[2]})")
                if pct >= 50: ex.append(f"nel ritardo il {pct}% delle partite ha avuto almeno 2 gol o entrambe a segno")
                if s3 >= 5 and not rT: ex.append(f"{tn} la fa meno della media ({round(100*pT)}% vs {round(100*pL)}%), margine di recupero")
                if ex: why.append("Inoltre " + "; ".join(ex) + ".")
                neg = []
                if s3 <= -5: neg.append(f"{tn} la fa già più della media ({round(100*pT)}% vs {round(100*pL)}%)")
                if s5 <= -5: neg.append(f"{on} la fa già spesso ({ko}/{no})")
                if neg: why.append("Attenzione: " + "; ".join(neg) + ".")
                cand = (round(sc, 1), lt, c, l, hn, an, nm, " ".join(why), [round(x, 1) for x in (s1, s2, s3, s4, s5, s6, s7)], LI)
                if not best or cand[0] > best[0]: best = cand
            if best: cands.append(best)
    cands.sort(key=lambda x: -x[0])
    return cands[:TIPS_MAX]

TIPS_RULES = [
 "Logica di recupero: per ogni partita di oggi e ogni combo (le 6) si considera la squadra con il ritardo più lungo; serve ritardo >= 6 e almeno 30 partite di storico.",
 "Motivo evidente obbligatorio: ritardo tra i primi 3 del campionato, oppure 🔴 (squadra o avversaria), oppure 🟢 >= 60%, oppure entrambe in ritardo.",
 "R  Ritardo vs campionato: 30 x ritardo / ritardo massimo del campionato su quella combo (max 30).",
 "C  Classifica campionato: +10 se è il ritardo più lungo del campionato, +5 se tra i primi 3.",
 "F  Frequenza squadra (ultime 100) sotto la media del campionato = positivo (deve recuperare): +/- 1 punto per punto %, max +/-15.",
 "G  🟢: +1 punto ogni 5% sopra il 50% di partite del ritardo con almeno 2 gol o entrambe a segno (max +8, pesa meno del 🔴).",
 "A  Avversaria con frequenza sotto la media = positivo: +/- 1 punto per punto %, max +/-10.",
 "E  Entrambe in ritardo (>= 6) sulla stessa combo: +10.",
 "S  🔴 Sottofrequenza = deve recuperare: +15 se la squadra in ritardo è top 3 sottofrequenza, +10 se lo è l'avversaria (cumulabili).",
 "Una tip per partita (la combo con punteggio più alto), punteggio minimo 35, massimo 10 tips. Tutto calcolato automaticamente da gen.py.",
]

def tables(d, teams):
    out = []
    try:
        for blk in d.get("table") or []:
            x = blk.get("data", {})
            tl = [x] if "table" in x else x.get("tables", [])
            for t in tl:
                rows = t.get("table", {}).get("all", [])
                out.append([[r.get("idx"), teams.get(str(r.get("id")), r.get("name")), r.get("pts"), r.get("played")] for r in rows])
    except Exception: pass
    return out

def red_sets(sotto):
    out = {}
    for name, rows in sotto:
        if not rows: out[name] = set(); continue
        cut = round(rows[min(2, len(rows)-1)][0] / rows[min(2, len(rows)-1)][1], 4)
        out[name] = {t for k, n, t in rows if round(k / n, 4) <= cut}
    return out

def tspan(li, a, b, t):
    E = lambda x: html.escape(str(x), quote=True)
    return f'<span class="pt" data-k="{li}" data-a="{E(a)}" data-b="{E(b)}">{E(t)}</span>'

def main():
    now = datetime.datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    data = []
    pools = {}
    for c, l, lid in LEAGUES:
        if c not in pools: pools[c] = country_pool(c)
        try: data.append((c, l, compute(lid, pools[c][0]), None))
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
    for KEY, TIT in (('goal', 'COMBO + GOAL'), ('over', 'COMBO + OVER 2,5')):
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
                      if key == KEY and v >= (SOGLIA_GOAL if key == "goal" else SOGLIA_OVER):
                          rr = [x for x in (teams[h], teams[a]) if x in red.get(name, ())]
                          parts.append(f"{name} ({v}{'+' if full else ''})" + (f" 🟢 {pct}%" if pct >= 50 else "") + ("".join(f" 🔴 {x}" for x in rr)))
                  if parts: info.append(f"      {tn}: " + "; ".join(parts))
              if info: fx.append((t, c, l, teams[h], teams[a], info))
      fx.sort(key=lambda x: (x[0], x[1], x[3]))
      P = [f"PROSSIME PARTITE ({GIORNI} GIORNI) - {TIT} - SQUADRE IN RITARDO", f"Aggiornato: {now} (ora italiana)",
           f"Soglia ritardo >= {SOGLIA_GOAL if KEY == 'goal' else SOGLIA_OVER}. Orari in ora italiana. 🔴 Squadra = quella squadra della partita è top 3 Sottofrequenza per quella combo. Fonte: FotMob", ""]
      day = None
      for t, c, l, hn, an, info in fx:
          lt = t.astimezone(ROME)
          d0 = lt.strftime("%d/%m/%Y")
          if d0 != day: P += ["", "="*50, d0, "="*50]; day = d0
          P.append(f"{lt:%H:%M}  {hn} vs {an}   [{c} - {l}]"); P += info
      if not fx: P.append("Nessuna partita nei prossimi giorni con ritardi sopra soglia.")
      sections["prossime_" + KEY] = "\n".join(P) + "\n"
    LAB = {"goal": "GOAL", "over": "OVER 2,5"}
    cf = []; POP = {}
    for LI, (c, l, r, err) in enumerate(data):
        if not r: continue
        up, teams, allr = r[4], r[5], r[6]; red = red_sets(r[7])
        POP[LI] = {"lg": f"{c} - {l}", "rit": {name: [[t, v, full, pct] for v, t, full, pct in rows] for k in r[3] for name, rows in r[3][k]},
                   "sotto": {name: [[t, k2, n] for k2, n, t in rows] for name, rows in r[7]}, "tab": r[9]}
        for t, h, a in up:
            tags = []  # (key, team, [part strings])
            for KEY in ("goal", "over"):
                for tid in (h, a):
                    tn = teams[tid]; parts = []; hparts = []
                    for key, name, v, _, full, pct in allr.get(tn, []):
                        if key == KEY and v >= (SOGLIA_GOAL if key == "goal" else SOGLIA_OVER):
                            rr = [x for x in (teams[h], teams[a]) if x in red.get(name, ())]
                            parts.append(f"{name} ({v}{'+' if full else ''})" + (f" 🟢 {pct}%" if pct >= 50 else "") + "".join(f" 🔴 {x}" for x in rr))
                            E = lambda x: html.escape(str(x), quote=True)
                            hparts.append(f'{E(name)} <span class="pp" data-k="{LI}" data-c="{E(name)}" data-t="{E(tn)}">({v}{"+" if full else ""})</span>' + (f" 🟢 {pct}%" if pct >= 50 else "") + "".join(f' <span class="pr" data-k="{LI}" data-c="{E(name)}" data-t="{E(x)}">🔴 {E(x)}</span>' for x in rr))
                    if parts: tags.append((KEY, tn, parts, hparts))
            if tags: cf.append((t, c, l, teams[h], teams[a], tags, LI))
    cf.sort(key=lambda x: (x[0], x[1], x[3]))
    P = [f"PROSSIME PARTITE ({GIORNI} GIORNI) - SQUADRE IN RITARDO", f"Aggiornato: {now} (ora italiana)",
         f"Soglie: combo Goal ritardo >= {SOGLIA_GOAL}, combo Over 2,5 ritardo >= {SOGLIA_OVER}. Orari in ora italiana. 🔴 Squadra = quella squadra della partita è top 3 Sottofrequenza per quella combo. Fonte: FotMob", ""]
    H = []; day = None
    for t, c, l, hn, an, tags, LIX in cf:
        lt = t.astimezone(ROME); d0 = lt.strftime("%d/%m/%Y")
        if d0 != day:
            P += ["", "="*50, d0, "="*50]; H.append(f'<h3 class="day">{d0}</h3>'); day = d0
        P.append(f"{lt:%H:%M}  {hn} vs {an}   [{c} - {l}]")
        hb = []
        for KEY, tn, parts, hparts in tags:
            P.append(f"      [{LAB[KEY]}] {tn}: " + "; ".join(parts))
            hb.append(f'<div class="tagrow"><span class="tag {KEY}">{LAB[KEY]}</span> <b>{tspan(LIX, hn, an, tn)}</b>: ' + "; ".join(hparts) + "</div>")
        H.append(f'<div class="fx"><div class="fxh"><span class="time">{lt:%H:%M}</span> {tspan(LIX, hn, an, hn)} vs {tspan(LIX, hn, an, an)} <span class="lg">{html.escape(c)} - {html.escape(l)}</span></div>' + "".join(hb) + "</div>")
    if not cf:
        P.append("Nessuna partita nei prossimi giorni con ritardi sopra soglia."); H.append("<p>Nessuna partita nei prossimi giorni con ritardi sopra soglia.</p>")
    sections["prossime"] = "\n".join(P) + "\n"
    sections["prossime_html"] = "\n".join(H)
    sections["popjson"] = json.dumps(POP, ensure_ascii=False).replace("</", "<\\/")
    today = datetime.datetime.now(ROME).date()
    tips = build_tips(data, today)
    TT = [f"TIPS DEL GIORNO - {today:%d/%m/%Y}", f"Aggiornato: {now} (ora italiana). Calcolo automatico, nessuna garanzia: sono solo statistiche.", ""]
    TH = []
    for i, (sc, lt, c, l, hn, an, nm, why, comp, LIX) in enumerate(tips, 1):
        det = " ".join(f"{a}{b:+g}" for a, b in zip("RCFGAES", comp))
        TT += [f"{i:>2}. {lt:%H:%M}  {hn} vs {an}   [{c} - {l}]", f"    {nm}  -  punteggio {sc}  ({det})", f"    {why}", ""]
        TH.append(f'<div class="tip"><div class="tiph"><span class="rk">{i}</span><span class="time">{lt:%H:%M}</span> {tspan(LIX, hn, an, hn)} vs {tspan(LIX, hn, an, an)} <span class="lg">{html.escape(c)} - {html.escape(l)}</span></div><div class="tipc"><span class="tag {"goal" if "GOAL" in nm else "over"}">{html.escape(nm)}</span> <span class="sc">{sc} pt</span> <span class="det">{det}</span></div><p>{html.escape(why)}</p></div>')
    if not tips:
        TT.append("Nessuna tip convincente oggi."); TH.append("<p>Nessuna tip convincente oggi.</p>")
    TT += ["", "REGOLE DEL PUNTEGGIO"] + ["  " + x for x in TIPS_RULES]
    sections["tips"] = "\n".join(TT) + "\n"
    sections["tips_html"] = "\n".join(TH)
    sections["tips_rules"] = "".join(f"<li>{html.escape(x)}</li>" for x in TIPS_RULES)
    open("tips_del_giorno.txt", "w").write(sections["tips"])
    S = [f"SOTTOFREQUENZE - DOPPIA CHANCE + GOAL e + OVER 2,5 (ultime {SOTTO_N} partite di campionato)", f"Aggiornato: {now} (ora italiana)",
         "Le 5 squadre con meno uscite della combo (pari merito inclusi). Incluse neopromosse/retrocesse (contano anche le partite in altre divisioni). Classifica per numero di uscite; incluse solo squadre con almeno 85 partite (N<100 = storico disponibile inferiore). Fonte: FotMob", ""]
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
    open("prossime_partite_goal.txt","w").write(sections["prossime_goal"])
    open("prossime_partite_over.txt","w").write(sections["prossime_over"])
    open("ritardi_goal.txt","w").write(sections["goal"])
    open("ritardi_over.txt","w").write(sections["over"])
    page = f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ritardi Combo</title><style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:1rem;background:#000;color:#e8e8e8;max-width:1100px;margin:auto}}h1{{color:#00ff88;text-shadow:0 0 12px #00ff8866;font-size:clamp(1.4rem,5vw,2.2rem)}}h2{{color:#10e07a;border-left:4px solid #00ff88;padding-left:.6rem;margin-top:2rem}}b{{color:#00ff88}}pre{{background:#0b0f0c;color:#d9ffe9;padding:1rem;overflow-x:auto;border:1px solid #00ff8855;border-radius:10px;box-shadow:0 0 18px #00ff8822;font-size:clamp(.72rem,2.6vw,.92rem);line-height:1.45;white-space:pre}}nav{{display:flex;flex-wrap:wrap;gap:.5rem;position:sticky;top:0;background:#000d;padding:.5rem 0;backdrop-filter:blur(6px)}}nav a{{color:#00ff88;border:1px solid #00ff88;border-radius:999px;padding:.35rem .8rem;text-decoration:none;font-size:.85rem}}nav a:hover{{background:#00ff88;color:#000}}h3.day{{color:#00ff88;margin:1.4rem 0 .5rem;border-bottom:1px solid #00ff8855}}.fx{{background:#0b0f0c;border:1px solid #00ff8844;border-radius:10px;padding:.6rem .8rem;margin:.5rem 0}}.fxh{{font-weight:600;color:#fff}}.time{{color:#00ff88;margin-right:.4rem}}.lg{{color:#8a9;font-weight:400;font-size:.85em;margin-left:.4rem}}.tagrow{{margin-top:.35rem;line-height:1.5}}.tag{{display:inline-block;padding:.05rem .5rem;border-radius:6px;font-size:.78em;font-weight:700;color:#000}}.tag.goal{{background:#2e9e5b;color:#000}}.tag.over{{background:#d9822b;color:#000}}.leg{{color:#aaa}}.pt{{cursor:pointer;border-bottom:1px dotted #8a9}}.pp,.pr{{cursor:pointer;border-bottom:1px dashed #00ff88}}.pp{{color:#00ff88;font-weight:700}}#pop{{position:absolute;z-index:200;display:none;background:#050805;border:1px solid #00ff88;border-radius:10px;box-shadow:0 0 20px #00ff8855;padding:.6rem .8rem;max-width:min(92vw,360px);font-size:.9em;color:#e8e8e8}}#pop h4{{margin:0 0 .4rem;color:#00ff88;font-size:.95em}}#pop table{{border-collapse:collapse;width:100%}}#pop td{{padding:.12rem .35rem;border-bottom:1px solid #00ff8822}}#pop td.n{{text-align:right;color:#00ff88;font-weight:700}}#pop tr.hl td{{background:#00ff8833;color:#fff;font-weight:700}}.tip{{background:#07140c;border:1px solid #00ff88;border-radius:12px;padding:.7rem .9rem;margin:.6rem 0;box-shadow:0 0 14px #00ff8822}}.tiph{{font-weight:700;color:#fff}}.rk{{display:inline-block;min-width:1.7em;height:1.7em;line-height:1.7em;text-align:center;border-radius:50%;background:#00ff88;color:#000;margin-right:.5rem}}.tipc{{margin:.4rem 0}}.sc{{color:#00ff88;font-weight:700;margin-left:.4rem}}.det{{color:#8a9;font-size:.8em;margin-left:.4rem}}.tip p{{margin:.3rem 0 0;color:#d9ffe9}}details.rules{{color:#aaa;margin:.5rem 0 1rem}}details.rules summary{{color:#00ff88;cursor:pointer}}#zoom{{position:fixed;top:10px;right:10px;z-index:99;display:flex;gap:6px}}#zoom button{{width:44px;height:44px;border-radius:50%;border:2px solid #00ff88;background:#000c;color:#00ff88;font-size:1.5rem;font-weight:bold;cursor:pointer;box-shadow:0 0 10px #00ff8855}}#zoom button:active{{background:#00ff88;color:#000}}</style></head><body>
<div id="zoom"><button onclick="z(-1)" aria-label="Riduci">−</button><button onclick="z(1)" aria-label="Ingrandisci">+</button></div>
<script>var Z=parseFloat(localStorage.getItem('zoomRC')||'1');function ap(){{document.querySelectorAll('pre').forEach(function(p){{p.style.fontSize='calc(clamp(.72rem,2.6vw,.92rem)*'+Z+')'}});document.querySelectorAll('.fxlist').forEach(function(f){{f.style.fontSize=(Z*100)+'%'}})}}function z(d){{Z=Math.min(3,Math.max(0.5,Math.round((Z+d*0.1)*10)/10));localStorage.setItem('zoomRC',Z);ap()}}document.addEventListener('DOMContentLoaded',ap);</script>
<h1>Ritardi Combo Doppia Chance</h1><p>Ultimo aggiornamento: <b>{now}</b> (ora italiana) &middot; si aggiorna ogni 6 ore</p>
<nav><a href="#tips">TIPS DEL GIORNO</a><a href="#goal">Sezione 1: + GOAL</a><a href="#over">Sezione 2: + OVER 2,5</a><a href="#prossime">Prossime partite (5 giorni)</a><a href="#sotto">Sottofrequenze</a><a href="ritardi_goal.txt">ritardi_goal.txt</a><a href="ritardi_over.txt">ritardi_over.txt</a><a href="prossime_partite.txt">prossime_partite.txt</a><a href="sottofrequenze.txt">sottofrequenze.txt</a><a href="tips_del_giorno.txt">tips_del_giorno.txt</a></nav>
<h2 id="tips">TIPS DEL GIORNO</h2><div class="fxlist">{sections['tips_html']}</div><details class="rules"><summary>Come viene calcolato il punteggio</summary><ul>{sections['tips_rules']}</ul></details>
<h2 id="sotto">Sottofrequenze (ultime 100 partite)</h2><pre>{html.escape(sections['sotto'])}</pre>
<h2 id="prossime">Prossime partite (5 giorni)</h2><p class="leg">Soglia ritardo &ge; {SOGLIA_GOAL} (Goal) / &ge; {SOGLIA_OVER} (Over 2,5) &middot; orari italiani &middot; <span class="tag goal">GOAL</span> <span class="tag over">OVER 2,5</span> &middot; 🔴 = top 3 Sottofrequenza</p><div class="fxlist">{sections['prossime_html']}</div>
<h2 id="goal">Sezione 1 - 1X+Goal, X2+Goal, 12+Goal</h2><pre>{html.escape(sections['goal'])}</pre>
<h2 id="over">Sezione 2 - 1X+Over 2,5, X2+Over 2,5, 12+Over 2,5</h2><pre>{html.escape(sections['over'])}</pre><div id="pop"></div><script>var POP={sections['popjson']};(function(){{var pop=document.getElementById('pop'),cur=null;function esc(x){{return String(x).replace(/[&<>"]/g,function(c){{return{{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]}})}}
function show(el){{var d=POP[el.dataset.k];if(!d)return;var c=el.dataset.c,t=el.dataset.t,h;if(el.classList.contains('pt')){{var A=el.dataset.a,B=el.dataset.b,tb=(d.tab||[]).filter(function(x){{return x.some(function(r){{return r[1]==A||r[1]==B}})}});if(!tb.length){{h='<h4>'+esc(d.lg)+'</h4>Classifica non disponibile'}}else{{h='<h4>'+esc(d.lg)+' - Classifica</h4>';tb.forEach(function(x){{var N=x.length;h+='<div>'+x.filter(function(r){{return r[1]==A||r[1]==B}}).map(function(r){{return '<b style="color:#00ff88">'+r[0]+'/'+N+'</b> '+esc(r[1])+' <b>'+r[2]+' pt</b>'}}).join('<br>')+'</div><details style="margin-top:.4rem"><summary style="color:#00ff88;cursor:pointer">Classifica completa</summary><table>'+x.map(function(r){{return '<tr'+((r[1]==A||r[1]==B)?' class="hl"':'')+'><td>'+r[0]+'.</td><td>'+esc(r[1])+'</td><td class="n">'+r[2]+'</td><td>'+r[3]+' g</td></tr>'}}).join('')+'</table></details>'}})}}}}else if(el.classList.contains('pp')){{var rows=d.rit[c]||[];h='<h4>'+esc(d.lg)+'<br>Ritardi '+esc(c)+' (top 10)</h4><table>'+rows.map(function(r,i){{return '<tr'+(r[0]==t?' class="hl"':'')+'><td>'+(i+1)+'.</td><td>'+esc(r[0])+'</td><td class="n">'+r[1]+(r[2]?'+':'')+'</td><td>'+(r[1]&&r[3]>=50?'🟢 '+r[3]+'%':'')+'</td></tr>'}}).join('')+'</table>'}}else{{var rows=d.sotto[c]||[];h='<h4>'+esc(d.lg)+'<br>Sottofrequenza '+esc(c)+'</h4><table>'+rows.map(function(r,i){{return '<tr'+(r[0]==t?' class="hl"':'')+'><td>'+(i+1)+'.</td><td>'+esc(r[0])+'</td><td class="n">'+r[1]+'/'+r[2]+'</td></tr>'}}).join('')+'</table>'}}
pop.innerHTML=h;pop.style.fontSize=(typeof Z!=='undefined'?Z*90:90)+'%';pop.style.display='block';var b=el.getBoundingClientRect(),w=pop.offsetWidth,x=b.left+window.scrollX;x=Math.max(window.scrollX+6,Math.min(x,window.scrollX+document.documentElement.clientWidth-w-6));pop.style.left=x+'px';pop.style.top=(b.bottom+window.scrollY+6)+'px';cur=el}}
function hide(){{pop.style.display='none';cur=null}}
document.addEventListener('click',function(e){{var el=e.target.closest('.pp,.pr,.pt');if(el){{if(cur===el)hide();else show(el);e.stopPropagation();return}}if(!pop.contains(e.target))hide()}});
if(window.matchMedia('(hover:hover)').matches){{document.addEventListener('mouseover',function(e){{var el=e.target.closest('.pp,.pr,.pt');if(el&&el!==cur)show(el)}})}}
document.addEventListener('keydown',function(e){{if(e.key==='Escape')hide()}})}})();</script></body></html>"""
    open("index.html","w").write(page)

if __name__ == "__main__":
    main()

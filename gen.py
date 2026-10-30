#!/usr/bin/env python3
"""Genera ritardi combo (1X/X2/12 + Goal) da FotMob.

Tre viste identiche: Totali (tutte le partite), Casa, Trasferta.
Nelle prossime partite: media xG FotMob (se pubblicata) e % GG sulle ultime 10.
"""
import gzip, json, time, urllib.request, datetime, html, re, unicodedata, urllib.parse
from zoneinfo import ZoneInfo

LEAGUES = [
 ("ITALIA","SERIE A",55),("ITALIA","SERIE B",86),("ITALIA","SERIE C",147),
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
 ("BRASILE","SÉRIE A",268),("ARGENTINA","PRIMERA DIVISIÓN",112),
 ("USA/CANADA","MLS",130),("AUSTRALIA","A-LEAGUE MEN",113),
 ("FINLANDIA","VEIKKAUSLIIGA",51),("FINLANDIA","YKKOSLIIGA",251),
 ("POLONIA","EKSTRAKLASA",196),("POLONIA","I LIGA",197),
]
COMBOS = {
 "goal": [("1X + GOAL", lambda h,a: h>=a and h>0 and a>0),
          ("X2 + GOAL", lambda h,a: a>=h and h>0 and a>0),
          ("12 + GOAL", lambda h,a: h!=a and h>0 and a>0)],
}
TOP = 10
SALTATI_MIN = 6      # ritardo minimo spezzato per la sezione Saltati
SALTATI_GIORNI = 7
DANGER_GIORNI = 10   # badge DANGEROUS: giorni considerati
DANGER_TOP = 5       # badge DANGEROUS: ritardo nella top N del campionato
DANGER_MIN = 6       # badge DANGEROUS: ritardo minimo al momento della rottura
SOTTO_N = 100     # partite considerate per le sottofrequenze
SOTTO_MIN = 100   # minimo storico valido: 100 partite nazionali
SOTTO_STAGIONI = 12
# campionati extra (non in classifica) usati solo per lo storico delle sottofrequenze
EXTRA = {"ITALIA":[147],"INGHILTERRA":[117],"GERMANIA":[512],"FRANCIA":[8970],"SPAGNA":[8968],
         "OLANDA":[9195],"NORVEGIA":[204],"DANIMARCA":[239],"PORTOGALLO":[9112],"POLONIA":[8935],
         "SCOZIA":[124],"FINLANDIA":[8969]}
_CACHE = {}
SOGLIA_GOAL = 6   # ritardo minimo per 'Prossime partite' (combo Goal)
GIORNI = 5
MIN_GIORNATE = 7  # giornate giocate minime per la frequenza di campionato
ROME = ZoneInfo('Europe/Rome')
# (campionato, combo) -> "🔥 2/16" oppure "" ; riempito a ogni aggiornamento
LEAGUE_BADGES = {}
# combo -> classifica campionati; league -> statistiche stagione
LEAGUE_FREQ = {}
LEAGUE_FREQ_META = {}

def get(url):
    err = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=30).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            err = e; time.sleep(3*(i+1))
    raise err

def matches(lid, season=None):
    k = (lid, season)
    if k not in _CACHE: _CACHE[k] = _matches(lid, season)
    return _CACHE[k]

def country_pool(country):
    # Recupera prima le stagioni più recenti e si ferma appena tutte le squadre
    # attualmente presenti nei campionati configurati hanno 100 partite valide.
    lids = list(dict.fromkeys(
        [lid for c, l, lid in LEAGUES if c == country] + EXTRA.get(country, [])
    ))
    print(f"Storico {country} ({len(lids)} campionati)...", flush=True)
    league_info, missing, target_teams = {}, [], set()
    ranked_lids = {lid for c, l, lid in LEAGUES if c == country}
    for lid in lids:
        try:
            d, current_matches, teams = matches(lid)
            ss = d.get("allAvailableSeasons") or []
            cs = d.get("details", {}).get("selectedSeason") or (ss[0] if ss else None)
            idx = ss.index(cs) if cs in ss else 0
            league_info[lid] = (ss[idx:idx + SOTTO_STAGIONI], current_matches, teams)
            if lid in ranked_lids:
                target_teams.update(teams.keys())
        except Exception:
            missing.append(str(lid))
    pool = {}
    max_rounds = min(SOTTO_STAGIONI, max((len(x[0]) for x in league_info.values()), default=0))
    for season_index in range(max_rounds):
        for lid, (seasons, current_matches, teams) in league_info.items():
            if season_index >= len(seasons):
                continue
            try:
                if season_index == 0:
                    ms = current_matches
                else:
                    _, ms, _ = matches(lid, seasons[season_index])
                    time.sleep(0.3)
                for m in ms:
                    pool[(m[0], m[1], m[2])] = m
            except Exception:
                missing.append(f"{lid} {seasons[season_index]}")
        counts, home_n, away_n = {}, {}, {}
        for m in pool.values():
            counts[m[1]] = counts.get(m[1], 0) + 1
            counts[m[2]] = counts.get(m[2], 0) + 1
            home_n[m[1]] = home_n.get(m[1], 0) + 1
            away_n[m[2]] = away_n.get(m[2], 0) + 1
        # Totali resta sulle ultime 100. Casa/Trasferta chiedono 100 gare per lato:
        # le stagioni più vecchie non cambiano le ultime 100 complessive.
        if target_teams and all(
            counts.get(tid, 0) >= SOTTO_MIN and home_n.get(tid, 0) >= SOTTO_MIN and away_n.get(tid, 0) >= SOTTO_MIN
            for tid in target_teams
        ):
            break
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

def _in_venue(m, tid, venue):
    """True se la partita entra nella vista. 1/X/2 restano quelli della partita:
    1 = vince chi gioca in casa, 2 = vince chi gioca fuori, X = pareggio.
    12 (non pareggio) è lo stesso dai due lati. In casa 1X è 'non perde la squadra';
    in trasferta X2 è 'non perde la squadra'."""
    if venue == "home":
        return m[1] == tid
    if venue == "away":
        return m[2] == tid
    return tid in (m[1], m[2])

def _fixture_sides(venue, home_id, away_id):
    """Nelle prossime partite la vista Casa vale solo per chi gioca in casa,
    la vista Trasferta solo per chi gioca fuori. Totali resta su entrambe."""
    if venue == "home":
        return (home_id,)
    if venue == "away":
        return (away_id,)
    return (home_id, away_id)

def _seq_for(tid, cur, prev_m, prev_teams, venue):
    seq = [m for m in cur if _in_venue(m, tid, venue)]
    if tid in prev_teams:
        seq = [m for m in prev_m if _in_venue(m, tid, venue)] + seq
    return seq

def season_combo_stats(d):
    """Frequenza delle combo sulla stagione corrente (tutte le partite, non casa/trasferta)."""
    ms = (d.get("fixtures") or {}).get("allMatches") or []
    rounds, played, unfinished = set(), 0, 0
    hits = {name: 0 for name, _ in COMBOS["goal"]}
    for m in ms:
        st = m.get("status") or {}
        if st.get("cancelled") or st.get("awarded"):
            continue
        if not st.get("finished"):
            unfinished += 1
            continue
        try:
            h, a = [int(x) for x in st["scoreStr"].split("-")]
        except Exception:
            continue
        played += 1
        rnd = m.get("round")
        if rnd is None:
            rnd = m.get("roundName")
        if rnd is not None and str(rnd).strip():
            rounds.add(str(rnd).strip())
        for name, f in COMBOS["goal"]:
            if f(h, a):
                hits[name] += 1
    return {"in_season": unfinished > 0, "rounds": len(rounds), "played": played, "hits": hits}

def ogni_label(played, hits):
    """'1 ogni 6,0' = partite giocate / uscite. None se non è mai uscita."""
    if not hits:
        return None
    return f"{played / hits:.1f}".replace(".", ",")

def league_badge_txt(league, combo):
    return LEAGUE_BADGES.get((league, combo), "")

def league_badge_html(league, combo):
    t = league_badge_txt(league, combo)
    if not t:
        return ""
    if t.startswith("🔥"):
        title = "Campionato tra i 7 in cui questa combo esce più spesso, sul totale di stagione"
    elif t.startswith("❗"):
        title = "Campionato tra le posizioni 8 e 14 di questa combo, sul totale di stagione"
    else:
        title = "Campionato tra i 10 in cui questa combo esce meno spesso, sul totale di stagione"
    return f' <span class="fq" title="{esc(title)}">{t}</span>'

def build_league_frequency(data):
    """Classifiche campionati: solo stagione in corso e almeno MIN_GIORNATE giornate."""
    global LEAGUE_BADGES, LEAGUE_FREQ, LEAGUE_FREQ_META
    LEAGUE_BADGES, LEAGUE_FREQ, LEAGUE_FREQ_META = {}, {}, {}
    eligible, excluded = [], []
    for (c, l, lid), (_c, _l, r, err) in zip(LEAGUES, data):
        label = f"{c} - {l}"
        if err or not r:
            excluded.append((label, "dati non disponibili"))
            LEAGUE_FREQ_META[label] = None
            continue
        try:
            d, _, _ = matches(lid)
            st = season_combo_stats(d)
        except Exception:
            excluded.append((label, "dati non disponibili"))
            LEAGUE_FREQ_META[label] = None
            continue
        LEAGUE_FREQ_META[label] = st
        if not st["in_season"]:
            excluded.append((label, f"stagione conclusa ({st['rounds']} giornate, {st['played']} partite)"))
            continue
        if st["rounds"] < MIN_GIORNATE:
            excluded.append((label, f"in corso, {st['rounds']} giornate (< {MIN_GIORNATE})"))
            continue
        eligible.append((label, st))
    n = len(eligible)
    for name, _f in COMBOS["goal"]:
        rows = []
        for label, st in eligible:
            hits = st["hits"][name]
            ogni = ogni_label(st["played"], hits)
            rows.append({"league": label, "played": st["played"], "hits": hits,
                         "rounds": st["rounds"], "ogni": ogni, "sort": (st["played"] / hits) if hits else None})
        rows.sort(key=lambda x: (x["sort"] is None, x["sort"] if x["sort"] is not None else 0, x["league"]))
        for i, row in enumerate(rows, 1):
            row["pos"] = i
            row["tot"] = n
            if i <= 7:
                LEAGUE_BADGES[(row["league"], name)] = f"🔥 {i}/{n}"
            elif 8 <= i <= 14:
                LEAGUE_BADGES[(row["league"], name)] = f"❗ {i}/{n}"
            elif i > n - 10:
                LEAGUE_BADGES[(row["league"], name)] = f"👻 {i}/{n}"
        LEAGUE_FREQ[name] = rows
    return excluded

def render_freq_text(now, excluded):
    lines = [
        "FREQUENZA CAMPIONATI — STAGIONE IN CORSO (TOTALE, NON CASA/TRASFERTA)",
        f"Aggiornato: {now} (ora italiana)",
        "1 ogni N = partite giocate della stagione corrente / partite in cui è uscita la combo.",
        f"Entrano solo i campionati ancora in corso con almeno {MIN_GIORNATE} giornate già giocate.",
        "Ordine: dal più frequente (N più basso) al meno frequente. 🔥 primi 7, ❗ posizioni 8-14, 👻 ultimi 10.",
        "Lo stesso badge è accanto ai ritardi di quella combo, anche nelle viste Casa e Trasferta.",
        "Fonte: FotMob",
        "",
    ]
    n = 0
    for name, _f in COMBOS["goal"]:
        rows = LEAGUE_FREQ.get(name) or []
        n = len(rows)
        lines += ["=" * 50, name, "=" * 50]
        if not rows:
            lines += ["Nessun campionato idoneo.", ""]
            continue
        for row in rows:
            lab = f"1 ogni {row['ogni']}" if row["ogni"] else "mai uscita"
            lines.append(f"  {row['pos']:>2}/{n}  {row['league']:<32} {lab:<16} ({row['hits']}/{row['played']}, {row['rounds']} giornate)")
        lines.append("")
    lines += ["=" * 50, "FUORI CLASSIFICA", "=" * 50]
    if not excluded:
        lines.append("Nessuno.")
    for label, why in excluded:
        lines.append(f"  {label:<32} {why}")
    lines.append("")
    return "\n".join(lines) + "\n", n

def freq_league_line(league):
    st = LEAGUE_FREQ_META.get(league)
    if not st:
        return ""
    if not st["in_season"] or st["rounds"] < MIN_GIORNATE:
        return ""
    bits = []
    for name, _f in COMBOS["goal"]:
        lab = ogni_label(st["played"], st["hits"][name])
        bits.append(f"{name} {('1 ogni ' + lab) if lab else 'mai uscita'}")
    return "  Frequenza stagione: " + " · ".join(bits)

def _gg(seq):
    """Percentuale di segnano-entrambe sulle ultime 10 (o meno, se non ce ne sono 10)."""
    last = seq[-10:]
    if not last:
        return None
    hits = sum(1 for m in last if m[3] > 0 and m[4] > 0)
    return (hits, len(last), round(100 * hits / len(last)))

def _table_groups(d):
    groups = []
    for blk in d.get("table") or []:
        x = blk.get("data") or {}
        if "table" in x:
            groups.append(x)
        else:
            groups.extend(x.get("tables") or [])
    return groups

def _xg_from_rows(rows):
    out = {}
    for r in rows or []:
        played = r.get("played") or 0
        xgf, xga = r.get("xg"), r.get("xgConceded")
        tid = r.get("id") if r.get("id") is not None else r.get("teamId")
        if tid is None or xgf is None or not played:
            continue
        try:
            played, xgf = float(played), float(xgf)
            xga = float(xga) if xga is not None else None
        except (TypeError, ValueError):
            continue
        if played <= 0:
            continue
        rec = {"for": xgf / played, "against": (xga / played if xga is not None else None), "played": played}
        out[str(tid)] = rec
    return out

def _stat_pairs(url):
    d = get(url)
    out = {}
    for block in d.get("TopLists") or []:
        for row in block.get("StatList") or []:
            tid, played, val = row.get("TeamId"), row.get("MatchesPlayed") or 0, row.get("StatValue")
            if tid is None or val is None or not played:
                continue
            out[str(tid)] = (float(val), float(played))
    return out

def extract_xg(d):
    """Media xG a partita dalla classifica FotMob. Vuoto se il campionato non la pubblica."""
    out = {}
    try:
        for g in _table_groups(d):
            out.update(_xg_from_rows((g.get("table") or {}).get("xg")))
    except Exception:
        out = {}
    if out:
        return out
    urls = {}
    for s in (d.get("stats") or {}).get("teams") or []:
        if s.get("name") in ("expected_goals_team", "expected_goals_conceded_team") and s.get("fetchAllUrl"):
            urls[s["name"]] = s["fetchAllUrl"]
    if "expected_goals_team" not in urls:
        return {}
    try:
        forg = _stat_pairs(urls["expected_goals_team"])
        conc = _stat_pairs(urls["expected_goals_conceded_team"]) if urls.get("expected_goals_conceded_team") else {}
    except Exception:
        return {}
    for tid, (val, played) in forg.items():
        if played <= 0:
            continue
        rec = {"for": val / played, "against": None, "played": played}
        if tid in conc and conc[tid][1] > 0:
            rec["against"] = conc[tid][0] / conc[tid][1]
        out[tid] = rec
    return out

def _pts_for_team(tid, m):
    """Punti della squadra in quella partita: 3 vittoria, 1 pareggio, 0 sconfitta."""
    gf, ga = (m[3], m[4]) if m[1] == tid else (m[4], m[3])
    if gf > ga:
        return 3
    if gf == ga:
        return 1
    return 0

def team_form_map(teams, cur, prev_m, prev_teams):
    """Punti delle ultime 5 partite complessive (casa e trasferta insieme)."""
    out = {}
    for tid, tname in teams.items():
        last = _seq_for(tid, cur, prev_m, prev_teams, "all")[-5:]
        rec = (sum(_pts_for_team(tid, m) for m in last), len(last))
        out[tname] = rec
        out[str(tid)] = rec
    return out

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
    xg = extract_xg(d)
    forms = team_form_map(teams, cur, prev_m, prev_teams)
    venues = {}
    for venue in ("all", "home", "away"):
        venues[venue] = _compute_venue(d, teams, cur, prev_m, prev_teams, POOL, venue, forms if venue == "all" else None)
    return {"cs": cur_season, "ps": prev, "n": len(cur), "up": d["_upcoming"], "teams": teams, "xg": xg, "venues": venues}

def _compute_venue(d, teams, cur, prev_m, prev_teams, POOL, venue, forms=None):
    sotto, freq, sinfo = [], {}, {}
    for name, f in COMBOS["goal"]:
        rows = []
        for tid, tname in teams.items():
            seq = [m for m in POOL if _in_venue(m, tid, venue)][-SOTTO_N:]
            rows.append((sum(1 for m in seq if f(m[3], m[4])), len(seq), tname))
        freq[name] = {t: (k, n) for k, n, t in rows if n >= SOTTO_MIN}
        rows = [r for r in rows if r[1] >= SOTTO_MIN]
        rows.sort(key=lambda r: (r[0], -r[1], r[2]))
        rows.reverse()  # ordine invertito: più uscite in cima, meno uscite in fondo
        sinfo[name] = (len(rows), list(rows[-1]) if rows else None)
        if len(rows) > 5:
            cut = rows[4][0]; rows = [r for r in rows if r[0] >= cut]
        sotto.append((name, rows))
    res, allr, salt, danger, gg, hist = {}, {}, [], {}, {}, {}
    for tid, tname in teams.items():
        gg[tname] = _gg(_seq_for(tid, cur, prev_m, prev_teams, venue))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=SALTATI_GIORNI)
    for key, combos in COMBOS.items():
        res[key] = []
        for name, f in combos:
            rows, seqs = [], {}
            for tid, tname in teams.items():
                seq = _seq_for(tid, cur, prev_m, prev_teams, venue)
                seqs[tid] = seq
                n = 0; g = 0
                for m in reversed(seq):
                    if f(m[3], m[4]): break
                    n += 1
                    if m[3]+m[4] >= 2 or (m[3] > 0 and m[4] > 0): g += 1
                full = n == len(seq)
                pct = round(100*g/n) if n else 0
                run = 0
                for m in seq:
                    if f(m[3], m[4]):
                        if run >= SALTATI_MIN:
                            mt = datetime.datetime.fromisoformat(m[0].replace("Z", "+00:00"))
                            if mt >= cutoff: salt.append((mt, m[1], m[2], m[3], m[4], tname, key, name, run))
                        run = 0
                    else: run += 1
                rows.append((n, tname, full, pct))
            rows.sort(key=lambda r: (-r[0], r[1]))
            res[key].append((name, rows[:TOP]))
            def d_at(tid, t0, _seqs=seqs, _f=f):
                n0 = 0
                for m in reversed([m for m in _seqs[tid] if m[0] < t0]):
                    if _f(m[3], m[4]): break
                    n0 += 1
                return n0
            dcut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DANGER_GIORNI)).strftime("%Y-%m-%dT%H:%M")
            ev = []
            for m in cur:
                if m[0][:16] < dcut or not f(m[3], m[4]): continue
                involved = []
                for tid in (m[1], m[2]):
                    if venue == "home" and tid != m[1]: continue
                    if venue == "away" and tid != m[2]: continue
                    if tid in seqs: involved.append(tid)
                if not involved: continue
                vals = sorted((d_at(t2, m[0]) for t2 in seqs), reverse=True)
                cutv = vals[min(DANGER_TOP, len(vals)) - 1] if vals else 0
                for tid in involved:
                    b0 = d_at(tid, m[0])
                    if b0 >= DANGER_MIN and b0 >= cutv: ev.append((m[0], b0))
            danger[name] = [b0 for _, b0 in sorted(ev, reverse=True)]
            for r in rows: allr.setdefault(r[1], []).append((key, name) + r)
            hist[name] = {teams[tid]: (sum(1 for m in seq if f(m[3], m[4])), len(seq)) for tid, seq in seqs.items() if seq}
    return {"res": res, "allr": allr, "sotto": sotto, "freq": freq, "tab": tables(d, teams, venue, forms),
            "salt": salt, "sinfo": sinfo, "danger": danger, "gg": gg, "hist": hist}

TIPS_MAX = 10
TIPS_MIN_DELAY = 6
TIPS_MIN_N = 30
# Pesi su 100. Frequenza squadra e ritardo rispetto alla media pesano un po' di più.
TIPS_WEIGHTS = (("freq", "Freq", 24), ("rit", "Rit", 26), ("lega", "Lega", 18), ("gg", "GG", 16), ("xg", "xG", 16))
TIPS_NOTE = ("Punteggio da 0 a 100 sulle partite di oggi. Pesi: frequenza squadra 24, ritardo rispetto alla media 26, "
             "frequenza del campionato 18, GG sulle ultime 10 16, xG 16. Chi fa uscire la combo più spesso prende più punti. "
             "Se manca l'xG o il campionato non è in classifica, quel fattore non conta e gli altri si riproporzionano.")

def _tip_pct(values):
    """Percentile 0-100. None resta None. I pari merito prendono il rango medio."""
    present = sorted(((i, v) for i, v in enumerate(values) if v is not None), key=lambda iv: iv[1])
    out = [None] * len(values)
    n = len(present)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and present[j + 1][1] == present[i][1]:
            j += 1
        avg = (i + j) / 2
        pct = 100.0 if n == 1 else 100.0 * avg / (n - 1)
        for k in range(i, j + 1):
            out[present[k][0]] = pct
        i = j + 1
    return out

def _tip_sample(view, combo, team):
    """Ultime 100 se lo storico c'è, altrimenti lo stesso periodo del ritardo (almeno 30)."""
    rec = (view["freq"].get(combo) or {}).get(team)
    if rec and rec[1] >= SOTTO_MIN:
        return rec
    rec = (view.get("hist") or {}).get(combo, {}).get(team)
    if rec and rec[1] >= TIPS_MIN_N:
        return rec
    return None

def _tip_xg(xg, tid):
    info = (xg or {}).get(str(tid))
    if not info or info.get("for") is None:
        return None
    if info.get("against") is None:
        return float(info["for"])
    return float(info["for"]) + float(info["against"])

def _gg_per10(g):
    if not g or not g[1]:
        return None
    hits, n, _pct = g
    return hits * 10 / n

def _league_hit_rate(league, combo):
    for row in LEAGUE_FREQ.get(combo) or []:
        if row["league"] == league and row["played"]:
            return row["hits"] / row["played"], row.get("ogni")
    return None, None

def _it1(x):
    return f"{float(x):.1f}".replace(".", ",")

def collect_tip_candidates(data, today):
    """Una candidata per (partita, combo, contesto). I valori grezzi si normalizzano dopo, tutti insieme."""
    cands = []
    for venue in ("all", "home", "away"):
        for LI, (c, l, r, err) in enumerate(data):
            if not r:
                continue
            v = r["venues"][venue]
            delay = {(t, x[1]): x for t, xs in v["allr"].items() for x in xs}
            league = f"{c} - {l}"
            for t, h, a in r["up"]:
                lt = t.astimezone(ROME)
                if lt.date() != today:
                    continue
                hn, an = r["teams"][h], r["teams"][a]
                for nm, _f in COMBOS["goal"]:
                    dh, da = delay.get((hn, nm)), delay.get((an, nm))
                    if venue == "home":
                        sides = [(h, hn, dh)]
                    elif venue == "away":
                        sides = [(a, an, da)]
                    else:
                        sides = [(h, hn, dh), (a, an, da)]
                    sides = [s for s in sides if s[2]]
                    if not sides or max(s[2][2] for s in sides) < TIPS_MIN_DELAY:
                        continue
                    facts = []
                    for tid, name, rec in sides:
                        sample = _tip_sample(v, nm, name)
                        if not sample:
                            continue
                        k, n = sample
                        streak = rec[2]
                        base = n - streak
                        ratio = (streak * k / base) if k > 0 and base > 0 else 0.0
                        avg = (base / k) if k > 0 and base > 0 else None
                        facts.append({"tid": tid, "name": name, "k": k, "n": n, "streak": streak,
                                      "rate": k / n, "ratio": ratio, "avg": avg})
                    if not facts:
                        continue
                    lega, ogni = _league_hit_rate(league, nm)
                    gg_vals, xg_vals = [], []
                    for fac in facts:
                        g = _gg_per10(v["gg"].get(fac["name"]))
                        if g is not None:
                            gg_vals.append((fac["name"], v["gg"][fac["name"]], g))
                        xv = _tip_xg(r["xg"], fac["tid"])
                        if xv is not None:
                            xg_vals.append((fac["name"], xv))
                    cands.append({
                        "raw": {
                            "freq": sum(f["rate"] for f in facts) / len(facts),
                            "rit": sum(f["ratio"] for f in facts) / len(facts),
                            "lega": lega,
                            "gg": (sum(g for _n, _rec, g in gg_vals) / len(gg_vals)) if gg_vals else None,
                            "xg": (sum(x for _n, x in xg_vals) / len(xg_vals)) if xg_vals else None,
                        },
                        "lt": lt, "c": c, "l": l, "hn": hn, "an": an, "nm": nm, "venue": venue, "LI": LI,
                        "facts": facts, "gg": gg_vals, "xg": xg_vals, "ogni": ogni,
                    })
    return cands

def rank_tips(cands):
    """Percentile di oggi per fattore, poi media pesata. Manca un fattore: il suo peso si redistribuisce."""
    if not cands:
        return []
    pct = {key: _tip_pct([c["raw"][key] for c in cands]) for key, _lab, _w in TIPS_WEIGHTS}
    for i, c in enumerate(cands):
        acc = wsum = 0.0
        parts = []
        for key, lab, w in TIPS_WEIGHTS:
            p = pct[key][i]
            if p is None:
                continue
            acc += w * p
            wsum += w
            parts.append((key, lab, p))
        c["score"] = (acc / wsum) if wsum else 0.0
        c["parts"] = parts
    best = {}
    for c in cands:
        key = (c["lt"].isoformat(), c["hn"], c["an"])
        old = best.get(key)
        if old is None or c["score"] > old["score"]:
            best[key] = c
    ranked = sorted(best.values(), key=lambda c: (-c["score"], c["lt"], c["hn"]))
    return ranked[:TIPS_MAX]

def _tip_seed(c):
    raw = f"{c['hn']}|{c['an']}|{c['nm']}|{c['venue']}|{c['lt'].strftime('%Y%m%d%H%M')}"
    h = 2166136261
    for ch in raw:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h

def _mix(seed, slot, options):
    return options[(seed // (3 * slot + 1) + slot) % len(options)]

def _cap(s):
    return (s[0].upper() + s[1:]) if s else s

def _e(s):
    """'e' oppure 'ed' davanti a vocale: 'ed è', 'e la fa'."""
    if s[:1].lower() in "aeiouàèéìòù":
        return "ed " + s
    return "e " + s

def _join_it(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " e " + parts[-1]

def _combo_label(nm):
    if nm.startswith("1X"):
        return "l'1X+GOAL"
    if nm.startswith("X2"):
        return "l'X2+GOAL"
    return "il 12+GOAL"

def _circa_pct(n):
    """'circa il 60%' / 'circa l'82%', con l'articolo giusto."""
    if n == 0:
        return "circa lo 0%"
    if n in (1, 8, 11) or 80 <= n <= 89:
        return f"circa l'{n}%"
    return f"circa il {n}%"

def _usual_words(avg):
    if not avg:
        return "nello storico che guardiamo non è ancora uscita"
    if avg < 1.25:
        return "di solito non passa una partita senza che esca"
    if avg < 1.85:
        return "di solito non passa più di una partita senza"
    if avg < 2.7:
        return "di solito ne saltano un paio"
    if avg < 4:
        return "in media ne restano fuori tre o quattro"
    return f"in media ne restano fuori circa {round(avg)}"

def _freq_words(f, seed):
    if not f["k"]:
        return "finora non è mai uscita"
    pct = _circa_pct(round(100 * f["rate"]))
    if f["rate"] >= 0.55:
        return _mix(seed, 2, [
            f"la fa spesso, {pct} delle volte",
            f"è una giocata che riesce spesso ({pct})",
            f"esce spesso nel suo calendario, {pct} delle partite",
        ])
    if f["rate"] >= 0.4:
        return _mix(seed, 2, [
            f"la vede abbastanza spesso, {pct} delle volte",
            f"la incontra abbastanza spesso, {pct} delle volte",
        ])
    return _mix(seed, 2, [
        f"la fa meno spesso, {pct} delle volte",
        f"non è tra le sue giocate più solite ({pct})",
    ])

def _league_words(ogni, seed):
    if not ogni:
        return ""
    try:
        x = float(str(ogni).replace(",", "."))
    except ValueError:
        return ""
    if x <= 2.2:
        return _mix(seed, 4, [
            "in questo campionato la combo esce quasi una partita sì e una no",
            "questo campionato la produce di continuo",
        ])
    if x <= 3.0:
        return _mix(seed, 4, [
            "anche il campionato la vede spesso",
            "in questo campionato non è una rarità",
        ])
    if x <= 4.2:
        return _mix(seed, 4, [
            "nel campionato esce con regolarità",
            "questo campionato la propone abbastanza spesso",
        ])
    return _mix(seed, 4, [
        "nel campionato esce più di rado",
        "questo campionato la vede meno spesso",
    ])

def _gg_words(gg, seed):
    if not gg:
        return ""
    name, rec, _scaled = max(gg, key=lambda t: t[1][0])
    hits, n, _pct = rec
    if n >= 10 and hits >= 8:
        return _mix(seed, 5, [
            f"nelle ultime 10 hanno segnato entrambe {hits} volte",
            f"il GG nelle ultime 10 è uscito {hits} volte",
        ])
    if n >= 10 and hits >= 5:
        return _mix(seed, 5, [
            f"nelle ultime 10 il gol di entrambe è arrivato {hits} volte",
            f"su 10 partite recenti il GG è uscito {hits} volte",
        ])
    if n >= 10:
        return f"nelle ultime 10 il GG è uscito {hits} volte"
    return f"nelle ultime {n} hanno segnato entrambe {hits} volte"

def _xg_words(xg, seed):
    if not xg:
        return ""
    avg = sum(v for _name, v in xg) / len(xg)
    if avg >= 2.7:
        return _mix(seed, 6, ["l'xG è alto", "c'è tanto xG"])
    if avg >= 2.2:
        return _mix(seed, 6, ["l'xG è buono", "l'xG dà una mano"])
    return _mix(seed, 6, ["l'xG resta nella media", "l'xG non spicca, ma c'è"])

def _tip_why(c):
    """Due frasi al massimo, in italiano semplice. Lo stampo cambia con la partita, in modo stabile."""
    seed = _tip_seed(c)
    combo = _combo_label(c["nm"])
    dove = {"home": " in casa", "away": " in trasferta", "all": ""}[c["venue"]]
    facts = c["facts"]
    lead = max(facts, key=lambda f: (f["ratio"], f["streak"], f["rate"]))
    usual = _usual_words(lead["avg"])
    freq = _freq_words(lead, seed)
    others = [f for f in facts if f is not lead]
    if others and others[0]["rate"] >= 0.48:
        freq += f", e anche {others[0]['name']} la trova spesso"
    name, n = lead["name"], lead["streak"]
    style = seed % 4
    if style == 0:
        first = f"{name} non vede {combo} da {n} partite{dove}: {usual}, {_e(freq)}."
    elif style == 1:
        first = f"Sono {n} partite che {name} resta senza {combo}{dove}: {usual}, {_e(freq)}."
    elif style == 2:
        first = f"{_cap(combo)} si fa aspettare da {name}{dove}: {n} gare, {usual}, {_e(freq)}."
    else:
        first = f"Per {name}{dove} {combo} manca da {n} partite: {usual}, {_e(freq)}."
    extra = _join_it([
        _league_words(c.get("ogni"), seed),
        _gg_words(c.get("gg"), seed),
        _xg_words(c.get("xg"), seed),
    ])
    if extra:
        return first + " " + _cap(extra) + "."
    return first

def render_tips(tips, data, today, now):
    head = [f"TIPS DEL GIORNO - {today:%d/%m/%Y}",
            f"Aggiornato: {now} (ora italiana). Calcolo automatico, nessuna garanzia: sono solo statistiche.",
            TIPS_NOTE, ""]
    rows_txt = list(head)
    html_rows = [f'<p class="leg">{esc(TIPS_NOTE)}</p>', '<div class="fxlist">']
    for i, c in enumerate(tips, 1):
        sc = _it1(c["score"])
        det = " · ".join(f"{lab} {round(p)}" for _k, lab, p in c["parts"])
        why = _tip_why(c)
        ctx = {"all": "TOTALE", "home": "CASA", "away": "TRASFERTA"}[c["venue"]]
        _dh, dt = dbadges(data[c["LI"]][2]["venues"][c["venue"]]["danger"], f"{c['c']} - {c['l']}", [c["nm"]])
        rows_txt += [f"{i:>2}. {ctx:<9} {c['lt']:%H:%M}  {c['hn']} vs {c['an']}   [{c['c']} - {c['l']}]  {dt}",
                     f"    {c['nm']}  -  punteggio {sc}  ({det})", f"    {why}", ""]
        dh, _dt = dbadges(data[c["LI"]][2]["venues"][c["venue"]]["danger"], f"{c['c']} - {c['l']}", [c["nm"]])
        html_rows.append(
            f'<div class="tip"><div class="tiph"><span class="rk">{i}</span>'
            f'<span class="time copy-time" data-copy="{esc(c["hn"] + " vs " + c["an"])}" title="Clicca per copiare la partita">{c["lt"]:%H:%M}</span> '
            f'{tspan(c["LI"], c["hn"], c["an"], c["hn"])} vs {tspan(c["LI"], c["hn"], c["an"], c["an"])} '
            f'<span class="lg">{esc(c["c"])} - {esc(c["l"])}</span> {dh}</div>'
            f'<div class="tipc"><span class="vtag {c["venue"]}">{ctx}</span><span class="tag goal">{esc(c["nm"])}</span> '
            f'<span class="sc">{sc} pt</span> <span class="det" title="Percentili di oggi, da 0 a 100">{esc(det)}</span></div>'
            f'<p>{esc(why)}</p></div>'
        )
    if not tips:
        rows_txt.append("Nessuna tip oggi con ritardo almeno 6 e storico sufficiente.")
        html_rows.append("<p>Nessuna tip oggi con ritardo almeno 6 e storico sufficiente.</p>")
    rows_txt += ["", "COME CALCOLIAMO IL PUNTEGGIO"] + ["  " + x for x in TIPS_RULES]
    html_rows.append("</div>")
    return {"txt": "\n".join(rows_txt) + "\n", "html": "\n".join(html_rows)}

TIPS_RULES = [
 "Per ogni partita di oggi si valuta ogni combo (1X+GOAL, X2+GOAL, 12+GOAL) in Totale, Casa e Trasferta. Resta la combinazione col punteggio più alto e in classifica entrano le 10 partite migliori, dalla più alta.",
 "Casa usa solo la squadra che gioca in casa e i suoi numeri in casa. Trasferta usa solo chi gioca fuori. Totale usa entrambe, sulle partite complessive.",
 "Serve un ritardo di almeno 6 e almeno 30 partite di storico. La frequenza è sulle ultime 100 se ci sono, altrimenti sullo stesso storico del ritardo.",
 "Ogni fattore è un percentile da 0 a 100 calcolato sulle candidate di oggi: chi ha il valore più alto prende 100, chi ha il più basso prende 0.",
 "Frequenza squadra, peso 24. Più la squadra fa uscire quella combo, più punti. Chi la fa meno prende meno.",
 "Ritardo rispetto alla media, peso 26. La media è quante partite passano di solito tra un'uscita e l'altra. Più il ritardo attuale supera quella media, più punti.",
 "Frequenza del campionato, peso 18. È la classifica totale della stagione (1 ogni N): i campionati in cui la combo esce più spesso pesano di più. Se il campionato non è in classifica, il fattore si salta.",
 "GG sulle ultime 10, peso 16. Più volte hanno segnato entrambe, più punti. Con meno di 10 gare recenti il conto si riporta su 10.",
 "xG, peso 16. Media a partita di fatti più subiti; se i subiti non ci sono, solo i fatti. Più è alto, più punti. Se manca, non è una penalità: si salta e il peso va agli altri fattori.",
 "Il punteggio mostrato è la media pesata dei percentili disponibili, da 0 a 100. Accanto ci sono i percentili dei singoli fattori. Nessuna garanzia: sono solo statistiche.",
]

def tables(d, teams, which="all", forms=None):
    """Righe [pos, nome, punti, giocate] e, sulla classifica totale, [forma, n forma]."""
    out = []
    try:
        for g in _table_groups(d):
            rows = (g.get("table") or {}).get(which) or []
            if not rows:
                continue
            block = []
            for r in rows:
                tid = r.get("id")
                name = teams.get(tid, teams.get(str(tid), r.get("name")))
                row = [r.get("idx"), name, r.get("pts"), r.get("played")]
                if forms is not None:
                    fp, fn = forms.get(name, forms.get(str(tid), (0, 0)))
                    row.append(fp if fn else None)
                    row.append(fn)
                block.append(row)
            out.append(block)
    except Exception: pass
    return out

def red_sets(sotto):
    # Pallino rosso = prime 3 della classifica (più uscite in cima), pari merito inclusi.
    out = {}
    for name, rows in sotto:
        if not rows: out[name] = set(); continue
        i = min(2, len(rows) - 1)
        cut = round(rows[i][0] / rows[i][1], 4)
        out[name] = {t for k, n, t in rows if round(k / n, 4) >= cut}
    return out

def under_sets(freq):
    # Tips: ancora le 3 con meno uscite. Non segue il pallino rosso.
    out = {}
    for name, fr in freq.items():
        rows = [(k, n, t) for t, (k, n) in fr.items()]
        rows.sort(key=lambda r: (r[0], -r[1], r[2]))
        if len(rows) > 5:
            cut = rows[4][0]
            rows = [r for r in rows if r[0] <= cut]
        if not rows: out[name] = set(); continue
        i = min(2, len(rows) - 1)
        cut = round(rows[i][0] / rows[i][1], 4)
        out[name] = {t for k, n, t in rows if round(k / n, 4) <= cut}
    return out

def dbadges(danger, lg, names):
    """Badge DANGEROUS/OK per ogni combo in ritardo nella partita."""
    H, T = [], []
    for nm in dict.fromkeys(names):
        ev = danger.get(nm, []); short = nm.replace(" ", "").replace("OVER2,5", "OVER2,5")
        if ev:
            msg = f"Negli ultimi {DANGER_GIORNI} giorni in {lg} {"è saltato 1 ritardo" if len(ev)==1 else f"sono saltati {len(ev)} ritardi"} top {DANGER_TOP} di {nm}: " + ", ".join(f"era a {x}" for x in ev)
            H.append(f'<span class="dz bad" data-msg="{html.escape(msg, quote=True)}">ALT {html.escape(short)}</span>'); T.append(f"[ALT {short}]")
        else:
            H.append(f'<span class="dz ok">{html.escape(short)}</span>'); T.append(f"[OK {short}]")
    return " ".join(H), " ".join(T)

# bet365: pagine hub ufficiali bet365.it per campionato (le route #/AC/... cambiano ogni stagione,
# quindi vengono lette dalla pagina hub a ogni aggiornamento). Altri campionati: pagina Calcio.
BET365_HUB = {55: "serie-a", 86: "serie-b", 47: "premier-league", 87: "la-liga", 54: "bundesliga"}
BET365_FALLBACK = "https://www.bet365.it/#/AS/B1/"
_B365 = {}

def bet365_url(lid):
    if lid in _B365: return _B365[lid]
    url = BET365_FALLBACK
    slug = BET365_HUB.get(lid)
    if slug:
        hub = f"https://www.bet365.it/hub/it-it/football/football-competitions/{slug}"
        url = hub
        try:
            req = urllib.request.Request(hub, headers={"User-Agent": "Mozilla/5.0"})
            txt = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            m = re.search(r"#/AC/B1/C1/D1002/E(\d+)/", txt)
            if m: url = f"https://www.bet365.it/#/AC/B1/C1/D1002/E{m.group(1)}/G40/"
        except Exception: pass
    _B365[lid] = url
    return url

def tspan(li, a, b, t):
    E = lambda x: html.escape(str(x), quote=True)
    return f'<span class="pt" data-k="{li}" data-a="{E(a)}" data-b="{E(b)}">{E(t)}</span>'

# Collegamenti ai bookmaker: si colorano solo se viene trovato un URL di evento
# che contiene riferimenti verificabili a entrambe le squadre. In caso contrario
# resta il collegamento generico, grigio.
_BOOKMAKER_CACHE = {}
_BOOKMAKER_PAGE_CACHE = {}
_BOOKMAKER_PAGES = {
    "bet365": ("https://www.bet365.it/hub/it-it/football", re.compile(r"https?://(?:www\.)?bet365\.it/[^\s\"'<>]*E\d+[^\s\"'<>]*", re.I)),
}

def _norm_team(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", s)

def _bookmaker_event(site, home, away):
    key = (site, _norm_team(home), _norm_team(away))
    if key in _BOOKMAKER_CACHE:
        return _BOOKMAKER_CACHE[key]
    base, url_re = _BOOKMAKER_PAGES[site]
    found = ""
    try:
        if site not in _BOOKMAKER_PAGE_CACHE:
            # Prima prova una pagina realmente renderizzata: i bookmaker caricano
            # spesso gli eventi via JavaScript, quindi urllib da solo non basta.
            rendered = ""
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        locale="it-IT",
                        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                    )
                    tab = context.new_page()
                    tab.goto(base, wait_until="domcontentloaded", timeout=25000)
                    tab.wait_for_timeout(5000)
                    rendered = tab.content()
                    browser.close()
            except Exception:
                rendered = ""
            if not rendered:
                req = urllib.request.Request(base, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
                })
                with urllib.request.urlopen(req, timeout=12) as response:
                    rendered = response.read(3_000_000).decode("utf-8", "ignore")
            _BOOKMAKER_PAGE_CACHE[site] = rendered
        page = _BOOKMAKER_PAGE_CACHE[site]
        nh, na = _norm_team(home), _norm_team(away)
        if nh and na:
            # Esamina i link del sito e il contesto testuale attorno a ciascuno.
            # Un link viene promosso a "diretto" soltanto se entrambi i nomi
            # compaiono vicino all'URL specifico dell'evento.
            for m in re.finditer(r"""(?:href|url)\s*=\s*["']([^"']+)["']""", page, re.I):
                raw_url = html.unescape(m.group(1)).replace("&amp;", "&")
                url = urllib.parse.urljoin(base, raw_url)
                if not url_re.fullmatch(url) or url.rstrip("/") == base.rstrip("/"):
                    continue
                lo, hi = max(0, m.start()-1800), min(len(page), m.end()+1800)
                chunk = _norm_team(page[lo:hi])
                if nh in chunk and na in chunk:
                    found = url
                    break
    except Exception:
        pass
    _BOOKMAKER_CACHE[key] = found
    return found

def bookmaker_badges(home, away, li=None):
    """Genera le due targhette: verde/blu solo per link evento verificati, grigie altrimenti."""
    out = []
    for site, label, base, css in (
        ("bet365", "bet365", "https://www.bet365.it/", "book-b365"),
    ):
        url = _bookmaker_event(site, home, away)
        direct = bool(url)
        fallback = "https://www.bet365.it/"
        if not direct and site == "bet365" and li is not None:
            lid = LEAGUES[li][2]
            fallback = bet365_url(lid)   # pagina del campionato (o pagina Calcio)
            if lid in BET365_HUB: direct = True
        href = html.escape(url or fallback, quote=True)
        state = " direct" if direct else " generic"
        out.append(f'<a class="book {css}{state}" href="{href}" target="_blank" rel="noopener">{label}</a>')
    return " ".join(out)

LAB = {"goal": "GOAL"}
LAB2 = LAB
VENUES = (
    ("all", "Totali", "tutte le partite, in casa o in trasferta"),
    ("home", "Casa", "solo le partite giocate in casa"),
    ("away", "Trasferta", "solo le partite giocate in trasferta"),
)
THEMES = [
    ("notte", "Notte verde", dict(bg="#000000", fg="#e8e8e8", accent="#00ff88", accent2="#10e07a", card="#0b0f0c", card2="#07140c", ink="#d9ffe9", muted="#88aa99", dim="#aaaaaa", line="#00ff8855", soft="#00ff8822", pop="#050805", side="#030805", on="#000000", bad="#ff5c5c", ok="#2e9e5b", onbad="#1a0000", glow="0 0 18px #00ff8822", head="inherit", radius="10px", scheme="dark")),
    ("chiaro", "Chiaro", dict(bg="#f4f7f4", fg="#14261c", accent="#0b7a43", accent2="#14915a", card="#ffffff", card2="#e7f6ee", ink="#143024", muted="#3e5c4c", dim="#5c6f64", line="#0b7a4444", soft="#0b7a4414", pop="#ffffff", side="#e7f3ec", on="#ffffff", bad="#c62828", ok="#0b7a43", onbad="#ffffff", glow="0 8px 22px #14261c18", head="inherit", radius="12px", scheme="light")),
    ("oceano", "Oceano", dict(bg="#061018", fg="#e7f7ff", accent="#3ecfff", accent2="#7ee7ff", card="#0b1b28", card2="#08202e", ink="#dff6ff", muted="#8eb4c6", dim="#9ec0d0", line="#3ecfff55", soft="#3ecfff22", pop="#07141f", side="#041018", on="#041018", bad="#ff6b6b", ok="#1aa37a", onbad="#1a0000", glow="0 0 18px #3ecfff33", head="inherit", radius="12px", scheme="dark")),
    ("bordeaux", "Bordeaux", dict(bg="#14080c", fg="#f8ecec", accent="#e6c27a", accent2="#f0d7a2", card="#241016", card2="#1c0c12", ink="#f8e8d0", muted="#c8a9a0", dim="#b89898", line="#e6c27a55", soft="#e6c27a22", pop="#1a0a0e", side="#10060a", on="#1a0c08", bad="#ff6b6b", ok="#c9a227", onbad="#1a0000", glow="0 0 18px #e6c27a33", head="Georgia,'Times New Roman',serif", radius="8px", scheme="dark")),
    ("tramonto", "Tramonto", dict(bg="#1a0e08", fg="#fff1e6", accent="#ff8a3d", accent2="#ffb07a", card="#2a160e", card2="#23140c", ink="#ffe8d6", muted="#e0b59a", dim="#c09070", line="#ff8a3d55", soft="#ff8a3d22", pop="#1c0e08", side="#140a06", on="#1a0a04", bad="#ff5c5c", ok="#e07a20", onbad="#1a0000", glow="0 0 18px #ff8a3d33", head="inherit", radius="14px", scheme="dark")),
    ("viola", "Viola", dict(bg="#120816", fg="#f7ecff", accent="#d580ff", accent2="#eab6ff", card="#1e1028", card2="#180c22", ink="#f4e6ff", muted="#c9a8dc", dim="#b898cc", line="#d580ff55", soft="#d580ff22", pop="#140a18", side="#0e0612", on="#1a0624", bad="#ff6b8a", ok="#b06cff", onbad="#1a0008", glow="0 0 18px #d580ff33", head="inherit", radius="14px", scheme="dark")),
    ("cielo", "Cielo", dict(bg="#e8f2fc", fg="#102033", accent="#0d47a1", accent2="#1976d2", card="#ffffff", card2="#f3f8fd", ink="#102033", muted="#3d5270", dim="#5a6d84", line="#0d47a155", soft="#0d47a114", pop="#ffffff", side="#f4f8fc", on="#ffffff", bad="#c62828", ok="#1565c0", onbad="#ffffff", glow="0 8px 22px #10203314", head="inherit", radius="16px", scheme="light")),
    ("carta", "Carta", dict(bg="#f6f1e6", fg="#2b2416", accent="#8a4b12", accent2="#b56a2b", card="#fffaf3", card2="#f3eadb", ink="#2b2416", muted="#6b5438", dim="#7d6a52", line="#8a4b1255", soft="#8a4b1214", pop="#fffaf3", side="#efe6d6", on="#ffffff", bad="#9d1c1c", ok="#5f6b2c", onbad="#ffffff", glow="0 8px 18px #2b241614", head="Georgia,'Times New Roman',serif", radius="4px", scheme="light")),
    ("foresta", "Foresta", dict(bg="#07140c", fg="#e9ffd8", accent="#c6ff4a", accent2="#9be04a", card="#0e2416", card2="#0b1c12", ink="#e7ffd0", muted="#a8c898", dim="#88aa88", line="#c6ff4a55", soft="#c6ff4a22", pop="#08160e", side="#05110a", on="#0c1a08", bad="#ff6b6b", ok="#7dce3a", onbad="#1a0000", glow="0 0 18px #c6ff4a33", head="inherit", radius="10px", scheme="dark")),
    ("stadio", "Stadio", dict(bg="#120206", fg="#ffe8ee", accent="#ff3355", accent2="#ff6b81", card="#24060e", card2="#1a040a", ink="#ffe0e6", muted="#e0a0ae", dim="#c08090", line="#ff335555", soft="#ff335522", pop="#160208", side="#0c0204", on="#ffffff", bad="#ffd166", ok="#ff3355", onbad="#1a0a04", glow="0 0 16px #ff335533", head="'Arial Black',Impact,sans-serif", radius="0px", scheme="dark")),
]
THEME_VARS = ["bg","fg","accent","accent2","card","card2","ink","muted","dim","line","soft","pop","side","on","bad","ok","onbad","glow","head","radius"]

def esc(x):
    return html.escape(str(x), quote=True)

def num_it(x):
    return f"{float(x):.2f}".replace(".", ",")

def gg_txt(g):
    if not g:
        return ""
    hits, n, pct = g
    return f" 🟢 GG {pct}%" if n >= 10 else f" 🟢 GG {pct}% ({hits}/{n})"

def gg_html(g):
    if not g:
        return ""
    hits, n, pct = g
    label = f"🟢 GG {pct}%" if n >= 10 else f"🟢 GG {pct}% ({hits}/{n})"
    title = f"Segnano entrambe (GG) nelle ultime {n} partite: {hits} su {n}."
    return f' <span class="gg" title="{esc(title)}">{label}</span>'

def xg_pieces(xg, pairs):
    out = []
    for tid, name in pairs:
        info = (xg or {}).get(str(tid))
        if not info or info.get("for") is None:
            continue
        af = round(float(info["for"]), 2)
        played = float(info["played"])
        nplay = str(int(played)) if played.is_integer() else num_it(played)
        if info.get("against") is None:
            title = f"Media xG fatti a partita su {nplay} gare della fase o stagione corrente (FotMob). xG subiti non disponibile."
            plain = f"{name} xG fatti {num_it(af)}"
            block = f'<span class="xg" title="{esc(title)}">{esc(name)} <b>xG fatti {num_it(af)}</b></span>'
        else:
            aa = round(float(info["against"]), 2)
            tot = round(af + aa, 2)
            title = f"Media xG totali a partita su {nplay} gare della fase o stagione corrente (FotMob): fatti {num_it(af)} + subiti {num_it(aa)}."
            plain = f"{name} xG {num_it(tot)} ({num_it(af)}+{num_it(aa)})"
            block = f'<span class="xg" title="{esc(title)}">{esc(name)} <b>xG {num_it(tot)}</b> <small>({num_it(af)}+{num_it(aa)})</small></span>'
        out.append((plain, block))
    return out

def vwrap(venue, inner):
    _key, label, desc = next(x for x in VENUES if x[0] == venue)
    return f'<div class="venue" data-v="{venue}"><p class="vnote">Vista <b>{esc(label)}</b> · {esc(desc)}</p>{inner}</div>'

def _scope_phrase(venue):
    if venue == "home":
        return "in casa"
    if venue == "away":
        return "in trasferta"
    return "valide"

def _ritardo_line(venue):
    if venue == "home":
        return "Ritardo = partite IN CASA consecutive senza la combo. Si contano solo le gare in cui la squadra gioca in casa."
    if venue == "away":
        return "Ritardo = partite IN TRASFERTA consecutive senza la combo. Si contano solo le gare in cui la squadra gioca in trasferta."
    return "Ritardo = partite di campionato consecutive senza la combo (segno della partita, casa o trasferta indifferente)."

def render_venue(data, venue, now):
    label = next(x[1] for x in VENUES if x[0] == venue)
    scope = _scope_phrase(venue)
    goal_L = [f"RITARDI DOPPIA CHANCE + GOAL — {label.upper()}", f"Aggiornato: {now} (ora italiana)",
              _ritardo_line(venue),
              "Include la stagione precedente solo se la squadra era nella stessa divisione. '+' = mai uscita nel periodo considerato.",
              "🔴 = squadra tra le prime 3 per uscite della combo (le più frequenti, pari merito inclusi) nel suo campionato.",
              "🟢 xx% = nelle partite del ritardo attuale, % con almeno 2 gol totali o entrambe a segno (mostrato se >= 50%).",
              "Fonte: FotMob", ""]
    sotto_L = [f"SOTTOFREQUENZE - DOPPIA CHANCE + GOAL (ultime {SOTTO_N} partite nazionali {scope})",
               f"Aggiornato: {now} (ora italiana)",
               "Le 5 squadre con più uscite della combo (pari merito inclusi). Incluse neopromosse/retrocesse quando lo storico nazionale è disponibile. Classifica per numero di uscite, dalla più frequente alla meno frequente; incluse solo squadre con almeno 100 partite nazionali " + scope + " (N<100 = storico insufficiente). Fonte: FotMob", ""]
    pop = {}
    cf = []
    for LI, (c, l, r, err) in enumerate(data):
        goal_L += ["=" * 50, f"{c} - {l}"]
        sotto_L += ["=" * 50, f"{c} - {l}", "=" * 50]
        if err or not r:
            goal_L += [f"  dati non disponibili ({err})", ""]
            sotto_L += ["  dati non disponibili", ""]
            continue
        view = r["venues"][venue]
        cs, ps, n = r["cs"], r["ps"], r["n"]
        red = red_sets(view["sotto"])
        lg = f"{c} - {l}"
        goal_L.append(f"Stagione {cs} ({n} partite giocate)" + (f" + {ps}" if ps else ""))
        fl = freq_league_line(lg)
        if fl:
            goal_L.append(fl)
        goal_L.append("=" * 50)
        for name, rows in view["res"]["goal"]:
            goal_L.append(f"RITARDI {name}")
            for i, (streak, t, full, pct) in enumerate(rows, 1):
                dot = f"  🟢 {pct}%" if streak and pct >= 50 else ""
                if t in red.get(name, ()):
                    dot += "  🔴"
                bdg = league_badge_txt(lg, name)
                if bdg:
                    dot += f"  {bdg}"
                goal_L.append(f"  {i:>2}. {t:<30} {str(streak)+('+' if full else ''):>4}{dot}")
            goal_L.append("")
        for name, rows in view["sotto"]:
            sotto_L.append(f"SOTTOFREQUENZA {name}")
            N, last = view["sinfo"].get(name, (len(rows), None))
            for i, (k, nn, t) in enumerate(rows, 1):
                sotto_L.append(f"  {f'{i}/{N}':>6} {t:<30} {k}/{nn}")
            if last and N > len(rows):
                sotto_L += ["     ...", f"  {f'{N}/{N}':>6} {last[2]:<30} {last[0]}/{last[1]}  (la fa meno spesso)"]
            sotto_L.append("")
        up, teams, allr, gg = r["up"], r["teams"], view["allr"], view["gg"]
        pop[LI] = {"lg": lg,
                   "rit": {name: [[t, streak, full, pct, league_badge_txt(lg, name)] for streak, t, full, pct in rows] for name, rows in view["res"]["goal"]},
                   "sotto": {name: [[t, k2, nn] for k2, nn, t in rows] for name, rows in view["sotto"]},
                   "tab": view["tab"],
                   "stot": {k: [val[0], [val[1][2], val[1][0], val[1][1]] if val[1] else None] for k, val in view["sinfo"].items()}}
        for t, h, a in up:
            info, tags = [], []
            for tid in _fixture_sides(venue, h, a):
                tn = teams[tid]
                parts, hparts = [], []
                for key, name, streak, _, full, pct in allr.get(tn, []):
                    if key != "goal" or streak < SOGLIA_GOAL:
                        continue
                    rr = [x for x in (teams[h], teams[a]) if x in red.get(name, ())]
                    bdg = league_badge_txt(lg, name)
                    bhtml = league_badge_html(lg, name)
                    parts.append(f"{name} ({streak}{'+' if full else ''})" + (f" {bdg}" if bdg else "") + "".join(f" 🔴 {x}" for x in rr))
                    hparts.append(f'{esc(name)} <span class="pp" data-k="{LI}" data-v="{venue}" data-c="{esc(name)}" data-t="{esc(tn)}">({streak}{"+" if full else ""})</span>{bhtml}'
                                  + "".join(f' <span class="pr" data-k="{LI}" data-v="{venue}" data-c="{esc(name)}" data-t="{esc(x)}">🔴 {esc(x)}</span>' for x in rr))
                if parts:
                    info.append((tn, parts, gg.get(tn)))
                    tags.append(("goal", tn, parts, hparts, gg.get(tn)))
            if info:
                xgp = xg_pieces(r["xg"], ((h, teams[h]), (a, teams[a])))
                nms = [p.split(" (")[0] for _k, _tn, ps, _hp, _g in tags for p in ps]
                dh, dt = dbadges(view["danger"], lg, nms)
                cf.append((t, c, l, teams[h], teams[a], tags, info, LI, xgp, dh, dt))
    sal = []
    for c, l, r, err in data:
        if not r:
            continue
        teams = r["teams"]
        for mt, h, a, gh, ga, tn, key, nm, run in r["venues"][venue]["salt"]:
            sal.append((mt, c, l, teams.get(h, h), teams.get(a, a), gh, ga, tn, key, nm, run))
    sal.sort(key=lambda x: (-x[0].timestamp(), x[1], x[7]))
    ST = [f"SALTATI - RITARDI >= {SALTATI_MIN} SPEZZATI NEGLI ULTIMI {SALTATI_GIORNI} GIORNI — {label.upper()}",
          f"Aggiornato: {now} (ora italiana). Dal più recente. {_ritardo_line(venue)} Fonte: FotMob", ""]
    SH = []
    for mt, c, l, hn, an, gh, ga, tn, key, nm, run in sal:
        lt = mt.astimezone(ROME)
        bdg = league_badge_txt(f"{c} - {l}", nm)
        bhtml = league_badge_html(f"{c} - {l}", nm)
        ST.append(f"{lt:%d/%m %H:%M}  [{LAB2[key]}] {tn}: {nm} uscita, era a {run}{(' ' + bdg) if bdg else ''}  -  {hn} {gh}-{ga} {an}   [{c} - {l}]")
        SH.append(f'<div class="fx"><div class="fxh"><span class="time">{lt:%d/%m %H:%M}</span> {esc(hn)} <b>{gh}-{ga}</b> {esc(an)} <span class="lg">{esc(c)} - {esc(l)}</span></div><div class="tagrow"><span class="tag goal">{LAB2[key]}</span> <b>{esc(tn)}</b>: {esc(nm)} uscita, <b>era a {run}</b>{bhtml}</div></div>')
    if not sal:
        ST.append("Nessun ritardo spezzato negli ultimi giorni.")
        SH.append("<p>Nessun ritardo spezzato negli ultimi giorni.</p>")
    return {
        "goal": "\n".join(goal_L) + "\n",
        "sotto": "\n".join(sotto_L) + "\n",
        "cards": cf,
        "saltati": "\n".join(ST) + "\n",
        "saltati_html": vwrap(venue, '<div class="fxlist">' + "\n".join(SH) + "</div>"),
        "goal_html": vwrap(venue, "<pre>" + html.escape("\n".join(goal_L) + "\n") + "</pre>"),
        "sotto_html": vwrap(venue, "<pre>" + html.escape("\n".join(sotto_L) + "\n") + "</pre>"),
        "pop": pop,
    }

def _bundle(chunks, key):
    blocks = []
    for venue, label, _desc in VENUES:
        blocks += ["#" * 50, f"# {label.upper()}", "#" * 50, "", chunks[venue][key].rstrip(), ""]
    return "\n".join(blocks) + "\n"

VENUE_TAG = {"all": "TOTALE", "home": "CASA", "away": "TRASFERTA"}

def render_prossime(chunks, now):
    """Una scheda per contesto, raggruppata sulla stessa partita: TOTALE, poi CASA, poi TRASFERTA."""
    groups = {}
    for venue, _label, _desc in VENUES:
        for t, c, l, hn, an, tags, info, LIX, xgp, dh, dt in chunks[venue]["cards"]:
            key = (t.isoformat(), c, l, hn, an)
            g = groups.setdefault(key, {"t": t, "c": c, "l": l, "hn": hn, "an": an, "by": {}})
            g["by"][venue] = (tags, info, LIX, xgp, dh, dt)
    ordered = sorted(groups.values(), key=lambda g: (g["t"], g["c"], g["hn"]))
    note = ("La stessa partita può comparire più volte, una scheda per contesto, in quest'ordine: "
            "TOTALE (entrambe le squadre, ritardi complessivi), CASA (solo chi gioca in casa, ritardi delle sue gare in casa), "
            "TRASFERTA (solo chi gioca fuori, ritardi delle sue gare in trasferta). "
            "Una scheda c'è solo se in quel contesto almeno una combo è sopra soglia. "
            "1 = vince chi gioca in casa, 2 = vince chi gioca fuori, X = pareggio, 12 = non pareggio (con GOAL = segnano entrambe). "
            "Il passaggio sul nome della squadra mostra sempre la classifica totale, con i punti delle ultime 5 partite.")
    full_header = [f"PROSSIME PARTITE ({GIORNI} GIORNI) - SQUADRE IN RITARDO",
                   f"Aggiornato: {now} (ora italiana)",
                   f"Soglia: combo Goal ritardo >= {SOGLIA_GOAL}. Orari in ora italiana. {note} "
                   "🟢 GG = segnano entrambe nelle ultime 10 partite di quel contesto (totale, casa o trasferta). "
                   "xG = media a partita fatti+subiti, fase/stagione FotMob, nascosto se assente; non è diviso casa/trasferta. "
                   "🔴 Squadra = tra le 3 con più uscite di quella combo (pari merito inclusi), nel contesto della scheda. "
                   "[ALT combo] = negli ultimi 10 giorni nel campionato è saltato almeno un ritardo top 5 (e >= 6) su quella combo; [OK combo] = nessuno. Fonte: FotMob", ""]
    goal_header = [f"PROSSIME PARTITE ({GIORNI} GIORNI) - COMBO + GOAL - SQUADRE IN RITARDO",
                   f"Aggiornato: {now} (ora italiana)",
                   f"Soglia ritardo >= {SOGLIA_GOAL}. Orari in ora italiana. {note} "
                   "🟢 GG = segnano entrambe nelle ultime 10 partite di quel contesto. "
                   "xG = media a partita (fatti + subiti) se FotMob la pubblica; è di stagione, non diviso casa/trasferta. "
                   "🔴 Squadra = tra le 3 con più uscite di quella combo. Fonte: FotMob", ""]
    leg = (f'<p class="leg">Soglia ritardo &ge; {SOGLIA_GOAL} (Goal) &middot; orari italiani '
           f'&middot; <span class="tag goal">GOAL</span> &middot; 🔴 = prime 3 per frequenza (più uscite) '
           f'&middot; <span class="gg">🟢 GG</span> = segnano entrambe nelle ultime 10 partite di quel contesto '
           f'(se sono meno di 10 si vede il rapporto) &middot; xG = media a partita, fatti + subiti, '
           f'della fase o stagione FotMob. Se il campionato non pubblica l&rsquo;xG, la riga non compare. '
           f'L&rsquo;xG è di stagione e non è diviso tra casa e trasferta. '
           f'La stessa partita può uscire più volte, in ordine: '
           f'<span class="vtag all">TOTALE</span> entrambe le squadre, '
           f'<span class="vtag home">CASA</span> solo chi gioca in casa, '
           f'<span class="vtag away">TRASFERTA</span> solo chi gioca fuori. '
           f'Il passaggio sul nome mostra sempre la classifica totale, con i punti delle ultime 5.</p>')
    P, PG, H = list(full_header), list(goal_header), []
    day = None
    if not ordered:
        msg = "Nessuna partita nei prossimi giorni con ritardi sopra soglia."
        P.append(msg)
        PG.append(msg)
        H.append(f"<p>{msg}</p>")
    for g in ordered:
        lt = g["t"].astimezone(ROME)
        d0 = lt.strftime("%d/%m/%Y")
        if d0 != day:
            P += ["", "=" * 50, d0, "=" * 50]
            PG += ["", "=" * 50, d0, "=" * 50]
            H.append(f'<h3 class="day">{d0}</h3>')
            day = d0
        hn, an, c, l = g["hn"], g["an"], g["c"], g["l"]
        for venue, _label, _desc in VENUES:
            item = g["by"].get(venue)
            if not item:
                continue
            tags, _info, LIX, xgp, dh, dt = item
            mark = VENUE_TAG[venue]
            P.append(f"{mark:<9} {lt:%H:%M}  {hn} vs {an}   [{c} - {l}]  {dt}")
            PG.append(f"{mark:<9} {lt:%H:%M}  {hn} vs {an}   [{c} - {l}]")
            if xgp:
                line = " · ".join(p for p, _h in xgp)
                P.append(f"           xG: {line}")
                PG.append(f"           xG: {line}")
            hb = []
            for KEY, tn, parts, hparts, ggv in tags:
                P.append(f"           [{LAB[KEY]}] {tn}{gg_txt(ggv)}: " + "; ".join(parts))
                PG.append(f"           {tn}{gg_txt(ggv)}: " + "; ".join(parts))
                hb.append(f'<div class="tagrow"><span class="tag goal">{LAB[KEY]}</span> <b>{tspan(LIX, hn, an, tn)}</b>{gg_html(ggv)}: ' + "; ".join(hparts) + "</div>")
            xg_html = ('<div class="xgline">' + " · ".join(h for _p, h in xgp) + "</div>") if xgp else ""
            H.append(
                f'<div class="fx"><span class="vtag {venue}">{mark}</span>'
                f'<div class="fxh"><span class="time copy-time" data-copy="{esc(hn + " vs " + an)}" title="Clicca per copiare la partita">{lt:%H:%M}</span> '
                f'{tspan(LIX, hn, an, hn)} vs {tspan(LIX, hn, an, an)} '
                f'<span class="lg">{esc(c)} - {esc(l)}</span> {dh} {bookmaker_badges(hn, an, LIX)}</div>{xg_html}'
                + "".join(hb) + "</div>"
            )
    return {"html": leg + '<div class="fxlist">' + "\n".join(H) + "</div>",
            "txt": "\n".join(P) + "\n",
            "goal": "\n".join(PG) + "\n"}

def _theme_css():
    out = []
    for tid, _label, spec in THEMES:
        sel = ':root, html[data-theme="notte"]' if tid == "notte" else f'html[data-theme="{tid}"]'
        decls = "".join(f"--{k}:{spec[k]};" for k in THEME_VARS) + f"color-scheme:{spec['scheme']};"
        out.append(f"{sel}{{{decls}}}")
    return "".join(out)

def _page_css():
    return _theme_css() + """
:root{--bar-h:52px}
@media(max-width:700px){:root{--bar-h:52px}}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0 auto;padding:1rem;padding-top:calc(var(--bar-h) + .5rem);background:var(--bg);color:var(--fg);max-width:1100px}
h1{color:var(--accent);text-shadow:0 0 12px var(--soft);font-size:clamp(1.4rem,5vw,2.2rem);font-family:var(--head)}
h2{color:var(--accent2);border-left:4px solid var(--accent);padding-left:.6rem;margin-top:2rem;font-family:var(--head)}
b{color:var(--accent)}
pre{background:var(--card);color:var(--ink);padding:1rem;overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--glow);font-size:clamp(.72rem,2.6vw,.92rem);line-height:1.45;white-space:pre}
h3.day{color:var(--accent);margin:1.4rem 0 .5rem;border-bottom:1px solid var(--line)}
.fx{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:.6rem .8rem;margin:.5rem 0;box-shadow:var(--glow)}
.fxh{font-weight:600;color:var(--fg)}.time{color:var(--accent);margin-right:.4rem}
.copy-time{cursor:pointer;border-bottom:1px dotted var(--accent)}.copy-time:hover{color:var(--fg)}
.lg{color:var(--muted);font-weight:400;font-size:.85em;margin-left:.4rem}
.tagrow{margin-top:.35rem;line-height:1.5}
.tag{display:inline-block;padding:.05rem .5rem;border-radius:6px;font-size:.78em;font-weight:700}
.tag.goal{background:var(--ok);color:var(--on)}.tag.over{background:#d9822b;color:#000}
.leg{color:var(--dim)}.pt{cursor:pointer;border-bottom:1px dotted var(--muted)}
.vtag{display:inline-block;margin:0 0 .28rem;padding:.08rem .5rem;border-radius:999px;font-size:.68rem;font-weight:800;letter-spacing:.05em;line-height:1.35}
.vtag.all{background:var(--accent);color:var(--on)}
.vtag.home{background:#2f6fed;color:#fff}
.vtag.away{background:#c4922a;color:#1a1004}
.leg .vtag{margin:0 .15rem;vertical-align:middle}
.pp,.pr{cursor:pointer;border-bottom:1px dashed var(--accent)}.pp{color:var(--accent);font-weight:700}
.vnote{color:var(--muted);margin:.1rem 0 .7rem}.gg{color:var(--accent);font-weight:800;white-space:nowrap}
.xgline{margin-top:.35rem;color:var(--muted);font-size:.86em;font-weight:600;line-height:1.45}
.xgline b{color:var(--accent)}.xgline small{color:var(--dim);font-weight:600}
#pop{position:absolute;z-index:280;display:none;background:var(--pop);border:1px solid var(--accent);border-radius:var(--radius);box-shadow:var(--glow);padding:.6rem .8rem;max-width:min(92vw,440px);font-size:.9em;color:var(--fg)}
#pop .fm{color:var(--muted);font-weight:650}
#pop h4{margin:0 0 .4rem;color:var(--accent);font-size:.95em}#pop table{border-collapse:collapse;width:100%}
#pop td{padding:.12rem .35rem;border-bottom:1px solid var(--line)}#pop td.n{text-align:right;color:var(--accent);font-weight:700}
#pop tr.hl td{background:var(--soft);color:var(--fg);font-weight:700}
.tip{background:var(--card2);border:1px solid var(--accent);border-radius:var(--radius);padding:.7rem .9rem;margin:.6rem 0;box-shadow:var(--glow)}
.tiph{font-weight:700;color:var(--fg)}
.rk{display:inline-block;min-width:1.7em;height:1.7em;line-height:1.7em;text-align:center;border-radius:50%;background:var(--accent);color:var(--on);margin-right:.5rem}
.tipc{margin:.4rem 0}.tipc .vtag{margin:0 .35rem 0 0;vertical-align:middle}.sc{color:var(--accent);font-weight:700;margin-left:.15rem}.det{color:var(--muted);font-size:.8em;margin-left:.4rem}
.tip p{margin:.3rem 0 0;color:var(--ink)}
details.rules{color:var(--dim);margin:.5rem 0 1rem}details.rules summary{color:var(--accent);cursor:pointer}
#totop{position:fixed;right:12px;bottom:14px;z-index:99;width:48px;height:48px;border-radius:50%;border:2px solid var(--accent);background:color-mix(in srgb, var(--bg) 88%, transparent);color:var(--accent);font-size:1.5rem;font-weight:bold;cursor:pointer;box-shadow:var(--glow);opacity:0;pointer-events:none;transition:opacity .2s}
#totop.on{opacity:1;pointer-events:auto}#totop:active{background:var(--accent);color:var(--on)}
#side{position:fixed;left:0;top:var(--bar-h);bottom:0;width:190px;z-index:120;background:var(--side);border-right:1px solid var(--line);padding:1rem .7rem;overflow-y:auto;display:flex;flex-direction:column;gap:.5rem;box-shadow:4px 0 18px #0006}
#side a{text-decoration:none;display:block}
#side a.sbig{background:linear-gradient(135deg,var(--accent),var(--accent2));color:var(--on);font-weight:800;font-size:1.05rem;border-radius:12px;padding:.85rem .7rem;line-height:1.2;box-shadow:var(--glow);display:flex;gap:.5rem;align-items:center}
#side a.sbig span{color:var(--on)}#side a.sbig:hover{filter:brightness(1.08)}
#side a.ssm{color:var(--accent);border:1px solid var(--line);border-radius:8px;padding:.4rem .6rem;font-size:.85rem}
#side a.ssm:hover,#side a.ssm.active{background:var(--accent);color:var(--on) !important;font-weight:800}
#side details.stext summary{color:var(--accent);border:1px dashed var(--line);border-radius:8px;padding:.4rem .6rem;font-size:.85rem;cursor:pointer;font-weight:700}
#side details.stext a{color:var(--muted);font-size:.78rem;padding:.25rem .6rem}#side details.stext a:hover{color:var(--accent)}
#hamb{display:none;position:fixed;left:10px;top:calc(var(--bar-h) + 8px);z-index:230;width:44px;height:44px;border-radius:10px;border:2px solid var(--accent);background:color-mix(in srgb, var(--bg) 88%, transparent);color:var(--accent);font-size:1.4rem;cursor:pointer}
@media (min-width:901px){body{margin-left:max(210px,calc((100vw - 1100px)/2))}}
@media (max-width:900px){#hamb{display:block}#side{transform:translateX(-105%);transition:transform .2s;width:220px;padding-top:3.4rem}#side.open{transform:none}h1{margin-top:3.2rem}}
.dz{display:inline-block;padding:.05rem .45rem;border-radius:6px;font-size:.72em;font-weight:800;margin-left:.3rem;vertical-align:middle}
.dz.bad{background:var(--bad);color:var(--onbad);cursor:pointer}.dz.ok{background:var(--ok);color:var(--on)}
#side a.sbig,#side a.sbig:link,#side a.sbig:visited,#side a.sbig:hover,#side a.sbig:active,#side a.sbig:focus,#side a.sbig *{color:var(--on) !important}
.book,.book:link,.book:visited{display:inline-block;padding:.05rem .45rem;border-radius:6px;font-size:.72em;font-weight:800;text-decoration:none;margin-left:.3rem;vertical-align:middle}
.book-b365.direct,.book-b365.direct:link,.book-b365.direct:visited{background:#20b957;color:#fff !important}
.book.generic,.book.generic:link,.book.generic:visited{background:#c5c5c5;color:#111 !important}.book:hover{filter:brightness(1.12)}
#side a.sbig.active{outline:3px solid var(--fg);outline-offset:2px}
#zoom{position:fixed;top:calc(var(--bar-h) + 8px);right:10px;z-index:140;display:flex;gap:6px}
#zoom button{width:44px;height:44px;border-radius:50%;border:2px solid var(--accent);background:color-mix(in srgb, var(--bg) 88%, transparent);color:var(--accent);font-size:1.5rem;font-weight:bold;cursor:pointer;box-shadow:var(--glow)}
#zoom button:active{background:var(--accent);color:var(--on)}
#topbar{position:fixed;left:0;right:0;top:0;z-index:250;display:flex;flex-wrap:wrap;align-items:center;gap:.45rem .6rem;padding:.45rem .75rem;background:var(--bg);border-bottom:1px solid var(--line);box-shadow:var(--glow)}
#topbar,#topbar button,#topbar select{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
#topbar .tsel{margin-left:auto;display:flex;align-items:center;gap:.35rem;color:var(--muted);font-size:.8rem;font-weight:700}
#topbar select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:.32rem .45rem;font-weight:700;font-size:.84rem}
.venue{display:block;margin:0 0 1.4rem}
"""

PAGE = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ritardi Combo</title>
<script>(function(){var okt={notte:1,chiaro:1,oceano:1,bordeaux:1,tramonto:1,viola:1,cielo:1,carta:1,foresta:1,stadio:1};var q=null;try{q=new URLSearchParams(location.search)}catch(e){}var t=(q&&q.get('tema'))||localStorage.getItem('themeRC')||'notte';if(!okt[t])t='notte';document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('themeRC',t)}catch(e){}})();</script>
<style>___CSS___</style></head><body>
<div id="topbar">
  <label class="tsel" for="theme">Tema <select id="theme">___THEMEOPTS___</select></label>
</div>
<div id="zoom"><button onclick="z(-1)" aria-label="Riduci">−</button><button onclick="z(1)" aria-label="Ingrandisci">+</button></div>
<script>var Z=parseFloat(localStorage.getItem('zoomRC')||'1');function ap(){document.querySelectorAll('pre').forEach(function(p){p.style.fontSize='calc(clamp(.72rem,2.6vw,.92rem)*'+Z+')'});document.querySelectorAll('.fxlist').forEach(function(f){f.style.fontSize=(Z*100)+'%'})}function z(d){Z=Math.min(3,Math.max(0.5,Math.round((Z+d*0.1)*10)/10));localStorage.setItem('zoomRC',Z);ap()}document.addEventListener('DOMContentLoaded',ap);</script>
<h1>Ritardi Combo Doppia Chance</h1>
<p>Ultimo aggiornamento: <b>___NOW___</b> (ora italiana) &middot; si aggiorna ogni 6 ore</p>
<p class="leg">Totali, Casa e Trasferta sono nella stessa pagina, una sotto l&rsquo;altra. In Prossime partite la stessa gara può comparire più volte: prima <b>TOTALE</b>, poi <b>CASA</b> e/o <b>TRASFERTA</b>. Il passaggio sul nome apre sempre la classifica totale, con i punti delle ultime 5 partite.</p>
<button id="hamb" aria-label="Menu" onclick="document.getElementById('side').classList.toggle('open')">☰</button>
<aside id="side" onclick="if(event.target.closest('a.sbig,a.ssm'))this.classList.remove('open')">
<a class="sbig" href="#tips">🎯<span>TIPS DEL GIORNO</span></a>
<a class="sbig" href="#prossime">📅<span>PROSSIME PARTITE</span></a>
<a class="ssm" href="#goal">Ritardi + GOAL</a><a class="ssm" href="#frequenza">Frequenza campionati</a><a class="ssm" href="#sotto">Sottofrequenze</a><a class="ssm" href="#saltati">Saltati</a>
<details class="stext"><summary>TEXT</summary><a href="tips_del_giorno.txt">tips_del_giorno.txt</a><a href="prossime_partite.txt">prossime_partite.txt</a><a href="ritardi_goal.txt">ritardi_goal.txt</a><a href="frequenza_campionati.txt">frequenza_campionati.txt</a><a href="sottofrequenze.txt">sottofrequenze.txt</a><a href="saltati.txt">saltati.txt</a></details>
</aside>
<h2 id="tips">TIPS DEL GIORNO</h2>
___TIPS___
<details class="rules"><summary>Come viene calcolato il punteggio</summary><ul>___RULES___</ul></details>
<h2 id="sotto">Sottofrequenze (ultime 100 partite)</h2>
___SOTTO___
<h2 id="prossime">Prossime partite (5 giorni)</h2>
___PROSSIME___
<h2 id="goal">Sezione 1 - 1X+Goal, X2+Goal, 12+Goal</h2>
___GOAL___
<h2 id="frequenza">Frequenza campionati</h2>
<p class="leg">Solo stagione in corso, tutte le partite (non casa/trasferta). 1 ogni N = partite giocate / uscite. Servono almeno 7 giornate. 🔥 = primi 7, ❗ = posizioni 8-14, 👻 = ultimi 10: lo stesso badge compare accanto ai ritardi, anche in Casa e Trasferta.</p>
<pre>___FREQUENZA___</pre>
<h2 id="saltati">Saltati (ritardi &ge; ___SALTMIN___ spezzati, ultimi ___SALTDAYS___ giorni)</h2>
___SALTATI___
<button id="totop" aria-label="Torna su" title="Torna su" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑</button>
<script>window.addEventListener("scroll",function(){document.getElementById("totop").classList.toggle("on",window.scrollY>400)},{passive:true});</script>
<div id="pop"></div>
<script>var POP=___POP___;(function(){var pop=document.getElementById('pop'),cur=null;function esc(x){return String(x).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function forma(r){return (r&&r.length>5&&r[5])?(' <span class="fm">· forma ultime '+r[5]+': '+r[4]+' pnt</span>'):''}
function pack(el){var v=(el&&el.dataset&&el.dataset.v)||'all';if(el&&el.classList.contains('pt'))return POP.all||{};return POP[v]||POP.all||{}}
function show(el){if(el.classList.contains('dz')){pop.innerHTML='<div>'+esc(el.dataset.msg)+'</div>';pop.style.display='block';var b=el.getBoundingClientRect(),w=pop.offsetWidth,x=b.left+window.scrollX;x=Math.max(window.scrollX+6,Math.min(x,window.scrollX+document.documentElement.clientWidth-w-6));pop.style.left=x+'px';pop.style.top=(b.bottom+window.scrollY+6)+'px';cur=el;return}var d=pack(el)[el.dataset.k];if(!d)return;var c=el.dataset.c,t=el.dataset.t,h;if(el.classList.contains('pt')){var A=el.dataset.a,B=el.dataset.b,tb=(d.tab||[]).filter(function(x){return x.some(function(r){return r[1]==A||r[1]==B})});if(!tb.length){h='<h4>'+esc(d.lg)+'</h4>Classifica totale non disponibile'}else{h='<h4>'+esc(d.lg)+' - Classifica totale</h4>';tb.forEach(function(x){var N=x.length;h+='<div>'+x.filter(function(r){return r[1]==A||r[1]==B}).map(function(r){return '<b style="color:var(--accent)">'+r[0]+'/'+N+'</b> '+esc(r[1])+' <b>'+r[2]+' pnt</b>'+forma(r)}).join('<br>')+'</div><details style="margin-top:.4rem"><summary style="color:var(--accent);cursor:pointer">Classifica completa</summary><table>'+x.map(function(r){return '<tr'+((r[1]==A||r[1]==B)?' class="hl"':'')+'><td>'+r[0]+'/'+N+'</td><td>'+esc(r[1])+'</td><td class="n">'+r[2]+' pnt</td><td>'+(r[5]?('ultime '+r[5]+': '+r[4]+' pnt'):'')+'</td></tr>'}).join('')+'</table></details>'})}}else if(el.classList.contains('pp')){var rows=d.rit[c]||[];h='<h4>'+esc(d.lg)+'<br>Ritardi '+esc(c)+' (top 10)</h4><table>'+rows.map(function(r,i){return '<tr'+(r[0]==t?' class="hl"':'')+'><td>'+(i+1)+'.</td><td>'+esc(r[0])+'</td><td class="n">'+r[1]+(r[2]?'+':'')+(r[4]?' '+r[4]:'')+'</td><td>'+(r[1]&&r[3]>=50?'🟢 '+r[3]+'%':'')+'</td></tr>'}).join('')+'</table>'}else{var rows=d.sotto[c]||[];var st=(d.stot||{})[c]||[rows.length,null],N=st[0];h='<h4>'+esc(d.lg)+'<br>Sottofrequenza '+esc(c)+'</h4><table>'+rows.map(function(r,i){return '<tr'+(r[0]==t?' class="hl"':'')+'><td>'+(i+1)+'/'+N+'</td><td>'+esc(r[0])+'</td><td class="n">'+r[1]+'/'+r[2]+'</td></tr>'}).join('')+(st[1]&&N>rows.length?'<tr><td colspan="3" style="text-align:center;color:var(--muted)">&middot;&middot;&middot;</td></tr><tr'+(st[1][0]==t?' class="hl"':'')+'><td>'+N+'/'+N+'</td><td>'+esc(st[1][0])+'</td><td class="n">'+st[1][1]+'/'+st[1][2]+'</td></tr>':'')+'</table>'}
pop.innerHTML=h;pop.style.fontSize=(typeof Z!=='undefined'?Z*90:90)+'%';pop.style.display='block';var b=el.getBoundingClientRect(),w=pop.offsetWidth,x=b.left+window.scrollX;x=Math.max(window.scrollX+6,Math.min(x,window.scrollX+document.documentElement.clientWidth-w-6));pop.style.left=x+'px';pop.style.top=(b.bottom+window.scrollY+6)+'px';cur=el}
function hide(){pop.style.display='none';cur=null}
document.addEventListener('click',function(e){var el=e.target.closest('.pp,.pr,.pt,.dz.bad');if(el){if(cur===el)hide();else show(el);e.stopPropagation();return}if(!pop.contains(e.target))hide()});
if(window.matchMedia('(hover:hover)').matches){document.addEventListener('mouseover',function(e){var el=e.target.closest('.pp,.pr,.pt,.dz.bad');if(el&&el!==cur)show(el)})}
document.addEventListener('keydown',function(e){if(e.key==='Escape')hide()})})();</script>
<script>(function(){function copyText(txt){if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(function(){copied()}).catch(function(){fallback(txt)})}else fallback(txt)}function copied(){var msg=document.getElementById('copymsg');if(!msg){msg=document.createElement('div');msg.id='copymsg';msg.style.cssText='position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:300;background:var(--accent);color:var(--on);padding:.65rem 1rem;border-radius:10px;font-weight:700;box-shadow:var(--glow)';document.body.appendChild(msg)}msg.textContent='Partita copiata!';msg.style.display='block';clearTimeout(msg._timer);msg._timer=setTimeout(function(){msg.style.display='none'},1600)}function fallback(txt){var ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();try{var ok=document.execCommand('copy');if(ok)copied();else alert('Seleziona e copia: '+txt)}catch(e){alert('Seleziona e copia: '+txt)}ta.remove()}document.addEventListener('click',function(e){var el=e.target.closest('.time[data-copy]');if(!el)return;copyText(el.dataset.copy);e.preventDefault();e.stopPropagation()})})();</script>
<script>(function(){var hs=[].slice.call(document.querySelectorAll('body > h2[id]')),ids=[];hs.forEach(function(h){var sec=document.createElement('section');sec.className='tabsec';sec.dataset.id=h.id;h.parentNode.insertBefore(sec,h);var n=h;while(n&&!(n!==h&&n.tagName==='H2')&&!(n.id==='pop'||n.id==='totop'||n.tagName==='SCRIPT'||n.tagName==='ASIDE'||(n.tagName==='BUTTON'))){var nx=n.nextElementSibling;sec.appendChild(n);n=nx}ids.push(h.id)});
function show(){var id=(location.hash||'').slice(1);if(ids.indexOf(id)<0)id='tips';document.querySelectorAll('section.tabsec').forEach(function(x){x.style.display=x.dataset.id===id?'':'none'});document.querySelectorAll('#side a.sbig,#side a.ssm').forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+id)});window.scrollTo(0,0);var p=document.getElementById('pop');if(p)p.style.display='none'}
window.addEventListener('hashchange',show);show()})();</script>
<script>(function(){function syncBar(){var t=document.documentElement.getAttribute('data-theme')||'notte';var sel=document.getElementById('theme');if(sel&&sel.value!==t)sel.value=t;var bar=document.getElementById('topbar');if(bar)document.documentElement.style.setProperty('--bar-h',bar.offsetHeight+'px')}
document.getElementById('theme').addEventListener('change',function(){document.documentElement.setAttribute('data-theme',this.value);try{localStorage.setItem('themeRC',this.value)}catch(err){}syncBar()});
window.addEventListener('resize',syncBar);syncBar()})();</script>
</body></html>"""

def main():
    now = datetime.datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    data = []
    pools = {}
    xg_rows = []
    for c, l, lid in LEAGUES:
        if c not in pools:
            pools[c] = country_pool(c)
        print(f"Calcolo {c} - {l}", flush=True)
        try:
            data.append((c, l, compute(lid, pools[c][0]), None))
            got = data[-1][2]["xg"]
            xg_rows.append((c, l, "ok" if got else "no", len(got)))
            print(f"  xG {'sì, '+str(len(got))+' squadre' if got else 'non disponibile'}", flush=True)
        except Exception as e:
            data.append((c, l, None, str(e)))
            xg_rows.append((c, l, "err", 0))
            print(f"  ERRORE {e}", flush=True)
        time.sleep(1)
    excluded = build_league_frequency(data)
    freq_text, n_freq = render_freq_text(now, excluded)
    print(f"Frequenza campionati: {n_freq} idonei, {len(excluded)} esclusi", flush=True)
    for label, why in excluded:
        print(f"  FUORI  {label}: {why}", flush=True)
    for name, rows in LEAGUE_FREQ.items():
        print(f"  {name}: " + ", ".join(f"{r['pos']}.{r['league']}={r['ogni'] or 'mai'}" for r in rows[:3]), flush=True)
    chunks = {venue: render_venue(data, venue, now) for venue, _label, _desc in VENUES}
    prossime = render_prossime(chunks, now)
    today = datetime.datetime.now(ROME).date()
    tips = render_tips(rank_tips(collect_tip_candidates(data, today)), data, today, now)
    print("TIPS", flush=True)
    for line in tips["txt"].splitlines():
        if line[:2].strip().isdigit() or line.startswith("    "):
            print(line, flush=True)
    open("tips_del_giorno.txt", "w").write(tips["txt"])
    open("saltati.txt", "w").write(_bundle(chunks, "saltati"))
    open("sottofrequenze.txt", "w").write(_bundle(chunks, "sotto"))
    open("prossime_partite.txt", "w").write(prossime["txt"])
    open("prossime_partite_goal.txt", "w").write(prossime["goal"])
    open("ritardi_goal.txt", "w").write(_bundle(chunks, "goal"))
    open("frequenza_campionati.txt", "w").write(freq_text)
    pop = {venue: chunks[venue]["pop"] for venue, _l, _d in VENUES}
    popjson = json.dumps(pop, ensure_ascii=False).replace("</", "<\\/")
    opts = "".join(f'<option value="{esc(tid)}">{esc(label)}</option>' for tid, label, _s in THEMES)
    page = PAGE
    repl = {
        "___CSS___": _page_css(),
        "___NOW___": esc(now),
        "___THEMEOPTS___": opts,
        "___TIPS___": tips["html"],
        "___RULES___": "".join(f"<li>{esc(x)}</li>" for x in TIPS_RULES),
        "___SOTTO___": "".join(chunks[v]["sotto_html"] for v, _l, _d in VENUES),
        "___PROSSIME___": prossime["html"],
        "___GOAL___": "".join(chunks[v]["goal_html"] for v, _l, _d in VENUES),
        "___FREQUENZA___": html.escape(freq_text),
        "___SALTATI___": "".join(chunks[v]["saltati_html"] for v, _l, _d in VENUES),
        "___POP___": popjson,
        "___SALTMIN___": str(SALTATI_MIN),
        "___SALTDAYS___": str(SALTATI_GIORNI),
    }
    for key, val in repl.items():
        page = page.replace(key, val)
    open("index.html", "w").write(page)
    print("XG_COPERTURA", flush=True)
    for c, l, status, n in xg_rows:
        print(f"XG\t{status}\t{c}\t{l}\t{n}", flush=True)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sei bozze di titolo e caratteri. Non tocca la pagina pubblicata."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "index.html").read_text(encoding="utf-8")
OUT = Path(__file__).resolve().parent

# Nome, frase, link Google Fonts, CSS.
BOZZE = [
    ("01-linea", "Linea", "Titolo Inter compatto, con un segno sotto e carte arrotondate.",
     "Inter:wght@400;600;800",
     """body,button,select{font-family:Inter,system-ui,sans-serif!important}
h1{font-family:Inter,sans-serif!important;font-weight:800!important;letter-spacing:-.045em!important;font-size:clamp(1.7rem,4.2vw,2.5rem)!important;text-shadow:none!important}
h1::after{content:"";display:block;width:64px;height:4px;margin-top:.4rem;background:var(--accent);border-radius:4px}
h2{font-family:Inter,sans-serif!important;font-weight:700!important;letter-spacing:-.03em}
.tip,.fx{border-radius:18px!important}
.tag,.vtag{border-radius:999px!important}"""),
    ("02-tecnica", "Tecnica", "Space Grotesk, titolo maiuscolo e carte quasi squadrate.",
     "Space+Grotesk:wght@400;600;700",
     """body,button,select{font-family:"Space Grotesk",system-ui,sans-serif!important}
h1{font-family:"Space Grotesk",sans-serif!important;font-weight:700!important;letter-spacing:.14em!important;text-transform:uppercase!important;font-size:clamp(1.15rem,3.2vw,1.7rem)!important;text-shadow:none!important}
h2{font-family:"Space Grotesk",sans-serif!important;letter-spacing:.08em!important;text-transform:uppercase!important;font-size:1rem!important}
.tip,.fx{border-radius:4px!important}
.tag,.vtag{border-radius:2px!important;letter-spacing:.04em}"""),
    ("03-morbida", "Morbida", "Outfit, titolo morbido e tag a pillola.",
     "Outfit:wght@400;600;700",
     """body,button,select{font-family:Outfit,system-ui,sans-serif!important}
h1{font-family:Outfit,sans-serif!important;font-weight:700!important;letter-spacing:-.03em!important;font-size:clamp(1.8rem,4.5vw,2.7rem)!important;text-shadow:none!important}
h2{font-family:Outfit,sans-serif!important;font-weight:700!important}
.tip,.fx{border-radius:22px!important;padding:.85rem 1rem!important}
.tag,.vtag,.rk{border-radius:999px!important}"""),
    ("04-fascia", "Fascia", "Sora, il titolo sta in una fascia come un'insegna.",
     "Sora:wght@400;600;700",
     """body,button,select{font-family:Sora,system-ui,sans-serif!important}
h1{font-family:Sora,sans-serif!important;font-weight:700!important;letter-spacing:-.04em!important;font-size:clamp(1.45rem,4vw,2.15rem)!important;text-shadow:none!important;background:var(--card);border:1px solid var(--line);border-left:6px solid var(--accent);border-radius:14px;padding:.7rem .9rem;box-shadow:none}
h2{font-family:Sora,sans-serif!important;font-weight:700!important}
.tip,.fx{border-radius:12px!important}
.tag,.vtag{border-radius:8px!important}"""),
    ("05-editoriale", "Editoriale", "Manrope, titolo leggero e carte con il bordo solo a sinistra.",
     "Manrope:wght@400;600;700",
     """body,button,select{font-family:Manrope,system-ui,sans-serif!important}
h1{font-family:Manrope,sans-serif!important;font-weight:600!important;letter-spacing:-.035em!important;font-size:clamp(1.9rem,4.6vw,2.8rem)!important;text-shadow:none!important}
h2{font-family:Manrope,sans-serif!important;font-weight:700!important;border-left-width:0!important;padding-left:0!important}
.tip,.fx{border-radius:0 12px 12px 0!important;border-left:3px solid var(--accent)!important;box-shadow:none!important}
.tag,.vtag{border-radius:6px!important}"""),
    ("06-manifesto", "Manifesto", "Titolo Bebas Neue grande, testo Inter.",
     "Bebas+Neue&family=Inter:wght@400;600;700",
     """body,button,select{font-family:Inter,system-ui,sans-serif!important}
h1{font-family:"Bebas Neue",Impact,sans-serif!important;font-weight:400!important;letter-spacing:.03em!important;font-size:clamp(3.1rem,11vw,5.4rem)!important;line-height:.84!important;text-shadow:none!important}
h2{font-family:"Bebas Neue",Impact,sans-serif!important;font-weight:400!important;letter-spacing:.06em!important;font-size:1.8rem!important}
.tip,.fx{border-radius:10px!important}
.tag,.vtag{border-radius:4px!important;letter-spacing:.06em}"""),
]

def main():
    for slug, _name, _desc, query, css in BOZZE:
        link = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link href="https://fonts.googleapis.com/css2?family={query}&display=swap" rel="stylesheet">'
            f"<style>/* bozza {slug} */{css}</style>"
        )
        html = SRC.replace("</head>", link + "</head>", 1)
        (OUT / f"{slug}.html").write_text(html, encoding="utf-8")
        print(slug)

if __name__ == "__main__":
    main()

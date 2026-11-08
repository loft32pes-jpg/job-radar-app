"""Numeri sul lavoro in Europa per l'attesa della ricerca, letti dal vivo dall'API pubblica di Eurostat.

A ogni ricerca si pescano indicatori e paesi diversi: i dati sono sempre quelli ufficiali più recenti, mai scritti a mano.
Se Eurostat non risponde la pagina usa i numeri di riserva che ha già dentro.
"""
import json
import random
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
VIEW = "https://ec.europa.eu/eurostat/databrowser/view/{}/default/table?lang=en"

GEO = {"IT": ("Italia", "Italy"), "ES": ("Spagna", "Spain"), "FR": ("Francia", "France"), "DE": ("Germania", "Germany"),
       "IE": ("Irlanda", "Ireland"), "NL": ("Paesi Bassi", "the Netherlands"), "BE": ("Belgio", "Belgium"),
       "PT": ("Portogallo", "Portugal"), "AT": ("Austria", "Austria"), "LU": ("Lussemburgo", "Luxembourg"),
       "SE": ("Svezia", "Sweden"), "DK": ("Danimarca", "Denmark"), "NO": ("Norvegia", "Norway"), "FI": ("Finlandia", "Finland"),
       "PL": ("Polonia", "Poland"), "CZ": ("Cechia", "Czechia"), "HU": ("Ungheria", "Hungary"), "RO": ("Romania", "Romania"),
       "EL": ("Grecia", "Greece"), "EE": ("Estonia", "Estonia"), "LV": ("Lettonia", "Latvia"), "LT": ("Lituania", "Lithuania"),
       "HR": ("Croazia", "Croatia"), "SI": ("Slovenia", "Slovenia"), "SK": ("Slovacchia", "Slovakia"), "BG": ("Bulgaria", "Bulgaria"),
       "MT": ("Malta", "Malta"), "CY": ("Cipro", "Cyprus"), "CH": ("Svizzera", "Switzerland")}

# (codice Eurostat, filtri, titolo it/en, frase it/en con {v} valore e {y} anno, unità mostrata, decimali)
INDICATORS = [
    ("isoc_sks_itspt", {"unit": "PC_EMP"}, ("Specialisti digitali", "Digital specialists"),
     ("degli occupati lavora come specialista ICT", "of people in work are ICT specialists"), "%", 1),
    ("isoc_sks_itsps", {"sex": "F", "unit": "PC"}, ("Donne nel digitale", "Women in tech"),
     ("degli specialisti ICT sono donne", "of ICT specialists are women"), "%", 1),
    ("lfsi_emp_a", {"indic_em": "EMP_LFS", "sex": "T", "age": "Y20-64", "unit": "PC_POP"}, ("Occupazione", "Employment"),
     ("delle persone tra 20 e 64 anni lavora", "of people aged 20-64 are in work"), "%", 1),
    ("une_rt_a", {"age": "Y15-74", "unit": "PC_ACT", "sex": "T"}, ("Disoccupazione", "Unemployment"),
     ("è il tasso di disoccupazione", "is the unemployment rate"), "%", 1),
    ("edat_lfse_24", {"sex": "T", "age": "Y20-34", "isced11": "ED5-8", "duration": "Y1-3", "unit": "PC"},
     ("Neolaureati al lavoro", "Recent graduates in work"),
     ("dei laureati da 1 a 3 anni ha un lavoro", "of people who graduated 1-3 years ago have a job"), "%", 1),
    ("lfsa_ehomp", {"frequenc": "USU", "sex": "T", "age": "Y15-64", "wstatus": "EMP", "unit": "PC"}, ("Lavoro da casa", "Working from home"),
     ("degli occupati lavora abitualmente da casa", "of people in work usually work from home"), "%", 1),
    ("isoc_sk_dskl_i21", {"ind_type": "IND_TOTAL", "indic_is": "I_DSK2_BAB", "unit": "PC_IND"}, ("Competenze digitali", "Digital skills"),
     ("delle persone ha competenze digitali almeno di base", "of people have at least basic digital skills"), "%", 0),
    ("lfsa_eppga", {"sex": "T", "age": "Y15-64", "unit": "PC"}, ("Part-time", "Part-time work"),
     ("degli occupati lavora part-time", "of people in work are part-time"), "%", 1),
    ("lfsa_etpgan", {"sex": "T", "age": "Y15-64", "citizen": "TOTAL", "unit": "PC"}, ("Contratti a termine", "Temporary contracts"),
     ("dei dipendenti ha un contratto a termine", "of employees have a temporary contract"), "%", 1),
    ("tec00114", {}, ("Ricchezza per abitante", "Wealth per person"),
     ("è il PIL per abitante a parità di potere d'acquisto, fatta 100 la media UE", "is GDP per person in purchasing power, with the EU average at 100"), "", 0),
    ("lfsa_ewhun2", {"nace_r2": "TOTAL", "worktime": "FT", "wstatus": "EMP", "age": "Y15-64", "sex": "T", "unit": "HR"},
     ("Ore di lavoro", "Working hours"),
     ("ore a settimana: l'orario abituale di chi lavora a tempo pieno", "hours a week: the usual schedule of full-time workers"), "", 1),
    ("isoc_ske_itrcrn2", {"size_emp": "GE10", "nace_r2": "C10-S951_X_K", "indic_is": "E_ITSPVAC2", "unit": "PC_ENT"},
     ("Profili digitali introvabili", "Hard-to-fill tech roles"),
     ("delle imprese ha avuto posti da specialista ICT difficili da coprire", "of companies had ICT specialist vacancies that were hard to fill"), "%", 1),
    ("earn_gr_gpgr2", {"nace_r2": "B-S_X_O", "unit": "PC"}, ("Divario retributivo", "Gender pay gap"),
     ("è il divario tra la paga oraria di uomini e donne", "is the gap between men's and women's hourly pay"), "%", 1),
]


LABEL = {  # nome dell'indicatore, per classifiche e confronti
    "isoc_sks_itspt": ("Specialisti ICT sul totale degli occupati", "ICT specialists as a share of people in work"),
    "isoc_sks_itsps": ("Donne tra gli specialisti ICT", "Women among ICT specialists"),
    "lfsi_emp_a": ("Tasso di occupazione (20-64 anni)", "Employment rate (ages 20-64)"),
    "une_rt_a": ("Tasso di disoccupazione", "Unemployment rate"),
    "edat_lfse_24": ("Laureati da 1 a 3 anni che lavorano", "Graduates of the last 1-3 years in work"),
    "lfsa_ehomp": ("Occupati che lavorano abitualmente da casa", "People who usually work from home"),
    "isoc_sk_dskl_i21": ("Persone con competenze digitali almeno di base", "People with at least basic digital skills"),
    "lfsa_eppga": ("Occupati part-time", "People working part-time"),
    "lfsa_etpgan": ("Dipendenti con contratto a termine", "Employees on temporary contracts"),
    "tec00114": ("PIL per abitante a parità di potere d'acquisto (media UE = 100)", "GDP per person in purchasing power (EU average = 100)"),
    "lfsa_ewhun2": ("Ore settimanali abituali di chi lavora a tempo pieno", "Usual weekly hours of full-time workers"),
    "isoc_ske_itrcrn2": ("Imprese con posti da specialista ICT difficili da coprire", "Companies with hard-to-fill ICT specialist vacancies"),
    "earn_gr_gpgr2": ("Divario tra la paga oraria di uomini e donne", "Gap between men's and women's hourly pay"),
}


def _fetch(code, filters):
    q = urlencode({**filters, "format": "JSON", "lang": "EN", "lastTimePeriod": 1})
    with urlopen(Request(API + code + "?" + q, headers={"User-Agent": "JobRadar/1.0"}), timeout=20) as r:
        d = json.load(r)
    geo = d["dimension"]["geo"]["category"]["index"]
    year = next(iter(d["dimension"]["time"]["category"]["index"]))
    pos = d["id"].index("geo")
    stride = 1
    for s in d["size"][pos + 1:]:
        stride *= s
    values = {g: d["value"].get(str(i * stride)) for g, i in geo.items()}
    return {g: v for g, v in values.items() if v is not None}, year


def _num(v, dec, lang):
    s = f"{v:.{dec}f}"
    return s.replace(".", ",") if lang == "it" else s


def build(n=14, seed=None):
    """Lista di n dati pescati a caso (indicatore e paese). Ogni voce ha testo in italiano e in inglese e il link alla fonte."""
    rnd = random.Random(seed)
    out = []
    picks = rnd.sample(INDICATORS, len(INDICATORS))
    for code, filters, title, phrase, unit, dec in picks:
        if len(out) >= n:
            break
        try:
            values, year = _fetch(code, filters)
        except Exception:
            continue  # Eurostat non risponde per questo indicatore: si passa al prossimo
        eu = values.get("EU27_2020")
        countries = [g for g in GEO if g in values]
        if len(countries) < 5:
            continue
        ranked = sorted(countries, key=lambda g: -values[g])
        kinds = rnd.sample(["paese", "classifica", "confronto"], 2)
        for kind in kinds:
            lab = LABEL[code]
            if kind == "paese":
                g = rnd.choice(countries)
                it = f"{GEO[g][0]}: " + (f"il {_num(values[g], dec, 'it')}% {phrase[0]}" if unit == "%" else f"{_num(values[g], dec, 'it')} {phrase[0]}") + f" ({year})."
                name_en = GEO[g][1][0].upper() + GEO[g][1][1:]
                en = f"{name_en}: {_num(values[g], dec, 'en')}{unit} {phrase[1]} ({year})."
                if eu is not None:
                    it += f" La media UE è {_num(eu, dec, 'it')}{unit}."
                    en += f" The EU average is {_num(eu, dec, 'en')}{unit}."
                big = {"it": _num(values[g], dec, "it") + unit, "en": _num(values[g], dec, "en") + unit}
            elif kind == "classifica":
                top = ranked[:3]
                it = f"{lab[0]} ({year}). I tre paesi più alti: " + ", ".join(f"{GEO[g][0]} {_num(values[g], dec, 'it')}{unit}" for g in top) + "."
                en = f"{lab[1]} ({year}). The top three countries: " + ", ".join(f"{GEO[g][1]} {_num(values[g], dec, 'en')}{unit}" for g in top) + "."
                big = {"it": GEO[top[0]][0], "en": GEO[top[0]][1].replace("the ", "")}
            else:
                if "IT" not in values:
                    continue
                g = rnd.choice([c for c in countries if c != "IT"])
                it = f"{lab[0]} ({year}): Italia {_num(values['IT'], dec, 'it')}{unit}, {GEO[g][0]} {_num(values[g], dec, 'it')}{unit}."
                en = f"{lab[1]} ({year}): Italy {_num(values['IT'], dec, 'en')}{unit}, {GEO[g][1]} {_num(values[g], dec, 'en')}{unit}."
                big = {"it": f"{_num(values['IT'], dec, 'it')} / {_num(values[g], dec, 'it')}", "en": f"{_num(values['IT'], dec, 'en')} / {_num(values[g], dec, 'en')}"}
            out.append({"k": {"it": title[0], "en": title[1]}, "big": big, "tx": {"it": it, "en": en}, "url": VIEW.format(code), "code": code})
    rnd.shuffle(out)
    return out[:n]


if __name__ == "__main__":
    for f in build(8):
        print(f["big"]["it"], "|", f["tx"]["it"], "|", f["tx"]["en"])

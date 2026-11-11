"""Regole di filtro e scoring (nessuna API a pagamento: tutto in locale).

Profilo: Ingegneria Gestionale, 2 anni di technical sales software in ambito mobility,
vuole uscire dalla mobility, solo italiano e inglese, junior/mid.

I ruoli si riconoscono per CONCETTO, non per parola esatta: ogni famiglia elenca i molti modi in cui
la stessa posizione viene chiamata, anche nelle lingue dei paesi (spagnolo, francese, tedesco, ecc.).
Per cambiare ruoli, parole chiave o pesi basta modificare questo file.
"""
import re

MIN_SCORE = 45
WIDE_MIN = 60  # voto minimo del giudice AI per un titolo fuori dai ruoli della persona, entrato solo dal filtro largo delle sue città

# (famiglia, punti base 0-40, regex sul titolo). Vince la prima che combacia.
FAMILIES = [
    ("tech_sales", 40,
     r"sales engineer|solutions? (engineer|consultant|architect|specialist|advisor)|pre[- ]?sales|technical account|"
     r"technical sales|customer engineer|field (application|sales) engineer|application engineer|sales consultant.{0,20}technical|"
     r"tecnic[oa][- ]commerciale|venditore tecnico|prevendita|ingegnere (commerciale|di vendita)|vendite tecniche|"
     r"ingenier[oa]\S* (de ventas|comercial|preventa)|t[eé]cnic[oa]\S* comercial|preventa|consultor\S* de soluciones|"
     r"ing[ée]nieure? (commercial|d.affaires|avant[- ]vente|technico)|avant[- ]vente|technico[- ]commercial|"
     r"vertriebsingenieur|technische[rn]? vertrieb|l[öo]sungsberater|engenheir[oa] (de vendas|comercial)|pr[ée][- ]venda|"
     r"technisch commercieel|in[zż]ynier sprzeda[zż]y"),
    ("bd", 34,
     r"business develop|biz ?dev|\bbdr\b|\bsdr\b|sales development|partnerships?\b|alliances?\b|new business|"
     r"growth (manager|executive|associate|lead)|market development|lead generation|"
     r"sviluppo (commerciale|business|del business|nuovi clienti)|desarrollo de negocio|desarrollador\S* de negocio|"
     r"d[ée]veloppement commercial|charg[ée]e? de d[ée]veloppement|d[ée]veloppeu(r|se) commercial|"
     r"gesch[äa]ftsentwicklung|neukunden(gewinnung|akquise)|desenvolvimento de neg[óo]cios?|rozw[óo]j biznesu"),
    ("change", 28,
     r"change manag|change (lead|consultant|agent|specialist|analyst)|business transformation|digital transformation|"
     r"transformation (consultant|manager|lead|analyst)|\badoption\b|organi[sz]ational (change|development)|"
     r"gestione del cambiamento|gesti[óo]n del cambio|conduite du changement|gestion du changement|"
     r"ver[äa]nderungsmanagement|gest[ãa]o da mudan[çc]a|verandermanagement"),
    ("affini", 20,
     r"customer success|client success|commercial analyst|sales (operations|ops\b|enablement|analyst|support|coordinator|excellence)|"
     r"revenue operations|\brevops\b|go[- ]?to[- ]?market|\bgtm\b|implementation (consultant|manager|specialist)|"
     r"onboarding (manager|specialist)|[ée]xito del cliente|successo del cliente|kundenerfolg"),
    ("sales", 28,
     r"account (executive|manager|associate|representative|specialist|partner)|accountmanager|key account|\bkam\b|inside sales|"
     r"sales (manager|representative|associate|executive|consultant|specialist|advisor|professional|agent|lead)|\bsales\b|"
     r"commercial (manager|executive|representative|consultant|associate)|territory manager|area manager|"
     r"client (manager|partner|executive)|relationship manager|"
     r"\bcommerciale?\b|venditore|venditrice|addett[oa] (alle )?vendite|responsabile (commerciale|clienti|vendite)|funzionario commerciale|"
     r"\bcomercial\b|ejecutiv[oa]\S* (de cuentas|comercial|de ventas)|gestor\S* de cuentas|responsable (comercial|de ventas|de cuentas)|"
     r"delegad[oa]\S* comercial|asesor\S* comercial|\bventas?\b|vendedor\w*|\bventes?\b|responsable (grands comptes|comptes)|charg[ée]e? d.affaires|"
     r"charg[ée]e? de client[èe]le|comptes? cl[ée]s?|attach[ée]e? commercial|\bvertrieb|\bverkauf|kundenberater|kundenbetreuer|"
     r"au[ßs]endienst|innendienst|gestor\S* de (contas|clientes)|executiv[oa] de (contas|vendas)|\bvendas\b|\bverkoop|commercieel|"
     r"handlowiec|przedstawiciel handlowy|sprzeda[zż]|opiekun klienta|s[äa]ljare|f[öo]rs[äa]ljning|\bsalgs|s[æa]lger|myynti|"
     r"kundeansvarlig|obchodn[íi]|[ée]rt[ée]kes[íi]t|v[âa]nz[ăa]ri"),
]
FAMILY_LABEL = {"tech_sales": "Technical Sales", "bd": "Business Development", "sales": "Sales B2B",
                "change": "Change Management", "affini": "ruolo affine"}

TITLE_EXCLUDE = re.compile(
    # troppo senior o non è un lavoro vero e proprio
    r"\b(director|directeur|direttore|directora?|vp|vice president|head of|chief|principal|"
    r"intern|internship|working student|werkstudent|trainee programme|apprentice|apprenti\w*|alternance|stagiaire|"
    r"praktikum|praktikant\w*|stage|tirocinio|becari[oa]|pr[áa]cticas|est[áa]gio)\b|"
    # altri mestieri che contengono le stesse parole
    r"\b(seo|sem|ppc|recruit\w*|talent acquisition|accountant|accounts? (payable|receivable)|payroll|bookkeeper|contabil\w*|"
    r"buchhalt\w*|marketing|advertising|creative|copywriter|designer|lawyer|counsel|legal|avvocat\w*|nurse|infermier\w*|"
    r"software (engineer|developer)|web developer|front[- ]?end|back[- ]?end|full[- ]?stack|devops|data (engineer|scientist))\b|"
    # vendita al dettaglio, porta a porta, call center, settori lontani
    r"\b(retail|store|shop|boutique|negozio|commess[oa]|tienda|dependient[ea]|magasin|filiale?|cashier|cassier\w*|"
    r"call ?cent\w+|telemarketing|televendit\w*|teleoperador\w*|door[- ]to[- ]door|porta a porta|real estate|immobili\w+|"
    r"inmobiliari\w+|insurance|assicura\w+|seguros|versicherung\w*|car sales|venditore auto|concessionari\w+|"
    r"informatore|pharma\w* rep\w*|medical rep\w*|beauty|estetic\w+|chef|waiter|cameriere|driver|autista|warehouse|magazzin\w+)\b|"
    # titoli che dichiarano una lingua che non parla
    r"\b(german|french|spanish|dutch|portuguese|polish|swedish|danish|norwegian|finnish|nordic|czech|hungarian|"
    r"turkish|arabic|greek|romanian|hebrew|russian)[- ]speak\w*|"
    r"\(\s*[mwfdxi*]\s*[/|]\s*[mwfdxi*]",
    re.I,
)

SOFTWARE_WORDS = re.compile(
    r"\bsaas\b|software|\bcloud\b|platform|piattaforma|plataforma|plateforme|\bapi\b|\bb2b\b|\bai\b|\bia\b|machine learning|"
    r"analytics|cybersecurity|ciberseguridad|\bcrm\b|salesforce|\berp\b|automation|fintech|solution selling|\bit solutions?\b|"
    r"digital|tecnolog|technolog|logiciel",
    re.I,
)

# Mobility: esclusione dura se nel titolo/azienda o con 2+ riscontri forti nel testo
MOBILITY_STRONG = re.compile(
    r"automotive|automoci[óo]n|automobile|car ?sharing|ride[- ]?(hailing|sharing)|e-?mobility|micro-?mobility|\bev[- ]charging|"
    r"charging (station|infrastructure|network|point)|fleet (management|telematics|operator|manager)|fleet[- ]?solutions|telematics|"
    r"\bmobility\b|mobilità|movilidad|mobilit[ée]\b|\bmaas\b|public transport|trasporto pubblico|car rental|noleggio auto|"
    r"ricarica elettrica|connected (car|vehicle)|\boem\b|vehicle (data|fleet)|electric vehicles?|veicoli elettrici",
    re.I,
)
MOBILITY_WEAK = re.compile(r"logistics|logistica|log[íi]stica|transport|trasporti|shipping|supply chain|vehicles?|veicol", re.I)

OTHER_LANGS = (
    r"german|deutsch|french|fran[cç]ais|spanish|espa[nñ]ol|castellano|dutch|nederlands|portuguese|portugu[eê]s|polish|polski|"
    r"swedish|svenska|danish|dansk|norwegian|norsk|finnish|suomi|czech|[cč]e[sš]tina|hungarian|magyar|romanian|greek|russian|"
    r"arabic|turkish|chinese|mandarin|japanese|tedesco|francese|spagnolo|olandese|portoghese|polacco|svedese|danese|norvegese|russo"
)
LANG_WORD = re.compile(rf"\b({OTHER_LANGS})\b", re.I)
LANG_PROF = re.compile(r"fluen\w*|proficien\w*|native|mother tongue|madrelingua|speak\w*|speaker|c1|c2|b2|required|mandatory|"
                       r"must|essential|communicat\w*|written|verbal|spoken|language|knowledge|command|conoscenza|lingua|"
                       r"ottim\w*|buon\w*", re.I)
LANG_SOFT = re.compile(r"preferred|plus|advantage|nice to have|bonus|desirable|an asset|appreciated|gradit|preferibil|"
                       r"preferenzial|beneficial|not required|not mandatory|optional|valutat", re.I)
# l'annuncio in lingua locale entra solo se nomina l'inglese (lingua di lavoro o requisito)
ENGLISH_MENTION = re.compile(r"\b(english|ingl[eéê]s|inglese|anglais|englisch|engels|angielski\w*|engelska|engelsk|englanti\w*|"
                             r"angli[cč]tin\w*|angol)\b", re.I)
EN_IT_TITLE = re.compile(
    r"\b(sales|account|business develop\w*|engineer|manager|consultant|executive|customer success|partnerships?|pre-?sales|"
    r"specialist|representative|associate|analyst|solutions?|change management|go-to-market|"
    r"commerciale|vendite|venditore|sviluppo|responsabile|prevendita|consulente|addett[oa])\b", re.I)
LOCAL_LANGUAGE = {  # paese -> lingua dell'annuncio locale, per l'avviso
    "Spagna": "spagnolo", "Francia": "francese", "Germania": "tedesco", "Austria": "tedesco", "Paesi Bassi": "olandese",
    "Portogallo": "portoghese", "Polonia": "polacco", "Svezia": "svedese", "Danimarca": "danese", "Norvegia": "norvegese",
    "Finlandia": "finlandese", "Repubblica Ceca": "ceco", "Ungheria": "ungherese", "Romania": "rumeno", "Grecia": "greco",
    "Slovacchia": "slovacco", "Bulgaria": "bulgaro", "Croazia": "croato", "Slovenia": "sloveno", "Estonia": "estone",
    "Lettonia": "lettone", "Lituania": "lituano",
}

COUNTRY_MAP = [  # (nome italiano, regex sulla località)
    ("Italia", r"\bitaly\b|italia|milan|milano|roma\b|rome\b|torino|turin|bologna|napoli|naples|firenze|florence|padova|verona|genova|"
               r"lombard|piemont|piedmont|veneto|emilia|toscana|tuscany|lazio|\(it\)"),
    ("Germania", r"germany|deutschland|berlin|munich|münchen|hamburg|frankfurt|köln|cologne|stuttgart|düsseldorf|heilbronn|"
                 r"bavaria|bayern|\(de\)|\bger\b"),
    ("Francia", r"france|paris|lyon|marseille|toulouse|lille|nantes|bordeaux|île-de-france|\(fr\)"),
    ("Regno Unito", r"united kingdom|\buk\b|london|manchester|edinburgh|birmingham|leeds|bristol|glasgow|england|scotland|wales|\(gb\)"),
    ("Spagna", r"spain|españa|madrid|barcelona|valencia|sevill|bilbao|zaragoza|m[áa]laga|catalonia|catalu|andalus|basque|"
               r"galicia|valladolid|murcia|alicante|\(es\)"),
    ("Paesi Bassi", r"netherlands|nederland|amsterdam|rotterdam|utrecht|eindhoven|the hague|den haag|\(nl\)"),
    ("Belgio", r"belgium|belgi[ëe]|belgique|brussels|bruxelles|antwerp|gent|ghent|flanders|\(be\)"),
    ("Svizzera", r"switzerland|schweiz|suisse|zurich|zürich|geneva|genève|basel|lausanne|zug\b|\(ch\)"),
    ("Austria", r"austria|österreich|vienna|wien|graz|salzburg|linz|\(at\)"),
    ("Polonia", r"poland|polska|warsaw|krak|wroc|gda|poznan|\(pl\)"),
    ("Irlanda", r"ireland|dublin|cork|galway|limerick"),
    ("Portogallo", r"portugal|lisbon|lisboa|porto\b|braga|faro|coimbra"),
    ("Svezia", r"sweden|sverige|stockholm|gothenburg|göteborg|malmö"),
    ("Danimarca", r"denmark|danmark|copenhagen|aarhus|jutland"),
    ("Norvegia", r"norway|norge|oslo|bergen"),
    ("Finlandia", r"finland|suomi|helsinki|tampere|espoo"),
    ("Repubblica Ceca", r"czech|prague|praha|brno"),
    ("Ungheria", r"hungary|budapest"),
    ("Romania", r"romania|bucharest|cluj"),
    ("Grecia", r"greece|athens|thessaloniki"),
    ("Lussemburgo", r"luxembourg"),
    ("Slovacchia", r"slovakia|bratislava"),
    ("Bulgaria", r"bulgaria|sofia"),
    ("Estonia", r"estonia|tallinn"),
    ("Lettonia", r"latvia|riga"),
    ("Lituania", r"lithuania|vilnius"),
    ("Croazia", r"croatia|zagreb"),
    ("Slovenia", r"slovenia|ljubljana"),
    ("Malta", r"\bmalta\b"),
    ("Cipro", r"cyprus|nicosia|limassol"),
]
LOCAL_MARKET_TITLE = re.compile(
    r"\b(france|french|germany|dach|nordics?|benelux|iberia|spain|netherlands|poland|sweden|denmark|norway|finland|"
    r"belgium|austria|switzerland|emea south|southern europe)\b", re.I)
EUROPE_GENERIC = re.compile(r"europe|emea|\beu\b|european union", re.I)
NON_EUROPE = re.compile(
    r"\bus\b|\busa\b|united states|america|canada|mexico|brazil|argentina|colombia|chile|\bindia\b|australia|new zealand|"
    r"singapore|japan|china|hong kong|korea|israel|dubai|\buae\b|saudi|africa|philippines|indonesia|"
    r"sydney|melbourne|\bapac\b|\basia\b|tokyo|bangalore|bengaluru|mumbai|toronto|vancouver|new york|san francisco|"
    r"seattle|austin|boston|chicago|los angeles|\blatam\b|sao paulo|são paulo|mexico city|tel aviv", re.I)


# ---------------------------------------------------------------- profilo dell'utente
# Senza profilo valgono le regole storiche scritte qui sopra. Con un profilo (profilo/ricerca.json, creato dall'intervista)
# ruoli, competenze, settori da evitare, lingue ed esperienza vengono da lì.
OTHER = "cx"                                    # famiglia dei titoli non previsti (vedi configure)
PROFILE = None
JUDGE_ON = False                                # c'è un'AI che può leggere gli annunci (lo imposta la ricerca)
SEARCH = None                                   # ricerche da fare sulle fonti (vedi searchprofile.search_plan)
USER = {"years": 2, "langs": {"it", "en"}}
SKILL_LIST = []                                 # [(etichetta, regex)] competenze del profilo
LOCAL_TITLES = None                             # titoli nelle lingue locali: servono per gli annunci non letti
NEVER = re.compile(r"(?!x)x")
PREFER = NEVER                                  # parole dei settori preferiti dall'utente: danno punti in più
NEAR_WORDS = NEVER                              # parole di mestiere che nelle sue città bastano per far leggere l'annuncio al giudice
FOLLOW = NEVER                                  # aziende che segue (ci si è candidata o ne ha salvato annunci)
AVOID_TEXT = None                               # parole da evitare contate nel testo (None = regole storiche)
# parole che in un titolo dicono il livello o il tipo di figura, non il mestiere
HEADS = {"manager", "specialist", "analyst", "coordinator", "associate", "executive", "representative", "lead", "officer",
         "consultant", "advisor", "partner", "director", "head", "junior", "senior", "jr", "sr", "mid", "intern", "trainee",
         "graduate", "i", "ii", "iii", "responsabile", "specialista", "analista", "coordinatore", "coordinatrice", "associato",
         "consulente", "addetto", "addetta", "referente", "impiegato", "impiegata"}
TITLE_STOPS = {"of", "and", "the", "for", "in", "to", "di", "del", "della", "dei", "delle", "e", "ed", "per", "a", "al", "alla", "con"}
# parole troppo larghe per bastare da sole (in coppia vanno bene: "business development", "key account")
BROAD = {"sales", "business", "project", "account", "product", "commercial", "customer", "operations", "marketing", "program",
         "process", "market", "digital", "technical", "service", "services", "client", "data", "it", "key", "global",
         "international", "regional", "italy", "italia", "vendite", "commerciale", "progetto", "programma", "prodotto", "clienti",
         "cliente", "operazioni", "processi", "mercato", "engineer", "ingegnere", "team", "new", "area", "general", "support",
         "management", "development", "sviluppo", "gestione", "solutions", "solution", "group", "emea", "europe", "owner"}
LANG_CODES = [("de", r"german|deutsch|tedesco"), ("fr", r"french|fran[cç]ais|francese"), ("es", r"spanish|espa[nñ]ol|castellano|spagnolo"),
              ("nl", r"dutch|nederlands|olandese"), ("pt", r"portuguese|portugu[eê]s|portoghese"), ("pl", r"polish|polski|polacco"),
              ("sv", r"swedish|svenska|svedese"), ("da", r"danish|dansk|danese"), ("no", r"norwegian|norsk|norvegese"),
              ("fi", r"finnish|suomi"), ("cs", r"czech|[cč]e[sš]tina"), ("hu", r"hungarian|magyar"), ("ro", r"romanian"), ("el", r"greek")]
LANG_IT = {"it": "italiano", "en": "inglese", "es": "spagnolo", "fr": "francese", "de": "tedesco", "pt": "portoghese", "nl": "olandese",
           "pl": "polacco", "sv": "svedese", "da": "danese", "no": "norvegese", "fi": "finlandese", "cs": "ceco", "hu": "ungherese",
           "ro": "rumeno", "el": "greco"}
SPEAKING = {"de": "german", "fr": "french", "es": "spanish", "nl": "dutch", "pt": "portuguese", "pl": "polish", "sv": "swedish",
            "da": "danish", "no": "norwegian", "fi": "finnish", "cs": "czech", "hu": "hungarian", "ro": "romanian", "el": "greek"}


def _words_rx(words):
    """Regex che trova una qualsiasi delle parole/frasi (parola intera, spazi e trattini equivalenti)."""
    parts = [re.escape(w.strip()).replace(r"\ ", r"[\s\-/]+") for w in sorted(set(words), key=len, reverse=True) if len(w.strip()) > 1]
    return r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)" if parts else None


def title_runs(title):
    """Le parole di mestiere di un titolo, a gruppi di parole vicine: 'Italy Home Category & Business Development Specialist'
    -> [['italy', 'home', 'category'], ['business', 'development']]. Livelli e figure (manager, specialist...) fanno da confine."""
    runs, cur = [], []
    for tok in re.findall(r"[a-zà-ÿ0-9][a-zà-ÿ0-9\-]*|[^\sa-zà-ÿ0-9]", str(title or "").lower()):
        if not re.match(r"[a-zà-ÿ0-9]", tok) or tok in HEADS or tok in TITLE_STOPS:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        runs.append(cur)
    return runs


def title_pairs(title):
    """Coppie di parole vicine: riconoscono lo stesso mestiere scritto con un'altra figura ('Business Development Specialist')."""
    return {" ".join(r[i:i + 2]) for r in title_runs(title) for i in range(len(r) - 1)}


def title_singles(title):
    """Mestieri di una parola sola ('Innovation Analyst' -> innovation), escluse le parole troppo larghe."""
    return {r[0] for r in title_runs(title) if len(r) == 1 and len(r[0]) >= 3 and r[0] not in BROAD and not r[0].isdigit()}


def configure(profile):
    """Attiva un profilo di ricerca: da qui in poi classify() ed evaluate() ragionano su quella persona."""
    global PROFILE, SEARCH, FAMILIES, FAMILY_LABEL, TITLE_EXCLUDE, SKILL_LIST, MOBILITY_STRONG, MOBILITY_WEAK, LOCAL_TITLES, PREFER
    global NEAR_WORDS, FOLLOW, AVOID_TEXT
    if not profile or not profile.get("clusters"):
        return False
    import details
    import searchprofile
    ans = profile.get("answers") or {}
    PROFILE = profile
    USER["langs"] = set(ans.get("languages") or ["it", "en"])
    try:
        USER["years"] = max(0, int(float(ans.get("years", 2))))
    except (TypeError, ValueError):
        USER["years"] = 2
    # quello che la ricerca ha imparato dalle scelte della persona (learn.py): vale più dell'intervista
    lr = profile.get("learned") or {}
    off = {str(x).lower() for x in profile.get("learned_off") or []}
    fams, pairs, labels, local, singles = [], [], {}, [], set()
    for c in profile["clusters"]:
        if not c.get("on", True):
            continue
        loc = [t for ts in (c.get("titles_local") or {}).values() for t in ts]
        rx = _words_rx(c["titles_en"] + c["titles_it"] + loc)
        if rx:
            pts = searchprofile.TIER_POINTS.get(c.get("tier"), 33)
            fams.append((c["id"], pts, rx))
            labels[c["id"]] = c["name"]
            local += loc
            # lo stesso mestiere con un'altra figura o dentro un titolo più lungo: "Business Development Manager" nel profilo
            # riconosce anche "Home Category & Business Development Specialist" (qualche punto in meno del titolo esatto)
            two = set()
            for t in c["titles_en"] + c["titles_it"]:
                two |= title_pairs(t)
                singles |= title_singles(t)
            if two:
                pairs.append((c["id"], pts - 5, _words_rx(two)))
    fams += pairs
    wide = _words_rx(profile.get("title_words") or [])
    if wide:  # titoli non previsti che contengono una parola del mestiere: entrano come candidati, decide il giudice AI
        fams.append((OTHER, 24, wide))
    labels[OTHER] = "Altri ruoli possibili"
    FAMILIES, FAMILY_LABEL = fams, labels
    # nelle sue città basta una parola di mestiere (dal profilo o dai titoli che ha scelto) perché l'annuncio arrivi al giudice AI;
    # lo stesso per gli annunci delle aziende che segue. Nel resto d'Europa no: sarebbero troppi annunci per la quota AI gratuita
    near = _words_rx({w for w in singles | {str(x).lower() for x in lr.get("words") or []} if w not in off and w not in BROAD})
    NEAR_WORDS = re.compile(near, re.I) if near else NEVER
    follow = _words_rx([c for c in lr.get("companies") or [] if c.lower() not in off])
    FOLLOW = re.compile(follow, re.I) if follow else NEVER
    LOCAL_TITLES = re.compile(_words_rx(local), re.I) if local else None
    # titoli da scartare: troppo senior per chi ha pochi anni, stage (se non cercati), lingue non parlate, altri mestieri dal profilo
    # (un filtro che avrebbe tolto annunci che lei ha scelto si spegne: lo decide learn.py, vedi "gates_off")
    ex, gates_off = [], set(lr.get("gates_off") or [])
    if USER["years"] < 6 and "senior" not in gates_off:
        ex.append(r"\b(director|directeur|direttore|directora?|vp|vice president|head of|chief|principal)\b")
    if "stage" not in (ans.get("level") or "").lower() and "intern" not in (ans.get("level") or "").lower() and "stage" not in gates_off:
        ex.append(r"\b(intern|internship|working student|werkstudent|trainee programme|apprentice|apprenti\w*|alternance|stagiaire|"
                  r"praktikum|praktikant\w*|stage|tirocinio|becari[oa]|pr[áa]cticas|est[áa]gio)\b")
    spoken = [w for code, w in SPEAKING.items() if code not in USER["langs"]]
    if spoken:
        ex.append(r"\b(" + "|".join(spoken) + r"|nordic|turkish|arabic|hebrew|russian)[- ]speak\w*")
    if "de" not in USER["langs"]:
        ex.append(r"\(\s*[mwfdxi*]\s*[/|]\s*[mwfdxi*]")
    unex = {str(x).lower() for x in lr.get("unexclude") or []}
    own = _words_rx([t for t in profile.get("exclude_titles") or [] if t.lower() not in unex])
    if own:
        ex.append(own)
    TITLE_EXCLUDE = re.compile("|".join(ex), re.I) if ex else NEVER
    SKILL_LIST = [(w, re.compile(_words_rx([w]), re.I)) for w in profile.get("skills") or []]
    unav = {str(x).lower() for x in lr.get("unavoid") or []}
    words = [w for w in profile.get("avoid_words") or [] if w.lower() not in unav]
    avoid = _words_rx(words)
    MOBILITY_STRONG = re.compile(avoid, re.I) if avoid else NEVER
    MOBILITY_WEAK = NEVER
    # nel testo si contano solo le parole che non hanno altri significati: "auto" e "car" stanno in mezzo agli annunci
    # ("auto aziendale", "company car") e toglierebbero annunci che con quel settore non c'entrano
    said = set(re.findall(r"[\wà-ÿ]+", str(ans.get("avoid") or "").lower()))
    in_text = _words_rx([w for w in words if " " in w.strip() or len(w.strip()) >= 6 or w.strip().lower() in said])
    AVOID_TEXT = re.compile(in_text, re.I) if in_text else NEVER
    pref = _words_rx(profile.get("prefer_words") or [])
    PREFER = re.compile(pref, re.I) if pref else NEVER
    details.set_extra_skills(profile.get("skills"))
    SEARCH = searchprofile.search_plan(profile)
    SEARCH["countries"] = set(ans.get("countries") or [])
    SEARCH["places"] = [p for p in ans.get("places") or [] if p.get("name") and p.get("cc")][:3]
    return True


def _lang_code(word: str):
    return next((code for code, rx in LANG_CODES if re.fullmatch(rx, word, re.I)), None)


def classify(title: str, near=None, company: str = ""):
    """Ritorna (famiglia, punti) oppure None se il titolo non è un ruolo target.
    near: l'annuncio è in una delle città della persona (lì il filtro è più largo e decide il giudice AI)."""
    if TITLE_EXCLUDE.search(title):
        return None
    for fam, pts, rx in FAMILIES:
        if re.search(rx, title, re.I):
            return fam, pts
    if near and PROFILE is not None and (NEAR_WORDS.search(title) or (company and FOLLOW.search(company))):
        return OTHER, 24
    return None


def followed(company: str) -> bool:
    return bool(company and PROFILE is not None and FOLLOW.search(company))


def infer_country(location: str):
    for name, rx in COUNTRY_MAP:
        if re.search(rx, location or "", re.I):
            return name
    if EUROPE_GENERIC.search(location or ""):
        return "Europa (remote)"
    return None


def in_europe(location: str) -> bool:
    if infer_country(location):
        return True
    return bool(re.search(r"remote", location or "", re.I)) and not NON_EUROPE.search(location or "")


def detect_mode(text: str):
    t = (text or "").lower()
    if re.search(r"hybrid|ibrido|h[íi]brido|\bhybride\b", t):
        return "Ibrido"
    if re.search(r"fully remote|100% remote|remote[- ]first|remote position|remote job|full remote|da remoto|lavoro da remoto|"
                 r"teletrabajo|t[ée]l[ée]travail|\bremote\b|\bremoto\b", t):
        return "Remote"
    if re.search(r"on-?site|in sede|in presenza|in office|office[- ]based|presencial|pr[ée]sentiel", t):
        return "On-site"
    return None


def language_check(title: str, text: str):
    """('exclude'|'nice'|'ok', lingua_rilevata). Una lingua straniera vicina a parole di competenza = requisito."""
    blob = f"{title} . {text}"
    nice = None
    for m in LANG_WORD.finditer(blob):
        around = blob[max(0, m.start() - 55): m.end() + 55]
        if not LANG_PROF.search(around):
            continue
        lang = m.group(1).capitalize()
        if _lang_code(m.group(1)) in USER["langs"]:
            continue  # è una lingua che l'utente parla
        if LANG_SOFT.search(around):
            nice = nice or lang
        else:
            return "exclude", lang
    return ("nice", nice) if nice else ("ok", "")


_STOP = {
    "en": {"the", "and", "with", "you", "our", "will", "for", "to", "of", "we", "your", "team", "experience", "is", "are", "this", "have"},
    "it": {"e", "il", "la", "di", "per", "con", "che", "una", "un", "le", "dei", "esperienza", "siamo", "sei", "del", "della",
           "nel", "gli", "sono", "nostro", "azienda", "clienti", "lavoro", "vendite", "ricerchiamo", "delle", "alla"},
    "other": {
        # tedesco
        "und", "der", "die", "das", "mit", "für", "sie", "wir", "ein", "eine", "ihre", "deine", "bei", "zu", "nicht",
        "auch", "sich", "von", "im", "als", "oder", "unser", "sowie",
        # francese
        "les", "des", "pour", "vous", "nous", "dans", "sur", "est", "avec", "une", "notre", "votre", "et", "du", "au",
        "recherchons", "poste", "entreprise", "vos", "nos",
        # spagnolo
        "el", "los", "las", "para", "por", "nuestro", "nuestra", "años", "empresa", "buscamos", "ventas", "clientes",
        "equipo", "somos", "trabajo", "experiencia", "y", "será", "tendrás", "como",
        # olandese
        "het", "een", "voor", "met", "wij", "jij", "je", "om", "zijn", "van", "naar", "onze", "jouw",
        # portoghese
        "uma", "você", "nós", "dos", "não", "com", "em", "os", "nossa", "vendas", "experiência", "ao", "são", "equipa",
        # svedese, norvegese, danese, finlandese, polacco, ceco
        "och", "att", "det", "som", "för", "är", "ett", "på", "og", "vi", "er", "til", "av", "du", "søker", "bli", "vår",
        "nye", "hos", "ja", "että", "tai", "myös", "sinä", "meillä", "olet", "oraz", "jest", "dla", "lub", "nebo", "jsme",
        "sökes", "söker", "hledáme", "szukamy", "etsimme",
    },
}


def probably_other_language(title: str, text: str) -> bool:
    """Annuncio scritto in una lingua diversa da IT/EN."""
    head = f"{title} {text[:1500]}".lower()
    if len(re.findall(r"[äöåøæüßłśżźćęąčřšžőűñ¿¡ãõçœ]", head[:600])) >= 2:
        return True  # lettere che non esistono in italiano né in inglese
    words = re.findall(r"[a-zà-ÿ]+", head)
    s = {k: sum(w in v for w in words) for k, v in _STOP.items()}
    if len(words) < 25:  # testo breve: basta qualche parola tipica e nessuna parola IT/EN
        return s["other"] >= 2 and s["en"] + s["it"] == 0
    return s["other"] > max(s["en"], s["it"]) * 1.2 and s["other"] >= 4


def years_required(text: str):
    best = None
    for m in re.finditer(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?|anni|a[ñn]os|ans|jahre|anos)", text, re.I):
        ctx = text[max(0, m.start() - 60): m.end() + 60].lower()
        if re.search(r"experien|esperienza|exp\b|background|track record|sales|erfahrung|expérience", ctx) and int(m.group(1)) <= 15:
            best = max(best or 0, int(m.group(1)))
    return best


def evaluate(job: dict):
    """Applica filtri e scoring. Ritorna il dizionario arricchito oppure (None, motivo_scarto)."""
    title, company, text = job["title"], job["company"], job.get("text", "")
    cls = classify(title, job.get("near"), company)
    if not cls:
        return None, "titolo non target"
    family, role_pts = cls

    generic = PROFILE is not None
    years_me = USER["years"]
    unread = not text.strip()
    if unread and (LOCAL_TITLES.search(title) if generic and LOCAL_TITLES else not EN_IT_TITLE.search(title)):
        # senza testo non si può verificare la lingua richiesta: resta solo se il titolo è in italiano o inglese
        return None, "testo non letto e titolo in lingua locale"

    lang_state, lang = language_check(title, text)
    if lang_state == "exclude":
        return None, f"richiede {lang}"
    local_ad = probably_other_language(title, text)
    local_lang = ""
    if local_ad:
        local_lang = LOCAL_LANGUAGE.get(infer_country(job.get("location", "")) or "", "la lingua locale")
        if local_lang in {LANG_IT[c] for c in USER["langs"]}:
            local_ad = False  # annuncio nella lingua del paese, che l'utente parla: è un annuncio normale
        elif not ENGLISH_MENTION.search(text) or "en" not in USER["langs"]:
            # annuncio in una lingua che l'utente non parla: entra solo se nomina l'inglese, e resta segnalato
            return None, "annuncio in lingua locale senza inglese"

    blob = f"{title} {company} {text}"
    strong_head = MOBILITY_STRONG.search(f"{title} {company}")
    strong_n = len((AVOID_TEXT or MOBILITY_STRONG).findall(text))
    # nel titolo o nel nome dell'azienda: fuori. Citato nel testo: fuori solo senza giudice AI, che altrimenti legge l'annuncio
    # e capisce se è davvero quel settore o se è solo nominato (un elenco di clienti, un benefit)
    if strong_head or (strong_n >= 2 and not (generic and JUDGE_ON)):
        return None, "settore o ruolo da evitare" if generic else "settore mobility"
    mob_pts = 0 if strong_n >= 2 else 5 if strong_n == 1 else (9 if MOBILITY_WEAK.search(blob) else 15)

    yrs = years_required(text)
    if yrs is not None and yrs >= max(8, years_me + 6):
        return None, "seniority troppo alta"
    junior_title = bool(re.search(r"\b(junior|graduate|entry[- ]level|associate|trainee)\b", title, re.I))
    is_senior = bool(re.search(r"\b(senior|sr|lead|staff|expert)\b", title, re.I))
    if junior_title:
        seniority = 10 if years_me <= 4 else 2      # chi ha molta esperienza è fuori misura per un ruolo junior
    elif is_senior:
        seniority = -10 if years_me < 5 else 10     # ruolo senior: penalità per chi ha pochi anni
    elif yrs is None:
        seniority = 6
    else:
        gap = yrs - years_me
        seniority = 10 if gap <= 0 else {1: 8, 2: 4, 3: 0}.get(gap, -8)
    if years_me < 5 and re.search(r"\b(enterprise|strategic|major accounts?|global accounts?|public sector)\b", title, re.I):
        seniority -= 5  # ruoli enterprise/strategici: di norma seniority alta

    head = f"{title} {text[:4000]}"
    if generic:
        found = [w for w, rx in SKILL_LIST if rx.search(head)]
        sw_hits = len(found)
    else:
        found = []
        sw_hits = len({m.lower() for m in SOFTWARE_WORDS.findall(f"{title} {text[:3000]}")})
    if generic and not unread and SKILL_LIST:
        role_pts = round(role_pts * 0.75)   # 30 / 25 / 20 / 18
        sw_pts = {0: 0, 1: 12, 2: 22, 3: 29, 4: 34}.get(sw_hits, 38)
        if family == OTHER and sw_hits < (0 if JUDGE_ON else 2):  # con il giudice AI attivo decide lui; senza, servono competenze citate
            return None, "titolo generico senza tue competenze"
    elif unread:
        sw_pts = 8  # testo non disponibile: valore neutro
    elif generic and not SKILL_LIST:
        sw_pts = 15
    else:
        sw_pts = 0 if sw_hits == 0 else 8 if sw_hits == 1 else 14 if sw_hits == 2 else 19 if sw_hits <= 4 else 25

    lang_pts = 10 if lang_state == "ok" else 6
    # Ruolo dedicato a un mercato di cui l'utente non parla la lingua (es. "Account Executive, France"): quasi sempre serve
    local_market = bool(LOCAL_MARKET_TITLE.search(title)) and lang_state == "ok" and not local_ad and USER["langs"] <= {"it", "en"}
    if local_market:
        lang_pts = 0
    if local_ad:
        lang_pts = 0

    preferred = generic and bool(PREFER.search(f"{title} {company} {text[:3000]}"))
    score = max(0, min(100, role_pts + sw_pts + mob_pts + seniority + lang_pts - (8 if unread else 0) + (8 if preferred else 0)))

    # motivi del punteggio: chip brevi ("ok" = punto a favore, "warn" = da controllare)
    reasons = [{"t": f"Ruolo {FAMILY_LABEL[family]}", "k": "ok"}]
    if generic:
        if sw_hits >= 2:
            reasons.append({"t": "Tue competenze citate: " + ", ".join(found[:4]), "k": "ok"})
        elif not unread and SKILL_LIST:
            reasons.append({"t": "Poche tue competenze citate nell'annuncio", "k": "warn"})
        if preferred:
            reasons.append({"t": "Settore che preferisci", "k": "ok"})
        if job.get("near") and followed(company):
            reasons.append({"t": "Azienda che segui", "k": "ok"})
        if MOBILITY_STRONG is not NEVER and mob_pts != 15:
            reasons.append({"t": "Cita un settore che hai escluso", "k": "warn"})
    else:
        reasons.append({"t": "Software B2B", "k": "ok"} if sw_hits >= 2 else {"t": "Componente software poco esplicita", "k": "warn"})
        reasons.append({"t": "Lontano dalla mobility", "k": "ok"} if mob_pts == 15 else {"t": "Verifica il legame con mobility/trasporti", "k": "warn"})
    if yrs and yrs > years_me:
        reasons.append({"t": f"Richiesti {yrs} anni di esperienza (tu: {years_me})", "k": "warn"})
    elif is_senior and years_me < 5:
        reasons.append({"t": "Livello senior", "k": "warn"})
    elif junior_title and years_me > 4:
        reasons.append({"t": "Ruolo junior: sotto il tuo livello", "k": "warn"})
    else:
        reasons.append({"t": "Livello in linea", "k": "ok"})
    if lang_state == "nice":
        reasons.append({"t": f"{lang} solo preferibile", "k": "ok"})
    if local_market:
        reasons.append({"t": "Verifica se serve la lingua del paese", "k": "warn"})
    if local_ad:
        reasons.append({"t": f"Annuncio in {local_lang} (cita l'inglese): la lingua locale probabilmente serve", "k": "warn"})
    if unread:
        reasons.append({"t": "Testo dell'annuncio non letto: requisiti da verificare", "k": "warn"})
    rationale = ". ".join(r["t"] for r in reasons) + "."
    mine = ", ".join(LANG_IT.get(c, c).capitalize() for c in ("it", "en", "es", "fr", "de", "pt", "nl") if c in USER["langs"]) or "Italiano, Inglese"
    languages = mine if lang_state == "ok" else f"{mine} ({lang} preferibile)"
    if local_market:
        languages = "Da verificare (mercato locale)"
    if local_ad:
        languages = f"Inglese citato, {local_lang} da verificare"
    if unread:
        languages = "Da verificare (annuncio non letto)"
    job = dict(job)
    job.update({
        "role_family": family,
        "score": score,
        "rationale": rationale,
        "reasons": reasons,
        "languages": languages,
        "local_ad": local_ad,
        "preferred": bool(generic and preferred),
        "mode": detect_mode(f"{job.get('location', '')} {text[:2500]}"),
    })
    return job, ""

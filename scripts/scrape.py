#!/usr/bin/env python3
"""Scrape Wikipedia for education data on US elected officials.

Outputs (relative to project root):
  data/officials.json
  data/schools.json
  data/roster.json
  data/cache/*.html
"""
import json, re, time, hashlib, urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
DATA.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

UA = "OfficialsEducationDB/1.0 (josh.greenman@gmail.com)"
SESS = requests.Session()
SESS.headers["User-Agent"] = UA
SLEEP = 0.35

def fetch(url, force=False):
    h = hashlib.md5(url.encode()).hexdigest()
    p = CACHE / f"{h}.html"
    if p.exists() and not force:
        return p.read_text(encoding="utf-8")
    r = SESS.get(url, timeout=30)
    r.raise_for_status()
    time.sleep(SLEEP)
    p.write_text(r.text, encoding="utf-8")
    return r.text

def soup(url, force=False):
    return BeautifulSoup(fetch(url, force=force), "html.parser")

STATE_ABBR = {
"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
"Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID",
"Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
"Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
"Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ",
"New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK",
"Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
"Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA",
"West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"
}
TERRITORIES = {"American Samoa","Guam","Northern Mariana Islands","Puerto Rico",
               "U.S. Virgin Islands","United States Virgin Islands","District of Columbia"}

def is_person_link(a, exclude=set()):
    if not a or not a.get("href"): return False
    href = a["href"]
    if not href.startswith("/wiki/"): return False
    if any(x in href for x in [":", "#", "File:", "Category:", "Help:", "Portal:"]):
        return False
    title = a.get("title") or a.get_text(strip=True)
    if not title: return False
    if title in STATE_ABBR or title in TERRITORIES: return False
    if title in exclude: return False
    bad = ["State","County","District","Republican Party","Democratic Party",
           "Independent","Libertarian","University","College","School","Institute",
           "House of Representatives","Senate","Congress","Election","List of"]
    if any(b in title for b in bad): return False
    txt = a.get_text(strip=True)
    if " " not in txt and "." not in txt: return False
    return True

# ---------- Roster collection ----------

def collect_governors():
    s = soup("https://en.wikipedia.org/wiki/List_of_current_United_States_governors")
    out = {}
    for tbl in s.find_all("table", class_="wikitable"):
        headers = " ".join(th.get_text(" ", strip=True) for th in tbl.find_all("th")[:10])
        if "Governor" not in headers or "State" not in headers: continue
        for tr in tbl.find_all("tr")[1:]:
            cells = tr.find_all(["td","th"])
            if len(cells) < 3: continue
            state_name = None
            for a in cells[0].find_all("a"):
                t = a.get_text(strip=True)
                if t in STATE_ABBR: state_name = t; break
            if not state_name: continue
            gov = None
            for c in cells[1:]:
                for a in c.find_all("a"):
                    if is_person_link(a): gov = a; break
                if gov: break
            if not gov: continue
            row_text = tr.get_text(" ", strip=True)
            party = "D" if "Democratic" in row_text else "R" if "Republican" in row_text else ("I" if "Independent" in row_text else None)
            if state_name not in out:
                out[state_name] = {
                    "name": gov.get_text(strip=True), "office": "Governor",
                    "state": STATE_ABBR[state_name], "city": None, "district": None,
                    "party": party,
                    "wikipedia_url": "https://en.wikipedia.org" + gov["href"],
                }
    return list(out.values())

def collect_senators():
    s = soup("https://en.wikipedia.org/wiki/List_of_current_United_States_senators")
    out = []
    state_count = {}
    seen_urls = set()
    best = None; best_rows = 0
    for tbl in s.find_all("table", class_="wikitable"):
        headers = " ".join(th.get_text(" ", strip=True) for th in tbl.find_all("th")[:14])
        if "Senator" not in headers and "Senators" not in headers: continue
        rows = tbl.find_all("tr")
        if len(rows) > best_rows: best = tbl; best_rows = len(rows)
    if not best: return out
    last_state = None
    for tr in best.find_all("tr")[1:]:
        cells = tr.find_all(["td","th"])
        if len(cells) < 3: continue
        row_text = tr.get_text(" ", strip=True)
        state_ab = None
        for a in cells[0].find_all("a"):
            t = a.get_text(strip=True)
            if t in STATE_ABBR: state_ab = STATE_ABBR[t]; break
        if not state_ab:
            for sn, ab in STATE_ABBR.items():
                if cells[0].get_text(" ", strip=True).startswith(sn):
                    state_ab = ab; break
        if not state_ab:
            # rowspan continuation — inherit previous state
            state_ab = last_state
        else:
            last_state = state_ab
        if not state_ab: continue
        if state_count.get(state_ab, 0) >= 2: continue
        person = None
        for a in tr.find_all("a"):
            if is_person_link(a): person = a; break
        if not person: continue
        href = person["href"]
        if href in seen_urls: continue
        seen_urls.add(href)
        party = "D" if "Democratic" in row_text else "R" if "Republican" in row_text else ("I" if "Independent" in row_text else None)
        state_count[state_ab] = state_count.get(state_ab, 0) + 1
        out.append({
            "name": person.get_text(strip=True), "office": "Senator", "state": state_ab,
            "city": None, "district": None, "party": party,
            "wikipedia_url": "https://en.wikipedia.org" + href,
        })
    return out

def collect_house():
    s = soup("https://en.wikipedia.org/wiki/List_of_current_members_of_the_United_States_House_of_Representatives")
    out = []
    for tbl in s.find_all("table", class_="wikitable"):
        headers = " ".join(th.get_text(" ", strip=True) for th in tbl.find_all("th")[:14])
        if "District" not in headers: continue
        if not any(x in headers for x in ["Member","Representative","Name","Incumbent"]): continue
        for tr in tbl.find_all("tr")[1:]:
            cells = tr.find_all(["td","th"])
            if len(cells) < 4: continue
            dist_txt = cells[0].get_text(" ", strip=True)
            m = re.match(r"([A-Za-z][A-Za-z\.\s]+?)\s+(\d+|at-large|At-large|AL)\b", dist_txt)
            if not m: continue
            state_full = m.group(1).strip().rstrip(".")
            dnum = m.group(2)
            if dnum.lower() in ("at-large","al"): dnum = "AL"
            state_ab = STATE_ABBR.get(state_full)
            if not state_ab: continue
            district = f"{state_ab}-{dnum}"
            person = None
            for c in cells[1:4]:
                for a in c.find_all("a"):
                    if is_person_link(a, exclude={state_full}): person = a; break
                if person: break
            if not person: continue
            row_text = tr.get_text(" ", strip=True)
            party = "D" if "Democratic" in row_text else "R" if "Republican" in row_text else ("I" if "Independent" in row_text else None)
            out.append({
                "name": person.get_text(strip=True), "office": "Representative", "state": state_ab,
                "city": None, "district": district, "party": party,
                "wikipedia_url": "https://en.wikipedia.org" + person["href"],
            })
    seen, uniq = set(), []
    for r in out:
        if r["district"] in seen: continue
        seen.add(r["district"]); uniq.append(r)
    return uniq

MAYORS = [
    ("Eric Adams",        "Eric_Adams",          "New York, NY",       "NY", "D"),
    ("Karen Bass",        "Karen_Bass",          "Los Angeles, CA",    "CA", "D"),
    ("Brandon Johnson",   "Brandon_Johnson",     "Chicago, IL",        "IL", "D"),
    ("John Whitmire",     "John_Whitmire",       "Houston, TX",        "TX", "D"),
    ("Kate Gallego",      "Kate_Gallego",        "Phoenix, AZ",        "AZ", "D"),
    ("Cherelle Parker",   "Cherelle_Parker",     "Philadelphia, PA",   "PA", "D"),
    ("Gina Ortiz Jones",  "Gina_Ortiz_Jones",    "San Antonio, TX",    "TX", "D"),
    ("Todd Gloria",       "Todd_Gloria",         "San Diego, CA",      "CA", "D"),
    ("Eric Johnson",      "Eric_Johnson_(Texas_politician)", "Dallas, TX", "TX", "R"),
    ("Donna Deegan",      "Donna_Deegan",        "Jacksonville, FL",   "FL", "D"),
    ("Kirk Watson",       "Kirk_Watson",         "Austin, TX",         "TX", "D"),
    ("Mattie Parker",     "Mattie_Parker",       "Fort Worth, TX",     "TX", "R"),
    ("Matt Mahan",        "Matt_Mahan",          "San Jose, CA",       "CA", "D"),
    ("Vi Lyles",          "Vi_Lyles",            "Charlotte, NC",      "NC", "D"),
    ("Andrew Ginther",    "Andrew_Ginther",      "Columbus, OH",       "OH", "D"),
    ("Joe Hogsett",       "Joe_Hogsett",         "Indianapolis, IN",   "IN", "D"),
    ("Daniel Lurie",      "Daniel_Lurie",        "San Francisco, CA",  "CA", "D"),
    ("Bruce Harrell",     "Bruce_Harrell",       "Seattle, WA",        "WA", "D"),
    ("Mike Johnston",     "Mike_Johnston_(politician)", "Denver, CO",  "CO", "D"),
    ("Muriel Bowser",     "Muriel_Bowser",       "Washington, DC",     "DC", "D"),
    ("Freddie O'Connell", "Freddie_O%27Connell", "Nashville, TN",      "TN", "D"),
    ("David Holt",        "David_Holt_(politician)", "Oklahoma City, OK", "OK", "R"),
    ("Renard Johnson",    "Renard_Johnson",      "El Paso, TX",        "TX", "D"),
    ("Michelle Wu",       "Michelle_Wu",         "Boston, MA",         "MA", "D"),
    ("Shelley Berkley",   "Shelley_Berkley",     "Las Vegas, NV",      "NV", "D"),
]

def collect_mayors():
    return [{
        "name": n, "office": "Mayor", "state": st, "city": c,
        "district": None, "party": p,
        "wikipedia_url": f"https://en.wikipedia.org/wiki/{slug}",
    } for n, slug, c, st, p in MAYORS]

# ---------- Education parsing ----------

DEGREE_PATTERNS = [
    (r"\bBachelor of Arts\b|\bB\.?A\.?\b", "BA"),
    (r"\bBachelor of Science\b|\bB\.?S\.?\b|\bB\.?Sc\.?\b", "BS"),
    (r"\bBachelor of Business Administration\b|\bB\.?B\.?A\.?\b", "BBA"),
    (r"\bBachelor of Engineering\b|\bB\.?Eng\.?\b", "BEng"),
    (r"\bBachelor of Fine Arts\b|\bB\.?F\.?A\.?\b", "BFA"),
    (r"\bBachelor of Social Work\b|\bB\.?S\.?W\.?\b", "BSW"),
    (r"\bBachelor of Laws\b|\bLL\.?B\.?\b", "LLB"),
    (r"\bBachelor's degree\b|\bBachelor\b", "Bachelor"),
    (r"\bMaster of Arts\b|\bM\.?A\.?\b", "MA"),
    (r"\bMaster of Science\b|\bM\.?S\.?\b|\bM\.?Sc\.?\b", "MS"),
    (r"\bMaster of Business Administration\b|\bM\.?B\.?A\.?\b", "MBA"),
    (r"\bMaster of Public Administration\b|\bM\.?P\.?A\.?\b", "MPA"),
    (r"\bMaster of Public Policy\b|\bM\.?P\.?P\.?\b", "MPP"),
    (r"\bMaster of Public Health\b|\bM\.?P\.?H\.?\b", "MPH"),
    (r"\bMaster of Education\b|\bM\.?Ed\.?\b", "MEd"),
    (r"\bMaster of Fine Arts\b|\bM\.?F\.?A\.?\b", "MFA"),
    (r"\bMaster of Divinity\b|\bM\.?Div\.?\b", "MDiv"),
    (r"\bMaster of Laws\b|\bLL\.?M\.?\b", "LLM"),
    (r"\bMaster of Social Work\b|\bM\.?S\.?W\.?\b", "MSW"),
    (r"\bMaster's degree\b|\bMaster\b", "Master"),
    (r"\bJuris Doctor\b|\bJ\.?D\.?\b", "JD"),
    (r"\bDoctor of Medicine\b|\bM\.?D\.?\b", "MD"),
    (r"\bDoctor of Osteopathic Medicine\b|\bD\.?O\.?\b", "DO"),
    (r"\bDoctor of Philosophy\b|\bPh\.?D\.?\b", "PhD"),
    (r"\bDoctor of Education\b|\bEd\.?D\.?\b", "EdD"),
    (r"\bDoctor of Dental Surgery\b|\bD\.?D\.?S\.?\b", "DDS"),
    (r"\bDoctor of Veterinary Medicine\b|\bD\.?V\.?M\.?\b", "DVM"),
]

def detect_degrees(text):
    positions = []
    for pat, code in DEGREE_PATTERNS:
        for m in re.finditer(pat, text):
            positions.append((m.start(), code))
    positions.sort()
    seen = set(); found = []
    for _, c in positions:
        if c in seen: continue
        seen.add(c); found.append(c)
    return found

def split_into_schools(td):
    segments = []
    current_html = []; current_text = []
    def flush():
        if current_text and any(t.strip() for t in current_text):
            segments.append({"text": " ".join(current_text).strip(), "links": list(current_html)})
    for child in td.children:
        if isinstance(child, Tag) and child.name == "br":
            flush(); current_html.clear(); current_text.clear(); continue
        if isinstance(child, Tag) and child.name == "ul":
            for li in child.find_all("li", recursive=False):
                flush(); current_html.clear(); current_text.clear()
                segments.append({"text": li.get_text(" ", strip=True), "links": list(li.find_all("a"))})
            continue
        if isinstance(child, NavigableString):
            current_text.append(str(child))
        elif isinstance(child, Tag):
            current_text.append(child.get_text(" ", strip=True))
            if child.name == "a": current_html.append(child)
            else: current_html.extend(child.find_all("a"))
    flush()
    return segments

SCHOOL_KEYWORDS = ["University","College","Institute","School","Academy","Conservatory","Polytechnic","Seminary"]

def is_school_link(a):
    if not a or not a.get("href"): return False
    href = a["href"]
    if not href.startswith("/wiki/"): return False
    title = a.get("title") or a.get_text(strip=True)
    if not title: return False
    if any(k in title for k in ["Bachelor of","Master of","Juris Doctor","Doctor of","Philosophiae","Associate of"]): return False
    if title.startswith("LL.") or title.startswith("Ph.D"): return False
    return any(k in title for k in SCHOOL_KEYWORDS) or "Law School" in title or "Business School" in title

def parse_education(soup_obj):
    ib = soup_obj.find("table", class_="infobox")
    if not ib: return [], ""
    edu_td = None
    for tr in ib.find_all("tr"):
        th = tr.find("th")
        if not th: continue
        label = th.get_text(" ", strip=True).lower()
        if label == "education" or "alma mater" in label:
            edu_td = tr.find("td"); break
    if not edu_td: return [], ""
    segments = split_into_schools(edu_td)
    raw = edu_td.get_text(" | ", strip=True)
    out = []
    for seg in segments:
        text = seg["text"]
        if not text: continue
        school = None
        for a in seg["links"]:
            if is_school_link(a): school = a.get_text(strip=True); break
        if not school:
            m = re.search(r"([A-Z][^()]*?(?:" + "|".join(SCHOOL_KEYWORDS) + r")[^()]*?)(?:\s*\(|$)", text)
            if m: school = m.group(1).strip(", ;:")
        if not school:
            school = re.split(r"\s*\(", text)[0].strip(", ;:")
        if not school or len(school) < 3: continue
        if any(k in school for k in ["Bachelor of","Master of","Juris Doctor","Doctor of"]): continue
        degrees = detect_degrees(text)
        field = None
        paren = re.search(r"\(([^)]+)\)", text)
        if paren:
            inner = paren.group(1)
            for p in [x.strip() for x in re.split(r"[,;]", inner)]:
                if not p: continue
                if detect_degrees(p): continue
                if re.fullmatch(r"\d{4}", p): continue
                if re.fullmatch(r"(19|20)\d{2}\s*[-–]\s*(19|20)?\d{2,4}", p): continue
                if len(p) <= 2: continue
                field = p; break
        year = None
        ym = re.search(r"\b(19|20)\d{2}\b", text)
        if ym: year = ym.group(0)
        if degrees:
            for d in degrees:
                out.append({"school": school, "degree": d, "field": field, "year": year})
        else:
            out.append({"school": school, "degree": None, "field": field, "year": year})
    return out, raw

# ---------- School classification ----------

KNOWN_PRIVATE = {
"Harvard University","Harvard College","Harvard Law School","Harvard Kennedy School","Harvard Business School",
"Yale University","Yale Law School","Yale College","Princeton University","Columbia University",
"Columbia Law School","Columbia Business School","Cornell University","Brown University","Dartmouth College",
"University of Pennsylvania","Stanford University","Stanford Law School","Massachusetts Institute of Technology",
"MIT","Duke University","Northwestern University","Vanderbilt University","University of Chicago",
"Johns Hopkins University","Georgetown University","George Washington University","American University",
"Boston College","Boston University","Tufts University","Brandeis University","New York University",
"Fordham University","University of Notre Dame","Wake Forest University","Emory University","Tulane University",
"Rice University","Southern Methodist University","Baylor University","Pepperdine University",
"University of Southern California","Loyola Marymount University","Santa Clara University",
"Saint Louis University","Marquette University","Creighton University","Villanova University",
"Drexel University","Lehigh University","Carnegie Mellon University","Case Western Reserve University",
"Howard University","Morehouse College","Spelman College","Hampton University","Wellesley College",
"Smith College","Mount Holyoke College","Bryn Mawr College","Vassar College","Williams College",
"Amherst College","Bowdoin College","Bates College","Colby College","Middlebury College","Hamilton College",
"Colgate University","Bucknell University","Lafayette College","Swarthmore College","Haverford College",
"Pomona College","Claremont McKenna College","Harvey Mudd College","Reed College","Whitman College",
"Lewis & Clark College","Occidental College","Trinity College","Wesleyan University","Skidmore College",
"Sarah Lawrence College","Bard College","Liberty University","Regent University","Quinnipiac University",
"Hofstra University","Pace University","Seton Hall University","Catholic University of America",
"Albany Law School","Suffolk University","DePaul University","Loyola University Chicago",
"Northeastern University","Yeshiva University","Brigham Young University","Wheaton College",
"Calvin University","Furman University","Davidson College","Rhodes College","Trinity University",
"Stetson University","Mercer University","Washington and Lee University","University of Richmond",
"University of Tulsa","University of Denver","University of San Diego","University of Miami",
"Syracuse University","Stevens Institute of Technology","Rensselaer Polytechnic Institute",
"Worcester Polytechnic Institute","Babson College","Bentley University","Bryant University",
"Providence College","Stonehill College","DePauw University","Earlham College","Kenyon College",
"Oberlin College","Denison University","Texas Christian University","Drake University","Samford University",
}

KNOWN_PUBLIC = {
"University of California, Berkeley","University of California, Los Angeles",
"University of California, Davis","University of California, San Diego","University of California, Irvine",
"University of California, Santa Barbara","University of California, Riverside","University of California, Santa Cruz",
"University of California, Hastings College of the Law","University of California College of the Law, San Francisco",
"UC Hastings","UCLA","UC Berkeley","University of Virginia","University of Michigan","University of Michigan Law School",
"University of North Carolina at Chapel Hill","University of North Carolina","UNC Chapel Hill",
"University of Texas at Austin","University of Texas","University of Texas School of Law",
"University of Florida","Florida State University","University of Georgia","Georgia State University",
"Georgia Institute of Technology","Georgia Tech","University of Wisconsin–Madison","University of Wisconsin",
"University of Illinois Urbana-Champaign","University of Illinois at Urbana–Champaign","University of Illinois",
"University of Illinois Chicago","Indiana University","Indiana University Bloomington",
"Ohio State University","The Ohio State University","Michigan State University","Pennsylvania State University",
"Penn State","University of Pittsburgh","Temple University","Rutgers University","Rutgers Law School",
"University of Maryland, College Park","University of Maryland","University of Connecticut",
"University of Massachusetts Amherst","University of Vermont","University of New Hampshire","University of Maine",
"University of Rhode Island","University of Delaware","University of Washington","Washington State University",
"University of Oregon","Oregon State University","University of Colorado Boulder","University of Colorado",
"Colorado State University","University of Utah","Utah State University","University of Arizona",
"Arizona State University","University of Nevada, Las Vegas","University of Nevada, Reno","University of New Mexico",
"University of Hawaii","University of Alaska Anchorage","University of Alaska Fairbanks",
"University of Alabama","Auburn University","University of Mississippi","Mississippi State University",
"University of Tennessee","University of Tennessee, Knoxville","University of Kentucky","University of Louisville",
"University of South Carolina","Clemson University","University of Arkansas","Louisiana State University","LSU",
"University of Oklahoma","Oklahoma State University","Texas A&M University","Texas Tech University",
"University of Houston","University of North Texas","Texas State University","University of Iowa","Iowa State University",
"University of Minnesota","University of Missouri","Missouri State University","University of Kansas","Kansas State University",
"University of Nebraska","University of Nebraska–Lincoln","University of South Dakota","South Dakota State University",
"University of North Dakota","North Dakota State University","University of Wyoming","University of Montana",
"Montana State University","University of Idaho","Boise State University","City University of New York","CUNY",
"Brooklyn College","Hunter College","Queens College","Baruch College","City College of New York",
"John Jay College of Criminal Justice","State University of New York","SUNY","University at Albany, SUNY",
"Stony Brook University","Binghamton University","University at Buffalo","California Polytechnic State University",
"California State University","San Francisco State University","San Diego State University","San Jose State University",
"California State University, Long Beach","California State University, Fullerton","California State University, Northridge",
"California State University, Sacramento","Florida International University","University of Central Florida",
"Florida Atlantic University","Virginia Commonwealth University","George Mason University","Virginia Tech",
"James Madison University","Old Dominion University","College of William & Mary","Norfolk State University",
"Virginia State University","Northern Arizona University","University of West Florida","Northern Illinois University",
"Western Illinois University","Eastern Illinois University","Illinois State University","Northern Kentucky University",
"Eastern Kentucky University","Western Kentucky University","Middle Tennessee State University","East Tennessee State University",
"Tennessee State University","Towson University","Salisbury University","Frostburg State University",
"Bowie State University","Morgan State University","Coppin State University","University of Maryland Eastern Shore",
}

MILITARY_ACADEMIES = {
"United States Military Academy","United States Naval Academy","United States Air Force Academy",
"United States Coast Guard Academy","United States Merchant Marine Academy","The Citadel",
"Virginia Military Institute","Naval Postgraduate School","Air War College","National War College",
"Army War College","United States Army War College","Naval War College",
}

ALIASES = {
"Harvard":"Harvard University","Yale":"Yale University","Princeton":"Princeton University",
"Stanford":"Stanford University","MIT":"Massachusetts Institute of Technology",
"UCLA":"University of California, Los Angeles","UC Berkeley":"University of California, Berkeley",
"Penn State":"Pennsylvania State University","UNC":"University of North Carolina at Chapel Hill",
"LSU":"Louisiana State University","BYU":"Brigham Young University","NYU":"New York University",
"USC":"University of Southern California","Georgia Tech":"Georgia Institute of Technology",
"West Point":"United States Military Academy",
}

def normalize_school(name):
    n = (name or "").strip().strip(",;:.")
    if n in ALIASES: return ALIASES[n]
    return n

def classify_school(name):
    n = normalize_school(name)
    if n in KNOWN_PRIVATE: return "private"
    if n in KNOWN_PUBLIC: return "public"
    if n in MILITARY_ACADEMIES: return "military"
    if re.search(r"^University of [A-Z]", n) and ", " not in n and "School" not in n: return "public"
    if re.search(r"\bState University\b|\bState College\b|\bCommunity College\b|\bCity College\b|\bCity University\b", n):
        return "public"
    return None

def lookup_school_wikipedia(name):
    title = name.replace(" ", "_")
    url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}"
    try: s = soup(url)
    except Exception: return "unknown"
    ib = s.find("table", class_="infobox")
    if not ib: return "unknown"
    for tr in ib.find_all("tr"):
        th = tr.find("th")
        if not th: continue
        if "Type" in th.get_text():
            td = tr.find("td")
            if not td: continue
            t = td.get_text(" ", strip=True).lower()
            if "public" in t and "private" not in t: return "public"
            if "private" in t and "public" not in t: return "private"
            if "military" in t: return "military"
    return "unknown"

# ---------- Main ----------

def main():
    print("Collecting rosters...", flush=True)
    rosters = []
    rosters += collect_governors(); print(f"  governors: {sum(1 for r in rosters if r['office']=='Governor')}")
    rosters += collect_senators();  print(f"  senators:  {sum(1 for r in rosters if r['office']=='Senator')}")
    rosters += collect_house();     print(f"  house:     {sum(1 for r in rosters if r['office']=='Representative')}")
    rosters += collect_mayors();    print(f"  mayors:    {sum(1 for r in rosters if r['office']=='Mayor')}")
    print(f"  total: {len(rosters)}")
    (DATA / "roster.json").write_text(json.dumps(rosters, indent=2))

    print("Fetching education pages...", flush=True)
    all_schools = set()
    out = []
    for i, r in enumerate(rosters):
        try:
            s = soup(r["wikipedia_url"])
            edu, raw = parse_education(s)
        except Exception as e:
            edu, raw = [], f"FETCH_ERR: {e}"
        for e in edu:
            e["school"] = normalize_school(e.get("school"))
            if e["school"]: all_schools.add(e["school"])
        r["education"] = edu
        r["education_raw"] = raw
        r["notes"] = None if edu else "no public education info on Wikipedia"
        out.append(r)
        if (i+1) % 50 == 0: print(f"  {i+1}/{len(rosters)}", flush=True)

    (DATA / "officials.json").write_text(json.dumps(out, indent=2))

    print(f"Classifying {len(all_schools)} schools...", flush=True)
    schools = []
    for name in sorted(all_schools):
        sector = classify_school(name)
        if sector is None: sector = lookup_school_wikipedia(name)
        schools.append({"school": name, "sector": sector})
    (DATA / "schools.json").write_text(json.dumps(schools, indent=2))

    by_office = {}
    with_edu = 0
    for r in out:
        by_office[r["office"]] = by_office.get(r["office"], 0) + 1
        if r["education"]: with_edu += 1
    print("DONE")
    print(f"  Officials: {len(out)} ({by_office})")
    print(f"  With education: {with_edu}/{len(out)}")
    pub = sum(1 for s in schools if s["sector"]=="public")
    pri = sum(1 for s in schools if s["sector"]=="private")
    unk = sum(1 for s in schools if s["sector"] not in ("public","private","military","foreign"))
    mil = sum(1 for s in schools if s["sector"]=="military")
    print(f"  Schools: {len(schools)} ({pub} public / {pri} private / {mil} military / {unk} unknown)")

if __name__ == "__main__":
    main()

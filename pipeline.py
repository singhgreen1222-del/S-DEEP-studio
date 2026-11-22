"""Cloud pipeline: plan -> news -> SEO scripts (Gemini free) -> render -> upload+schedule -> analytics -> insights."""
import json, os, random, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"; SCRIPTS = DATA / "scripts"; COMM = DATA / "community"      # git mein save hota hai
WORK = ROOT / "work"; OUT = WORK / "out"; LOOKS = WORK / "looks"                # temporary (runner par)
HOST = ROOT / "host.png"
for _p in (DATA, SCRIPTS, COMM, OUT, LOOKS):
    _p.mkdir(parents=True, exist_ok=True)
IST = timezone(timedelta(hours=5, minutes=30))
STATE_F = DATA / "state.json"

FEEDS = {
    "RBI Press Releases": "https://rbi.org.in/pressreleases_rss.xml",
    "SEBI": "https://www.sebi.gov.in/sebirss.xml",
    "Google News: Nifty Sensex": "https://news.google.com/rss/search?q=Nifty+Sensex+when:2d&hl=en-IN&gl=IN&ceid=IN:en",
    "Google News: RBI SEBI": "https://news.google.com/rss/search?q=RBI+OR+SEBI+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
    "Google News: Reuters India": "https://news.google.com/rss/search?q=site:reuters.com+India+economy+OR+markets+when:3d&hl=en-IN&gl=IN&ceid=IN:en",
}


# ---------------- state ----------------
def load():
    s = json.loads(STATE_F.read_text(encoding="utf-8")) if STATE_F.exists() else {}
    s.setdefault("jobs", {}); s.setdefault("recent_looks", [])
    s["settings"] = {"engine": os.environ.get("ENGINE", "edge"), "voice": os.environ.get("VOICE", "hi-IN-MadhurNeural"),
                     "model": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "music": "", "intro": True, "ref": ""}
    return s


def save(s):
    s2 = {k: v for k, v in s.items() if k != "settings"}
    STATE_F.write_text(json.dumps(s2, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- planner ----------------
def plan_week(s, monday):
    new = 0
    for i in range(7):
        day = monday + timedelta(days=i)
        slots = [("short", 11), ("short", 19)]
        if day.weekday() in (2, 4):
            slots.append(("long", 18))
        if day.weekday() in (0, 2, 6):
            slots.append(("community", 13))
        for kind, hh in slots:
            jid = f"{day:%Y%m%d}_{kind}_{hh:02d}"
            if jid not in s["jobs"]:
                s["jobs"][jid] = {"id": jid, "kind": kind, "publish_at": datetime(day.year, day.month, day.day, hh, tzinfo=IST).isoformat(),
                                  "scripted": False, "rendered": False, "uploaded": False, "scheduled": False,
                                  "video_id": "", "link": "", "error": "", "look": "", "title": "", "warnings": []}
                new += 1
    save(s)
    return new


# ---------------- news ----------------
def fetch_news(limit=30):
    import calendar, feedparser
    items, seen = [], set()
    for name, url in FEEDS.items():
        try:
            d = feedparser.parse(url)
        except Exception as e:
            print("feed error", name, e); continue
        for e in d.entries[:12]:
            title = (e.get("title") or "").strip()
            if not title or title.lower() in seen:
                continue
            seen.add(title.lower())
            ts = calendar.timegm(e["published_parsed"]) if e.get("published_parsed") else 0
            items.append({"source": name, "title": title, "link": e.get("link", ""), "ts": ts,
                          "published": e.get("published") or e.get("updated") or "",
                          "summary": re.sub(r"<[^>]+>", " ", e.get("summary", "") or "")[:350].strip()})
    items.sort(key=lambda x: -x["ts"])
    items = items[:limit]
    (DATA / "news.json").write_text(json.dumps({"fetched_at": datetime.now(IST).isoformat(), "items": items},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def news_block(items):
    return "\n".join(f"[{i}] {x['source']} | {x['published']} | {x['title']} | {x['summary']} | {x['link']}"
                     for i, x in enumerate(items))


# ---------------- LLM scripts (SEO + learnings) ----------------
RULES = ("You write for S DEEP, a Hindi finance YouTube channel about the Indian share market and economy. "
         "Output language: Hindi in Devanagari (terms like Nifty, Sensex, RBI, SEBI, GDP, FII may stay in English). "
         "Use ONLY facts present in the NEWS ITEMS below. Never invent numbers, dates, quotes, companies or links. "
         "If a number is not in the items, do not state it. Clearly separate facts from expectations/opinion (say 'अनुमान'). "
         "Mention the source name and date for key claims. No guaranteed returns, no buy/sell/hold advice, no stock tips. "
         "End with one short line: educational content, not investment advice. Return ONLY valid JSON.\n")
SEO = ("SEO rules: title <=60 chars, main search keyword inside the first 40 chars, honest curiosity (no fake claims, no ALL CAPS). "
       "description: first 2 lines contain the main keywords and summarise the video (150+ words for long, 40+ words for short). "
       "keywords: 8-15 search phrases people actually type (Hindi + Roman/English). hashtags: exactly 3, like #Nifty #ShareMarket #SDEEP.\n")


def learnings():
    f = DATA / "insights.json"
    try:
        p = json.loads(f.read_text(encoding="utf-8")).get("next_week_plan", {})
    except Exception:
        return ""
    bits = [f"{k}: {p[k]}" for k in ("topics_to_emphasize", "topics_to_avoid", "title_style_tip") if p.get(k)]
    return ("Performance learnings from past videos (use ONLY to pick angle/style, never to change facts): "
            + "; ".join(bits) + "\n") if bits else ""


def _base():
    return RULES + SEO + learnings()


def llm_json(s, prompt, tries=2):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY secret set nahi hai")
    from google import genai
    from google.genai import types
    client, last = genai.Client(api_key=key), None
    for _ in range(tries):
        try:
            r = client.models.generate_content(model=s["settings"]["model"], contents=prompt,
                                               config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.6))
            return json.loads(r.text)
        except Exception as e:
            last = e; time.sleep(10)
    raise RuntimeError(f"LLM error: {last}")


def _clean_sources(cfg, items, fallback):
    links = {x["link"] for x in items}
    cfg["sources"] = [u for u in cfg.get("sources", []) if u in links] or [fallback]


def _unsupported(texts, news):
    norm = lambda t: set(x.replace(",", "").rstrip(".") for x in re.findall(r"\d[\d,\.]*", t))
    return sorted(norm(texts) - norm(news))


SHORT_SCHEMA = ('Write ONE YouTube Shorts script: 70-95 spoken words, 4-6 scenes, first scene is a hook. Return JSON: '
                '{"title":"","thumb_text":"2-4 WORDS ROMAN CAPS","description":"","keywords":[],"hashtags":[],"tags":[],'
                '"sources":["urls copied exactly from items"],"scenes":[{"text":"Hindi text","chart":null}]}. '
                'Set "chart" to "^NSEI" or "^BSESN" for ONE scene only if it discusses the overall index trend.\n')
OUTLINE_SCHEMA = ('Plan a 20-minute long video in exactly 10 sections (hook, context, 3-4 news deep dives, what to watch next, '
                  'risks/uncertainties, recap + disclaimer). Return JSON: {"title":"","thumb_text":"2-4 WORDS ROMAN CAPS","description":"",'
                  '"keywords":[],"hashtags":[],"tags":[],"sources":["urls copied exactly from items"],'
                  '"sections":[{"heading":"short chapter title","points":"what to cover, which item numbers","chart":null}]}. '
                  'chart may be "^NSEI" or "^BSESN" for at most 3 sections.\n')


def _short(s, items, idx):
    cfg = llm_json(s, _base() + SHORT_SCHEMA + f"Focus story: item [{idx % len(items)}].\nNEWS ITEMS:\n" + news_block(items))
    _clean_sources(cfg, items, items[idx % len(items)]["link"])
    return cfg


def _long(s, items, k):
    from make_video import split_chunks
    rot = items[k * 6:] + items[:k * 6]; nb = news_block(rot)
    cfg = llm_json(s, _base() + OUTLINE_SCHEMA + f"Long video #{k + 1} of the week; build it around the first items.\nNEWS ITEMS:\n" + nb)
    scenes, done = [], []
    for i, sec in enumerate(cfg["sections"]):
        time.sleep(4)
        r = llm_json(s, RULES + 'Write section %d of %d for the video "%s". Previous sections: %s. This section: %s - %s. '
                     'About 300 spoken Hindi words, natural spoken style, no headings. Return JSON {"text":"..."}.\nNEWS ITEMS:\n' %
                     (i + 1, len(cfg["sections"]), cfg["title"], "; ".join(done) or "none", sec["heading"], sec["points"]) + nb)
        done.append(sec["heading"])
        for j, ch in enumerate(split_chunks(r["text"], 230)):
            sc = {"text": ch, "chart": None}
            if j == 0:
                sc["chapter"] = sec["heading"]
                if sec.get("chart"):
                    sc.update(chart=sec["chart"], layout="chart_full")
            scenes.append(sc)
    cfg["scenes"] = scenes
    _clean_sources(cfg, items, rot[0]["link"])
    return cfg


def generate_script(s, jid, items, log=print):
    job = s["jobs"][jid]; kind = job["kind"]
    idx = sorted(j for j in s["jobs"] if s["jobs"][j]["kind"] == kind).index(jid)
    log(f"[{jid}] script ban rahi hai")
    if kind == "community":
        r = llm_json(s, _base() + 'Write one YouTube Community post (Hindi, <=60 words, with a question to the audience). '
                     'Return JSON {"text":"...","poll":null,"sources":["urls"]}.\nNEWS ITEMS:\n' + news_block(items[idx % 5 * 2:] + items[:idx % 5 * 2]))
        txt = r["text"] + "\n\nSources: " + ", ".join(r.get("sources", [])) + f"\nPost time: {job['publish_at']}\n(Community post API se nahi hoti: YouTube app > Create > Post se manually daalein.)"
        (COMM / f"{jid}.txt").write_text(txt, encoding="utf-8")
        job.update(scripted=True, error=""); return
    cfg = _short(s, items, idx) if kind == "short" else _long(s, items, idx)
    cfg["mode"], cfg["publish_at"] = kind, job["publish_at"]
    allt = " ".join(sc["text"] for sc in cfg["scenes"])
    job["warnings"] = [f"Number '{n}' news items mein nahi mila - verify karein" for n in _unsupported(allt, news_block(items))]
    job.update(title=cfg.get("title", ""), scripted=True, error="")
    (SCRIPTS / f"{jid}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------- looks / render / upload ----------------
def ensure_looks():
    import looks
    if not list(LOOKS.glob("*.jpg")):
        looks.make_looks(HOST, LOOKS, 12)


def pick_look(s):
    ensure_looks()
    files = sorted(LOOKS.glob("*.jpg"))
    recent = s["recent_looks"][-2:]
    f = random.choice([x for x in files if x.name not in recent] or files)
    s["recent_looks"] = (s["recent_looks"] + [f.name])[-6:]
    return f


def _fmt(t):
    t = int(t); h, m, sec = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02}:{sec:02}" if h else f"{m}:{sec:02}"


def render_job(s, jid, log=print):
    import make_video
    job, st = s["jobs"][jid], s["settings"]
    sf = SCRIPTS / f"{jid}.json"
    cfg = json.loads(sf.read_text(encoding="utf-8"))
    look = pick_look(s)
    path = make_video.render_video(cfg, jid, OUT, st["engine"], st["ref"], st["voice"], str(look), None, st["intro"], log)
    make_video.make_thumb(look, cfg.get("thumb_text"), OUT / f"{jid}.jpg")
    chf = OUT / f"{jid}_work/chapters.json"
    if cfg["mode"] == "long" and chf.exists():
        ch = json.loads(chf.read_text(encoding="utf-8"))
        if len(ch) >= 3:
            cfg["chapters_text"] = "\n".join(f"{_fmt(t)} {title}" for t, title in ch)
            sf.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    job.update(rendered=True, error="", look=look.name, out=str(path))
    save(s)


def upload_job(s, jid, log=print):
    import upload
    job = s["jobs"][jid]
    cfg = json.loads((SCRIPTS / f"{jid}.json").read_text(encoding="utf-8"))
    r = upload.upload_video(cfg, job["out"], OUT / f"{jid}.jpg", OUT / f"{jid}.srt")
    job.update(uploaded=r["uploadStatus"] in ("uploaded", "processed"), scheduled=bool(r["publishAt"]),
               video_id=r["id"], link=r["link"], privacy=r["privacy"], error="")
    log(f"[{jid}] {r['link']} privacy={r['privacy']} publishAt={r['publishAt']} extras={r['extras']}")
    save(s)


# ---------------- modes ----------------
def produce(s, hours=48, max_uploads=5, log=print):
    """Daily: agle 48 ghante ke slots ke liye script -> render -> upload + schedule (quota: <=5 uploads/run)."""
    now = datetime.now(IST); mon = now.date() - timedelta(days=now.weekday())
    plan_week(s, mon); plan_week(s, mon + timedelta(days=7))
    due = sorted((j for j in s["jobs"].values()
                  if not (j["scripted"] if j["kind"] == "community" else j["uploaded"])
                  and now + timedelta(minutes=20) <= datetime.fromisoformat(j["publish_at"]) <= now + timedelta(hours=hours)),
                 key=lambda j: j["publish_at"])
    log(f"Due slots: {[j['id'] for j in due]}")
    if not due:
        return
    items = fetch_news()
    if not items:
        raise RuntimeError("News feeds se kuch nahi mila")
    uploads = 0
    for j in due:
        jid = j["id"]
        try:
            if not j["scripted"]:
                generate_script(s, jid, items, log)
            if j["kind"] != "community" and uploads < max_uploads:
                render_job(s, jid, log); upload_job(s, jid, log); uploads += 1
        except Exception as e:
            j["error"] = f"{type(e).__name__}: {e}"[:300]; log(f"[{jid}] FAIL: {j['error']}")
        save(s)
        time.sleep(4)


def dryrun(s, log=print):
    """Ek Short banao, upload NAHI karo (video artifact ke roop mein download karke dekhein)."""
    now = datetime.now(IST); mon = now.date() - timedelta(days=now.weekday())
    plan_week(s, mon); plan_week(s, mon + timedelta(days=7))
    jid = next(j for j in sorted(s["jobs"]) if s["jobs"][j]["kind"] == "short" and datetime.fromisoformat(s["jobs"][j]["publish_at"]) > now)
    items = fetch_news()
    s["jobs"][jid]["scripted"] = False
    generate_script(s, jid, items, log); render_job(s, jid, log)
    s["jobs"][jid].update(rendered=False)  # file ephemeral hai; asli run mein dobara banegi
    save(s); log(f"DRYRUN ready: {OUT / (jid + '.mp4')}")


def weekly(s, log=print):
    import analytics
    analytics.fetch(s, log)
    rows = analytics.table(s)
    groups = analytics.group_stats(rows)
    if rows:
        try:
            ins = llm_json(s, "You are a YouTube growth analyst for the Hindi finance channel S DEEP. Below is performance data of recent videos "
                           "(views, likes, comments, avg view %, subs gained) with kind (short/long), publish hour, turban colour, and group averages. "
                           "Sample sizes are small: be honest, no causal claims, say 'indication' not 'proof'. Write in simple Hinglish (Roman script). "
                           'Return JSON {"summary":"","what_worked":[],"what_didnt":[],"next_week_plan":{"topics_to_emphasize":[],"topics_to_avoid":[],'
                           '"title_style_tip":"","best_slots_note":"","experiments":[]},"action_items":[]}.\nROWS:\n'
                           + json.dumps(rows[-40:], ensure_ascii=False) + "\nGROUPS:\n" + json.dumps(groups, ensure_ascii=False))
            ins["generated_at"] = datetime.now(IST).isoformat()
            (DATA / "insights.json").write_text(json.dumps(ins, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log(f"insights FAIL: {e}")
    analytics.write_report(s, rows, groups)

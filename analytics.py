"""YouTube stats -> data/analytics.json, per-video table, group stats, REPORT.md."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _read(name, default):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return default


def fetch(s, log=print):
    import upload
    from googleapiclient.discovery import build
    ids = [j["video_id"] for j in s["jobs"].values() if j.get("video_id")]
    creds = upload.get_creds()
    yt = build("youtube", "v3", credentials=creds)
    out = {"fetched_at": datetime.now(timezone.utc).isoformat(), "videos": {}, "channel": {}, "notes": []}
    ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
    out["channel"] = {"subs": int(ch.get("subscriberCount", 0)), "views": int(ch.get("viewCount", 0)), "videos": int(ch.get("videoCount", 0))}
    for i in range(0, len(ids), 50):
        for it in yt.videos().list(part="statistics,status", id=",".join(ids[i:i + 50])).execute().get("items", []):
            st = it.get("statistics", {})
            out["videos"][it["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                                       "comments": int(st.get("commentCount", 0)), "privacy": it["status"].get("privacyStatus"),
                                       "publishAt": it["status"].get("publishAt")}
    try:
        ya = build("youtubeAnalytics", "v2", credentials=creds)
        for i in range(0, len(ids), 50):
            r = ya.reports().query(ids="channel==MINE", startDate=(date.today() - timedelta(days=90)).isoformat(),
                                   endDate=date.today().isoformat(), dimensions="video", sort="-views", maxResults=50,
                                   metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
                                   filters="video==" + ",".join(ids[i:i + 50])).execute()
            for row in r.get("rows", []):
                out["videos"].setdefault(row[0], {}).update({"minutes": row[2], "avg_view_sec": row[3],
                                                             "avg_view_pct": round(row[4], 1), "subs_gained": row[5]})
    except Exception as e:
        out["notes"].append(f"Analytics API detail nahi mili (API enable/scope check karein): {str(e)[:150]}")
    (DATA / "analytics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    hist = _read("analytics_history.json", [])
    hist = [h for h in hist if h["date"] != date.today().isoformat()] + [{"date": date.today().isoformat(), **out["channel"]}]
    (DATA / "analytics_history.json").write_text(json.dumps(hist[-120:], indent=1), encoding="utf-8")
    log(f"analytics: {len(out['videos'])} videos, channel={out['channel']}")


def table(s):
    a = _read("analytics.json", {}).get("videos", {})
    rows = []
    for j in s["jobs"].values():
        if not j.get("video_id"):
            continue
        st = a.get(j["video_id"], {})
        parts = j.get("look", "").replace(".jpg", "").split("_")
        rows.append({"id": j["id"], "kind": j["kind"], "title": j.get("title", ""), "hour": j["publish_at"][11:13],
                     "turban": parts[2] if len(parts) > 3 else "", "views": st.get("views", 0), "likes": st.get("likes", 0),
                     "comments": st.get("comments", 0), "avg_view_pct": st.get("avg_view_pct"), "subs_gained": st.get("subs_gained"),
                     "privacy": st.get("privacy"), "link": j.get("link", "")})
    return sorted(rows, key=lambda r: r["id"])


def group_stats(rows):
    res = {}
    for key in ("kind", "hour", "turban"):
        g = {}
        for r in rows:
            g.setdefault(r[key] or "-", []).append(r)
        res[key] = {k: {"videos": len(v), "avg_views": round(sum(x["views"] for x in v) / len(v), 1),
                        "avg_view_pct": (round(sum(x["avg_view_pct"] for x in v if x["avg_view_pct"] is not None) /
                                               max(1, sum(1 for x in v if x["avg_view_pct"] is not None)), 1))} for k, v in g.items()}
    return res


def write_report(s, rows, groups):
    J = list(s["jobs"].values()); vids = [j for j in J if j["kind"] != "community"]
    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    ins = _read("insights.json", {}); ch = _read("analytics.json", {}).get("channel", {})
    L = [f"# S DEEP Report ({now:%d %b %Y %H:%M} IST)\n",
         f"**Channel:** {ch.get('subs', '?')} subs, {ch.get('views', '?')} views, {ch.get('videos', '?')} videos\n",
         "## Production (ab tak)",
         f"- Scripts/posts tayyar: {sum(j['scripted'] for j in J)} / {len(J)} planned",
         f"- Videos upload (verified): {sum(j['uploaded'] for j in vids)} | scheduled (publishAt confirm): {sum(j['scheduled'] for j in vids)}",
         "- Paid service: koi nahi (Gemini free key; billing on ho to charge lag sakta hai)", ""]
    private = [r for r in rows if r["privacy"] == "private" and not any(j["id"] == r["id"] and j["scheduled"] for j in J)]
    if private:
        L.append(f"⚠ {len(private)} video private hain bina schedule ke: API audit lock ho sakta hai, Studio se publish karein.\n")
    errs = [f"- {j['id']}: {j['error']}" for j in J if j["error"]]
    L += ["## Errors / adhoore kaam"] + (errs or ["- koi nahi"]) + [""]
    L += ["## Performance (latest 20)", "| Video | Type | Views | Likes | Cmts | Avg view % | Subs |", "|---|---|---|---|---|---|---|"]
    for r in rows[-20:]:
        L.append(f"| [{r['id']}]({r['link']}) | {r['kind']} | {r['views']} | {r['likes']} | {r['comments']} | {r['avg_view_pct']} | {r['subs_gained']} |")
    L += ["", "## Groups (avg)"]
    for k, v in groups.items():
        L.append(f"- **{k}**: " + "; ".join(f"{a}: {b['avg_views']} views ({b['videos']} vids)" for a, b in v.items()))
    if ins:
        p = ins.get("next_week_plan", {})
        L += ["", "## Insights", ins.get("summary", ""), "", "**Kya chala:** " + "; ".join(ins.get("what_worked", [])),
              "", "**Kya nahi chala:** " + "; ".join(ins.get("what_didnt", [])), "", "## Next week plan",
              f"- Zyada: {p.get('topics_to_emphasize')}", f"- Kam: {p.get('topics_to_avoid')}", f"- Title tip: {p.get('title_style_tip')}",
              f"- Slots: {p.get('best_slots_note')}", f"- Experiments: {p.get('experiments')}",
              "", "**Action items:** " + "; ".join(ins.get("action_items", []))]
    (ROOT / "REPORT.md").write_text("\n".join(L), encoding="utf-8")

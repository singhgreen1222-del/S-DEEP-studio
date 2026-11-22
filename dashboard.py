"""S DEEP mobile dashboard (Streamlit). Reads data committed by GitHub Actions."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

D = Path(__file__).parent / "data"
st.set_page_config(page_title="S DEEP", page_icon="📈", layout="centered")


def rd(name, default):
    try:
        return json.loads((D / name).read_text(encoding="utf-8"))
    except Exception:
        return default


state, ana, ins, hist = rd("state.json", {"jobs": {}}), rd("analytics.json", {}), rd("insights.json", {}), rd("analytics_history.json", [])
jobs = sorted(state["jobs"].values(), key=lambda j: j["publish_at"])
vstats = ana.get("videos", {})
st.title("📈 S DEEP Dashboard")
ch = ana.get("channel", {})
c1, c2, c3 = st.columns(3)
c1.metric("Subscribers", ch.get("subs", "-")); c2.metric("Total views", ch.get("views", "-")); c3.metric("Videos", ch.get("videos", "-"))
t1, t2, t3, t4, t5 = st.tabs(["📅 Schedule", "📈 Performance", "🧠 Next plan", "📝 Scripts", "⚙️ Run"])

with t1:
    rows = [{"slot": j["publish_at"][:16].replace("T", " "), "type": j["kind"], "title": j.get("title", ""),
             "script": "✅" if j["scripted"] else "—", "upload": "✅" if j["uploaded"] else "—",
             "scheduled": "✅" if j["scheduled"] else "—", "look": j.get("look", "").replace(".jpg", "")[8:],
             "error": j["error"], "link": j["link"]} for j in jobs]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={"link": st.column_config.LinkColumn("link")})
    else:
        st.info("Abhi koi plan nahi. 'Run' tab se pehla run chalayein.")
    warn = [f"{j['id']}: {w}" for j in jobs for w in j.get("warnings", [])]
    if warn:
        st.warning("Verify karein:\n\n" + "\n".join("- " + w for w in warn))

with t2:
    rows = []
    for j in jobs:
        if j.get("video_id"):
            v = vstats.get(j["video_id"], {})
            rows.append({"video": j["id"], "type": j["kind"], "views": v.get("views", 0), "likes": v.get("likes", 0),
                         "comments": v.get("comments", 0), "avg view %": v.get("avg_view_pct"), "subs +": v.get("subs_gained"),
                         "status": v.get("privacy")})
    if rows:
        df = pd.DataFrame(rows)
        st.bar_chart(df.set_index("video")["views"])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.write("**Type ke hisab se avg views**"); st.bar_chart(df.groupby("type")["views"].mean())
    else:
        st.info("Abhi koi uploaded video nahi.")
    if len(hist) > 1:
        st.write("**Channel growth**"); st.line_chart(pd.DataFrame(hist).set_index("date")[["subs", "views"]])
    for n in ana.get("notes", []):
        st.caption(n)

with t3:
    if ins:
        p = ins.get("next_week_plan", {})
        st.write(ins.get("summary", ""))
        st.subheader("Kya chala"); [st.write("• " + x) for x in ins.get("what_worked", [])]
        st.subheader("Kya nahi chala"); [st.write("• " + x) for x in ins.get("what_didnt", [])]
        st.subheader("Agle hafte ka plan")
        for k, lab in (("topics_to_emphasize", "Zyada"), ("topics_to_avoid", "Kam"), ("title_style_tip", "Title tip"),
                       ("best_slots_note", "Slots"), ("experiments", "Experiments")):
            st.write(f"**{lab}:** {p.get(k)}")
        st.subheader("Action items"); [st.write("☐ " + x) for x in ins.get("action_items", [])]
        st.caption(f"Generated: {ins.get('generated_at', '')} (har Saturday)")
    else:
        st.info("Pehla weekly analysis Saturday ko banega (ya Run tab se 'weekly' chalayein).")

with t4:
    ids = [j["id"] for j in jobs if j["scripted"]]
    if ids:
        jid = st.selectbox("Select", ids[::-1])
        kind = state["jobs"][jid]["kind"]
        if kind == "community":
            st.code((D / "community" / f"{jid}.txt").read_text(encoding="utf-8"), language=None)
            st.caption("Copy karke YouTube app > Create > Post mein daalein.")
        else:
            cfg = rd(f"scripts/{jid}.json", {})
            st.subheader(cfg.get("title", "")); st.write(cfg.get("description", ""))
            st.caption("Keywords: " + ", ".join(cfg.get("keywords", [])) + " | " + " ".join(cfg.get("hashtags", [])))
            with st.expander("Script text"):
                st.write("\n\n".join(sc["text"] for sc in cfg.get("scenes", [])))
            st.write("Sources:", cfg.get("sources", []))

with t5:
    st.write("GitHub Actions ko abhi chalane ke liye (secrets mein GH_TOKEN aur GH_REPO chahiye):")
    mode = st.radio("Mode", ["dryrun", "daily", "weekly"], help="dryrun = ek test Short, upload nahi | daily = agle 48 ghante ke slots | weekly = analytics + next plan")
    if st.button("▶ Run"):
        import requests
        try:
            r = requests.post(f"https://api.github.com/repos/{st.secrets['GH_REPO']}/actions/workflows/weekly.yml/dispatches",
                              headers={"Authorization": f"Bearer {st.secrets['GH_TOKEN']}", "Accept": "application/vnd.github+json"},
                              json={"ref": "main", "inputs": {"mode": mode}}, timeout=20)
            st.success("Start ho gaya, 5-30 min mein data update hoga") if r.status_code == 204 else st.error(f"{r.status_code}: {r.text[:200]}")
        except Exception as e:
            st.error(e)
    if (D.parent / "REPORT.md").exists():
        with st.expander("Full REPORT.md"):
            st.markdown((D.parent / "REPORT.md").read_text(encoding="utf-8"))

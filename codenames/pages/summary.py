import streamlit as st
from statistics import mean, median, pstdev
import pandas as pd
import os, json

st.title("Summary")

# ---- persistent store path ----
STATS_PATH = os.path.join("results", "tech_stats.json")

# ---- helpers: load/save ----
# def _load_stats_from_disk():
#     try:
#         with open(STATS_PATH, "r", encoding="utf-8") as f:
#             data = json.load(f)
#         # migrate old "Real" bucket to "OpenAI" if present
#         if "OpenAI" not in data and "Real" in data:
#             data["OpenAI"] = data.pop("Real")
#         data.setdefault("Mock", {})
#         data.setdefault("OpenAI", {})
#         return data
#     except FileNotFoundError:
#         return {"Mock": {}, "OpenAI": {}}
#     except Exception:
#         return {"Mock": {}, "OpenAI": {}}

def _load_stats_from_disk():
    try:
        with open(STATS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "OpenAI" not in data and "Real" in data:
            data["OpenAI"] = data.pop("Real")
        data.setdefault("Mock", {})
        data.setdefault("OpenAI", {})
        data.setdefault("Gemini", {})
        return data
    except FileNotFoundError:
        return {"Mock": {}, "OpenAI": {}, "Gemini": {}}
    except Exception:
        return {"Mock": {}, "OpenAI": {}, "Gemini": {}}


def _save_stats_to_disk(stats):
    os.makedirs("results", exist_ok=True)
    tmp = STATS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATS_PATH)

# =========================================================
#  TURNS-BASED SUMMARY (ONLY)
# =========================================================

def summarize_turns(rec: dict):
    turns = rec.get("turns", []) or []
    n = len(turns)

    runs   = rec.get("runs", n)
    wins   = rec.get("wins", 0)
    losses = rec.get("losses", 0)

    games_with_outcome = wins + losses if (wins + losses) > 0 else runs

    mean_turns   = round(mean(turns), 3) if n else 0.0
    median_turns = median(turns) if n else 0
    min_turns    = min(turns) if n else 0
    std_turns    = round(pstdev(turns), 3) if n >= 2 else 0.0

    if games_with_outcome:
        win_rate = wins / games_with_outcome * 100
        loss_rate = losses / games_with_outcome * 100
    else:
        win_rate = 0.0
        loss_rate = 0.0

    return {
        "Runs": runs,
        "Mean turns": mean_turns,
        "Median turns": median_turns,
        "Min turns": min_turns,
        "Std turns": std_turns,
        "Wins": wins,
        "Losses": losses,
        "Win rate": f"{win_rate:.1f}%",
        "Loss rate": f"{loss_rate:.1f}%",
    }

def build_df_turns(tech_dict: dict) -> pd.DataFrame:
    rows = []
    for tech, rec in tech_dict.items():
        row = {"Technique": tech}
        row.update(summarize_turns(rec))
        rows.append(row)
    rows.sort(key=lambda r: r["Technique"].lower())
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(
        columns=[
            "Technique",
            "Runs",
            "Mean turns",
            "Median turns",
            "Min turns",
            "Std turns",
            "Wins",
            "Losses",
            "Win rate",
            "Loss rate",
        ]
    )

def add_totals_turns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    totals = {"Technique": "— Total —"}

    # Sum counts
    for col in ["Runs", "Wins", "Losses"]:
        if col in df.columns:
            totals[col] = df[col].sum()

    wins = totals.get("Wins") or 0
    losses = totals.get("Losses") or 0
    games_with_outcome = wins + losses

    if games_with_outcome:
        totals["Win rate"] = f"{wins / games_with_outcome * 100:.1f}%"
        totals["Loss rate"] = f"{losses / games_with_outcome * 100:.1f}%"
    else:
        totals["Win rate"] = "0.0%"
        totals["Loss rate"] = "0.0%"

    totals_df = pd.DataFrame([totals])
    totals_df = totals_df.reindex(columns=df.columns)

    return pd.concat([df, totals_df], ignore_index=True)

# =========================================================
#  LOAD STATS
# =========================================================

stats = st.session_state.get("tech_stats")
if stats is None:
    stats = _load_stats_from_disk()
    st.session_state.tech_stats = stats

# ---- controls ----
col1, col2 = st.columns(2)
if col1.button("Reload from disk"):
    st.session_state.tech_stats = _load_stats_from_disk()
    stats = st.session_state.tech_stats
    st.success("Reloaded summary from results/tech_stats.json")

# Clear all three buckets: Mock, OpenAI, Gemini
if col2.button("Clear summary (all buckets)"):
    st.session_state.tech_stats = {"Mock": {}, "OpenAI": {}, "Gemini": {}}
    _save_stats_to_disk(st.session_state.tech_stats)
    stats = st.session_state.tech_stats
    st.warning("Cleared summary for Mock, OpenAI and Gemini. File updated.")

# =========================================================
#  TABS: MOCK vs OPENAI vs GEMINI (TURNS ONLY)
# =========================================================

tab1, tab2, tab3 = st.tabs(["Mock mode", "OpenAI (GPT)", "Gemini"])

with tab1:
    bucket = stats.get("Mock", {})

    st.subheader("Turns-based stats (how fast the game ends)")
    df_turns = build_df_turns(bucket)
    df_turns = add_totals_turns(df_turns)
    st.dataframe(df_turns, width="stretch")
    st.download_button(
        "Download CSV (Mock - turns)",
        df_turns.to_csv(index=False).encode("utf-8"),
        file_name="summary_mock_turns.csv",
        mime="text/csv",
    )

with tab2:
    bucket = stats.get("OpenAI", {})

    st.subheader("Turns-based stats (how fast the game ends)")
    df_turns = build_df_turns(bucket)
    df_turns = add_totals_turns(df_turns)
    st.dataframe(df_turns, width="stretch")
    st.download_button(
        "Download CSV (OpenAI - turns)",
        df_turns.to_csv(index=False).encode("utf-8"),
        file_name="summary_openai_turns.csv",
        mime="text/csv",
    )

with tab3:
    bucket = stats.get("Gemini", {})

    st.subheader("Turns-based stats (how fast the game ends)")
    df_turns = build_df_turns(bucket)
    df_turns = add_totals_turns(df_turns)
    st.dataframe(df_turns, width="stretch")
    st.download_button(
        "Download CSV (Gemini - turns)",
        df_turns.to_csv(index=False).encode("utf-8"),
        file_name="summary_gemini_turns.csv",
        mime="text/csv",
    )

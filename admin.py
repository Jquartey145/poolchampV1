import streamlit as st
import pandas as pd
import requests
import datetime
from data_loader import save_tournament_teams, build_regular_season_data, TOURNAMENT_YEAR
from firebase_util import db

st.set_page_config(page_title="Admin - Tournament Setup", page_icon="⚙️")

st.title("⚙️ Tournament Admin")
st.subheader("Fetch Tournament Teams from ESPN")

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard"
    "?groups=100&limit=200&dates={date}"
)

# ── Core fetch function ───────────────────────────────────────────────────────

def _get_tournament_dates(year: int) -> list:
    """
    Return YYYYMMDD date strings covering First Four through Round 2.
    These 6 days guarantee all 68 teams appear at least once.
    Calculated from Selection Sunday (2nd Sunday of March).
    """
    d = datetime.date(year, 3, 1)
    sundays = [day for day in (d + datetime.timedelta(n) for n in range(31)) if day.weekday() == 6]
    selection_sunday = sundays[1]  # second Sunday of March
    return [
        (selection_sunday + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in [2, 3, 4, 5, 6, 7]  # Tue–Sun: First Four, Round 1, Round 2
    ]


def fetch_teams_from_espn() -> tuple:
    """
    Fetch all 68 tournament teams directly from the ESPN scoreboard API.
    This is the same source used by ESPN's own bracket page, giving us
    explicit seed and bracketRegion fields on each competitor.

    Queries First Four + Round 1 + Round 2 dates, deduplicates teams,
    and keeps the best region info (real region beats "First Four").

    Returns (teams_list, total_games_seen) where teams_list is:
      [{"team_name": ..., "seed": ..., "region": ...}, ...]
    """
    dates = _get_tournament_dates(TOURNAMENT_YEAR)
    st.write(f"Querying {len(dates)} ESPN scoreboard dates: {dates}")

    teams = {}   # team_name → {team_name, seed, region}
    total_games = 0

    for date_str in dates:
        url = ESPN_SCOREBOARD.format(date=date_str)
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            st.warning(f"  {date_str}: request failed — {e}")
            continue

        events = data.get("events", [])
        tournament_events = [
            e for e in events
            if e.get("season", {}).get("type") == 3
        ]
        st.write(f"  {date_str}: {len(tournament_events)} tournament games")
        total_games += len(tournament_events)

        for event in tournament_events:
            for competition in event.get("competitions", []):
                # bracketRegion is set at the competition level
                bracket_region = competition.get("bracketRegion", "")

                # Fall back to parsing notes if bracketRegion is empty
                if not bracket_region:
                    for note in competition.get("notes", []):
                        headline = note.get("headline", "")
                        for region in ["East", "West", "South", "Midwest"]:
                            if region in headline:
                                bracket_region = region
                                break
                        if bracket_region:
                            break

                region = bracket_region if bracket_region else "First Four"

                for competitor in competition.get("competitors", []):
                    team = competitor.get("team", {})
                    team_name = team.get("displayName", "")
                    if not team_name:
                        continue

                    # seed is a direct field on competitor in tournament games
                    raw_seed = competitor.get("curatedRank", {}).get("current")                         if not competitor.get("seed") else competitor.get("seed")
                    try:
                        seed = int(raw_seed)
                        if not (1 <= seed <= 16):
                            seed = None
                    except (TypeError, ValueError):
                        seed = None

                    if team_name not in teams:
                        teams[team_name] = {"team_name": team_name, "seed": seed, "region": region}
                    else:
                        # Upgrade region from vague → specific
                        current_region = teams[team_name]["region"]
                        if current_region in ("First Four", "Unknown", "") and region not in ("First Four", "Unknown", ""):
                            teams[team_name]["region"] = region
                        # Upgrade seed if missing
                        if teams[team_name]["seed"] is None and seed is not None:
                            teams[team_name]["seed"] = seed

    result = sorted(teams.values(), key=lambda x: (x["seed"] or 99, x["team_name"]))
    return result, total_games


# ── Read saved teams from Firestore ──────────────────────────────────────────

def get_saved_teams() -> list:
    try:
        docs = (
            db.collection("tournament_teams")
            .document(str(TOURNAMENT_YEAR))
            .collection("teams")
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception:
        return []


# ── Page UI ───────────────────────────────────────────────────────────────────

saved_teams = get_saved_teams()

if saved_teams:
    st.success(f"✅ {len(saved_teams)} tournament teams already saved for {TOURNAMENT_YEAR}.")
    saved_df = pd.DataFrame(saved_teams).sort_values(["seed", "team_name"])
    st.dataframe(
        saved_df[["seed", "team_name", "region"]],
        hide_index=True,
        use_container_width=True
    )
    if st.button("🔄 Re-fetch and overwrite teams", type="secondary"):
        st.session_state.fetch_triggered = True
else:
    st.info(
        f"No tournament teams saved yet for {TOURNAMENT_YEAR}. "
        "Click below after Selection Sunday to auto-fetch all 68 teams."
    )
    if st.button("🏀 Fetch Tournament Teams from ESPN", type="primary"):
        st.session_state.fetch_triggered = True


# ── Fetch ─────────────────────────────────────────────────────────────────────

if st.session_state.get("fetch_triggered"):
    st.session_state.fetch_triggered = False

    with st.spinner("Fetching tournament bracket from ESPN..."):
        result = fetch_teams_from_espn()

    if not result or not result[0]:
        st.error(
            "No teams found. The bracket may not be published yet — "
            "try again after Selection Sunday."
        )
    else:
        teams, total_games = result

        if not teams:
            st.error("No teams could be extracted from ESPN data.")
        else:
            missing_seeds = sum(1 for t in teams if t["seed"] is None)
            if missing_seeds:
                st.warning(
                    f"⚠️ {missing_seeds} team(s) are missing seeds — "
                    "please fill them in manually in the table below before saving."
                )
            st.success(f"Found {len(teams)} teams across {total_games} games! Review and edit below before saving.")
            st.session_state.fetched_teams = teams


# ── Preview, edit, save ───────────────────────────────────────────────────────

if st.session_state.get("fetched_teams"):
    teams = st.session_state.fetched_teams

    st.markdown("### Preview — Edit before saving")
    st.caption(
        "Seeds and regions are auto-detected from ESPN. "
        "Correct any errors before saving to Firestore."
    )

    preview_df = pd.DataFrame(teams)[["seed", "team_name", "region"]]

    edited_df = st.data_editor(
        preview_df,
        column_config={
            "seed": st.column_config.NumberColumn("Seed", min_value=1, max_value=16),
            "team_name": st.column_config.TextColumn("Team Name (ESPN)"),
            "region": st.column_config.SelectboxColumn(
                "Region",
                options=["East", "West", "South", "Midwest", "First Four", "Unknown"]
            ),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
    )

    st.markdown(f"**{len(edited_df)} teams ready to save**")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("💾 Save to Firestore", type="primary"):
            final_teams = edited_df.to_dict(orient="records")
            for t in final_teams:
                if t["seed"] is not None:
                    t["seed"] = int(t["seed"])

            with st.spinner("Saving tournament teams to Firestore..."):
                save_tournament_teams(final_teams)
            st.success(f"✅ {len(final_teams)} teams saved!")

            # Immediately populate regular season stats for all tournament teams
            st.info(
                "📊 Loading regular season player data for all tournament teams. "
                "This takes ~60 seconds — please wait before navigating away."
            )
            with st.spinner("Fetching regular season stats from ESPN parquet..."):
                reg_df = build_regular_season_data(final_teams)

            if not reg_df.empty:
                from firebase_util import save_regular_season_data
                save_regular_season_data(str(TOURNAMENT_YEAR), reg_df.to_dict(orient="records"))
                st.success(
                    f"✅ Regular season data loaded for {reg_df['Team'].nunique()} teams "
                    f"({len(reg_df)} players). Your app is ready for team selection!"
                )
            else:
                st.warning(
                    "⚠️ Regular season data could not be loaded. "
                    "Team names may not match ESPN parquet — check the table above. "
                    "Users can still browse players but stats may be missing."
                )

            st.session_state.fetched_teams = None
            st.rerun()

    with col2:
        if st.button("✖ Cancel", type="secondary"):
            st.session_state.fetched_teams = None
            st.rerun()


# ── Admin tools ───────────────────────────────────────────────────────────────

with st.expander("🛠 Admin Tools"):
    st.warning("These actions are irreversible.")

    if st.button("🗑 Clear saved tournament teams + player cache", type="secondary"):
        # Clear tournament teams
        docs = (
            db.collection("tournament_teams")
            .document(str(TOURNAMENT_YEAR))
            .collection("teams")
            .stream()
        )
        for doc in docs:
            doc.reference.delete()

        # Clear regular season player cache so it re-fetches with new teams
        docs2 = (
            db.collection("regular_season_data")
            .document(str(TOURNAMENT_YEAR))
            .collection("players")
            .stream()
        )
        for doc in docs2:
            doc.reference.delete()

        st.success("Cleared tournament teams and player data cache.")
        st.rerun()
import streamlit as st
import pandas as pd
import requests
import datetime
from data_loader import save_tournament_teams, build_regular_season_data, TOURNAMENT_YEAR
from firebase_util import db, save_regular_season_data

st.set_page_config(page_title="Admin - Tournament Setup", page_icon="⚙️")

st.title("⚙️ Tournament Admin")
st.subheader("Fetch Tournament Teams from ESPN")

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard"
    "?groups=100&limit=200&dates={date}"
)

# ── Tournament dates ──────────────────────────────────────────────────────────

def _get_tournament_dates(year: int) -> list:
    """
    Return YYYYMMDD date strings covering First Four through Round 2.
    Hardcoded for 2026; dynamic fallback for other years.
    """
    if year == 2026:
        return ["20260317", "20260318", "20260319", "20260320", "20260321", "20260322"]
    d = datetime.date(year, 3, 1)
    sundays = [
        day for day in (d + datetime.timedelta(n) for n in range(31))
        if day.weekday() == 6
    ]
    selection_sunday = sundays[1]
    return [
        (selection_sunday + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in [2, 3, 4, 5, 6, 7]
    ]


# ── Core fetch function ───────────────────────────────────────────────────────

def fetch_teams_from_espn() -> tuple:
    """
    Fetch all 68 tournament teams from the ESPN scoreboard API.
    Queries First Four + Round 1 + Round 2 dates, deduplicates teams,
    and keeps the best region info (real region beats "First Four").

    Returns (teams_list, total_games_seen).
    """
    dates = _get_tournament_dates(TOURNAMENT_YEAR)
    st.write(f"Querying {len(dates)} ESPN scoreboard dates: {dates}")

    teams       = {}   # team_name → {team_name, seed, region}
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

        # Try season type 3 first, fall back to notes headline detection
        tournament_events = [
            e for e in events
            if e.get("season", {}).get("type") in (3, "3")
        ]
        if not tournament_events:
            tournament_events = [
                e for e in events
                if any(
                    any(kw in n.get("headline", "") for kw in [
                        "NCAA", "Tournament", "First Round", "Second Round",
                        "Sweet", "Elite", "Final Four", "Championship", "First Four"
                    ])
                    for comp in e.get("competitions", [])
                    for n in comp.get("notes", [])
                )
            ]

        st.write(f"  {date_str}: {len(tournament_events)} tournament games found")
        total_games += len(tournament_events)

        for event in tournament_events:
            for competition in event.get("competitions", []):

                # Get region from bracketRegion first
                region = competition.get("bracketRegion", "")

                # Fall back to parsing notes headline
                if not region:
                    for note in competition.get("notes", []):
                        headline = note.get("headline", "")
                        for r in ["East", "West", "South", "Midwest"]:
                            if r in headline:
                                region = r
                                break
                        if region:
                            break

                region = region if region else "First Four"

                for competitor in competition.get("competitors", []):
                    team      = competitor.get("team", {})
                    team_name = team.get("displayName", "")
                    if not team_name:
                        continue

                    # Try direct seed field first, then curatedRank as fallback
                    raw_seed = competitor.get("seed")
                    if raw_seed is None:
                        raw_seed = competitor.get("curatedRank", {}).get("current")
                    try:
                        seed = int(raw_seed)
                        if not (1 <= seed <= 16):
                            seed = None
                    except (TypeError, ValueError):
                        seed = None

                    if team_name not in teams:
                        teams[team_name] = {
                            "team_name": team_name,
                            "seed":      seed,
                            "region":    region,
                        }
                    else:
                        # Upgrade vague region → real region
                        current_region = teams[team_name]["region"]
                        if current_region in ("First Four", "Unknown", "") \
                                and region not in ("First Four", "Unknown", ""):
                            teams[team_name]["region"] = region
                        # Fill in missing seed
                        if teams[team_name]["seed"] is None and seed is not None:
                            teams[team_name]["seed"] = seed

    result = sorted(
        teams.values(),
        key=lambda x: (x["seed"] or 99, x["team_name"])
    )
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
        "The bracket was announced — click below to fetch all 68 teams."
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
            "No teams found. The bracket data may not be on ESPN's scoreboard yet — "
            "try again in a few hours, or check that the dates in _get_tournament_dates() are correct."
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
            st.success(
                f"Found {len(teams)} teams across {total_games} games! "
                "Review and edit below before saving."
            )
            st.session_state.fetched_teams = teams


# ── Preview, edit, save ───────────────────────────────────────────────────────

if st.session_state.get("fetched_teams"):
    teams = st.session_state.fetched_teams

    st.markdown("### Preview — Edit before saving")
    st.caption(
        "Seeds and regions are auto-detected from ESPN. "
        "Correct any errors before saving to Firestore."
    )

    preview_df  = pd.DataFrame(teams)[["seed", "team_name", "region"]]
    edited_df   = st.data_editor(
        preview_df,
        column_config={
            "seed":      st.column_config.NumberColumn("Seed", min_value=1, max_value=16),
            "team_name": st.column_config.TextColumn("Team Name (ESPN)"),
            "region":    st.column_config.SelectboxColumn(
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

            st.info(
                "📊 Loading regular season player data for all tournament teams. "
                "This may take a few minutes — please wait before navigating away."
            )
            with st.spinner("Fetching regular season stats from ESPN..."):
                reg_df = build_regular_season_data(final_teams)

            if not reg_df.empty:
                save_regular_season_data(str(TOURNAMENT_YEAR), reg_df.to_dict(orient="records"))
                st.success(
                    f"✅ Regular season data loaded for {reg_df['Team'].nunique()} teams "
                    f"({len(reg_df)} players). Your app is ready for team selection!"
                )
            else:
                st.warning(
                    "⚠️ Regular season data could not be loaded. "
                    "Team names may not match ESPN — check the table above."
                )

            st.session_state.fetched_teams = None
            st.rerun()

    with col2:
        if st.button("✖ Cancel", type="secondary"):
            st.session_state.fetched_teams = None
            st.rerun()


# ── Add a single team manually ───────────────────────────────────────────────

with st.expander("➕ Add a Single Team Manually"):
    st.caption(
        "Use this to add a missing or First Four team. "
        "If the team name search fails, find the ESPN ID from the team's ESPN URL "
        "(e.g. espn.com/mens-college-basketball/team/_/id/**2511**/queens-nc-royals) "
        "and paste it directly."
    )

    existing_names = {t["team_name"] for t in get_saved_teams()}

    # ── Step 1: name search OR ID lookup ─────────────────────────────────────
    st.markdown("**Step 1 — Find the team on ESPN**")
    search_col, id_col, btn_col = st.columns([2, 1, 1])
    with search_col:
        search_query = st.text_input(
            "Search by name",
            placeholder="e.g. Queens",
            key="team_search_query"
        )
    with id_col:
        direct_id = st.text_input(
            "Or enter ESPN ID directly",
            placeholder="e.g. 2511",
            key="team_direct_id"
        )
    with btn_col:
        st.markdown("<br>", unsafe_allow_html=True)
        do_search = st.button("🔍 Look Up", key="team_search_btn")

    if do_search:
        # ── Direct ID path ────────────────────────────────────────────────────
        if direct_id.strip():
            espn_id = direct_id.strip()
            url = (
                f"https://site.api.espn.com/apis/site/v2/sports/basketball"
                f"/mens-college-basketball/teams/{espn_id}"
            )
            try:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                team_data = resp.json().get("team", {})
                display_name = team_data.get("displayName", "")
                abbreviation = team_data.get("abbreviation", "")
                if display_name:
                    st.success(f"Found: **{display_name}** ({abbreviation}) — ESPN ID: `{espn_id}`")
                    st.info(f"Copy this exact name into the form below: `{display_name}`")
                    # Store in session so the form can pre-fill
                    st.session_state.resolved_team_name = display_name
                    st.session_state.resolved_espn_id   = espn_id
                else:
                    st.error(f"No team found for ESPN ID {espn_id}.")
            except Exception as e:
                st.error(f"ESPN ID lookup failed: {e}")

        # ── Name search path ──────────────────────────────────────────────────
        elif search_query.strip():
            url = (
                "https://site.api.espn.com/apis/site/v2/sports/basketball"
                "/mens-college-basketball/teams?limit=1000"
            )
            try:
                resp       = requests.get(url, timeout=10)
                data       = resp.json()
                teams_list = (
                    data.get("sports", [{}])[0]
                        .get("leagues", [{}])[0]
                        .get("teams", [])
                )
                q = search_query.strip().lower()
                matches = [
                    {
                        "displayName":  t["team"].get("displayName", ""),
                        "abbreviation": t["team"].get("abbreviation", ""),
                        "espn_id":      t["team"].get("id", ""),
                    }
                    for t in teams_list
                    if q in t["team"].get("displayName", "").lower()
                    or q in t["team"].get("shortDisplayName", "").lower()
                    or q in t["team"].get("nickname", "").lower()
                ]
                if matches:
                    st.success(f"Found {len(matches)} match(es) — copy the exact Display Name into the form below.")
                    st.dataframe(pd.DataFrame(matches), hide_index=True, use_container_width=True)
                else:
                    st.warning(
                        f"No ESPN teams found matching '{search_query}'. "
                        "Try a shorter term, or find the team's ESPN page and paste the ID above."
                    )
            except Exception as e:
                st.error(f"ESPN team search failed: {e}")
        else:
            st.warning("Enter a name to search or an ESPN ID to look up.")

    # ── Step 2: form ──────────────────────────────────────────────────────────
    st.markdown("**Step 2 — Enter the team details**")

    # Pre-fill name if we resolved it via direct ID lookup
    prefill_name = st.session_state.get("resolved_team_name", "")

    with st.form("add_single_team"):
        col_a, col_b, col_c, col_d = st.columns([3, 1, 1, 1])
        with col_a:
            new_team_name = st.text_input(
                "Team Name (exact ESPN display name)",
                value=prefill_name,
                placeholder="e.g. Queens NC Royals",
            )
        with col_b:
            new_espn_id = st.text_input(
                "ESPN ID (optional)",
                value=st.session_state.get("resolved_espn_id", ""),
                placeholder="e.g. 2511",
            )
        with col_c:
            new_seed = st.number_input("Seed", min_value=1, max_value=16, step=1)
        with col_d:
            new_region = st.selectbox(
                "Region",
                options=["East", "West", "South", "Midwest", "First Four"]
            )

        add_submitted = st.form_submit_button("➕ Add Team", type="primary")

        if add_submitted:
            if not new_team_name.strip():
                st.error("Please enter a team name.")
            elif new_team_name.strip() in existing_names:
                st.warning(f"**{new_team_name.strip()}** is already saved — use the table above to edit it.")
            else:
                new_team = {
                    "team_name": new_team_name.strip(),
                    "seed":      int(new_seed),
                    "region":    new_region,
                }
                # Store ESPN ID override if provided so build_regular_season_data can use it
                if new_espn_id.strip():
                    new_team["espn_id"] = new_espn_id.strip()

                with st.spinner(f"Saving {new_team_name.strip()}..."):
                    save_tournament_teams([new_team])
                st.success(f"✅ **{new_team_name.strip()}** (Seed {new_seed}, {new_region}) saved!")

                st.info("📊 Loading regular season stats for the new team...")
                with st.spinner("Fetching stats from ESPN..."):
                    reg_df = build_regular_season_data([new_team])

                if not reg_df.empty:
                    from firebase_util import get_regular_season_data
                    existing_players   = get_regular_season_data(str(TOURNAMENT_YEAR)) or []
                    existing_names_set = {p["Player"] + "|" + p["Team"] for p in existing_players}
                    new_players = [
                        p for p in reg_df.to_dict(orient="records")
                        if p["Player"] + "|" + p["Team"] not in existing_names_set
                    ]
                    if new_players:
                        save_regular_season_data(str(TOURNAMENT_YEAR), new_players)
                        st.success(f"✅ Added {len(new_players)} player records for {new_team_name.strip()}.")
                    else:
                        st.info("No new player records to add (may already be cached).")
                else:
                    st.warning(
                        "⚠️ Could not load regular season stats. "
                        "If the name lookup is failing, make sure the ESPN ID is filled in above."
                    )

                # Clear prefill state
                st.session_state.pop("resolved_team_name", None)
                st.session_state.pop("resolved_espn_id", None)
                st.rerun()


# ── Debug expander — shows raw ESPN response for first date ───────────────────

with st.expander("🔍 Debug — Raw ESPN response"):
    st.caption("Use this to inspect what ESPN is returning if teams aren't showing up.")
    debug_date = st.text_input("Date to inspect (YYYYMMDD)", value="20260317")
    if st.button("Fetch raw ESPN data"):
        url = ESPN_SCOREBOARD.format(date=debug_date)
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            events = data.get("events", [])
            st.write(f"**{len(events)} total events returned**")

            type_counts = {}
            for e in events:
                t = e.get("season", {}).get("type")
                type_counts[t] = type_counts.get(t, 0) + 1
            st.write(f"season.type breakdown: {type_counts}")

            if events:
                st.write("**First event raw:**")
                e    = events[0]
                comp = e.get("competitions", [{}])[0]
                c0   = comp.get("competitors", [{}])[0]
                st.json({
                    "event_name":       e.get("name"),
                    "season_type":      e.get("season", {}).get("type"),
                    "bracketRegion":    comp.get("bracketRegion"),
                    "tournamentId":     comp.get("tournamentId"),
                    "notes":            comp.get("notes"),
                    "competitor_seed":  c0.get("seed"),
                    "curatedRank":      c0.get("curatedRank"),
                    "team_displayName": c0.get("team", {}).get("displayName"),
                })
        except Exception as e:
            st.error(f"Request failed: {e}")


# ── Admin tools ───────────────────────────────────────────────────────────────

with st.expander("🛠 Admin Tools"):
    st.warning("These actions are irreversible.")

    if st.button("🗑 Clear saved tournament teams + player cache", type="secondary"):
        docs = (
            db.collection("tournament_teams")
            .document(str(TOURNAMENT_YEAR))
            .collection("teams")
            .stream()
        )
        for doc in docs:
            doc.reference.delete()

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
import datetime
from data_loader import fetch_with_retry, safe_get, load_net_rankings, TOURNAMENT_YEAR, BASE_URL, API_KEY
from firebase_util import get_top16_player_data, save_top16_player_data

def update_player_active_status():
    """
    Check the tournament schedule and update each player's "active" status in Firestore.
    A player's "active" status is set to True if their team has a future game scheduled,
    and False otherwise.
    """
    year_str = str(TOURNAMENT_YEAR)
    url = f"{BASE_URL}/tournaments/{TOURNAMENT_YEAR}/PST/schedule.json"
    schedule_data = fetch_with_retry(url, {"api_key": API_KEY})
    if not schedule_data:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    team_active = {}
    for round_data in safe_get(schedule_data, ['rounds'], []):
        for game in safe_get(round_data, ['games'], []):
            scheduled_str = game.get("scheduled")
            if scheduled_str:
                try:
                    scheduled_time = datetime.datetime.fromisoformat(scheduled_str)
                except Exception:
                    continue
                if scheduled_time > now:
                    for side in ['home', 'away']:
                        team_id = safe_get(game, [side, 'id'])
                        if team_id:
                            team_active[team_id] = True
    net_rankings = load_net_rankings()
    if net_rankings:
        for team in net_rankings.get("top16", []):
            team_id = team.get("team_id")
            if team_id and team_id not in team_active:
                team_active[team_id] = False

    players = get_top16_player_data(year_str)
    if not players:
        return
    updated_players = []
    for player in players:
        team_id = player.get("Team_ID")
        active = team_active.get(team_id, False)
        player["active"] = active
        updated_players.append(player)
    save_top16_player_data(year_str, updated_players)

if __name__ == "__main__":
    update_player_active_status()

import requests

# An api key is emailed to you when you sign up to a plan
# Get a free API key at https://api.the-odds-api.com/
ODDS_API_KEY = '2ba7ca910ee0dc43ade8c5a7c0c9cce8'

SPORT = 'basketball_ncaab' # use the sport_key from the /sports endpoint below, or use 'upcoming' to see the next 8 games across all sports

REGIONS = 'us' # uk | us | eu | au. Multiple can be specified if comma delimited

MARKETS = 'h2h,spreads' # h2h | spreads | totals. Multiple can be specified if comma delimited

ODDS_FORMAT = 'decimal' # decimal | american

DATE_FORMAT = 'iso' # iso | unix

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
#
# First get a list of in-season sports
#   The sport 'key' from the response can be used to get odds in the next request
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# scores_response = requests.get(
#     f'https://api.the-odds-api.com/v4/sports/{SPORT}/scores?apiKey={ODDS_API_KEY}&daysFrom=1&dateFormat={DATE_FORMAT}', 
#     params={
#         'api_key': ODDS_API_KEY
#     }
# )


# if scores_response.status_code != 200:
#     print(f'Failed to get sports: status_code {scores_response.status_code}, response body {scores_response.text}')

# else:
#     print(f'List of scores in the past {1} days:', scores_response.json())


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
#
# Now get a list of live & upcoming games for the sport you want, along with odds for different bookmakers
# This will deduct from the usage quota
# The usage quota cost = [number of markets specified] x [number of regions specified]
# For examples of usage quota costs, see https://the-odds-api.com/liveapi/guides/v4/#usage-quota-costs
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 

# odds_response = requests.get(
#     f'https://api.the-odds-api.com/v4/sports/{SPORT}/odds',
#     params={
#         'api_key': API_KEY,
#         'regions': REGIONS,
#         'markets': MARKETS,
#         'oddsFormat': ODDS_FORMAT,
#         'dateFormat': DATE_FORMAT,
#     }
# )

# if odds_response.status_code != 200:
#     print(f'Failed to get odds: status_code {odds_response.status_code}, response body {odds_response.text}')

# else:
#     odds_json = odds_response.json()
#     print('Number of events:', len(odds_json))
#     print(odds_json)

#     # Check the usage quota
#     print('Remaining requests', odds_response.headers['x-requests-remaining'])
#     print('Used requests', odds_response.headers['x-requests-used'])


SDIO_API_KEY = 'dc1b86adc30b445bad4e9106bd403754'

SEASON = 2023

stats_response = requests.get(
    f'https://api.sportsdata.io/v3/cbb/stats/json/PlayerSeasonStats/{SEASON}?key={SDIO_API_KEY}', 
    params={
        'api_key': SDIO_API_KEY
    }
)

if stats_response.status_code != 200:
    print(f'Failed to get sports: status_code {stats_response.status_code}, response body {stats_response.text}')

else:
    print(f'List of player stats in {SEASON}:', stats_response.json())

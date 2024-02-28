import requests
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd

url_stats = "https://basketball.realgm.com/ncaa/conferences/Atlantic-Coast-Conference/1/stats/2024/Averages/Qualified/All/Season/All/points/desc/{}"

def check_valid_html(html_content):

    soup = BeautifulSoup(html_content, 'html.parser')
    return True if soup.find('table') else False

page_count = 0

for page in range(1, 51):
    
    url = url_stats.format(page)

    # Send an HTTP GET request to the URL to fetch the webpage content
    data = requests.get(url)
    html_content = data.text

    if not check_valid_html(html_content):
        break

    #Write the retrieved HTML data to a file named after the year
    with open("side_channel_app/test_data/stats_page_{}.html".format(page), "w+") as f:
        f.write(html_content)
    
    # Update page count
    page_count += 1

stats = pd.DataFrame()

for page in range(1, page_count + 1):
    # Read the HTML content from the file for the specific year
    with open("side_channel_app/test_data/stats_page_{}.html".format(page)) as f:
        p = f.read()

    #Initialize the parser
    soup = BeautifulSoup(p, "html.parser")

    #Find specific metadata of the table and convert the HTML table to DataFrame
    table = soup.find('table')
    page_stats = pd.read_html(StringIO(str(table)))[0]

    stats = pd.concat([stats, page_stats], ignore_index=True)

print(stats)
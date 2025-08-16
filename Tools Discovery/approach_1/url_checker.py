import pandas as pd
import requests
import csv

def check_url(url):
    if not isinstance(url, str) or not url.startswith('http'):
        return 'Invalid URL'
    try:
        response = requests.head(url, allow_redirects=True, timeout=5)
        if response.status_code == 200:
            return 'OK'
        else:
            return f'Broken (Status code: {response.status_code})'
    except requests.RequestException as e:
        return f'Broken ({e.__class__.__name__})'

def validate_links(input_file, output_file):
    df = pd.read_csv(input_file)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        header = df.columns.tolist() + ['Website Status', 'YouTube Status']
        writer.writerow(header)

        for index, row in df.iterrows():
            website_url = row['Website']
            #youtube_url = row['YouTube URL']

            website_status = check_url(website_url)
            #youtube_status = check_url(youtube_url)

            new_row = row.tolist() + [website_status, 
                                      #youtube_status
                                      ]
            writer.writerow(new_row)

if __name__ == '__main__':
    validate_links('new_tools_final.csv', 'new_tools_with_validation.csv')
    print("Link validation complete. Results saved to new_tools_with_validation.csv") 
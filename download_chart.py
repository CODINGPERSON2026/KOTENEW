import os
import urllib.request

url = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
dest_path = "static/js/chart.umd.min.js"

os.makedirs(os.path.dirname(dest_path), exist_ok=True)
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response, open(dest_path, 'wb') as out_file:
        out_file.write(response.read())
    print("Successfully downloaded Chart.js")
except Exception as e:
    print("Download error:", e)

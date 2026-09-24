import os
import urllib.request

files_to_download = [
    # Font Awesome CSS
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css", "static/css/all.min.css"),
    # Font Awesome Webfonts
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2", "static/webfonts/fa-solid-900.woff2"),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.ttf", "static/webfonts/fa-solid-900.ttf"),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-brands-400.woff2", "static/webfonts/fa-brands-400.woff2"),
    ("https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.woff2", "static/webfonts/fa-regular-400.woff2"),
    # Google Inter Font (all weights for offline use)
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuOKfMZg.ttf", "static/fonts/inter/Inter-Light.ttf"),
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfMZg.ttf", "static/fonts/inter/Inter-Regular.ttf"),
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuI6fMZg.ttf", "static/fonts/inter/Inter-Medium.ttf"),
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuGKYMZg.ttf", "static/fonts/inter/Inter-SemiBold.ttf"),
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZg.ttf", "static/fonts/inter/Inter-Bold.ttf"),
    ("https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuDyYMZg.ttf", "static/fonts/inter/Inter-ExtraBold.ttf"),
    # Chart.js (for offline graphs)
    ("https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js", "static/js/chart.umd.min.js"),
]

def download_file(url, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(dest_path, 'wb') as out_file:
        out_file.write(response.read())

def ensure_cdn_downloaded():
    """Ensure static assets are downloaded for offline use."""
    for url, path in files_to_download:
        if not os.path.exists(path):
            try:
                print(f"Downloading CDN asset for offline use: {path}...")
                download_file(url, path)
                print(f"Successfully saved {path}")
            except Exception as e:
                print(f"Note: Could not download {url} ({e}). If already offline, ensure files are in {path}.")

if __name__ == '__main__':
    ensure_cdn_downloaded()

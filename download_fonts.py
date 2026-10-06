"""Download Inter font files from Google Fonts for offline use."""
import os
import urllib.request

FONT_DIR = os.path.join(os.path.dirname(__file__), 'static', 'fonts', 'inter')
os.makedirs(FONT_DIR, exist_ok=True)

FONTS = {
    'Inter-Light.ttf':     'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuOKfMZg.ttf',
    'Inter-Regular.ttf':   'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfMZg.ttf',
    'Inter-Medium.ttf':    'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuI6fMZg.ttf',
    'Inter-SemiBold.ttf':  'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuGKYMZg.ttf',
    'Inter-Bold.ttf':      'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuFuYMZg.ttf',
    'Inter-ExtraBold.ttf': 'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuDyYMZg.ttf',
    'Inter-Black.ttf':     'https://fonts.gstatic.com/s/inter/v20/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuBWYMZg.ttf',
}

for filename, url in FONTS.items():
    dest = os.path.join(FONT_DIR, filename)
    if os.path.exists(dest):
        print(f"  Already exists: {filename}")
        continue
    print(f"  Downloading {filename}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  ✓ Saved {filename}")

print(f"\nAll fonts saved to: {FONT_DIR}")

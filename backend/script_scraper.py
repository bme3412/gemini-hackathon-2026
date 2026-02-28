import os
import requests
from bs4 import BeautifulSoup
import time

SCRIPTS_DIR = "scripts_library"
os.makedirs(SCRIPTS_DIR, exist_ok=True)

# Sample of iconic scripts identified from research
TARGET_SCRIPTS = {
    "Pulp Fiction": "https://imsdb.com/scripts/Pulp-Fiction.html",
    "The Matrix": "https://imsdb.com/scripts/Matrix,-The.html",
    "The Shawshank Redemption": "https://imsdb.com/scripts/Shawshank-Redemption,-The.html",
    "The Godfather": "https://imsdb.com/scripts/Godfather.html",
    "Fight Club": "https://imsdb.com/scripts/Fight-Club.html",
    "Inception": "https://imsdb.com/scripts/Inception.html",
    "Forrest Gump": "https://imsdb.com/scripts/Forrest-Gump.html",
    "Jurassic Park": "https://imsdb.com/scripts/Jurassic-Park.html",
    "Good Will Hunting": "https://imsdb.com/scripts/Good-Will-Hunting.html",
    "The Truman Show": "https://imsdb.com/scripts/Truman-Show,-The.html"
}

def scrape_script(name, url):
    print(f"Scraping {name}...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # IMSDb scripts are usually inside a <pre> tag
        script_pre = soup.find('pre')
        if not script_pre:
            # Fallback for some atypical formats
            script_text = soup.get_text()
        else:
            script_text = script_pre.get_text()
            
        file_path = os.path.join(SCRIPTS_DIR, f"{name.replace(' ', '_')}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(script_text)
        print(f"Successfully saved to {file_path}")
        return True
    except Exception as e:
        print(f"Failed to scrape {name}: {e}")
        return False

if __name__ == "__main__":
    for name, url in TARGET_SCRIPTS.items():
        scrape_script(name, url)
        # Polite scraping
        time.sleep(1)

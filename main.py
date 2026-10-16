import bs4
import requests
import os
from dotenv import load_dotenv
from Movie import Movie
import threading
from downloader import download_m3u8, get_movie_download_link
from time import sleep
import concurrent.futures
from urllib.parse import urlsplit, urlunsplit

BASEURL = "https://einthusan.tv"
load_dotenv()
FOLDER = os.getenv("FOLDER", "movies")
PAGECOUNT = int(os.getenv("PAGECOUNT", "3"))
JELLYFIN_ADDR = os.getenv("JELLYFINADDR", "").strip()
JELLYFIN_API_KEY = os.getenv("JELLYFINAPIKEY", "").strip()
TESTING_MODE = os.getenv("TESTING", "False") == "True"

if TESTING_MODE:
    print("[TESTING MODE ON]")

downloadedMovies = []

# Check if the downloaded text file is there and if not create it
if not os.path.exists("downloaded"):
    with open("downloaded", "w") as f:
        f.write("")
with open("downloaded", "r") as f:
    downloadedMovies = f.read().split("\n")
    downloadedMovies = set(list(filter(lambda x: x.strip() != "", downloadedMovies)))

print("Already Downloaded Movies: ", downloadedMovies)

# Remove the movies that should not be in the folder
if os.path.exists(FOLDER):
    for movie_file in os.listdir(FOLDER):
        movie_title, ext = os.path.splitext(movie_file)
        if ext == ".mp4" and movie_title not in downloadedMovies:
            os.remove(os.path.join(FOLDER, movie_file))

moviePages = []
for page in range(1, PAGECOUNT + 1):
    newMoviesPage = requests.get(
        f"https://einthusan.tv/movie/results/?find=Recent&lang=tamil&page={page}"
    )
    moviePages.append(newMoviesPage)
    sleep(3)

movieLinks = []

for page in range(PAGECOUNT):
    soup = bs4.BeautifulSoup(moviePages[page].text, "html.parser")

    section = soup.find("section", id="UIMovieSummary")

    movie_list = section.find("ul")
    if movie_list:
        movies = movie_list.find_all("li", recursive=False)

    for movie in movies:
        title = movie.find("a", class_="title")

        link = title.get("href")
        if link:
            movieLinks.append(Movie(title.find("h3").text, BASEURL + link, link.split("/")[-2]))

        print(title.find("h3").text)

for movie in movieLinks:
    print(f"Title: {movie.title}, Link: {movie.link}, ID: {movie.id}")


if not os.path.exists(FOLDER):
    os.makedirs(FOLDER)


def download_movie(movie):
    # Check if the movie is already downloaded
    if os.path.exists(os.path.join(FOLDER, f"{movie.id}.mp4")):
        print(f"{movie.title} is already downloaded.")
        return movie.id, False

    # Get the m3u8 link from the movie page
    m3u8_link = get_movie_download_link(movie.link)
    if not m3u8_link:
        print(f"Failed to get download link for {movie.title}")
        return None

    print(f"Downloading: {movie.title} from {m3u8_link}")

    output_filename = os.path.join(FOLDER, f"{movie.id}.mp4")
    downloaded = download_m3u8(
        m3u8_link,
        output_filename,
        testing=TESTING_MODE,
    )
    if not downloaded:
        return None

    return movie.id, True


def refresh_jellyfin():
    if not JELLYFIN_ADDR or not JELLYFIN_API_KEY:
        print("Jellyfin refresh skipped; configure JELLYFINADDR and JELLYFINAPIKEY.")
        return

    address = JELLYFIN_ADDR
    if not address.startswith(("http://", "https://")):
        address = f"http://{address}"
    parsed_address = urlsplit(address)
    if parsed_address.port is None:
        parsed_address = parsed_address._replace(
            netloc=f"{parsed_address.netloc}:8096"
        )
    base_url = urlunsplit(parsed_address).rstrip("/")

    try:
        response = requests.post(
            f"{base_url}/Library/Refresh",
            headers={"Authorization": f'MediaBrowser Token="{JELLYFIN_API_KEY}"'},
            timeout=10,
        )
        response.raise_for_status()
        print("Jellyfin library refresh requested.")
    except requests.RequestException as error:
        print(f"Could not request Jellyfin library refresh: {error}")



# Download movies to the folder
with concurrent.futures.ThreadPoolExecutor(max_workers=int(os.getenv("CONCURRENT_DOWNLOADS", "2"))) as executor:
    futures = {
        executor.submit(download_movie, movie): movie
        for movie in movieLinks
    }
    for future in concurrent.futures.as_completed(futures):
        movie = futures[future]
        try:
            result = future.result()
        except Exception as error:
            print(f"Download failed for {movie.title}: {error}")
            continue

        if result is None:
            continue

        movie_id, is_new_download = result
        downloadedMovies.add(movie_id)
        with open("downloaded", "w") as f:
            f.write("\n".join(downloadedMovies))

        if is_new_download:
            refresh_jellyfin()

print("All Downloads Complete")

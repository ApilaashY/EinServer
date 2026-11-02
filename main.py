import bs4
import requests
import os
from dotenv import load_dotenv
from Movie import Movie
import threading
from downloader import download_m3u8, get_movie_download_link
from time import sleep
import concurrent.futures
import json
import re
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit, quote

BASEURL = "https://einthusan.tv"
load_dotenv()
FOLDER = os.getenv("FOLDER", "movies")
PAGECOUNT = int(os.getenv("PAGECOUNT", "3"))
JELLYFIN_ADDR = os.getenv("JELLYFINADDR", "").strip()
JELLYFIN_API_KEY = os.getenv("JELLYFINAPIKEY", "").strip()
DOWNLOADED_FILE = os.getenv("DOWNLOADED_FILE", "downloaded")
API_PORT = int(os.getenv("API_PORT", "0"))
API_LANG = os.getenv("API_LANG", "tamil")
JELLYFIN_PUBLIC_URL = os.getenv("JELLYFIN_PUBLIC_URL", "").strip().rstrip("/")
TESTING_MODE = os.getenv("TESTING", "False") == "True"

if TESTING_MODE:
    print("[TESTING MODE ON]")

downloadedMovies = []

# Check if the downloaded text file is there and if not create it
if not os.path.exists(DOWNLOADED_FILE):
    with open(DOWNLOADED_FILE, "w") as f:
        f.write("")
with open(DOWNLOADED_FILE, "r") as f:
    downloadedMovies = f.read().split("\n")
    downloadedMovies = set(list(filter(lambda x: x.strip() != "", downloadedMovies)))

print("Already Downloaded Movies: ", downloadedMovies)

# Remove the movies that should not be in the folder
if os.path.exists(FOLDER):
    for movie_file in os.listdir(FOLDER):
        movie_title, ext = os.path.splitext(movie_file)
        if ext in (".mp4", ".mkv") and movie_title.split("-")[0].strip() not in downloadedMovies:
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


# Urgent (API) downloads run immediately; every other download is paused (SIGSTOP)
# until they finish. pause_cond guards all of the state below.
pause_cond = threading.Condition()
urgent_ids = set()
claimed = set()  # movie ids currently being handled by some download_movie call
running = {}  # movie id -> ffmpeg process


def apply_pause():
    # Caller holds pause_cond
    for movie_id, proc in running.items():
        if proc.poll() is not None:
            continue
        pause = bool(urgent_ids) and movie_id not in urgent_ids
        try:
            proc.send_signal(signal.SIGSTOP if pause else signal.SIGCONT)
        except ProcessLookupError:
            pass


def register_process(movie_id, proc):
    with pause_cond:
        running[movie_id] = proc
        apply_pause()


def download_movie(movie, on_ready=None, urgent=False):
    """Returns (id, is_new), None on failure/skip, or (id, None) if an urgent
    request was merged into a download that was already in the queue."""
    with pause_cond:
        if movie.id in claimed:
            if not urgent:
                return None
            # Same movie is already queued/running: just stop pausing it
            urgent_ids.add(movie.id)
            apply_pause()
            pause_cond.notify_all()
            return movie.id, None
        claimed.add(movie.id)
        if urgent:
            urgent_ids.add(movie.id)
            apply_pause()

    try:
        with pause_cond:
            while urgent_ids and movie.id not in urgent_ids:
                pause_cond.wait()

        # Check if the movie is already downloaded
        base = os.path.join(FOLDER, f"{movie.id} - {movie.title}")
        if os.path.exists(base + ".mkv") or os.path.exists(base + ".mp4"):
            print(f"{movie.title} is already downloaded.")
            return movie.id, False

        # Get the m3u8 link from the movie page
        m3u8_link = get_movie_download_link(movie.link)
        if not m3u8_link:
            print(f"Failed to get download link for {movie.title}")
            return None

        print(f"Downloading: {movie.title} from {m3u8_link}")

        output_filename = base + ".mkv"
        downloaded = download_m3u8(
            m3u8_link,
            output_filename,
            testing=TESTING_MODE,
            on_start=lambda: (refresh_jellyfin(), on_ready and on_ready()),
            on_process=lambda proc: register_process(movie.id, proc),
        )
        if not downloaded:
            return None

        return movie.id, True
    finally:
        with pause_cond:
            claimed.discard(movie.id)
            running.pop(movie.id, None)
            urgent_ids.discard(movie.id)
            apply_pause()
            pause_cond.notify_all()


def jellyfin_base_url():
    address = JELLYFIN_ADDR
    if not address.startswith(("http://", "https://")):
        address = f"http://{address}"
    parsed_address = urlsplit(address)
    if parsed_address.port is None:
        parsed_address = parsed_address._replace(
            netloc=f"{parsed_address.netloc}:8096"
        )
    return urlunsplit(parsed_address).rstrip("/")


def refresh_jellyfin():
    if not JELLYFIN_ADDR or not JELLYFIN_API_KEY:
        print("Jellyfin refresh skipped; configure JELLYFINADDR and JELLYFINAPIKEY.")
        return

    base_url = jellyfin_base_url()

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



downloaded_lock = threading.Lock()


def record_downloaded(movie_id):
    with downloaded_lock:
        downloadedMovies.add(movie_id)
        with open(DOWNLOADED_FILE, "w") as f:
            f.write("\n".join(downloadedMovies))


# On-demand downloads: GET /<code> shows a loading page, downloads the movie, scans
# Jellyfin, then sends the browser to the movie's page in Jellyfin
CODE_RE = re.compile(r"^[A-Za-z0-9]{2,12}$")
jobs = {}  # movie code -> {"status": starting|scanning|ready|error, "url": str, "error": str}

LOADING_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<title>Preparing movie</title>
<body style="font-family:sans-serif;background:#111;color:#eee;text-align:center;padding-top:20vh">
<h2 id=m>Starting download...</h2><p>This page will open the movie when it is ready.</p>
<script>
const labels = {starting: "Starting download...", scanning: "Adding to Jellyfin..."};
async function poll() {
  try {
    const r = await (await fetch("/status/__CODE__")).json();
    if (r.status === "ready") { location.href = r.url; return; }
    if (r.status === "error") { document.getElementById("m").textContent = r.error; return; }
    document.getElementById("m").textContent = labels[r.status] || r.status;
  } catch (e) {}
  setTimeout(poll, 2000);
}
poll();
</script>"""


def fetch_title(code):
    page = requests.get(f"{BASEURL}/movie/watch/{code}/?lang={API_LANG}", timeout=15)
    page.raise_for_status()
    title = bs4.BeautifulSoup(page.text, "html.parser").title
    # Page titles look like "Name (2026) Tamil in HD - Einthusan"
    name = re.sub(r'[\\/:*?"<>|]', "", title.text.split(" (")[0]).strip() if title else ""
    return name or code


def find_jellyfin_item(code, title):
    response = requests.get(
        f"{jellyfin_base_url()}/Items",
        params={
            "Recursive": "true",
            "IncludeItemTypes": "Movie",
            "Fields": "Path",
            "SearchTerm": code,
        },
        headers={"Authorization": f'MediaBrowser Token="{JELLYFIN_API_KEY}"'},
        timeout=10,
    )
    response.raise_for_status()
    for item in response.json().get("Items", []):
        if f"{code} - " in os.path.basename(item.get("Path", "")):
            return item["Id"]
    return None


def locate_in_jellyfin(code, title, job):
    base = JELLYFIN_PUBLIC_URL or jellyfin_base_url()
    search_url = f"{base}/web/index.html#!/search.html?query={quote(code)}"
    if not JELLYFIN_ADDR or not JELLYFIN_API_KEY:
        job.update(status="ready", url=search_url)
        return

    job["status"] = "scanning"
    for attempt in range(30):
        if attempt % 5 == 0:
            refresh_jellyfin()
        try:
            item_id = find_jellyfin_item(code, title)
        except requests.RequestException as error:
            print(f"Jellyfin lookup failed: {error}")
            item_id = None
        if item_id:
            job.update(status="ready", url=f"{base}/web/index.html#!/details?id={item_id}")
            return
        sleep(3)
    job.update(status="ready", url=search_url)  # scan is slow; fall back to search


def start_on_demand(code):
    with downloaded_lock:
        if code in jobs:
            return
        job = jobs[code] = {"status": "starting"}

    def run():
        located = threading.Event()

        def locate(title):
            if not located.is_set():
                located.set()
                locate_in_jellyfin(code, title, job)

        try:
            movie = Movie(
                fetch_title(code),
                f"{BASEURL}/movie/watch/{code}/?lang={API_LANG}",
                code,
            )
            result = download_movie(
                movie,
                on_ready=lambda: threading.Thread(target=locate, args=(movie.title,)).start(),
                urgent=True,
            )
            if result:
                if result[1] is not None:
                    record_downloaded(result[0])
                # Also covers files that already existed or merged into the queue
                locate(movie.title)
            elif not located.is_set():
                job.update(status="error", error="Download failed. Check the code.")
        except Exception as error:
            print(f"On-demand download failed for {code}: {error}")
            job.update(status="error", error="Could not start the download. Check the code.")
        finally:
            if job["status"] == "error":
                # Allow a retry
                with downloaded_lock:
                    jobs.pop(code, None)

    threading.Thread(target=run, daemon=True).start()


class MovieRequestHandler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        parts = self.path.split("?")[0].strip("/").split("/")
        if parts[0] == "watch":
            parts = parts[1:]
        is_status = len(parts) == 2 and parts[0] == "status"
        code = parts[-1]
        if len(parts) > 2 or (len(parts) == 2 and not is_status) or not CODE_RE.match(code):
            self.send_error(400, "Expected /<movie code>")
            return

        if is_status:
            job = jobs.get(code, {"status": "error", "error": "Unknown code."})
            self.reply(200, json.dumps(job), "application/json")
            return

        start_on_demand(code)
        self.reply(200, LOADING_PAGE.replace("__CODE__", code), "text/html")

    def log_message(self, format, *args):
        print("API:", format % args)


if API_PORT:
    server = ThreadingHTTPServer(("0.0.0.0", API_PORT), MovieRequestHandler)
    threading.Thread(target=server.serve_forever).start()
    print(f"API listening on port {API_PORT}")


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
        record_downloaded(movie_id)

        if is_new_download:
            refresh_jellyfin()

print("All Downloads Complete")

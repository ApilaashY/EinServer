import bs4
import requests
import os
from dotenv import load_dotenv
from Movie import Movie
import threading
from downloader import download_m3u8, get_movie_download_link
from time import sleep

BASEURL = "https://einthusan.tv"
load_dotenv()
FOLDER = os.getenv("FOLDER", "movies")
PAGECOUNT = int(os.getenv("PAGECOUNT", "3"))

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
            movieLinks.append(Movie(title.find("h3").text, BASEURL + link))

        print(title.find("h3").text)

for movie in movieLinks:
    print(f"Title: {movie.title}, Link: {movie.link}")


if not os.path.exists(FOLDER):
    os.makedirs(FOLDER)


def download_movie(movie):
    # Check if the movie is already downloaded
    if os.path.exists(os.path.join(FOLDER, f"{movie.title}.mp4")):
        print(f"{movie.title} is already downloaded.")
        downloadedMovies.add(movie.title)
        with open("downloaded", "w") as f:
            f.write("\n".join(list(downloadedMovies)))
        return

    # Get the m3u8 link from the movie page
    m3u8_link = get_movie_download_link(movie.link)
    if not m3u8_link:
        print(f"Failed to get download link for {movie.title}")
        return

    print(f"Downloading: {movie.title} from {m3u8_link}")

    output_filename = os.path.join(FOLDER, f"{movie.title}.mp4")
    download_m3u8(m3u8_link, output_filename)

    # Save the new downloaded movie list
    downloadedMovies.add(movie.title)
    with open("downloaded", "w") as f:
        f.write("\n".join(list(downloadedMovies)))

# Download movies to the folder
for movie in movieLinks:
    download_movie(movie)

import subprocess
import m3u8_To_MP4
import os
from playwright.sync_api import sync_playwright

def download_m3u8(m3u8_url, output_filename="output.mp4"):
    # TESTING
    # Create a fake file for faster testing
    # with open(output_filename, "w") as f:
    #     f.write("")

    # return
    """
    Downloads an M3U8 streaming playlist and saves it as a single MP4 file.
    """
    # FFmpeg flags: -i specifies input, -c copy copies audio/video streams without re-encoding
    # -bsf:a aac_adtstoasc fixes bitstream filtering issues for AAC audio tracks
    command = [
        'ffmpeg',
        '-y',                             # Automatically overwrite existing files
        '-http_persistent', '1',          # Persist the connection (Must be before -i)
        '-http_multiple', '1',             # Use multiple HTTP connections for HLS segments
        '-i', m3u8_url,
        '-c', 'copy', 
        '-bsf:a', 'aac_adtstoasc', 
        output_filename
    ]
    
    try:
        print(f"Starting download for: {m3u8_url}")
        # Execute the FFmpeg command
        subprocess.run(command, check=True)
        print(f"Download complete! Saved as {output_filename}")
    except subprocess.CalledProcessError as e:
        print(f"An error occurred during downloading: {e}")
    except FileNotFoundError:
        print("Error: FFmpeg is not installed or not found in your system PATH.")


def get_movie_download_link(movie_page_url) -> str:

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        page.goto(movie_page_url)
        
        # Define your element selector and the target attribute name
        selector = 'video[x-webkit-airplay="deny"]'
        attribute_name = "src" # Replace with whatever attribute you are waiting for

        # 1. Wait for the attribute to exist and grab it in one go
        attribute_value = page.wait_for_function(
            """
            ([sel, attr]) => {
                const el = document.querySelector(sel);
                // Returns the value (string) if it exists, otherwise returns null/false to keep waiting
                return el && el.hasAttribute(attr) ? el.getAttribute(attr) : false;
            }
            """,
            arg=[selector, attribute_name]
        ).json_value() # Evaluates the JS handle and extracts the string value
        
        browser.close()

        return attribute_value
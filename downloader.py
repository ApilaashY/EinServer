import signal
import subprocess
import threading
from contextlib import contextmanager
import m3u8_To_MP4
import os
from playwright.sync_api import sync_playwright

# Priority (on-demand) jobs pause normal downloads until every priority job is done
_lock = threading.Lock()
_priority_jobs = 0
_normal_procs = set()
_normal_may_run = threading.Event()
_normal_may_run.set()


@contextmanager
def priority_job():
    global _priority_jobs
    with _lock:
        _priority_jobs += 1
        _normal_may_run.clear()
        for proc in _normal_procs:
            proc.send_signal(signal.SIGSTOP)
    try:
        yield
    finally:
        with _lock:
            _priority_jobs -= 1
            if _priority_jobs == 0:
                for proc in _normal_procs:
                    proc.send_signal(signal.SIGCONT)
                _normal_may_run.set()


def wait_for_turn():
    """Blocks a normal (non-priority) download while a priority job is running."""
    _normal_may_run.wait()


def download_m3u8(m3u8_url, output_filename="output.mkv", testing=False, on_start=None, priority=False):
    # TESTING
    # Create a fake file for faster testing
    if testing:
        with open(output_filename, "w") as f:
            f.write("")
        return True

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
        # Reconnect if the connection drops, e.g. after a long pause
        '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '30',
        '-reconnect', '1',                # Survive dropped connections (e.g. after a long pause)
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '30',
        '-i', m3u8_url,
        '-c', 'copy', 
        '-bsf:a', 'aac_adtstoasc', 
        output_filename
    ]
    
    try:
        print(f"Starting download for: {m3u8_url}")
        # Execute the FFmpeg command
        # MKV is playable while still being written, so Jellyfin can stream the partial file
        if not priority:
            wait_for_turn()
        process = subprocess.Popen(command)
        if on_process:
            on_process(process)
        if not priority:
            with _lock:
                _normal_procs.add(process)
                if _priority_jobs:
                    process.send_signal(signal.SIGSTOP)
        if on_start:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                on_start()
        try:
            returncode = process.wait()
        finally:
            with _lock:
                _normal_procs.discard(process)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command)
        print(f"Download complete! Saved as {output_filename}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"An error occurred during downloading: {e}")
        if os.path.exists(output_filename):
            os.remove(output_filename)
        return False
    except FileNotFoundError:
        print("Error: FFmpeg is not installed or not found in your system PATH.")
        return False


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
import os
import tempfile
import platform
from enum import Enum
import urllib.request
import urllib.error
import json


class OSType(Enum):
    WINDOWS = "windows"
    MAC = "mac"
    LINUX = "linux"


class AppUpdater:
    def __init__(self, repo_path: str, current_version: str):
        """
        Initializes the updater engine.
        """
        self.repo_path = repo_path
        self.current_version = current_version

        self.os_type = self._detect_os()
        self.temp_dir = self._setup_temp_directory()
        print(self._get_download_url(self._fetch_latest_release_data()["assets"]))

    def _detect_os(self) -> OSType:
        """
        Detects the current operating system.
        Returns a clean string: 'windows', 'mac', or 'linux'.
        Raises an EnvironmentError if the OS is unsupported.
        """
        os_name = platform.system()

        match os_name:
            case "Windows":
                return OSType.WINDOWS
            case "Darwin":
                return OSType.MAC
            case "Linux":
                return OSType.LINUX
            case _:
                raise EnvironmentError(f"Unsupported operating system: {os_name}")

    def _setup_temp_directory(self) -> str:
        """
        Locates the system's temporary folder and creates a dedicated
        subfolder for our app updates (e.g., /tmp/MyAwesomeApp_Updates).
        Returns the path to this folder.
        """
        base_temp = tempfile.gettempdir()
        safe_app_name = self.repo_path.split("/")[-1] + "_update_cache"
        full_path = os.path.join(base_temp, safe_app_name)
        os.makedirs(full_path, exist_ok=True)

        return full_path

    def _fetch_latest_release_data(self) -> dict:
        """
        Hits the GitHub API to fetch the latest release JSON.
        Returns the parsed JSON dictionary, or an empty dict if it fails.
        """
        url = f"https://api.github.com/repos/{self.repo_path}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "CustomAppUpdater"})

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_data = response.read().decode("utf-8")
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            raise

        json_data = json.loads(raw_data)

        return json_data

    def _parse_version(self, version_str: str) -> tuple:
        clean_str = version_str.removeprefix("v")
        return tuple(int(x) for x in clean_str.split("."))

    def _get_download_url(self, assets: list) -> str | None:
        """
        Loops through the release assets and finds the correct download URL
        for the current operating system. Returns None if not found.
        """
        match self.os_type:
            case OSType.WINDOWS:
                valid_extensions = (".exe",)
            case OSType.MAC:
                valid_extensions = (".dmg", ".pkg", ".zip")
            case OSType.LINUX:
                valid_extensions = (".AppImage", ".tar.gz", ".deb")

        target_asset = next(
            (
                asset
                for asset in assets
                if asset.get("name", "").endswith(valid_extensions)
            ),
            None,
        )

        if target_asset:
            return target_asset.get("browser_download_url")

        return None

    def _download_update(self, download_url: str) -> str | None:
        """
        Downloads the asset from the provided URL into the temporary directory.
        Returns the absolute path to the downloaded file, or None if it fails.
        """
        if not download_url:
            return None

        # 1. Extract the file name from the URL
        file_name = download_url.split("/")[-1]

        # 2. Join the temp directory with the file name
        save_path = os.path.join(self.temp_dir, file_name)

        # 3. Create the Request object
        req = urllib.request.Request(
            download_url, headers={"User-Agent": "CustomAppUpdater"}
        )

        try:
            # 4. Open the network stream and the local file stream simultaneously
            with (
                urllib.request.urlopen(req, timeout=30) as response,
                open(save_path, "wb") as out_file,
            ):
                # 5. The Chunked Download Loop
                chunk_size = 1024 * 1024

                while True:
                    # Read a chunk from the internet
                    chunk = response.read(chunk_size)

                    # If the chunk is empty, the download is completely finished
                    if not chunk:
                        break

                    # Write the chunk to the hard drive
                    out_file.write(chunk)

            return save_path

        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            print(f"Failed to download update: {e}")
            return None


test = AppUpdater("christopher-pedraza/multiopener", "v1.1")

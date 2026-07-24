import os
import tempfile
import platform
from enum import Enum
import urllib.request
import urllib.error
import json
import subprocess
import sys
from typing import Callable


class OSType(Enum):
    WINDOWS = "windows"
    MAC = "mac"
    LINUX = "linux"


class AppUpdater:
    def __init__(
        self,
        repo_path: str,
        current_version: str,
        on_log: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.repo_path = repo_path
        self.current_version = current_version

        # Save the callbacks. If the user didn't provide one, use a dummy lambda
        # so we don't have to write `if self.on_log:` every single time.
        self.on_log = on_log or (lambda msg: None)
        self.on_error = on_error or (lambda msg: None)

        self.os_type = self._detect_os()
        self.temp_dir = self._setup_temp_directory()

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

    def check_for_updates(self) -> str | None:
        self.on_log(f"Checking for updates for {self.repo_path}...")
        release_data = self._fetch_latest_release_data()

        if not release_data:
            self.on_error("Could not fetch release data from GitHub.")
            return None

        latest_tag = release_data.get("tag_name", "")
        if not latest_tag:
            self.on_error("No release tags found in the repository.")
            return None

        current_tuple = self._parse_version(self.current_version)
        latest_tuple = self._parse_version(latest_tag)

        if latest_tuple > current_tuple:
            self.on_log(f"Update found! {self.current_version} -> {latest_tag}")
            return self._get_download_url(release_data.get("assets", []))

        self.on_log("App is up to date.")
        return None

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
            self.on_error(f"Failed to download update: {e}")
            return None

    def _apply_update(self, new_file_path: str):
        """
        Generates a hand-off script, launches it, and exits the current app.
        """
        current_exe = sys.executable

        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }

        match self.os_type:
            case OSType.WINDOWS:
                bat_content = f"""@echo off
timeout /t 2 /nobreak > NUL
move /y "{new_file_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
                bat_path = os.path.join(self.temp_dir, "updater.bat")
                with open(bat_path, "w") as f:
                    f.write(bat_content)

                kwargs["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0x08000000
                )
                command = ["cmd.exe", "/c", bat_path]

            case OSType.MAC | OSType.LINUX:
                bash_content = f"""#!/bin/bash
sleep 2
mv -f "{new_file_path}" "{current_exe}"
chmod +x "{current_exe}"
nohup "{current_exe}" >/dev/null 2>&1 &
rm -- "$0"
"""
                bash_path = os.path.join(self.temp_dir, "updater.sh")
                with open(bash_path, "w") as f:
                    f.write(bash_content)

                os.chmod(bash_path, 0o755)

                kwargs["start_new_session"] = True
                command = ["bash", bash_path]

        # 4. Launch the subprocess (type checker is suppressed for cross-platform dynamic kwargs)
        subprocess.Popen(command, **kwargs)  # type: ignore

        # 5. Exit the Python app so the lock drops
        sys.exit(0)

    def check_and_update(self) -> bool:
        """
        The main entry point for host apps.
        Checks for updates, downloads the new version, and applies it.
        Returns True if an update was applied (though the app will exit before returning),
        and False if no update was needed or an error occurred.
        """
        # Phase 2: Check for updates
        download_url = self.check_for_updates()
        if not download_url:
            return False

        # Phase 3: Download
        print(f"Starting download from {download_url}...")
        new_file_path = self._download_update(download_url)
        if not new_file_path:
            return False

        # Phase 4: Apply and restart
        print("Download complete. Applying update...")
        self._apply_update(new_file_path)

        return True

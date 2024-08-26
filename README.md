# Plex YouTube Sync

**Project Description:**  
This project synchronizes Plex playlists with YouTube. It allows you to match tracks from Plex with corresponding YouTube videos and create or update YouTube playlists based on your Plex playlists.

## Table of Contents
- [Installation](#installation)
- [Environment Setup](#environment-setup)
- [Usage](#usage)
  - [Commands](#commands)
- [Contributing](#contributing)
- [License](#license)

## Installation

### Prerequisites
- **Python Version:** Python 3.8+
- **Dependencies:** Install the required Python packages with the following command:

  ```bash
  pip install -r requirements.txt
  ```

  Create a `requirements.txt` file with the following content:

  ```
  click
  requests
  plexapi
  sqlalchemy
  pytube
  ytmusicapi
  ```

### Environment Setup
1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/plex-youtube-sync.git
   cd plex-youtube-sync
   ```

2. **Database Initialization:**
   
   The project uses SQLite for managing data. The database will be automatically initialized when you first run the application.

   ```bash
   python plexmusic_youtubevideos.py configure
   ```

   This command will prompt you to enter your Plex server URL, Plex token, and the path to your YouTube client secrets file.

3. **Configure Authentication:**

   You need to provide a YouTube client secrets file to authenticate with the YouTube API. The path to this file will be specified during the `configure` step.

## Usage

### Commands
The CLI provides several commands to manage and synchronize your playlists.

- **Configure the Application:**

  Run the following command to configure your Plex and YouTube API keys:

  ```bash
  python plexmusic_youtubevideos.py configure
  ```

- **Match Tracks:**

  This command matches tracks from your Plex playlists with YouTube videos.

  ```bash
  python plexmusic_youtubevideos.py match
  ```

  **Options:**
  - `--update-only`: Only update existing matches without presenting new matches.

- **Re-Match Tracks:**

  Use this command to re-match an existing Plex track to a different YouTube video.

  ```bash
  python plexmusic_youtubevideos.py re_match --track-id <TRACK_ID> --video-id <VIDEO_ID>
  ```

  **Options:**
  - `--track-id`: The Plex track ID to re-match.
  - `--video-id`: The YouTube video ID to match with a Plex track.

- **Synchronize Playlists:**

  This command synchronizes the local database state to YouTube playlists.

  ```bash
  python plexmusic_youtubevideos.py sync
  ```

- **Check Tracks:**

  This command checks the availability of the tracks in the local database on YouTube.

  ```bash
  python plexmusic_youtubevideos.py check_tracks
  ```

## Contributing
1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes with clear messages.
4. Push to the branch.
5. Submit a pull request.

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.


> Contributions are welcome, please go ahead and create a pull request to contribute, thanks!
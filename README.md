# Plex-YouTube Sync

Plex-YouTube Sync is a command-line tool to synchronize your Plex smart music playlists with YouTube music videos. The tool allows you to watch your favorite music videos on YouTube based on your playlists in Plex.

## Features

- Authenticate using OAuth2 with both Plex and YouTube.
- Maintain a list of Plex playlists to sync in a config file.
- Use a local SQLite database to store already matched playlist items and avoid updating them on repeated runs.
- Use `pytube` to search for YouTube videos, minimizing YouTube API usage.
- Prompt the user to select the correct video match.
- Sync the local playlist state to YouTube, adding new songs and removing those that have been removed.

## Installation

### Prerequisites

- Python 3.7+
- [Poetry](https://python-poetry.org/docs/#installation)

### Steps

1. **Clone the Repository**

   ```sh
   git clone https://github.com/yourusername/plex-youtube-sync.git
   cd plex-youtube-sync
   ```

2. ** Install Dependencies

   ```sh
   poetry install
   ```

3. Create Configuration Files

  * Create youtube_credentials.json from the Google API Console for OAuth2.
  * Run the configure command to set up Plex and YouTube credentials.

## Configuration
Run the following command to configure Plex and YouTube settings:

   ```sh
   poetry run python sync.py configure
   ```

You will be prompted for:

  * Plex Server URL
  * Plex Token
  * Path to the YouTube client secrets JSON file
  * Comma-separated list of Plex Playlist IDs to sync

## Usage
### Sync Playlists
Synchronize specified Plex playlists with YouTube music videos:

```sh
poetry run python sync.py sync
```

### Sync YouTube Playlists
Sync the local playlist state to YouTube, adding new songs and removing those that have been removed:

```sh
poetry run python sync.py sync_youtube
```

### Search YouTube Videos
Search YouTube videos matching a title:

```sh
poetry run python sync.py search_youtube <query>
```

### List Plex Playlist Items
List all items in a Plex playlist:

```sh
poetry run python sync.py list_plex_items <playlist_id>
```

List YouTube Playlist Items
List all items in a stored YouTube playlist:

```sh
poetry run python sync.py list_youtube_items <youtube_playlist_id>
```

### List All Playlists
List all playlists, showing both Plex playlist name and YouTube playlist ID:

```sh
poetry run python sync.py list_playlists
```

## Development
To contribute to this project:

  * Fork the repository.
  * Create a new feature branch.
  * Make your changes and commit them.
  * Push to your fork and create a pull request.

## License
This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments
  * Plex API for interacting with Plex.
  * Google APIs Client Library for Python for interacting with YouTube.
  * Pytube for YouTube video search.
 
Feel free to open an issue if you find a bug or have a suggestion!

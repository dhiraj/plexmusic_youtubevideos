import os
import json
import click
from plexapi.server import PlexServer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from pytube import Search


# File paths to store authentication tokens and config
CONFIG_FILE = os.path.expanduser("~/.plex_youtube_sync_config.json")
YOUTUBE_CREDENTIALS_FILE = 'youtube_credentials.json'
YOUTUBE_TOKEN_FILE = os.path.expanduser("~/.youtube_token.json")
DATABASE_FILE = os.path.expanduser("~/.plex_youtube_sync.db")

SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Initialize database
Base = declarative_base()


class PlexPlaylist(Base):
    __tablename__ = 'plex_playlists'
    id = Column(Integer, primary_key=True)
    playlist_id = Column(String, unique=True)
    playlist_title = Column(String)


class PlexPlaylistItem(Base):
    __tablename__ = 'plex_playlist_items'
    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey('plex_playlists.id'))
    track_id = Column(String)
    track_title = Column(String)
    video_id = Column(String)


class YouTubePlaylist(Base):
    __tablename__ = 'youtube_playlists'
    id = Column(Integer, primary_key=True)
    plex_playlist_id = Column(Integer, ForeignKey('plex_playlists.id'))
    playlist_id = Column(String, unique=True)
    playlist_title = Column(String)


class YouTubePlaylistItem(Base):
    __tablename__ = 'youtube_playlist_items'
    id = Column(Integer, primary_key=True)
    youtube_playlist_id = Column(Integer, ForeignKey('youtube_playlists.id'))
    video_id = Column(String, unique=True)


# Create the SQLite engine and session
engine = create_engine(f'sqlite:///{DATABASE_FILE}')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}


def authenticate_youtube():
    creds = None
    if os.path.exists(YOUTUBE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(YOUTUBE_TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    return creds


def fetch_plex_playlists(plex_url, plex_token):
    plex = PlexServer(plex_url, plex_token)
    playlists = plex.playlists()
    return playlists


def search_pytube(query, max_results=5):
    search = Search(query)
    results = search.results[:max_results]
    video_data = []

    for video in results:
        video_data.append({
            'title': video.title,
            'url': video.watch_url,
            'video_id': video.video_id
        })

    return video_data[0]['video_id']


def search_youtube_videos(youtube_service, query):
    request = youtube_service.search().list(q=query, part='snippet', type='video', maxResults=1)
    response = request.execute()
    return response['items'][0]['id']['videoId'] if response['items'] else None


def get_existing_video_id(track_id):
    record = session.query(PlexPlaylistItem).filter_by(track_id=track_id).first()
    return record.video_id if record else None


def save_video_id(plex_playlist_id, track_id, track_title, video_id):
    session.add(
        PlexPlaylistItem(playlist_id=plex_playlist_id, track_id=track_id, track_title=track_title, video_id=video_id))
    session.commit()


def create_youtube_playlist(youtube_service, title):
    request = youtube_service.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": f"A playlist created based on the Plex playlist: {title}",
                "tags": ["Plex", "Music", "YouTube"],
                "defaultLanguage": "en"
            },
            "status": {
                "privacyStatus": "public"
            }
        }
    )
    response = request.execute()
    return response["id"]


def add_video_to_youtube_playlist(youtube_service, playlist_id, video_id):
    request = youtube_service.playlistItems().insert(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
    request.execute()


@click.group()
def cli():
    pass


@cli.command()
@click.option('--plex-url', prompt='Plex Server URL', help='URL of the Plex server')
@click.option('--plex-token', prompt='Plex Token', hide_input=True, help='Plex token for authentication')
@click.option('--youtube-client-secrets', prompt='YouTube Client Secrets File', type=click.Path(exists=True),
              help='Path to the YouTube client secrets JSON file')
@click.option('--playlists', prompt='Plex Playlist IDs', help='Comma-separated list of Plex Playlist IDs to sync')
def configure(plex_url, plex_token, youtube_client_secrets, playlists):
    """Configure the Plex and YouTube API keys, and specify playlists to sync."""
    config = {
        "plex_url": plex_url,
        "plex_token": plex_token,
        "youtube_client_secrets": youtube_client_secrets,
        "playlists": playlists.split(',')
    }
    save_config(config)
    click.echo("Configuration saved successfully.")


@cli.command()
def sync():
    """Sync specified Plex playlists with YouTube music videos."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    youtube_service = build('youtube', 'v3', credentials=authenticate_youtube())
    plex_url = config["plex_url"]
    plex_token = config["plex_token"]
    playlist_titles = config["playlists"]

    playlists = fetch_plex_playlists(plex_url, plex_token)
    for playlist in playlists:
        if playlist.title not in playlist_titles:
            continue

        click.echo(f"Playlist: {playlist.title}")

        # Check if this Plex playlist already has a corresponding YouTube playlist
        youtube_playlist = session.query(YouTubePlaylist).filter_by(plex_playlist_id=playlist.guid).first()
        if youtube_playlist:
            youtube_playlist_id = youtube_playlist.playlist_id
        else:
            youtube_playlist_id = create_youtube_playlist(youtube_service, playlist.title)
            session.add(YouTubePlaylist(plex_playlist_id=playlist.guid, playlist_id=youtube_playlist_id,
                                        playlist_title=playlist.title))
            session.commit()

        for track in playlist.items():
            existing_video_id = get_existing_video_id(track.ratingKey)
            if existing_video_id:
                click.echo(
                    f"Track: {track.title}, YouTube Video: https://www.youtube.com/watch?v={existing_video_id} (cached)")
                add_video_to_youtube_playlist(youtube_service, youtube_playlist_id, existing_video_id)
                continue

            query = f"{track.title} {track.originalTitle} -lyrical -lyric -audio"
            video_id = search_pytube(query)
            if video_id:
                click.echo(f"Track: {track.title}, YouTube Video: https://www.youtube.com/watch?v={video_id}")
                save_video_id(playlist.guid, track.ratingKey, track.title, video_id)
                add_video_to_youtube_playlist(youtube_service, youtube_playlist_id, video_id)
                # Avoid adding duplicate video entries in YouTube playlist
                if not session.query(YouTubePlaylistItem).filter_by(video_id=video_id).first():
                    session.add(YouTubePlaylistItem(youtube_playlist_id=youtube_playlist_id, video_id=video_id))
                    session.commit()
            else:
                click.echo(f"No video found for track: {track.title}")


@cli.command()
@click.argument('query')
def search_youtube(query):
    """Search YouTube videos matching a title."""
    youtube_service = build('youtube', 'v3', credentials=authenticate_youtube())
    video_id = search_pytube(query)
    if video_id:
        click.echo(f"Video ID: {video_id}")
    else:
        click.echo("No video found.")


@cli.command()
@click.argument('playlist_id')
def list_plex_items(playlist_id):
    """List all items in a Plex playlist."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    plex_url = config["plex_url"]
    plex_token = config["plex_token"]
    plex = PlexServer(plex_url, plex_token)
    playlist = plex.playlist(playlist_id)
    click.echo(f"Playlist: {playlist.title}")
    for item in playlist.items:
        click.echo(f"Track: {item.title}, Artist: {item.originalTitle}")


@cli.command()
@click.argument('youtube_playlist_id')
def list_youtube_items(youtube_playlist_id):
    """List all items in a stored YouTube playlist."""
    items = session.query(YouTubePlaylistItem).filter_by(youtube_playlist_id=youtube_playlist_id).all()
    if not items:
        click.echo("No items found in this YouTube playlist.")
        return

    for item in items:
        click.echo(f"Video ID: {item.video_id}")


if __name__ == "__main__":
    cli()

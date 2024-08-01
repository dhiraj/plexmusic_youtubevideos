import os
import json
import click
from google_auth_httplib2 import Request
from plexapi.server import PlexServer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from pytube import Search
from google.auth.transport.requests import Request

# File paths to store authentication tokens and config
CONFIG_FILE = os.path.expanduser("~/.plex_youtube_sync_config.json")
YOUTUBE_CREDENTIALS_FILE = 'youtube_credentials.json'
YOUTUBE_TOKEN_FILE = os.path.expanduser("./youtube_token.json")
DATABASE_FILE = os.path.expanduser("~/.plex_youtube_sync.db")

SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Initialize database
Base = declarative_base()


class PlexPlaylist(Base):
    __tablename__ = 'plex_playlists'
    id = Column(Integer, primary_key=True)
    playlist_id = Column(String, unique=True)
    title = Column(String, unique=True)


class PlexPlaylistItem(Base):
    __tablename__ = 'plex_playlist_items'
    id = Column(Integer, primary_key=True)
    playlist_id = Column(Integer, ForeignKey('plex_playlists.id'))
    track_id = Column(String, ForeignKey('plex_tracks.track_id'))


class PlexTrack(Base):
    __tablename__ = 'plex_tracks'
    id = Column(Integer, primary_key=True)
    track_id = Column(String)
    title = Column(String)
    artist_name = Column(String)
    album_name = Column(String)
    video_id = Column(String, nullable=True)
    no_match = Column(Boolean, default=False)


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
    return plex.playlists()


def search_youtube_videos(query):
    search = Search(query)
    return search.results


def get_existing_video_id(track_id):
    record = session.query(PlexPlaylistItem).filter_by(track_id=track_id).first()
    return record.video_id if record else None


def save_playlistitem(plex_playlist_id, track_id, track_title, artist_name, album_name, video_id):
    plex_item = PlexPlaylistItem(
        playlist_id=plex_playlist_id,
        track_id=track_id,
        track_title=track_title,
        artist_name=artist_name,
        album_name=album_name,
        video_id=video_id
    )
    session.add(plex_item)
    session.commit()


def save_track(track_id, track_title, artist_name, album_name, video_id):
    plex_item = PlexTrack(
        track_id=track_id,
        title=track_title,
        artist_name=artist_name,
        album_name=album_name,
        video_id=video_id
    )
    session.add(plex_item)
    session.commit()


def mark_no_match(track_id, track_title, artist_name, album_name):
    session.add(PlexTrack(
        track_id=track_id,
        title=track_title,
        artist_name=artist_name,
        album_name=album_name,
        no_match=True
    ))
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


def sync_local_to_youtube(youtube_service):
    """Sync local playlist state to YouTube."""
    playlists = session.query(YouTubePlaylist).all()
    for yt_playlist in playlists:
        # Fetch existing items in the YouTube playlist
        existing_items = session.query(YouTubePlaylistItem).filter_by(youtube_playlist_id=yt_playlist.id).all()
        existing_video_ids = {item.video_id for item in existing_items}

        # Fetch corresponding Plex playlist items
        plex_items = session.query(PlexPlaylistItem).filter_by(playlist_id=yt_playlist.plex_playlist_id).all()
        plex_video_ids = {item.video_id for item in plex_items if item.video_id}

        # Add new items to YouTube playlist
        with click.progressbar(plex_items) as items:
            for item in items:
                if item.video_id and item.video_id not in existing_video_ids:
                    add_video_to_youtube_playlist(youtube_service, yt_playlist.playlist_id, item.video_id)
                    session.add(YouTubePlaylistItem(youtube_playlist_id=yt_playlist.id, video_id=item.video_id))
                    session.commit()

        # Remove items from YouTube playlist that are no longer in the Plex playlist
        with click.progressbar(existing_items) as items_remove:
            for item in items_remove:
                if item.video_id not in plex_video_ids:
                    request = youtube_service.playlistItems().delete(id=item.video_id)
                    request.execute()
                    session.delete(item)
                    session.commit()


@click.group()
def cli():
    pass


@cli.command()
@click.option('--plex-url', prompt='Plex Server URL', help='URL of the Plex server')
@click.option('--plex-token', prompt='Plex Token', hide_input=True, help='Plex token for authentication')
@click.option('--youtube-client-secrets', prompt='YouTube Client Secrets File', type=click.Path(exists=True),
              help='Path to the YouTube client secrets JSON file')
@click.option('--playlists', prompt='Plex Playlist Titles', help='Comma-separated list of Plex Playlist titles to sync')
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
def match():
    """Match specified Plex playlists with YouTube music videos and save the matches."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    plex_url = config["plex_url"]
    plex_token = config["plex_token"]
    playlist_titles = config["playlists"]
    creds = authenticate_youtube()
    youtube_service = build("youtube", "v3", credentials=creds)

    playlists = fetch_plex_playlists(plex_url, plex_token)
    playlist_map = {playlist.title: playlist for playlist in playlists}

    for title in playlist_titles:
        if title not in playlist_map:
            click.echo(f"Playlist '{title}' not found on Plex server.")
            continue

        playlist = playlist_map[title]

        click.echo(f"Playlist: {playlist.title}")
        existing_track_ids = session.scalars(session.query(PlexTrack.track_id)).all()

        for track in playlist.items():
            if track.type != 'track':
                continue
            if track.ratingKey in existing_track_ids:
                continue

            click.echo(
                f"Track: {track.title}, Artist: {track.artist().title}, Album: {track.album().title}, id: {track.ratingKey}")

            # Default search with artist and song title
            query = f"{track.artist().title} - {track.title} - {track.album().title}"

            results = search_youtube_videos(query)
            if results:
                click.echo("1. Enter custom YouTube video ID")
                click.echo("2. Mark as no match")
                for i, video in enumerate(results):
                    click.echo(f"{i + 1 + 2}. {video.title} (https://www.youtube.com/watch?v={video.video_id})")

                selected_index = click.prompt("Select a match (0 to skip)", type=int, default=3)
                if 2 < selected_index <= len(results):
                    selected_video = results[selected_index - 1 - 2]
                    save_track(track.ratingKey, track.title, track.artist().title,track.album().title, selected_video.video_id)
                    click.echo(f"Selected: {selected_video.title}")
                    continue

                elif selected_index == 1:
                    custom_video_id = click.prompt("Enter YouTube video ID")
                    save_track(track.ratingKey, track.title, track.artist().title,track.album().title, custom_video_id)
                    click.echo(f"Custom video ID saved: {custom_video_id}")

                elif selected_index == 2:
                    mark_no_match(track.ratingKey, track.title, track.artist().title,track.album().title)
                    click.echo("Track marked as no match.")

    click.echo("All YouTube video matches updated in the database.")


@cli.command()
def sync_youtube():
    """Sync the local playlist state to YouTube."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    creds = authenticate_youtube()
    youtube_service = build("youtube", "v3", credentials=creds)
    sync_local_to_youtube(youtube_service)


@cli.command()
@click.argument('query')
def search_youtube(query):
    """Search YouTube videos matching a query."""
    results = search_youtube_videos(query)
    if results:
        for i, video in enumerate(results):
            click.echo(f"{i + 1}. {video.title} (https://www.youtube.com/watch?v={video.video_id})")
    else:
        click.echo("No video found.")


@cli.command()
@click.argument('playlist_title')
def list_plex_items(playlist_title):
    """List all items in a Plex playlist."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    plex_url = config["plex_url"]
    plex_token = config["plex_token"]
    plex = PlexServer(plex_url, plex_token)
    playlists = fetch_plex_playlists(plex_url, plex_token)
    playlist_map = {playlist.title: playlist for playlist in playlists}

    if playlist_title not in playlist_map:
        click.echo(f"Playlist '{playlist_title}' not found on Plex server.")
        return

    playlist = playlist_map[playlist_title]
    click.echo(f"Playlist: {playlist.title}")
    for item in playlist.items():
        if item.type == 'track':
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


@cli.command()
def list_playlists():
    """List all playlists, showing both Plex playlist name and YouTube playlist ID."""
    playlists = session.query(YouTubePlaylist).all()
    for playlist in playlists:
        plex_playlist = session.query(PlexPlaylist).filter_by(id=playlist.plex_playlist_id).first()
        click.echo(f"Plex Playlist: {plex_playlist.title}, YouTube Playlist ID: {playlist.playlist_id}")


if __name__ == "__main__":
    cli()

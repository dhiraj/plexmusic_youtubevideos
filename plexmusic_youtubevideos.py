import os
import json
from dataclasses import dataclass
from typing import List
from urllib.parse import quote

import click
from plexapi.server import PlexServer
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from pytube import Search
from ytmusicapi import YTMusic

# File paths to store authentication tokens and config
CONFIG_FILE = os.path.expanduser("~/.plex_youtube_sync_config.json")
YOUTUBE_CREDENTIALS_FILE = 'oauth.json'
DATABASE_FILE = os.path.expanduser("~/.plex_youtube_sync.db")

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
    if os.path.exists(YOUTUBE_CREDENTIALS_FILE):
        ytmusic = YTMusic(YOUTUBE_CREDENTIALS_FILE)
    else:
        click.echo(f"Please provide a valid YouTube credentials file at {YOUTUBE_CREDENTIALS_FILE}")
        exit(1)
    return ytmusic


def fetch_plex_playlists(plex_url, plex_token):
    plex = PlexServer(plex_url, plex_token)
    return plex.playlists()


def search_youtube_videos(query):
    search = Search(query)
    return search.results


def get_existing_video_id(track_id):
    record = session.query(PlexPlaylistItem).filter_by(track_id=track_id).first()
    return record.video_id if record else None


def save_playlistitem(plex_playlist_id, track_id):
    record = session.query(PlexPlaylistItem).filter(PlexPlaylistItem.track_id == track_id, PlexPlaylistItem.playlist_id == plex_playlist_id).first()
    if not record:
        plex_item = PlexPlaylistItem(
            playlist_id=plex_playlist_id,
            track_id=track_id,
        )
        session.add(plex_item)
        session.commit()
        return True
    return False


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
    response = youtube_service.create_playlist(title=title,
                                               description=f"A playlist created based on the Plex playlist: {title}")
    return response


def add_video_to_youtube_playlist(youtube_service, playlist_id, video_id):
    youtube_service.add_playlist_items(playlist_id, [video_id])


def sync_local_to_youtube(youtube_service):
    """Sync local playlist state to YouTube."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    youtube_service = authenticate_youtube()

    for plex_playlist in session.query(PlexPlaylist).all():
        title = plex_playlist.title
        if title == '❤️ Tracks':
            continue
        yt_playlist = session.query(YouTubePlaylist).filter_by(playlist_title=title).first()

        if not yt_playlist:
            # Create new YouTube playlist
            yt_playlist_id = create_youtube_playlist(youtube_service, title)
            new_yt_playlist = YouTubePlaylist(
                plex_playlist_id=plex_playlist.id,
                playlist_id=yt_playlist_id,
                playlist_title=title
            )
            session.add(new_yt_playlist)
            session.commit()
            click.echo(f"Created YouTube playlist for '{title}': {yt_playlist_id}")
        else:
            yt_playlist_id = yt_playlist.playlist_id
            #Clear out existing items in the YouTube playlist
            response = youtube_service.get_playlist(
                playlistId=yt_playlist.playlist_id,
                limit=None,
            )
            videos_to_remove = [{'videoId':item['videoId'],'setVideoId':item['setVideoId']} for item in response['tracks']]
            if len(videos_to_remove) > 0:
                response = youtube_service.remove_playlist_items(playlistId=yt_playlist.playlist_id,videos=videos_to_remove)
                click.echo(f"{response}")
            else:
                click.echo(f"Playlist {yt_playlist.playlist_id} exists but is EMPTY!?")


        # Fetch corresponding Plex playlist items from the local database
        plex_items = session.query(PlexTrack)\
            .filter(PlexTrack.video_id != None, PlexPlaylistItem.playlist_id == plex_playlist.id)\
            .join(PlexPlaylistItem,PlexTrack.track_id == PlexPlaylistItem.track_id)\
            .all()
        add_ids = [item.video_id for item in plex_items]
        if len(add_ids) > 0:
            response = youtube_service.add_playlist_items(playlistId=yt_playlist_id, videoIds=add_ids)
            click.echo(f"Added {len(add_ids)} videos to {plex_playlist.title}")
            # incrementer = 50
            # start_at = -incrementer
            # while start_at < len(add_ids):
            #     start_at += incrementer
            #     sliced = add_ids[slice(start_at,start_at+incrementer)]
            #     if len(sliced) > 0:
            #         response = youtube_service.add_playlist_items(playlistId=yt_playlist_id, videoIds=sliced)
            #         click.echo(f"Added {len(sliced)} to {plex_playlist.title}")
            #     else:
            #         break

        # Re-add all items to the YouTube playlist
        # with click.progressbar(plex_items) as items:
        #     for item in items:
        #         session.add(YouTubePlaylistItem(youtube_playlist_id=yt_playlist_id, video_id=item.video_id))
        #     session.commit()

    click.echo("All YouTube playlists have been synchronized.")


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
@click.option('--update-only', is_flag=True, help="Only update existing matches without presenting new matches.")
def match(update_only):
    """Match specified Plex playlists with YouTube music videos and save the matches."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    plex_url = config["plex_url"]
    plex_token = config["plex_token"]
    youtube_service = authenticate_youtube()

    playlists = fetch_plex_playlists(plex_url, plex_token)
    playlist_map = {playlist.title: playlist for playlist in playlists}

    for title in playlist_map.keys():
        if title == '❤️ Tracks':
            continue
        playlist = playlist_map[title]

        plex_playlist = session.query(PlexPlaylist).filter_by(title=title).first()
        if not plex_playlist:
            plex_playlist = PlexPlaylist(title=title, playlist_id=playlist.guid)
            session.add(plex_playlist)
            session.commit()
            click.echo(f"Plex Playlist '{title}' not found in local database, created.")

        click.echo(f"Playlist: {playlist.title}")
        existing_track_ids = session.scalars(session.query(PlexTrack.track_id)).all()

        for track in playlist.items():
            if track.type != 'track':
                continue

            if track.ratingKey in existing_track_ids:
                if save_playlistitem(plex_playlist.id, track.ratingKey):
                    click.echo(f"Saved pre-matched Track: {track.title}, Artist: {track.artist().title}, Album: {track.album().title}, id: {track.ratingKey}")
                continue

            if update_only:
                # Skip the tracks without existing matches when update-only is specified
                continue

            # Default search with artist and song title
            query = f"{track.artist().title} - {track.title} - {track.album().title}"
            click.echo(f"Track: {track.title}, Artist: {track.artist().title}, Album: {track.album().title}, id: {track.ratingKey}, https://www.youtube.com/results?search_query={quote(query)}")

            results = search_youtube_videos(query)
            if results:
                click.echo("1. Enter custom YouTube video ID")
                click.echo("2. Mark as no match")
                for i, result in enumerate(results, 3):
                    click.echo(f"{i}. {result.title} (https://www.youtube.com/watch?v={result.video_id})")

                while True:
                    choice = click.prompt("Select an option", type=int, default=3)
                    if choice == 1:
                        video_id = click.prompt("Enter the YouTube video ID", type=str)
                        save_track(track.ratingKey, track.title, track.artist().title, track.album().title, video_id)
                        save_playlistitem(plex_playlist.id, track.ratingKey)
                        break
                    elif choice == 2:
                        mark_no_match(track.ratingKey, track.title, track.artist().title, track.album().title)
                        break
                    elif 3 <= choice < 3 + len(results):
                        selected = results[choice - 3]
                        save_track(track.ratingKey, track.title, track.artist().title, track.album().title,
                                   selected.video_id)
                        save_playlistitem(plex_playlist.id, track.ratingKey)
                        break


@cli.command()
def create():
    """Create YouTube playlists and add matched videos."""
    config = load_config()
    if not config:
        click.echo("No configuration found. Please run 'configure' command first.")
        return

    youtube_service = authenticate_youtube()
    playlist_titles = config["playlists"]

    for title in playlist_titles:
        plex_playlist = session.query(PlexPlaylist).filter_by(title=title).first()
        if not plex_playlist:
            click.echo(f"Plex Playlist '{title}' not found in local database.")
            continue

        # Check if YouTube playlist already exists
        yt_playlist = session.query(YouTubePlaylist).filter_by(plex_playlist_id=plex_playlist.id).first()
        if yt_playlist:
            click.echo(f"YouTube playlist for '{title}' already exists: {yt_playlist.playlist_id}")
            continue

        # Create new YouTube playlist
        yt_playlist_id = create_youtube_playlist(youtube_service, title)
        new_yt_playlist = YouTubePlaylist(
            plex_playlist_id=plex_playlist.id,
            playlist_id=yt_playlist_id,
            playlist_title=title
        )
        session.add(new_yt_playlist)
        session.commit()


@cli.command()
def sync():
    """Synchronize the local database state to YouTube playlists."""
    youtube_service = authenticate_youtube()
    sync_local_to_youtube(youtube_service)


if __name__ == "__main__":
    cli()

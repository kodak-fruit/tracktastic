#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
import getpass
import json
import logging
import math
import random
import subprocess as sp
import textwrap
import time
from collections import defaultdict
from dataclasses import InitVar, dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, ClassVar, List, Optional, Set

import psutil
import tomli
import tqdm
from appscript import CommandError, app, its, k
from colorlog import ColoredFormatter

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CONFIG_PATH = SCRIPT_DIR / "config.toml"

NOW = dt.datetime.now()
ONE_YEAR = dt.timedelta(days=365.25)
ONE_DAY = dt.timedelta(days=1)
ONE_HOUR = dt.timedelta(hours=1)
ONE_MIN = dt.timedelta(minutes=1)

MEDIAN_SONG_LENGTH = dt.timedelta(minutes=3, seconds=45)
DEFAULT_SCORE_BASE = 3.0
TARGET_MEDIAN_SCORE = 1.0

LOG_PATH = SCRIPT_DIR / "log.txt"

PROGRESS_INTERVAL = 2.5

logger = logging.getLogger(__name__)


class FavoriteStatus(Enum):
    FAVORITED = auto()
    DISLIKED = auto()
    NONE = auto()


@dataclass
class Track:
    api: InitVar[Any]

    _api: Any = field(init=False)

    name: str = field(init=False)
    track_artist: str = field(init=False)
    album: str = field(init=False)
    album_artist: str = field(init=False)
    genre: str = field(init=False)
    year: int = field(init=False)
    track_number: int = field(init=False)
    play_count: int = field(init=False)
    skip_count: int = field(init=False)
    duration: dt.timedelta = field(init=False)
    date_added: dt.datetime = field(init=False)
    rating: int = field(init=False)
    dbid: int = field(init=False)
    shuffleable: bool = field(init=False)

    duration_since_added: dt.timedelta = field(init=False)
    play_rate: float = field(init=False)
    listen_rate: dt.timedelta = field(init=False)
    score: float = field(init=False)

    playlists: List[str] = field(default_factory=list)

    # class variables
    median_song_length: ClassVar[dt.timedelta] = MEDIAN_SONG_LENGTH
    score_base: ClassVar[float] = DEFAULT_SCORE_BASE
    downranked_artists: ClassVar[Set[str]] = set()
    downranked_genres: ClassVar[Set[str]] = set()

    def __post_init__(self, api):
        self._api = api
        self.name = api.name() or "Unknown Track"
        self.track_artist = api.artist() or "Unknown Track Artist"
        self.album = api.album() or "Unknown Album"
        self.album_artist = api.album_artist() or "Unknown Album Artist"
        self.genre = api.genre() or "Unknown Genre"
        self.year = api.year()
        self.track_number = api.track_number()
        self.play_count = api.played_count()
        self.skip_count = api.skipped_count()
        self.duration = dt.timedelta(seconds=api.duration())
        self.date_added = api.date_added()
        self.rating = api.rating()
        self.dbid = api.database_ID()
        self.shuffleable = api.shufflable()
        if not self.shuffleable:
            logger.warning(f"{self.display()} is not shuffleable")

        net_play_count = self.play_count - self.skip_count
        time_spent_listening = self.play_count * self.duration
        self.duration_since_added = NOW - self.date_added

        years_since_added = self.duration_since_added / ONE_YEAR
        self.play_rate = net_play_count / years_since_added
        self.listen_rate = time_spent_listening / years_since_added
        norm_listen_rate = self.listen_rate / self.median_song_length
        rate_avg = (self.play_rate + norm_listen_rate) / 2
        self.score = math.log(1 + rate_avg, self.score_base)

    @classmethod
    def set_down_ranked_arists(cls, downranked_artists: List[str]) -> None:
        cls.downranked_artists = {x.casefold() for x in downranked_artists}

    @classmethod
    def set_down_ranked_genres(cls, downranked_genres: List[str]) -> None:
        cls.downranked_genres = {x.casefold() for x in downranked_genres}

    def display(self) -> str:
        return f"{self.name} - {self.track_artist}"

    def to_dict(self):
        return {
            "name": self.name,
            "track_artist": self.track_artist,
            "album": self.album,
            "album_artist": self.album_artist,
            "genre": self.genre,
            "year": self.year,
            "track_number": self.track_number,
            "play_count": self.play_count,
            "skip_count": self.skip_count,
            "duration": self.duration / ONE_MIN,
            "rating": self.rating,
            "date_added": self.date_added.isoformat(),
            "duration_since_added": self.duration_since_added / ONE_YEAR,
            "play_rate": self.play_rate,
            "listen_rate": self.listen_rate / ONE_MIN,
            "score": self.score,
            "playlists": sorted(self.playlists),
            "dbid": self.dbid,
        }

    def is_downranked(self) -> bool:
        return (
            self.genre.casefold() in self.downranked_genres
            or self.album_artist.casefold() in self.downranked_artists
            or any(
                artist
                for artist in self.downranked_artists
                if artist in self.track_artist.casefold()
            )
        )

    def get_all_playlists(self) -> List[Any]:
        return self._api.playlists.get()

    def set_rating(self, rating: int) -> None:
        assert 0 <= rating <= 100
        self._api.rating.set(rating)
        self.rating = rating

    def set_favorite_status(self, status: FavoriteStatus) -> None:
        if status == FavoriteStatus.FAVORITED:
            if self._api.favorited.get() is False:
                logger.info(f"💗 {self.display()}")
                self._api.favorited.set(True)
        elif status == FavoriteStatus.DISLIKED:
            if self._api.disliked.get() is False:
                logger.info(f"😾 {self.display()}")
                self._api.disliked.set(True)
        elif status == FavoriteStatus.NONE:
            if self._api.favorited.get() is True:
                logger.info(f"💔 {self.display()}")
                self._api.favorited.set(False)
            if self._api.disliked.get() is True:
                logger.info(f"🫤 {self.display()}")
                self._api.disliked.set(False)
        else:
            raise ValueError(f"Invalid favorite status: {status}")

    def add_to_playlist(self, playlist: Any) -> None:
        self._api.duplicate(to=playlist)


@dataclass
class MetadataStats:
    total: float = field(init=False)
    median_total: float = field(init=False)
    avg: float = field(init=False)
    median: float = field(init=False)
    max: float = field(init=False)
    min: float = field(init=False)
    std_dev: float = field(init=False)
    mode: float = field(init=False)

    values: InitVar[List[float]]
    to_display: Callable[[float], str] = str
    to_json: Callable[[float], Any] = lambda x: x

    def __post_init__(self, values):
        count = len(values)
        assert count > 0
        value_type = type(values[0])
        self.total = sum(values, start=value_type())
        self.avg = self.total / count
        sorted_values = sorted(values)
        half = count // 2
        if count & 1:
            self.median = sorted_values[half]
        else:
            self.median = (sorted_values[half - 1] + sorted_values[half]) / 2
        self.median_total = self.median * count
        self.max = max(values)
        self.min = min(values)
        self.std_dev = (sum((x - self.avg) ** 2 for x in values) / count) ** 0.5
        self.mode = max(set(values), key=values.count)

    def __str__(self):
        return "\n".join(
            [
                f"Total: {self.to_display(self.total)}",
                f"Avg: {self.to_display(self.avg)}",
                f"Median: {self.to_display(self.median)}",
                f"Max: {self.to_display(self.max)}",
                f"Min: {self.to_display(self.min)}",
            ]
        )

    def to_dict(self):
        return {
            "total": self.to_json(self.total),
            "total_median": self.to_json(self.median_total),
            "avg": self.to_json(self.avg),
            "median": self.to_json(self.median),
            "max": self.to_json(self.max),
            "min": self.to_json(self.min),
            "std_dev": self.to_json(self.std_dev),
            "mode": self.to_json(self.mode),
        }


@dataclass
class TrackCollection:
    name: str

    count: int = field(init=False)

    score: MetadataStats = field(init=False)
    play_rate: MetadataStats = field(init=False)
    listen_rate: MetadataStats = field(init=False)
    duration: MetadataStats = field(init=False)
    play_count: MetadataStats = field(init=False)
    skip_count: MetadataStats = field(init=False)
    rating: MetadataStats = field(init=False)
    year: MetadataStats = field(init=False)
    track_number: MetadataStats = field(init=False)
    duration_since_added: MetadataStats = field(init=False)
    num_playlists: MetadataStats = field(init=False)

    tracks: InitVar[List[Track]]

    def __post_init__(self, tracks):
        self.count = len(tracks)
        self.score = MetadataStats(
            [track.score for track in tracks],
            to_display=lambda x: f"{x:.2f}",
        )
        self.play_rate = MetadataStats(
            [track.play_rate for track in tracks],
            to_display=lambda x: f"{x:.2f} plays/year",
        )
        self.listen_rate = MetadataStats(
            [track.listen_rate.total_seconds() for track in tracks],
            to_json=lambda x: x / 60,  # seconds to min
            to_display=lambda x: f"{dt.timedelta(seconds=x)} per year",
        )
        self.duration = MetadataStats(
            values=[track.duration.total_seconds() for track in tracks],
            to_json=lambda x: x / 60,
            to_display=lambda x: str(dt.timedelta(seconds=x)),
        )
        self.play_count = MetadataStats(
            values=[track.play_count for track in tracks],
            to_display=lambda x: f"{x:.1f} plays",
        )
        self.skip_count = MetadataStats(
            values=[track.skip_count for track in tracks],
            to_display=lambda x: f"{x:.1f} skips",
        )
        self.rating = MetadataStats(
            values=[track.rating for track in tracks],
            to_display=lambda x: f"{x:.1f}",
        )
        self.year = MetadataStats(
            values=[track.year for track in tracks],
        )
        self.track_number = MetadataStats(
            values=[track.track_number for track in tracks],
        )
        self.duration_since_added = MetadataStats(
            values=[track.duration_since_added.total_seconds() for track in tracks],
            to_json=lambda x: x / 60 / 60 / 24 / 365.25,  # seconds to years
            to_display=lambda x: str(dt.timedelta(seconds=x)),
        )
        self.num_playlists = MetadataStats(
            values=[len(track.playlists) for track in tracks],
            to_display=lambda x: f"{x:.1f} playlists",
        )

    def __str__(self):
        return "\n".join(
            [
                f"{self.name}:",
                f"  Count: {self.count}",
            ]
            + [
                f"  {name}:\n{textwrap.indent(str(metadata), '    ')}"
                for name, metadata in {
                    "Score": self.score,
                    "Play Rate": self.play_rate,
                    "Listen Rate": self.listen_rate,
                    "Duration": self.duration,
                    "Play Count": self.play_count,
                    # "Rating": self.rating,
                }.items()
            ]
        )

    def to_dict(self):
        return {
            "name": self.name,
            "count": self.count,
            "score": self.score.to_dict(),
            "play_rate": self.play_rate.to_dict(),
            "listen_rate": self.listen_rate.to_dict(),
            "duration": self.duration.to_dict(),
            "play_count": self.play_count.to_dict(),
            "skip_count": self.skip_count.to_dict(),
            "rating": self.rating.to_dict(),
            "year": self.year.to_dict(),
            "track_number": self.track_number.to_dict(),
            "duration_since_added": self.duration_since_added.to_dict(),
            "num_playlists": self.num_playlists.to_dict(),
        }


@dataclass
class Config:
    # i'm a monster

    @dataclass
    class Sync:
        enabled: bool
        iphone_name: Optional[str]

    sync: Sync

    @dataclass
    class Playlists:
        @dataclass
        class Input:
            source_playlist: str
            subset_playlist: Optional[str]
            save_stats: bool

        input: Input

        @dataclass
        class Output:
            force_update: bool
            update_every: Optional[dt.timedelta]
            remove_only: bool

            @dataclass
            class Shuffle:
                enabled: bool
                name: Optional[str]
                downranked_genres: List[str]
                downranked_artists: List[str]

            shuffle: Shuffle

        output: Output

    playlists: Playlists

    @dataclass
    class AlbumRatings:
        clear: bool

    album_ratings: AlbumRatings

    @dataclass
    class TrackRatings:
        update: bool

    track_ratings: TrackRatings

    @dataclass
    class Favorites:
        update: bool
        top_percent: Optional[float]

    favorites: Favorites

    @dataclass
    class Collections:
        save_stats: bool
        playlist_folder: Optional[str]

    collections: Collections

    # or is the real monster python

    @classmethod
    def from_toml(cls, path: Path) -> Config:
        with path.open("rb") as file:
            data = tomli.load(file)
        return cls(
            sync=cls.Sync(
                enabled=data["sync"]["enabled"],
                iphone_name=data["sync"].get("iphone_name"),
            ),
            playlists=cls.Playlists(
                input=cls.Playlists.Input(
                    source_playlist=data["playlists"]["input"]["source_playlist"],
                    subset_playlist=data["playlists"]["input"].get("subset_playlist"),
                    save_stats=data["playlists"]["input"]["save_stats"],
                ),
                output=cls.Playlists.Output(
                    force_update=data["playlists"]["output"]["force_update"],
                    update_every=(
                        dt.timedelta(**update_every)
                        if (
                            update_every := data["playlists"]["output"].get(
                                "update_every"
                            )
                        )
                        is not None
                        else None
                    ),
                    remove_only=data["playlists"]["output"]["remove_only"],
                    shuffle=cls.Playlists.Output.Shuffle(
                        enabled=data["playlists"]["output"]["shuffle"]["enabled"],
                        name=data["playlists"]["output"]["shuffle"].get("name"),
                        downranked_genres=data["playlists"]["output"]["shuffle"].get(
                            "downranked_genres", []
                        ),
                        downranked_artists=data["playlists"]["output"]["shuffle"].get(
                            "downranked_artists", []
                        ),
                    ),
                ),
            ),
            album_ratings=cls.AlbumRatings(clear=data["album_ratings"]["clear"]),
            track_ratings=cls.TrackRatings(update=data["track_ratings"]["update"]),
            favorites=cls.Favorites(
                update=data["favorites"]["update"],
                top_percent=data["favorites"].get("top_percent"),
            ),
            collections=cls.Collections(
                save_stats=data["collections"]["save_stats"],
                playlist_folder=data["collections"].get("playlist_folder"),
            ),
        )


def init_logger(level: int) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter("%(log_color)s[%(levelname)s]%(reset)s %(message)s")
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
    # also save to log.txt
    root.debug(f"Logging to {LOG_PATH}")
    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(file_handler)


def update_track_params(subdir_name: str):
    totals_path = OUTPUT_DIR / subdir_name / "totals.json"
    if totals_path.exists():
        with totals_path.open("r", encoding="utf-8") as total_json_file:
            total_data = json.load(total_json_file)
        # update median song length
        median_duration_min = total_data[0]["duration"]["median"]
        median_duration = dt.timedelta(minutes=median_duration_min)
        Track.median_song_length = median_duration
        # update score base so that avg score is equal to target
        if TARGET_MEDIAN_SCORE is not None:
            avg_play_rate = total_data[0]["play_rate"]["median"]
            listen_rate = total_data[0]["listen_rate"]["median"]
            norm_listen_rate = listen_rate / median_duration_min
            rate_avg = (avg_play_rate + norm_listen_rate) / 2
            if TARGET_MEDIAN_SCORE == 1.0:
                n = 1 + rate_avg
            else:
                n = (1 + rate_avg) ** (1 / TARGET_MEDIAN_SCORE)
            Track.score_base = n
    else:
        logger.warning(f"Could not find {totals_path}")
    logger.info(f"Median song length: {Track.median_song_length}")
    logger.info(f"Score base: {Track.score_base:.3f}")


def update_track_ratings(tracks: List[Track]) -> None:
    logger.info("Updating track ratings")
    num_bins = min(100, len(tracks))
    bin_size = len(tracks) / num_bins
    # TODO: debug
    logger.info(f"num bins: {num_bins}, bin size: {bin_size}")
    for i, track in enumerate(tracks):
        if track.play_count > 0:
            rating = 100 - int(i // bin_size)
        else:
            rating = 0
        track.set_rating(rating)


def update_favorites(tracks: List[Track], fav_percent: float) -> None:
    logger.info("Updating favorites")
    fav_limit = round(len(tracks) * (fav_percent / 100))
    for i, track in enumerate(tracks):
        if i < fav_limit:
            favorited = FavoriteStatus.FAVORITED
        else:
            favorited = FavoriteStatus.NONE
        track.set_favorite_status(favorited)


def weighted_shuffle(tracks: List[Track]) -> List[Track]:
    logger.info("Shuffling tracks")

    # TODO: better weighted shuffle? random.sample?
    def weight(track: Track) -> float:
        if track.is_downranked():
            logger.debug(f"Downranking {track.display()}")
            # min(rand, rand) is linear towards 0
            # rand * rand is higher near 0
            # rand ** 2 is much near 0
            return min(random.random(), random.random()) * track.score

        return random.random() * track.score

    return sorted(
        tracks,
        key=weight,
        reverse=True,
    )


def process_source(music_app, playlist_name: str):
    logger.info(f"Retrieving tracks from {playlist_name!r}")
    source_tracks = music_app.playlists[playlist_name].tracks()

    logger.info(f"Processing tracks ({len(source_tracks)})")
    tracks = []
    for track in tqdm.tqdm(source_tracks, unit="track", mininterval=PROGRESS_INTERVAL):
        tracks.append(Track(api=track))
    return tracks


def attach_playlists(music_app, tracks, playlist_folder: str) -> None:
    logger.info("Retrieving playlists")
    folders_to_check = {music_app.playlists[playlist_folder].get()}
    folder_playlists = set()
    while folders_to_check:
        folder = folders_to_check.pop()
        for playlist in music_app.playlists.get():
            parent = playlist.parent
            if not parent.exists():
                continue
            if parent.get() != folder:
                continue
            kind = playlist.special_kind.get()
            if kind == k.folder:
                folders_to_check.add(playlist)
            elif kind == k.none:
                folder_playlists.add(playlist)
    logging.info(f"Attaching playlists ({len(folder_playlists)}) to tracks")
    for track in tqdm.tqdm(tracks, unit="track", mininterval=PROGRESS_INTERVAL):
        track.playlists.extend(
            track_playlist.name()
            for track_playlist in track.get_all_playlists()
            if track_playlist in folder_playlists
        )


def update_playlist(*, music_app: Any, source_tracks, playlist_name: str) -> None:
    playlist = music_app.playlists[playlist_name]
    if not playlist.exists():
        logger.info(f"Creating playlist {playlist_name!r}")
        music_app.make(
            new=k.playlist,
            with_properties={k.name: playlist_name},
        )

    logger.info(f"Clearing existing tracks from {playlist_name!r}")
    playlist.tracks.delete()

    logger.info(f"Adding tracks to {playlist_name!r}")
    # use tqdm to show progress
    for track in tqdm.tqdm(source_tracks, unit="track", mininterval=PROGRESS_INTERVAL):
        track.add_to_playlist(playlist)


def remove_unsynced_tracks(music_app, synced_tracks, playlist_name: str) -> None:
    playlist = music_app.playlists[playlist_name]
    if not playlist.exists():
        logger.info(f"Playlist {playlist_name!r} does not exist")
        return

    synced_dbids = {track.dbid for track in synced_tracks}
    unsynced_tracks = [
        track for track in playlist.tracks() if track.database_ID() not in synced_dbids
    ]

    logger.info(
        f"Removing {len(unsynced_tracks)} unsynced tracks from {playlist_name!r}"
    )
    for track in unsynced_tracks:
        track.delete()


def save_track_data(tracks: List[Track], subdir_name: str, show_diff: bool) -> None:
    save_data(
        data=[track.to_dict() for track in tracks],
        subdir_name=subdir_name,
        name="tracks",
        show_diff=show_diff,
        key=lambda x: x["dbid"],
        sentinel=lambda x: x["play_count"] + x["skip_count"],
        pretty=lambda x: f"{x['name']} - {x['track_artist']}",
    )


def save_collection_stats(tracks: List[Track], subdir_name: str):
    album_artists = defaultdict(list)
    track_artists = defaultdict(list)
    albums = defaultdict(list)
    genres = defaultdict(list)
    years = defaultdict(list)
    track_numbers = defaultdict(list)
    playlists = defaultdict(list)
    logger.info("Grouping tracks")
    for track in tracks:
        album_artists[track.album_artist].append(track)
        track_artists[track.track_artist].append(track)
        albums[f"{track.album} ({track.album_artist})"].append(track)
        genres[track.genre].append(track)
        years[str(track.year)].append(track)
        track_numbers[str(track.track_number)].append(track)
        for playlist in track.playlists:
            playlists[playlist].append(track)

    collections = {
        "album_artists": album_artists,
        "track_artists": track_artists,
        "albums": albums,
        "genres": genres,
        "years": years,
        "track_numbers": track_numbers,
        "playlists": playlists,
    }
    for collection_name, collection in collections.items():
        logger.info(f"Calculating stats for {collection_name} ({len(collection)})")
        track_collection = []
        for group_name, items in collection.items():
            if not items:
                continue
            track_collection.append(TrackCollection(name=group_name, tracks=items))
        if not track_collection:
            logger.warning(f"No data for {collection_name}")
            continue
        stats = sorted(
            (x.to_dict() for x in track_collection),
            key=lambda x: x["score"]["avg"],
            reverse=True,
        )
        save_data(
            data=stats,
            subdir_name=subdir_name,
            name=collection_name,
            show_diff=True,
            key=lambda x: x["name"],
            sentinel=lambda x: x["play_count"]["total"] + x["skip_count"]["total"],
            pretty=None,
        )


def save_total_stats(tracks, subdir_name: str):
    source = TrackCollection(name=subdir_name, tracks=tracks)
    save_data(
        data=[source.to_dict()],
        subdir_name=subdir_name,
        name="totals",
        show_diff=False,
        key=None,
        sentinel=None,
        pretty=None,
    )
    logger.info(source)


def save_data(
    *,
    data,
    subdir_name: str,
    name: str,
    show_diff: bool,
    key: Optional[Any],
    sentinel: Optional[Any],
    pretty: Optional[Any],
) -> None:
    json_subdir = OUTPUT_DIR / subdir_name
    json_subdir.mkdir(parents=True, exist_ok=True)
    json_path = json_subdir / f"{name}.json"

    # grab existing file for later if it exists
    existing_data: Optional[List[dict]]
    if show_diff and json_path.exists():
        with json_path.open("r", encoding="utf-8") as json_file:
            existing_data = json.load(json_file)
    else:
        existing_data = None

    data = [{"index": i, **item} for i, item in enumerate(data)]
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=4)
    logger.debug(f"Saved {json_path}")

    if show_diff and existing_data is not None and data != existing_data:
        assert key is not None
        assert sentinel is not None
        prev_items_by_key = {key(item): item for item in existing_data}
        diff_list = []
        total_diff = 0
        for item in data:
            prev_item = prev_items_by_key.get(key(item))
            pretty_name = pretty(item) if pretty else key(item)
            if prev_item is None:
                diff_list.append(f"  ADD {item['index']: >5}. {pretty_name}")
            elif (diff := item["index"] - prev_item["index"]) and sentinel(
                item
            ) != sentinel(prev_item):
                abs_diff = abs(diff)
                total_diff += abs_diff
                diff_list.append(f"{-diff: >+5} {item['index']: >5}. {pretty_name}")
        current_keys = {key(item) for item in data}
        for item in existing_data:
            if key(item) not in current_keys:
                pretty_name = pretty(item) if pretty else key(item)
                diff_list.append(f"  DEL {item['index']: >5}. {pretty_name}")
        if diff_list:
            logger.info(f"{name} diff:")
            for line in diff_list:
                logger.info(line)
        logger.debug(f"Total {name} diff: {total_diff}")


def print_ui_tree(root: Any):
    root = root.get()

    def print_tree(node, indent):
        for action in node.actions.get():
            print(f"{' ' * indent}[{action.name()}]")
        for child in node.UI_elements.get():
            name = str(child)
            name = name.replace(str(node), "")
            name = name.replace(str(root), "")
            print(f"{'.' * indent}{name}")
            print_tree(child, indent + 1)

    print(str(root))
    print_tree(root, 0)


def open_new_device_window(finder: Any, device_name: str) -> Any:
    logger.info("Opening new window for device")
    # open a new window, or steal an already open window
    home = getpass.getuser()
    open_windows = finder.windows[its.name == home].get()
    if open_windows:
        device_window = open_windows[0]
    else:
        menu_bar = finder.menu_bars[1]
        file_menu = menu_bar.menu_bar_items["File"].menus[1]
        new_window_item = file_menu.menu_items["New Finder Window"]
        new_window_item.click()
        wait_for_ui(
            lambda: finder.windows[  # pylint: disable=unnecessary-lambda
                its.name == home
            ].get(),
            timeout=dt.timedelta(seconds=30),
        )
        device_window = finder.windows[home]
    sidebar = device_window.splitter_groups[1].scroll_areas[1].outlines[1]
    device_rows = [
        row
        for row in sidebar.rows()
        for element in row.UI_elements()
        if element.name() == device_name
    ]
    if not device_rows:
        row_names = [
            name
            for row in sidebar.rows()
            if (name := row.UI_elements[1].name()) != k.missing_value
        ]
        logger.error(
            f"Could not find {device_name} in Finder sidebar.\n"
            "If you can see the device in the sidebar, then copy-and-paste "
            f"the exact name from below into the {CONFIG_PATH.name}:\n"
            + "\n".join(repr(name) for name in row_names)
        )
        # print_ui_tree(sidebar)
        raise RuntimeError(f"{device_name} not found in Finder sidebar")
    item = device_rows[0].UI_elements[1]
    item.actions["AXOpen"].perform()
    wait_for_ui(
        lambda: finder.windows[  # pylint: disable=unnecessary-lambda
            its.name == device_name
        ].get(),
        timeout=dt.timedelta(seconds=30),
    )
    return finder.windows[device_name]


def wait_for_ui(cond, *, timeout: dt.timedelta) -> None:
    start = dt.datetime.now()
    while not cond():
        if dt.datetime.now() - start > timeout:
            raise TimeoutError("Timed out waiting for UI condition")
        time.sleep(1)


def sync_device(device_name: str) -> bool:
    try:
        logger.info(f"Syncing {device_name}")
        # Ensure Finder is active
        system_events = app("System Events")
        finder = system_events.processes["Finder"]
        finder.activate()

        # open the device window
        open_windows = finder.windows[its.name == device_name].get()
        if open_windows:
            device_window = open_windows[0]
        else:
            device_window = open_new_device_window(finder, device_name)
        devices_ui = device_window.splitter_groups[1].splitter_groups[1]

        # print_ui_tree(devices_ui)

        # start a sync
        if butts := devices_ui.buttons[its.name == "Sync"].get():
            butts[0].click()
            logger.info("Sync started")
        else:
            logger.warning("Sync already in progress")

        # wait for sync to finish
        wait_for_ui(
            lambda: (butts := devices_ui.buttons[its.name == "Sync"].get())
            and butts[0].enabled(),
            timeout=dt.timedelta(minutes=10),
        )
        logger.info("Sync complete")
        return True
    except CommandError:
        logger.exception("Error syncing device")
        return False


def wait_for_amplibraryagent():
    logger.info("Waiting for AMPLibraryAgent to finish updating library")
    process_name = "AMPLibraryAgent"
    cmd = ["pgrep", "-x", process_name]
    output = sp.check_output(cmd, universal_newlines=True)
    pid = int(output.strip())
    proc = psutil.Process(pid)
    cpu_interval = 10
    cpu_threshold = 10
    while proc.cpu_percent(interval=cpu_interval) > cpu_threshold:
        time.sleep(0)

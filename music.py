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
from typing import Any, Callable, ClassVar, Dict, List, Optional, Set

import numpy as np
import psutil
import tomli
import tqdm
from appscript import CommandError, app, its, k
from colorlog import ColoredFormatter

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CONFIG_PATH = SCRIPT_DIR / "config.toml"
LOG_PATH = OUTPUT_DIR / "log.txt"

# TODO: just use a sql database for stats w/ history, instead of json file snapshots
# TODO: last.fm playlists

NOW = dt.datetime.now()
ONE_YEAR = dt.timedelta(days=365.25)
ONE_MONTH = dt.timedelta(days=30)
ONE_DAY = dt.timedelta(days=1)
ONE_HOUR = dt.timedelta(hours=1)
ONE_MIN = dt.timedelta(minutes=1)

MEDIAN_SONG_LENGTH = dt.timedelta(minutes=3, seconds=48.1)
DEFAULT_SCORE_BASE = 1.591
TARGET_MEDIAN_SCORE = (5.0 + 0.05) / 2

PROGRESS_INTERVAL = 2.5

logger = logging.getLogger(__name__)


class FavoriteStatus(Enum):
    FAVORITED = auto()
    DISLIKED = auto()
    NONE = auto()


@dataclass
class Track:
    api: Optional[Any]

    name: str
    track_artist: str
    album: str
    album_artist: str
    genre: str
    year: int
    track_number: int
    play_count: int
    skip_count: int
    duration: dt.timedelta
    date_added: dt.datetime
    rating: int
    dbid: int
    compilation: bool
    size: int
    favorite: bool
    disliked: bool
    last_played: dt.datetime
    last_skipped: dt.datetime

    duration_since_last_played: dt.timedelta
    duration_since_last_skipped: dt.timedelta
    duration_since_added: dt.timedelta
    duration_since_last_interaction: dt.timedelta
    play_rate: float
    skip_rate: float
    listen_rate: dt.timedelta
    net_rate: float
    score: float
    time_between_plays: dt.timedelta
    overdue_duration: dt.timedelta
    overdue: float

    playlists: List[str]

    # class variables
    median_song_length: ClassVar[dt.timedelta] = MEDIAN_SONG_LENGTH
    score_base: ClassVar[float] = DEFAULT_SCORE_BASE
    downranked_artists: ClassVar[Set[str]] = set()
    downranked_genres: ClassVar[Set[str]] = set()
    loaded_playlists: ClassVar[Set[Any]] = set()

    @classmethod
    def set_down_ranked(cls, *, artists: List[str], genres: List[str]) -> None:
        cls.downranked_artists = {x.casefold() for x in artists}
        cls.downranked_genres = {x.casefold() for x in genres}

    def similarity_to(self, other: Track) -> float:
        """Returns a similarity score between 0 and 1"""
        sim_vec: List[float] = []
        # album
        sim_vec.append(self.album == other.album)
        # album artist
        sim_vec.append(self.album_artist == other.album_artist)
        # genre
        sim_vec.append(self.genre == other.genre)
        # closeness of year
        year_cutoff = 5
        year_diff = abs(self.year - other.year)
        year_sim = 1 - year_diff / year_cutoff if year_diff <= year_cutoff else 0
        sim_vec.append(year_sim)
        # added within 6 months of each other
        added_cutoff = 6 * ONE_MONTH
        added_diff = abs(self.date_added - other.date_added)
        added_sim = 1 - added_diff / added_cutoff if added_diff <= added_cutoff else 0
        sim_vec.append(added_sim)
        # last played on the same day
        sim_vec.append(self.last_played.date() == other.last_played.date())
        # overlapping playlists
        combined_playlists = set(self.playlists) | set(other.playlists)
        common_playlists = set(self.playlists) & set(other.playlists)
        playlist_sim = (
            len(common_playlists) / len(combined_playlists) if combined_playlists else 0
        )
        sim_vec.append(playlist_sim)
        # is compilation
        sim_vec.append(self.compilation == other.compilation)
        # duration
        duration_diff = abs(self.duration - other.duration)
        duration_sim = (
            1 - duration_diff / self.median_song_length
            if duration_diff <= self.median_song_length
            else 0
        )
        sim_vec.append(duration_sim)
        # similar score
        score_diff = abs(self.score - other.score)
        score_sim = (
            1 - score_diff / TARGET_MEDIAN_SCORE
            if score_diff < TARGET_MEDIAN_SCORE
            else 0
        )
        sim_vec.append(score_sim)
        # similar overdue
        overdue_diff = abs(self.overdue - other.overdue)
        overdue_sim = 1 - overdue_diff if overdue_diff <= 1 else 0
        sim_vec.append(overdue_sim)
        # upper / lowe case title
        sim_vec.append(
            self.name.islower() == other.name.islower()
            and self.name.isupper() == other.name.isupper()
        )
        # track number
        sim_vec.append(self.track_number == other.track_number)
        # TODO: has artwork

        # return sum(sim_vec) / len(sim_vec)

        alpha = self.score_base  # why not
        n = len(sim_vec)
        exp_sum = np.sum(np.exp(alpha * np.array(sim_vec)))
        max_exp_sum = n * np.exp(alpha)
        min_exp_sum = n * np.exp(0)

        # Normalize to the range [0, 1]
        normalized_value = (exp_sum - min_exp_sum) / (max_exp_sum - min_exp_sum)
        assert isinstance(normalized_value, float)
        return normalized_value

    def display(self) -> str:
        return f"{self.name} - {self.track_artist}"

    @classmethod
    def from_api(cls, api: Any) -> Track:
        name = api.name() or "Unknown Track"
        track_artist = api.artist() or "Unknown Track Artist"
        album = api.album() or "Unknown Album"
        album_artist = api.album_artist() or "Unknown Album Artist"
        genre = api.genre() or "Unknown Genre"
        year = api.year()
        track_number = api.track_number()
        play_count = api.played_count()
        skip_count = api.skipped_count()
        duration = dt.timedelta(seconds=api.duration())
        date_added = api.date_added()
        rating = api.rating()
        dbid = api.database_ID()
        shuffleable = api.shufflable()
        if not shuffleable:
            logger.warning(f"{name} - {track_artist} is not shuffleable")
        compilation = api.compilation()
        size = api.size()
        favorite = api.favorited()
        disliked = api.disliked()
        last_played = api.played_date()
        last_skipped = api.skipped_date()

        # TODO: just handle the optionals
        if last_played == k.missing_value:
            last_played = NOW - 100 * ONE_YEAR
        if last_skipped == k.missing_value:
            last_skipped = NOW - 100 * ONE_YEAR

        duration_since_last_played = NOW - last_played
        duration_since_last_skipped = NOW - last_skipped
        time_spent_listening = play_count * duration
        duration_since_added = NOW - date_added
        years_since_added = duration_since_added / ONE_YEAR

        duration_since_last_interaction = min(
            duration_since_last_played, duration_since_last_skipped
        )

        play_rate = play_count / years_since_added
        skip_rate = skip_count / years_since_added
        listen_rate = time_spent_listening / years_since_added
        norm_listen_rate = listen_rate / cls.median_song_length
        net_rate = (play_rate + norm_listen_rate - skip_rate) / 2
        if net_rate > 0:
            time_between_plays = ONE_YEAR / net_rate
        else:
            time_between_plays = 100 * ONE_YEAR
        overdue_duration = duration_since_last_interaction - time_between_plays
        overdue = overdue_duration / time_between_plays
        score = math.log(1 + net_rate, cls.score_base)

        # get the playlist objects
        playlists: List[str] = []
        if cls.loaded_playlists:
            playlists.extend(
                track_playlist.name()
                for track_playlist in api.playlists.get()
                if track_playlist in cls.loaded_playlists
            )

        return cls(
            api=api,
            name=name,
            track_artist=track_artist,
            album=album,
            album_artist=album_artist,
            genre=genre,
            year=year,
            track_number=track_number,
            play_count=play_count,
            skip_count=skip_count,
            duration=duration,
            date_added=date_added,
            rating=rating,
            dbid=dbid,
            compilation=compilation,
            size=size,
            favorite=favorite,
            disliked=disliked,
            last_played=last_played,
            last_skipped=last_skipped,
            duration_since_last_played=duration_since_last_played,
            duration_since_last_skipped=duration_since_last_skipped,
            duration_since_added=duration_since_added,
            duration_since_last_interaction=duration_since_last_interaction,
            play_rate=play_rate,
            skip_rate=skip_rate,
            listen_rate=listen_rate,
            net_rate=net_rate,
            score=score,
            time_between_plays=time_between_plays,
            overdue_duration=overdue_duration,
            overdue=overdue,
            playlists=playlists,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Track:
        return cls(
            api=None,
            name=data["name"],
            track_artist=data["track_artist"],
            album=data["album"],
            album_artist=data["album_artist"],
            genre=data["genre"],
            year=data["year"],
            track_number=data["track_number"],
            play_count=data["play_count"],
            skip_count=data["skip_count"],
            duration=dt.timedelta(minutes=data["duration"]),
            duration_since_added=dt.timedelta(days=data["years_since_added"] * 365.25),
            duration_since_last_played=dt.timedelta(
                days=data["days_since_last_played"]
            ),
            duration_since_last_skipped=dt.timedelta(
                days=data["days_since_last_skipped"]
            ),
            duration_since_last_interaction=dt.timedelta(
                days=data["days_since_last_interaction"]
            ),
            date_added=dt.datetime.fromisoformat(data["date_added"]),
            rating=int(data["rating"] * 20),
            score=data["score"],
            time_between_plays=dt.timedelta(days=data["days_between_plays"]),
            overdue_duration=dt.timedelta(days=data["days_overdue"]),
            overdue=data["overdue"],
            play_rate=data["play_rate"],
            skip_rate=data["skip_rate"],
            listen_rate=dt.timedelta(minutes=data["listen_rate"]),
            net_rate=data["net_rate"],
            dbid=data["dbid"],
            compilation=data["compilation"],
            size=data["size"],
            favorite=data["favorite"],
            disliked=data["disliked"],
            last_played=NOW - data["days_since_last_played"] * ONE_DAY,
            last_skipped=NOW - data["days_since_last_skipped"] * ONE_DAY,
            playlists=data["playlists"],
        )

    def to_dict(self) -> Dict[str, Any]:
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
            "rating": self.rating / 20,
            "date_added": self.date_added.isoformat(),
            "years_since_added": self.duration_since_added / ONE_YEAR,
            "days_since_last_played": self.duration_since_last_played / ONE_DAY,
            "days_since_last_skipped": self.duration_since_last_skipped / ONE_DAY,
            "days_since_last_interaction": (
                self.duration_since_last_interaction / ONE_DAY
            ),
            "play_rate": self.play_rate,
            "skip_rate": self.skip_rate,
            "listen_rate": self.listen_rate / ONE_MIN,
            "net_rate": self.net_rate,
            "days_between_plays": self.time_between_plays / ONE_DAY,
            "score": self.score,
            "days_overdue": self.overdue_duration / ONE_DAY,
            "overdue": self.overdue,
            "playlists": sorted(self.playlists),
            "compilation": self.compilation,
            "favorite": self.favorite,
            "disliked": self.disliked,
            "size": self.size,
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

    def set_rating(self, rating: int, *, active: bool) -> None:
        assert self.api is not None
        assert 0 <= rating <= 100
        self.rating = rating
        if active:
            self.api.rating.set(rating)

    def set_favorite_status(self, status: FavoriteStatus, *, active: bool) -> None:
        assert self.api is not None
        if status == FavoriteStatus.FAVORITED:
            if self.favorite is False:
                logger.info(f"💗 {self.display()}")
                self.favorite = True
                if active:
                    self.api.favorited.set(True)
        elif status == FavoriteStatus.DISLIKED:
            if self.disliked is False:
                logger.info(f"😾 {self.display()}")
                self.disliked = True
                if active:
                    self.api.disliked.set(True)
        elif status == FavoriteStatus.NONE:
            if self.favorite is True:
                logger.info(f"💔 {self.display()}")
                self.favorite = False
                if active:
                    self.api.favorited.set(False)
            if self.disliked is True:
                logger.info(f"🫤 {self.display()}")
                self.disliked = False
                if active:
                    self.api.disliked.set(False)
        else:
            raise ValueError(f"Invalid favorite status: {status}")

    def add_to_playlist(self, playlist: Any) -> None:
        assert self.api is not None
        self.api.duplicate(to=playlist)


def median(values: List[float]) -> float:
    count = len(values)
    sorted_values = sorted(values)
    half = count // 2
    if count & 1:
        return sorted_values[half]
    return (sorted_values[half - 1] + sorted_values[half]) / 2


@dataclass
class MetadataStats:
    total: float = field(init=False)
    avg: float = field(init=False)
    median: float = field(init=False)
    median_total: float = field(init=False)
    max: float = field(init=False)
    min: float = field(init=False)
    std_dev: float = field(init=False)
    mode: float = field(init=False)

    values: InitVar[List[float]]
    to_display: Callable[[float], str] = str
    to_json: Callable[[float], Any] = lambda x: x

    def __post_init__(self, values: List[float]) -> None:
        count = len(values)
        assert count > 0
        value_type = type(values[0])
        self.total = sum(values, start=value_type())
        self.avg = self.total / count
        self.median = median(values)
        self.median_total = self.median * count
        self.max = max(values)
        self.min = min(values)
        self.std_dev = (sum((x - self.avg) ** 2 for x in values) / count) ** 0.5
        self.mode = max(set(values), key=values.count)

    def __str__(self) -> str:
        return "\n".join(
            [
                f"Total: {self.to_display(self.total)}",
                f"Avg: {self.to_display(self.avg)}",
                f"Median: {self.to_display(self.median)}",
                f"Median Total: {self.to_display(self.median_total)}",
                f"Max: {self.to_display(self.max)}",
                f"Min: {self.to_display(self.min)}",
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.to_json(self.total),
            "avg": self.to_json(self.avg),
            "median": self.to_json(self.median),
            "median_total": self.to_json(self.median_total),
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
    skip_rate: MetadataStats = field(init=False)
    net_rate: MetadataStats = field(init=False)
    days_between_plays: MetadataStats = field(init=False)
    overdue: MetadataStats = field(init=False)
    duration: MetadataStats = field(init=False)
    play_count: MetadataStats = field(init=False)
    skip_count: MetadataStats = field(init=False)
    rating: MetadataStats = field(init=False)
    year: MetadataStats = field(init=False)
    track_number: MetadataStats = field(init=False)
    years_since_added: MetadataStats = field(init=False)
    days_since_last_played: MetadataStats = field(init=False)
    num_playlists: MetadataStats = field(init=False)
    size: MetadataStats = field(init=False)

    tracks: InitVar[List[Track]]

    def __post_init__(self, tracks: List[Track]) -> None:
        self.count = len(tracks)
        self.score = MetadataStats(
            [track.score for track in tracks],
            to_display=lambda x: f"{x:.2f}",
        )
        self.play_rate = MetadataStats(
            [track.play_rate for track in tracks],
            to_display=lambda x: f"{x:.2f}",
        )
        self.listen_rate = MetadataStats(
            [track.listen_rate.total_seconds() for track in tracks],
            to_json=lambda x: x / 60,  # seconds to min
            to_display=lambda x: f"{dt.timedelta(seconds=x)}",
        )
        self.skip_rate = MetadataStats(
            [track.skip_rate for track in tracks],
            to_display=lambda x: f"{x:.2f}",
        )
        self.net_rate = MetadataStats(
            [track.net_rate for track in tracks],
            to_display=lambda x: f"{x:.2f}",
        )
        self.days_between_plays = MetadataStats(
            [track.time_between_plays.total_seconds() for track in tracks],
            to_json=lambda x: x / 60 / 60 / 24,  # seconds to days
            to_display=lambda x: f"{dt.timedelta(seconds=x)}",
        )
        self.overdue = MetadataStats(
            [track.overdue for track in tracks],
            to_display=lambda x: f"{x:.2f}%",
        )
        self.duration = MetadataStats(
            values=[track.duration.total_seconds() for track in tracks],
            to_json=lambda x: x / 60,
            to_display=lambda x: str(dt.timedelta(seconds=x)),
        )
        self.play_count = MetadataStats(
            values=[track.play_count for track in tracks],
            to_display=lambda x: f"{x:.1f}",
        )
        self.skip_count = MetadataStats(
            values=[track.skip_count for track in tracks],
            to_display=lambda x: f"{x:.1f}",
        )
        self.rating = MetadataStats(
            values=[track.rating for track in tracks],
            to_display=lambda x: f"{x/20:.2f}★",
            to_json=lambda x: x / 20,
        )
        self.year = MetadataStats(
            values=[track.year for track in tracks],
        )
        self.track_number = MetadataStats(
            values=[track.track_number for track in tracks],
        )
        self.years_since_added = MetadataStats(
            values=[track.duration_since_added.total_seconds() for track in tracks],
            to_json=lambda x: x / 60 / 60 / 24 / 365.25,  # seconds to years
            to_display=lambda x: str(dt.timedelta(seconds=x)),
        )
        self.days_since_last_played = MetadataStats(
            values=[
                track.duration_since_last_played.total_seconds() for track in tracks
            ],
            to_json=lambda x: x / 60 / 60 / 24,  # seconds to days
            to_display=lambda x: str(dt.timedelta(seconds=x)),
        )
        self.num_playlists = MetadataStats(
            values=[len(track.playlists) for track in tracks],
            to_display=lambda x: f"{x:.1f}",
        )
        self.size = MetadataStats(
            values=[track.size for track in tracks],
            to_display=human_readable_size,
        )

    def __str__(self) -> str:
        return "\n".join(
            [
                f"{self.name}:",
                f"  Count: {self.count}",
            ]
            + [
                f"  {name}:\n{textwrap.indent(str(metadata), '    ')}"
                for name, metadata in {
                    "Score": self.score,
                    # "Play Rate": self.play_rate,
                    # "Listen Rate": self.listen_rate,
                    # "Skip Rate": self.skip_rate,
                    "Net Rate": self.net_rate,
                    "Days Between Plays": self.days_between_plays,
                    # "Overdue": self.overdue,
                    "Duration": self.duration,
                    # "Days Since Last Played": self.days_since_last_played,
                    # "Play Count": self.play_count,
                    # "Rating": self.rating,
                    "Size": self.size,
                }.items()
            ]
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "score": self.score.to_dict(),
            "play_rate": self.play_rate.to_dict(),
            "listen_rate": self.listen_rate.to_dict(),
            "skip_rate": self.skip_rate.to_dict(),
            "net_rate": self.net_rate.to_dict(),
            "days_between_plays": self.days_between_plays.to_dict(),
            "overdue": self.overdue.to_dict(),
            "duration": self.duration.to_dict(),
            "play_count": self.play_count.to_dict(),
            "skip_count": self.skip_count.to_dict(),
            "rating": self.rating.to_dict(),
            "year": self.year.to_dict(),
            "track_number": self.track_number.to_dict(),
            "years_since_added": self.years_since_added.to_dict(),
            "days_since_last_played": self.days_since_last_played.to_dict(),
            "num_playlists": self.num_playlists.to_dict(),
            "size": self.size.to_dict(),
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
            playlist_folder: Optional[str]

        input: Input

        @dataclass
        class Stats:
            name: str
            save_totals: bool
            show_totals: bool
            save_tracks: bool
            show_track_diff: bool
            save_collections: bool
            show_collection_diff: bool

        stats: List[Stats]

        @dataclass
        class Output:
            force_update: bool
            update_every: Optional[dt.timedelta]
            remove_only: bool

            @dataclass
            class Shuffle:
                enabled: bool
                name: Optional[str]
                parent_playlist: Optional[str]
                save_tracks: bool
                downranked_genres: List[str]
                downranked_artists: List[str]

            shuffle: Shuffle

            @dataclass
            class Overdue:
                enabled: bool
                name: Optional[str]
                parent_playlist: Optional[str]
                save_tracks: bool

            overdue: Overdue

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
                    playlist_folder=data["playlists"]["input"].get("playlist_folder"),
                ),
                stats=[
                    cls.Playlists.Stats(
                        name=stat["name"],
                        save_totals=stat["save_totals"],
                        show_totals=stat["show_totals"],
                        save_tracks=stat["save_tracks"],
                        show_track_diff=stat["show_track_diff"],
                        save_collections=stat["save_collections"],
                        show_collection_diff=stat["show_collection_diff"],
                    )
                    for stat in data["playlists"]["stats"]
                ],
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
                        parent_playlist=data["playlists"]["output"]["shuffle"].get(
                            "parent_playlist"
                        ),
                        save_tracks=data["playlists"]["output"]["shuffle"][
                            "save_tracks"
                        ],
                        downranked_genres=data["playlists"]["output"]["shuffle"].get(
                            "downranked_genres", []
                        ),
                        downranked_artists=data["playlists"]["output"]["shuffle"].get(
                            "downranked_artists", []
                        ),
                    ),
                    overdue=cls.Playlists.Output.Overdue(
                        enabled=data["playlists"]["output"]["overdue"]["enabled"],
                        name=data["playlists"]["output"]["overdue"].get("name"),
                        parent_playlist=data["playlists"]["output"]["overdue"].get(
                            "parent_playlist"
                        ),
                        save_tracks=data["playlists"]["output"]["overdue"][
                            "save_tracks"
                        ],
                    ),
                ),
            ),
            album_ratings=cls.AlbumRatings(clear=data["album_ratings"]["clear"]),
            track_ratings=cls.TrackRatings(update=data["track_ratings"]["update"]),
            favorites=cls.Favorites(
                update=data["favorites"]["update"],
                top_percent=data["favorites"].get("top_percent"),
            ),
        )


def track_iter(tracks: List[Track], *, active: bool = True) -> tqdm.tqdm[Track]:
    return tqdm.tqdm(
        tracks,
        unit="track",
        mininterval=PROGRESS_INTERVAL,
        # bar_format="{l_bar}{bar}| ",
        disable=not active,
    )


def init_logger(level: int) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    formatter = ColoredFormatter("%(log_color)s[%(levelname)s]%(reset)s %(message)s")
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root.addHandler(console_handler)
    # also save to log.txt at debug level
    root.debug(f"Logging to {LOG_PATH}")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(file_handler)


def update_track_params(music_app: Any, config: Config) -> None:
    Track.set_down_ranked(
        artists=config.playlists.output.shuffle.downranked_artists,
        genres=config.playlists.output.shuffle.downranked_genres,
    )

    subdir_name = config.playlists.input.source_playlist
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
            net_rate = total_data[0]["net_rate"]["median"]
            if math.isclose(TARGET_MEDIAN_SCORE, 1.0):
                n = 1 + net_rate
            else:
                n = (1 + net_rate) ** (1 / TARGET_MEDIAN_SCORE)
            Track.score_base = n
    else:
        logger.warning(f"Could not find {totals_path}")
    logger.info(f"Median song length: {Track.median_song_length}")
    logger.info(f"Score base: {Track.score_base:.3f}")

    if config.playlists.input.playlist_folder is not None:
        Track.loaded_playlists = load_playlists_from_folder(
            music_app, config.playlists.input.playlist_folder
        )


def update_track_ratings(tracks: List[Track], *, active: bool) -> None:
    logger.info("Updating track ratings")
    num_bins = min(100, len(tracks))
    assert num_bins > 0
    bin_size = len(tracks) / num_bins
    logger.debug(f"Tracks per 0.05 stars: {bin_size:.1f}")
    for i, track in enumerate(track_iter(tracks, active=active)):
        if track.play_count > 0:
            rating = 100 - int(i // bin_size)
        else:
            rating = 0
        track.set_rating(rating, active=active)


def update_favorites(tracks: List[Track], *, fav_percent: float, active: bool) -> None:
    logger.info("Updating favorites")
    fav_limit = round(len(tracks) * (fav_percent / 100))
    # assumes sorted
    for i, track in enumerate(tracks):
        if i < fav_limit:
            favorited = FavoriteStatus.FAVORITED
        else:
            favorited = FavoriteStatus.NONE
        track.set_favorite_status(favorited, active=active)


def weighted_shuffle(tracks: List[Track]) -> List[Track]:
    logger.info("Shuffling tracks")

    # set random seed based on day
    seed = NOW.toordinal()
    random.seed(seed)

    shuffled = []
    tracks = tracks.copy()
    min_score = min(track.score for track in tracks)
    weight_floor = 0.01
    weights = []
    for track in tracks:
        # raise weights to a minimum floor (to avoid negative and zero weights)
        weight = track.score - min_score + weight_floor
        weight *= 1 + track.overdue
        if track.is_downranked():
            weight /= 2
        elif track.favorite:
            weight *= 2
        weights.append(weight)
    tic = time.perf_counter()
    # sims = [0.0] * len(tracks)
    total_weight = sum(weights)
    while tracks:
        # similarity.... it was a nice idea
        # adjusted_weights = [weight * (1 + sim) for weight, sim in zip(weights, sims)]
        # total_adjusted_weight = sum(adjusted_weights)
        adjusted_weights = weights
        total_adjusted_weight = total_weight
        r = random.uniform(0, total_adjusted_weight)
        for i, weight in enumerate(adjusted_weights):
            r -= weight
            if r <= 0:
                picked = tracks.pop(i)
                shuffled.append(picked)
                # logger.debug(
                # f"{picked.display()} ({weights[i]:.3f}, {sims[i]:.3f}, {weight:.3f})")
                logger.debug(f"{picked.display()} ({weights[i]:.3f})")
                del weights[i]
                total_weight -= weight
                # del sims[i]
                # for i, track in enumerate(tracks):
                #     sims[i] = (sims[i] * 0.5) + (picked.similarity_to(track) * 0.5)
                break
        else:
            raise RuntimeError("Weighted shuffle failed")
    toc = time.perf_counter()
    logger.debug(f"Shuffled in {toc - tic:.2f} seconds")
    logger.debug(f"Weighted shuffle error: {total_weight}")
    return shuffled


class PlaylistLoader:

    def __init__(self, music_app: Any) -> None:
        self.music_app = music_app

        self.tracks_by_dbid: Dict[int, Track] = {}
        self.tracks_by_playlist: Dict[str, List[Track]] = {}

    def load(self, playlist_name: str) -> List[Track]:
        if (tracks := self.tracks_by_playlist.get(playlist_name)) is not None:
            return tracks

        playlist = self.music_app.playlists[playlist_name]
        if not playlist.exists():
            raise ValueError(f"Playlist {playlist_name!r} does not exist")

        logger.info(f"Loading playlist {playlist_name!r}")
        out = []
        tracks_to_process = []
        for track in playlist.tracks():
            dbid = track.database_ID()
            if (track_obj := self.tracks_by_dbid.get(dbid)) is not None:
                out.append(track_obj)
            else:
                tracks_to_process.append(track)
        if tracks_to_process:
            for track in track_iter(tracks_to_process):
                track_obj = Track.from_api(api=track)
                self.tracks_by_dbid[track_obj.dbid] = track_obj
                out.append(track_obj)
        out.sort(key=lambda x: x.score, reverse=True)
        self.tracks_by_playlist[playlist_name] = out
        return out


def load_playlists_from_folder(music_app: Any, playlist_folder: str) -> Set[Any]:
    logger.info(f"Retrieving playlists from {playlist_folder}")
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
    return folder_playlists


def update_playlist(
    *, music_app: Any, source_tracks: List[Track], playlist_name: str
) -> None:
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
    for track in track_iter(source_tracks):
        track.add_to_playlist(playlist)


def remove_unsynced_tracks(
    music_app: Any, synced_tracks: List[Track], playlist_name: str
) -> None:
    playlist = music_app.playlists[playlist_name]
    if not playlist.exists():
        logger.info(f"Playlist {playlist_name!r} does not exist")
        return

    synced_dbids = {track.dbid for track in synced_tracks}
    unsynced_tracks = [
        track for track in playlist.tracks() if track.database_ID() not in synced_dbids
    ]

    logger.info(f"Removing {len(unsynced_tracks)} tracks from {playlist_name!r}")
    for track in unsynced_tracks:
        track.delete()


def save_track_data(tracks: List[Track], subdir_name: str, show_diff: bool) -> None:
    save_data(
        data=[track.to_dict() for track in tracks],
        subdir_name=subdir_name,
        name="tracks",
        show_diff=show_diff,
        key=lambda x: x["dbid"],
        rating=lambda x: x["rating"],
        counts=lambda x: x["play_count"] + x["skip_count"],
        # score=lambda x: x["score"],
        score=lambda x: x["net_rate"],
        pretty=lambda x: f"{x['name']} - {x['track_artist']}",
    )


def save_collection_stats(tracks: List[Track], *, subdir_name: str) -> None:
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
            rating=lambda x: x["rating"]["avg"],
            counts=lambda x: x["play_count"]["total"] + x["skip_count"]["total"],
            score=None,
            pretty=None,
        )


def save_total_stats(
    tracks: List[Track], *, subdir_name: str, show_stats: bool
) -> None:
    source = TrackCollection(name=subdir_name, tracks=tracks)
    save_data(
        data=[source.to_dict()],
        subdir_name=subdir_name,
        name="totals",
        show_diff=False,
        key=None,
        rating=None,
        score=None,
        counts=None,
        pretty=None,
    )
    if show_stats:
        logger.info(source)


def save_data(
    *,
    data: List[Dict[str, Any]],
    subdir_name: str,
    name: str,
    show_diff: bool,
    key: Optional[Any],
    rating: Optional[Any],
    score: Optional[Any],
    counts: Optional[Any],
    pretty: Optional[Any],
) -> None:
    json_subdir = OUTPUT_DIR / subdir_name
    json_subdir.mkdir(parents=True, exist_ok=True)
    json_path = json_subdir / f"{name}.json"

    # grab existing file for later if it exists
    existing_data: Optional[List[Dict[str, Any]]]
    if show_diff and json_path.exists():
        with json_path.open("r", encoding="utf-8") as json_file:
            existing_data = json.load(json_file)
    else:
        existing_data = None

    data = [{"index": i, **item} for i, item in enumerate(data)]

    if show_diff and existing_data is not None and data != existing_data:
        assert key is not None
        assert rating is not None
        assert counts is not None
        show_diffs(
            current=data,
            previous=existing_data,
            name=name,
            key=key,
            rating=rating,
            score=score,
            counts=counts,
            pretty=pretty,
        )

    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=4)
    logger.debug(f"Saved {json_path}")


def show_diffs(
    current: List[Dict[str, Any]],
    previous: List[Dict[str, Any]],
    name: str,
    key: Callable[[Dict[str, Any]], Any],
    rating: Callable[[Dict[str, Any]], float],
    counts: Callable[[Dict[str, Any]], float],
    score: Optional[Callable[[Dict[str, Any]], float]],
    pretty: Optional[Callable[[Dict[str, Any]], str]],
) -> None:
    rating_diff_threshold = 0.01
    pretty_diff: Callable[[float], str] = lambda x: f"{x:+.2f}"
    pretty_rating: Callable[[Dict[str, Any]], str] = lambda x: f"{rating(x):.2f}★"
    score_diff_threshold = 0.01

    prev_items_by_key = {key(item): item for item in previous}
    diff_list = []
    total_diff = 0.0
    for item in current:
        prev_item = prev_items_by_key.get(key(item))
        pretty_name = pretty(item) if pretty else key(item)
        if prev_item is None:
            if score is not None:
                total_diff += score(item)
            diff_list.append(f"ADD    {pretty_rating(item)} {pretty_name}")
        else:
            if score is not None:
                total_diff += score(item) - score(prev_item)
            if counts(item) != counts(prev_item):
                item_rating = rating(item)
                rating_diff = item_rating - rating(prev_item)
                abs_rating_diff = abs(rating_diff)
                if abs_rating_diff >= rating_diff_threshold:
                    if rating_diff > 0:
                        disp = " " + pretty_diff(rating_diff)
                    else:
                        disp = pretty_diff(rating_diff) + " "
                    diff_list.append(f"{disp} {pretty_rating(item)} {pretty_name}")
    current_keys = {key(item) for item in current}
    for item in previous:
        if key(item) not in current_keys:
            if score is not None:
                total_diff -= score(item)
            pretty_name = pretty(item) if pretty else key(item)
            diff_list.append(f"DEL    {pretty_rating(item)} {pretty_name}")
    if diff_list:
        diff_str = f"{name} ratings:\n" + "\n".join(diff_list)
        logger.info(diff_str)
    if abs(total_diff) > score_diff_threshold:
        logger.info(f"{name} total score: {total_diff:+.2f}")
    avg_diff = total_diff / len(current)
    if abs(avg_diff) > score_diff_threshold:
        logger.info(f"{name} avg score: {avg_diff:+.2f}")


def print_ui_tree(root: Any, *, actions: bool = True) -> None:
    root = root.get()

    def print_tree(node: Any, indent: int) -> None:
        if actions:
            for action in node.actions.get():
                print(f"{' ' * indent}[{action.name()}]")
        for child in node.UI_elements.get():
            base = node if indent == 0 else root
            name = str(child).replace(str(base), "")
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


def wait_for_ui(
    cond: Callable[[], bool],
    *,
    timeout: dt.timedelta,
) -> None:
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

        # start a sync
        time.sleep(2)
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
        # for window in app("System Events").processes["Finder"].windows():
        #     print_ui_tree(window, actions=False)
        return False


def wait_for_library_update() -> None:
    logger.info("Waiting for library to update...")
    process_name = "AMPLibraryAgent"
    cmd = ["pgrep", "-x", process_name]
    output = sp.check_output(cmd, universal_newlines=True)
    pid = int(output.strip())
    proc = psutil.Process(pid)
    cpu_interval = 5
    cpu_threshold = 10
    while proc.cpu_percent(interval=cpu_interval) > cpu_threshold:
        time.sleep(0)


def human_readable_size(size: float) -> str:
    base = 1024
    if size < base:
        return f"{size} B"
    size /= base
    if size < base:
        return f"{size:.1f} KB"
    size /= base
    if size < base:
        return f"{size:.1f} MB"
    size /= base
    return f"{size:.1f} GB"


def filter_percent(tracks: List[Track], percent: float) -> List[Track]:
    return tracks[: int(len(tracks) * percent / 100)]


def filter_duration(tracks: List[Track], duration: dt.timedelta) -> List[Track]:
    length = dt.timedelta()
    filtered = []
    for track in tracks:
        if length + track.duration <= duration:
            filtered.append(track)
            length += track.duration
    return filtered


def filter_unique_track_numbers(tracks: List[Track]) -> List[Track]:
    track_numbers = set()
    filtered = []
    for track in tracks:
        if track.track_number not in track_numbers:
            filtered.append(track)
            track_numbers.add(track.track_number)
    return filtered

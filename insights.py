#!/usr/bin/env python

from __future__ import annotations

import datetime as dt
import json
import random
from typing import Any, Callable, Dict, List

import click

from music import (
    NOW,
    ONE_DAY,
    ONE_MONTH,
    OUTPUT_DIR,
    Track,
    filter_duration,
    filter_percent,
    filter_unique_track_numbers,
)

INSIGHTS_DIR = OUTPUT_DIR / "insights"

MAX_LINES = 15

DictKey = Callable[[Dict[str, Any]], float]
TrackKey = Callable[[Track], float]


def stripped_artist(artist: str) -> str:
    words = ["feat.", "Feat.", "w/"]
    for word in words:
        artist = artist.split(word)[0].strip()
    return artist


def best_non_album_artists(
    track_artists: List[Dict[str, Any]],
    album_artists: List[Dict[str, Any]],
    score_avg: float,
) -> None:
    # find the best track artists that aren't album artists yet
    album_artist_names = {x["name"] for x in album_artists}
    non_album_artists = [
        x
        for x in track_artists
        if stripped_artist(x["name"]) not in album_artist_names
        if x["score"]["avg"] > score_avg
    ]
    if non_album_artists:
        non_album_artists.sort(key=lambda x: x["score"]["avg"], reverse=True)
        lines = [f"- {x['name']} ({x['score']['avg']:.2f})" for x in non_album_artists]
        (INSIGHTS_DIR / "non_album_artists.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("buy their albums")
        print("\n".join(lines))


def negative_score(tracks: List[Track]) -> None:
    # negative scores
    negative_score_tracks = [x for x in tracks if x.score < 0]
    if negative_score_tracks:
        negative_score_tracks.sort(key=lambda x: x.score)
        lines = [
            f"- {x.name} - {x.track_artist} ({x.score:.2f})"
            for x in negative_score_tracks
        ]
        (INSIGHTS_DIR / "negative_score_tracks.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("why... i can't even")
        print("\n".join(lines))


def lowest_overdue(tracks: List[Track]) -> None:
    # lowest overdue magnitude
    on_schedule_tracks = tracks.copy()
    on_schedule_tracks.sort(key=lambda x: abs(x.overdue))
    on_schedule_tracks = filter_percent(on_schedule_tracks, 1)
    lines = [
        f"- {x.name} - {x.track_artist} "
        f"({x.time_between_plays/ONE_DAY:.2f}{x.overdue_duration/ONE_DAY:+.2f} days)"
        for x in on_schedule_tracks
    ]
    (INSIGHTS_DIR / "on_schedule_tracks.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("right on schedule")
    print("\n".join(lines))


def score_times_overdue(tracks: List[Track]) -> None:
    # score * overdue
    adjusted_scores = tracks.copy()
    adjusted_score: TrackKey = lambda x: x.score * (1 + x.overdue)
    adjusted_scores.sort(key=adjusted_score, reverse=True)
    adjusted_scores = filter_percent(adjusted_scores, 1)
    lines = [
        f"- {x.name} - {x.track_artist} "
        f"({x.score:.2f} * {1 + x.overdue:.2f} = {adjusted_score(x):.2f})"
        for x in adjusted_scores
    ]
    (INSIGHTS_DIR / "adjusted_scores.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("best bang for the buck")
    print("\n".join(lines))


def negative_overdue_high_score(tracks: List[Track], score_avg: float) -> None:
    # negative overdue, high score
    negative_overdue_tracks = [
        x for x in tracks if x.overdue < 0 and x.score > score_avg
    ]
    if negative_overdue_tracks:
        key: TrackKey = lambda x: x.score * x.overdue
        negative_overdue_tracks.sort(key=key)
        lines = [
            f"- {x.name} - {x.track_artist} "
            f"({x.score:.2f} * {x.overdue:.2f} = {key(x):.2f})"
            for x in negative_overdue_tracks
        ]
        (INSIGHTS_DIR / "negative_overdue_tracks.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("you're early")
        print("\n".join(lines))


def similar_to(tracks: List[Track]) -> None:
    # picked = tracks[0]
    picked = random.choice(tracks)
    sim_key: TrackKey = lambda x: x.similarity_to(picked)
    similar_tracks = tracks.copy()
    similar_tracks.sort(key=sim_key, reverse=True)
    similar_tracks = filter_percent(similar_tracks, 10)
    lines = [
        f"- {x.name} - {x.track_artist} ({sim_key(x):.2f})" for x in similar_tracks
    ]
    (INSIGHTS_DIR / "similar_tracks.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("similar to something")
    print("\n".join(lines))


def highest_bit_rates(tracks: List[Track]) -> None:
    # highest bit rates
    bit_rate_tracks = tracks.copy()
    bit_rate_key: TrackKey = lambda x: (x.size * 8 / 1024) / x.duration.total_seconds()
    bit_rate_tracks.sort(key=bit_rate_key, reverse=True)
    bit_rate_tracks = filter_percent(bit_rate_tracks, 1)
    lines = [
        f"- {x.name} - {x.track_artist} ({bit_rate_key(x):.2f} kbps)"
        for x in bit_rate_tracks
    ]
    (INSIGHTS_DIR / "bit_rate_tracks.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("highest bit rates")
    print("\n".join(lines))


def largest_sizes(tracks: List[Track]) -> None:
    # largest sizes
    size_tracks = tracks.copy()
    size_tracks.sort(key=lambda x: x.size, reverse=True)
    size_tracks = filter_percent(size_tracks, 1)
    lines = [
        f"- {x.name} - {x.track_artist} ({x.size / 1024 / 1024:.2f} MB)"
        for x in size_tracks
    ]
    (INSIGHTS_DIR / "size_tracks.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("largest sizes")
    print("\n".join(lines))


def overdue_unsynced(tracks: List[Track]) -> None:
    # highest overdue unsynced tracks
    overdue_unsynced_tracks = [x for x in tracks if x.overdue > 0]
    if overdue_unsynced_tracks:
        overdue_unsynced_tracks.sort(key=lambda x: x.overdue, reverse=True)
        lines = [
            f"- {x.name} - {x.track_artist} ({x.overdue:.2f})"
            for x in overdue_unsynced_tracks
        ]
        (INSIGHTS_DIR / "overdue_unsynced_tracks.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("overdue unsynced tracks")
        print("\n".join(lines))


def mixtape(tracks: List[Track]) -> None:
    # weighted shuffle tracks
    # - in "Indie Girls" playlist
    # - last skipped not in last 1 month
    # - last played not in last 3 days
    # - track number is not zero
    # - limit to 1 song per unique track number
    # - limit to 45 minutes
    # - sort by track number ascending
    master = [
        track
        for track in tracks
        # if "Indie Girls" in track.playlists
        if NOW - track.last_skipped > ONE_MONTH
        if NOW - track.last_played > 3 * ONE_DAY
    ]
    mixtape_tracks = [track for track in master if track.track_number != 0]
    mixtape_tracks = filter_unique_track_numbers(mixtape_tracks)
    mixtape_tracks = filter_duration(mixtape_tracks, dt.timedelta(minutes=45))
    if mixtape_tracks:
        mixtape_tracks.sort(key=lambda x: x.track_number)
        # now add a bonus track to the end (track no = 0)
        mixtape_tracks += [track for track in master if track.track_number == 0][:1]
        lines = [
            f"{x.track_number}. {x.name} - {x.track_artist}" for x in mixtape_tracks
        ]
        (INSIGHTS_DIR / "mixtape.txt").write_text("\n".join(lines))
        print()
        print("i made you a mixtape")
        print("\n".join(lines))


def long_time_no_see(tracks: List[Track]) -> None:
    # highest time since last interaction
    long_time_tracks = tracks.copy()
    long_time_tracks.sort(key=lambda x: x.duration_since_last_interaction, reverse=True)
    long_time_tracks = filter_percent(long_time_tracks, 1)
    lines = [
        f"- {x.name} - {x.track_artist} "
        f"({x.duration_since_last_interaction / ONE_DAY:.2f} days)"
        for x in long_time_tracks
    ]
    (INSIGHTS_DIR / "long_time_tracks.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("long time no see")
    print("\n".join(lines))


def lower_case(tracks: List[Track]) -> None:
    lower_case_tracks = [track for track in tracks if track.name.islower()]
    if lower_case_tracks:
        lower_case_tracks.sort(key=lambda x: len(x.name), reverse=True)
        lines = [f"- {x.name} - {x.track_artist}" for x in lower_case_tracks]
        (INSIGHTS_DIR / "lower_case_tracks.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("lower case tracks")
        print("\n".join(lines))


def upper_case(tracks: List[Track]) -> None:
    upper_case_tracks = [track for track in tracks if track.name.isupper()]
    if upper_case_tracks:
        upper_case_tracks.sort(key=lambda x: len(x.name), reverse=True)
        lines = [f"- {x.name} - {x.track_artist}" for x in upper_case_tracks]
        (INSIGHTS_DIR / "upper_case_tracks.txt").write_text("\n".join(lines))
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
        print()
        print("upper case tracks")
        print("\n".join(lines))


def meander(tracks: List[Track]) -> None:
    meander_len = MAX_LINES
    remaining = tracks.copy()
    previous = random.choice(
        [
            x
            for x in remaining
            # if x.track_number == 1
        ]
    )
    remaining.remove(previous)
    lines = ["- " + previous.display()]
    sim_key: TrackKey = lambda x: x.similarity_to(previous)
    recent_albums = [previous.album]
    recent_album_artists = [previous.album_artist]
    recent_track_artists = [previous.track_artist]
    recent_cutoff = 5
    for _ in range(meander_len - 1):
        # TODO: add some sort of exponential decay so it explores
        # instead of bouncing between the same artists
        possible = [
            x
            for x in remaining
            # if x.album != previous.album
            # if x.track_artist != previous.track_artist
            # if x.album_artist != previous.album_artist
            # if x.track_number == previous.track_number + 1
            if x.album not in recent_albums
            if x.album_artist not in recent_album_artists
            if x.track_artist not in recent_track_artists
        ]
        if not possible:
            break
        next_track = max(possible, key=sim_key)
        lines.append("- " + next_track.display() + f" ({sim_key(next_track):.2f})")
        remaining.remove(next_track)
        recent_albums.append(next_track.album)
        recent_album_artists.append(next_track.album_artist)
        recent_track_artists.append(next_track.track_artist)
        if len(recent_albums) > recent_cutoff:
            recent_albums.pop(0)
            recent_album_artists.pop(0)
            recent_track_artists.pop(0)
        previous = next_track
    (INSIGHTS_DIR / "meander.txt").write_text("\n".join(lines))
    if len(lines) > MAX_LINES:
        lines = lines[:MAX_LINES] + [f"+ {len(lines) - MAX_LINES} more"]
    print()
    print("meandered")
    print("\n".join(lines))


@click.command()
def cli() -> None:

    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    path = OUTPUT_DIR / "candidates" / "track_artists.json"
    with path.open("r") as file:
        track_artists = json.load(file)

    path = OUTPUT_DIR / "candidates" / "album_artists.json"
    with path.open("r") as file:
        album_artists = json.load(file)

    path = OUTPUT_DIR / "candidates" / "tracks.json"
    with path.open("r") as file:
        candidates = json.load(file)
    candidate_tracks = [Track.from_dict(x) for x in candidates]

    path = OUTPUT_DIR / "synced" / "tracks.json"
    with path.open("r") as file:
        synced = json.load(file)
    synced_tracks = [Track.from_dict(x) for x in synced]

    synced_dbids = {x["dbid"] for x in synced}
    unsynced = [x for x in candidates if x["dbid"] not in synced_dbids]
    unsynced_tracks = [Track.from_dict(x) for x in unsynced]

    # path = OUTPUT_DIR / "candidates" / "totals.json"
    # with path.open("r") as file:
    #     candid_total = json.load(file)[0]

    path = OUTPUT_DIR / "synced" / "totals.json"
    with path.open("r") as file:
        synced_total = json.load(file)[0]

    path = OUTPUT_DIR / "weighted shuffle" / "tracks.json"
    with path.open("r") as file:
        weighted_shuffle = json.load(file)
    weighted_shuffle_tracks = [Track.from_dict(x) for x in weighted_shuffle]

    score_avg = synced_total["score"]["avg"]

    best_non_album_artists(track_artists, album_artists, score_avg)
    negative_score(candidate_tracks)
    lowest_overdue(candidate_tracks)
    score_times_overdue(candidate_tracks)
    negative_overdue_high_score(candidate_tracks, score_avg)
    similar_to(weighted_shuffle_tracks)
    highest_bit_rates(candidate_tracks)
    largest_sizes(candidate_tracks)
    overdue_unsynced(unsynced_tracks)
    mixtape(weighted_shuffle_tracks)
    long_time_no_see(candidate_tracks)
    lower_case(candidate_tracks)
    upper_case(candidate_tracks)
    meander(synced_tracks)

    print()


if __name__ == "__main__":
    cli.main()

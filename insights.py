#!/usr/bin/env python

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Callable, Dict, List

import click

from music import NOW, ONE_DAY, ONE_MONTH, OUTPUT_DIR, Track

INSIGHTS_DIR = OUTPUT_DIR / "insights"

DictKey = Callable[[Dict[str, Any]], float]
# TrackKey = Callable[[Track], float]


def stripped_artist(artist: str) -> str:
    words = ["feat.", "Feat.", "w/"]
    for word in words:
        artist = artist.split(word)[0].strip()
    return artist


@click.command()
def cli() -> None:

    max_lines = 15

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

    synced_dbids = {x["dbid"] for x in synced}
    unsynced = [x for x in candidates if x["dbid"] not in synced_dbids]

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

    # find the best track artists that aren't album artists yet
    album_artist_names = {x["name"] for x in album_artists}
    non_album_artists = [
        x
        for x in track_artists
        if stripped_artist(x["name"]) not in album_artist_names
        if x["score"]["avg"] > synced_total["score"]["avg"]
    ]
    if non_album_artists:
        non_album_artists.sort(key=lambda x: x["score"]["avg"], reverse=True)
        lines = [f"- {x['name']} ({x['score']['avg']:.2f})" for x in non_album_artists]
        (INSIGHTS_DIR / "non_album_artists.txt").write_text("\n".join(lines))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
        print()
        print("buy their albums")
        print("\n".join(lines))

    # candidates with negative scores
    negative_score_tracks = [x for x in candidates if x["score"] < 0]
    if negative_score_tracks:
        negative_score_tracks.sort(key=lambda x: x["score"])
        lines = [
            f"- {x['name']} - {x['track_artist']} ({x['score']:.2f})"
            for x in negative_score_tracks
        ]
        (INSIGHTS_DIR / "negative_score_tracks.txt").write_text("\n".join(lines))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
        print()
        print("why... i can't even")
        print("\n".join(lines))

    # lowest overdue magnitude
    on_schedule_tracks = candidates.copy()
    on_schedule_tracks.sort(key=lambda x: abs(x["overdue"]))
    top_percent = 1
    on_schedule_tracks = on_schedule_tracks[
        : int(len(on_schedule_tracks) * top_percent / 100)
    ]
    lines = [
        f"- {x['name']} - {x['track_artist']} "
        f"({x['days_between_plays']:.2f}{x['days_overdue']:+.2f} days)"
        for x in on_schedule_tracks
    ]
    (INSIGHTS_DIR / "on_schedule_tracks.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("right on schedule")
    print("\n".join(lines))

    # score * overdue
    adjusted_scores = candidates.copy()
    adjusted_score: DictKey = lambda x: x["score"] * (1 + x["overdue"])
    adjusted_scores.sort(key=adjusted_score, reverse=True)
    top_percent = 1
    adjusted_scores = adjusted_scores[: int(len(adjusted_scores) * top_percent / 100)]
    lines = [
        f"- {x['name']} - {x['track_artist']} "
        f"({x['score']:.2f} * {1 + x['overdue']:.2f} = {adjusted_score(x):.2f})"
        for x in adjusted_scores
    ]
    (INSIGHTS_DIR / "adjusted_scores.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("best bang for the buck")
    print("\n".join(lines))

    # negative overdue, high score
    score_avg = synced_total["score"]["avg"]
    negative_overdue_tracks = [
        x for x in candidates if x["overdue"] < 0 and x["score"] > score_avg
    ]
    if negative_overdue_tracks:
        key: DictKey = lambda x: x["score"] * x["overdue"]
        negative_overdue_tracks.sort(key=key)
        lines = [
            f"- {x['name']} - {x['track_artist']} "
            f"({x['score']:.2f} * {x['overdue']:.2f} = {key(x):.2f})"
            for x in negative_overdue_tracks
        ]
        (INSIGHTS_DIR / "negative_overdue_tracks.txt").write_text("\n".join(lines))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
        print()
        print("you're early")
        print("\n".join(lines))

    # similar to something
    similar_tracks = weighted_shuffle_tracks.copy()
    picked = similar_tracks[0]
    # picked = random.choice(tracks)
    # picked = next(track for track in tracks if track.dbid == 39524)
    sim_key: Callable[[Track], float] = lambda x: x.similarity_to(picked)
    similar_tracks.sort(key=sim_key, reverse=True)
    lines = [
        f"- {x.name} - {x.track_artist} ({sim_key(x):.2f})" for x in similar_tracks
    ]
    (INSIGHTS_DIR / "similar_tracks.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("similar to something")
    # print(f"similar to {picked.name} - {picked.track_artist}")
    print("\n".join(lines))

    # highest bit rates
    bit_rate_tracks = candidates.copy()
    bit_rate_key: DictKey = lambda x: (x["size"] * 8 / 1024) / (x["duration"] * 60)
    bit_rate_tracks.sort(key=bit_rate_key, reverse=True)
    top_percent = 1
    bit_rate_tracks = bit_rate_tracks[: int(len(bit_rate_tracks) * top_percent / 100)]
    lines = [
        f"- {x['name']} - {x['track_artist']} ({bit_rate_key(x):.2f} kbps)"
        for x in bit_rate_tracks
    ]
    (INSIGHTS_DIR / "bit_rate_tracks.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("high bit rates")
    print("\n".join(lines))

    # largest sizes
    size_tracks = candidates.copy()
    size_key = lambda x: x["size"]
    size_tracks.sort(key=size_key, reverse=True)
    top_percent = 1
    size_tracks = size_tracks[: int(len(size_tracks) * top_percent / 100)]
    lines = [
        f"- {x['name']} - {x['track_artist']} ({x['size'] / 1024 / 1024:.2f} MB)"
        for x in size_tracks
    ]
    (INSIGHTS_DIR / "size_tracks.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("largest sizes")
    print("\n".join(lines))

    # overdue unsynced tracks
    overdue_unsynced_tracks = [x for x in unsynced if x["overdue"] > 0]
    if overdue_unsynced_tracks:
        overdue_unsynced_tracks.sort(key=lambda x: x["overdue"], reverse=True)
        lines = [
            f"- {x['name']} - {x['track_artist']} ({x['overdue']:.2f})"
            for x in overdue_unsynced_tracks
        ]
        (INSIGHTS_DIR / "overdue_unsynced_tracks.txt").write_text("\n".join(lines))
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
        print()
        print("overdue unsynced tracks")
        print("\n".join(lines))

    # mixtape
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
        for track in weighted_shuffle_tracks
        # if "Indie Girls" in track.playlists
        if NOW - track.last_skipped > ONE_MONTH
        if NOW - track.last_played > 3 * ONE_DAY
    ]
    mixtape = [track for track in master if track.track_number != 0]
    mixtape = filter_unique_track_numbers(mixtape)
    mixtape = filter_duration(mixtape, dt.timedelta(minutes=45))
    if mixtape:
        mixtape.sort(key=lambda x: x.track_number)
        # now add a bonus track to the end (track no = 0)
        mixtape += [track for track in master if track.track_number == 0][:1]
        lines = [f"{x.track_number}. {x.name} - {x.track_artist}" for x in mixtape]
        (INSIGHTS_DIR / "mixtape.txt").write_text("\n".join(lines))
        print()
        print("i made you a mixtape")
        print("\n".join(lines))

    # highest time since last interaction
    long_time_tracks = candidate_tracks.copy()
    long_time_tracks.sort(key=lambda x: x.duration_since_last_interaction, reverse=True)
    top_percent = 1
    long_time_tracks = long_time_tracks[
        : int(len(long_time_tracks) * top_percent / 100)
    ]
    lines = [
        f"- {x.name} - {x.track_artist} "
        f"({x.duration_since_last_interaction / ONE_DAY:.2f} days)"
        for x in long_time_tracks
    ]
    (INSIGHTS_DIR / "long_time_tracks.txt").write_text("\n".join(lines))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"+ {len(lines) - max_lines} more"]
    print()
    print("long time no see")
    print("\n".join(lines))

    print()


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


if __name__ == "__main__":
    cli.main()

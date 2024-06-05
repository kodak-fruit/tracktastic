#!/usr/bin/env python

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

import click
import matplotlib.pyplot as plt

from music import OUTPUT_DIR


@click.command()
def cli() -> None:
    """
    Plots the specified field from a JSON file containing a list of records.

    Args:
    field (str): The field to plot, chosen from a predefined list of valid fields.
    """
    path = OUTPUT_DIR / "synced" / "tracks.json"
    with path.open("r") as file:
        synced = json.load(file)

    path = OUTPUT_DIR / "candidates" / "tracks.json"
    with path.open("r") as file:
        candidates = json.load(file)

    path = OUTPUT_DIR / "weighted shuffle" / "tracks.json"
    with path.open("r") as file:
        shuffled = json.load(file)

    path = OUTPUT_DIR / "candidates" / "album_artists.json"
    with path.open("r") as file:
        album_artists = json.load(file)

    path = OUTPUT_DIR / "candidates" / "track_artists.json"
    with path.open("r") as file:
        track_artists = json.load(file)

    path = OUTPUT_DIR / "candidates" / "years.json"
    with path.open("r") as file:
        years = json.load(file)

    path = OUTPUT_DIR / "candidates" / "track_numbers.json"
    with path.open("r") as file:
        track_numbers = json.load(file)

    path = OUTPUT_DIR / "candidates" / "genres.json"
    with path.open("r") as file:
        genres = json.load(file)

    # artist_names = set()
    # for track in candidates:
    #     if track["compilation"]:
    #         artist_names.add(track["track_artist"])
    #     else:
    #         artist_names.add(track["album_artist"])
    # artists = []
    # for album_artist in album_artists:
    #     if album_artist["name"] in artist_names:
    #         artists.append(album_artist)
    # for track_artist in track_artists:
    #     if track_artist["name"] in artist_names:
    #         artists.append(track_artist)
    # artists.sort(key=lambda x: x["score"]["avg"], reverse=True)

    default_tracks = candidates

    plot_score_over_rating(candidates, synced)
    plot_highlighted_scores(
        default_tracks,
        title="ill/IAN",
        cond=lambda x: (
            x["track_artist"].casefold() in (artists := ("ian sweet", "ill peach"))
            or x["album_artist"].casefold() in artists
        ),
        max_notes=3,
    )
    plot_rates(default_tracks)
    plot_shuffle(shuffled)
    plot_highlighted_scores(
        shuffled,
        title="downranked",
        cond=lambda x: (
            (
                x["track_artist"].casefold()
                in (artists := ("matt pond pa", "shakey graves"))
            )
            or x["album_artist"].casefold() in artists
            or x["genre"].casefold() in ("video game music", "chill lofi")
        ),
        max_notes=3,
    )
    plot_highlighted_scores(
        shuffled,
        title="favorites",
        cond=lambda x: x["favorite"],
        max_notes=3,
    )
    hist_shuffle_distribution(shuffled, parts=3, bins=100)
    plot_artists_with_std_devs(album_artists, title="album artists")
    plot_artists_with_std_devs(track_artists, title="track artists")
    plot_genres_with_std_devs(genres)
    plot_score_vs_year(years)
    plot_score_vs_track_number(track_numbers)
    plot_score_vs_date_since_added(candidates)
    plot_track_number_counts(track_numbers)
    plot_score_vs_overdue(default_tracks)
    plot_days_since_last_interaction_vs_overdue(default_tracks)
    plot_and_hist(
        default_tracks,
        title="size",
        key=lambda x: x["size"] / 1024 / 1024,
        y_label="size (MB)",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="score",
        key=lambda x: x["score"],
        y_label="score",
        bins=500,
    )
    plot_and_hist(
        default_tracks,
        title="duration",
        key=lambda x: x["duration"],
        y_label="duration (min)",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="bit rate",
        key=lambda x: (x["size"] * 8 / 1024) / (x["duration"] * 60),
        y_label="bit rate (kbps)",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="overdue",
        key=lambda x: x["overdue"],
        y_label="overdue",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="average time between plays/skips",
        key=lambda x: x["days_between_plays"],
        y_label="days",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="days since last interaction",
        key=lambda x: x["days_since_last_interaction"],
        y_label="days since last interaction",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="years since added",
        key=lambda x: x["years_since_added"],
        y_label="years since added",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="days overdue",
        key=lambda x: x["days_overdue"],
        y_label="days overdue",
        bins=100,
    )
    plot_and_hist(
        default_tracks,
        title="last played",
        key=lambda x: x["days_since_last_played"],
        y_label="days",
        bins=100,
    )

    plt.show()


def plot_score_over_rating(
    candidates: List[Dict[str, Any]], synced: List[Dict[str, Any]]
) -> None:
    y_field = "rating"
    y1 = [record[y_field] for record in candidates]
    y2 = [record[y_field] for record in synced]

    y2_field = "score"
    y3 = [record[y2_field] for record in candidates]
    y4 = [record[y2_field] for record in synced]

    x1 = range(len(y1))
    x2 = range(len(y2))

    _fig, (ax1, ax2) = plt.subplots(2, 1)
    ax1.grid(True)
    ax2.grid(True)

    ax1.scatter(x1, y1, marker=".", label=y_field)
    ax1.scatter(x1, y3, marker=".", label=y2_field)
    ax1.set_title("candidates")
    ax1.set_xlabel("index")
    ax1.set_ylabel("value")
    ax1.legend()

    ax2.scatter(x2, y2, marker=".", label=y_field)
    ax2.scatter(x2, y4, marker=".", label=y2_field)
    ax2.set_title("synced")
    ax2.set_xlabel("index")
    ax2.set_ylabel("value")
    ax2.legend()
    ax2.set_xlim(ax1.get_xlim())
    ax2.set_ylim(ax1.get_ylim())


def plot_rates(tracks: List[Dict[str, Any]]) -> None:
    y_field = "play_rate"
    y = [record[y_field] for record in tracks]

    y2_field = "norm_listen_rate"
    median_song_length = sum(record["duration"] for record in tracks) / len(tracks)
    y2 = [record["listen_rate"] / median_song_length for record in tracks]

    y3_field = "skip_rate"
    y3 = [-record[y3_field] for record in tracks]

    y4_field = "net_rate"
    y4 = [record[y4_field] for record in tracks]

    x = range(len(y))

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(x, y, marker=".", label=y_field)
    ax.scatter(x, y2, marker=".", label=y2_field)
    ax.scatter(x, y3, marker=".", label=y3_field)
    ax.scatter(x, y4, marker=".", label=y4_field)
    ax.set_title("rates")
    ax.set_xlabel("index")
    ax.set_ylabel("value")
    ax.legend()


def plot_shuffle(shuffled: List[Dict[str, Any]]) -> None:
    y_key: Callable[[Dict[str, Any]], float] = lambda x: x["score"] * (1 + x["overdue"])
    y = [y_key(record) for record in shuffled]

    x = range(len(y))

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(x, y)
    ax.set_title("shuffle score distribution")
    ax.set_xlabel("index")
    ax.set_ylabel("score * (1 + overdue)")


def plot_highlighted_scores(
    tracks: List[Dict[str, Any]],
    *,
    title: str,
    cond: Callable[[Dict[str, Any]], bool],
    max_notes: int,
) -> None:
    low = [record for record in tracks if not cond(record)]
    high = [record for record in tracks if cond(record)]

    y_key: Callable[[Dict[str, Any]], float] = lambda x: x["score"]
    y1 = [y_key(record) for record in low]
    y2 = [y_key(record) for record in high]

    x_field = "index"
    x1 = [record[x_field] for record in low]
    x2 = [record[x_field] for record in high]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(x1, y1, marker=".")
    ax.scatter(x2, y2, marker="x", color="red")
    ax.set_xlabel("index")
    ax.set_ylabel("value")
    ax.set_title(title)

    # annotate max_notes lowest/highest values on both x and y axes
    annotated = []
    annotated.extend(sorted(high, key=y_key)[:max_notes])
    annotated.extend(sorted(high, key=y_key, reverse=True)[:max_notes])
    annotated.extend(sorted(high, key=y_key)[:max_notes])
    annotated.extend(sorted(high, key=y_key, reverse=True)[:max_notes])
    annotated = list({record["dbid"]: record for record in annotated}.values())
    for record in annotated:
        note = f"{record['name']} - {record['track_artist']}"
        safe_note = note.replace("$", r"\$")
        ax.annotate(
            safe_note,
            (record[x_field], y_key(record)),
            textcoords="offset points",
            xytext=(0, 10),
            ha="center",
        )


def hist_shuffle_distribution(
    tracks: List[Dict[str, Any]],
    *,
    parts: int,
    bins: int,
) -> None:
    """Separate histograms for each part of shuffled tracks, on top of each other."""

    y_field = "score"
    ys = [
        [
            record[y_field]
            for record in tracks[
                part * len(tracks) // parts : (part + 1) * len(tracks) // parts
            ]
        ]
        for part in range(parts)
    ]

    _fig, ax = plt.subplots()
    ax.grid(True)

    for i, y in reversed(list(enumerate(ys))):
        ax.hist(
            y,
            bins=bins,
            alpha=0.5,
            histtype="stepfilled",
            linewidth=0,
            density=True,
            stacked=True,
            label=f"part {i}",
        )
    ax.set_title("shuffle score distribution")
    ax.set_xlabel(y_field)
    ax.set_ylabel("count")
    ax.legend()


def plot_artists_with_std_devs(artists: List[Dict[str, Any]], *, title: str) -> None:
    """Plots score of arists with std dev as error bars."""
    # filter out artists with 1 song
    artists = [x for x in artists if x["count"] > 1]

    scores = [x["score"]["avg"] for x in artists]
    std_devs = [x["score"]["std_dev"] for x in artists]
    names = [x["name"] for x in artists]

    x = range(len(scores))

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.errorbar(x, scores, yerr=std_devs, fmt="o")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=90)
    ax.set_xlabel("artist")
    ax.set_ylabel("score")
    ax.set_title(f"{title} scores with std devs")

    # fix artists going off screen
    # plt.tight_layout()


def plot_genres_with_std_devs(genres: List[Dict[str, Any]]) -> None:
    """Plots score of arists with std dev as error bars."""
    # genres = [x for x in genres if x["count"] > 1]

    # sort by std dev lol
    # album_artists.sort(key=lambda x: x["score"]["std_dev"], reverse=True)

    scores = [x["score"]["avg"] for x in genres]
    std_devs = [x["score"]["std_dev"] for x in genres]
    names = [x["name"] for x in genres]

    x = range(len(scores))

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.errorbar(x, scores, yerr=std_devs, fmt="o")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=90)
    ax.set_xlabel("genre")
    ax.set_ylabel("score")
    ax.set_title("genre scores with std devs")

    # fix artists going off screen
    # plt.tight_layout()


def plot_score_vs_year(years: List[Dict[str, Any]]) -> None:
    years = [record for record in years if record["name"] != "0"]

    avg_scores = [record["score"]["avg"] for record in years]
    std_devs = [record["score"]["std_dev"] for record in years]
    # maxs = [record["score"]["max"] for record in years]
    # mins = [record["score"]["min"] for record in years]
    # lower = [avg - min for avg, min in zip(avg_scores, mins)]
    # upper = [max - avg for avg, max in zip(avg_scores, maxs)]

    names = [int(record["name"]) for record in years]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.errorbar(names, avg_scores, yerr=std_devs, fmt="o")
    # ax.errorbar(names, avg_scores, yerr=[lower, upper], fmt="o")
    ax.set_xlabel("year")
    ax.set_ylabel("score")
    ax.set_title("score vs year")


def plot_score_vs_track_number(track_numbers: List[Dict[str, Any]]) -> None:
    avg_scores = [record["score"]["avg"] for record in track_numbers]
    std_devs = [record["score"]["std_dev"] for record in track_numbers]
    # maxs = [record["score"]["max"] for record in track_numbers]
    # mins = [record["score"]["min"] for record in track_numbers]
    # lower = [avg - min for avg, min in zip(avg_scores, mins)]
    # upper = [max - avg for avg, max in zip(avg_scores, maxs)]

    names = [int(record["name"]) for record in track_numbers]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.errorbar(names, avg_scores, yerr=std_devs, fmt="o")
    # ax.errorbar(names, avg_scores, yerr=[lower, upper], fmt="o")
    ax.set_xlabel("track number")
    ax.set_ylabel("score")
    ax.set_title("score vs track number")


def plot_score_vs_date_since_added(tracks: List[Dict[str, Any]]) -> None:
    scores = [record["score"] for record in tracks]

    years_since_added = [record["years_since_added"] for record in tracks]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(years_since_added, scores)
    ax.set_xlabel("years since added")
    ax.set_ylabel("score")
    ax.set_title("score vs years since added")


def plot_track_number_counts(track_numbers: List[Dict[str, Any]]) -> None:
    counts = [record["count"] for record in track_numbers]
    names = [int(record["name"]) for record in track_numbers]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.bar(names, counts)
    ax.set_xlabel("track number")
    ax.set_ylabel("count")
    ax.set_title("track number counts")


def plot_score_vs_overdue(tracks: List[Dict[str, Any]]) -> None:
    y_field = "overdue"
    y = [record[y_field] for record in tracks]

    x_field = "score"
    x = [record[x_field] for record in tracks]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(x, y)
    ax.set_title(f"{x_field} vs {y_field}")
    ax.set_xlabel(x_field)
    ax.set_ylabel(y_field)


def plot_days_since_last_interaction_vs_overdue(tracks: List[Dict[str, Any]]) -> None:
    y_field = "overdue"
    y = [record[y_field] for record in tracks]

    x_field = "days_since_last_interaction"
    x = [record[x_field] for record in tracks]

    _fig, ax = plt.subplots()
    ax.grid(True)

    ax.scatter(x, y)
    ax.set_title(f"{x_field} vs {y_field}")
    ax.set_xlabel(x_field)
    ax.set_ylabel(y_field)


def plot_and_hist(
    tracks: List[Dict[str, Any]],
    *,
    title: str,
    y_label: str,
    key: Callable[[Dict[str, Any]], float],
    bins: int,
) -> None:
    y = [key(record) for record in tracks]
    y.sort()

    x = range(len(y))

    _fig, (ax1, ax2) = plt.subplots(2, 1)
    ax1.grid(True)
    ax2.grid(True)

    ax1.scatter(x, y)
    ax1.set_title(title)
    ax1.set_ylabel(y_label)

    ax2.hist(y, bins=bins)
    ax2.set_title(f"{title} histogram")
    ax2.set_ylabel("count")
    ax2.set_xlabel(y_label)


# unused functions:
# -


if __name__ == "__main__":
    cli.main()

#!/usr/bin/env python

import json

# import random

import click
import matplotlib.pyplot as plt

from music import OUTPUT_DIR

# Define the fields available for plotting
FIELDS = [
    "index",
    # "name",
    # "track_artist",
    # "album",
    # "album_artist",
    # "genre",
    "year",
    "track_number",
    "play_count",
    "skip_count",
    "duration",
    "rating",
    # "date_added",
    "duration_since_added",
    "play_rate",
    "listen_rate",
    "score",
    "dbid",
]

NAME = "synced"
# NAME = "candidates"

TRACKS_PATH = OUTPUT_DIR / NAME / "tracks.json"


@click.command()
def cli() -> None:
    """
    Plots the specified field from a JSON file containing a list of records.

    Args:
    field (str): The field to plot, chosen from a predefined list of valid fields.
    """
    with TRACKS_PATH.open("r") as file:
        data = json.load(file)

    # data = [d for d in data if d["year"] != 0]
    # data = [
    #     d
    #     for d in data
    #     # if d["album_artist"] in ("IAN SWEET", "ill peach")
    #     # or d["track_artist"] in ("IAN SWEET", "ill peach")
    #     # if d["rating"] >= 4
    #     # if d["rating"] != 4
    #     # if d["year"] != 0
    # ]
    # for x in data:
    #     x["score"] *= random.random()
    #     # x["random_score"] = x["score"] * random.random()
    # data.sort(key=lambda x: x["score"])
    # labels = [f"{d['name']} - {d['track_artist']}" for d in data]

    y_field = "rating"
    y = [record[y_field] for record in data]
    # y = [random.random() * random.random() * record[y_field] for record in data]
    # y.sort()
    # random.shuffle(y)

    x_field = "score"
    x = [record[x_field] for record in data]
    # x = [len(record["playlists"]) for record in data]
    # x = range(len(y))

    # (x, y) = (y, x)

    _fig, ax = plt.subplots()

    ax.scatter(x, y)
    ax.set_title(f"{x_field} vs {y_field}")
    ax.set_xlabel(x_field)
    ax.set_ylabel(y_field)

    # ax.hist(y, bins=100)
    # ax.set_title(y_field)
    # ax.set_ylabel("Frequency")
    # ax.set_xlabel(y_field)

    ax.grid(True)

    # for i, label in enumerate(labels):
    #     ax.annotate(label, (x[i], y[i]))
    #     if i > 50:
    #         break

    plt.show()


if __name__ == "__main__":
    cli.main()

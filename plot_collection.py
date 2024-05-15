#!/usr/bin/env python


import json
from pathlib import Path

import click
import matplotlib.pyplot as plt
from music import OUTPUT_DIR

STATS = [
    "total",
    "total_median",
    "avg",
    "median",
    "max",
    "min",
    "std_dev",
    "mode",
]
FIELDS = [
    "score",
    "play_rate",
    "listen_rate",
    "duration",
    "play_count",
    "skip_count",
    "rating",
    "year",
    "track_number",
    "duration_since_added",
]

NAME = "candidates"
KIND = "years"


@click.command()
def cli():
    file_path = OUTPUT_DIR / NAME / f"{KIND}.json"

    with file_path.open("r") as file:
        data = json.load(file)
    name = file_path.stem

    y_field = "rating"
    y_stat = "avg"
    y_name = f"{y_stat} {y_field}"
    y = [record[y_field][y_stat] for record in data]

    x_field = "year"
    x_stat = "avg"
    x_name = f"{x_stat} {x_field}"
    x = [record[x_field][x_stat] for record in data]
    # x_name = "index"
    # x = range(len(y))

    plt.figure(figsize=(10, 5))
    # plt.plot(x, y)
    plt.scatter(x, y, marker=".")
    plt.title(f"{name} - {x_name} vs {y_name}")
    plt.xlabel(x_name)
    plt.ylabel(y_name)
    # plt.legend()
    plt.grid(True)
    plt.show()


if __name__ == "__main__":
    cli.main()

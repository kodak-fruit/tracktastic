#!/usr/bin/env python3

import datetime as dt
import logging
from typing import Dict, List

import click
from appscript import app, its, k

from music import (
    CONFIG_PATH,
    NOW,
    ONE_HOUR,
    OUTPUT_DIR,
    Config,
    Track,
    attach_playlists,
    init_logger,
    process_source,
    remove_unsynced_tracks,
    save_collection_stats,
    save_total_stats,
    save_track_data,
    sync_device,
    update_favorites,
    update_playlist,
    update_track_params,
    update_track_ratings,
    wait_for_amplibraryagent,
    weighted_shuffle,
)

LOG_LEVEL = logging.INFO

logger = logging.getLogger(__name__)


@click.command()
@click.option("--active", is_flag=True)
@click.option("--sync", is_flag=True)
@click.option("--no-sync", is_flag=True)
@click.option("--update-playlists", is_flag=True)
@click.option("-v", "--verbose", count=True, help="Increase logging verbosity.")
@click.option("-q", "--quiet", count=True, help="Decrease logging verbosity.")
def cli(
    active: bool,
    sync: bool,
    no_sync: bool,
    update_playlists: bool,
    verbose: int,
    quiet: int,
) -> None:
    assert not (sync and no_sync), "Cannot specify both --sync and --no-sync"

    level = LOG_LEVEL - 10 * verbose + 10 * quiet
    init_logger(level)

    config = Config.from_toml(CONFIG_PATH)
    if sync:
        config.sync.enabled = True
    if no_sync:
        config.sync.enabled = False
    if update_playlists:
        config.playlists.output.force_update = True

    if active:
        logger.warning("ACTIVE MODE")
    else:
        logger.info("TEST MODE")

    # sync the iphone
    # TODO: add a sentinel that only syncs every so often
    if active and config.sync.enabled:
        assert config.sync.iphone_name, "No iPhone name provided in the config file."
        sync_device(config.sync.iphone_name)
        logger.info(dt.datetime.now() - NOW)
        wait_for_amplibraryagent()
        logger.info(dt.datetime.now() - NOW)

    music_app = app(name="Music")

    # update track params based on prior runs
    update_track_params(config.playlists.input.source_playlist)

    # get all library tracks
    if active and config.album_ratings.clear:
        logger.info("Removing album ratings")
        for track in music_app.tracks[its.album_rating_kind == k.user].get():
            track.album_rating.set(0)
        # TODO: set rating to 0 for all unsynced tracks

    # get all candidate tracks
    source_tracks = process_source(music_app, config.playlists.input.source_playlist)

    if (
        config.playlists.input.save_stats or config.collections.save_stats
    ) and config.collections.playlist_folder is not None:
        attach_playlists(music_app, source_tracks, config.collections.playlist_folder)

    logger.info("Sorting source tracks")
    source_tracks.sort(key=lambda x: x.score, reverse=True)

    # set the rating
    if active and config.track_ratings.update:
        update_track_ratings(source_tracks)

    # set favorites
    if active and config.favorites.update:
        assert (
            config.favorites.top_percent
        ), "No top percent provided in the config file."
        update_favorites(source_tracks, config.favorites.top_percent)

    # get subset of tracks that are synced
    if config.playlists.input.subset_playlist is not None:
        logger.info("Getting subset of tracks")
        subset_dbids = {
            track.database_ID()
            for track in music_app.playlists[
                config.playlists.input.subset_playlist
            ].tracks()
        }
        subset_tracks = [track for track in source_tracks if track.dbid in subset_dbids]
        logger.info(f"Subset: {len(subset_tracks)}")
    else:
        subset_tracks = source_tracks

    # playlists to generate
    playlist_map: Dict[str, List[Track]] = {}

    # create the weighted shuffle playlist
    if config.playlists.output.shuffle.enabled:
        assert (
            config.playlists.output.shuffle.name
        ), "No shuffle playlist name provided in the config file."
        Track.set_down_ranked_arists(config.playlists.output.shuffle.downranked_artists)
        Track.set_down_ranked_genres(config.playlists.output.shuffle.downranked_genres)
        playlist_map[config.playlists.output.shuffle.name] = weighted_shuffle(
            subset_tracks
        )

    # update generated playlists
    if active:
        for playlist_name, tracks in playlist_map.items():
            sentinel_path = OUTPUT_DIR / f".{playlist_name}"
            if not sentinel_path.exists():
                overdue = True
            elif config.playlists.output.update_every is not None:
                time_since_update = NOW - dt.datetime.fromtimestamp(
                    sentinel_path.stat().st_mtime
                )
                hours = time_since_update / ONE_HOUR
                logger.info(
                    f"Time since last {playlist_name!r} update: {hours:.2f} hours"
                )
                overdue = time_since_update > config.playlists.output.update_every
            else:
                overdue = False
            if overdue:
                logger.warning(f"{playlist_name!r} is overdue for update")
            if config.playlists.output.force_update or overdue:
                update_playlist(
                    music_app=music_app,
                    source_tracks=tracks,
                    playlist_name=playlist_name,
                )
                sentinel_path.parent.mkdir(parents=True, exist_ok=True)
                sentinel_path.touch()
            elif config.playlists.output.remove_only:
                # still remove unsynced tracks even if not updating the whole playlist
                remove_unsynced_tracks(music_app, tracks, playlist_name)

    # save data
    if config.playlists.input.save_stats:
        save_track_data(
            source_tracks, config.playlists.input.source_playlist, show_diff=False
        )
        save_total_stats(source_tracks, config.playlists.input.source_playlist)
        if config.playlists.input.subset_playlist is not None:
            save_track_data(
                subset_tracks, config.playlists.input.subset_playlist, show_diff=True
            )
            save_total_stats(subset_tracks, config.playlists.input.subset_playlist)

    if config.collections.save_stats:
        save_collection_stats(source_tracks, config.playlists.input.source_playlist)

    logger.info(dt.datetime.now() - NOW)

    # wait for library update to finish
    if active and config.sync.enabled:
        assert config.sync.iphone_name, "No iPhone name provided in the config file."
        wait_for_amplibraryagent()
        logger.info(dt.datetime.now() - NOW)
        # then sync again
        sync_device(config.sync.iphone_name)
        logger.info(dt.datetime.now() - NOW)


if __name__ == "__main__":
    cli.main()

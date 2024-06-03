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
    PlaylistLoader,
    Track,
    init_logger,
    remove_unsynced_tracks,
    save_collection_stats,
    save_total_stats,
    save_track_data,
    sync_device,
    update_favorites,
    update_playlist,
    update_track_params,
    update_track_ratings,
    wait_for_library_update,
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
    if active and config.sync.enabled:
        assert config.sync.iphone_name, "No iPhone name provided in the config file."
        assert sync_device(config.sync.iphone_name)
        logger.info(dt.datetime.now() - NOW)
        wait_for_library_update()
        logger.info(dt.datetime.now() - NOW)

    music_app = app(name="Music")

    # update track params based on config and prior runs
    update_track_params(music_app, config)

    # get all library tracks
    if active and config.album_ratings.clear:
        logger.info("Removing album ratings")
        for track in music_app.tracks[its.album_rating_kind == k.user].get():
            track.album_rating.set(0)
        # TODO: set rating to 0 for all unsynced tracks

    # get all candidate tracks
    playlist_loader = PlaylistLoader(music_app)
    source_tracks = playlist_loader.load(config.playlists.input.source_playlist)

    # set the rating
    update_track_ratings(source_tracks, active=active and config.track_ratings.update)
    if active:
        wait_for_library_update()
        logger.info(dt.datetime.now() - NOW)

    # set favorites
    if active and config.favorites.update:
        assert (
            config.favorites.top_percent
        ), "No top percent provided in the config file."
        update_favorites(source_tracks, config.favorites.top_percent)

    # playlists to generate
    playlist_map: Dict[str, List[Track]] = {}

    # create overdue playlist
    if config.playlists.output.overdue.enabled:
        assert (
            config.playlists.output.overdue.name
        ), "No overdue playlist name provided in the config file."
        playlist_tracks = (
            playlist_loader.load(config.playlists.output.overdue.parent_playlist)
            if config.playlists.output.overdue.parent_playlist is not None
            else source_tracks
        )
        playlist_map[config.playlists.output.overdue.name] = sorted(
            (x for x in playlist_tracks if x.overdue > 0),
            key=lambda x: x.overdue,
            reverse=True,
        )

    # create the weighted shuffle playlist
    if config.playlists.output.shuffle.enabled:
        assert (
            config.playlists.output.shuffle.name
        ), "No shuffle playlist name provided in the config file."
        playlist_tracks = (
            playlist_loader.load(config.playlists.output.shuffle.parent_playlist)
            if config.playlists.output.shuffle.parent_playlist is not None
            else source_tracks
        )
        playlist_map[config.playlists.output.shuffle.name] = weighted_shuffle(
            playlist_tracks
        )

    # update generated playlists
    for playlist_name, tracks in playlist_map.items():
        sentinel_path = OUTPUT_DIR / f".{playlist_name}"
        if not sentinel_path.exists():
            overdue = True
        elif config.playlists.output.update_every is not None:
            time_since_update = NOW - dt.datetime.fromtimestamp(
                sentinel_path.stat().st_mtime
            )
            hours = time_since_update / ONE_HOUR
            logger.info(f"Time since last {playlist_name!r} update: {hours:.2f} hours")
            overdue = time_since_update > config.playlists.output.update_every
        else:
            overdue = False
        if overdue:
            logger.warning(f"{playlist_name!r} is overdue for update")
        if active:
            if config.playlists.output.force_update or overdue:
                update_playlist(
                    music_app=music_app,
                    source_tracks=tracks,
                    playlist_name=playlist_name,
                )
                # TODO: update the playlist description with date
                sentinel_path.parent.mkdir(parents=True, exist_ok=True)
                sentinel_path.touch()
            elif config.playlists.output.remove_only:
                # still remove unsynced tracks even if not updating the whole playlist
                remove_unsynced_tracks(music_app, tracks, playlist_name)
            wait_for_library_update()
            logger.info(dt.datetime.now() - NOW)

    # save data
    # TODO: show diff for total stats
    for stat_playlist in config.playlists.stats:
        tracks = playlist_loader.load(stat_playlist.name)
        if stat_playlist.save_totals:
            save_total_stats(
                tracks,
                subdir_name=stat_playlist.name,
                show_stats=stat_playlist.show_totals,
            )
        if stat_playlist.save_tracks:
            save_track_data(
                tracks,
                subdir_name=stat_playlist.name,
                show_diff=stat_playlist.show_track_diff,
            )
        if stat_playlist.save_collections:
            save_collection_stats(tracks, subdir_name=stat_playlist.name)
    if (
        config.playlists.output.shuffle.enabled
        and config.playlists.output.shuffle.save_tracks
    ):
        assert config.playlists.output.shuffle.name
        save_track_data(
            playlist_map[config.playlists.output.shuffle.name],
            subdir_name=config.playlists.output.shuffle.name,
            show_diff=False,
        )
    if (
        config.playlists.output.overdue.enabled
        and config.playlists.output.overdue.save_tracks
    ):
        assert config.playlists.output.overdue.name
        save_track_data(
            playlist_map[config.playlists.output.overdue.name],
            subdir_name=config.playlists.output.overdue.name,
            show_diff=False,
        )

    logger.info(dt.datetime.now() - NOW)

    # wait for library update to finish
    if active and config.sync.enabled:
        assert config.sync.iphone_name, "No iPhone name provided in the config file."
        # then sync again
        sync_device(config.sync.iphone_name)
        logger.info(dt.datetime.now() - NOW)


if __name__ == "__main__":
    cli.main()

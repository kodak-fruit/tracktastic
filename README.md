# Tracktastic

## Overview

This repository contains scripts to manage and update track ratings and playlists in your music library. The scripts are designed to work with iTunes/Music app on macOS and can sync with your iPhone.

## Files

- `config.toml.example`: Example configuration file. Copy this to `config.toml` and update the settings as needed.
- `music.py`: Core library containing the logic for processing tracks and updating ratings.
- `sync.py`: Script to sync your iPhone with iTunes/Music app.
- `update.py`: Script to update track ratings and playlists based on the configuration.
- `makefile`: Contains commands to set up the environment, run scripts, and lint the code.

## Setup

1. **Clone the repository:**
   ```sh
   git clone https://github.com/sherbet-refuser/tracktastic.git
   cd tracktastic
   ```

2. **Create and activate a virtual environment:**
   ```sh
   make env
   ```

3. **Copy the example configuration file and update it:**
   ```sh
   cp config.toml.example config.toml
   ```

4. **Edit `config.toml` to match your preferences:**
   - Set `source_playlist` to the name of the playlist you want to use for track ratings.
   - Set `iphone_name` to the name of your iPhone as it appears in Finder.
   - Adjust other settings as needed.

## Usage

### Update Track Ratings and Playlists

To dry-run the script and generate statistics for your library, run:
```sh
make update
```

### Sync iPhone

To sync your iPhone with iTunes/Music app, run:
```sh
make sync
```

### Active Mode

To run the update script in active mode (actually apply changes), use:
```sh
make update-active
```

## Configuration Options

### `config.toml`

- **Sync Settings:**
  - `enabled`: Enable or disable syncing.
  - `iphone_name`: Name of your iPhone as it appears in Finder.

- **Playlists Input:**
  - `source_playlist`: The source playlist to use for track ratings and favorites.
  - `subset_playlist`: Only the subset of tracks also in this playlist will be used when generating output playlists.
  - `save_stats`: Save statistics for every track in the source/subset playlists to JSON files in `output/`.

- **Album Ratings:**
  - `clear`: Clears the album rating for all albums in the entire library.

- **Track Ratings:**
  - `update`: Updates the rating for all tracks in the source playlist based on a calculated score.

- **Favorites:**
  - `update`: Updates the favorite status of all tracks in the source playlist.
  - `top_percent`: If a song has a calculated score within the top percent of the playlist, it is marked as a favorite.

- **Playlists Output:**
  - `force_update`: The playlists will be cleared and regenerated from scratch.
  - `update_every`: Playlists will only be updated if the last update was more than the specified duration ago.
  - `remove_only`: The songs not in the source will be removed, but it won't otherwise be updated.
  - `shuffle`: A generated playlist with the tracks shuffled, weighted by a calculated score.

- **Collections:**
  - `save_stats`: Save statistics for albums/artists/genres/etc. in the source playlist to JSON files in `output/`.
  - `playlist_folder`: Only stats for playlists in this folder will be calculated.

## License

This project is licensed under the MIT License.

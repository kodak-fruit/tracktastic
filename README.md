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

To dry-run the script and generate the statistics for your library, run:
```sh
make dry-run
```

### Active Mode

To run the update script and actually update iTunes, use:
```sh
make update
```

### Sync iPhone

To sync your iPhone with iTunes/Music app, run:
```sh
make sync
```

### Other

The `plot` and `insights` make targets expose additional python scripts, but these currently rely on hard-coded playlist names and may not work with other setups.

<!-- ## Configuration Options -->


## Calculated Track Score

This section explains the calculation process for determining the score of a music track based on various metrics such as play count, skip count, and time-based factors.

### Key Metrics

1. **Play Rate**: The average number of plays per unit time since the track was added.
   ```
   play_rate = play_count / duration_since_added
   ```

2. **Skip Rate**: The average number of skips per unit time since the track was added.
   ```
   skip_rate = skip_count / duration_since_added
   ```

3. **Listen Rate**: The total time spent listening to the track per unit time since it was added, normalized by the median song length.
   ```
   time_spent_listening = play_count * track_duration
   listen_rate = time_spent_listening / duration_since_added
   norm_listen_rate = listen_rate / median_song_length
   ```

4. **Net Rate**: A composite metric that combines play rate, normalized listen rate, and skip rate.
   ```
   net_rate = (play_rate + norm_listen_rate - skip_rate) / 2
   ```

## Time Between Plays and Overdue Duration

5. **Time Between Plays**: A representative value for the average duration between plays based on the net rate.
   ```
   time_between_plays = 1 / net_rate
   ```

6. **Overdue Duration**: The difference between the duration since the last interaction (either play or skip) and the expected duration between plays.
   ```
   duration_since_last_interaction = min(duration_since_last_played, duration_since_last_skipped)
   overdue_duration = duration_since_last_interaction - time_between_plays
   ```

7. **Overdue Factor**: The normalized ratio of the overdue duration to the expected duration between plays.
   ```
   overdue = overdue_duration / time_between_plays
   ```

The overdue factor measures how overdue a track is for being played again. Positive values indicates that a track has not been played for a longer time than expected based on its play rate. This metric has a minimum value of -1.

### Score Calculation

The final score is a logarithmic function of the net rate.
```
score = log_n(1 + net_rate)
```

Where:
- `n` is used to adjust the scaling of the score.

The score provides a relative measure of how often the track is played, taking into account how often it is played versus skipped, and adjusting for the time since it was added to the library.

The scaling value `n` is determined by finding that value forces the median score to equal 2.5. This helps create a (non-linear) range of values that are comparable to the (linear) 0-5 scale used for star ratings.

## Weighted Shuffle Algorithm

This section describes the weighted shuffle algorithm used for ordering a list of music tracks based on their individual scores and other influencing factors. The algorithm ensures that tracks with higher scores or positive attributes have a higher probability of appearing earlier in the shuffled list.

### Algorithm Description

1. **Prepare Weights**:
   - For each track, an initial weight is set to the track's score.
   - The weight is normalized by subtracting the minimum score of all the tracks and adding a small floor (0.01), to prevent negative and zero weights.
   - The weight is multiplied by `(1 + overdue)`.
   - If the track artist or genre is downranked, the weight is halved.
   - If the track is marked as a favorite, the weight is doubled.


2. **Shuffle Process**:
   - The total weight of all tracks is calculated.
   - A loop runs until all tracks have been shuffled:
     - A random value between 0 and the total weight is generated.
     - The algorithm iterates through the tracks and subtracts their respective weights from the random value until it reaches zero or below. The corresponding track is selected and removed from the list.
     - The weight of the selected track is subtracted from the total weight.
   - This process is repeated until all tracks have been selected and added to the shuffled list.

### Summary

The weighted shuffle algorithm provides a method for ordering tracks based on a combination of their scores, downranking, favorite status, and overdue factors. By adjusting the weights accordingly, the algorithm ensures a fair and dynamic shuffle that reflects the varying attributes of each track.

## Similarity Score Behavior

The similarity score is a measure that quantifies how similar two tracks are based on various attributes. The score ranges from 0 to 1, with 0 indicating no similarity and 1 indicating identical attributes. Here’s how the similarity score is determined:

1. **Album and Album Artist**:
   - If both tracks belong to the same album and have the same album artist, they are considered more similar.

2. **Genre**:
   - Tracks sharing the same genre are considered more similar.

3. **Year of Release**:
   - Track similarity scales with similar release years if they are within five years.

4. **Date Added**:
   - Tracks added to the library within six months of each other are considered more similar.

5. **Last Played Date**:
   - If both tracks were last played on the same day, they are considered more similar.

6. **Playlists**:
   - The more playlists the two tracks share, the higher their similarity.

7. **Compilation Status**:
   - If both tracks are part of a compilation, they are considered more similar.

8. **Duration**:
   - Track similar scales with similar durations if they are within one median song length.

<!-- TODO: discuss the other fields -->

The similarity score aggregates these individual factors, normalizing them to ensure the final score is between 0 and 1. This score helps in identifying tracks that have multiple shared attributes, which can be useful for creating cohesive playlists or recommendations.

## License

This project is licensed under the MIT License.

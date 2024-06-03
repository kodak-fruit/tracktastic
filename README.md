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


## Score Calculation for Music Tracks

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
   overdue_duration = duration_since_last_interaction - time_between_plays
   ```

7. **Overdue Factor**: The normalized ratio of the overdue duration to the expected duration between plays.
   ```
   overdue = overdue_duration / time_between_plays
   ```

#### Explanation of Overdue Factor

The overdue factor measures how overdue a track is for being played again. A higher overdue factor indicates that a track has not been played for a longer time than expected based on its play rate. This metric helps in identifying tracks that might need attention or re-evaluation, especially in creating playlists or deciding which tracks to promote or demote.

### Score Calculation

The final score is a logarithmic function of the net rate.
```
score = log_n(1 + net_rate)
```

Where:
- `n` is a predefined constant used to adjust the scaling of the score.

The score provides a quantitative measure of the track's popularity and engagement, taking into account how often it is played versus skipped, and adjusting for the time since it was added to the library.

## Weighted Shuffle Algorithm

This section describes the weighted shuffle algorithm used for ordering a list of music tracks based on their individual scores and other influencing factors. The algorithm ensures that tracks with higher scores or positive attributes have a higher probability of appearing earlier in the shuffled list.

### Algorithm Description

1. **Initialize Random Seed**:
   - A random seed is set based on the current day to ensure that the shuffle result remains consistent throughout the day.

2. **Prepare Weights**:
   - For each track, an initial weight is calculated based on the track's score. If a track has a score of zero, a predefined target median score is used instead.
   - The weight is then adjusted:
     - If the track is downranked, the weight is halved.
     - If the track is marked as a favorite, the weight is doubled.
   - Further adjustments are made based on the track's overdue factor, which measures how overdue the track is for being played. The weight is multiplied by `(1 + overdue factor)`.

3. **Normalize Weights**:
   - To avoid negative or zero weights, the smallest weight is identified, and a small floor value (e.g., 0.01) is added to each weight after subtracting the minimum weight from each.

4. **Shuffle Process**:
   - The total weight of all tracks is calculated.
   - A loop runs until all tracks have been shuffled:
     - A random value between 0 and the total weight is generated.
     - The algorithm iterates through the tracks and subtracts their respective weights from the random value until it reaches zero or below. The corresponding track is selected and removed from the list.
     - The weight of the selected track is subtracted from the total weight.
   - This process is repeated until all tracks have been selected and added to the shuffled list.

### Summary

The weighted shuffle algorithm provides a method for ordering tracks based on a combination of their scores, downranking, favorite status, and overdue factors. By adjusting the weights accordingly, the algorithm ensures a fair and dynamic shuffle that reflects the varying attributes of each track.

## License

This project is licensed under the MIT License.

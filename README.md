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


## Calculated Track Metrics

This section explains various metrics that are calculated for each track.

1. **Play Rate**: The average number of plays per unit time since the track was added.
   ```
   play_rate = play_count / duration_since_added
   ```

   The Play Rate is useful for finding favorite tracks because it doesn't suffer the same limitations of Play Count, which favors older tracks. The Play Rate will be elevated for both newer and older tracks in the library that are consistently listened to.

   It can conceptually be thought of as, e.g. "This song is played 5 times per year".

   The Play Rate will also naturally decay over time for tracks that are no longer listened to.

   However this metric tends to overweight shorter songs which may naturally have a higher play count than average.

2. **Listen Rate**: The total time spent listening to the track per unit time since it was added.
   ```
   time_spent_listening = play_count * track_duration
   listen_rate = time_spent_listening / duration_since_added
   ```

   Similar to the Play Rate, the Listen Rate can be conceptually interpretted as, e.g. "This song is played for 30 minutes per year".

   This metric provides a counterweight against the Play Rate, as it tends to overweight longer songs instead.

3. **Skip Rate**: The average number of skips per unit time since the track was added.
   ```
   skip_rate = skip_count / duration_since_added
   ```

4. **Net Rate**: A composite metric that combines play rate, normalized listen rate, and skip rate.
   ```
   norm_listen_rate = listen_rate / median_song_length
   net_rate = (play_rate + norm_listen_rate - skip_rate) / 2
   ```

   Averaging the Play Rate and Listen Rate provides a decent compromise between the tendency of each to overweight shorter/longer songs. To make their units compatible, the Listen Rate is normalized by the median song length.

   The median song length is calculated from the statistics generated from prior runs. If unavailable, a default value of approximately 3:45 is used.

   The Skip Rate also provides a signal that accelerates the decay of the Net Rate, although at a decreased effect compared to a playing.

5. **Score**: The score is a logarithmically scaled value of the Net Rate.
   ```
   score = log_n(1 + net_rate)
   ```
   Where:
   - `n` is used to adjust the scaling of the score.

   The scaling value `n` is determined by finding the value that forces the median score to equal 2.5. This helps create a (still non-linear) range of values that are comparable to the (linear) 0-5 scale used for star ratings.

   The Score is useful because it has a narrower range of values than the Net Rate and can be easier to interpret in user-facing applications. Because the use of the logarithm renders this value unitless, it is simply referred to as the "score".

6. **Track Rating**: The track rating is from the Music app and updated by this script based on the Score.

   Because the rating is fixed point and doesn't accept arbitrary fractional values, the rating is set by creating 100 equal-sized bins, populating them by traversing the tracks ordered by score, and setting the rating to the next available increment.

   This creates a truly linearized value from 0.05 to 5.00 based on the ordering.

7. **Time Between Plays**: A representative value for the average duration between plays based on the net rate.
   ```
   time_between_plays = 1 / net_rate
   ```

   The Time Between Plays provides an alternative interpretation of the Net Rate and is more well-behaved for highly played songs.

8. **Overdue Duration**: The difference between the duration since the last interaction (either play or skip) and the expected duration between plays.
   ```
   duration_since_last_interaction = min(duration_since_last_played, duration_since_last_skipped)
   overdue_duration = duration_since_last_interaction - time_between_plays
   ```

   The Overdue Duration represents how much time has passed since the track was expected to be interacted with again.

   Positive durations represent how overdue the user is in playing or skipping this track pas the Time Between Plays. Negative durations represent times in the future (e.g. -5 days means the track is expected to be played in 5 days.).

9. **Overdue Factor**: The normalized ratio of the overdue duration to the expected duration between plays.
   ```
   overdue = overdue_duration / time_between_plays
   ```

   The normalized overdue factor is useful when comparing relative values for different tracks, as the overdue duration may otherwise span a large range.

   This metric has a minimum value of -1 (for just played/skipped), a 0 value indicating , and an unbounded upper bound as the track becomes more overdue.

   Note: This value has some interesting dynamics in how it evolves over time, considering that durations affect both the numerator and denominator. However, for songs with a positive Net Rate, the overdue factor is always expected to become positive given enough time.

## Smart Shuffle Algorithm

This section describes the weighted shuffle algorithm used for ordering a list of tracks based on their metrics.

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

The smart shuffle provides a fair balance between how liked a track is and whether it is overdue to be played again. Even in cases where a selected track is skipped, this provides an aditional signal to update the score and overdue factor to help refine future selections.

## Similarity Score Behavior (WIP)

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

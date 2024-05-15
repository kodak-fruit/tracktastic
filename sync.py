#!/usr/bin/env python3


import logging

from music import CONFIG_PATH, Config, init_logger, sync_device

LOG_LEVEL = logging.INFO

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    init_logger(LOG_LEVEL)
    config = Config.from_toml(CONFIG_PATH)
    assert config.sync.iphone_name, "No iPhone name provided in the config file."
    sync_device(config.sync.iphone_name)

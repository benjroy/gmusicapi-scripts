#!/usr/bin/env bash

set -xe

VENV="./.env-gmusic-local"

python3 --version
python3 -m venv $VENV
source $VENV/bin/activate
which pip

./setup.py install

gmsync down --log --favorites "__favorites__" -p "../google_music/playlists" --removed "../google_music/removed" "../google_music/music/%artist%/%album%/%track2% - %title%"

deactivate

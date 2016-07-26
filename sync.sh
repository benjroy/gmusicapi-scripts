#!/usr/bin/env bash

set -xe

VENV="./.env-gmusic-local"

python3 --version
python3 -m venv $VENV
source $VENV/bin/activate
which pip

./setup.py install

gmsync down --log --favorites "__favorites1__" -p "./playlists" --removed "bizbaz" "./downloaded/%artist%/%album%/%track2% - %title%"

deactivate

#!/bin/bash

set -e

VENV="./.env-gmusic-local"

python3 --version
python3 -m venv $VENV
PATH=$VENV/bin:$PATH
source $VENV/bin/activate
which pip
#exit

python3 setup.py install

# python3 $VENV/bin/gmsync down --log --favorites "__favorites__" -p "/home/benjamin/media/4tb_ntfs/music/google_music/playlists" --removed "/home/benjamin/media/4tb_ntfs/music/google_music/removed" "/home/benjamin/media/4tb_ntfs/music/google_music/music/%artist%/%album%/%track2% - %title%"
python3 $VENV/bin/gmsync down --log --favorites "__favorites__" -p "/home/benjamin/media/4tb_ntfs/music/google_music/playlists" "/home/benjamin/media/4tb_ntfs/music/google_music/music/%artist%/%album%/%track2% - %title%"

deactivate

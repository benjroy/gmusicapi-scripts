#!/usr/bin/env python3
# coding=utf-8

"""
A sync script for Google Music using https://github.com/simon-weber/gmusicapi.
More information at https://github.com/thebigmunch/gmusicapi-scripts.

Usage:
  gmsync (-h | --help)
  gmsync up [-e PATTERN]... [-f FILTER]... [-F FILTER]... [options] [<input>]...
  gmsync down [-e PATTERN]... [-f FILTER]... [-F FILTER]... [options] [<output>]
  gmsync [-e PATTERN]... [-f FILTER]... [-F FILTER]... [options] [<input>]...

Commands:
  up                                    Sync local songs to Google Music. Default behavior.
  down                                  Sync Google Music songs to local computer.

Arguments:
  input                                 Files, directories, or glob patterns to upload.
										Defaults to current directory.
  output                                Output file or directory name which can include a template pattern.
										Defaults to name suggested by Google Music in your current directory.

Options:
  -h, --help                            Display help message.
  -c CRED, --cred CRED                  Specify oauth credential file name to use/create. [Default: oauth]
  -U ID --uploader-id ID                A unique id given as a MAC address (e.g. '00:11:22:33:AA:BB').
										This should only be provided when the default does not work.
  -l, --log                             Enable gmusicapi logging.
  -m, --match                           Enable scan and match.
  -d, --dry-run                         Output list of songs that would be uploaded.
  -q, --quiet                           Don't output status messages.
										With -l,--log will display gmusicapi warnings.
										With -d,--dry-run will display song list.
  --delete-on-success                   Delete successfully uploaded local files.
  -R, --no-recursion                    Disable recursion when scanning for local files.
										This is equivalent to setting --max-depth to 0.
  --max-depth DEPTH                     Set maximum depth of recursion when scanning for local files.
										Default is infinite recursion.
										Has no effect when -R, --no-recursion set.
  -e PATTERN, --exclude PATTERN         Exclude file paths matching pattern.
										This option can be set multiple times.
  -f FILTER, --include-filter FILTER    Include Google songs (download) or local songs (upload)
										by field:pattern filter (e.g. "artist:Muse").
										Songs can match any filter criteria.
										This option can be set multiple times.
  -F FILTER, --exclude-filter FILTER    Exclude Google songs (download) or local songs (upload)
										by field:pattern filter (e.g. "artist:Muse").
										Songs can match any filter criteria.
										This option can be set multiple times.
  -a, --all-includes                    Songs must match all include filter criteria to be included.
  -A, --all-excludes                    Songs must match all exclude filter criteria to be excluded.
  -p, --playlists						Output directory name for synced playlists.
										Sync Playlists to local files (download)
  -r, --removed 						Output directory name for removed files.
										Move local files removed from Google Music there (download).
  --favorites 							Name of Favorites playlist when syncing playlists.

Patterns can be any valid Python regex patterns.
"""

import logging
import os
import sys
import shutil
import tempfile
import json

from docopt import docopt

from gmusicapi_wrapper import MusicManagerWrapper
from gmusicapi_wrapper import MobileClientWrapper
from gmusicapi_wrapper.utils import compare_song_collections, template_to_filepath

from gmusicapi.utils import utils
from gmusicapi.clients import OAUTH_FILEPATH
from functools import reduce


QUIET = 25
logging.addLevelName(25, "QUIET")

logger = logging.getLogger('gmusicapi_wrapper')
sh = logging.StreamHandler()
logger.addHandler(sh)

def template_to_base_path(template, google_songs):
	"""Get base output path for a list of songs for download."""

	if template == os.getcwd() or template == '%suggested%':
		base_path = os.getcwd()
	else:
		template = os.path.abspath(template)
		song_paths = [template_to_filepath(template, song) for song in google_songs]
		base_path = os.path.dirname(os.path.commonprefix(song_paths))

	return base_path

def metadata_from_mobile_client_song (song):
	metadata = {}

	if song['artist']: metadata['artist'] = song['artist']
	if song['album']: metadata['album'] = song['album']
	if song['title']: metadata['title'] = song['title']
	if song['year']: metadata['date'] = song['year']
	if song['albumArtist']: metadata['albumartist'] = song['albumArtist']

	metadata['tracknumber'] = "{0}/{1}".format(song['trackNumber'], song['totalTrackCount'])
	metadata['discnumber'] = "{0}/{1}".format(song['discNumber'], song['totalDiscCount'])

	return metadata

def login_mobile_client(mcw):
	mcw.api.session._master_token = None
	mcw.api.session._authtoken = None
	mcw.api.android_id = None
	mcw.api.session.is_authenticated = False

	logger.info("Logging in to Mobile Client")

	username = input("Enter your Google username or email address: ")
	mcw.login(username=username)
	creds = {
		'masterToken': mcw.api.session._master_token,
		'authToken': mcw.api.session._authtoken,
		'email': username,
		'androidId': mcw.api.android_id
	}
	return creds

def login_mobile_client_from_cache(mcw, oauth_filename='oauth'):
	# mcw is MobileClientWrapper
	creds_filepath = os.path.join(os.path.dirname(OAUTH_FILEPATH), 'mc' + oauth_filename + '.cred')
	# fetch credentials from file
	try:
		logger.info("Trying stored credentials to log in to Mobile Client")
		with open(creds_filepath) as creds_file:
			creds = json.load(creds_file)
		logger.info(creds);
		# fake login
		mcw.api.session._master_token = creds['masterToken']
		mcw.api.session._authtoken = creds['authToken']
		mcw.api.android_id = creds['androidId']
		mcw.api.session.is_authenticated = True
	except:
		logger.info("Unable to load credentials file...")

	try:
		# test fake login with get_devices call
		devices = mcw.api.get_registered_devices()
		# logger.info(devices);
	except:
		creds = login_mobile_client(mcw);

	utils.make_sure_path_exists(os.path.dirname(creds_filepath), 0o700)
	with open(creds_filepath, 'w') as outfile:
		json.dump(creds, outfile)
	
	logger.info("Stored Mobile Client credentials")

def removeEmptyFolders(path, removeRoot=True):
	"""Function to remove empty folders inside"""
	if not os.path.isdir(path):
		return

	# remove empty subfolders
	files = os.listdir(path)
	if len(files):
		for f in files:
			fullpath = os.path.join(path, f)
			if os.path.isdir(fullpath):
				removeEmptyFolders(fullpath)

	# if folder empty, delete it
	files = os.listdir(path)
	if len(files) == 0 and removeRoot:
		print("Removing empty folder: {0}".format(path))
		os.rmdir(path)


def main():
	cli = dict((key.lstrip("-<").rstrip(">"), value) for key, value in docopt(__doc__).items())

	pp.pprint(cli);

	if cli['no-recursion']:
		cli['max-depth'] = 0
	else:
		cli['max-depth'] = int(cli['max-depth']) if cli['max-depth'] else float('inf')

	if cli['quiet']:
		logger.setLevel(QUIET)
	else:
		logger.setLevel(logging.INFO)

	if not cli['input']:
		cli['input'] = [os.getcwd()]

	if not cli['output']:
		cli['output'] = os.getcwd()

	include_filters = [tuple(filt.split(':', 1)) for filt in cli['include-filter']]
	exclude_filters = [tuple(filt.split(':', 1)) for filt in cli['exclude-filter']]

	mmw = MusicManagerWrapper(enable_logging=cli['log'])
	mmw.login(oauth_filename=cli['cred'], uploader_id=cli['uploader-id'])

	if not mmw.is_authenticated:
		sys.exit()

	mcw = MobileClientWrapper(enable_logging=cli['log'])

	if cli['playlists']:
		login_mobile_client_from_cache(mcw, oauth_filename=cli['cred'])

		if not mcw.is_authenticated:
			sys.exit()

	if cli['down']:
		matched_google_songs, filtered_google_songs = mmw.get_google_songs(
			include_filters=include_filters, exclude_filters=exclude_filters,
			all_includes=cli['all-includes'], all_excludes=cli['all-excludes']
		)

		cli['input'] = [template_to_base_path(cli['output'], matched_google_songs)]


		def download_songs(songs_to_download):
			if cli['dry-run']:
				logger.info("\nFound {0} song(s) to download".format(len(songs_to_download)))
				if songs_to_download:
					logger.info("\nSongs to download:\n")
					for song in songs_to_download:
						title = song.get('title', "<title>")
						artist = song.get('artist', "<artist>")
						album = song.get('album', "<album>")
						song_id = song['id']
						logger.log(QUIET, "{0} -- {1} -- {2} ({3})".format(title, artist, album, song_id))
				else:
					logger.info("\nNo songs to download")
			else:
				if songs_to_download:
					logger.info("\nDownloading {0} song(s) from Google Music\n".format(len(songs_to_download)))
					mmw.download(songs_to_download, template=cli['output'])
				else:
					logger.info("\nNo songs to download")

		def download_missing_google_songs(mmw_songs):
			# recheck the local songs after any previous sync
			matched_local_songs, __, __ = mmw.get_local_songs(cli['input'], exclude_patterns=cli['exclude'])
			logger.info("\nFinding missing songs...")
			songs_to_download = compare_song_collections(mmw_songs, matched_local_songs)
			songs_to_download.sort(key=lambda song: (song.get('artist'), song.get('album'), song.get('track_number')))
			return download_songs(songs_to_download)

		logger.info("\nFetching Library songs...")
		download_missing_google_songs(matched_google_songs)

		if cli['removed']:
			logger.info("Moving Removed songs...")
			# path to move songs removed from google music
			removed_dir = os.path.abspath(cli['removed'])
			# ensure directory is there
			utils.make_sure_path_exists(removed_dir, 0o700)
			# local songs after sync
			matched_local_songs, filtered_local_songs, excluded_local_songs = mmw.get_local_songs(cli['input'], exclude_patterns=cli['exclude'])
			all_local_songs = matched_local_songs + filtered_local_songs + excluded_local_songs
			all_google_songs = matched_google_songs + filtered_google_songs
			songs_to_move = compare_song_collections(all_local_songs, all_google_songs)

			for filepath in songs_to_move:
				rel_file_path = os.path.relpath(filepath, cli['input'][0])
				removed_filepath = os.path.join(removed_dir, rel_file_path)
				utils.make_sure_path_exists(os.path.dirname(removed_filepath), 0o700)
				logger.info("Removing {0}".format(rel_file_path))
				shutil.move(filepath, removed_filepath)

			# clean up empty folders
			logger.info(" ")
			removeEmptyFolders(cli['input'][0], False)

		if cli['playlists']:
			logger.info("Syncing playlists...")
			# get all songs from mobileClient api (to include ratings)
			all_songs = mcw.api.get_all_songs()
			# get id, prioritize trackId over id
			def songid (track):
				return track['trackId'] if 'trackId' in track else track['id']
			# create a dictionary of all fetched google songs, indexed by id
			def songs_to_dict (songs, song):
				id = songid(song)
				songs[id] = song
				return songs
			# create lookup dicts for tracks (mmw) and songs (mcw)
			songs_dict = reduce(songs_to_dict, all_songs, {})
			tracks_dict = reduce(songs_to_dict, matched_google_songs + filtered_google_songs, {})

			# returns music manager wrapper tracks for list of objects with song id or trackId
			#  also removes duplicates
			def get_mmw_tracks (songs):
				tracks = []
				seen = {}
				for song in songs:
					id = songid(song)
					if id not in seen:
						tracks.append(tracks_dict[id])
						seen[id] = True
				return tracks;

			# path to save playlists
			playlists_dir = os.path.abspath(cli['playlists'])
			# ensure directory is there
			utils.make_sure_path_exists(playlists_dir, 0o700)

			def create_playlist_file (name, songs, outpath):
				filename = os.path.join(outpath, name + '.m3u')

				if not cli['dry-run']:
					m3u = [u'#EXTM3U']
					for track in songs:
						id = songid(track)
						song = songs_dict[id]
						artist = song['artist']
						title = song['title']
						duration = str(int(int(song['durationMillis']) / 1000)) if 'durationMillis' in song else '0'
						metadata = metadata_from_mobile_client_song(song)
						songpath = template_to_filepath(cli['output'], metadata) + '.mp3'
						m3u.append(u'#EXTINF,' + duration + ',' + song['artist'] + ' - ' + song['title'])
						m3u.append(os.path.relpath(songpath, outpath))
					# write m3u file
					contentstr = u'\n'.join(m3u)
					# write to temp file
					with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as temp:
						temp.write(contentstr.encode('UTF-8-SIG'))
					# move tempfile into place
					shutil.move(temp.name, filename)

				logger.log(QUIET, "Playlist ({0} tracks): {1}".format(len(songs), filename))


			# get playlists with ordered lists of tracks
			playlists = mcw.api.get_all_user_playlist_contents()
			# concatenate all the playlist tracks into a single list
			playlist_tracks = reduce(lambda x, y: x + y, map(lambda x: x['tracks'], playlists)) if len(playlists) else []
			# remove duplicates and get mmw tracks to download
			playlist_tracks = get_mmw_tracks(playlist_tracks)
			# download any missing songs
			logger.info("\nFetching Playlist songs...")
			download_missing_google_songs(playlist_tracks)
			# create the m3u files for the playlists
			for playlist in playlists:
				create_playlist_file(playlist['name'], playlist['tracks'], playlists_dir)

			# create an m3u file for all favorited songs
			favorites_playlist_name = cli['favorites'] if 'favorites' in cli else '___auto_favorites___'
			# filter mobile client songs into favorites list
			thumbs_up = [t for t in all_songs if int(t['rating']) > 3]
			# most recent first
			thumbs_up.sort(key=lambda song: (int(song.get('lastModifiedTimestamp')) * -1))
			# get music_manager_wrapper style tracks to compare
			thumbs_up_tracks = get_mmw_tracks(thumbs_up)
			# download any missing favorited songs
			logger.info("\nFetching Favorited songs...")
			download_missing_google_songs(thumbs_up_tracks)
			# create favorites playlist
			create_playlist_file(favorites_playlist_name, thumbs_up, playlists_dir)

	else:
		matched_google_songs, _ = mmw.get_google_songs()

		logger.info("")

		matched_local_songs, songs_to_filter, songs_to_exclude = mmw.get_local_songs(
			cli['input'], include_filters=include_filters, exclude_filters=exclude_filters,
			all_includes=cli['all-includes'], all_excludes=cli['all-excludes'],
			exclude_patterns=cli['exclude'], max_depth=cli['max-depth']
		)

		logger.info("\nFinding missing songs...")

		songs_to_upload = compare_song_collections(matched_local_songs, matched_google_songs)

		# Sort lists for sensible output.
		songs_to_upload.sort()
		songs_to_exclude.sort()

		if cli['dry-run']:
			logger.info("\nFound {0} song(s) to upload".format(len(songs_to_upload)))

			if songs_to_upload:
				logger.info("\nSongs to upload:\n")

				for song in songs_to_upload:
					logger.log(QUIET, song)
			else:
				logger.info("\nNo songs to upload")

			if songs_to_filter:
				logger.info("\nSongs to filter:\n")

				for song in songs_to_filter:
					logger.log(QUIET, song)
			else:
				logger.info("\nNo songs to filter")

			if songs_to_exclude:
				logger.info("\nSongs to exclude:\n")

				for song in songs_to_exclude:
					logger.log(QUIET, song)
			else:
				logger.info("\nNo songs to exclude")
		else:
			if songs_to_upload:
				logger.info("\nUploading {0} song(s) to Google Music\n".format(len(songs_to_upload)))

				mmw.upload(songs_to_upload, enable_matching=cli['match'], delete_on_success=cli['delete-on-success'])
			else:
				logger.info("\nNo songs to upload")

				# Delete local files if they already exist on Google Music.
				if cli['delete-on-success']:
					for song in matched_local_songs:
						try:
							os.remove(song)
						except:
							logger.warning("Failed to remove {} after successful upload".format(song))

	mmw.logout()
	mcw.logout()
	logger.info("\nAll done!")


if __name__ == '__main__':
	main()

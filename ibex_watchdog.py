#!/usr/bin/python
import argparse
import logging

from ibex-backup import *

# Read options from command line
parser = argparse.ArgumentParser()
parser.add_argument('-n', '--dryrun',
                    help='Dry run',
                    action="store_true"
                    )
parser.add_argument('-s', '--settings',
                    help='Settings file',
                    type=str
                    )
args = parser.parse_args()

# Read settings from file
settings = {}
with open(args.settings, 'r') as f:
    for line in f:
        (key, val) = line.split('=')
        settings[str(key).strip()] = str(val).strip()

# Start logging
logging.basicConfig(
    filename=settings['logDir'] + '/ibex-watchdog.log',
    format='%(asctime)s:%(levelname)s:%(message)s',
    datefmt='%Y-%m-%d %T',
    level=logging.DEBUG
    )

logging.info('Starting watchdog run')

# Check for all settings
mandatory_settings = [
    'secondaryBaseDir',
    'offsiteBaseDir',
    'tempBaseDir',
    'logDir',
]

for m in mandatory_settings:
    if m not in settings or settings[m] == '':
        logging.critical('Setting "' + m + '" is missing!')
        sys.exit(1)

# Setup variables
# ---------------

# Misc
timeStamp = time.strftime("%Y-%m-%d_%H-%M-%S")
# Directories
secondaryBaseDir = settings['secondaryBaseDir']
offsiteBaseDir = settings['offsiteBaseDir']
tempBaseDir = settings['tempBaseDir']
watchDirs = next(os.walk(tempBaseDir))[1]
# Directories to check and create
criticalDirectories = [secondaryBaseDir, offsiteBaseDir, tempBaseDir]
# Status files
wdStatusFile = settings['tempBaseDir'] + '/status-watchdog'
# Monitor files
fullMonitorFile = settings['logDir'] + '/monitor-watchdog'

# Check if watchdog is already running


# Check configured directories for things to do
for directory in watchDirs:
    if os.path.isfile(wdStatusFile):
        status = checkStatus(wdStatusFile)

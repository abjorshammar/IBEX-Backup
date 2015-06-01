#!/usr/bin/python
import os
import errno
import sys
import time
import argparse
import logging
import shlex
from subprocess import Popen, PIPE, STDOUT

from ibex_func import *

# Read options from command line
parser = argparse.ArgumentParser()
parser.add_argument('backupType',
                    help='Type of backup to run',
                    type=str,
                    choices=['full', 'firstinc', 'inc', 'lastinc'],
                    default='/etc/ibex-backup/settings.conf'
                    )
parser.add_argument('-o', '--no-offsite',
                    help='Does not copy the archived backup offsite',
                    action="store_false"
                    )
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
    filename=settings['logDir'] + '/ibex-backup.log',
    format='%(asctime)s:%(levelname)s:%(message)s',
    datefmt='%Y-%m-%d %T',
    level=logging.DEBUG
    )

logging.info('Starting ' + args.backupType + ' backup run')

# Check for all settings
mandatory_settings = [
    'dbuser',
    'dbpass',
    'baseDir',
    'secondaryBaseDir',
    'offsiteBaseDir',
    'tempBaseDir',
    'logDir',
]

for m in mandatory_settings:
    if m not in settings or settings[m] == '':
        logging.critical('Setting "' + m + '" is missing!')
        sys.exit(1)

# Set defaults
if 'databaseDir' not in settings or settings['databaseDir'] == '':
    settings['databaseDir'] = '/var/lib/mysql'

if 'socketPath' not in settings or settings['socketPath'] == '':
    settings['socketPath'] = '/var/run/mysqld/mysqld.sock'


# Setup variables
# ---------------

# Database settings
dbuser = settings['dbuser']
dbpass = settings['dbpass']
# Misc
timeStamp = time.strftime("%Y-%m-%d_%H-%M-%S")
socketPath = settings['socketPath']
# Directories
databaseDir = settings['databaseDir']
baseDir = settings['baseDir']
secondaryBaseDir = settings['secondaryBaseDir']
offsiteBaseDir = settings['offsiteBaseDir']
tempBaseDir = settings['tempBaseDir']
tempDir = tempBaseDir + '/' + timeStamp
targetDir = baseDir + '/prepared/' + timeStamp
# Directories to check and create
criticalDirectories = [baseDir, secondaryBaseDir, offsiteBaseDir, tempBaseDir]
# Symbolic links
lastFull = baseDir + '/latest_full'
lastInc = baseDir + '/latest_inc'
# Status files
fullStatusFile = settings['logDir'] + '/status-full-backup'
incStatusFile = settings['logDir'] + '/status-inc-backup'
tempStatusFile = tempDir + '/status-watchdog'
# Monitor files
fullMonitorFile = settings['logDir'] + '/monitor-full-backup'
incMonitorFile = settings['logDir'] + '/monitor-inc-backup'


# Main
# ----

# Check some important dirs
logging.debug('Checking critical directories')

if args.dryrun:
    for directory in criticalDirectories:
        logging.info('Would have checked "' + directory + '"')
else:
    for directory in criticalDirectories:
        status = checkDirectory(directory)
        if status == 1:
            msg = 'Directory "' + directory + '" is missing, backup failed!'
            logging.critical(msg)
            if args.backupType == 'full':
                setMonitor(fullMonitorFile, 'critical', msg)
            else:
                setMonitor(incMonitorFile, 'critical', msg)
            sys.exit(1)


# Run backup
# ----------

# Full
if args.backupType == 'full':
    if not os.path.islink(lastFull):
        logging.warning('This seems like the first run, skipping latest_full link')
        # Check free space
        freeSpace = checkFreeSpace(databaseDir, baseDir, 1.5)
        freeSpaceSecondary = checkFreeSpace(databaseDir, secondaryBaseDir, 1.5)
        freeSpaceTemp = checkFreeSpace(databaseDir, tempBaseDir, 1.5)
    else:
        freeSpace = checkFreeSpace(lastFull, baseDir, 1.5)
        freeSpaceSecondary = checkFreeSpace(lastFull, secondaryBaseDir, 1.5)
        freeSpaceTemp = checkFreeSpace(lastFull, tempBaseDir, 1.5)
    if not freeSpace:
        msg = 'Not enough free space!'
        logging.critical(msg)
        setMonitor(fullMonitorFile, 'critical', msg)
        sys.exit(1)
    else:
        msg = None
        if not freeSpaceSecondary:
            msg = 'Not enough free space in secondary location!'
        if not freeSpaceTemp:
            msg = 'Not enough free space in temp location!'

        if msg:
            logging.warning(msg)
            setMonitor(fullMonitorFile, 'warning', msg)
            logging.debug('Starting full backup, not copying to secondary location!')

            status = fullBackup(copy=False)
        else:
            logging.debug('Starting full backup')
            status = fullBackup(copy=True)

        if status == 1:
            logging.debug('Setting status file to failed')
            setStatus(fullStatusFile, 'failed')
            msg = 'Full backup failed!'
            logging.critical(msg)
            setMonitor(fullMonitorFile, 'critical', msg)
            sys.exit(1)
        else:
            msg = 'Full backup sucessful'
            logging.info(msg)
            setMonitor(fullMonitorFile, 'ok', msg)
            sys.exit(0)
# Incremental
else:
    if not os.path.islink(lastInc):
        logging.warning('This seems like the first run, skipping latest_inc link')
        freeSpace = checkFreeSpace(databaseDir, baseDir, 1.5)
        freeSpaceSecondary = checkFreeSpace(databaseDir, secondaryBaseDir, 1.5)
    else:
        freeSpace = checkFreeSpace(lastInc, baseDir, 1.5)
        freeSpaceSecondary = checkFreeSpace(lastInc, secondaryBaseDir, 1.5)
    if not freeSpace:
        msg = 'Not enough free space!'
        logging.critical(msg)
        setMonitor(incMonitorFile, 'critical', msg)
        sys.exit(1)
    else:
        if not freeSpaceSecondary:
            msg = 'Not enough free space on secondary location!'
            logging.warning(msg)
            setMonitor(incMonitorFile, 'warning', msg)
            logging.debug('Starting incremental backup, not copying to secondary location!')
            copy = False
        else:
            copy = True
            # First incremental
            if args.backupType == 'firstinc':
                logging.debug('Starting first incremental backup')
                status = incBackup('first', copy=copy)
                if status == 1:
                    msg = 'First incremental backup failed!'
                    logging.critical(msg)
                    setMonitor(incMonitorFile, 'critical', msg)
                    sys.exit(1)
                else:
                    if copy is True:
                        msg = 'First incremental backup sucessful'
                        logging.info(msg)
                        setMonitor(incMonitorFile, 'ok', msg)
                    else:
                        msg = 'First incremental backup sucessful, without copy'
                        logging.warning(msg)
                        setMonitor(incMonitorFile, 'warning', msg)
                    sys.exit(0)
            # Normal incremental
            elif args.backupType == 'inc':
                logging.debug('Starting incremental backup')
                status = incBackup('normal', copy=copy)
                if status == 1:
                    msg = 'Incremental backup failed!'
                    logging.critical(msg)
                    setMonitor(incMonitorFile, 'critical', msg)
                    sys.exit(1)
                else:
                    if copy is True:
                        msg = 'Incremental backup sucessful'
                        logging.info(msg)
                        setMonitor(incMonitorFile, 'ok', msg)
                    else:
                        msg = 'Incremental backup sucessful, without copy'
                        logging.warning(msg)
                        setMonitor(incMonitorFile, 'warning', msg)
                    sys.exit(0)
            # Last incremental
            elif args.backupType == 'lastinc':
                logging.debug('Starting last incremental backup')
                status = incBackup('last', copy=copy, offsite=args.no_offsite)
                if status == 1:
                    msg = 'Last incremental backup failed!'
                    logging.critical(msg)
                    setMonitor(incMonitorFile, 'critical', msg)
                    sys.exit(1)
                else:
                    if copy is True:
                        msg = 'Last incremental backup sucessful'
                        logging.info(msg)
                        setMonitor(incMonitorFile, 'ok', msg)
                    else:
                        msg = 'Last incremental backup sucessful, without copy'
                        logging.warning(msg)
                        setMonitor(incMonitorFile, 'warning', msg)
                    sys.exit(0)
            # Somehow wrong type of backup
            else:
                msg = 'No proper backup type set!'
                logging.critical(msg)
                if args.backupType == 'full':
                    setMonitor(fullMonitorFile, 'critical', msg)
                else:
                    setMonitor(incMonitorFile, 'critical', msg)
                sys.exit(1)

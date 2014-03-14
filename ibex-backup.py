#!/usr/bin/python
import os
import errno
import sys
import time
import argparse
import logging
from subprocess import Popen, PIPE

# Read options from command line
parser = argparse.ArgumentParser()
parser.add_argument('backupType',
    help='Type of backup to run',
    type=str,
    choices=['full', 'firstinc', 'inc', 'lastinc'],
    default='/etc/ibex-backup/settings.conf'
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
    'logDir',
]

for m in mandatory_settings:
    if m not in settings or settings[m] == '':
        logging.critical('Setting "' + m + '" is missing!')
        sys.exit(1)


# Setup variables
dbuser = settings['dbuser']
dbpass = settings['dbpass']
timeStamp = time.strftime("%Y-%m-%d_%H-%M-%S")
baseDir = settings['baseDir']
secondaryBaseDir = settings['secondaryBaseDir']
offsiteBaseDir = settings['offsiteBaseDir']
targetDir = baseDir + '/prepared/' + timeStamp
lastFull = baseDir + '/latest_full'
lastInc = baseDir + '/latest_inc'
fullStatusFile = settings['logDir'] + '/status-full-backup'
incStatusFile = settings['logDir'] + '/status-inc-backup'

# Check some important dirs
logging.debug('Checking directories and links')
if not os.path.isdir(baseDir):
    logging.critical('BaseDir "' + baseDir + '" does not exist!')
    sys.exit(1)


# Functions
def checkFreeSpace(path, multiplicator):
    # Check the backup size
    du = Popen(['du', '-s', path], stdout=PIPE)
    output = du.communicate()[0]
    backupSize = output.split('\t')[0]

    # Check the partition free space
    df = Popen(['df', '-k', path], stdout=PIPE)
    output = df.communicate()[0]
    partitionSize = output.split()[-3]

    # Calculate the size needed
    spaceNeeded = int(backupSize) * multiplicator
    logging.debug('Space needed is: ' + str(spaceNeeded) + 'KB')
    logging.debug('Space available is: ' + str(partitionSize) + 'KB')

    if int(spaceNeeded) >= int(partitionSize):
        logging.debug('Space needed is more then space available')
        return False
    else:
        logging.debug('Space needed is less then space available')
        return True


def setStatus(statFile, status):
    try:
        with open(statFile, 'w') as stat:
            logging.debug('Writing "' + status + '" to "' + statFile + '"')
            stat.write(status)
        return
    except IOError:
        logging.critical('Unable to write "' + statFile + '" file')
        sys.exit(1)


def checkStatus(statFile):
    try:
        with open(statFile, 'r') as stat:
            logging.debug('Reading "' + statFile + '"')
            status = stat.readline().strip()
            logging.debug('Status: "' + status + '"')
        return status
    except IOError:
        logging.warning('Unable to read "' + statFile + '" file')
        return None


def fullBackup():
    status = checkStatus(fullStatusFile)
    if status == 'started':
        logging.critical('Last full backup still running?!')
        return 1

    setStatus(fullStatusFile, 'started')

    # Run the full backup
    cmd = "innobackupex --user={0} --password={1} --no-timestamp {2}/".format(dbuser, dbpass, targetDir)
    logging.debug('Backup command: "' + cmd + '"')

    # Copy the unprepared backup to secondary location
    cmd = "cp -a {0} {1}/".format(targetDir, secondaryBaseDir)
    logging.debug('Copy command: "' + cmd + '"')

    # Prepare the full backup
    cmd = "innobackupex --apply-log --redo-only {0}/".format(targetDir)
    logging.debug('Prepare command: "' + cmd + '"')

    # Create latest_full link
    try:
        logging.debug('Creating symlink: "' + targetDir + '" <- "' + lastFull +'"')
        os.symlink(targetDir, lastFull)
    except OSError, e:
        if e.errno == errno.EEXIST:
            logging.debug('Removing old symlink')
            os.remove(lastFull)
            logging.debug('Recreating symlink')
            os.symlink(targetDir, lastFull)

    setStatus(fullStatusFile, 'completed')

    return


def incBackup(incType):
    return


#
# Main
#

# Check what kind of backup we're running
if args.backupType == 'full':
    if not os.path.islink(lastFull):
        logging.warning('This seems like the first run, skipping latest_full link')
        freeSpace = checkFreeSpace(baseDir, 1.5)
    else:
        freeSpace = checkFreeSpace(lastFull, 1.5)
    if not freeSpace:
        logging.critical('Not enough free space!')
        sys.exit(1)
    else:
        logging.debug('Starting full backup')
        status = fullBackup()
        if status == 1:
            logging.critical('Full backup failed!')
            sys.exit(1)
        else:
            logging.info('Full backup sucessfull')
            sys.exit(0)
else:
    if not os.path.islink(lastInc):
        logging.warning('This seems like the first run, skipping latest_inc link')
        freeSpace = checkFreeSpace(baseDir, 1.5)
    else:
        freeSpace = checkFreeSpace(lastInc, 1.5)
    if not freeSpace:
        logging.critical('Not enough free space!')
        sys.exit(1)
    else:
        if args.backupType == 'firstinc':
            logging.debug('Starting first incremental backup')
            status = incBackup('first')
            if status == 1:
                logging.critical('First incremental backup failed!')
                sys.exit(1)
            else:
                logging.info('First incremental backup sucessfull')
                sys.exit(0)
        elif args.backupType == 'inc':
            logging.debug('Starting incremental backup')
            status = incBackup('normal')
            if status == 1:
                logging.critical('Incremental backup failed!')
                sys.exit(1)
            else:
                logging.info('Incremental backup sucessfull')
                sys.exit(0)
        elif args.backupType == 'lastinc':
            logging.debug('Starting last incremental backup')
            status = incBackup('last')
            if status == 1:
                logging.critical('Last incremental backup failed!')
                sys.exit(1)
            else:
                logging.info('Last incremental backup sucessfull')
                sys.exit(0)
        else:
            logging.critical('No proper backup type set!')
            sys.exit(1)

#!/usr/bin/python
import os
import sys
import argparse
import logging
import shlex
from subprocess import Popen, PIPE, STDOUT


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

logging.info('Starting watchdog')


# Check for all settings
mandatory_settings = [
    'secondaryBaseDir',
    'storageBaseDir',
    'offsiteBaseDir',
    'logDir',
]

for m in mandatory_settings:
    if m not in settings or settings[m] == '':
        logging.critical('Setting "' + m + '" is missing!')
        sys.exit(1)


# Setup variables
# ---------------

# Directories
secondaryBaseDir = settings['secondaryBaseDir']
offsiteBaseDir = settings['offsiteBaseDir']
storageBaseDir = settings['storageBaseDir']
# Directories to check and create
criticalDirectories = [secondaryBaseDir, storageBaseDir]
# Status files
copyStatusFile = 'copy-status'
# Misc
pidFile = '/tmp/ibex-watchdog.pid'


# Functions
# ---------

def checkDirectory(directory):
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
            logging.debug('Created "' + directory + '"')
            return 0
        except OSError:
            logging.critical('Unable to create "' + directory + '"!')
            return 1
    else:
        logging.debug('Directory "' + directory + '" already exists')
        return 0


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


def setStatus(statFile, status):

    # If dry run, return log statement
    if args.dryrun:
        logging.info('Would have written "' + status + '" to "' + statFile + '"')
        return 0

    try:
        with open(statFile, 'w') as stat:
            logging.debug('Writing "' + status + '" to "' + statFile + '"')
            stat.write(status)
        return
    except IOError:
        logging.critical('Unable to write "' + statFile + '" file')
        os.unlink(pidFile)
        sys.exit(1)


def runCommand(command):

    # If dry run, just return the command
    if args.dryrun:
        logging.info('Would run command: "' + command + '"')
        return 0

    cmd = shlex.split(command)
    logging.debug('Running command: "' + command + '"')

    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    for line in proc.stderr:
        logging.warning(str(line.strip()))

    for line in proc.stdout:
        logging.debug(str(line.strip()))

    proc.wait()

    if proc.returncode != 0:
        logging.critical('Command failed with return code "' + str(proc.returncode) + '"')
        return 1
    else:
        logging.debug('Command successfully finished with returncode "' + str(proc.returncode) + '"')
        return 0


def getOrSetPid(pidFile):
    pid = str(os.getpid())

    if os.path.isfile(pidFile):
        logging.info(pidFile + ' already exists, exiting')
        sys.exit(0)
    else:
        logging.debug('Creating pid file: ' + pidFile)
        file(pidFile, 'w').write(pid)
        return

# Main
# ----

# Check if watchdog is already running
logging.debug('Checking if watchdog is already running')
getOrSetPid(pidFile)

# Check some important dirs
logging.debug('Checking critical directories')

if args.dryrun:
    for directory in criticalDirectories:
        logging.info('Would have checked "' + directory + '"')
else:
    for directory in criticalDirectories:
        status = checkDirectory(directory)
        if status == 1:
            msg = 'Directory "' + directory + '" is missing, watchdog failed!'
            logging.critical(msg)
            os.unlink(pidFile)
            sys.exit(1)

# Check for directories in secondaryBaseDir
logging.info('Looking for directories to work on')
secondaryDirectories = next(os.walk(secondaryBaseDir))[1]
if secondaryDirectories:
    logging.info('Found ' + str(len(secondaryDirectories)) + ' directories')
    logging.debug(str(secondaryDirectories))
    for directory in secondaryDirectories:
        currentDir = secondaryBaseDir + '/' + directory
        currentStatusFile = currentDir + '/' + copyStatusFile
        storageStatusFile = storageBaseDir + '/' + directory + '/' + copyStatusFile

        # Check the status file of current directory
        fileStatus = checkStatus(currentStatusFile)
        if fileStatus == 'ready':
            # Copy the unprepared backup to storage location
            logging.info('Copying "' + directory + '" to "' + storageBaseDir + '"')
            setStatus(currentStatusFile, 'moving')
            command = "cp -a {0} {1}/".format(currentDir, storageBaseDir)
            status = runCommand(command)
            if status == 1:
                logging.critical('Copy failed!')
                setStatus(currentStatusFile, 'move failed')
                os.unlink(pidFile)
                sys.exit(1)
            else:
                setStatus(storageStatusFile, 'ok')
                # Time to remove the backup from secondaryBaseDir
                logging.info('Removing "' + currentDir + '"')
                command = "rm -rf {0}".format(currentDir)
                status = runCommand(command)
                if status == 1:
                    logging.critical('Removal failed!')
                    setStatus(currentStatusFile, 'removal failed')
                    os.unlink(pidFile)
                    sys.exit(1)
        else:
            logging.info('Directory not ready to be moved, waiting')
else:
    logging.info('No directories found, nothing to do')

os.unlink(pidFile)
sys.exit(0)

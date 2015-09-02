#!/usr/bin/python
import os
import sys
import time
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
    filename=settings['logDir'] + '/ibex-archiver.log',
    format='%(asctime)s:%(levelname)s:%(message)s',
    datefmt='%Y-%m-%d %T',
    level=logging.DEBUG
    )

logging.info('Starting archiver')


# Check for all settings
mandatory_settings = [
    'incomingBaseDir',
    'archiveBaseDir',
    'logDir',
]

for m in mandatory_settings:
    if m not in settings or settings[m] == '':
        logging.critical('Setting "' + m + '" is missing!')
        sys.exit(1)


# Setup variables
# ---------------

# Directories
incomingBaseDir = settings['incomingBaseDir']
archiveBaseDir = settings['archiveBaseDir']
if settings['offsiteBaseDir']:
    offsiteBaseDir = settings['offsiteBaseDir']

# Directories to check and create
criticalDirectories = [incomingBaseDir, archiveBaseDir]
# Status files
copyStatusFile = 'copy-status'
# Monitor files
monitorFile = settings['logDir'] + '/monitor-archiver'
# Misc
pidFile = '/tmp/ibex-archiver.pid'
errorDict = {'Failed mvs': 0, 'Failed rms': 0}


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


def setMonitor(monitorFile, status, message):

    # Get a current timestamp
    currentTimeStamp = time.strftime("%Y-%m-%d_%H-%M-%S")

    # Line to be put in to monitor file
    line = "{0}:{1}:{2}\n".format(currentTimeStamp, status.upper(), message)

    # If dry run, return log statement
    if args.dryrun:
        logging.info('Would have written "' + line + '" to "' + monitorFile + '"')
        return 0

    try:
        with open(monitorFile, 'a') as f:
            logging.debug('Writing "' + line + '" to "' + monitorFile + '"')
            f.write(line)
        return
    except IOError:
        logging.critical('Unable to write to"' + monitorFile + '"')
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


def updateMonitorFile(monitorFile, errorDict):
    status = 'ok'
    msg = []
    for key in errorDict:
        if errorDict[key] is not 0:
            status = 'critical'
        msg.append(key + ':' + str(errorDict[key]))

    msg = ' '.join(msg)
    setMonitor(monitorFile, status, msg)


# Main
# ----

# Check if archiver is already running
logging.debug('Checking if archiver is already running')
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
            msg = 'Directory "' + directory + '" is missing, archiver failed!'
            logging.critical(msg)
            os.unlink(pidFile)
            sys.exit(1)

# Check for directories in incomingBaseDir
logging.info('Looking for directories to work on')
incomingDirectories = next(os.walk(incomingBaseDir))[1]
if incomingDirectories:
    logging.info('Found ' + str(len(incomingDirectories)) + ' directories')
    logging.debug(str(incomingDirectories))
    for directory in incomingDirectories:
        currentDir = incomingBaseDir + '/' + directory
        currentStatusFile = currentDir + '/' + copyStatusFile

        # Check the status file of current directory
        fileStatus = checkStatus(currentStatusFile)
        if fileStatus == 'ready':
            # Compress the current directory to archive directory
            logging.info('Compressing "' + directory + '"')
            setStatus(currentStatusFile, 'compressing')
            tarball = "{0}/{1}.tar.bz2".format(archiveBaseDir, directory)
            command = "tar caf {0} {1}".format(tarball, currentDir)
            status = runCommand(command)
            if status == 1:
                logging.critical('Compression failed!')
                setStatus(currentStatusFile, 'compression failed')
                os.unlink(pidFile)
                sys.exit(1)
            else:
                # Are we copying the tarball to offsite storage?
                if offsiteBaseDir:
                    logging.info('Copying tarball to "' + offsiteBaseDir + '"')
                    setStatus(currentStatusFile, 'copying offsite')
                    command = "rsync -rlv --bwlimit=5000 {0} {1}/".format(tarball, offsiteBaseDir)
                    status = runCommand(command)
                    if status == 1:
                        logging.critical('Copying offsite failed!')
                        setStatus(currentStatusFile, 'copying offsite failed')
                        os.unlink(pidFile)
                        sys.exit(1)

                # Time to remove the backup from incomingBaseDir
                logging.info('Removing "' + currentDir + '"')
                command = "rm -rf {0}".format(currentDir)
                status = runCommand(command)
                if status == 1:
                    logging.critical('Removal failed!')
                    setStatus(currentStatusFile, 'removal failed')
                    os.unlink(pidFile)
                    sys.exit(1)

        elif fileStatus == 'compression failed':
            errorDict['Failed mvs'] += 1
            logging.warning('Directory compression failed, ignoring')

        elif fileStatus == 'copying offsite failed':
            errorDict['Failed mvs'] += 1
            logging.warning('Tarball offsite copy failed, ignoring')

        elif fileStatus == 'removal failed':
            errorDict['Failed rms'] += 1
            logging.warning('Directory removal failed, ignoring')

        else:
            logging.info('Directory not ready to be archived, waiting')

else:
    logging.info('No directories found, nothing to do')

# Update the monitor file
updateMonitorFile(monitorFile, errorDict)

os.unlink(pidFile)
sys.exit(0)

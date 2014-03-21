#!/usr/bin/python
import os
import errno
import sys
import time
import argparse
import logging
import shlex
from subprocess import Popen, PIPE, STDOUT

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
    action="store_true"
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
offsite = args.no_offsite
# Directories
databaseDir = settings['databaseDir']
baseDir = settings['baseDir']
secondaryBaseDir = settings['secondaryBaseDir']
offsiteBaseDir = settings['offsiteBaseDir']
targetDir = baseDir + '/prepared/' + timeStamp
# Directories to check and create
criticalDirectories = [baseDir, secondaryBaseDir, offsiteBaseDir]
# Symbolic links
lastFull = baseDir + '/latest_full'
lastInc = baseDir + '/latest_inc'
# Status files
fullStatusFile = settings['logDir'] + '/status-full-backup'
incStatusFile = settings['logDir'] + '/status-inc-backup'


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


def checkFreeSpace(path, partition, multiplicator):
    # Check the backup size
    path = path + '/'
    du = Popen(['du', '-s', path], stdout=PIPE)
    output = du.communicate()[0]
    backupSize = output.split('\t')[0]

    # Check the partition free space
    df = Popen(['df', '-k', partition], stdout=PIPE)
    output = df.communicate()[0]
    partitionFreeSpace = output.split()[-3]

    # Calculate the size needed
    spaceNeeded = int(backupSize) * multiplicator
    logging.debug('Space needed on "' + partition + '" is: ' + str(spaceNeeded) + 'KB')
    logging.debug('Space available is: ' + str(partitionFreeSpace) + 'KB')

    if int(spaceNeeded) >= int(partitionFreeSpace):
        logging.debug('Space needed is more then space available')
        return False
    else:
        logging.debug('Space needed is less then space available')
        return True


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


def runCommandWithOutput(command):

    cmd = shlex.split(command)
    logging.debug('Running command: "' + command + '"')

    proc = Popen(cmd, stdout=PIPE, stderr=STDOUT)
    output = proc.communicate()[0].strip()

    if proc.returncode != 0:
        logging.critical('Command failed with return code "' + str(proc.returncode) + '"')
        logging.critical(str(output.strip()))
        returnval = 1
    else:
        logging.debug('Command successfully finished with returncode "' + str(proc.returncode) + '"')
        logging.debug('Command output "' + str(output) + '"')
        returnval = 0

    return (output, returnval)


def checkBackup(checkType):
    if checkType == 'backupType':
        backupTypeCommand = "grep backup_type {0}/xtrabackup_checkpoints".format(lastFull)
        result = runCommandWithOutput(backupTypeCommand)
        status = result[1]
        if status != 0:
            return False
        else:
            check = result[0].split(' = ')[1]

        if check != 'full-prepared':
            return False
        else:
            return True

    elif checkType == 'lsn':
        fullLsnCommand = "grep to_lsn {0}/xtrabackup_checkpoints".format(lastFull)
        result = runCommandWithOutput(fullLsnCommand)
        status = result[1]
        if status != 0:
            return False
        else:
            fullLsn = result[0].split(' = ')[1]

        incLsnCommand = "grep to_lsn {0}/xtrabackup_checkpoints".format(lastInc)
        result = runCommandWithOutput(incLsnCommand)
        status = result[1]
        if status != 0:
            return False
        else:
            incLsn = result[0].split(' = ')[1]

        logging.debug('Full backup LSN "' + str(fullLsn) + '"')
        logging.debug('Incremental backup LSN "' + str(incLsn) + '"')

        if fullLsn == incLsn:
            return True
        else:
            return False

    else:
        return False


def fullBackup(copy):
    status = checkStatus(fullStatusFile)
    if status == 'started':
        logging.critical('Last full backup still running?!')
        return 1

    setStatus(fullStatusFile, 'started')

    # Run the full backup
    logging.info('Running backup')
    command = "innobackupex --user={0} --password={1} --socket={2} --no-timestamp {3}/".format(dbuser, dbpass, socketPath, targetDir)
    status = runCommand(command)
    if status == 1:
        return 1

    # Copy the unprepared backup to secondary location
    logging.info('Copying backup to secondary location')
    if copy:
        command = "cp -a {0} {1}/".format(targetDir, secondaryBaseDir)
        status = runCommand(command)
        if status == 1:
            return 1
    else:
        logging.warning('Skipping copy to secondary location, not enough free space!')

    # Prepare the full backup
    logging.info('Preparing backup')
    command = "innobackupex --apply-log --redo-only {0}/".format(targetDir)
    status = runCommand(command)
    if status == 1:
        return 1

    # Create latest_full link
    if args.dryrun:
        logging.info('Would have created symlink "' + targetDir + '" <- "' + lastFull +'"')
    else:
        try:
            logging.debug('Creating symlink: "' + targetDir + '" <- "' + lastFull +'"')
            os.symlink(targetDir, lastFull)
        except OSError as exception:
            if exception.errno == errno.EEXIST:
                logging.debug('Removing old symlink')
                os.remove(lastFull)
                logging.debug('Recreating symlink')
                os.symlink(targetDir, lastFull)

    setStatus(fullStatusFile, 'completed')

    return 0


def incBackup(incType, copy=True, offsite=True):
    status = checkStatus(incStatusFile)
    if status == 'started':
        logging.critical('Last inc backup still running?!')
        return 1

    if incType == 'first':
        incBaseDir = lastFull
        if not checkBackup('backupType'):
            logging.critical('Full backup is not fully prepared!')
            return 1
    else:
        incBaseDir = lastInc
        if not checkBackup('lsn'):
            logging.critical('Last backup is not fully prepared!')
            return 1

    setStatus(incStatusFile, 'started')

    # Run the incremental backup
    logging.info('Running backup')
    command = "innobackupex --user={0} --password={1} --socket={2} --incremental {3} --incremental-basedir={4}/ --no-timestamp".format(dbuser, dbpass, socketPath, targetDir, incBaseDir)
    status = runCommand(command)
    if status == 1:
        return 1

    # Copy the unprepared backup to secondary location
    logging.info('Copying backup to secondary location')
    if copy:
        command = "cp -a {0} {1}/".format(targetDir, secondaryBaseDir)
        status = runCommand(command)
        if status == 1:
            return 1
    else:
        logging.warning('Skipping copy to secondary location, not enough free space!')

    # Prepare the incremental backup
    logging.info('Preparing backup')
    if incType == 'lastinc':
        command = "innobackupex --apply-log {0}/ --incremental-dir={1}/".format(lastFull, targetDir)
    else:
        command = "innobackupex --apply-log --redo-only {0}/ --incremental-dir={1}/".format(lastFull, targetDir)
    status = runCommand(command)
    if status == 1:
        return 1

    # Create latest_inc link
    if args.dryrun:
        logging.info('Would have created symlink "' + targetDir + '" <- "' + lastInc +'"')
    else:
        try:
            logging.debug('Creating symlink: "' + targetDir + '" <- "' + lastInc +'"')
            os.symlink(targetDir, lastInc)
        except OSError as exception:
            if exception.errno == errno.EEXIST:
                logging.debug('Removing old symlink')
                os.remove(lastInc)
                logging.debug('Recreating symlink')
                os.symlink(targetDir, lastInc)

    if args.backupType == 'lastinc':
        # Get name of full backup
        logging.debug('Getting name of full backup')
        command = "readlink {0}".format(lastFull)
        result = runCommandWithOutput(command)
        status = result[1]
        if status != 0:
            return 1
        else:
            fullName = result[0].split('/')[-1]

        logging.debug('Full backup name: "' + fullName + '"')

        # Prepare the full backup
        logging.info('Preparing full backup')
        command = "innobackupex --apply-log {0}/".format(lastFull)
        status = runCommand(command)
        if status == 1:
            return 1

        # Tar and compress newly prepared full backup
        freeSpace = checkFreeSpace(lastFull, baseDir, 1)
        if not freeSpace:
            logging.warning('Not enough free space, skipping archiving!')
            return 1

        logging.info('Archiving full backup')
        tarball = "{0}/prepared/{1}.tar.bz2".format(baseDir, fullName)
        command = "tar caf {0} {1}/prepared/{2}".format(tarball, baseDir, fullName)
        status = runCommand(command)
        if status == 1:
            return 1

        if offsite:
            if args.dryrun:
                freeSpace = checkFreeSpace(lastFull, baseDir, 1)
            else:
                freeSpace = checkFreeSpace(tarball, offsiteBaseDir, 1)

            if not freeSpace:
                logging.warning('Not enough free space, not moving archive!')
                return 1

            # Move newly created tar.gz-file to online share
            command = "mv {0} {1}/".format(tarball, offsiteBaseDir)
            status = runCommand(command)
            if status == 1:
                return 1
        else:
            logging.warning('Skipping move to offsfite location')

    setStatus(incStatusFile, 'completed')

    return 0


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
            logging.critical('Backup failed!')
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
    else:
        freeSpace = checkFreeSpace(lastFull, baseDir, 1.5)
        freeSpaceSecondary = checkFreeSpace(lastFull, secondaryBaseDir, 1.5)
    if not freeSpace:
        logging.critical('Not enough free space!')
        sys.exit(1)
    else:
        if not freeSpaceSecondary:
            logging.warning('Not enough free space on secondary location!')
            logging.debug('Starting full backup, not copying to secondary location!')
            status = fullBackup(copy=False)
        else:
            logging.debug('Starting full backup')
            status = fullBackup(copy=True)

        if status == 1:
            logging.debug('Setting status file to failed')
            setStatus(fullStatusFile, 'failed')
            logging.critical('Full backup failed!')
            sys.exit(1)
        else:
            logging.info('Full backup sucessful')
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
        logging.critical('Not enough free space!')
        sys.exit(1)
    else:
        if not freeSpaceSecondary:
            logging.warning('Not enough free space on secondary location!')
            logging.debug('Starting incremental backup, not copying to secondary location!')
            copy = False
        else:
            copy = True
            # First incremental
            if args.backupType == 'firstinc':
                logging.debug('Starting first incremental backup')
                status = incBackup('first', copy=copy)
                if status == 1:
                    logging.critical('First incremental backup failed!')
                    sys.exit(1)
                else:
                    logging.info('First incremental backup sucessful')
                    sys.exit(0)
            # Normal incremental
            elif args.backupType == 'inc':
                logging.debug('Starting incremental backup')
                status = incBackup('normal', copy=copy)
                if status == 1:
                    logging.critical('Incremental backup failed!')
                    sys.exit(1)
                else:
                    logging.info('Incremental backup sucessful')
                    sys.exit(0)
            # Last incremental
            elif args.backupType == 'lastinc':
                logging.debug('Starting last incremental backup')
                status = incBackup('last', copy=copy)
                if status == 1:
                    logging.critical('Last incremental backup failed!')
                    sys.exit(1)
                else:
                    logging.info('Last incremental backup sucessful')
                    sys.exit(0)
            # Somehow wrong type of backup
            else:
                logging.critical('No proper backup type set!')
                sys.exit(1)

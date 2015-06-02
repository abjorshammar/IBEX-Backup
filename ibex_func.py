#!/usr/bin/python
import os
import errno
import sys
import time
import argparse
import logging
import shlex
from subprocess import Popen, PIPE, STDOUT


# Functions

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
    # Check if the path is a path or file
    if os.path.isfile(path):
        if not os.path.islink(path):
            logging.debug(path + ' is a file')
        else:
            path = path + '/'
    else:
        path = path + '/'

    # Check the backup size
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


def setStatus(dryRun=True, statFile, status):

    # If dry run, return log statement
    if dryRun:
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


def fullBackup(copy=False, targetDir, fullStatusFile, tempStatusFile, ):
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

    # Copy the unprepared backup to temp location
    logging.info('Copying backup to temp location')
    if copy:
        setStatus(tempStatusFile, 'copying')
        command = "cp -a {0} {1}/".format(targetDir, tempBaseDir)
        status = runCommand(command)
        if status == 1:
            return 1
        else:
            setStatus(tempStatusFile, 'ok')
    else:
        logging.warning('Skipping copy to temp location, not enough free space!')

    # Prepare the full backup
    logging.info('Preparing backup')
    command = "innobackupex --apply-log --redo-only {0}/".format(targetDir)
    status = runCommand(command)
    if status == 1:
        return 1

    # Create latest_full link
    if args.dryrun:
        logging.info('Would have created symlink "' + targetDir + '" <- "' + lastFull + '"')
    else:
        try:
            logging.debug('Creating symlink: "' + targetDir + '" <- "' + lastFull + '"')
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
        logging.info('Would have created symlink "' + targetDir + '" <- "' + lastInc + '"')
    else:
        try:
            logging.debug('Creating symlink: "' + targetDir + '" <- "' + lastInc + '"')
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
        else:
            setStatus(incStatusFile, 'completed')

        if offsite:
            logging.info('Moving archive to offsite location')
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
                logging.debug('Move successful')
        else:
            logging.warning('Skipping move to offsite location')

    setStatus(incStatusFile, 'completed')

    return 0

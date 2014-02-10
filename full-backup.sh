#!/bin/bash
#
# full-backup.sh - This script will: 
# 1. Create a full backup in to a timestamped folder
# 2. Copy the full backup to a secondary location
# 3. "Prepare" the copy to be a restorable backup
#

# Setup variables
_dbUser=""
_dbPass=""
_backupBaseDir=""
_secondaryBackupBaseDir=""
_timestamp=`date +"%d-%m-%Y_%T"`
_targetDir="${_backupBaseDir}/prepared/${_timestamp}"

printf "Backup started ${_targetDir}\n"

# Run the full backup
printf "Running full backup...\n\n"
innobackupex --user=${_dbUser} --password=${_dbPass} --no-timestamp ${_targetDir} ; _status=$?

if [ ${_status} != "0" ]; then
	printf "\nBackup failed!\n"
	printf "Backup finished ${_timestamp}\n"
	exit 1
else
	printf "\nFull backup done\n"

# Copy the full backup to secondary location
printf "Copying full backup to secondary location..."
cp -a ${_targetDir} ${_secondaryBackupBaseDir} ; _status=$?

if [ ${_status} != "0" ]; then
	printf "\nCopy failed!\n"
	printf "Backup finished ${_timestamp}\n"
	exit 1
else
	printf "done\n"

# Prepare the full backup
printf "Preparing full backup ${_timestamp}\n"
innobackupex --apply-log --redo-only ${_targetDir}/ ; _status=$?

if [ ${_status} != "0" ]; then
	printf "\nPreparation failed!\n"
	printf "Backup finished ${_timestamp}\n"
	exit 1
else
	printf "\nPreparation done\n"

# Create latest_full link
printf "Creating link..."
ln -s ${_targetDir} ${_backupBaseDir}/latest_full ; _status=$?

if [ ${_status} != "0" ]; then
	printf "failed!\n"
	printf "Backup finished ${_timestamp}\n"
	exit 1
else
	printf "done\n"

# Backup finished
printf "\nBackup finished ${_timestamp}\n"
exit 0
#!/bin/bash
#
# incremental-backup.sh - This script will: 
# 1. Create a full backup in to a timestamped folder
# 2. Copy the full backup to a secondary location
# 3. "Prepare" the copy to be a restorable backup
#

# Setup variables
_dbUser=""
_dbPass=""
_backupBaseDir=""
_secondaryBackupBaseDir=""
_tertiaryBackupBaseDir=""
_timestamp=`date +"%d-%m-%Y_%H-%M-%S"`
_targetDir="${_backupBaseDir}/prepared/${_timestamp}"

# Functions
function usage {
	printf "\n\tUsage:\n"
	printf -- "\tincremental-backup.sh -[fnl]\n"
	printf "\n\tOptions:\n"
	printf -- "\t-f\tFirst incremental backup\n"
	printf -- "\t-n\tNormal incremental backup\n"
	printf -- "\t-l\tLast incremental backup\n"
	printf "\n"
}

# Main backup function, needs the backup and incremental basedirs as an arguments
function runBackup {

	# Check for arguments
	if [ -z "$1" ]; then
		printf "No backup basedir provided!\n\n"
		exit 1
	fi
	if [ -z "$2" ]; then
		printf "No incremental basedir provided!\n\n"
		exit 1
	fi
	if [ -z "$3" ]; then
		local _last="false"
	else
		local _last="true"
	fi

	# Set variables
	local _baseDir="$1"
	local _incBaseDir="$2"
	local _fullBaseDir="${_baseDir}/latest_full"

	# Run backup
	printf "Running incremental backup...\n\n"
	innobackupex --user=${_dbUser} --password=${_dbPass} --incremental ${_targetDir} --incremental-basedir=${_incBaseDir}/ --no-timestamp ; _status=$?

	if [ ${_status} != "0" ]; then
		printf "\nIncremental backup failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "\nIncremental backup done\n"
	fi

	# Copy the incremental backup to secondary location
	printf "Copying incremental backup to secondary location..."
	cp -a ${_targetDir} ${_secondaryBackupBaseDir}/ ; _status=$?
	
	if [ ${_status} != "0" ]; then
		printf "\nCopy failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "done\n"
	fi
	
	# Prepare the full backup
	if [ ${_last} == "true" ]; then
		printf "Preparing final incremental backup\n"
		innobackupex --apply-log ${_fullBaseDir}/ --incremental-dir=${_targetDir}/ ; _status=$?
	else
		printf "Preparing incremental backup\n"
		innobackupex --apply-log --redo-only ${_fullBaseDir}/ --incremental-dir=${_targetDir}/ ; _status=$?
	fi
	
	if [ ${_status} != "0" ]; then
		printf "\nPreparation failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "\nPreparation done\n"
	fi
	
	# Create latest_inc link
	printf "Creating link..."
	if [ -a ${_baseDir}/latest_inc ]; then
		rm ${_baseDir}/latest_inc
		printf "removed old..."
	fi
	
	ln -s ${_targetDir} ${_baseDir}/latest_inc ; _status=$?
	
	if [ ${_status} != "0" ]; then
		printf "failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "done\n"
	fi

	return 0
}

function firstBackup {
	printf "Backup started `date +"%d-%m-%Y_%T"`\n"

	# Setup variables
	local _incBaseDir="${_backupBaseDir}/latest_full"
	local _backupStatus=`grep backup_type ${_incBaseDir}/xtrabackup_checkpoints | awk -F ' = ' '{print $2}'`

	# Check status of backup
	if [ ${_backupStatus} != "full-prepared" ]; then
		printf "Backup is not fully prepared!\n\n"
		exit 1
	fi

	runBackup ${_backupBaseDir} ${_incBaseDir}

	return 0
}

function normalBackup {
	printf "Backup started `date +"%d-%m-%Y_%T"`\n"
	# Setup variables
	local _fullBaseDir="${_backupBaseDir}/latest_full"
	local _incBaseDir="${_backupBaseDir}/latest_inc"
	local _fullLsn=`grep to_lsn ${_fullBaseDir}/xtrabackup_checkpoints | awk -F ' = ' '{print $2}'`
	local _incLsn=`grep to_lsn ${_incBaseDir}/xtrabackup_checkpoints | awk -F ' = ' '{print $2}'`

	# Check status of backup
	if [ ${_fullLsn} != ${_incLsn} ]; then
		printf "Backup is not fully prepared!\n\n"
		exit 1
	fi

	runBackup ${_backupBaseDir} ${_incBaseDir}

	return 0
}

function lastBackup {
	printf "Backup started `date +"%d-%m-%Y_%T"`\n"
	# Setup variables
	local _fullBaseDir="${_backupBaseDir}/latest_full"
	local _incBaseDir="${_backupBaseDir}/latest_inc"
	local _fullLsn=`grep to_lsn ${_fullBaseDir}/xtrabackup_checkpoints | awk -F ' = ' '{print $2}'`
	local _incLsn=`grep to_lsn ${_incBaseDir}/xtrabackup_checkpoints | awk -F ' = ' '{print $2}'`
	local _fullName=`readlink ${_fullBaseDir} | awk -F '/' '{print $(NF)}'`

	# Check status of backup
	if [ ${_fullLsn} != ${_incLsn} ]; then
		printf "Backup is not fully prepared!\n\n"
		exit 1
	fi

	runBackup ${_backupBaseDir} ${_incBaseDir} "true"

	# Prepare the FULL backup one last time
	printf "Preparing full backup...\n"
	innobackupex --apply-log ${_fullBaseDir}/ ; _status=$?
		
	if [ ${_status} != "0" ]; then
		printf "\nPreparation failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "\nPreparation done\n"
	fi

	# Tar and compress newly prepared full backup
	printf "Archiving full backup..."
	tar caf ${_fullName}.tar.bz2 ${_backupBaseDir}/prepared/${_fullName} ; _status=$?
		
	if [ ${_status} != "0" ]; then
		printf "failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "done\n"
	fi
	
	# Move newly created tar.gz-file to online share
	printf "Moving archive to tertiary dir..."
	mv ${_fullName}.tar.bz2 ${_tertiaryBackupBaseDir}/ ; _status=$?
		
	if [ ${_status} != "0" ]; then
		printf "failed!\n"
		printf "Backup finished `date +"%d-%m-%Y_%T"`\n"
		exit 1
	else
		printf "done\n"
	fi

	return 0
}

# Main

case "$1" in

-f) firstBackup
    ;;
-n) normalBackup
    ;;
-l) lastBackup
    ;;
*) usage
   ;;
esac

printf "Backup finished `date +"%d-%m-%Y_%T"`\n"

exit 0
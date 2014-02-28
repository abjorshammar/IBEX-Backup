#!/bin/bash
#
# cleanup.sh - This script will: 
# 1. Cleanup various backupdirs
#

# Setup variables
_backupBaseDir=""
_secondaryBackupBaseDir=""
_tertiaryBackupBaseDir=""
_timestamp=`date +"%d-%m-%Y_%H-%M-%S"`
_targetDir="${_backupBaseDir}/prepared/${_timestamp}"

# Functions
function usage {
cat << EOF

usage: $0 options

  Options:
    -h   Show this message
    -d   Directory to clean
    -t   Time in minutes (Dirs older will be deleted)
    -n   Dry run (Will not delete anything)
    -v   Verbose

EOF
}

function cleandir {
	
	# Set variables
	local _timeInHours=`expr ${_timeInMinutes} / 60`
	local _command="find ${_cleanDir}/* -type d -mmin +${_timeInMinutes}"
	local _rmCommand="${_command} -delete -print"

	printf "Cleanup started `date +"%d-%m-%Y_%T"`\n\n"
	printf "Removing folders older then ${_timeInHours} hours in ${_cleanDir}..."
	if [[ ${_dryRun} == true ]]; then
		if [[ ${_verbose} == true ]]; then
			printf "\nDoing a verbose dry run...\n\n"
			${_command}
			printf "\ndone\n\n"
		else
			printf "\nDoing a dry run..."
			_lines=$(${_command} | wc -l)
			printf "done!\nWould have removed ${_lines} folders.\n\n"
		fi
	else
		if [[ ${_verbose} == true ]]; then
			printf "\n\n"
			${_rmCommand}
			printf "\nCleanup done!\n\n"
		else
			_lines=$(${_rmCommand} | wc -l)
			printf "done!\nRemoved ${_lines} folders.\n\n"
		fi
	fi
	
}

# Main

while getopts “hd:t:nv” _option
do
	case ${_option} in
		h)
			usage
			exit 1
			;;
		d)
			 _cleanDir=$OPTARG
			 ;;
		t)
			_timeInMinutes=$OPTARG
			;;
		n)
			_dryRun=true
			;;
		v)
			_verbose=true
			;;
		?)
			usage
			exit 1
			;;
	esac
done

printf "\n"

if [[ -z ${_cleanDir} ]]; then
	printf "ERROR: No directory to clean provided!\n"
	_error=true
fi
if [[ -z ${_timeInMinutes} ]]; then
	printf "ERROR: No time provided!\n"
	_error=true
elif [[ ${_timeInMinutes} == *[!0-9]* ]]; then
	printf "ERROR: Time option '${_timeInMinutes}' is not a number!\n"
	_error=true
fi
if [[ ${_error} == true ]]; then
	usage
	exit 1
fi

cleandir

printf "Cleanup finished `date +"%d-%m-%Y_%T"`\n\n"

exit 0
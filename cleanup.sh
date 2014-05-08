#!/bin/bash
#
# cleanup.sh - This script will: 
# 1. Cleanup various backupdirs
#

# Setup variables

# Functions
function usage {
cat << EOF

usage: $0 options

  Options:
    -h   Show this message
    -d   Directory to clean
    -f   Perform cleanup of files instead of directories within the specified directory
    -t   Time in minutes (Dirs older will be deleted)
    -n   Dry run (Will not delete anything)
    -v   Verbose

EOF
}

function cleandir {
	
	# Set variables
	local _timeInHours=`expr ${_timeInMinutes} / 60`
	local _command="find ${_cleanDir} -maxdepth 1 -type d -mmin +${_timeInMinutes}"
	local _commandFiles="find ${_cleanDir} -maxdepth 1 -type f -mmin +${_timeInMinutes}"
	local _captureCommand="-print0"
	local _rmCommand="xargs -0 rm -rf"

	# Removing files
	if [[ ${_cleanFiles} == true ]]; then
		printf "Cleanup started `date +"%d-%m-%Y_%T"`\n\n"
	        printf "Removing files older then ${_timeInHours} hours in ${_cleanDir}..."
        	if [[ ${_dryRun} == true ]]; then
                	if [[ ${_verbose} == true ]]; then
                        	printf "\nDoing a verbose dry run...\n\n"
	                        ${_commandFiles}
        	                _lines=$(${_commandFiles} | wc -l)
                	        printf "\nDone!\nWould have removed ${_lines} files.\n\n"
	                else
        	                printf "\nDoing a dry run..."
                	        _lines=$(${_commandFiles} | wc -l)
                        	printf "done!\nWould have removed ${_lines} files.\n\n"
	                fi
	        else
        	        if [[ ${_verbose} == true ]]; then
                	        printf "\n\n"
                        	${_commandFiles}
	                        _lines=$(${_commandFiles} | wc -l)
        	                ${_commandFiles} ${_captureCommand} | ${_rmCommand}
                	        printf "\nCleanup done!\nRemoved ${_lines} files.\n\n"
	                else
        	                _lines=$(${_commandFiles} | wc -l)
                	        ${_commandFiles} ${_captureCommand} | ${_rmCommand}
                        	printf "Done!\nRemoved ${_lines} files.\n\n"
	                fi
        	fi

	# Removing folders
	else
		printf "Cleanup started `date +"%d-%m-%Y_%T"`\n\n"
		printf "Removing folders older then ${_timeInHours} hours in ${_cleanDir}..."
		if [[ ${_dryRun} == true ]]; then
			if [[ ${_verbose} == true ]]; then
				printf "\nDoing a verbose dry run...\n\n"
				${_command}
				_lines=$(${_command} | wc -l)
				printf "\nDone!\nWould have removed ${_lines} folders.\n\n"
			else
				printf "\nDoing a dry run..."
				_lines=$(${_command} | wc -l)
				printf "done!\nWould have removed ${_lines} folders.\n\n"
			fi
		else
			if [[ ${_verbose} == true ]]; then
				printf "\n\n"
				${_command}
				_lines=$(${_command} | wc -l)
				${_command} ${_captureCommand} | ${_rmCommand}
				printf "\nCleanup done!\nRemoved ${_lines} folders.\n\n"
			else
				_lines=$(${_command} | wc -l)
				${_command} ${_captureCommand} | ${_rmCommand}
				printf "Done!\nRemoved ${_lines} folders.\n\n"
			fi
		fi
	fi
}

# Main

while getopts "hd:t:fnv" _option
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
		f)
			_cleanFiles=true
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

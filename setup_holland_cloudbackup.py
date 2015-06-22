#!/usr/bin/env python
"""Cloud Holland Backup Setup

Usage:
  setup_holland_cloudbackup.py -u <user> -k <key> -r <dc> -i <serverid>
  setup_holland_cloudbackup.py -V | --version
  setup_holland_cloudbackup.py -h | --help

Options:
  -V, --version          Show version
  -h, --help             Show this message
  -u, --username=<user>  Rackspace Cloud Username
  -k, --apikey=<key>     Rackspace Account API Key
  -r, --region=<dc>      Rackspace Region/Datacenter
  -i, --uuid=<serverid>  Cloud Server UUID to backup

"""

from docopt import docopt, DocoptExit
import requests
import json
import os

if os.geteuid() != 0:
    exit("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")

try:
    args = docopt(__doc__, version='1.0')
except DocoptExit as e:
    print e.message

username = args['--username']
api_key = args['--apikey']
region = args['--region']
server_id = args['--uuid']

## Authenticate:
url = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
data = { "auth": { "RAX-KSKEY:apiKeyCredentials": { "username": username, "apiKey": api_key } } }
headers = { "Content-Type": "application/json" }
response = requests.post( url, data=json.dumps(data), headers=headers )
api_token = response.json['access']['token']['id']
ddi = response.json['access']['token']['tenant']['id']
headers["X-Auth-Token"] = api_token

## Get user email address:
url = 'https://identity.api.rackspacecloud.com/v2.0/users?name={}'.format(username)
email_address = requests.post( url, headers=headers )

## Get Agent information for server:
url = 'https://{}.backup.api.rackspacecloud.com/v1.0/{}/agent/server/{}'.format(region, ddi, server_id)
response = requests.post( url, headers=headers )
agentid = response.json['MachineAgentId']

## Create Backup configurations for Agent:
url = 'https://{}.backup.api.rackspacecloud.com/v1.0/{}/backup-configuration'.format(region, ddi)
holland_backup_config = {
    "MachineAgentId": agentid,
    "BackupConfigurationName": "Daily Holland Backup",
    "IsActive": true,
    "VersionRetention": 30,
    "MissedBackupActionId": 1,
    "Frequency": "Manually",
    "StartTimeHour": null,
    "StartTimeMinute": null,
    "StartTimeAmPm": null,
    "DayOfWeekId": null,
    "HourInterval": null,
    "TimeZoneId": "Central Standard Time",
    "NotifyRecipients": email_address,
    "NotifySuccess": true,
    "NotifyFailure": true,
    "Inclusions": [
        {
            "FilePath": "/var/spool/holland",
            "FileItemType": "Folder"
        }
    ],
    "Exclusions": []
}

server_backup_config = {
    "MachineAgentId": agentid,
    "BackupConfigurationName": "Daily Server Backup",
    "IsActive": true,
    "VersionRetention": 30,
    "MissedBackupActionId": 1,
    "Frequency": "Daily",
    "StartTimeHour": 12,
    "StartTimeMinute": 0,
    "StartTimeAmPm": "AM",
    "DayOfWeekId": null,
    "HourInterval": null,
    "TimeZoneId": "Central Standard Time",
    "NotifyRecipients": email_address,
    "NotifySuccess": true,
    "NotifyFailure": true,
    "Inclusions": [
        {
            "FilePath": "/",
            "FileItemType": "Folder"
        }
    ],
    "Exclusions": [
        {
            "FilePath": "/var/lib/mysql",
            "FileItemType": "Folder"
        },
        {
            "FilePath": "/var/spool/holland",
            "FileItemType": "Folder"
        }
    ]
}

response = requests.post( url, data=json.dumps(holland_backup_config), headers=headers )
holland_backup_id = response.json['BackupConfigurationId']

response = requests.post( url, data=json.dumps(server_backup_config), headers=headers )
server_backup_id = response.json['BackupConfigurationId']

def make_executable(path):
    ''' from http://stackoverflow.com/a/30463972 '''
    mode = os.stat(path).st_mode
    mode |= (mode & 292) >> 2    # copy R bits to X
    os.chmod(path, mode)

## Now create a script to run holland backup first, then start the cloud backup once finished

cloudbackup_script = """#!/bin/bash

username=${1}
apikey=${2}
region=${3}
region=${region,,}
accountid=${4}
bkpcfgid=${5}

echo "Starting Holland Backup"
/usr/sbin/holland bk 2>&1
echo "Finished Holland Backup"

echo "Starting Cloud Backup"
authurl='https://identity.api.rackspacecloud.com/v2.0/tokens'
authdata='{ "auth":{ "RAX-KSKEY:apiKeyCredentials":{ "username":"'$username'", "apiKey":"'$apikey'" } } }'
jsonhead="Content-Type: application/json"
authtoken=$(curl -s $authurl -X POST -d "$authdata" -H "$jsonhead" | python -m json.tool | sed -n '/expires/{n;p;}' | sed -e 's/^.*"id": "\(.*\)",/\1/')
posturl="https://${region}.backup.api.rackspacecloud.com/v1.0/${accountid}/backup/action-requested"
bkpdata='{ "Action": "StartManual", "Id": '$bkpcfgid' }'
backupid=$(curl -s $posturl -X POST -d "$bkpdata" -H "X-Auth-Token: $authtoken" -H "$jsonhead")
if [ ! -z "$backupid" ]; then
  echo "Started Cloud Backup with ID: $backupid";
else
  echo "Manually starting Cloud Backup failed";
fi
"""

cloudbackup_scriptfile = '/usr/local/bin/holland-cloudbackup'

with open(cloudbackup_scriptfile, 'w') as file:
  file.write(cloudbackup_script)

## Be sure to make the script executable

make_executable(cloudbackup_scriptfile)

## Now we will use systemd's service and timer features to schedule the backup

# Service Unit
cloudbackup_service = """[Unit]
Description=Holland Cloud Backup

[Service]
ExecStart=/usr/local/bin/holland-cloudbackup '{}' '{}' '{}' '{}' '{}'
""".format(username, api_key, region.lower(), ddi, holland_backup_id)

cloudbackup_servicefile = '/etc/systemd/system/holland-cloudbackup.service'

with open(cloudbackup_servicefile, 'w') as file:
  file.write(cloudbackup_service)

# Timer Unit
cloudbackup_timer = """[Timer]
OnCalendar=daily

[Install]
WantedBy=timers.target
"""

cloudbackup_timerfile = '/etc/systemd/system/holland-cloudbackup.timer'

with open(cloudbackup_timerfile, 'w') as file:
  file.write(cloudbackup_timer)

## Now enable the timer, and start it (no need to worry about the service)

os.system('/usr/bin/systemctl enable holland-cloudbackup.timer')

os.system('/usr/bin/systemctl start holland-cloudbackup.timer')

## Done!

# Holland Backup + Cloud Backup = Automation awesome!

Available articles:

Install Holland: https://community.rackspace.com/products/f/54/t/1638  
Install backup agent: http://www.rackspace.com/knowledge_center/article/rackspace-cloud-backup-install-the-agent-on-linux  
Configure cloud backup: http://www.rackspace.com/knowledge_center/article/rackspace-cloud-backup-create-a-backup-0

OS - CentOS 7

## Install MySQL (MariaDB on Cent/RHEL 7)

`sudo yum install mariadb mariadb-server`

## Install Holland backup and the MySQLdump plugin

`sudo yum install holland holland-mysqldump`

## Create a credentials file for holland to log in as, replacing <rootpassword> as appropriate

```vim /root/.my.cnf
[client]
user=root
password=<rootpassword>```

## Alternatively, create a holland backup user with the following permissions:
`GRANT SELECT, RELOAD, SUPER, LOCK TABLES, REPLICATION CLIENT, SHOW VIEW ON *.* TO 'holland'@'localhost' IDENTIFIED BY 'XXXXXXXXXXXXXXXXXX';`

## And add the user= and password= options to the /etc/holland/holland.conf or /etc/holland/backupsets/default.conf file under [mysql:client]
http://docs.hollandbackup.org/provider_configs/mysqldump.html#mysql-connection-info-mysql-client

## Install the Cloud Backup agent

`sudo rpm -Uvh 'http://agentrepo.drivesrvr.com/redhat/cloudbackup-updater-latest.rpm'`

`sudo cloudbackup-updater -v`

## Configure the client with the cloud username, api key, and region/datacenter

`sudo /usr/local/bin/driveclient -c -u <username> -k <apikey> -t <region>`

## Start and enable the driveclient

`sudo systemctl start driveclient`

`sudo systemctl enable driveclient`

## When I installed holland, it didn't include the default config for some reason

`sudo wget https://raw.githubusercontent.com/holland-backup/holland/master/config/backupsets/default.conf -O /etc/holland/backupsets/default.conf`

## I like me some tight xz compression

`sudo sed -i -e 's/^#\[compression/\[compression/' -e 's/^#method/method/' -e 's/= gzip/= lzma/' /etc/holland/backupsets/default.conf`

## Test holland backup:

`sudo /usr/sbin/holland bk --dry-run`



## Configure Cloud Backups: ( Run through all this OR run setup_holland_cloudbackup.py )
      Backup Name: Full Disk except MySQL
    Schedule
      Backup: Daily
      at: 12:00 AM CDT
      Retain Prior Versions: indefinitely
    Notifications
      Email Address: <you>@<email.com>
    >Next
    Select Items to Backup
      Select /
      Unselect /var/lib/mysql
      Unselect /var/spool/holland
    >Next
    >Save
    --
      Backup Name: Holland MySQL
    Schedule
      Backup: Manually
      Retain Prior Versions: indefinitely
    Notifications
      Email Address: <you>@<email.com>
    >Next
    Select Items to Backup
      Select /var/spool/holland
    >Next
    >Save

## Get Region and Backup ID from URL:
https://clouddrive.rackspace.com/cloud-backup/[region]/[backupid]

## Now create a script to run holland backup first, then the cloudbackup script once finished

    sudo cat << 'EOF' > /usr/local/bin/holland-cloudbackup
    #!/bin/bash

    username=$1
    apikey=$2
    region=${3,,}
    accountid=$4
    bkpcfgid=$5

    echo "Starting Holland Backup"
    /usr/sbin/holland bk 2>&1
    echo "Finished Holland Backup"

    echo "Starting Cloud Backup"
    authdata='{ "auth":{ "RAX-KSKEY:apiKeyCredentials":{ "username":"'$username'", "apiKey":"'$apikey'" } } }'
    authtoken=$(curl -s https://identity.api.rackspacecloud.com/v2.0/tokens -X POST -d "$authdata" \
    -H "Content-Type: application/json" | python -m json.tool | sed -n '/expires/{n;p;}' | sed -e 's/^.*"id": "\(.*\)",/\1/')
    posturl="https://${region}.backup.api.rackspacecloud.com/v1.0/${accountid}/backup/action-requested"
    bkpdata='{ "Action": "StartManual", "Id": '$bkpcfgid' }'
    backupid=$(curl -s $posturl -X POST -d "$bkpdata" -H "X-Auth-Token: $authtoken" -H "Content-Type: application/json")
    if [ ! -z "$backupid" ]; then
      echo "Started Cloud Backup with ID: $backupid";
    else
      echo "Manually starting Cloud Backup failed";
    fi
    EOF

## Be sure to make the script executable

`chmod +x /usr/local/bin/holland-cloudbackup`

## Now we will use systemd's service and timer features to schedule the backup
## Replace items in angle brackets (e.g. <username>) with the appropriate values

    sudo cat << 'EOF' > /etc/systemd/system/holland-cloudbackup.service
    [Unit]
    Description=Holland Cloud Backup

    [Service]
    ExecStart=/usr/local/bin/holland-cloudbackup <username> <apikey> <region> <accountid> <bkpcfgid>
    EOF


    sudo cat << 'EOF' > /etc/systemd/system/holland-cloudbackup.timer
    [Timer]
    OnCalendar=daily

    [Install]
    WantedBy=timers.target
    EOF

## Then enable the timer, and start it (no need to worry about the service)

`sudo systemctl enable holland-cloudbackup.timer`

`sudo systemctl start holland-cloudbackup.timer`

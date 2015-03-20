#!/bin/sh

# These aren't normal invocations of rsync: the targets use the
# 'command' option in /root/.ssh/authorized_keys to force execution of
# the 'backup-snapshot' script at the remote end, which then starts the
# rsync server process. So the backup SSH key can only be used to make
# backups, nothing more.

# Don't make the mistake of trying to run this from a systemd unit. There is
# some brokenness in systemd that causes the SSH connection forwarding to not
# work, so you will not be able to connect to the remote machines.

# Database
/usr/bin/rsync --archive --delete-before --delete-excluded \
    --hard-links --human-readable --progress --sparse \
    root@192.168.222.30: /srv/backup/database
date > /srv/backup/database.timestamp

# Gerrit
/usr/bin/rsync --archive --delete-before --delete-excluded \
    --hard-links --human-readable --progress --sparse \
    --exclude='cache/' --exclude='tmp/' \
    root@192.168.222.69: /srv/backup/gerrit
date > /srv/backup/gerrit.timestamp


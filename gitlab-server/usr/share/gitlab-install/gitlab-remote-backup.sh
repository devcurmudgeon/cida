#!/bin/sh
#
# Copy relevant files of a Baserock Gitlab instance out of the instance.
#
# Usage: backup.sh ADDR
# where ADDR is the address (domain name, IP address) of the instance.
# The files are copied to the current directory.

set -eux

ADDR="$1"

backup()
{
    rsync -ahHS --delete "root@$ADDR:$1" "$2"
}

mkdir -p dumps repositories uploads
backup /home/postgres/dumps/. dumps/.
backup /home/git/repositories/. repositories/.
backup /home/git/gitlab/public/uploads/. uploads/.


#!/bin/sh
#
# Restore a Baserock Gitlab system backup to a fresh instance.
#
# Usage: restore.sh ADDR
# where ADDR is the address (domain name, IP address) of the instance.
#
# What this does is a) stop services b) copy files over c) reset the Postgres
# databases.

set -eux

ADDR="$1"

restore()
{
    rsync -ahHS --delete "$2" "root@$ADDR:$1"
}

# Stop services so we don't modify files and databases from underneath
# them, and also so they don't modify things while restore is happening.

ssh "root@$ADDR" systemctl stop \
    crond gitlab-backup.service \
    gitlab-ci-sidekiq.service \
    gitlab-ci-unicorn.service \
    gitlab-sidekiq.service \
    gitlab-unicorn.service \
    gitlab.target \
    gitlab-backup.timer \
    nginx.service \
    redis.service

# Create the directory where postgres dump files go.

ssh "root@$ADDR" install -d -o postgres -g postgres /home/postgres/dumps

# Restore the various files.

restore /home/postgres/dumps/. dumps/.
restore /home/git/repositories/. repositories/.
restore /home/git/gitlab/public/uploads/. uploads/.

# And thier uid/gid
ssh "root@$ADDR" chown -R git:git /home/git/repositories /home/git/gitlab/public/uploads

# Delete tables and roles from Postgres so that the restore can happen.

ssh "root@$ADDR" sudo -u postgres psql <<EOF
drop database gitlabhq_production;
drop database gitlab_ci_production;
drop role git, gitlab_ci;
EOF

# Restore the Postgres databases from the latest dump.

ssh "root@$ADDR" sudo -u postgres psql -q -f /home/postgres/dumps/gitlab.pg_dumpall

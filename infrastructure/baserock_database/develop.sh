#!/bin/sh

# Start up a development instance of 'database', which will be accessible on
# the local machine. (To stop it again, use `docker stop baserock-database`).

# Note that this container works in a different way to the official Docker
# MariaDB image (<https://registry.hub.docker.com/_/mariadb/>). That's
# intentional: the official image is for use when Docker is being used as a
# production environment and the official Docker images are considered trusted.
# Here I am using Docker as a tool to locally test out trusted(ish) images that
# I create with Packer, before deploying them to an OpenStack cloud.

set -eu

# These lines of SQL are needed to authorize the container host for accessing
# the database remotely. (It actually grants access to any host, but since
# this is a development instance that's OK!)
CREATE_REMOTE_ROOT_USER_SQL="CREATE USER 'root'@'%' IDENTIFIED BY 'insecure' ;"
ALLOW_REMOTE_ROOT_USER_SQL="GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION ;"

docker run --detach \
    --name=baserock-database \
    --publish=127.0.0.1:3306:3306 \
    baserock/database \
    /bin/sh -c " \
      echo \"$CREATE_REMOTE_ROOT_USER_SQL\" > /tmp/mariadb-init.sql && \
      echo \"$ALLOW_REMOTE_ROOT_USER_SQL\" >> /tmp/mariadb-init.sql && \
      /usr/libexec/mariadb-prepare-db-dir mariadb && \
      /usr/bin/mysqld_safe --basedir=/usr --init-file=/tmp/mariadb-init.sql"

trap 'docker rm -f baserock-database > /dev/null' ERR

# Create some dummy accounts (in production deployments, this is done using the
# 'service-config.yml' Ansible playbook). We expect that there exists a 'root'
# user with no password set already.

create_without_overwriting() {
    target_file="$1"
    content="$2"
    if [ -e "$target_file" -a "$(cat "$target_file")" != "$content" ]; then
        echo >&2 "Not overwriting existing file $target_file"
        # Don't let the user create a development environment using files that
        # could contain the real passwords, to avoid them being used in an
        # insecure deployment.
        exit 1
    fi
    echo "$content" > "$target_file"
}

create_without_overwriting "database/root.database_password.yml" "root_password: insecure"
create_without_overwriting "database/baserock_openid_provider.database_password.yml" "baserock_openid_provider_password: openid_insecure"

# Ouch! Would be nice if you could get the 'docker run' command to wait until
# the database server is ready, or poll somehow until it is.
echo "Waiting 30 seconds for database server to be ready"
sleep 30

# Note that the Python 'mysqldb' module is required on the machine Ansible
# connects to for this playbook. For development deployments that is *your*
# machine (since we cannot and should not SSH into the Docker container). On
# Red Hat OSes the package you need is called 'MySQL-python'.
ansible-playbook database/user_config.yml

echo "You have a container named 'baserock-database' listening on port 3306."
echo
echo "Pass '--link baserock-database:mysql' to 'docker run' when starting "
echo "other containers if you want to give them access to this instance."
echo
echo "Run 'docker stop baserock-database; docker rm baserock-database' when "
echo "you are done with it (all data will then be lost)."

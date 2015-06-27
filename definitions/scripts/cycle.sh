#!/bin/sh
# Copyright (C) 2014  Codethink Limited
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

usage() {
    echo "Usage: cycle.sh some-system some-cluster [newversion]"
    echo
    echo "This builds and deploys the current checked out version of"
    echo "some-system, applying it as a self-upgrade to the system you"
    echo "are working in, using configuration from some-cluster."
    echo "The upgrade is labelled TEST by default, or [newversion] if"
    echo "specified, and is set to be the default for next boot."
}

if [ -z "$1" ] || [ -z "$2" ] || [ ! -z "$4" ] ; then
    usage
    exit 1
fi

newversion=TEST
if [ ! -z "$3" ] ; then
    newversion=$3
    if (echo "$newversion" | grep ' ' > /dev/null 2>&1) ; then
        echo 'Version label must not contain spaces.'
        exit 1
    fi
fi

if system-version-manager get-running | grep -q "^$newversion$"; then
  echo "You are currently running the $newversion system."
  echo "Maybe you want to boot into a different system version?"
  exit 1
fi

set -e
set -v

runningversion=`system-version-manager get-running`
system-version-manager set-default $runningversion
if system-version-manager list | grep -q "^$newversion$"; then
  system-version-manager remove $newversion
fi

morph gc
morph build "$1"

sed -i "s|^- morph: .*$|- morph: $1|" "$2"
morph deploy --upgrade "$2" self.HOSTNAME=$(hostname) self.VERSION_LABEL=$newversion
system-version-manager list

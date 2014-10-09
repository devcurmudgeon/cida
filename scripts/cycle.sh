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
    echo "Usage: cycle.sh some-system some-cluster"
    echo
    echo "This builds and deploys the current checked out version of"
    echo "some-system, applying it as a self-upgrade to the system you"
    echo "are working in, using configuration from some-cluster."
    echo "The upgrade is labelled TEST, and is set to be the default for"
    echo "next boot."
}

if [ -z "$1" ] || [ -z "$2" ] ; then
    usage
    exit 1
fi

if [ `system-version-manager get-running | grep ^TEST$` ]; then
  echo "You are currently running the TEST system."
  echo "Maybe you want to boot into a different system version?"
  exit 1
fi

set -e
set -v

system-version-manager set-default factory              
if [ `system-version-manager list | grep ^TEST$` ]; then
  system-version-manager remove TEST                                       
fi 

morph gc
morph build $1

sed -i "s|^- morph: .*$|- morph: $1|" $2
morph deploy --upgrade $2 self.HOSTNAME=$(hostname) self.VERSION_LABEL=TEST

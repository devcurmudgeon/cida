#!/bin/sh

# Copyright (C) 2013  Codethink Limited
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

set -e

usage() {
    echo "Usage: license-check your-system"
    echo
    echo "This checks license info for all the chunks in your-system"
    echo "It's re-runnable, and does morph edit to get each chunk."
    echo "The process can take a while."
}


if [ -z "$1" ]; then
    usage
    exit 1
fi

workspace="$PWD"/../../..
system="$1"

gplv3_chunks="\
autoconf \
automake \
bash \
binutils \
bison \
ccache \
cmake \
flex \
gawk \
gcc \
gdbm \
gettext \
gperf \
groff \
libtool \
m4 \
make \
nano \
texinfo-tarball"

gplv3_repos=""


for f in *.morph; do
    cp "$f" "$f.bak"
done


strata=`grep "morph.*: *" "$system.morph" | cut -d: -f2-`
for stratum in $strata; do
    chunks=`grep "name.*: *" "$stratum.morph" | cut -d: -f2-`
    for chunk in $chunks; do
        if [ "$chunk" != "$stratum" ]; then
            if ! (echo $gplv3_chunks | grep -wq "$chunk"); then
                morph edit $chunk 1>&2
            else
                repo=`grep "name.*: *$chunk" "$stratum.morph" -A1 | \
                      tail -n1 | cut -d: -f3-`
                gplv3_repos="$gplv3_repos $repo"
            fi
        fi
    done
done


repos=`for stratum in $strata; do
           grep "repo.*: *" "$stratum.morph" | cut -d: -f3-
       done | sort -u`


for repo in $repos; do
    if ! (echo $gplv3_repos | grep -wq "$repo") && \
            [ -d "$workspace/upstream/$repo" ] ; then
        echo "$repo"
        perl licensecheck.pl -r "$workspace/upstream/$repo" | \
            cut -d: -f2- | sort -u
        echo
    fi
done


for f in *.morph.bak; do
    mv "$f" "${f%.bak}"
done

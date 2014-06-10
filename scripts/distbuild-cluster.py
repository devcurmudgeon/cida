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

import os
import subprocess
import sys
import time
import yaml

import morphlib


''' distbuild-cluster: Build all systems in a cluster using distbuild.

This script should be removed once Morph has grown the capability to
build an entire cluster itself. This will require changes either to the
distbuild component (so that a single controller can build for multiple
architectures) or to the way Morph talks to distbuild (so that it can
handle multiple controllers).

'''

controllers = {
    'armv7lhf': '10.24.1.134',
    'x86_32': 'distbuild-x86-32',
    'x86_64': 'distbuild-x86-64',
}


ref_to_build = 'baserock-14.22'


def read_morph(morph_name, kind=None):
    with open(morph_name + '.morph') as f:
        morph = yaml.load(f)
    if kind is not None:
        assert morph['kind'] == kind
    return morph


class Build(object):
    '''A single distbuild instance.'''

    def __init__(self, system_name, arch):
        self.system_name = system_name
        self.distbuild_controller = controllers[system['arch']]

        self.command = [
            'morph', 'distbuild-morphology',
            '--controller-initiator-address=%s' % self.distbuild_controller,
            'baserock:baserock/definitions', ref_to_build, system_name]

    def start(self):
        self.process = subprocess.Popen(self.command)

    def completed(self):
        return (self.process.poll() is not None)


if __name__ == '__main__':
    cluster_name = morphlib.util.strip_morph_extension(sys.argv[1])

    cluster = read_morph(cluster_name, kind='cluster')
    system_list = [system['morph'] for system in cluster['systems']]

    builds = []
    for system_name in system_list:
        system = read_morph(system_name)
        builds.append(Build(system_name, system['arch']))

    # Morph dumps many log files to the current directory, which I don't
    # want to be in the root of 'definitions'.
    if not os.path.exists('builds'):
        os.mkdir('builds')
    os.chdir('builds')

    for build in builds:
        build.start()

    while not all(build.completed() for build in builds):
        time.sleep(1)

    for build in builds:
        if build.process.returncode != 0:
            sys.stderr.write("Building failed for %s\n" % build.system_name)

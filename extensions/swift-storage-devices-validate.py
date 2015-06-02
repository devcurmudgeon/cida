#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2015 Codethink Limited
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
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# This is used by the openstack-swift.configure extension
# to validate any provided storage device specifiers
# under SWIFT_STORAGE_DEVICES
#


'''
 This is used by the swift-storage.configure extension
 to validate any storage device specifiers specified
 in the SWIFT_STORAGE_DEVICES environment variable
'''

from __future__ import print_function

import yaml
import sys

EXAMPLE_DEVSPEC = '{device: sdb1, ip: 127.0.0.1, weight: 100}'
REQUIRED_KEYS = ['ip', 'device', 'weight']

def err(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

if len(sys.argv) != 2:
    err('usage: %s STRING_TO_BE_VALIDATED' % sys.argv[0])

swift_storage_devices = yaml.load(sys.argv[1])

if not isinstance(swift_storage_devices, list):
    err('Expected list of device specifiers\n'
        'Example: [%s]' % EXAMPLE_DEVSPEC)

for d in swift_storage_devices:
    if not isinstance(d, dict):
        err("Invalid device specifier: `%s'\n"
            'Device specifier must be a dictionary\n'
            'Example: %s' % (d, EXAMPLE_DEVSPEC))

    if set(d.keys()) != set(REQUIRED_KEYS):
        err("Invalid device specifier: `%s'\n"
            'Specifier should contain: %s\n'
            'Example: %s' % (d, str(REQUIRED_KEYS)[1:-1], EXAMPLE_DEVSPEC))

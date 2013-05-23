#!/bin/sh
# Copyright (C) 2012  Codethink Limited
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

# Creates a GENIVI development system image that is configured for
# being run inside a qemu-arm emulator.

morph deploy rawdisk genivi-devel-system-armv7-versatile \
             genivi-devel-system-armv7-versatile.img \
             DISK_SIZE=30G INSTALL_FILES=genivi-devel-system-armv7/manifest

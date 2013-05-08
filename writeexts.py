# Copyright (C) 2012-2013  Codethink Limited
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


import cliapp
import os
import re
import sys
import time
import tempfile


class WriteExtension(cliapp.Application):

    '''A base class for deployment write extensions.
    
    A subclass should subclass this class, and add a
    ``process_args`` method.
    
    Note that it is not necessary to subclass this class for write
    extensions. This class is here just to collect common code for
    write extensions.
    
    '''
    
    def process_args(self, args):
        raise NotImplementedError()

    def status(self, **kwargs):
        '''Provide status output.
        
        The ``msg`` keyword argument is the actual message,
        the rest are values for fields in the message as interpolated
        by %.
        
        '''
        
        self.output.write('%s\n' % (kwargs['msg'] % kwargs))
    
    def create_local_system(self, temp_root, raw_disk):
        '''Create a raw system image locally.'''
        
        size = self.get_disk_size()
        self.create_raw_disk_image(raw_disk, size)
        try:
            self.mkfs_btrfs(raw_disk)
            mp = self.mount(raw_disk)
        except BaseException:
            sys.stderr.write('Error creating disk image')
            os.remove(raw_disk)
            raise
        try:
            self.create_factory(mp, temp_root)
            self.create_fstab(mp)
            self.create_factory_run(mp)
            if self.bootloader_is_wanted():
                self.install_extlinux(mp)
        except BaseException, e:
            sys.stderr.write('Error creating disk image')
            self.unmount(mp)
            os.remove(raw_disk)
            raise
        else:
            self.unmount(mp)

    def _parse_size(self, size):
        '''Parse a size from a string.
        
        Return size in bytes.
        
        '''

        m = re.match('^(\d+)([kmgKMG]?)$', size)
        if not m:
            return None

        factors = {
            '': 1,
            'k': 1024,
            'm': 1024**2,
            'g': 1024**3,
        }
        factor = factors[m.group(2).lower()]

        return int(m.group(1)) * factor

    def _parse_size_from_environment(self, env_var, default):
        '''Parse a size from an environment variable.'''

        size = os.environ.get(env_var, default)
        bytes = self._parse_size(size)
        if bytes is None:
            raise morphlib.Error('Cannot parse %s value %s' % (env_var, size))
        return bytes

    def get_disk_size(self):
        '''Parse disk size from environment.'''
        return self._parse_size_from_environment('DISK_SIZE', '1G')

    def get_ram_size(self):
        '''Parse RAM size from environment.'''
        return self._parse_size_from_environment('RAM_SIZE', '1G')

    def create_raw_disk_image(self, filename, size):
        '''Create a raw disk image.'''

        self.status(msg='Creating empty disk image')
        with open(filename, 'wb') as f:
            if size > 0:
                f.seek(size-1)
                f.write('\0')

    def mkfs_btrfs(self, location):
        '''Create a btrfs filesystem on the disk.'''
        self.status(msg='Creating btrfs filesystem')
        cliapp.runcmd(['mkfs.btrfs', '-L', 'baserock', location])
        
    def mount(self, location):
        '''Mount the filesystem so it can be tweaked.
        
        Return path to the mount point.
        The mount point is a newly created temporary directory.
        The caller must call self.unmount to unmount on the return value.
        
        '''

        self.status(msg='Mounting filesystem')        
        tempdir = tempfile.mkdtemp()
        cliapp.runcmd(['mount', '-o', 'loop', location, tempdir])
        return tempdir
        
    def unmount(self, mount_point):
        '''Unmount the filesystem mounted by self.mount.
        
        Also, remove the temporary directory.
        
        '''
        
        self.status(msg='Unmounting filesystem')
        cliapp.runcmd(['umount', mount_point])
        os.rmdir(mount_point)

    def create_factory(self, real_root, temp_root):
        '''Create the default "factory" system.'''

        factory = os.path.join(real_root, 'factory')

        self.status(msg='Creating factory subvolume')
        cliapp.runcmd(['btrfs', 'subvolume', 'create', factory])
        self.status(msg='Copying files to factory subvolume')
        cliapp.runcmd(['cp', '-a', temp_root + '/.', factory + '/.'])

        # The kernel needs to be on the root volume.
        self.status(msg='Copying boot directory to root subvolume')
        factory_boot = os.path.join(factory, 'boot')
        root_boot = os.path.join(real_root, 'boot')
        cliapp.runcmd(['cp', '-a', factory_boot, root_boot])
        
    def create_factory_run(self, real_root):
        '''Create the 'factory-run' snapshot.'''

        self.status(msg='Creating factory-run subvolume')
        factory = os.path.join(real_root, 'factory')
        factory_run = factory + '-run'
        cliapp.runcmd(
            ['btrfs', 'subvolume', 'snapshot', factory, factory_run])

    def create_fstab(self, real_root):
        '''Create an fstab.'''

        self.status(msg='Creating fstab')        
        fstab = os.path.join(real_root, 'factory', 'etc', 'fstab')
        with open(fstab, 'w') as f:
            f.write('/dev/sda  /     btrfs defaults,rw,noatime 0 1\n')

    def install_extlinux(self, real_root):
        '''Install extlinux on the newly created disk image.'''

        self.status(msg='Creating extlinux.conf')
        config = os.path.join(real_root, 'extlinux.conf')
        with open(config, 'w') as f:
            f.write('default linux\n')
            f.write('timeout 1\n')
            f.write('label linux\n')
            f.write('kernel /boot/vmlinuz\n')
            f.write('append root=/dev/sda rootflags=subvol=factory-run '
                    'init=/sbin/init rw\n')

        self.status(msg='Installing extlinux')
        cliapp.runcmd(['extlinux', '--install', real_root])

        # FIXME this hack seems to be necessary to let extlinux finish
        cliapp.runcmd(['sync'])
        time.sleep(2)

    def parse_attach_disks(self):
        '''Parse $ATTACH_DISKS into list of disks to attach.'''

        if 'ATTACH_DISKS' in os.environ:
            s = os.environ['ATTACH_DISKS']
            return s.split(':')
        else:
            return []

    def bootloader_is_wanted(self):
        '''Does the user request a bootloader?

        The user may set $BOOTLOADER to yes, no, or auto. If not
        set, auto is the default and means that the bootloader will
        be installed on x86-32 and x86-64, but not otherwise.

        '''

        value = os.environ.get('BOOTLOADER', 'auto')
        if value == 'auto':
            if os.uname()[-1] in ['x86_32', 'x86_64']:
                value = 'yes'
            else:
                value = 'no'

        return value == 'yes'

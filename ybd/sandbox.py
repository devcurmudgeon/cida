# Copyright (C) 2011-2015  Codethink Limited
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
# =*= License: GPL-2 =*=


import sandboxlib

import os
import pipes
import shutil
import stat
import tempfile
from subprocess import call, PIPE

import app
import cache
import utils
from repos import get_repo_url


# This must be set to a sandboxlib backend before the run_sandboxed() function
# can be used.
executor = None


def builddir_for_component(this):
    return this['name'] + '.build'


def installdir_for_component(this):
    return this['name'] + '.inst'


def setup(this):
    currentdir = os.getcwd()

    tempfile.tempdir = app.settings['tmp']
    this['sandbox'] = tempfile.mkdtemp()
    this['build'] = os.path.join(
        this['sandbox'], builddir_for_component(this))
    this['install'] = os.path.join(
        this['sandbox'], installdir_for_component(this))
    this['baserockdir'] = os.path.join(this['install'], 'baserock')
    this['tmp'] = os.path.join(this['sandbox'], 'tmp')
    for directory in ['build', 'install', 'tmp', 'baserockdir']:
        os.makedirs(this[directory])
    this['log'] = os.path.join(app.settings['artifacts'],
                               this['cache'] + '.build-log')
    assembly_dir = this['sandbox']
    for directory in ['dev', 'tmp']:
        call(['mkdir', '-p', os.path.join(assembly_dir, directory)])

    devnull = os.path.join(assembly_dir, 'dev/null')
    if not os.path.exists(devnull):
        call(['sudo', 'mknod', devnull, 'c', '1', '3'])
        call(['sudo', 'chmod', '666', devnull])


def remove(this):
    if this['sandbox'] != '/' and os.path.isdir(this['sandbox']):
        shutil.rmtree(this['sandbox'])
        app.log(this, 'Cleaned up', this['sandbox'])


def install(defs, this, component):
    if os.path.exists(os.path.join(this['sandbox'], 'baserock',
                                   component['name'] + '.meta')):
        return

    app.log(this, 'Installing %s' % component['cache'])
    _install(defs, this, component)


def _install(defs, this, component):
    if os.path.exists(os.path.join(this['sandbox'], 'baserock',
                                   component['name'] + '.meta')):
        return

    for it in component.get('build-depends', []):
        dependency = defs.get(it)
        if (dependency.get('build-mode', 'staging') ==
                component.get('build-mode', 'staging')):
            _install(defs, this, dependency)

    for it in component.get('contents', []):
        subcomponent = defs.get(it)
        if subcomponent.get('build-mode', 'staging') != 'bootstrap':
            _install(defs, this, subcomponent)

    unpackdir = cache.unpack(defs, component)
    if this.get('kind') is 'system':
        utils.copy_all_files(unpackdir, this['sandbox'])
    else:
        utils.hardlink_all_files(unpackdir, this['sandbox'])


def ldconfig(this):
    conf = os.path.join(this['sandbox'], 'etc', 'ld.so.conf')
    if os.path.exists(conf):
        path = os.environ['PATH']
        os.environ['PATH'] = '%s:/sbin:/usr/sbin:/usr/local/sbin' % path
        cmd_list = ['ldconfig', '-r', this['sandbox']]
        run_logged(this, cmd_list)
        os.environ['PATH'] = path
    else:
        app.log(this, 'No %s, not running ldconfig' % conf)


def argv_to_string(argv):
    return ' '.join(map(pipes.quote, argv))


def run_sandboxed(this, command, env=None, allow_parallel=False):
    global executor

    app.log(this, 'Running command:\n%s' % command)
    with open(this['log'], "a") as logfile:
        logfile.write("# # %s\n" % command)

    mounts = ccache_mounts(this, ccache_target=env['CCACHE_DIR'])

    if this.get('build-mode') == 'bootstrap':
        # bootstrap mode: builds have some access to the host system, so they
        # can use the compilers etc.
        tmpdir = app.settings.get("TMPDIR", "/tmp")

        writable_paths = [this['build'], this['install'], tmpdir, ]

        config = dict(
            cwd=this['build'],
            filesystem_root='/',
            filesystem_writable_paths=writable_paths,
            mounts='isolated',
            extra_mounts=[],
            network='isolated',
        )
    else:
        # normal mode: builds run in a chroot with only their dependencies
        # present.

        mounts.extend([(None, '/dev/shm', 'tmpfs'), (None, '/proc', 'proc'), ])

        if this.get('kind') == 'system':
            writable_paths = 'all'
        else:
            writable_paths = [
                builddir_for_component(this),
                installdir_for_component(this),
                '/dev', '/proc', '/tmp',
            ]

        config = dict(
            cwd=builddir_for_component(this),
            filesystem_root=this['sandbox'],
            filesystem_writable_paths=writable_paths,
            mounts='isolated',
            extra_mounts=mounts,
            network='isolated',
        )

    argv = ['sh', '-c', command]

    cur_makeflags = env.get("MAKEFLAGS")

    # Adjust config for what the backend is capable of. The user will be warned
    # about any changes made.
    config = executor.degrade_config_for_capabilities(config, warn=True)

    try:
        if not allow_parallel:
            env.pop("MAKEFLAGS", None)

        app.log_env(this['log'], env, argv_to_string(argv))

        with open(this['log'], "a") as logfile:
            exit_code = executor.run_sandbox_with_redirection(
                argv, stdout=logfile, stderr=sandboxlib.STDOUT,
                env=env, **config)

        if exit_code != 0:
            app.log(this, 'ERROR: command failed in directory %s:\n\n' %
                    os.getcwd(), argv_to_string(argv))
            call(['tail', '-n', '200', this['log']])
            app.exit(this, 'ERROR: log file is at', this['log'])
    finally:
        if cur_makeflags is not None:
            env['MAKEFLAGS'] = cur_makeflags


def run_logged(this, cmd_list):
    app.log_env(this['log'], os.environ, argv_to_string(cmd_list))
    with open(this['log'], "a") as logfile:
        if call(cmd_list, stdin=PIPE, stdout=logfile, stderr=logfile):
            app.log(this, 'ERROR: command failed in directory %s:\n\n' %
                    os.getcwd(), argv_to_string(cmd_list))
            call(['tail', '-n', '200', this['log']])
            app.exit(this, 'ERROR: log file is at', this['log'])


def run_extension(this, deployment, step, method):
    app.log(this, 'Running %s extension:' % step, method)
    extensions = utils.find_extensions()
    tempfile.tempdir = tmp = app.settings['tmp']
    cmd_tmp = tempfile.NamedTemporaryFile(delete=False)
    cmd_bin = extensions[step][method]

    envlist = ['UPGRADE=no'] if method == 'ssh-rsync' else ['UPGRADE=yes']

    if 'PYTHONPATH' in os.environ:
        envlist.append('PYTHONPATH=%s:%s' % (os.environ['PYTHONPATH'],
                                             app.settings['extsdir']))
    else:
        envlist.append('PYTHONPATH=%s' % app.settings['extsdir'])

    for key, value in deployment.iteritems():
        if key.isupper():
            envlist.append("%s=%s" % (key, value))

    command = ["env"] + envlist + [cmd_tmp.name]

    if step in ('write', 'configure'):
        command.append(this['sandbox'])

    if step in ('write', 'check'):
        command.append(deployment['location'])

    with app.chdir(app.settings['defdir']):
        try:
            with open(cmd_bin, "r") as infh:
                shutil.copyfileobj(infh, cmd_tmp)
            cmd_tmp.close()
            os.chmod(cmd_tmp.name, 0o700)

            if call(command):
                app.log(this, 'ERROR: %s extension failed:' % step, cmd_bin)
                raise SystemExit
        finally:
            os.remove(cmd_tmp.name)
    return


def ccache_mounts(this, ccache_target):
    if app.settings['no-ccache'] or 'repo' not in this:
        mounts = []
    else:
        name = os.path.basename(get_repo_url(this['repo']))

        ccache_dir = os.path.join(app.settings['ccache_dir'], name)
        if not os.path.isdir(ccache_dir):
            os.mkdir(ccache_dir)

        mounts = [(ccache_dir, ccache_target, None, 'bind')]
    return mounts


def env_vars_for_build(defs, this):
    env = {}
    extra_path = []
    arch_dict = {
        'i686': "x86_32",
        'armv8l64': "aarch64",
        'armv8b64': "aarch64_be",
        'mips64b': 'mips64',
        'mips64l': 'mips64',
        'mips32b': 'mips',
        'mips32l': 'mips',
    }

    if app.settings['no-ccache']:
        ccache_path = []
    else:
        ccache_path = ['/usr/lib/ccache']
        env['CCACHE_DIR'] = '/tmp/ccache'
        env['CCACHE_EXTRAFILES'] = ':'.join(
            f for f in ('/baserock/binutils.meta',
                        '/baserock/eglibc.meta',
                        '/baserock/gcc.meta') if os.path.exists(f))
        if not app.settings.get('no-distcc'):
            env['CCACHE_PREFIX'] = 'distcc'

    prefixes = []

    for name in this.get('build-depends', []):
        dependency = defs.get(name)
        prefixes.append(dependency.get('prefix', '/usr'))
    prefixes = set(prefixes)
    for prefix in prefixes:
        if prefix:
            bin_path = os.path.join(prefix, 'bin')
            extra_path += [bin_path]

    if this.get('build-mode') == 'bootstrap':
        rel_path = extra_path + ccache_path
        full_path = [os.path.normpath(this['sandbox'] + p) for p in rel_path]
        path = full_path + app.settings['base-path']
        env['DESTDIR'] = this.get('install')
    else:
        path = extra_path + ccache_path + app.settings['base-path']
        env['DESTDIR'] = os.path.join('/',
                                      os.path.basename(this.get('install')))

    env['PATH'] = ':'.join(path)
    env['PREFIX'] = this.get('prefix') or '/usr'
    env['MAKEFLAGS'] = '-j%s' % (this.get('max-jobs') or
                                 app.settings['max-jobs'])
    env['TERM'] = 'dumb'
    env['SHELL'] = '/bin/sh'
    env['USER'] = env['USERNAME'] = env['LOGNAME'] = 'tomjon'
    env['LC_ALL'] = 'C'
    env['HOME'] = '/tmp'
    env['TZ'] = 'UTC'

    arch = app.settings['arch']
    cpu = arch_dict.get(arch, arch)
    abi = 'eabi' if arch.startswith(('armv7', 'armv5')) else ''
    env['TARGET'] = cpu + '-baserock-linux-gnu' + abi
    env['TARGET_STAGE1'] = cpu + '-bootstrap-linux-gnu' + abi
    env['MORPH_ARCH'] = arch
    env['DEFINITIONS_REF'] = app.settings['def-version']
    env['PROGRAM_REF'] = app.settings['program-version']

    return env


def create_devices(this):
    perms_mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO
    for device in this['devices']:
        destfile = os.path.join(this['install'], './' + device['filename'])
        mode = int(device['permissions'], 8) & perms_mask
        if device['type'] == 'c':
            mode = mode | stat.S_IFCHR
        elif device['type'] == 'b':
            mode = mode | stat.S_IFBLK
        else:
            raise IOError('Cannot create device node %s,'
                          'unrecognized device type "%s"'
                          % (destfile, device['type']))
        app.log(this, "Creating device node", destfile)
        os.mknod(destfile, mode, os.makedev(device['major'], device['minor']))
        os.chown(destfile, device['uid'], device['gid'])

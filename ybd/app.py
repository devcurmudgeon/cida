# Copyright (C) 2014-2015  Codethink Limited
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

import contextlib
import datetime
import os
import shutil
import sys
import warnings
import yaml
from multiprocessing import cpu_count
from subprocess import call, check_output

from repos import get_version


xdg_cache_home = os.environ.get('XDG_CACHE_HOME') or \
    os.path.join(os.path.expanduser('~'), '.cache')
settings = {}


def log(component, message='', data=''):
    ''' Print a timestamped log. '''
    if settings.get('pid') and os.getpid() != settings.get('pid'):
        return

    name = component['name'] if type(component) is dict else component

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = '%s [%s] %s %s\n' % (timestamp, name, message, data)
    if 'ERROR' in log_entry:
        log_entry = '\n\n%s\n\n' % log_entry
    print(log_entry),


def log_env(log, env, message=''):
    with open(log, "a") as logfile:
        for key in sorted(env):
            msg = env[key] if 'PASSWORD' not in key else '(hidden)'
            logfile.write('%s=%s\n' % (key, msg))
        logfile.write(message + '\n')
        logfile.flush()


def exit(component, message, data):
    log(component, message, data)
    sys.exit(1)


def warning_handler(message, category, filename, lineno, file=None, line=None):
    '''Output messages from warnings.warn().

    The default output is a bit ugly.

    '''
    return 'WARNING: %s\n' % (message)


@contextlib.contextmanager
def setup(target, arch):
    warnings.formatwarning = warning_handler
    with open(os.devnull, "w") as fnull:
        if call(['git', 'describe', '--all'], stdout=fnull, stderr=fnull):
            exit(target, 'ERROR: %s is not a git repo' % os.getcwd(),'')

    try:
        settings_file = './ybd.conf'
        if not os.path.exists(settings_file):
            settings_file = os.path.join(os.path.dirname(__file__), 'ybd.conf')
        with open(settings_file) as f:
            text = f.read()
        for key, value in yaml.safe_load(text).items():
            settings[key] = value
        settings['pid'] = os.getpid()
        settings['ybd-version'] = get_version(os.path.dirname(__file__))
        settings['defdir'] = os.getcwd()
        settings['extsdir'] = os.path.join(settings['defdir'], 'extensions')
        settings['def-ver'] = get_version('.')
        settings['target'] = target
        settings['arch'] = arch

        settings['base'] = os.path.join(xdg_cache_home, settings['base'])
        settings['artifacts'] = os.path.join(settings['base'], 'artifacts')
        settings['gits'] = os.path.join(settings['base'], 'gits')
        settings['tmp'] = os.path.join(settings['base'], 'tmp')
        settings['ccache'] = os.path.join(settings['base'], 'ccache_dir')
        settings['deployment'] = os.path.join(settings['base'], 'deployment')

        for directory in ['artifacts', 'gits', 'tmp', 'ccache', 'deployment']:
            try:
                os.makedirs(settings[directory])
            except OSError:
                if not os.path.isdir(settings[directory]):
                    exit(target, 'ERROR: Can not find or create',
                         settings[directory])

        # git replace means we can't trust that just the sha1 of a branch
        # is enough to say what it contains, so we turn it off by setting
        # the right flag in an environment variable.
        os.environ['GIT_NO_REPLACE_OBJECTS'] = '1'

        settings['max-jobs'] = max(int(cpu_count() * 1.5 + 0.5), 1)
        yield

    finally:
        log(target, 'Finished')


@contextlib.contextmanager
def chdir(dirname=None):
    currentdir = os.getcwd()
    try:
        if dirname is not None:
            os.chdir(dirname)
        yield
    finally:
        os.chdir(currentdir)


@contextlib.contextmanager
def timer(this, start_message=''):
    starttime = datetime.datetime.now()
    log(this, start_message)
    if type(this) is dict:
        this['start-time'] = starttime
    try:
        yield
    finally:
        log(this, 'Elapsed time', elapsed(starttime))


def elapsed(starttime):
    td = datetime.datetime.now() - starttime
    hours, remainder = divmod(int(td.total_seconds()), 60*60)
    minutes, seconds = divmod(remainder, 60)
    return "%02d:%02d:%02d" % (hours, minutes, seconds)

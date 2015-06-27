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


import os
import json
import re
import shutil
import string
from subprocess import call, check_output
import sys

import app
import utils


if sys.version_info.major == 2:
    # For compatibility with Python 2.
    from ConfigParser import RawConfigParser
    from StringIO import StringIO
    from urllib2 import urlopen
else:
    from configparser import RawConfigParser
    from io import StringIO
    from urllib.request import urlopen


def get_repo_url(repo):
    for alias, url in app.settings.get('aliases', {}).items():
        repo = repo.replace(alias, url)
    if repo.endswith('.git'):
        repo = repo[:-4]
    return repo


def get_repo_name(repo):
    ''' Convert URIs to strings that only contain digits, letters, _ and %.

    NOTE: this naming scheme is based on what lorry uses

    '''
    valid_chars = string.digits + string.ascii_letters + '%_'
    transl = lambda x: x if x in valid_chars else '_'
    return ''.join([transl(x) for x in get_repo_url(repo)])


def get_version(gitdir, ref='HEAD'):
    try:
        with app.chdir(gitdir), open(os.devnull, "w") as fnull:
            described = check_output(['git', 'describe', '--tags', '--dirty'],
                                     stderr=fnull)[0:-1]
            last_tag = check_output(['git', 'describe', '--abbrev=0',
                                     '--tags', ref], stderr=fnull)[0:-1]
            commits = check_output(['git', 'rev-list', last_tag + '..' + ref,
                                    '--count'])[0:-1]
        result = "%s %s (%s + %s commits)" % (ref[:8], described, last_tag,
                                              commits)
    except:
        result = ref[:8] + " (No tag found)"

    return result


def get_tree(this):
    ref = this['ref']
    gitdir = os.path.join(app.settings['gits'], get_repo_name(this['repo']))

    if not os.path.exists(gitdir):
        try:
            url = (app.settings['cache-server'] + 'repo=' +
                   get_repo_url(this['repo']) + '&ref=' + ref)
            with urlopen(url) as response:
                tree = json.loads(response.read().decode())['tree']
                return tree
        except:
            app.log(this, 'WARNING: no tree from cache-server', ref)
            mirror(this['name'], this['repo'])

    with app.chdir(gitdir), open(os.devnull, "w") as fnull:
        if call(['git', 'rev-parse', ref + '^{object}'], stdout=fnull,
                stderr=fnull):
            # can't resolve this ref. is it upstream?
            app.log(this, 'Fetching from upstream to resolve %s' % ref)
            call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)

        try:
            tree = check_output(['git', 'rev-parse', ref + '^{tree}'],
                                universal_newlines=True)[0:-1]
            return tree

        except:
            # either we don't have a git dir, or ref is not unique
            # or ref does not exist
            app.exit(this, 'ERROR: could not find tree for ref', (ref, gitdir))


def mirror(name, repo):
    gitdir = os.path.join(app.settings['gits'], get_repo_name(repo))
    tmpdir = gitdir + '.tmp'
    if os.path.isdir(tmpdir):
        shutil.rmtree(tmpdir)
    repo_url = get_repo_url(repo)
    try:
        os.makedirs(tmpdir)
        tar_file = get_repo_name(repo_url) + '.tar'
        app.log(name, 'Try fetching tarball %s' % tar_file)
        # try tarball first
        with app.chdir(tmpdir), open(os.devnull, "w") as fnull:
            call(['wget', os.path.join(app.settings['tar-url'], tar_file)])
            call(['tar', 'xf', tar_file], stdout=fnull, stderr=fnull)
            os.remove(tar_file)
            call(['git', 'config', 'remote.origin.url', repo_url],
                 stdout=fnull, stderr=fnull)
            call(['git', 'config', 'remote.origin.mirror', 'true'],
                 stdout=fnull, stderr=fnull)
            if call(['git', 'config', 'remote.origin.fetch',
                     '+refs/*:refs/*'],
                    stdout=fnull, stderr=fnull) != 0:
                raise BaseException('Did not get a valid git repo')
            call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)
    except:
        app.log(name, 'Try git clone from', repo_url)
        with open(os.devnull, "w") as fnull:
            if call(['git', 'clone', '--mirror', '-n', repo_url, tmpdir]):
                app.exit(name, 'ERROR: failed to clone', repo)

    with app.chdir(tmpdir):
        if call(['git', 'rev-parse']):
            app.exit(name, 'ERROR: problem mirroring git repo at', tmpdir)

    os.rename(tmpdir, gitdir)
    app.log(name, 'Git repo is mirrored at', gitdir)


def fetch(repo):
    with app.chdir(repo), open(os.devnull, "w") as fnull:
        call(['git', 'fetch', 'origin'], stdout=fnull, stderr=fnull)


def mirror_has_ref(gitdir, ref):
    with app.chdir(gitdir), open(os.devnull, "w") as fnull:
        out = call(['git', 'cat-file', '-t', ref], stdout=fnull, stderr=fnull)
        return out == 0


def update_mirror(name, repo, gitdir):
    with app.chdir(gitdir), open(os.devnull, "w") as fnull:
        app.log(name, 'Refreshing mirror for %s' % repo)
        if call(['git', 'remote', 'update', 'origin'], stdout=fnull,
                stderr=fnull):
            app.exit(name, 'ERROR: git update mirror failed', repo)


def checkout(name, repo, ref, checkout):
    gitdir = os.path.join(app.settings['gits'], get_repo_name(repo))
    if not os.path.exists(gitdir):
        mirror(name, repo)
    elif not mirror_has_ref(gitdir, ref):
        update_mirror(name, repo, gitdir)
    # checkout the required version of this from git
    with open(os.devnull, "w") as fnull:
        # We need to pass '--no-hardlinks' because right now there's nothing to
        # stop the build from overwriting the files in the .git directory
        # inside the sandbox. If they were hardlinks, it'd be possible for a
        # build to corrupt the repo cache. I think it would be faster if we
        # removed --no-hardlinks, though.
        if call(['git', 'clone', '--no-hardlinks', gitdir, checkout],
                stdout=fnull, stderr=fnull):
            app.exit(name, 'ERROR: git clone failed for', ref)

        with app.chdir(checkout):
            if call(['git', 'checkout', '--force', ref], stdout=fnull,
                    stderr=fnull):
                app.exit(name, 'ERROR: git checkout failed for', ref)

            app.log(name, 'Git checkout %s in %s' % (repo, checkout))
            app.log(name, 'Upstream version %s' % get_version(checkout, ref))

            if os.path.exists('.gitmodules'):
                checkout_submodules(name, ref)

    utils.set_mtime_recursively(checkout)


def checkout_submodules(name, ref):
    app.log(name, 'Git submodules')
    with open('.gitmodules', "r") as gitfile:
        # drop indentation in sections, as RawConfigParser cannot handle it
        content = '\n'.join([l.strip() for l in gitfile.read().splitlines()])
    io = StringIO(content)
    parser = RawConfigParser()
    parser.readfp(io)

    for section in parser.sections():
        # validate section name against the 'submodule "foo"' pattern
        submodule = re.sub(r'submodule "(.*)"', r'\1', section)
        url = parser.get(section, 'url')
        path = parser.get(section, 'path')

        try:
            # list objects in the parent repo tree to find the commit
            # object that corresponds to the submodule
            commit = check_output(['git', 'ls-tree', ref, path])

            # read the commit hash from the output
            fields = commit.split()
            if len(fields) >= 2 and fields[1] == 'commit':
                submodule_commit = commit.split()[2]

                # fail if the commit hash is invalid
                if len(submodule_commit) != 40:
                    raise Exception

                fulldir = os.path.join(os.getcwd(), path)
                checkout(name, url, submodule_commit, fulldir)

            else:
                app.log(name, 'Skipping submodule %s, not a commit:' % path,
                        fields)

        except:
            app.exit(name, "ERROR: git submodules problem")

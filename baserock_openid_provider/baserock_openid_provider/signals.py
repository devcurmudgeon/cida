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


from django.dispatch import receiver
import registration.signals

import logging


# This should watch 'registration.signals.user_activated' instead, if we ever
# decide to enable activation emails (i.e. if we switch from the 'simple'
# backend to the 'default' backend).
@receiver(registration.signals.user_registered)
def user_creation_handler(sender, user, request, **kwargs):
    logging.info('Creating OpenID for user %s' % (user.username))
    user.openid_set.create(openid=user.username)

# Copyright (C) 2015  Codethink Limited
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


from registration.forms import RegistrationForm

from django import forms
from django.utils.translation import ugettext_lazy as _


class RegistrationFormWithNames(RegistrationForm):
    # I'd rather just have a 'Full name' box, but django.contrib.auth is
    # already set up to separate first_name and last_name.

    first_name = forms.CharField(label=_("First name(s)"),
                                 required=False)
    last_name = forms.CharField(label=_("Surname"))

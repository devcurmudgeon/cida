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


import registration.backends.default.views

from registration import signals
from registration.users import UserModel

from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.shortcuts import render

from . import forms


def index(request):
    return render(request, '../templates/index.html')


class RegistrationViewWithNames(registration.backends.default.views.RegistrationView):
    # Overrides the django-registration default view so that the extended form
    # including the full name gets used.
    form_class = forms.RegistrationFormWithNames

    def register(self, request, **cleaned_data):
        # Calling the base class first means that we don't have to copy and
        # paste the contents of the register() function, but it has the
        # downside that we don't know the user's name when we send the
        # activation email.
        superclass = super(RegistrationViewWithNames, self)
        user = superclass.register(request, **cleaned_data)

        first_name, last_name = cleaned_data['first_name'], cleaned_data['last_name']
        user.first_name = first_name
        user.last_name = last_name
        user.save()

        return user


registration.backends.default.views.RegistrationView = RegistrationViewWithNames

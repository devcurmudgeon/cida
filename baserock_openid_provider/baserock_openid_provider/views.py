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


import registration.backends.simple.views

from registration import signals
from registration.users import UserModel

from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.shortcuts import render

from . import forms


def index(request):
    return render(request, '../templates/index.html')


class RegistrationViewWithNames(registration.backends.simple.views.RegistrationView):
    # Overrides the django-registration default view so that the extended form
    # including the full name gets used.
    form_class = forms.RegistrationFormWithNames

    def register(self, request, **cleaned_data):
        # It's a shame that we have to override the whole class here. We could
        # patch django-registration(-redux) to avoid the need.
        username, email, password = cleaned_data['username'], cleaned_data['email'], cleaned_data['password1']
        first_name, last_name = cleaned_data['first_name'], cleaned_data['last_name']
        UserModel().objects.create_user(username, email, password,
                                        first_name=first_name,
                                        last_name=last_name)

        new_user = authenticate(username=username, password=password)
        login(request, new_user)
        signals.user_registered.send(sender=self.__class__,
                                     user=new_user,
                                     request=request)
        return new_user


registration.backends.simple.views.RegistrationView = RegistrationViewWithNames

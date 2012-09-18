# -*- coding: utf-8 -*-
"""
    engineauth.models
    ====================================

    Auth related models.

    :copyright: 2011 by Rodrigo Moraes.
    :license: Apache Sotware License, see LICENSE for details.

    :copyright: 2011 by tipfy.org.
    :license: Apache Sotware License, see LICENSE for details.
    
    AuthProvider
    UserEmail
    User
    Session
    
    
"""
from google.appengine.ext import ndb
from webapp2_extras import securecookie
from webapp2_extras import security
import logging
from shg_utils import prettydate

class Error(Exception):
    """Base user exception."""

class DuplicatePropertyError(Error):
    def __init__(self, value):
        self.values = value
        self.msg = u'duplicate properties(s) were found.'

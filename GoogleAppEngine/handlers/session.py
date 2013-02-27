"""handlers/session.py

Called from any of the jinja2 or api handlers to:

    manage the session cookie
    
    -ie checks if we have a cookie
    -if not, set the session cookie
    
"""

from google.appengine.ext import ndb
import json
from functools import wraps
import shg_utils
import webapp2
from webapp2_extras import securecookie
from webapp2_extras import security
import logging
from models import authprovider
from handlers.jinja import Jinja2Handler
from datetime import datetime, timedelta
from auth_helpers import secrets

def manage_session(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        
        self.request.session = None
        value = self.request.cookies.get('_eauth')
        
        if value:
            self.request.session = Session.get_by_value(value)
        #elif not self.request.get('letmein'):
        #    return self.generic_error(title='Woah - hold ya horses',message="We're sorry, we aren't quite ready for launch!")
        
        if self.request.session:
            if self.request.session.last_seen < datetime.now() + timedelta(minutes=-30):
                self.request.session.last_seen = datetime.now()
                self.request.session.put()
        else:
            self.request.session = Session.create()
            self.response.set_cookie('_eauth', self.request.session.serialize(),expires=datetime.now() + timedelta(weeks=14))

        self.request.session.user = None

        return fn(self,*args,**kwargs)
    return wrapper
        

class Session(ndb.Model):
    _default_indexed = False
    
    created = ndb.DateTimeProperty(auto_now_add=True)
    last_seen = ndb.DateTimeProperty(auto_now=True)
    user_id = ndb.IntegerProperty()
    data = ndb.PickleProperty(compressed=True, default={}) #used by oauth
    email_hash = ndb.IntegerProperty()
    
    @staticmethod
    def _generate_sid():
        return security.generate_random_string(entropy=192)

    @staticmethod
    def _serializer():
        return securecookie.SecureCookieSerializer(serializer_secret)

    def hash(self):
        """
        Creates a unique hash from the session.
        This will be used to check for session changes.
        :return: A unique hash for the session
        """
        return hash(str(self))
    
    def _get_session_id(self):
        return str(self.key.id())
        
    def serialize(self):
        values = {'session_id': self._get_session_id()}
        return self._serializer().serialize('_eauth', values)

    @classmethod
    def deserialize(cls, value):
        return cls._serializer().deserialize('_eauth', value)

    @classmethod
    def get_by_value(cls, value):
        v = cls.deserialize(value)
        if not v:
            return None
        sid = v.get('session_id')
        return cls.get_by_sid(sid) if sid else None

    @classmethod
    def get_by_sid(cls, sid):
        return cls.get_by_id(sid)

    def upgrade_to_user_session(self, user_id):
        self.user_id = user_id
        self.put()
        return self

    @classmethod
    def create(cls):
        """Create a session (never happens if we already know who the user is)"""
        session_id = cls._generate_sid()
        session = cls(id=session_id)
        session.put()
        return session

    @classmethod
    def remove_inactive(cls, days_ago=30, now=None):
        import datetime
        # for testing we want to be able to pass a value for now.
        now = now or datetime.datetime.now()
        dtd = now + datetime.timedelta(-days_ago)
        for s in cls.query().filter(cls.last_seen < dtd).fetch():
            s.key.delete()



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
from engineauth import config
from google.appengine.ext import ndb
from webapp2_extras import securecookie
from webapp2_extras import security
import logging


class Error(Exception):
    """Base user exception."""

class DuplicatePropertyError(Error):
    def __init__(self, value):
        self.values = value
        self.msg = u'duplicate properties(s) were found.'

class User(ndb.Model):
    """
    The user is the actual individual.
    Parent to 
        AuthProvider(s) authenticate a user (for example Facebook)
        UserProperties (not yet implemented)
    """
    
    _default_indexed=False
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)
    primary_email = ndb.StringProperty(indexed=True)
    display_name = ndb.StringProperty()

    #authenticated = ndb.BooleanProperty(default=False)

    def _get_id(self):
        """Returns this user's unique ID, which can be an integer or string."""
        return str(self.key.id())
    
    @classmethod
    def _get_user_from_child(cls, child):
        """Gets a user based on its child entity (ie a property or authtoken)
        """
        return cls.get_by_id(child.parent())
    
    def _add_auth_token(cls, auth_token):
        
        auth_token



class AuthProvider(ndb.Model):
    """
    AuthProvider stores the authentication credentials (eg from Facebook)
    for a User - each user may have multiple AuthProviders
    """
    _default_indexed = False
    user_info = ndb.JsonProperty(indexed=False, compressed=True)
#    credentials = ndb.PickleProperty(indexed=False)

    @classmethod
    def get_user_create(cls,user_id, auth_id,user_info):
        """Create an auth_token for a specified user"""
        
        auth_token = cls.get_by_id(id=auth_id)
        
        if auth_token is None:
            #create a new token
            auth_token = cls(id=auth_id)
            auth_token.user_info = user_info
            auth_token.put()
            
        return auth_token
    
    @staticmethod
    def generate_auth_id(provider, uid, subprovider=None):
        """Standardized generator for auth_ids
    
        :param provider:
            A String representing the provider of the id.
            E.g.
            - 'google'
            - 'facebook'
            - 'appengine_openid'
            - 'twitter'
        :param uid:
            A String representing a unique id generated by the Provider.
            I.e. a user id.
        :param subprovider:
            An Optional String representing a more granular subdivision of a provider.
            i.e. a appengine_openid has subproviders for Google, Yahoo, AOL etc.
        :return:
            A concatenated String in the following form:
            '{provider}#{subprovider}:{uid}'
            E.g.
            - 'facebook:1111111111'
            - 'twitter:1111111111'
            - 'appengine_google#yahoo:1111111111'
            - 'appengine_google#google:1111111111'
        """
        if subprovider is not None:
            provider = '{0}#{1}'.format(provider, subprovider)
        return '{0}:{1}'.format(provider, uid)
    #
    #def _add_auth_id(self, auth_id):
    #    """A helper method to add additional auth ids to a User
    #
    #    :param auth_id:
    #        String representing a unique id for the user. Examples:
    #
    #        - own:username
    #        - google:username
    #    :returns:
    #        A tuple (boolean, info). The boolean indicates if the user
    #        was saved. If creation succeeds, ``info`` is the user entity;
    #        otherwise it is a list of duplicated unique properties that
    #        caused creation to fail.
    #    """
    #    # If the auth_id is already in the list return True
    #    if auth_id in self.auth_ids:
    #        return self
    #    if self.__class__.get_by_auth_id(auth_id):
    #        raise DuplicatePropertyError(value=['auth_id'])
    #    else:
    #        self.auth_ids.append(auth_id)
    #        self.put()
    #        return self
    #
    #@classmethod
    #def _get_by_auth_id(cls, auth_id):
    #    """Returns a user object based on a auth_id.
    #
    #    :param auth_id:
    #        String representing a unique id for the user. Examples:
    #
    #        - own:username
    #        - google:username
    #    :returns:
    #        A user object.
    #    """
    #    return cls.query(cls.auth_ids == auth_id).get()
    #get_by_auth_id = _get_by_auth_id



class Session(ndb.Model):
    _default_indexed = False
    
    session_id = ndb.StringProperty(indexed=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    last_seen = ndb.DateTimeProperty(auto_now=True)
    user_id = ndb.StringProperty()
    data = ndb.PickleProperty(compressed=True, default={}) #used by oauth


    @staticmethod
    def _generate_sid():
        return security.generate_random_string(entropy=192)

    @staticmethod
    def _serializer():
        engineauth_config = config.load_config()
        return securecookie.SecureCookieSerializer(engineauth_config['secret_key'])

    def hash(self):
        """
        Creates a unique hash from the session.
        This will be used to check for session changes.
        :return: A unique hash for the session
        """
        return hash(str(self))

    def serialize(self):
        values = self.to_dict(include=['session_id', 'user_id'])
        return self._serializer().serialize('_eauth', values)

    @classmethod
    def deserialize(cls, value):
        return cls._serializer().deserialize('_eauth', value)

    @classmethod
    def get_by_value(cls, value):
        v = cls.deserialize(value)
        sid = v.get('session_id')   
        return cls.get_by_sid(sid) if sid else None

    @classmethod
    def get_by_sid(cls, sid):
        return cls.get_by_id(sid)

    @classmethod
    def upgrade_to_user_session(cls, session_id, user_id):
        session = cls.get_by_sid(session_id)
        session.user_id = user_id
        session.put()
        return session

    @classmethod
    def create(cls):
        """Create a session (never happens if we already know who the user is)"""
        
        session_id = cls._generate_sid()
        session = cls(session_id=session_id)
        session.put()
        return session

    @classmethod
    def remove_inactive(cls, days_ago=30, now=None):
        import datetime
        # for testing we want to be able to pass a value for now.
        now = now or datetime.datetime.now()
        dtd = now + datetime.timedelta(-days_ago)
        for s in cls.query(cls.last_seen < dtd).fetch():
            s.key.delete()
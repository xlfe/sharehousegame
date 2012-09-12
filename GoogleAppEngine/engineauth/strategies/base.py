import threading
from webob import Request
import webob
from engineauth import models
from engineauth.middleware import EngineAuthRequest
import logging

class Error(Exception):
    """Base user exception."""

class EngineAuthError(Error):
    def __init__(self, msg):
        self.message = msg

def _abstract():
    raise NotImplementedError('You need to override this function')


class BaseStrategy(object):

    error_class = EngineAuthError

    def __init__(self, app, config=None):
        self.app = app
        self.config = config

    def __call__(self, environ, start_response):
        
        req = EngineAuthRequest(environ)
        
        req._config = self.config
        
        req.provider_config = self.config['provider.{0}'.format(req.provider)]
        
        redirect_uri = self.handle_request(req)
        
        resp = webob.exc.HTTPTemporaryRedirect(location=redirect_uri)

        resp.request = req
        return resp(environ, start_response)

    @property
    def options(self):
        """
        Strategy Options must be overridden by sub-class
        :return:
        """
        return _abstract()

    def user_info(self, req):
        """
        """
        _abstract()

    def get_or_create_auth_token(self, auth_id, user_info, credentials,user):
        """Callback where we've got an Auth Token from our provider
        and we need to decide what to do with it"""
        
        existing_at = models.AuthProvider.get_by_auth_id(auth_id)
        existing_user = user
        
        if existing_at and existing_user:
            #if the user is logged on, and the at is for that user, do nothing
            if existing_at.parent() == existing_user:
                logging.error('Existing user and at')
                return existing_at
            else:
                raise Exception('Access token already assigned to another user')
        
        
        if existing_at and not existing_user:
            logging.error('Existing at but no existing user')
            return existing_at
        
        if existing_user and not existing_at:
            logging.error('Existing user but no existing at, creating one')
            return models.AuthProvider._create(existing_user,auth_id,user_info,credentials)
            
        if not existing_user and not existing_at:
            logging.error('creating both user and at')
            new_user = models.User._create()
            return models.AuthProvider._create(new_user,auth_id,user_info,credentials)
            
        raise Exception('Logic failure in get_or_create_auth_token')
                
    
    def handle_request(self, req):
        _abstract()

    def raise_error(self, message):
        raise EngineAuthError(msg=message)

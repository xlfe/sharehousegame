import webapp2
import webob
from engineauth import models
from engineauth.middleware import EngineAuthRequest
import logging

def _abstract():
    raise NotImplementedError('You need to override this function')

class BaseStrategy(webapp2.Response):

    def __init__(self, app, config):
        self.app = app
        self.config = config

    def __call__(self, environ, start_response):
        req = EngineAuthRequest(environ)
        
        req._config = self.config
        
        req.provider_config = self.config['provider.{0}'.format(req.provider)]
        
        
        #call the parent class's handle_request
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

    def get_or_create_auth_token(self, auth_id, user_info, credentials, user):
        """Callback where we've got an Auth Token from our provider
        and we need to decide what to do with it"""
        
        existing_at = models.AuthProvider.get_by_auth_id(auth_id)
        existing_user = user
        
        duplicate_user = models.User._get_user_from_email(user_info['info']['email'])
        
        if duplicate_user:
            if existing_at.user_id != duplicate_user._get_id():
                return self.raise_error('Please login before attempting to add a second authentication method to your account.')
        
        if existing_at and existing_user:
            #if the user is logged on, and the at is for that user, do nothing
            if existing_at.user_id == existing_user._get_id():
                return existing_at
            else:
                raise Exception('Access token already assigned to another user')
        
        if existing_at and not existing_user:
            #User has already signed up, and is logging on
            return existing_at
        
        if existing_user and not existing_at:
            #User is adding an authentication method
            logging.error('Existing user but no existing at, creating one')
            return models.AuthProvider._create(existing_user,auth_id,user_info,credentials)
            
        if not existing_user and not existing_at:
            #New user/new access token
            new_user = models.User._create()
            return models.AuthProvider._create(new_user,auth_id,user_info,credentials)
            
        raise Exception('Logic failure in get_or_create_auth_token')
                
    
    def handle_request(self, req):
        _abstract()
        
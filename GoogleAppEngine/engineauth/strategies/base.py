import threading
from webob import Request
import webob
from engineauth import models
from engineauth.middleware import EngineAuthRequest


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

    def get_or_create_authprovider(self, user,auth_id, user_info, **kwargs):
        """Callback where we've got an Auth Token from our provider
        and we need to decide what to do with it"""
        
        
        
        
        
        
        return models.AuthProvider.get_or_create(user,auth_id, user_info, **kwargs)

    def handle_request(self, req):
        _abstract()

    def raise_error(self, message):
        raise EngineAuthError(msg=message)

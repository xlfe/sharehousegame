from __future__ import absolute_import
from engineauth import models
import re
import logging
import webapp2

def import_class(full_path):
    path_split = full_path.split('.')
    path = ".".join(path_split[:-1])
    klass = path_split[-1:]
    mod = __import__(path, fromlist=[klass])
    return getattr(mod, klass[0])



class EngineAuthResponse(webapp2.Response):

    def _save_session(self):
        session = self.request.session
        # Compare the hash that we set in load_session to the current one.
        # We only save the session and cookie if this value has changed.
        if self.request.session_hash == session.hash():
            return session
        session.put()
        self.set_cookie('_eauth', session.serialize())
        return self

    def _save_user(self):
        pass


class EngineAuthRequest(webapp2.Request):

    ResponseClass = EngineAuthResponse

    def _load_session(self):
        #Check if we have an existing session
        value = self.cookies.get('_eauth')
        session = None
        if value:
            session = models.Session.get_by_value(value)
        if session is not None:
            # Create a hash for later comparison,
            # to determine if a put() is required
            session_hash = session.hash()
        else:
            session = models.Session.create()
            # set this to False to ensure a cookie
            # is saved later in the response.
            session_hash = '0'
        self.session = session
        self.session_hash = session_hash
        return self

    def _get_user_class(self):
        return models.User

    def _load_user(self):
        if self.session is not None and self.session.user_id:
            self.user = self._get_user_class().get_by_id(int(self.session.user_id))
            if self.user is None:
                # then remove it.
                pass
        else:
            self.user = None
        return self

    def _get_user_from_auth_token(self, auth_token):
        """Match a session to an auth token"""
        
        self.user = models.User._get_user_from_id(auth_token.user_id)
        self.session.user_id = self.user._get_id()
        
    get_user_from_auth_token = _get_user_from_auth_token

    def _add_message(self, message, level=None, key='_messages'):
        if not self.session.data.get(key):
            self.session.data[key] = []
        return self.session.data[key].append({
            'message': message, 'level': level})
    add_message = _add_message

    def _get_messages(self, key='_messages'):
        try:
            return self.session.data.pop(key)
        except KeyError:
            pass
    get_messages = _get_messages

    def _set_redirect_uri(self):
        next_uri = self.GET.get('next')
        if next_uri is not None:
            self.session.data['_redirect_uri'] = next_uri
    set_redirect_uri = _set_redirect_uri

    def _get_redirect_uri(self):
        try:
            return self.session.data.pop('_redirect_uri').encode('utf-8')
        except KeyError:
            return self._config['success_uri']
    get_redirect_uri = _get_redirect_uri

    def _set_globals(self, environ):
#        environ['ea.config'] = req.config
        environ['ea.session'] = self.session
        environ['ea.user'] = self.user
        
    def handle_exception(self,request, response, e):
        logging.error('handle exception in middleware')
        return self.app.handle_exception(request,response,e)



class AuthMiddleware(object):
    
    def __init__(self, app, config):
        self.app = app
        self._config = config
        self._url_parse_re = re.compile(r'%s/([^\s/]+)/*(\S*)' % (self._config['base_uri']))

    def __call__(self, environ, start_response):
        """Called by WSGI when a request comes in.
        Parameters:	
                    environ: A WSGI environment.
                    start_response: A callable accepting a status code, a list
                                    of headers and an optional exception context
                                    to start the response.
        Returns:	
                An iterable with the response to return to the client."""

        
        if environ['PATH_INFO'].startswith('/_ah/'):
            
            # If the request is to the admin, call the parent app's __call__
            return self.app(environ, start_response)
            
        # load session
        req = EngineAuthRequest(environ)
        req._config = self._config
        req._load_session()
        req._load_user()
        req._set_redirect_uri()
        resp = None
        # If the requesting url is for engineauth load the strategy
        if environ['PATH_INFO'].startswith(self._config['base_uri']):
            # extract provider and additional params from the url
            provider, provider_params = self._url_parse_re.match(
                req.path_info).group(1, 2)
            if provider:
                req.provider = provider
                req.provider_params = provider_params
                # load the desired strategy class
                resp = req.get_response(application=strategy_class(self.app, self._config))
                if resp.request is None:
                    logging.error('resp.request is none')
                    # TODO: determine why this is necessary.
                    resp.request = req
        if resp is None:
            resp = req.get_response(self.app)
        # Save session, return response
        resp._save_session()
        return resp(environ, start_response)

    def _load_strategy(self, provider):
            strategy_location = self._config[
                                'provider.{0}'.format(provider)]['class_path']
            return import_class(strategy_location)

    def handle_exception(self,request, response, e):
        logging.error('handle exception in middleware')
        return self.app.handle_exception(request,response,e)

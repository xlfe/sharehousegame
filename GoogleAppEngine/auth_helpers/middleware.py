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


class EngineAuthRequest(webapp2.Request):


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


class AuthMiddleware(object):
    
    def __call__(self, environ, start_response):
        """Called by WSGI when a request comes in.
        Parameters:	
                    environ: A WSGI environment.
                    start_response: A callable accepting a status code, a list
                                    of headers and an optional exception context
                                    to start the response.
        Returns:	
                An iterable with the response to return to the client."""

        
        # load session
        req = EngineAuthRequest(environ)
        req._config = self._config
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


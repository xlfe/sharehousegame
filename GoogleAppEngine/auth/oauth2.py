from __future__ import absolute_import
import cPickle as pickle
from engineauth.strategies.base import BaseStrategy
import httplib2
from oauth2client.client import OAuth2WebServerFlow
import logging



def _abstract():
    raise NotImplementedError('You need to override this function')

class OAuth2(webapp2.RequestHandler):

    def http(self, req):
        """Returns an authorized http instance.
        """
        if req.credentials is not None and not req.credentials.invalid:
            return req.credentials.authorize(httplib2.Http())

    def auth_start(self):
        
        provider = self.options['provider']
        self.callback_uri = '{0}/auth/{1}/callback'.format(self.request.host_url,provider)
        
        self.session_key = '_auth_strategy:{0}'.format(provider)
        
        self.request.flow = OAuth2WebServerFlow(            
            self.options['client_id'],
            self.options['client_secret'],
            self.options['scope'],
            auth_uri=self.options['auth_uri'],
            token_uri=self.options['token_uri'],
        )
        
        self.request.flow.params['state'] = self.request.path_url
        authorize_url = req.flow.step1_get_authorize_url(self.callback_uri)
        self.request.session.data[self.session_key] = pickle.dumps(req.flow)
        return authorize_url

    def auth_callback(self, req):
        
        if req.GET.get('error'):
            return req.GET.get('error')
            
        flow = pickle.loads(str(req.session.data.get(self.session_key)))
        
        if flow is None:
            self.raise_error('And Error has occurred. Please try again.')
        
        req.credentials = flow.step2_exchange(req.params)
        
        user_info = self.user_info(req)
                
        auth_token = self.get_or_create_auth_token(
            auth_id=user_info['auth_id'],
            user_info=user_info,
            credentials=req.credentials,
            user=req.user)
        
        req.get_user_from_auth_token(auth_token)
        
        updated=False
        if req.user.display_name is None:
            req.user.display_name = user_info['info']['displayName']
            updated=True
        if req.user.primary_email is None:
            req.user.primary_email = user_info['info']['email']
            updated=True
            
        if updated:
            req.user.put()
        
        return req.get_redirect_uri()

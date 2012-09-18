from __future__ import absolute_import
import cPickle as pickle
import httplib2
import webapp2
from oauth2client.client import OAuth2WebServerFlow
import logging

class OAuth2(webapp2.RequestHandler):

    def http(self, req):
        """Returns an authorized http instance.
        """
        if req.credentials is not None and not req.credentials.invalid:
            return req.credentials.authorize(httplib2.Http())

    def auth_start(self,request):
        
        provider = self.options['provider']
        callback_uri = '{0}/auth/{1}/callback'.format(request.host_url,provider)
        
        
        flow = OAuth2WebServerFlow(            
            self.options['client_id'],
            self.options['client_secret'],
            self.options['scope'],
            auth_uri=self.options['auth_uri'],
            token_uri=self.options['token_uri'],
        )
        
        flow.params['state'] = request.path_url
        authorize_url = flow.step1_get_authorize_url(callback_uri)
        logging.error(flow)
        request.session.data[self.options['session_key']] = pickle.dumps(flow)
        request.session.put()
        return authorize_url

    def auth_callback(self, req):
        
        if req.GET.get('error'):
            return req.GET.get('error')
        
        flow = pickle.loads(str(req.session.data.get(self.options['session_key'])))
        
        if flow is None:
            self.raise_error('And Error has occurred. Please try again.')
        
        #Oauth2 Credentials Object
        req.credentials = flow.step2_exchange(req.params)
        user_info = self.user_info(req)
        
        return req.credentials,user_info
        

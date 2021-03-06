from __future__ import absolute_import
import cPickle as pickle
import httplib2
import webapp2
from oauth2client.client import OAuth2WebServerFlow
import logging
from models import authprovider

class OAuth2(webapp2.RequestHandler):

    def http(self, req):
        """Returns an authorized http instance.
        """
        if req.credentials is not None and not req.credentials.invalid:
            return req.credentials.authorize(httplib2.Http())

    def auth_start(self,request,front_page=False):
        

        for k,v in request.GET.iteritems():
            logging.info('{0} - {1}'.format(k,v))
        provider = self.options['provider']
        if front_page:
            redirect_uri = request.host_url + '/?' + '&'.join( '{0}={1}'.format(v,request.get(v)) for v in request.GET )
        else:
            redirect_uri =  '{0}/auth/{1}/callback'.format(request.host_url,provider)
        flow = OAuth2WebServerFlow(            
            self.options['client_id'],
            self.options['client_secret'],
            self.options['scope'],
            auth_uri=self.options['auth_uri'],
            token_uri=self.options['token_uri'],
            redirect_uri= redirect_uri
        )

        logging.info(redirect_uri)

        flow.params['state'] = request.path_url
        authorize_url = flow.step1_get_authorize_url()

        request.session.data[self.options['session_key']] = pickle.dumps(flow)
        request.session.put()

        return authorize_url

    def auth_callback(self, req):
        
        if req.GET.get('error'):
            return {'error': req.GET.get('error')}

        flow = pickle.loads(str(req.session.data.get(self.options['session_key'])))
        
        if flow is None:
            return {'error':'Error contacting Facebook. Please try again.'}
        
        #Oauth2 Credentials Object
        req.credentials = flow.step2_exchange(req.params)
        user_info = self.user_info(req)
        
        return {
            'credentials':req.credentials,
            'user_info':user_info
            }
        

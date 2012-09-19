import webapp2
import webob
from handlers import session
from auth_helpers import facebook,password
import logging
from models import user as _user
from models import authprovider

auth_secret_key = 'shaisd8f9as8d9fashd89fahsd9f8asdf9as8df9sa8dfa9schJKSHDAJKSHDJAsd9a8sd9sa'


class FacebookAuth(webapp2.RequestHandler):
    
    @session.manage_user
    def start(self):
        redirect_uri = facebook.FacebookAuth().auth_start(self.request)
        
        resp = webob.exc.HTTPTemporaryRedirect(location=redirect_uri)
        
        return self.request.get_response(resp)

    @session.manage_user
    def callback(self):
        
        callback = facebook.FacebookAuth().auth_callback(self.request)
        auth_id = authprovider.AuthProvider.generate_auth_id('facebook', callback['user_info']['id'])
        
        #auth_id is their authenticated facebook id
        
        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
        
        if matched_at:
            #login the facebook user
            self.request.session.upgrade_to_user_session(matched_at.user_id)
        
        else:
            
            at_user = self.request.session.user
                
            if not at_user:
                at_user = _user.User._create(name=callback['user_info']['displayName'])
            
            new_at = authprovider.AuthProvider._create(user=at_user,auth_id=auth_id,user_info=callback['user_info'],credentials=callback['credentials'])
                
            self.request.session.upgrade_to_user_session(at_user._get_id())
        
        resp = webob.exc.HTTPTemporaryRedirect(location='/')
        
        return self.request.get_response(resp)
    
        
class AuthLogout(webapp2.RequestHandler):
    
    @session.manage_user
    def get(self):        
        session=self.request.session
        if session is not None:
            session.user_id=None
            session.put()
        self.redirect('/')
            
    
import webapp2
import webob
from handlers import session
from auth_helpers import facebook
import logging
import json
from models import user as _user
from models import authprovider
from webapp2_extras import security
from google.appengine.ext import ndb
import shg_utils
from handlers.jinja import Jinja2Handler

class PasswordAuth(Jinja2Handler):
    
    error_msg = 'We were unable to log you on using the supplied email address and password.'
    
    @session.manage_user
    def start(self):
        password = self.request.POST['password']
        email = self.request.POST['email']
        auth_id = authprovider.AuthProvider.generate_auth_id('password',email)
        
        auth_token = authprovider.AuthProvider._get_by_auth_id(auth_id)
        
        if auth_token is None:
	    raise Exception(self.error_msg)
    
        if not security.check_password_hash(password=password,pwhash=auth_token.password_hash,pepper=shg_utils.password_pepper):
	    raise Exception(self.error_msg)
        
        self.request.session.upgrade_to_user_session(auth_token.user_id)
        
        return self.redirect('/')


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
	        raise Exception('Sorry your Facebook account is not assocaited with a Sharehouse Game account. Please login to your Sharehouse Game account using your email/password you setup when you joined, and then click the add Facebook button.')
	
                #at_user = _user.User._create(name=callback['user_info']['displayName'])
            
            new_at = authprovider.AuthProvider._create(user=at_user,auth_id=auth_id,user_info=callback['user_info'],credentials=callback['credentials'])
                
            #self.request.session.upgrade_to_user_session(at_user._get_id())
        
        return self.redirect('/')
    
        
class AuthLogout(webapp2.RequestHandler):
    
    @session.manage_user
    def get(self):        
        session=self.request.session
        if session is not None:
            session.user_id=None
            session.put()
        self.redirect('/')

class AuthSignup(Jinja2Handler):
    
    
    @ndb.transactional(xg=True)
    def post(self):
        
        name = self.request.get('name')
        email = self.request.get('email')
        password = self.request.get('password')
        
        if not name or not email or not password:
            raise Exception('Error not all values passed')
            
        auth_id = authprovider.AuthProvider.generate_auth_id('password', email)
            
        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
        
        if matched_at:
            raise Exception('Error email already exists in system')
        
        
        password_hash = security.generate_password_hash(password=password,pepper=shg_utils.password_pepper)
        token = _user.EmailHash.create(name=name,email=email,password_hash=password_hash)
        
        token.send_email(self.request.host_url,'new_user')
        
        resp = {
                    'success': 'Validation email sent. Please check your email!'
                }
        
        self.json_response(json.dumps(resp))
    
        return
    
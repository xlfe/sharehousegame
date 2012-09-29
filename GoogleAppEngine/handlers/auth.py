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
from time import sleep

class PasswordAuth(Jinja2Handler):
    
    @session.manage_user
    def start(self):
	error_msg = 'We were unable to log you on using the supplied email address and password. Do you need to reset your password?'
	password = self.request.POST['password']
	email = self.request.POST['email']
	auth_id = authprovider.AuthProvider.generate_auth_id('password',email)
	
	auth_token = authprovider.AuthProvider._get_by_auth_id(auth_id)
	
	if auth_token is None or not security.check_password_hash(password=password,pwhash=auth_token.password_hash,pepper=shg_utils.password_pepper):
	    return self.generic_error(title='Error logging in',message=error_msg,action='Password reset &raquo;',
				      action_link="""#login" data-toggle="modal" onclick="$('#password-reset').click();" """)
	    
	self.request.session.upgrade_to_user_session(auth_token.user_id)
	if self.request.POST.get('dont_persist') == "True":
	    self.response.set_cookie('_eauth', self.request.session.serialize(),expires=None)
	    
	
	
	return self.redirect('/')
    
    def reset(self):
	
	email = self.request.POST['email']
	
	auth_id = authprovider.AuthProvider.generate_auth_id('password',email)
	auth_token = authprovider.AuthProvider._get_by_auth_id(auth_id)
	
	if not auth_token:
	    return self.generic_error(title='Account not found',message="We're sorry, we couldn't find an account with email address '{0}'".format(email),
				      action='Sign up &raquo;',action_link='/')
	token = _user.EmailHash.get_or_create(email=email,user_id=auth_token.user_id,password_hash='reset')
	
	reason = token.limited()
	
	if reason:
	    return self.generic_error(title='Unable to send verification email',message=reason)
	
	if token.send_email(self.request.host_url,'reset_password'):
	    self.generic_success(title='Verification email sent',message='Please follow the instructions in your email inbox to reset your password')
	else:
	    self.generic_error(title='Unable to send verification email',messsage='An unknown error occurred, please try again')
	
	return


class FacebookAuth(Jinja2Handler):
    
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
		return self.generic_error(title='Unknown user',message="We're sorry, your Facebook account is not assocaited with a Sharehouse Game account. Please login to your Sharehouse Game account using your email/password you setup when you joined, and then click the add Facebook button.",
					  action="Login",action_link='#login" data-toggle="modal')
	
                #at_user = _user.User._create(name=callback['user_info']['displayName'])
            
            new_at = authprovider.AuthProvider._create(user=at_user,auth_id=auth_id,user_info=callback['user_info'],credentials=callback['credentials'])
                
            #self.request.session.upgrade_to_user_session(at_user._get_id())
        sleep(1)
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
    
    def post(self):

	name = self.request.get('name')
	email = self.request.get('email')
	password = self.request.get('password')
	
	if not name or not email or not password:
	    raise Exception('Error not all values passed')
	    
	auth_id = authprovider.AuthProvider.generate_auth_id('password', email)
	    
	matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
	
	if matched_at:
	    return self.json_response(json.dumps({'failure':'Email already exists in system &raquo; <a href="#login" class="btn btn-small btn-success" data-toggle="modal" >Login or reset password</a>'}))
	
	password_hash = security.generate_password_hash(password=password,pepper=shg_utils.password_pepper)
	token = _user.EmailHash.get_or_create(name=name,email=email,password_hash=password_hash)
	
	reason = token.limited()
	
	if reason:
	    return self.json_response(json.dumps({'failure':reason}))
	
	if token.send_email(self.request.host_url,'new_user'):
	    return self.json_response(json.dumps({'success':'Validation email sent. Please check your inbox!'}))
	else:
	    return self.json_response(json.dumps({'failure':'Unable to send email - please try again shortly'}))
	    

    
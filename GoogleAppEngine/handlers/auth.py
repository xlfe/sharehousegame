import webapp2
import webob
from handlers import session
from auth_helpers import facebook,password
import logging
from models import user as _user
from models import authprovider

auth_secret_key = 'shaisd8f9as8d9fashd89fahsd9f8asdf9as8df9sa8dfa9schJKSHDAJKSHDJAsd9a8sd9sa'


class AuthHandler(webapp2.RequestHandler):
    
    providers = {'facebook':facebook.FacebookAuth
                   ,'password':password.PasswordAuth}
 
    
    @session.manage_user
    def begin(self,provider):
        """Starts the authentication transaction"""
        
        if provider in self.providers:
            redirect_uri = self.providers[provider]().auth_start(self.request)
        else:
            raise Exception('Unknown auth provider')
            
        resp = webob.exc.HTTPTemporaryRedirect(location=redirect_uri)
        
        return self.request.get_response(resp)
        
    @session.manage_user
    def callback(self,provider):
        
        if provider in self.providers:
            credentials,user_info = self.providers[provider]().auth_callback(self.request)
        else:
            raise Exception('unknown auth provider')
        
        at_user = self.get_user(
            auth_id=user_info['auth_id'],
            user_info=user_info,
            credentials=credentials,
            user=self.request.session.user)
        
        self.request.session.user_id = at_user._get_id()
        self.request.session.put()
        
        resp = webob.exc.HTTPTemporaryRedirect(location='/')
        
        return self.request.get_response(resp)
        

    def get_user(self, auth_id, user_info, credentials, user):
        """
        Return the user associated with the auth token, or create a user and
        associate them with the token and return them"""
        
        existing_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
        session_user = user
        
        db_user = _user.User._get_user_from_email(user_info['info']['email'])
        
        if db_user and not existing_at:
            if not session_user or session_user._get_id() != db_user._get_id():
                raise Exception('Please login before attempting to add a second authentication method to your account.')
    
        if existing_at and session_user:
            #if the user is logged on, and the at is for that user, do nothing
            if existing_at.user_id == session_user._get_id():
                return session_user
            else:
                raise Exception('Access token already assigned to another user')
        
        if existing_at and not session_user:
            #Access token exists, but the user is not logged on
            return _user.User._get_user_from_id(existing_at.user_id)
        
        if session_user and not existing_at:
            #User is adding an authentication method
            logging.info('Existing user but no existing at, creating one')
            new_at = models.authprovider.AuthProvider._create(user=session_user,auth_id=auth_id,user_info=user_info,credentials=credentials)
            return session_user
            
        if not session_user and not existing_at:
            #New user/new access token
            new_user = models.user.User._create()
            new_user.primary_email = user_info['info']['email']
            new_user.display_name = user_info['info']['displayName']
            new_user.put()
            new_at = models.authprovider.AuthProvider._create(user=new_user,auth_id=auth_id,user_info=user_info,credentials=credentials)
            return new_user
            
        raise Exception('Logic failure in get_or_create_auth_token')
    
    @session.manage_user
    def logout(self):        
        session=self.request.session
        if session is not None:
            session.user_id=None
            session.put()
        self.redirect('/')
                
    
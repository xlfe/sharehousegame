import webapp2
import models
from handlers import session
from google.appengine.ext import ndb
from auth import facebook,password

auth_secret_key = 'shaisd8f9as8d9fashd89fahsd9f8asdf9as8df9sa8dfa9schJKSHDAJKSHDJAsd9a8sd9sa'

class AuthProvider(ndb.Model):
    """
    AuthProvider stores the authentication credentials (eg from Facebook)
    for a User - each user may have multiple AuthProviders
    """
    _default_indexed = False
    user_id = ndb.IntegerProperty(indexed=True)
    user_info = ndb.JsonProperty(indexed=False, compressed=True)
    credentials = ndb.PickleProperty()
    password_hash = ndb.StringProperty(indexed=False)

    @classmethod
    def _get_by_auth_id(cls, auth_id):
        """Returns a AuthToken based on a auth_id."""
        
        return cls.get_by_id(id=auth_id)
    get_by_auth_id = _get_by_auth_id

    @classmethod
    def _create(cls, user, auth_id, **kwargs):
        """Create an auth_token, must specify a user_id"""
        
        auth_token = cls.get_by_id(id=auth_id)
        
        if auth_token:
            raise Exception('Trying to create a duplicate auth token')
            
        auth_token = cls(id=auth_id,user_id=user._get_id())
        auth_token.populate(**kwargs)
        auth_token.put()
        
        return auth_token
    
    @staticmethod
    def generate_auth_id(provider, uid, subprovider=None):
        """Standardized generator for auth_ids
        """
        if subprovider is not None:
            provider = '{0}#{1}'.format(provider, subprovider)
        return '{0}:{1}'.format(provider, uid)
 

class AuthHandler(webapp2.RequestHandler):
    
    @session.manage_session
    def begin(self,provider):
        """Starts the authentication transaction"""
        
        providers = {'facebook':facebook.FacebookAuth
                     ,'password':password.PasswordAuth}
 
        if provider in providers:
            redirect_uri = providers[provider].auth_start(self)
        else:
            raise Exception('Unknown auth provider')

        resp = webob.exc.HTTPTemporaryRedirect(location=redirect_uri)

        resp.request = req
        return resp(environ, start_response)
        
        
        
        
        

    def get_or_create_auth_token(self, auth_id, user_info, credentials, user):
        """Callback where we've got an Auth Token from our provider
        and we need to decide what to do with it"""
        
        existing_at = models.AuthProvider.get_by_auth_id(auth_id)
        existing_user = user
        
        duplicate_user = models.User._get_user_from_email(user_info['info']['email'])
        
        if duplicate_user:
            if existing_at.user_id != duplicate_user._get_id():
                return self.raise_error('Please login before attempting to add a second authentication method to your account.')
        
        if existing_at and existing_user:
            #if the user is logged on, and the at is for that user, do nothing
            if existing_at.user_id == existing_user._get_id():
                return existing_at
            else:
                raise Exception('Access token already assigned to another user')
        
        if existing_at and not existing_user:
            #User has already signed up, and is logging on
            return existing_at
        
        if existing_user and not existing_at:
            #User is adding an authentication method
            logging.error('Existing user but no existing at, creating one')
            return models.AuthProvider._create(existing_user,auth_id,user_info,credentials)
            
        if not existing_user and not existing_at:
            #New user/new access token
            new_user = models.User._create()
            return models.AuthProvider._create(new_user,auth_id,user_info,credentials)
            
        raise Exception('Logic failure in get_or_create_auth_token')
                
    
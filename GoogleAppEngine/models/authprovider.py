
from google.appengine.ext import ndb


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
 
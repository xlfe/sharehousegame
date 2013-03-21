from __future__ import absolute_import
import json
from auth_helpers.oauth2 import OAuth2
from models import authprovider
import os
from auth_helpers.secrets import FACEBOOK_APP_KEY,FACEBOOK_APP_SECRET

ON_DEV = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

class FacebookAuth(OAuth2):

    @property
    def options(self):
        return {
            'provider': 'facebook',
            'site_uri': 'https://graph.facebook.com',
            'auth_uri': 'https://graph.facebook.com/oauth/authorize',
            'token_uri': 'https://graph.facebook.com/oauth/access_token',
            'client_id': FACEBOOK_APP_KEY,
            'client_secret': FACEBOOK_APP_SECRET,
            'scope': 'publish_actions',
            'session_key': '_auth_strategy:facebook'
            }

    def user_info(self, req):
        
        url = "https://graph.facebook.com/me?access_token=" + req.credentials.access_token
        
        res, results = self.http(req).request(url)
        
        if res.status is not 200:
            raise Exception('There was an error contacting Facebook. Please try again.')
            
        user = json.loads(results)
        
        return {
                'id': user['id'],
                'displayName': user.get('name'),
                'birthday': user.get('birthday'), # user_birthday
                'gender': user.get('gender'),
                'utcOffset': user.get('timezone'),
                'locale': user.get('locale'),
                'verified': user.get('verified'),
                'email': user.get('email'), 
                'nickname': user.get('login'),
                'location': user.get('location'), # user_location
                'aboutMe': user.get('bio'),
                'image': "http://graph.facebook.com/{0}/picture?type=square".format(user.get('id')),
                'homepage': user.get('link'),
                'raw_info': user
            }



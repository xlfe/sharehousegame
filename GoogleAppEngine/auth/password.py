"""
    engineauth.strategies.password
    ============================

    OAuth2 Authentication Strategy
    :copyright: (c) 2011 Kyle Finley.
    :license: Apache Sotware License, see LICENSE for details.

    :copyright: (c) 2010 Google Inc.
    :license: Apache Software License, see LICENSE for details.
"""
from __future__ import absolute_import
from engineauth import models
from engineauth.strategies.base import BaseStrategy
from webapp2_extras import security
import webapp2
import logging



class PasswordAuth(webapp2.RequestHandler):

    def user_info(self, req):
        user_info = {
            'email' : req.POST['email']
            #,'displayName':req.POST['name']
        }
        
        auth_id = models.AuthProvider.generate_auth_id(req.provider, user_info['email'])
        
        return {
            'auth_id': auth_id,
            'info': user_info,
        }

    def get_or_create_auth_token(self, auth_id, user_info, **kwargs):
        """
        
        """
        pepper='IOASJoasjdioajsd(A*S9a8sd9hasudhasih2i1h2ueh1*A(S*D('
        password = kwargs.pop('password')        
        existing_user = kwargs.pop('user')
        
        auth_token = models.AuthProvider._get_by_auth_id(auth_id)
        
        if auth_token is None:
            # We haven't seen this email address used to authenticate before
            
            # Check for an existing user with this email address as their primary email address
            duplicate_user = models.User._get_user_from_email(user_info['email'])
            logging.error(duplicate_user)
            
            if duplicate_user:
                #if the existing user is not the logged in user, don't continue
                if duplicate_user != existing_user:
                    return self.raise_error('Please login before attempting to add a second authentication method to your account.')
            
            #There is no-one registered using this email address, so lets continue
            if existing_user:
                associate_user = existing_user
            else:
                associate_user = models.User._create()
             #   associate_user.display_name = user_info['displayName']
                associate_user.primary_email = user_info['email']
                associate_user.put()
                
            password_hash = security.generate_password_hash(password=password,pepper=pepper)
            auth_token = models.AuthProvider._create(user=associate_user,auth_id=auth_id,user_info=user_info,password_hash=password_hash)
        else:
            #Check the password hash against what we've got...
            
            if not security.check_password_hash(password,auth_token.password_hash,pepper):
                return self.raise_error('We were unable to log you on using the supplied email address and password.')
        
        return auth_token

    def handle_request(self, req):
        
        #when /auth/password is called this is where the request ends up
        #auth flow:
        #lookup the auth token using the email address
        # if it existst, check the password
        #  if the password is correct, log the user in
        # if it doesnt exist, create the auth token (and potentially user)
        # 
        
        
        # confirm that required fields are provided.
        password = req.POST['password']
        email = req.POST['email']
        if not password or not email:
            return self.raise_error('Please provide a valid email '
                                    'and a password.')
        
        user_info = self.user_info(req)
        auth_token = self.get_or_create_auth_token(
            auth_id=user_info['auth_id'],
            user_info=user_info['info'],
            password=password,
            user=req.user)
        req._get_user_from_auth_token(auth_token)
        #req.associate_user_with_auth_token(auth_token)
        return req.get_redirect_uri()

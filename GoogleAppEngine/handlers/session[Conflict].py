"""handlers/session.py

Called from any of the jinja2 or api handlers to:

    manage the session cookie
    
    -ie checks if we have a cookie
    -if not, set the session cookie
    
"""

from google.appengine.ext import ndb
import json
from functools import wraps
import shg_utils
import webapp2
from webapp2_extras import securecookie
from webapp2_extras import security
import logging
from models import user as _user,authprovider,house
from handlers.jinja import Jinja2Handler
from datetime import datetime, timedelta

serializer_secret = 'dfs9adh8fas0dbfash0d8fbaH8A0U8AHU80UA8DQUW98&D(SA^A^%D&*'

def manage_session(fn):
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        
        self.request.session = None
        value = self.request.cookies.get('_eauth')
        
        if value:
            self.request.session = Session.get_by_value(value)
        
        if self.request.session:
            if self.request.session.last_seen < datetime.now() + timedelta(minutes=-30):
                self.request.session.last_seen = datetime.now()
                self.request.session.put()
        else:
            self.request.session = Session.create()
            self.response.set_cookie('_eauth', self.request.session.serialize(),expires=datetime.now() + timedelta(weeks=14))
            
        return fn(self,*args,**kwargs)
    return wrapper
        
def manage_user(fn):
    @manage_session
    @wraps(fn)  
    def wrapper(self, *args, **kwargs):
        """self is a webapp2.RequestHandler instance"""
        
	self.request.session.user = self.request.session.get_user()
      
        return fn(self,*args, **kwargs)
    return wrapper


class Session(ndb.Model):
    _default_indexed = False
    
    created = ndb.DateTimeProperty(auto_now_add=True)
    last_seen = ndb.DateTimeProperty(auto_now=True)
    user_id = ndb.IntegerProperty()
    data = ndb.PickleProperty(compressed=True, default={}) #used by oauth
    email_hash = ndb.IntegerProperty()
    
    def get_user(self):
        if self.user_id:
            return _user.User.get_by_id(self.user_id)
        else:
            return None

    @staticmethod
    def _generate_sid():
        return security.generate_random_string(entropy=192)

    @staticmethod
    def _serializer():
        return securecookie.SecureCookieSerializer(serializer_secret)

    def hash(self):
        """
        Creates a unique hash from the session.
        This will be used to check for session changes.
        :return: A unique hash for the session
        """
        return hash(str(self))
    
    def _get_session_id(self):
        return str(self.key.id())
        
    def serialize(self):
        values = {'session_id': self._get_session_id()}
        return self._serializer().serialize('_eauth', values)

    @classmethod
    def deserialize(cls, value):
        return cls._serializer().deserialize('_eauth', value)

    @classmethod
    def get_by_value(cls, value):
        v = cls.deserialize(value)
        if not v:
            return None
        sid = v.get('session_id')
        return cls.get_by_sid(sid) if sid else None

    @classmethod
    def get_by_sid(cls, sid):
        return cls.get_by_id(sid)

    def upgrade_to_user_session(self, user_id):
        self.user_id = user_id
        self.put()

    @classmethod
    def create(cls):
        """Create a session (never happens if we already know who the user is)"""
        session_id = cls._generate_sid()
        session = cls(id=session_id)
        session.put()
        return session

    @classmethod
    def remove_inactive(cls, days_ago=30, now=None):
        import datetime
        # for testing we want to be able to pass a value for now.
        now = now or datetime.datetime.now()
        dtd = now + datetime.timedelta(-days_ago)
        for s in cls.query(cls.last_seen < dtd).fetch():
            s.key.delete()


class EmailToken(Jinja2Handler):
    
    @ndb.transactional(xg=True)
    @manage_user
    def verify(self,id,hash):
        
        if id and hash:
            token = _user.EmailHash.get_token(id,hash)
        
        if not id or not hash or not token:
            return self.generic_error(title='Unknown email token',message="We're sorry, we don't recognize that email token.")
            
        
        if not token.user_id:

            if token.house_id:
                
                if self.request.session.user:
                    if self.request.session.user.verified_email == token.email:
                        
                        #existing user clicking on a join house email...
                        
                        self.request.session.user.house_id = token.house_id
                        self.request.session.user.put()
                        hse = house.House._get_house_by_id(self.request.session.user.house_id)
                        hse.add_user(self.request.session.user)
                        self.generic_success(title='Welcome to {0}!'.format(hse.name),
                                             message='You have successfully joined the house',action='Continue &raquo;',action_link='/')
                        token.key.delete()
                        return
                    else:
                        raise Exception('Please make sure you have logged in as yourself')
                    
                else:
                    if not self.request.get('password'):
                        #Show the user a signup form to get a password and confirm their name
                    
                        assert token.email, 'Should have a verified email here...'
                        
                        self.render_template('not_logged_in.html',{
                                    'signup_name':token.name,
                                    'referred_by':token.referred_by,
                                    'signup_email':token.email,
                                    'signup_action':self.request.host_url + token.get_link()
                                    })
                        return
                    
                    else:
                        #create account
                        name = self.request.get('name')
                        password = self.request.get('password')
                        
                        if not name or not password:
                            raise Exception('Error not all values passed')
            
                        auth_id = authprovider.AuthProvider.generate_auth_id('password', token.email)
            
                        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
        
                        if matched_at:
                            raise Exception('Error email already exists in system')
        
                        password_hash = security.generate_password_hash(password=password,pepper=shg_utils.password_pepper)
                        
                        new_user = _user.User._create(house_id = token.house_id, display_name=name,verified_email=token.email)
            
                        auth_id = authprovider.AuthProvider.generate_auth_id('password', token.email)
            
                        new_at = authprovider.AuthProvider._create(user=new_user,auth_id=auth_id,password_hash=password_hash)
                        
                        self.request.session.upgrade_to_user_session(new_user._get_id())
                        hse = house.House._get_house_by_id(token.house_id)
                        hse.add_user(new_user)
                        invited_by = token.referred_by
                        token.key.delete()
                        return self.json_response(json.dumps({'success':'Account created!','redirect':'/'}))
                        
            else:
                
                #must be a new signup - create account
        
                new_user = _user.User._create(house_id = token.house_id, display_name=token.name,verified_email=token.email)
            
                auth_id = authprovider.AuthProvider.generate_auth_id('password', token.email)
            
                new_at = authprovider.AuthProvider._create(user=new_user,auth_id=auth_id,password_hash=token.password_hash)
            
                self.generic_success(title='Thank you!',message='Your account is now enabled.',action='Login',action_link='#login" data-toggle="modal')
                                                                     
                token.key.delete()
                
        else:
            #has user_id - modify existing account
            if token.password_hash == "reset":
                new_password = self.request.get('password',None)
                
                if new_password:
                    
                    auth_id = authprovider.AuthProvider.generate_auth_id('password', token.email)
                    
                    at = authprovider.AuthProvider.get_by_auth_id(auth_id)
                    at.password_hash = security.generate_password_hash(password=new_password,pepper=shg_utils.password_pepper)
                    at.put()
                    token.key.delete()
                    
                    return self.generic_success(title='Account updated',message='You have successfully reset your password',
                                                action='Login',action_link='#login" data-toggle="modal')
                else:
                    
                    return self.generic_question(title='Reset password',message='Please enter your new password',form_action="",submit_name='Save',
                                                 questions = [{'label':'New password','name':'password','type':'password'}])

                    
                
                
                #prompt to set new passrod
                return
            if token.email:
                #update user's email address
                return
    
            
        return


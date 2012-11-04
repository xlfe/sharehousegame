from google.appengine.ext import ndb
import json
from webapp2_extras import security
from shg_utils import prettydate
import shg_utils
from models.email import EmailHash
from models import user as _user, authprovider
from functools import wraps

from datetime import datetime, timedelta
import logging

def manage_house(fn):
    @_user.manage_user
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        
        if self.request.session.user:
            if self.request.session.user.house_id:
                self.request.session.user.house = House._get_house_by_id(self.request.session.user.house_id)
        
        return fn(self,*args, **kwargs)
    return wrapper
    
        
class HouseInvite(EmailHash):
    """Invite email"""
    
    name = ndb.StringProperty(required=True)
    house_id = ndb.IntegerProperty()
    referred_by = ndb.StringProperty()
    _default_hash_length = 32
    
    def render_body(self,host_url):
        firstname = self.name.split(' ')[0]
        
        email_body = 'Dear {0},\n\n' + \
          "Your housemate {1} would like you to join them in Sharehouse Game!\n" + \
          "In order to join their sharehouse, please click the link below and follow the instructions on the bottom of the page that opens:\n" + \
          "{2}\n\n" + \
          "Bert Bert\n" + \
          "Sharehouse Game - Support\n" + \
          "http://www.SharehouseGame.com\n"
    
        return email_body.format(firstname,self.referred_by,host_url+self.get_link())
        
    def render_subject(self):
        firstname = self.name.split(' ')[0]
        return "{0}, {1} has sent you an invitation".format(firstname,self.referred_by)
    
    @ndb.transactional(xg=True)
    def matched_at(self,jinja,matched_at,loggedin_user):
        
        #existing user - must have joined seperately   
        if not loggedin_user:
            at_user = _user.User.get_by_id(matched_at.user_id)
            
        else:
            if loggedin_user.verified_email != self.email:
                
                jinja.request.session.user_id = None
                jinja.request.session.put()
                at_user = _user.User.get_by_id(matched_at.user_id)
            else:
                at_user = loggedin_user
        
        at_user.house_id = self.house_id
        at_user.put()
        
        hse = House._get_house_by_id(self.house_id)
        hse.add_user(at_user)
        self.key.delete()
        
        return jinja.generic_success(title='Welcome to {0}!'.format(hse.name),
                             message='You have successfully joined the house',action='Continue &raquo;',action_link='/')
    
    @ndb.transactional(xg=True)    
    def create_account(self,jinja,auth_id):
        #create account
        name = jinja.request.get('name')
        password = jinja.request.get('password')
        
        if not name or not password:
            raise Exception('Error not all values passed')
        
        password_hash = security.generate_password_hash(password=password,pepper=shg_utils.password_pepper)
        
        new_user = _user.User._create(house_id = self.house_id, display_name=name,verified_email=self.email)
        
        new_at = authprovider.AuthProvider._create(user=new_user,auth_id=auth_id,password_hash=password_hash)
        
        jinja.request.session.upgrade_to_user_session(new_user._get_id())
        hse = House._get_house_by_id(self.house_id)
        hse.add_user(new_user)
        self.key.delete()
        
        return jinja.json_response(json.dumps({'success':'Account created!','redirect':'/'}))

    def verified(self,jinja):
        
        loggedin_user = _user.User._get_by_id(jinja.request.session.user_id) if jinja.request.session.user_id else None
        auth_id = authprovider.AuthProvider.generate_auth_id('password', self.email)
        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)
         
        if matched_at:
            return self.matched_at(jinja,matched_at,loggedin_user)
            
        else:
            
            if jinja.request.get('password'):
                
                return self.create_account(jinja,auth_id)
               
                
                
            else:
                return jinja.render_template('not_logged_in.html',{
                            'signup_name':self.name,
                            'referred_by':self.referred_by,
                            'signup_email':self.email,
                            'signup_action':jinja.request.host_url + self.get_link()
                            })
            
            

class InvitedUser(ndb.Model):
    _default_indexed=False
    
    name = ndb.StringProperty()
    email = ndb.StringProperty()
    initial_invite = ndb.DateTimeProperty(auto_now_add=True)
    
    def elapsed(self):
        
        if self.initial_invite < datetime.now() + timedelta(minutes=-5):
            return True
        return False

class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)
    timezone = ndb.StringProperty(required=True)
    invited_users = ndb.StructuredProperty(InvitedUser,repeated=True)
    users = ndb.IntegerProperty(repeated=True)

    def get_house_id(self):
        return self.key.id()
    
    @classmethod
    def _get_house_by_id(cls,id):
        
        return cls.get_by_id(int(id))
        
    def recent_activity(self):
        ra = []
        
        for h in HouseLog.query(ancestor=self.key).order(-HouseLog.when):


            log_user = _user.User._get_user_from_id(h.user_id) if h.user_id else None
            
            a = {'who': log_user.get_first_name() if log_user else ''
                 ,'when':prettydate(h.when)
                 ,'desc':h.desc
                 ,'points':h.points
                 ,'link':h.link}
            ra.append(a)
            
        return ra
    
    def add_house_event(self,**kwargs):
        hl = HouseLog(parent=self.key)
        hl.populate(**kwargs)
        hl.put()
    
    def get_users(self):
        user_list = []
        for u in self.users:
            user_list.append(_user.User._get_user_from_id(u))
        return user_list
    
    def add_user(self,user):
        self.users.append(user._get_id())
        self.invited_users = filter (lambda u: u.email != user.verified_email, self.invited_users )
        self.put()
        return
    
    def remove_user(self,user_id):
        self.users = filter ( lambda x: x != user_id, self.users )
        self.put()
        self.add_house_event(user_id,'left the house',0)
        
        if len(self.users) == 0:
            self.key.delete()
        
    
class HouseLog(ndb.Model):
    _default_indexed = False

    user_id = ndb.IntegerProperty()
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty(required=True)
    link = ndb.StringProperty()
    points = ndb.IntegerProperty(required=True)
    reference = ndb.KeyProperty(indexed=True)

        
    
    
    
from google.appengine.ext import ndb

from shg_utils import prettydate
from models import user as _user
from datetime import datetime, timedelta

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
        
        for h in HouseLog.query(ancestor=self.key).order(HouseLog.when):
            log_user = _user.User._get_user_from_id(h.user_id)
            
            a = {'who': log_user.get_first_name() if log_user else 'Unknown'
                 ,'when':prettydate(h.when)
                 ,'desc':h.desc
                 ,'points':h.points
                 ,'link':h.link}
            ra.append(a)
            
        return ra
    
    def add_house_event(self,user_id,desc,points,link=None):
        hl = HouseLog(parent=self.key,user_id=user_id,points=points,desc=desc,link=link)
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
    
    user_id = ndb.IntegerProperty(indexed=False)
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty(indexed=False)
    link = ndb.StringProperty(indexed=False)
    points = ndb.IntegerProperty(indexed=False)

        
    
    
    
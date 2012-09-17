from google.appengine.ext import ndb
from engineauth import models
from shg_utils import prettydate

class InvitedUser(ndb.Model):
    _default_indexed=False
    
    name = ndb.StringProperty()
    email = ndb.StringProperty()
    invited = ndb.DateTimeProperty()
    

class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)
    invited_users = ndb.StructuredProperty(InvitedUser,repeated=True)
    users = ndb.IntegerProperty(repeated=True)

    def get_house_id(self):
        return str(self.key.id())
    
    @classmethod
    def _get_house_by_id(cls,id):
        """Gets a user based on their ID"""
        
        return cls.get_by_id(int(id))
        
    def recent_activity(self):
        ra = []
        
        for h in HouseLog.query(ancestor=self.key).order(HouseLog.when):
            a = {'who':models.User._get_first_name(h.user_id)
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
            user_list.append(models.User._get_user_from_id(u))
        return user_list
            
        
    
class HouseLog(ndb.Model):
    
    user_id = ndb.IntegerProperty(indexed=False)
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty(indexed=False)
    link = ndb.StringProperty(indexed=False)
    points = ndb.IntegerProperty(indexed=False)

        
    
    
    
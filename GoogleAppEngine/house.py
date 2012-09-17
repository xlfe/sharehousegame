from google.appengine.ext import ndb
from engineauth import models
import datetime

def prettydate(d):
    diff = datetime.datetime.utcnow() - d
    s = diff.seconds
    if diff.days > 7 or diff.days < 0:
        return d.strftime('%d %b %y')
    elif diff.days == 1:
        return '1 day ago'
    elif diff.days > 1:
        return '{} days ago'.format(diff.days)
    elif s <= 1:
        return 'just now'
    elif s < 60:
        return '{} seconds ago'.format(s)
    elif s < 120:
        return '1 minute ago'
    elif s < 3600:
        return '{} minutes ago'.format(s/60)
    elif s < 7200:
        return '1 hour ago'
    else:
        return '{} hours ago'.format(s/3600)




class HouseUser(ndb.Model):
    _default_indexed=False
    
    name = ndb.StringProperty()
    email = ndb.StringProperty()
    user_id = ndb.StringProperty()
    invited = ndb.DateTimeProperty()


class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)
    users = ndb.StructuredProperty(HouseUser,repeated=True)

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
                 ,'link':h.link}
            ra.append(a)
            
        return ra
        
        
        
    
class HouseLog(ndb.Model):
    
    user_id = ndb.IntegerProperty(indexed=False)
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty(indexed=False)
    link = ndb.StringProperty(indexed=False)
    
def add_house_event(house_id,user_id,desc,link):
    
    hl = HouseLog(parent=ndb.Key('House',int(house_id)),user_id=int(user_id),desc=desc,link=link)
    hl.put()
    
    
    
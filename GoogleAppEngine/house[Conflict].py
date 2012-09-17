from google.appengine.ext import ndb
from engineauth import models

class HouseUser(ndb.Model):
    _default_indexed=False
    
    name = ndb.StringProperty()
    email = nbd.StringProperty()
    user_id = ndb.StringProperty()
    invited = ndb.DateTimeProperty()


class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)
    users = ndb.StructuredProperty(HouseUser,repeated=True)

    @classmethod
    def get_house_by_user(cls,user):
        return None
    
    
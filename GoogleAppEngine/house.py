from google.appengine.ext import ndb
from engineauth import models


class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)
    users = ndb.StringProperty(repeated=True)
    invites = ndb.StringProperty(repeated=True)

    @classmethod
    def get_house_by_user(cls,user):
        return None
    
    
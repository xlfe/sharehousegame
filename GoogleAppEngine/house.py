from google.appengine.ext import ndb
from engineauth import models


class House(ndb.Model):
    created = ndb.DateTimeProperty(auto_now_add = True, indexed=False)
    name = ndb.StringProperty(indexed=False)

def get_house(user):
    pass
    
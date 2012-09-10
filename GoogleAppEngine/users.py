from google.appengine.ext import db



class UserAuth(db.Model):
    created = db.DateTimeProperty(auto_now_add = True, indexed=False)
    name = db.StringProperty(indexed=False)
    email = db.StringProperty()
    fb_token = db.StringProperty()
    cookie_secret = db.StringProperty()

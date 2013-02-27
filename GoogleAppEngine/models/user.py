import logging


from google.appengine.ext import ndb
from webapp2_extras import security,securecookie
from google.appengine.api import mail
import datetime
import os
from functools import wraps
from math import exp
import json
from shg_utils import prettydate
import shg_utils
from models.email import EmailHash
from models import authprovider
from handlers.session import manage_session
from google.appengine.api import users

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

def manage_user(fn):
    @manage_session
    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        """self is a webapp2.RequestHandler instance"""

        if self.request.session.user_id:
            self.request.session.user = User._get_user_from_id(self.request.session.user_id)
            self.request.session.user.house = None

        return fn(self,*args, **kwargs)
    return wrapper


class EmailVerify(EmailHash):
    """Verification email"""
    _default_hash_length = 32
    user_id = ndb.IntegerProperty()
    password_hash = ndb.StringProperty()
    name = ndb.StringProperty(required=True)

    def render_body(self,host_url):
        firstname = self.name.split(' ')[0]

        email_body = "Dear {0},\n\n" + \
            "Thank you for signing up for Sharehouse Game.\n" + \
            "We just need you to click the link below to confirm your email address:\n{1}\n\n"+ \
            "Please let us know if you have any questions.\n" + \
            "If you didn't signup for Sharehouse Game, please disregard this email.\n\n" + \
            "Bert Bert\n" + \
            "Sharehouse Game - Support\n" +\
            "http://www.SharehouseGame.com\n"
        return email_body.format(firstname,host_url+self.get_link())

    def render_subject(self):
        firstname = self.name.split(' ')[0]
        return "{0}, please verify your email address".format(firstname)

    @ndb.transactional(xg=True)
    def verified(self,jinja):

        new_user = User._create(display_name=self.name,verified_email=self.email)
        auth_id = authprovider.AuthProvider.generate_auth_id('password', self.email)

        new_at = authprovider.AuthProvider._create(user=new_user,auth_id=auth_id,password_hash=self.password_hash)
        self.key.delete()

        return jinja.generic_success(title='Thank you!',message='Your account is now enabled.',action='Login',action_link='#login" data-toggle="modal')

def points_remaining(points_obj,days_offset=0):

    now= datetime.datetime.utcnow() + datetime.timedelta(days=days_offset)
    hours = int((now - points_obj.when).total_seconds()/(60*60))

    return calc_points_remaining(points_obj.points,hours)


def calc_points_remaining(initial_points,hours_elapsed):
    #decay constant determines the slope
    decay_const = -2.0

    proportion = ( decay_const / initial_points ) * ( initial_points - hours_elapsed )

    return int(max(0,initial_points +exp(decay_const)*initial_points - exp(proportion) * initial_points))

class User(ndb.Model):
    """
    The user is the actual individual"""

    _default_indexed=False
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)
    verified_email = ndb.StringProperty()
    display_name = ndb.StringProperty()
    house_id = ndb.IntegerProperty()
#    display_help =ndb.IntegerProperty(default=True)

    def _get_id(self):
        """Returns this user's unique ID, which is an integer."""
        return self.key.id()

    def _get_house_id(self):
        return self.house_id

    def _get_key(self):
        """gets the key for the user (ID and entity type)"""
        return self.key

    def get_first_name(self):
        return self.display_name.split(' ')[0]


    @classmethod
    def _create(cls,**kwargs):

        new_user = cls()
        new_user.populate(**kwargs)

        new_user.put()

        new_user.insert_points_transaction(points=100,desc='Joined Sharehouse Game!')

        return new_user


    def get_points_log(self):
        self._pts_lg_get = Points.query(ancestor=self.key).order(-Points.when).fetch_async()

    @property
    def pts_lg_obj(self):
        try:
            return self._pts_lg_obj
        except AttributeError:
            self._pts_lg_obj = self._pts_lg_get.get_result()
            return self._pts_lg_obj

    def points_log_json(self,days=31):

        now = datetime.datetime.utcnow()
        threshold = now + datetime.timedelta(days=-days)
        pts = []

        for p in self.pts_lg_obj:
            if threshold > p.when and points_remaining(p,-31) <= 1:
                continue

            hours = int((now - p.when).total_seconds()/(60*60))

            pts.append(
                json.dumps({'name':self.get_first_name(),
                            'desc':p.desc,
                            'points':p.points,
                            'hours_elapsed':hours})
            )

        return pts


    def points_log(self,days=31):
        pl = []

        for h in self.pts_lg_obj:

            #if datetime.datetime.utcnow() + datetime.timedelta(days=-days) > h.when:
            #    continue
            pr = points_remaining(h)
            if pr ==0 :
                continue
            a = {'when':prettydate(h.when)
                 ,'desc':h.desc
                 ,'points':pr}#points_remaining(h)}
            pl.append(a)

        return pl

    def points_balance(self):
        balance = 0
        #utc

        for p in self.pts_lg_obj:

            balance += points_remaining(p)

            #balance += p.points

        return int(balance)

    def needs_facebook(self):
        nfb = True
        try:
            for ap in authprovider.AuthProvider.query().filter(authprovider.AuthProvider.user_id == self._get_id()).iter():
                if str(ap.key.id())[:8] == "facebook":
                    nfb = False
        except:
            nfb = False

        return nfb

    def insert_points_transaction(self,points,desc,link=None,**kwargs):
        pl = Points(parent=self.key,desc=desc,points=points,link=link)
        pl.populate(**kwargs)
        pl.put()

    @classmethod
    def _get_user_from_id(cls, id):
        """"Gets a user based on their ID"""

        me = cls.get_by_id(int(id))
        me.get_points_log()

        return me

    @classmethod
    def _get_user_from_email(cls,email):
        """returns a user based on their primary email"""
        try:
            return cls.query().filter(cls.verified_email == email).iter().next()
        except StopIteration:
            return None


class Points(ndb.Model):
    _default_indexed=False
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty()
    link = ndb.StringProperty()
    points = ndb.IntegerProperty(required=True)
    reference = ndb.KeyProperty(indexed=True)


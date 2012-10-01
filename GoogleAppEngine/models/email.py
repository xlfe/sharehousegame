

from google.appengine.ext import ndb
import logging
from shg_utils import prettydate
from webapp2_extras import security,securecookie
from google.appengine.api import mail
from models import authprovider
import datetime
import os
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')


base_links = {
        'EmailVerify': 'v'
    ,   'EmailInvite':  'i'
    ,   'EmailRemind':  'r'
    ,   'EmailPasswordReset':'p'
}


class EmailHash(ndb.Model):
    """ Base class used to send emails with unique links"""
    
    _default_indexed = False

    last_emailed = ndb.DateTimeProperty()
    number_of_emails = ndb.IntegerProperty(default=0)
    
    token_hash = ndb.StringProperty(indexed=True,required=True)
    email = ndb.StringProperty(indexed=True,required=True)
    name = ndb.StringProperty(required=True)
    
    @property
    def base_link(self):
        raise Exception('Need to overwrite this...')
    
    @classmethod
    def _get(cls,**kwargs):
        """If there is an existing email hash of the same type, return it. Otherwise create a new one"""
        
        assert 'email' in kwargs, 'Unknown email address'
        email = kwargs['email']
        
        return cls.query(cls.email == email).get()
        
    @classmethod
    def _create(cls,**kwargs):
        
        assert 'email' in kwargs, 'No email supplied'
        
        new_hash = cls(token_hash=security.generate_random_string(length=35,pool=security.ALPHANUMERIC))
        new_hash.populate(**kwargs)
        new_hash.put()
        return new_hash
    
    @classmethod
    def get_or_create(cls,**kwargs):
        
        existing = cls._get(**kwargs)

        if not existing:
            return cls._create(**kwargs)
        else:
            return existing
    
    def get_link(self):
        return '/{0}/{1}/{2}/'.format(self.base_link,self.key.id(),self.token_hash)
        
    @classmethod
    def get_token(cls,id,hash):
        token = cls.get_by_id(id=int(id))
        
        if token:
            if token.token_hash==hash:
                return token
        
        return None
    
    def limited(self):
        """Returns a reason why we can't send an email, or None if we can!"""
        
        #Max emails in a 24 hour period
        if self.number_of_emails >= 6:
            if self.last_emailed < (datetime.datetime.now() + datetime.timedelta(days=-1)):
                self.number_of_emails = 0
                self.put()
                return None
            else:
                return 'Daily email limit reached (please try tomorrow).'
        
        #max of 1 email every 5 minutes
        if self.last_emailed:
            if self.last_emailed > (datetime.datetime.now() + datetime.timedelta(minutes=-5)):
                return "We've just licked the stamp :) - please check your email inbox or spam folder (or try again in a few minutes)."
        return False
    
    
    def send_email(self,base_url):
        
        if self.limited():
            return False

        message = mail.EmailMessage(sender="Sharehouse Game <bert@sharehousegame.com>")

        message.to = "{0} <{1}>".format(self.name,self.email)
        message.subject = self.render_subject()
        message.body = self.render_body(base_url)
        
        if DEBUG:
            logging.debug(message)
        
        if DEBUG:
            logging.info(message.body)
        else:
            message.send()
        
        self.last_emailed = datetime.datetime.now()
        self.number_of_emails = +1
        self.put()
        return True
    
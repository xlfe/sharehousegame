# -*- coding: utf-8 -*-
import webapp2
from webapp2_extras import jinja2
from engineauth import models
from google.appengine.ext import ndb
from house import get_house


class Jinja2Handler(webapp2.RequestHandler):
    """
        BaseHandler for all requests all other handlers will
        extend this handler

    """
    @webapp2.cached_property
    def jinja2(self):
        logging.error('im here')
        return jinja2.get_jinja2(app=self.app)

    def get_messages(self, key='_messages'):
        try:
            return self.request.session.data.pop(key)
        except KeyError:
            return None

    def render_template(self, template_name, template_values={}):
        messages = self.get_messages()
        if messages:
            template_values.update({'messages': messages})
            
        template_values['page_base'] = self.request.route.name
        
        self.response.write(self.jinja2.render_template(
            template_name, **template_values))

    def render_string(self, template_string, template_values={}):
        self.response.write(self.jinja2.environment.from_string(
            template_string).render(**template_values))

    def json_response(self, json):
        self.response.headers.add_header('content-type', 'application/json', charset='utf-8')
        self.response.out.write(json)

import logging

from functools import wraps

def check_user(fn):
    @wraps(fn)  
    def wrapper(self, *args, **kwargs):
        
      user = self.request.user if self.request.user else None
      
      if not user:
          self.render_template('not_logged_in.html')
          return
        
      return fn(self,*args, **kwargs)
    return wrapper
    

class PageHandler(Jinja2Handler):
    
    @check_user    
    def dashboard(self):
        session = self.request.session if self.request.session else None
        user = self.request.user if self.request.user else None
        auth_tokens = models.AuthProvider.query(ancestor=user._get_key())
      
        self.render_template('dashboard.html',{'user':user})
        
    @check_user
    def profile(self):
        
        user = self.request.user if self.request.user else None
        self.render_template('profile.html',{'user':user})
    
    @check_user
    def rentbills(self):
        self.profile()
    
    
    def logout(self):        
        session=self.request.session if self.request.session else None
        if session is not None:
            session.user_id=None
            session.put()
        self.redirect('/')





def wipe_datastore():
    users = models.User.query().fetch()
    profiles = models.AuthProvider.query().fetch()
    emails = models.UserEmail.query().fetch()
    tokens = models.AuthToken.query().fetch()
    sessions = models.Session.query().fetch()

    for t in [users, profiles, emails, tokens, sessions]:
        for i in t:
            i.key.delete()

class WipeDSHandler(webapp2.RequestHandler):

    def get(self):
        # TODO: discover why importing deferred outside of a
        # function causes problems with jinja2 filters.
        from google.appengine.ext import deferred
        deferred.defer(wipe_datastore)
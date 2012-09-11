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
        self.response.write(self.jinja2.render_template(
            template_name, **template_values))

    def render_string(self, template_string, template_values={}):
        self.response.write(self.jinja2.environment.from_string(
            template_string).render(**template_values))

    def json_response(self, json):
        self.response.headers.add_header('content-type', 'application/json', charset='utf-8')
        self.response.out.write(json)


class PageHandler(Jinja2Handler):

    def root(self):
        session = self.request.session if self.request.session else None
        user = self.request.user if self.request.user else None
        profiles = None
        name = None
        if user:
            profile_keys = [ndb.Key('AuthProvider', p) for p in user.auth_ids]
            profiles = ndb.get_multi(profile_keys)
            template = 'home.html'
        else:
            template = 'not_logged_in.html'
            
        self.render_template(template, {
            'user': user,
            'session': session,
            'profiles': profiles,
        })
        
    def logout(self):        
        self.response.delete_cookie('_eauth')
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
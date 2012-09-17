# -*- coding: utf-8 -*-
import webapp2
from webapp2_extras import jinja2
from engineauth import models
from google.appengine.ext import ndb
import house
import json
import logging
from functools import wraps

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


def check_user(fn):
    @wraps(fn)  
    def wrapper(self, *args, **kwargs):
        
        user = self.request.user if self.request.user else None
      
        if not user:
            self.render_template('not_logged_in.html')
            return
          
        house = user._get_house_id()
        
        if house is None:
            #new user, hasn't setup a house yet -> setup wizzard
            self.render_template('house_wizzard.html',{'user':user})
            return
        
        return fn(self,*args, **kwargs)
    return wrapper


def parse_form_data(data):
        
        if len(data) == 0:
            return
        
        form_data = {}
        data = json.loads(data)
        
        for item in data:
            for k,v in item.items():
                form_data[k] = v
        
        
        return form_data


class API(webapp2.RequestHandler):
    
    def api(self):
        
        resp = {'redirect':''}
        user = self.request.user if self.request.user else None
        
        if user:
            
            what = self.request.get('what')
            
            if what == "house-setup":
                
                if user._get_house_id():
                    logging.error('User already has house_id, should not be in house setup userid {0}'.format(user._get_id()))
                    return
                
                name = self.request.get('houseName')
                
                my_name = user.display_name
                my_email = user.primary_email
                
                housemates = []
                i = 0
                
                while True:
                    hm_name,hm_email = self.request.get('hm{0}_name'.format(i),None),self.request.get('email_hm_{0}'.format(i),None)
                    
                    if not (hm_name or hm_email):
                        break
                    
                    if len(hm_name) > 0:
                        
                        if hm_name == my_name or hm_email == my_email:
                            i+=1
                            continue
                        else:
                            hu = house.InvitedUser(name = hm_name,email=hm_email)
                        housemates.append(hu)
                    i+=1
                
                if len(housemates) > 1:
                    hse = house.House(name = name,invited_users=housemates,users=[user._get_id()])
                    hse.put()
                    
                user.house_id = hse.get_house_id()
                user.put()
                
                user.insert_points_transaction(points=100,desc='Setup your sharehouse')
                hse.add_house_event(user_id=user._get_id(),desc='setup the house',points=100)
                
                resp = {
                    'redirect':'?home',
                    'success':'House created {0} with {1} housemates'.format(name,i)
                }
        
        self.response.out.write(json.dumps(resp)) #self.request.params)

        

class PageHandler(Jinja2Handler):
    
    @check_user    
    def main(self):
        session = self.request.session
        user = self.request.user
        hse = house.House._get_house_by_id(user._get_house_id())

        self.render_template('{0}.html'.format(self.request.route.name if self.request.route.name != '' else 'dashboard'),{'user':user,'house':hse})
    
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
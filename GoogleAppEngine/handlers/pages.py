# -*- coding: utf-8 -*-
import webapp2
from webapp2_extras import jinja2
from google.appengine.ext import ndb
import json
import logging
import session
from models import house

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
            
        template_values['page_base'] = self.request.route.name
        
        self.response.write(self.jinja2.render_template(
            template_name, **template_values))

    def render_string(self, template_string, template_values={}):
        self.response.write(self.jinja2.environment.from_string(
            template_string).render(**template_values))

    def json_response(self, json):
        self.response.headers.add_header('content-type', 'application/json', charset='utf-8')
        self.response.out.write(json)
        
#    def handle_exception(self,exception,debug_mode):
 #       
  #      logging.error('Ooops {0} {1}'.format(exception,debug_mode))
   #     return
        

 

class PageHandler(Jinja2Handler):
    
    @session.manage_user    
    def main(self):
        
        session = self.request.session
        
        if not session.user:
            self.render_template('not_logged_in.html')
            return
          
        hse_id = self.request.session.user._get_house_id()
        
        if hse_id is None:
            #new user, hasn't setup a house yet -> setup wizzard
            self.render_template('house_wizzard.html',{'user':session.user,'house':{'name':'Your House'}})
            return
        
        hse = house.House._get_house_by_id(hse_id)

        self.render_template('{0}.html'.format(self.request.route.name if self.request.route.name != '' else 'dashboard'),
                             {'user':session.user,'house':hse})
    
 




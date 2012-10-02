import webapp2
from google.appengine.ext import ndb
import json
import logging
from models import house, authprovider
from handlers.jinja import Jinja2Handler

class PageHandler(Jinja2Handler):
    
    @house.manage_house
    def main(self):
        
        session = self.request.session
        
        if not session.user:
            self.render_template('not_logged_in.html')
            return
        
        if not session.user.verified_email:
            self.render_template('actions/verify_email.html',{'user':session.user})
            return
        
          
        hse_id = self.request.session.user._get_house_id()
        
        if hse_id is None:
            #new user, hasn't setup a house yet -> setup wizzard
            self.render_template('house_wizzard.html',{'user':session.user,'house':{'name':'Your House'}})
            return
        
        hse = house.House._get_house_by_id(hse_id)

        self.render_template('{0}.html'.format(self.request.route.name if self.request.route.name != '' else 'dashboard'),
                             {'user':session.user,'house':hse})
    
 






from google.appengine.ext import ndb
import json
import logging
import session
from models import house, authprovider
from handlers.jinja import Jinja2Handler

class Task(Jinja2Handler):
    
    @session.manage_user    
    def post(self,action):
	
	
	logging.info(self.request.POST)
	
	return
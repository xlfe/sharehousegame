

from google.appengine.ext import ndb
import json
import logging
import session
import shg_utils
from models import house, authprovider
from handlers.jinja import Jinja2Handler

class RepeatedTask(ndb.Model):
    
    _default_indexed= False
    
    _definitions = {
		'repeat_by'  : [ 'dom', 'dow']
	,	'repeat_on'  : ['sunday', 'monday','tuesday','wednesday','thursday','friday','saturday' ]
	,	'repeat_freq':range(1,31)
	,	'repeat_period': ['Daily','Weekly','Monthly','Yearly']
	,	'reminders'	:  [
				'That afternoon (about 2pm)',
				'Lunch time (about 12pm)',
				'That morning (about 10am)',
				'The night before (about 7pm)',
				'The evening before (about 5pm)',
				'The afternoon before (about 3pm)',
				'Anytime the day before',
				'2 days before',
				'3 days before',
				'5 days before',
				'7 days before',
				'10 days before',
				'14 days before'
			    ]
    }
 
    name = ndb.StringProperty(required=True)
    start_date = ndb.StringProperty(required=True)
    desc = ndb.TextProperty(required=True)
    timezone = ndb.StringProperty(required=True)
    repeat = ndb.BooleanProperty(required=True)
    repeat_period = ndb.StringProperty(required = True)
    repeat_freq = ndb.IntegerProperty(required = True)
    repeat_by = ndb.StringProperty()
    repeat_on = ndb.StringProperty(repeated=True)
    group_task = ndb.BooleanProperty(default=False)
    no_reminder = ndb.BooleanProperty(default=False)
    reminders = ndb.StringProperty(repeated=True)
    
    house_id = ndb.IntegerProperty(required=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    
    @classmethod
    def create(cls, dict):
	rt = cls()
	
	#encapsulate repeated properties
	dict = shg_utils.encapsulate_dict(dict,RepeatedTask())
	
	for k,v in cls._definitions.iteritems():
	    if type(dict[k]) == type([]):
		for i in dict[k]:
		    assert i in v, "Incorrect value : {0}".format(i)
	    else:
		assert dict[k] in v, "Incorrect value : {0}".format(dict[k])
	    

	rt.populate(**dict)
	
	rt.put()
	
	return 
	
    

class Task(Jinja2Handler):
    
    

    
    
#  UnicodeMultiDict([(u'timezone', u'Australia/Sydney'), (u'task_name', u'Rent'), (u'task_date', u'Tuesday 09 October, 2012'),
#  (u'repeat', u'as_specified'), (u'repeat-period', u'Monthly'), (u'repeat-freq', u'1'), (u'repeat-by', u'dom'),
#  (u'reminder', u'5 days before'), (u'reminder', u'2 days before'), (u'task_desc', u'Time to pay rent guys!')])
    
    
    
    @session.manage_user    
    def post(self,action):
	
	
	if (action == 'create'):
	    
	    dict = self.request.POST
	    dict['created_by'] = self.request.session.user._get_id()
	    dict['house_id'] = self.request.session.user.house_id
	    
	    rt = RepeatedTask().create(dict)
	
	
	return
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
    ,       'repeat_on'  : ['Sunday', 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday' ]
    ,       'repeat_freq':range(1,31)
    ,       'repeat_period': ['Daily','Weekly','Monthly','Yearly']
    ,       'reminders'     :  [
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
    
    house_id = ndb.IntegerProperty(required=True, indexed=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)

    @classmethod
    def create(cls, dict):
	
	rt = cls()

	logging.info(dict)
	
	#encapsulate repeated properties
	dict = shg_utils.encapsulate_dict(dict,RepeatedTask())
	
	for k,v in cls._definitions.iteritems():
	    if k in dict:
		if type(dict[k]) == type([]):
		    for i in dict[k]:
			assert i in v, "Incorrect value : {0}".format(i)
		else:
		    assert dict[k] in v, "Incorrect value : {0}".format(dict[k])
		
	rt.populate(**dict)
	rt.put()
	
	return rt
    
    
    
    def describe_repeat(self):
	
	if not self.repeat:
	    return "-"
	
	extra = ''
	
	perd_desc = { 'Daily' : ['daily','days']
	    ,	'Weekly'	:['weekly','weeks']
	    ,	'Monthly'	:['monthly','months']
	    ,	'Yearly'	:['yearly','years']}
	
	if self.repeat_period == "Weekly":
	    
	    if len(self.repeat_on) > 0:
		extra = ' on ' + ' and '.join(self.repeat_on)
		
	elif self.repeat_period == "Monthly":
	    
	    day =  self.start_date.split(' ')[0]
	    date = int(self.start_date.split(' ')[1])
	    
	    if date > 28:
		which = "last"
	    elif date > 21:
		which = "fourth"
	    elif date > 14:
		which = "third"
	    elif date > 7:
		which = "second"
	    else:
		which = "first"
	    
	    if self.repeat_by == "dow":
		
		extra = ' on the {0} {1}'.format(which,day)
		
	    elif self.repeat_by == "dom":
		
		extra = ' on day {0}'.format(date)
	
	if self.repeat_freq == 1:
	    desc = 'Repeats {0}{1}'.format(perd_desc.get(self.repeat_period)[0],extra)
	    short = self.repeat_period
	else:
	    desc = 'Repeats every {0} {1} {2}'.format(self.repeat_freq,perd_desc.get(self.repeat_period)[1],extra )
	    short = 'Every {0} {1}'.format(self.repeat_freq,perd_desc.get(self.repeat_period)[1])
	
	return '<span class="tt-right" title="{0}"> {1}</span>'.format(desc,short)
    
	
    
	
    @staticmethod
    def get_tasks_by_house_id(house_id):
	return RepeatedTask().query(RepeatedTask.house_id == house_id).fetch()

class Task(Jinja2Handler):

    @session.manage_user
    def post(self,action):

	if action == 'create':
		
	    dict = self.request.POST
	    dict['created_by'] = self.request.session.user._get_id()
	    dict['house_id'] = self.request.session.user.house_id
	    
	    rt = RepeatedTask().create(dict)
	    
	    self.json_response(json.dumps({'success':'Task created','redirect':'/tasks'}))
	    
	return
		
    @session.manage_user
    def list(self):
	
	tasks = RepeatedTask.get_tasks_by_house_id(self.request.session.user.house_id)
	self.render_template('tasks.html',{'tasks':tasks})
	return

    @session.manage_user
    def get(self,action):
	    
	if action == 'edit':
		
	    pass
	
	elif action == 'create':
		
	    self.render_template('repeating_task.html')
	
	
	    
	    
	return

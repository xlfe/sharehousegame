from google.appengine.ext import ndb
import json
import logging
import session
import shg_utils
from models import house, authprovider
from handlers.jinja import Jinja2Handler
from pytz.gae import pytz
from datetime import datetime, timedelta, time
from time import sleep
import calendar

def add_months(sourcedate,months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month / 12
    month = month % 12 + 1
    day = min(sourcedate.day,calendar.monthrange(year,month)[1])
    return datetime(year,month,day,sourcedate.hour,sourcedate.minute,sourcedate.second)
    
def add_years(sourcedate,years):
    month = sourcedate.month 
    year = sourcedate.year + years
    month = sourcedate.month
    day = min(sourcedate.day,calendar.monthrange(year,month)[1])
    return datetime(year,month,day,sourcedate.hour,sourcedate.minute,sourcedate.second)

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
    start_date = ndb.DateProperty(required=True)
    desc = ndb.TextProperty(required=True)
    timezone = ndb.StringProperty(required=True)
    repeat = ndb.BooleanProperty(required=True)
    repeat_period = ndb.StringProperty(required = True)
    repeat_freq = ndb.IntegerProperty(required = True)
    repeat_by = ndb.StringProperty()
    repeat_on = ndb.StringProperty(repeated=True)
    repeats_limited = ndb.BooleanProperty(default=False)
    repeats_times = ndb.IntegerProperty()
    group_task = ndb.BooleanProperty(default=False)
    no_reminder = ndb.BooleanProperty(default=False)
    reminders = ndb.StringProperty(repeated=True)
    points = ndb.IntegerProperty(required=True)
    
    house_id = ndb.IntegerProperty(required=True, indexed=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)

    @classmethod
    def create(cls, dict):
        
        rt = cls()
        
        #encapsulate repeated properties
        dict = shg_utils.encapsulate_dict(dict,RepeatedTask())
        
        for k,v in cls._definitions.iteritems():
            if k in dict:
                if type(dict[k]) == type([]):
                    for i in dict[k]:
                        assert i in v, "Incorrect value : {0}".format(i)
                else:
                    assert dict[k] in v, "Incorrect value : {0}".format(dict[k])
        
        if 'reminders' in dict:
            assert len(dict['reminders']) <= 10, 'Sorry, a maximum of 10 reminders'
            #make sure we only have one of each...
            dict['reminders'] = set(dict['reminders'])
            
        assert dict['start_date'].year >= 2012,'Start date must be after 2012'
        
        try:
            rt.populate(**dict)
            rt.put()
        except:
            logging.error(dict)
            raise
        
        return rt
    
    
    
    def describe_repeat(self):
        
        if not self.repeat:
            return "-"
        
        extra = ''
        
        perd_desc = {   'Daily'     : ['daily'  ,'days'  ]
                ,	'Weekly'    : ['weekly' ,'weeks' ]
                ,	'Monthly'   : ['monthly','months']
                ,	'Yearly'    : ['yearly' ,'years' ]
                }
        
        if self.repeat_period == "Weekly" and len(self.repeat_on) > 0:
                extra = ' on ' + ' and '.join(self.repeat_on)
                
        elif self.repeat_period == "Monthly":
            
            day =  self.start_date.strftime('%A')
            date = self.start_date.day
            
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
    def reminder_to_time_delta(reminder):
        """takes a description of the reminder and returns the time delta
        assuming a standard 12pm on the day"""
        
        intervals = {   'That afternoon (about 2pm)'     : timedelta(hours=2),
                        'Lunch time (about 12pm)'        : timedelta(hours=0),
                        'That morning (about 10am)'      : timedelta(hours=-2),
                        'The night before (about 7pm)'   : timedelta(days=-1,hours=+7),
                        'The evening before (about 5pm)' : timedelta(days=-1,hours=+5),
                        'The afternoon before (about 3pm)':timedelta(days=-1,hours=+3),
                        'Anytime the day before'          :timedelta(days=-1),
                        '2 days before'                   :timedelta(days=-2),
                        '3 days before'                   :timedelta(days=-3),
                        '5 days before'                   :timedelta(days=-5),
                        '7 days before'                   :timedelta(days=-7),
                        '10 days before'                  :timedelta(days=-10),
                        '14 days before'                  :timedelta(days=-14),
                    }
        
        return intervals[reminder]
    @staticmethod
    def weekdays_to_int(weekday):
        """uses ISO weekday assignments"""
        
        wdn = {
            'Monday':1,
            'Tuesday':2,
            'Wednesday':3,
            'Thursday':4,
            'Friday':5,
            'Saturday':6,
            'Sunday':7
        }
        
        return wdn[weekday]
        
    def next_event_utc(self):
        """the next event trigger"""
        
        now = pytz.UTC.localize(datetime.now())
        
        for event in self.iter_instances(None):
            if event > now:
                return event
    def next_reminder_utc(self):
        
        now = pytz.UTC.localize(datetime.now())
        ne = self.next_event_utc()
        if ne:
            for reminder in self.iter_reminders(ne,None):
                if reminder > now:
                    return reminder
        
    def localize(self,dt):
        fmt = '%Y-%m-%d'
        
        if dt:
            local = pytz.timezone(self.timezone)
            return local.normalize(dt.astimezone(local)).strftime(fmt)
        else:
            return '-'
        
    
    def pretty(self,dt):
        if dt:
            return shg_utils.prettydate(dt)
        else:
            return '-'
            
    def iter_reminders(self,dt_event,max_reminders=10):
        """ returns UTC datetime objects for reminders for an event occuring on dt_event"""
        
        sorted_reminders = sorted(self.reminder_to_time_delta(r) for r in self.reminders)
        n= 0
        
        for r in sorted_reminders:
            n+=1
            yield  dt_event + r 
        
            if max_reminders and n > max_reminders:
                return

    
    def next_wd(self,weekdays,last_event):
        eow = True
        for d in weekdays:
            if d > last_event.isoweekday():
                last_event += timedelta(days=d-last_event.isoweekday())
                eow = False
                break
        if eow:
            #reset to the begining of the week
            last_event += timedelta(days=weekdays[0] -last_event.isoweekday())
            
            last_event += timedelta(weeks=self.repeat_freq)
        
        return last_event
        
    
    def iter_instances(self,max_events=10):
        """ returns a list of UTC datetime objects for a repeating event"""
        
        local_tz = pytz.timezone(self.timezone)
        last_event = datetime.combine( self.start_date , time(12,0,0) )
        
        if not self.repeat:
            #doesn't repeat, so return just the event
            yield local_tz.localize( last_event )
            return
        
        if len(self.repeat_on) > 0:
            wd = sorted([self.weekdays_to_int(d) for  d in self.repeat_on])
            if last_event.isoweekday() not in wd:
                last_event = self.next_wd(wd,last_event)
            
            original_dow = None
        else:
            wd = None
            original_dow = {'day':last_event.day,'weekday':last_event.isoweekday()}
        
        i=0
        while True:
            
            if (max_events and i >= max_events) or (self.repeats_limited and i >= self.repeats_times):
                return
            
            i+=1
            yield local_tz.localize( last_event )
            
            if self.repeat_period == "Daily":
                
                last_event += timedelta(days=self.repeat_freq)
                
            elif self.repeat_period == "Weekly":
                if wd:
                    last_event = self.next_wd(wd,last_event)
                else:
                    last_event += timedelta(weeks=self.repeat_freq)
                
            elif self.repeat_period == "Monthly":
                
                #closest day possible in the right month
                last_event = add_months( datetime.combine(self.start_date,time(12,0,0)) ,self.repeat_freq * i)

                if self.repeat_by == "dow":
                    assert(original_dow), 'Something went wrong'
                    
                    #how many days forward to get to the same day of week
                    dd_b = (last_event.isoweekday() - original_dow['weekday']) % 7
                    dd_f = 7- dd_b
                    
                    if original_dow['day'] > 28:
                        max_day = calendar.monthrange(last_event.year,last_event.month)[1]
                        min_day = 0
                    elif original_dow['day'] > 21:
                        max_day = 28
                        min_day = 22
                    elif original_dow['day'] > 14:
                        max_day = 21
                        min_day = 15
                    elif original_dow['day'] > 7:
                        max_day = 14
                        min_day = 8
                    else:
                        max_day = 7
                        min_day = 1
                    
                    if last_event.day + dd_f > max_day:
                        #logging.info('{3} le day {0} dow {1} going backwards {2} - f{4} b{5}'.format(last_event.day,last_event.isoweekday(),-dd_b,last_event.month,dd_f,dd_b))
                        last_event += timedelta(days= -dd_b)
                    else:
                        #logging.info('{3} le day {0} dow {1} going forwards {2} - f{4} b{5}'.format(last_event.day,last_event.isoweekday(),dd_f,last_event.month,dd_f,dd_b))
                        last_event += timedelta(days= dd_f)
                
            elif self.repeat_period == "Yearly":
                
                last_event = add_years(datetime.combine(self.start_date,time(12,0,0)),i)
                    
        
        
        
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
            
            hse = house.House.get_by_id(self.request.session.user.house_id)
            hse.add_house_event(self.request.session.user._get_id(),'created a task named {0}'.format(dict['name']),0)
                
            
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
        elif action == 'delete':
            
            id = self.request.GET['id']
            
            task = ndb.Key('RepeatedTask',int(id)).get()
            
            if task:
                
                if self.request.session.user.house_id == task.house_id:
                    hse = house.House.get_by_id(self.request.session.user.house_id)
                    hse.add_house_event(self.request.session.user._get_id(),'deleted the task called {0}'.format(task.name),0)
                
                    task.key.delete(use_datastore=False)
                    task.key.delete()
                
                
                
            sleep(1)
            self.redirect('/tasks?deleted')
        
        
            
            
        return

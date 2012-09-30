from google.appengine.ext import ndb
import json
import logging
import session
import shg_utils
import re
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

class StandingTask(ndb.Model):
    _default_indexed=False
    
    name = ndb.StringProperty(required=True)
    desc = ndb.TextProperty(required=True)
    points = ndb.IntegerProperty(required=True)
    
    house_id = ndb.IntegerProperty(required=True, indexed=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)

class TaskCompletion(ndb.Model):
    """Stores a record of a housemate completing a task"""
    
    user_id = ndb.IntegerProperty(required=True)
    when = ndb.DateTimeProperty(auto_now_add=True)
    
class TaskInteractions(ndb.Model):
    """Stores a record of reminders / other emails sent"""
    
    user_id = ndb.IntegerProperty(required=True)
    when = ndb.DateTimeProperty(auto_now_add=True)

class TaskInstance(ndb.Model):
    """Basically a pointer to the Owner Task to be called at a regular interval using cron"""
    _default_indexed = False
    
    owner = ndb.KeyProperty(required=True,indexed=True)
    next_action_reqd = ndb.DateTimeProperty(required=True,indexed=True)
    
    completions = ndb.StructuredProperty(TaskCompletion,repeated=True)
    interactions = ndb.StructuredProperty(TaskInteractions,repeated=True)
    

class RepeatedTask(ndb.Model):
    
    _default_indexed= False
    
    definitions = {
        'repeat_by'  : [ 'dom', 'dow']
    ,       'repeat_on'  : ['Sunday', 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday' ]
    ,       'repeat_freq':range(1,31)
    ,       'repeat_period': ['Daily','Weekly','Monthly','Yearly']
    ,       'wd_names' : {
                        'Monday':   1,
                        'Tuesday':  2,
                        'Wednesday':3,
                        'Thursday': 4,
                        'Friday':   5,
                        'Saturday': 6,
                        'Sunday':   7
            }
    }

    name = ndb.StringProperty(required=True)
    start_date = ndb.DateProperty(required=True)
    desc = ndb.TextProperty(required=True)
    repeat = ndb.BooleanProperty(required=True)
    repeat_period = ndb.StringProperty(required = True)
    repeat_freq = ndb.IntegerProperty(required = True)
    repeat_by = ndb.StringProperty()
    repeat_on = ndb.StringProperty(repeated=True)
    repeats_limited = ndb.BooleanProperty(default=False)
    repeats_times = ndb.IntegerProperty()
    shared_task = ndb.BooleanProperty(default=False)
    shared_number = ndb.IntegerProperty()
    shared_all_reqd = ndb.BooleanProperty()
    no_reminder = ndb.BooleanProperty(default=False)
    reminders = ndb.StringProperty(repeated=True)
    doesnt_expire = ndb.BooleanProperty()
    points = ndb.IntegerProperty(required=True)
    
    house_id = ndb.IntegerProperty(required=True, indexed=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    
    disabled = ndb.BooleanProperty(default=False)
    
    event_expiry_tm = time(23,59,59)

    @classmethod
    @ndb.transactional(xg=True)
    def create(cls, dict):
        
        rt = cls()
        
        #encapsulate repeated properties
        dict = shg_utils.encapsulate_dict(dict,RepeatedTask())
        
        for k,v in cls.definitions.iteritems():
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
            
            for r in dict['reminders']:
                assert cls.calc_reminder_delta(r) != None,'Unknown reminder interval {0}'.format(r) 
            
        assert dict['start_date'].year >= 2012,'Start date must be after 2012'
        
        try:
            rt.populate(**dict)
            rt.put()
        except:
            logging.error(dict)
            raise
        
        try:
            next_reminder = rt.next_reminder_utc()
            
            next_event = rt.next_event_utc()
            if next_reminder and next_event:    
                nar = min(next_event,next_reminder)
            else:
                nar = next_event
            if next_event:
                logging.info(nar)
                ti = TaskInstance(owner=rt.key,next_action_reqd=nar.replace(tzinfo=None))
                ti.put()
        except:
            raise
            
        return rt
    
    @staticmethod
    def calc_reminder_delta(desc):
        """Turns '9am the day before' into a timdelta"""
        
        #0 - hours 1-minuts 2-am/pm
        tm = re.match('([1][0-2]|[0]?[0-9])(?::|.)?([0-5][0-9])?[\s]*(am|pm)',desc,flags=re.I)
        
        if not tm:
            return None
        
        assert tm.group(1) and tm.group(3), 'Unknown time from {0}'.format(desc)
        
        hours = int(tm.group(1))
        
        if tm.group(3).lower() == "pm":
            hours += 12
        
        minutes = 60 - int(tm.group(2)) if tm.group(2) else 0
            
        days = desc[len(tm.group(0))+1:]
        
        if days == "same day":
            days = 0
        elif days == "the day before":
            days = 1
        else:
            days = int(days.split(' ')[0])
        
        assert hours >=0 and minutes >= 0 and days >=0,'Unknown time from {0}'.format(desc)
        assert hours <= 24 and minutes <= 60 and days <=14, 'Unknown time from {0}'.format(desc)
        
        return timedelta(days=-days,hours=(hours-23),minutes=-minutes)
        
        #logging.info("'{0}' => {1} - {2} days before".format(desc,td,days))
            
    
    
    @property
    def shared_desc(self):
        
        if not self.shared_task:
            return None
        
        if self.shared_all_reqd:
            return 'All'
        else:
            return str(self.shared_number)
    
    @property
    def timezone(self):
        hse = house.House.get_by_id(self.house_id)
        return hse.timezone
    
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
    
    def weekdays_to_int(self,weekday):
        """uses ISO weekday assignments"""
        return self.definitions['wd_names'][weekday]
    
    def next_event_utc(self):
        """the next event trigger"""
        
        now = pytz.UTC.localize(datetime.now())
        
        
        for event in self.iter_instances(None):
            if event > now:
                return pytz.UTC.normalize(event.astimezone(pytz.UTC))
                #return event
        
    def next_reminder_utc(self):
        
        now = pytz.UTC.localize(datetime.now())
        ne = self.next_event_utc()
        if ne:
            for reminder in self.iter_reminders(ne,None):
                if reminder > now:
                    return reminder
        
    def localize(self,dt):
        """Converts the UTC dt into the local timezone """
        fmt = '%Y-%m-%d %H:%M %Z'
        
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
        """ returns datetime objects for reminders for an event occuring on dt_event"""
        
        sorted_reminders = sorted(self.calc_reminder_delta(r) for r in self.reminders)
        n= 0
        
        for r in sorted_reminders:
            n+=1
            yield  dt_event + r + timedelta(minutes=1)
        
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
        """ returns a list of localized datetime objects for a repeating event"""
        
        local_tz = pytz.timezone(self.timezone)
        last_event = datetime.combine( self.start_date , self.event_expiry_tm)
        
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
                last_event = add_months( datetime.combine(self.start_date, self.event_expiry_tm) ,self.repeat_freq * i)

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
                
                last_event = add_years(datetime.combine(self.start_date,self.event_expiry_tm),i)
                    
        
    @staticmethod
    def get_tasks_by_house_id(house_id):
        return RepeatedTask().query(RepeatedTask.house_id == house_id,RepeatedTask.disabled == False).fetch()
    
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
                    task.key.delete()
                
                
                
            sleep(1)
            self.redirect('/tasks?deleted')
            
        return
    
    def send_reminders(self):
        """Cron job that is run every 15 minutes"""
        
        
        return

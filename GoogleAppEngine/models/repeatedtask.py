from google.appengine.ext import ndb
import json
import logging
import shg_utils
import re
from models import house, authprovider,user
from models.email import EmailHash
from handlers.jinja import Jinja2Handler
from pytz.gae import pytz
from datetime import datetime, timedelta, time
from time import sleep
import calendar
import os

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

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

    name            = ndb.StringProperty(required=True)
    due_date        = ndb.DateProperty(required=True)
    desc            = ndb.TextProperty(required=True)
    repeat          = ndb.BooleanProperty(required=True)
    repeat_period   = ndb.StringProperty(required = True)
    repeat_freq     = ndb.IntegerProperty(required = True)
    repeat_by       = ndb.StringProperty()
    repeat_on       = ndb.StringProperty(repeated=True)
    repeats_limited = ndb.BooleanProperty(default=False)
    repeats_times   = ndb.IntegerProperty()
    shared_task     = ndb.BooleanProperty(default=False)
    shared_number   = ndb.IntegerProperty()
    shared_all_reqd = ndb.BooleanProperty()
    no_reminder     = ndb.BooleanProperty(default=False)
    reminders       = ndb.StringProperty(repeated=True)
    doesnt_expire   = ndb.BooleanProperty()
    points          = ndb.IntegerProperty(required=True)

    house_id        = ndb.IntegerProperty(required=True, indexed=True)
    created_by      = ndb.IntegerProperty(required=True)
    created         = ndb.DateTimeProperty(auto_now_add=True)

    disabled        = ndb.BooleanProperty(default=False)

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
            assert len(dict['reminders']) <= 4, 'Sorry, a maximum of 10 reminders'
            #make sure we only have one of each...

            dict['reminders'] = set(dict['reminders'])

            for r in dict['reminders']:
                assert cls.calc_reminder_delta(r) != None,'Unknown reminder interval {0}'.format(r)

        assert dict['due_date'].year >= 2012,'Due date must be after 2012'

        try:
            rt.populate(**dict)
            rt.put()
        except:
            logging.error(rt)
            logging.error(dict)
            raise

        #Populates TaskEvents that need to occur...
        rt.setup_events()

        return rt

    def housemates_completed(self,task_instance):
        """returns a list of housemates who have completed a particular task instance"""

        task_completions = TaskCompletion.query(ancestor=self.key).filter(TaskCompletion.task_instance == task_instance).fetch()

        housemates = []

        for tc in task_completions:
            housemates.append(tc.user_id)

        return housemates

    def complete_task(self,task_instance,user_id):

        assert user_id in self.house.users,"User {0} is not found in house {1} for task '{2}'".format(user_id,self.house_id,self.name)
        assert user_id not in self.housemates_completed(task_instance),'Housemate {0} already completed task {1}'.format(user_id,self.name)

        tc = TaskCompletion(parent=self.key,user_id=user_id,task_instance=task_instance)
        tc.put()

        return True

    def setup_events(self):

        next_expiry = self.next_expiry_utc()
        next_expiry = next_expiry.replace(tzinfo=None) if next_expiry else None

        if next_expiry:
            ti = TaskInstance(parent=self.key,action_reqd=next_expiry)
        else:
            ti = TaskInstance(parent=self.key,action_reqd=None)

        ti.put()

        self.add_next_reminder(ti.key)

    def add_next_reminder(self,task_instance,after=None):

        next_reminder = self.next_reminder_utc(after)
        next_reminder = next_reminder.replace(tzinfo=None) if next_reminder else None

        if next_reminder:

            tr = TaskReminder(owner=task_instance,action_reqd=next_reminder)
            tr.put()


    @staticmethod
    def calc_reminder_delta(desc):
        """Turns '9am the day before' into a timdelta"""

        #0 - hours 1-minutes 2-am/pm
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
        return self.house.timezone

    @property
    def housemates(self):
        return self.house.users

    @property
    def house(self):
        if not self._house:
            self._house = house.House.get_by_id(self.house_id)
            return self._house

    def __init__(self):
        self._house = None

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

            day =  self.due_date.strftime('%A')
            date = self.due_date.day

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

    def next_expiry_utc(self,now=None):
        """the next time the task expires based on:
            -the due date
            -the repeat options
            -the expiry options

            -optionally takes an argument 'after' which finds the next expiry after
                a certian date (default is now())
        """
        if now is None:
            now = pytz.UTC.localize(datetime.now())

        if self.doesnt_expire:
            #must expire half way between the current due date and the next one...

            now_offset = now

            last_due, next_due = None, None

            #iter_due_dates_utc starts at the oldest due and increments forwards in time
            for dd in self.iter_due_dates_utc(None):
                if dd > now_offset:
                    return dd

                if dd < now_offset and not next_due:
                    last_due = dd

                if dd > now_offset:
                    next_due = dd

                if last_due and next_due:

                    diff = timedelta(seconds = (next_due - last_due).total_seconds()/2)

                    if last_due + diff > now:
                        return last_due + diff
                    else:
                        now_offset = now_offset + diff + diff
                        last_due, next_due = None
        else:
            #if a task expires, its expiry date is the next due date after now

            for dd in self.iter_due_dates_utc(None):
                if dd > now:
                    return dd


    def next_due_utc(self,after=None):
        """the next datetime a task is due, after a certian datetime (defaults to now)"""

        if not after:
            after = pytz.UTC.localize(datetime.now())

        for event in self.iter_due_dates_utc(None):
            if event > after:
                return event


    def next_reminder_utc(self,after=None):
        """next reminder for a task
            -reminders are based on task due date, not expiry date"""

        if not after:
            after = pytz.UTC.localize(datetime.now())

        next_event = self.next_due_utc(after)

        if next_event:
            for reminder in self.iter_reminders(next_event,None):
                if reminder > after:
                    return reminder

    def iter_reminders(self,dt_event,max_reminders=21):
        """ returns datetime objects for reminders for an event occuring on dt_event"""

        sorted_reminders = sorted([self.calc_reminder_delta(r) for r in self.reminders])#,key=lambda k: k.total_seconds())

        n= 0

        for r in sorted_reminders:
            n+=1
            yield  dt_event + r + timedelta(seconds=1)

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

    def iter_due_dates_utc(self,max_events=10):
        """returns a list of UTC datetime objects for a repeating task"""

        utc = pytz.UTC

        for e in self.iter_due_dates(max_events):
            yield utc.normalize(e.astimezone(utc))

    def iter_due_dates(self,max_events=10):
        """ returns a list of localized datetime due dates for a repeating task"""

        local_tz = pytz.timezone(self.timezone)
        last_event = datetime.combine( self.due_date , self.event_expiry_tm)

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
                last_event = add_months( datetime.combine(self.due_date, self.event_expiry_tm) ,self.repeat_freq * i)

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

                last_event = add_years(datetime.combine(self.due_date,self.event_expiry_tm),i)


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



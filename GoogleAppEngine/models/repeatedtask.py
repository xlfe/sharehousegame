from google.appengine.ext import ndb
import json
import logging
import shg_utils
import re
from models import house, authprovider,user
import models
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
        'repeat_by'  : [ 'dom', 'dow' ]
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
#       event_expiry_tm = time(16,59,59)


    @property
    def due_in(self):
        nd = self.next_due_utc()
        return '{1} ({0})'.format(self.pretty(nd),self.localize(nd))

    @ndb.transactional(xg=True)
    def update(self,dict):
        #encapsulate repeated properties
        dict = shg_utils.encapsulate_dict(dict,RepeatedTask())

        for k,v in self.definitions.iteritems():
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
                assert self.calc_reminder_delta(r) != None,'Unknown reminder interval {0}'.format(r)

        assert dict['due_date'].year >= 2012,'Due date must be after 2012'

        self.populate(**dict)
        self.put()

        return True

    @classmethod
    @ndb.transactional(xg=True)
    def create(cls, dict):

        rt = cls()

        rt.update(dict)
        #Populates TaskEvents that need to occur...
        rt.setup_events()

        return rt

    def housemates_completed(self,task_instance):
        """returns a list of housemates who have completed a particular task instance"""

        task_completions = models.tasks.TaskCompletion.query(ancestor=self.key).filter(models.tasks.TaskCompletion.task_instance == task_instance).fetch()

        housemates = []

        for tc in task_completions:
            housemates.append(tc.user_id)

        return housemates

    def complete_task(self,task_instance,user_id):

        assert user_id in self.house.users,"User {0} is not found in house {1} for task '{2}'".format(user_id,self.house_id,self.name)
        assert user_id not in self.housemates_completed(task_instance),'Housemate {0} already completed task {1}'.format(user_id,self.name)

        tc = models.tasks.TaskCompletion(parent=self.key,user_id=user_id,task_instance=task_instance)
        tc.put()

        return True

    @ndb.transactional(xg=True)
    def setup_events(self):

        next_expiry = self.next_expiry_utc()
        logging.info('setup_events - next_expiry {0}'.format(next_expiry))
        next_expiry = next_expiry.replace(tzinfo=None) if next_expiry else None
        logging.info('setup_events - next_expiry no zt {0}'.format(next_expiry))

        if next_expiry:
            ti = models.tasks.TaskInstance(parent=self.key,action_reqd=next_expiry)
        else:
            ti = models.tasks.TaskInstance(parent=self.key,action_reqd=None)

        ti.put()
        self.add_next_reminder(ti.key)

    def add_next_reminder(self,task_instance,after=None):

        next_reminder = self.next_reminder_utc(after)
        logging.info('add_next_reminder next_reminder {0}'.format(next_reminder))
        next_reminder = next_reminder.replace(tzinfo=None) if next_reminder else None
        logging.info('add_next_reminder next_reminder no tz {0}'.format(next_reminder))

        if next_reminder:

            #Only add a reminder if it occurs before the TaskInstance expires...
            if not task_instance.get().expired(next_reminder):
                logging.info('reminder occurs before task instance, adding...'.format(next_reminder))
                tr = models.tasks.TaskReminder(owner_instance=task_instance,action_reqd=next_reminder)
                tr.put()
            else:
                logging.info('task instance would have expired by {0} - not adding a reminder {1}'.format(task_instance.get().action_reqd,next_reminder))


    def calc_reminder_delta(self,desc,dt_event=None):
        """Turns '9am the day before' into a timdelta"""

        #0 - hours 1-minutes 2-am/pm
        tm = re.match('([1][0-2]|[0]?[0-9])(?::|.)?([0-5][0-9])?[\s]*(am|pm)',desc,flags=re.I)

        if not tm:
            return None

        assert tm.group(1) and tm.group(3), 'Unknown time from {0}'.format(desc)

        hours = int(tm.group(1))

        if tm.group(3).lower() == "pm":
            hours += 12

        minutes = int(tm.group(2)) if tm.group(2) else 0

        days = desc[len(tm.group(0))+1:]

        if days == "same day":
            days = 0
        elif days == "the day before":
            days = 1
        else:
            days = int(days.split(' ')[0])

        assert hours >=0 and minutes >= 0 and days >=0,'Unknown time from {0}'.format(desc)
        assert hours <= 24 and minutes <= 60 and days <=14, 'Unknown time from {0}'.format(desc)
        if not dt_event:
            return True

        td = (dt_event + timedelta(days=-days)).replace(hour=hours,minute=minutes,second=0) -\
            dt_event.replace(hour=self.event_expiry_tm.hour,minute=self.event_expiry_tm.minute)

#        td = (self.event_expiry_tm - time(hour=hours,minute=minutes)) + timedelta(days=-days)



#        td = timedelta(days=-days,hours=(hours-24),minutes=-minutes)
        logging.info('{0} -> {1}'.format(desc,td))
        return td

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
        if not '_house' in self.__dict__:
            self._house = house.House.get_by_id(self.house_id)
        return self._house

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

    @property
    def now_utc(self):
        return pytz.UTC.localize(datetime.now()) + timedelta(seconds=10)

    def next_expiry_utc(self,now=None):
        """the next time the task expires based on:
            -the due date
            -the repeat options
            -the expiry options

            -optionally takes an argument 'after' which finds the next expiry after
                a certian date (default is now())
        """
        if now is None:
            now = self.now_utc

        if self.doesnt_expire:
            logging.info("task doesn't expire - setting expiry half way between the current due date and the next one...")

            now_offset = now

            #get the next two due dates
            next_due = self.next_due_utc(after = now)
            next_due_1 = self.next_due_utc(after=next_due)

            diff = timedelta(seconds = (next_due_1 - next_due).total_seconds()/2)

            logging.info('{0} + {1}'.format(next_due,diff))
            return next_due + diff
        else:
            logging.info("Task expires, expiry is set as due date")
            #if a task expires, its expiry date is the next due date after now

            for dd in self.iter_due_dates_utc(None):
                if dd > now:
                    logging.info('dd = {0}'.format(dd))
                    return dd


    def next_due_utc(self,after=None):
        """the next datetime a task is due, after a certian datetime (defaults to now)"""

        if not after:
            after = self.now_utc

        for event in self.iter_due_dates_utc(None):
            if event > after:
                logging.info('next_due_utc event {0} > after {1} returning event'.format(event,after))
                return event


    def next_reminder_utc(self,after=None):
        """next reminder for a task
            -reminders are based on task due date, not expiry date"""

        if not after:
            after = self.now_utc

        next_event = self.next_due_utc(after)

        if next_event:
            for reminder in self.iter_reminders(next_event,None):
                if reminder > after:
                    logging.info('{0} > {1} returning {0}'.format(reminder,after))
                    return reminder

    def iter_reminders(self,dt_event,max_reminders=21):
        """ returns datetime objects for reminders for an event occuring on dt_event"""

        sorted_reminders = sorted([self.calc_reminder_delta(r,dt_event) for r in self.reminders])#,key=lambda k: k.total_seconds())

        n= 0

        for r in sorted_reminders:
            n+=1
            logging.info('Yeilding {0} + {1}'.format(dt_event,r))
            yield  dt_event + r #+ timedelta(seconds=1)

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
            idd= utc.normalize(e.astimezone(utc))
            logging.info('iter_due_dates_utc {0}'.format(idd))
            yield idd

    def iter_due_dates(self,max_events=10):
        """ returns a list of localized datetime due dates for a repeating task"""

        local_tz = pytz.timezone(self.timezone)
        last_event = datetime.combine( self.due_date , self.event_expiry_tm)

        if not self.repeat:
            #doesn't repeat, so return just the event
            logging.info(local_tz.localize(last_event))
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
            logging.info('iter_due_dates rep {0}'.format(local_tz.localize(last_event)))
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
        return self.smart_date(dt)
        fmt = '%a %d %b at %H:%M %Z'

        if  not dt:
            return '-'

        local_tz = pytz.timezone(self.timezone)
        localized_dt = local_tz.normalize(dt.astimezone(local_tz))
        self.smart_date(dt)
        return localized_dt.strftime(fmt)
    def smart_date(self,dt):

        if not dt:
            return '-'


        local_tz = pytz.timezone(self.timezone)
        localized_dt = local_tz.normalize(dt.astimezone(local_tz))
        now = pytz.UTC.localize(datetime.now())

        assert localized_dt > now,'smart_date only works with dates in the future'
        diff = localized_dt - now

        end_of_today = local_tz.normalize(now.astimezone(local_tz)).replace(hour=23,minute=59,second=59)

        if diff < timedelta(days=1):
            if localized_dt < end_of_today:
                fmt = "%I:%M%p"
            else:
                fmt = "%I:%M%p tomorrow"
        elif diff < timedelta(days=6):
            fmt = "%I:%M%p on %a"
        else:
            fmt = "%I:%M%p on %a %d %b"

        r = localized_dt.strftime(fmt)
        on = r.split('on')
        if len(on) > 1:
            r = on[0].lower() +' on '+ on[1]
        else:
            r=r.lower()
        if r[0] == "0":
            return r[1:]
        else:
            return r




    def pretty(self,dt):
        if dt:
            return shg_utils.prettydate(dt)
        else:
            return '-'


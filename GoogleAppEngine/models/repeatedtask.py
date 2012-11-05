from google.appengine.ext import ndb
import json
import logging
import cPickle
from functools import wraps
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

#Helper functions

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

def next_wd(weekdays,last_event,repeat_freq):
    eow = True
    for d in weekdays:
        if d > last_event.isoweekday():
            last_event += timedelta(days=d-last_event.isoweekday())
            eow = False
            break
    if eow:
        #reset to the begining of the week
        last_event += timedelta(days=weekdays[0] -last_event.isoweekday())

    last_event += timedelta(weeks=repeat_freq)

    return last_event

def human_date(timezone,dt):
    """Human readable format with precision ~1day"""

    if not dt:
        return '-'

    local_tz = pytz.timezone(timezone)
    localized_dt = local_tz.normalize(dt.astimezone(local_tz))
    now = pytz.UTC.localize(datetime.now())

    diff = localized_dt - now

    if abs(diff).days ==0:
        if diff.days >= 0:
            return 'today'
        else:
            return 'yesterday'
    elif diff.days > 0:
        if diff.days == 1:
            return 'tomorrow'
        else:
            return '{0} days'.format(diff.days)
    else:
        return '{0} days ago'.format(abs(diff.days))



def human_time(timezone,dt):
    """Human readable format with precision the minute"""

    if not dt:
        return '-'

    local_tz = pytz.timezone(timezone)
    localized_dt = local_tz.normalize(dt.astimezone(local_tz))
    now = pytz.UTC.localize(datetime.now())

    assert localized_dt > now,'smart_date only works with dates in the future'
    diff = localized_dt - now

    end_of_today = local_tz.normalize(now.astimezone(local_tz)).replace(hour=23,minute=59,second=59)

    # 2:00pm
    # 20 minutes ago
    # 2pm yesterday
    # 2pm on X

    #within 24 hours
    if diff < timedelta(days=1):

        if localized_dt < end_of_today:
            fmt = "%I:%M%p"
        else:
            fmt = "%I:%M%p tomorrow"
    elif abs(diff) < timedelta(days=6):
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

def parse_time(delta_string):
    """Turns '9am the day before' into

    f('9am the day before') = {'days':1,'hours':9,'minutes':0}
    """

    #0 - hours 1-minutes 2-am/pm
    tm = re.match('([1][0-2]|[0]?[0-9])(?::|.)?([0-5][0-9])?[\s]*(am|pm)',delta_string,flags=re.I)

    if not tm:
        return None

    assert tm.group(1) and tm.group(3), 'Unknown time from {0}'.format(delta_string)

    hours = int(tm.group(1))

    if tm.group(3).lower() == "pm":
        hours += 12

    minutes = int(tm.group(2)) if tm.group(2) else 0

    days = delta_string[len(tm.group(0))+1:]

    if days == "same day":
        days = 0
    elif days == "the day before":
        days = 1
    else:
        days = int(days.split(' ')[0])

    assert hours >=0 and minutes >= 0 and days >=0,'Unknown time from {0}'.format(delta_string)
    assert hours <= 24 and minutes <= 60 and days <=14, 'Unknown time from {0}'.format(delta_string)

    return {'days':days,
            'hours':hours,
            'minutes':minutes}

def dates_around(iterator,dt,need_post,need_prev=0):
    dates = []
    prev = 0
    post = 0

    for date in iterator:

        dates.append(date)

        if date <= dt:
            prev += 1

        if date > dt:
            post +=1

        if post > need_post:
            break

    dates_after  = [d for d in dates if d > dt]
    dates_before = [d for d in dates if d <= dt]

    return dates_before[-need_prev:] + dates_after[:need_post]


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
    #event_expiry_tm = time(14,30,59)


    @property
    def due_in(self):
        hd = self.human_date(self.next_due_utc())
        if 'days' in hd:
            return 'in ' + hd
        else:
            return hd

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
            new_r = []
            for r in dict['reminders']:
                if parse_time(r) != None:
                    new_r.append(r)
            if len(new_r) ==0:
                dict['no_reminder'] = True
            dict['reminders'] = new_r

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
    def completed_info(self,task_instance):

        task_completions = models.tasks.TaskCompletion.query(ancestor=self.key).\
        filter(models.tasks.TaskCompletion.task_instance == task_instance).fetch()

        return [{'housemate':tc.user_id,'when':tc.when} for tc in task_completions]

    def housemates_completed(self,task_instance=None):
        """returns a list of housemates who have completed a particular task instance"""
        if task_instance == None:
            task_instance = self.last_instance_key

        task_completions = self.completed_info(task_instance)
        return [tc['housemate'] for tc in task_completions]

    def get_task_completions(self,task_instance=None):
        if not task_instance:
            task_instance = self.last_instance_key

        return models.tasks.\
        TaskCompletion.query(ancestor=self.key).\
        filter(models.tasks.TaskCompletion.task_instance == task_instance).count()

    def is_task_complete(self,task_instance=None,task_completions=None,user_id=None):
        #todo - the task should stay completed, even if a new housemate joins..

        if task_completions == None:
            task_completions = self.get_task_completions(task_instance)

        if task_completions > 0:

            if user_id:
                hc = self.housemates_completed()
                logging.info(hc)
                if user_id in self.housemates_completed():
                    return True

            if not self.shared_task:
                return True

            if self.shared_all_reqd:

                if task_completions >= len(self.house.users):
                    return True

            elif task_completions >= self.shared_number:
                return True

        return False

    @ndb.transactional(xg=True)
    def complete_task(self,task_instance_key,user_id):

        if task_instance_key == None:
            task_instance_key = self.last_instance_key

        assert user_id in self.house.users,"User {0} is not found in house {1} for task '{2}'".format(user_id,self.house_id,self.name)
        assert user_id not in self.housemates_completed(task_instance_key),'Housemate {0} already completed task {1}'.format(user_id,self.name)

        task_completions = self.get_task_completions()

        tc = models.tasks.TaskCompletion(parent=self.key,user_id=user_id,task_instance=task_instance_key)
        tc.put()

        u = user.User._get_user_from_id(user_id)
        u.insert_points_transaction(points=self.points,desc='Completed ' + self.name,reference=task_instance_key)
        self.house.add_house_event(
            user_id=user_id,
            desc='completed ' + self.name,
            points=self.points,
            reference=task_instance_key)

        if self.is_task_complete(task_instance=None,task_completions=task_completions+1):
            self.house.add_house_event(
                                desc=self.name + ' is done.',
                                points=0,
                                reference=task_instance_key)

        return True

    @property
    def last_instance_key(self):
        """returns the last (most recent) task instance key for this task"""

        return models.tasks.TaskInstance.\
                query(ancestor=self.key,default_options=ndb.QueryOptions(keys_only=True)).\
                order(-models.tasks.TaskInstance.action_reqd).\
                get()

    def instance_keys(self,limit=10):
        """returns a list of task_instance keys that belong to this task in reverse order (most recent first)"""

        return models.tasks.TaskInstance.\
            query(ancestor=self.key,
            default_options=ndb.QueryOptions(keys_only=True)).\
            order(-models.tasks.TaskInstance.updated).\
            fetch(limit=limit)

    def update_events(self):
        last_ti = self.last_instance_key.get()

        child_reminders = models.tasks.TaskReminder.query()\
        .filter(models.tasks.TaskReminder.owner_instance==last_ti.key).fetch()

        for c in child_reminders:
            c.key.delete()

        next_expiry = self.next_expiry_utc()
        next_expiry = next_expiry.replace(tzinfo=None) if next_expiry else None
        last_ti.action_reqd = next_expiry
        last_ti.put()
        self.add_next_reminder(last_ti.key)

        return

    @ndb.transactional(xg=True)
    def setup_events(self):

        next_expiry = self.next_expiry_utc()
        next_expiry = next_expiry.replace(tzinfo=None) if next_expiry else None

        if next_expiry:
            ti = models.tasks.TaskInstance(parent=self.key,action_reqd=next_expiry)
        else:
            ti = models.tasks.TaskInstance(parent=self.key,action_reqd=None)

        ti.put()
        self.add_next_reminder(ti.key)

    def add_next_reminder(self,task_instance,after=None):

        next_reminder = self.next_reminder_utc(after)
        next_reminder = next_reminder.replace(tzinfo=None) if next_reminder else None

        if next_reminder:

            #Only add a reminder if it occurs before the TaskInstance expires...
            if not task_instance.get().expired(next_reminder):
                tr = models.tasks.TaskReminder(owner_instance=task_instance,action_reqd=next_reminder)
                tr.put()
            else:
                logging.info('task instance would have expired by {0} - not adding a reminder {1}'.format(task_instance.get().action_reqd,next_reminder))

    def calc_reminder_delta(self,desc,dt_event):
        """take a reminder description and a datetime and calculate the offset"""

        delta = parse_time(desc)

        return (dt_event + timedelta(days=-delta['days'])).replace(hour=delta['hours'],minute=delta['minutes'],second=0) -\
            dt_event.replace(hour=self.event_expiry_tm.hour,minute=self.event_expiry_tm.minute)

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
        return house.House.get_by_id(self.house_id)

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
        return pytz.UTC.localize(datetime.now()) # + timedelta(seconds=1)

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

        if self.due_date is None:
            return None

        if self.doesnt_expire:

            if not self.repeat:
                return now + timedelta(days=365)

            dates = dates_around(iterator=self.iter_due_dates(),dt=now,need_prev=2,need_post=2)

            expiries = []
            last_exp = dates.pop(0)
            for d in dates:

                diff = d - last_exp
                expiries.append( last_exp + timedelta(seconds = diff.total_seconds()/2) )
                last_exp =d

            expiry_before = [e for e in expiries if e <= now]
            expiry_after = [e for e in expiries if e > now]

            logging.info('{0} expiries returned around {1}'.format(len(expiries),now))

            for d in expiries:
                logging.info(d)

            assert len(expiry_after) > 0,'No expiry found after'
            #assert len(expiry_before) > 0,'No expiry found before'

            return expiry_after[0]

        else:
            #if a task expires, its expiry date is the next due date after now

            for dd in self.iter_due_dates_utc(None):
                if dd > now:
                    return dd

    def next_due_utc(self,after=None):
        """the next datetime a task is due, after a certain datetime (defaults to now)"""

        if not after:
            after = self.now_utc

        for event in self.iter_due_dates_utc(None):
            if event > after:
                return event

    def completable_from(self):
        """returns when the task completable from"""

        if not self.repeat:
            #tasks that dont repeat are completable from when they are created
            return pytz.UTC.localize(self.created)

        now = self.now_utc
        dates = dates_around(iterator=self.iter_due_dates(),dt=now,need_prev=2,need_post=2)

        expiries = []
        last_exp = dates.pop(0)
        for d in dates:

            diff = d - last_exp
            expiries.append( last_exp + timedelta(seconds = diff.total_seconds()/2) )
            last_exp =d

        expiry_before = [e for e in expiries if e <= now]
        expiry_after = [e for e in expiries if e > now]
        if self.doesnt_expire:

            if len(expiry_before) >0:
                return expiry_before[-1]
            else:
                return now
        else:
            next_dd = self.next_due_utc()
            logging.info('nextdd: {0}'.format(next_dd))
            prev_expiry = None

            for e in expiries:
                if e >= next_dd:
                    if prev_expiry:
                        logging.info('prevex: {0}'.format(prev_expiry))
                        return prev_expiry
                    else:
                        logging.info('nopre: {0}'.format(e))
                        return now
                prev_expiry = e





    def is_completable(self):
        return self.completable_from() <= self.now_utc

    def current_due_dt(self):

        local_tz = pytz.timezone(self.timezone)

        next_expiry = self.next_expiry_utc()
        last_due=None
        for d in self.iter_due_dates_utc():

            if d > next_expiry:
                if last_due:
                    return local_tz.normalize(last_due.astimezone(local_tz))
                else:
                    return local_tz.normalize(d.astimezone(local_tz))

            last_due = d


    def next_reminder_utc(self,after=None):
        """next reminder for a task
            -reminders are based on task due date, not expiry date"""
        if self.no_reminder:
#            logging.error('next reminder being called, but no_reminder is set')
            return None

        if not after:
            after = self.now_utc

        next_event = self.next_due_utc(after)

        if next_event:
            for reminder in self.iter_reminders(next_event):
                if reminder > after:
                    return reminder

    def iter_reminders(self,dt_event):
        """ returns datetime objects for reminders for an event occurring on dt_event """

        sorted_reminders = sorted([self.calc_reminder_delta(r,dt_event) for r in self.reminders])

        for r in sorted_reminders:
            yield  dt_event + r


    def iter_due_dates_utc(self,max_events=10):
        """returns a list of UTC datetime objects for a repeating task"""

        utc = pytz.UTC

        for e in self.iter_due_dates(self.now_utc + timedelta(days=800)):
            idd= utc.normalize(e.astimezone(utc))
            yield idd

    def iter_due_dates(self,up_to=None):
        """ returns a list of localized datetime due dates for a repeating task upto and including up_to"""

        assert self.due_date, 'Cant iter due dates with no due date..'

        local_tz = pytz.timezone(self.timezone)
        last_event = datetime.combine( self.due_date , self.event_expiry_tm)

        if not self.repeat:
            #doesn't repeat, so return just the due date
            yield local_tz.localize( last_event )
            return

        if len(self.repeat_on) > 0:
            wd = sorted([self.weekdays_to_int(d) for  d in self.repeat_on])
            if last_event.isoweekday() not in wd:
                last_event = next_wd(wd,last_event,self.repeat_freq)

            original_dow = None
        else:
            wd = None
            original_dow = {'day':last_event.day,'weekday':last_event.isoweekday()}

        i=0
        while True:

            if i > 0:
                #always return the sole due date..

                if self.repeats_limited and i >= self.repeats_times:
                    return

                if up_to is not None and local_tz.localize(last_event) > up_to:
                    return

            i+=1
            yield local_tz.localize( last_event )

            if self.repeat_period == "Daily":

                last_event += timedelta(days=self.repeat_freq)

            elif self.repeat_period == "Weekly":
                if wd:
                    last_event = next_wd(wd,last_event,self.repeat_freq)
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
                    elif original_dow['day'] > 21:
                        max_day = 28
                    elif original_dow['day'] > 14:
                        max_day = 21
                    elif original_dow['day'] > 7:
                        max_day = 14
                    else:
                        max_day = 7

                    if last_event.day + dd_f > max_day:
                        #logging.info('{3} le day {0} dow {1} going backwards {2} - f{4} b{5}'.format(last_event.day,last_event.isoweekday(),-dd_b,last_event.month,dd_f,dd_b))
                        last_event += timedelta(days= -dd_b)
                    else:
                        #logging.info('{3} le day {0} dow {1} going forwards {2} - f{4} b{5}'.format(last_event.day,last_event.isoweekday(),dd_f,last_event.month,dd_f,dd_b))
                        last_event += timedelta(days= dd_f)

            elif self.repeat_period == "Yearly":

                last_event = add_years(datetime.combine(self.due_date,self.event_expiry_tm),i)



    #todo - pretty
    #todo localize
    def human_date(self,dt):
        return human_date(self.timezone,dt)

    def human_time(self,dt):
        return human_time(self.timezone,dt)

    def human_relative_time(self,dt):
        """relative time with precision to the second"""

        if not dt:
            return '-'

        return shg_utils.prettydate(dt)



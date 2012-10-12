from google.appengine.ext import ndb
import json
import logging
import session
import shg_utils
import re
from models import house, authprovider,user
from models.email import EmailHash
from handlers.jinja import Jinja2Handler
from models.repeatedtask import RepeatedTask
from pytz.gae import pytz
from datetime import datetime, timedelta, time
from time import sleep
import calendar
import os
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')





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
    
    #user who completed the task
    user_id = ndb.IntegerProperty(required=True)
    
    #when the task was completed
    when = ndb.DateTimeProperty(auto_now_add=True)
    
    #If the object referenced here exists, the task has not 'refreshed' yet
    task_instance = ndb.KeyProperty(required=True)


#Task Event is the base class for lightweight pointers for events
#that need to happen at a certian utc DT

class TaskEvent(ndb.Model):
    """A pointer to the Owner Task to be called at a regular interval using cron"""
    
    #
    action_reqd = ndb.DateTimeProperty(required=True,indexed=True)


#class TaskOwnerDelete(TaskEvent):
#    """Deletes the owner after action_reqd"""
#    
#    def action(self):
#        self.owner.delete()


#Task expiry is an example of a task event

class TaskInstance(TaskEvent):
    """The TaskInstance class is used to represent a single occurence of a task.
    
    It's key is referenced to determine whether a particular task has expired or not
    
    """
    @property
    def ptask(self):
        return self.key.parent.get()
    
    def expired(self):
        return self.action_reqd < datetime.now()

    
    def action(self):
        """Expiry of task"""
        
        logging.info("Task expiring: '{0}'".format(self.ptask.name))


class TaskReminderEmail(EmailHash):
    """A record of reminder emails sent
        - provides a unique link for users to click on to action a task
        - maps back to original task
    """
    user_id = ndb.IntegerProperty(required=True)
    name = ndb.StringProperty(required=True)
    #reference to task_instance
    owner = ndb.KeyProperty(required=True)
    task_name = ndb.StringProperty(required=True)
    due_in = ndb.StringProperty(required=True)
    task_name = ndb.StringProperty(required=True)

    @classmethod
    def _get_or_create(cls,**kwargs):
        
        assert 'email' in kwargs, 'Unknown email address'
        owner = kwargs['owner']
        email = kwargs['email']
        
        tre = cls.query(cls.email == email, cls.owner == owner).get()
        
        if not tre:
            tre = cls._create(**kwargs)
        
        return tre
                
    def render_body(self,host_url):
        firstname = self.name.split(' ')[0]
        
        email_body = 'Dear {firstname},\n\n' + \
          "'{task_name}' is due in {due_in}.\n" + \
          ":\n" + \
          "{1}\n\n" + \
          "Bert Bert\n" + \
          "Sharehouse Game - Support\n" + \
          "http://www.SharehouseGame.com\n"
    
        return email_body.format(firstname,host_url+self.get_link())
        
    def render_subject(self):
        firstname = self.name.split(' ')[0]

        return "{0}, '{task_name} is due in {due_in}".format(firstname)
    
    @staticmethod
    @house.manage_house
    def login(jinja):
        return jinja
    
    @ndb.transactional(xg=True)
    def verified(self,jinja):
        
        jinja=self.login(jinja)
        
        owner = self.owner.get()
        if owner.expired():
        
            return jinja.generic_error(title="Task expired",message='Sorry')
        else:
            
            rt = owner.key.parent().get()
            if self.user_id in rt.housemates_completed(owner.key):
                return jinja.generic_error(title='Already completed',message="You've already completed this task for this <week>, sorry")
            else:
                rt.complete_task(owner.key,self.user_id)
                return jinja.generic_success(title="Link good",message='Task completed')


class TaskReminder(TaskEvent):
    """Goes through and sends reminders"""
    owner = ndb.KeyProperty(required=True,indexed=True)
    
    ndb.transactional(xg=True)
    def create_new(self,rt,ti):
        rt.add_next_reminder(self.owner,pytz.UTC.localize(self.action_reqd))
        self.key.delete()
        
    def action(self):
    
        #TaskInstance
        ti = self.owner.get()
        
        #Parent of the TaskInstance is a Repeated Task
        rt = ti.key.parent().get()
        
        logging.info('House {0} with users {1}'.format(rt.house,rt.house.users)   )
        for housemate_id in rt.house.users:
            hm = user.User._get_by_id(housemate_id)
            
            tre = TaskReminderEmail._get_or_create(name=hm.display_name,user_id=housemate_id,email=hm.verified_email,owner=ti.key)
            logging.info('sending reminder to {0}'.format(hm.verified_email))
            tre.send_email()
            
        self.create_new(rt,ti)
                
        #exclude housemates who
        #   have completed the task
        #   have muted the task
        #   have disabled emails
        

class Task(Jinja2Handler):
    
    @house.manage_house
    def post(self,action):
    
        if action == 'create':
                
            dict = self.request.POST
            dict['created_by'] = self.request.session.user._get_id()
            dict['house_id'] = self.request.session.user.house_id
            
            rt = RepeatedTask.create(dict)
            
            hse = house.House.get_by_id(self.request.session.user.house_id)
            hse.add_house_event(self.request.session.user._get_id(),'created a task named {0}'.format(dict['name']),0)
                
            self.json_response(json.dumps({'success':'Task created','redirect':'/tasks'}))
            
        return

    @house.manage_house
    def list(self):
        house_id = self.request.session.user.house_id
        assert int(house_id) > 0,'No house ID?'
        logging.info(house_id)

        tasks = RepeatedTask.query(RepeatedTask.house_id == house_id).fetch()

        #assert len(tasks) > 0,'No tasks found'
        return self.render_template('tasks.html',{'tasks':tasks})
    
    @house.manage_house
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
        
        action_entities = [TaskReminder]
        
        if DEBUG:
            td = timedelta(days=100)
        else:
            td = timedelta(minutes=10)
        
        for ae in action_entities:
            for task_event in ae.query(ae.action_reqd < (datetime.now() + td)).fetch():
                task_event.action()
                
        
        
        return

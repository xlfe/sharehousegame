from google.appengine.ext import ndb
import logging
from models.repeatedtask import RepeatedTask
from models import house,user
from models.email import EmailHash
from pytz.gae import pytz
from datetime import datetime, timedelta, time
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


#Task Event is the base class for lightweight pointers for events
#that need to happen at a certian utc DT

class TaskEvent(ndb.Model):
    """A pointer to the Owner Task to be called at a regular interval using cron"""
    action_reqd = ndb.DateTimeProperty(required=True,indexed=True)



class TaskInstance(TaskEvent):
    """The TaskInstance class is used to represent a single occurence of a task.

    It's key is referenced to determine whether a particular task has expired or not.

    It is the child of a (Repeated)Task
    """
    @property
    def parent_task(self):
        return self.key.parent().get()

    def expired(self,when=None):
        if not when:
            when = datetime.now()
        return self.action_reqd < when

    def action(self):
        """Expiry of task"""

        logging.info("Task expiring: '{0}'".format(self.parent_task.name))
        self.parent_task.setup_events()


class TaskReminderEmail(EmailHash):
    """A record of reminder emails sent
        - provides a unique link for users to click on to action a task
        - maps back to original task
    """
    user_id = ndb.IntegerProperty(required=True)
    firstname = ndb.StringProperty(required=True)
    #reference to task_instance
    owner = ndb.KeyProperty(required=True)
    details = ndb.StringProperty(required=True)
    task_name = ndb.StringProperty(required=True)
    due_in = ndb.StringProperty(required=True)

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

        email_body = 'Dear {0},\n\n' + \
          "Your SharehouseGame task '{1}' is due soon:\n\n" \
          "Due: {2}.\n" +\
          "Quick action links:\n" +\
          "Task details: {3}\n" +\
          "Task done: {3}?done\n" +\
          "Mute future email notifications: {3}?mute\n" +\
          "Details: \n{4}\n\n" + \
          "Bert Bert\n" + \
          "Sharehouse Game - Support\n" + \
          "http://www.SharehouseGame.com\n"

        return email_body.format(self.firstname,self.task_name,self.due_in,host_url+self.get_link(),self.details)

    def render_subject(self):
        return "{0}, the task '{1}' is due in {2}".format(self.firstname,self.task_name,self.due_in)

    @staticmethod
    @user.manage_user
    def login(jinja):
        return jinja

    @ndb.transactional(xg=True)
    def verified(self,jinja):

        jinja=self.login(jinja)

        owner = self.owner.get()
        if owner.expired():
            #maybe direct them to the current instance of the task...
            return jinja.generic_error(title="Task expired",message='Sorry')
        else:

            rt = owner.parent_task
            if self.user_id in rt.housemates_completed(owner.key):
                return jinja.generic_error(title='Already completed',
                    message="You've already completed this task for this <week>, sorry")
            else:
                rt.complete_task(owner.key,self.user_id)
                return jinja.generic_success(title="Link good",message='Task completed')


class TaskReminder(TaskEvent):
    """Goes through and sends reminders"""
    owner_instance = ndb.KeyProperty(required=True,indexed=True)

    ndb.transactional(xg=True)
    def create_new(self,rt,ti):
        rt.add_next_reminder(self.owner_instance,pytz.UTC.localize(self.action_reqd))
        self.key.delete()

    def action(self):

        #TaskInstance
        ti = self.owner_instance.get()

        #Parent of the TaskInstance is a Repeated Task
        rt = ti.parent_task

        logging.info('Task {0} is due in {1}'.format(rt.name,rt.due_in)   )

        for housemate_id in rt.house.users:
            hm = user.User._get_by_id(housemate_id)
            firstname = hm.display_name.split(' ')[0]
            tre = TaskReminderEmail._create(
                due_in=rt.due_in
                ,   user_id = housemate_id
                ,   task_name = rt.name
                ,   owner = ti.key
                ,   firstname = firstname
                ,   email = hm.verified_email
                ,   details = rt.desc
            )

            tre.send_email()

        self.create_new(rt,ti)





class TaskCompletion(ndb.Model):
    """Stores a record of a housemate completing a task"""

    user_id = ndb.IntegerProperty(required=True)
    when = ndb.DateTimeProperty(auto_now_add=True)
    task_instance = ndb.KeyProperty(required=True)


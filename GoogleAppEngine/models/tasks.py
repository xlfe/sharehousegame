from google.appengine.ext import ndb
import logging
from models.repeatedtask import RepeatedTask, human_time
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
    delay = ndb.IntegerProperty(required=True)

    house_id = ndb.IntegerProperty(required=True, indexed=True)
    created_by = ndb.IntegerProperty(required=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    disabled = ndb.BooleanProperty(default=False)

    def get_last_completion(self):

        return TaskCompletion().\
        query(TaskCompletion.task_instance==self.key).\
        order(-TaskCompletion.when).\
        get()

    def completable_from(self):

        lc = self.get_last_completion()

        cf = lc.when + timedelta(minutes = self.delay)

        tz = house.House.get_by_id(self.house_id).timezone

        return human_time(tz,pytz.UTC.localize(cf))

    def is_completable(self):

        lc = self.get_last_completion()

        if lc is None:
            return True

        if lc.when + timedelta(minutes = self.delay) < datetime.now():
            return True
        else:
            return False

    def complete_task(self,user_id):

        tc = TaskCompletion()
        tc.task_instance = self.key
        tc.user_id=user_id
        tc.put()

        u = user.User._get_user_from_id(user_id)
        u.insert_points_transaction(points=self.points,desc='Completed ' + self.name,reference=tc.key)
        hse = house.House.get_by_id(u.house_id)
        hse.add_house_event(
            user_id=user_id,
            desc='completed ' + self.name,
            points=self.points,
            reference=tc.key)

#Task Event is the base class for lightweight pointers for events
#that need to happen at a certian utc DT

class TaskEvent(ndb.Model):
    """A pointer to the Owner Task to be called at a regular interval using cron"""
    action_reqd = ndb.DateTimeProperty(indexed=True)
    updated      = ndb.DateTimeProperty(indexed=True,auto_now=True)




def remove_children_of_instance(instance_key):
    default_options=ndb.QueryOptions(keys_only=True)
    for c in TaskReminder.query(default_options=default_options)\
                         .filter(TaskReminder.owner_instance==instance_key).fetch():
        c.delete()

    for r in TaskReminderEmail.query(default_options=default_options)\
                            .filter(TaskReminderEmail.owner == instance_key).fetch():
        r.delete()



class TaskInstance(TaskEvent):
    """The TaskInstance class is used to represent a single occurence of a task.

    It's key is referenced to determine whether a particular task has expired or not.

    It is the child of a (Repeated)Task
    """
    @property
    def parent_task(self):
        return self.key.parent().get()

    def expired(self,when=None):
        if not self.action_reqd:
            return True
        if not when:
            when = datetime.now()
        return self.action_reqd < when

    def action(self):
        """Expiry of task"""
        self.action_reqd = None
        self.put()
        pt = self.parent_task
        if pt:
            pt.setup_events()
            logging.info("Task expiring: '{0}'".format(pt.name))
        else:
            logging.info('Removing TaskInstance without parent')
            self.key.delete()


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
    task_id = ndb.IntegerProperty(required=True)
    due_in = ndb.StringProperty(required=True)

    @classmethod
    def _get_or_create(cls,**kwargs):

        assert 'email' in kwargs, 'Unknown email address'
        owner = kwargs['owner']
        email = kwargs['email']

        tre = cls.query().filter(cls.email == email,cls.owner == owner).get()

        if not tre:
            tre = cls._create(**kwargs)
        else:
            kwargs.pop('email')
            kwargs.pop('owner')
            tre.populate(**kwargs)
            tre.put()

        return tre

    def render_body(self,host_url):

        email_body = 'Dear {0},\n\n' + \
          "The task '{1}' is due {2}!\n" +\
          "Details: \n{4}\n\n" + \
          "If you have completed the task: \n{3}\n\n" +\
          "Bert Bert\n" + \
          "Sharehouse Game - Support\n" + \
          "http://www.SharehouseGame.com\n"

        return email_body.format(self.firstname,self.task_name,self.due_in,host_url+self.get_link(),self.details)

    def render_subject(self):
        return "{0}, the task '{1}' is due {2}".format(self.firstname,self.task_name,self.due_in)

    @staticmethod
    @user.manage_user
    def login(jinja):
        return jinja

    @ndb.transactional(xg=True)
    def verified(self,jinja):

        jinja=self.login(jinja)
        owner = self.owner.get()

        if not owner:
            self.key.delete()
            return jinja.generic_error(title="Task not found",message='Sorry, we were unable to find that task.')

        if jinja.request.session.user is None:
            #todo this is not really secure (assumes users email is secure)
            jinja.request.session.upgrade_to_user_session(self.user_id)
            self.key.delete()

        task_link = "/task/complete?id={0}".format(self.task_id)

        return jinja.redirect(task_link)

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

        if ti.expired() or rt.is_task_complete(ti.key):
            self.key.delete()
            logging.info('Task is complete or expired, removing reminder')
            return

        logging.info('Task {0} is due in {1}'.format(rt.name,rt.due_in)   )

        already_completed = rt.housemates_completed(ti.key)

        for housemate_id in rt.house.users:

            if housemate_id in already_completed:
                continue

            hm = user.User._get_by_id(housemate_id)
            firstname = hm.display_name.split(' ')[0]

            tre = TaskReminderEmail._get_or_create(
                due_in=rt.due_in
                ,   user_id = housemate_id
                ,   task_name = rt.name
                ,   owner = ti.key
                ,   firstname = firstname
                ,   email = hm.verified_email
                ,   details = rt.desc
                ,   task_id = rt.key.id()
            )

            tre.send_email()

        self.create_new(rt,ti)





class TaskCompletion(ndb.Model):
    """Stores a record of a housemate completing a task"""

    user_id = ndb.IntegerProperty(required=True)
    when = ndb.DateTimeProperty(auto_now_add=True)
    task_instance = ndb.KeyProperty(required=True)


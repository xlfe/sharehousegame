from google.appengine.ext import ndb
from google.appengine.ext import deferred
import json
import logging
import session
import shg_utils
import re
from models import house, authprovider,user, tasks
import models
from models.email import EmailHash
from handlers.jinja import Jinja2Handler
from models.repeatedtask import RepeatedTask
from models.tasks import StandingTask
from pytz.gae import pytz
from datetime import datetime, timedelta, time
from time import sleep
import calendar
import os
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

class Task(Jinja2Handler):

    def match_user_task(self,action):
        """ If task ID supplied
                The user is logged in
                The user has permission to view the task
                saves self.task as the task"""

        #User must be logged in

        if self.request.session.user is None:
            return self.generic_error(title='Not logged in',message="This page is only available to logged in users")

        #User must have valid house
        if self.request.session.user.house is None:
            self.redirect('/')

        id = self.request.get('id',None)

        if id is None:
            return getattr(self,action)()
        else:
            if self.request.route.name == 'tasks':
                task = ndb.Key('RepeatedTask',int(id)).get()
            elif self.request.route.name == 'standing':
                task = ndb.Key('StandingTask',int(id)).get()

            if task and self.request.session.user.house.get_house_id() == task.house_id:
                self.task = task
                return getattr(self,action)()
            else:
                return self.generic_error(title='Unknown task',
                                        message="We're sorry, but we can't find that task",
                                        action_link='/tasks')

    @house.manage_house
    def post(self,action):
        return self.match_user_task('post_'+action)

    @house.manage_house
    def get(self,action):
        return self.match_user_task('get_'+action)

    @house.manage_house
    def list(self):
        if self.request.session.user is None:
            return self.generic_error(title='Not logged in',message='Please login to access that page')
        house_id = self.request.session.user.house_id
        if not house_id:
            return self.generic_error(title='Registration not complete',message='You must complete your Sharehouse setup prior to continuing...')

        if self.request.route.name == 'tasks':
            tasks = RepeatedTask.query().filter(RepeatedTask.house_id == house_id,RepeatedTask.disabled==False).fetch()

    #        sorted_reminders = sorted([self.calc_reminder_delta(r,dt_event) for r in self.reminders])
            #,key=lambda k: k.total_seconds())
            if tasks:
                tasks = sorted(tasks,key=lambda k:k.current_due_dt() if k.current_due_dt() != None else pytz.UTC.localize(datetime(2100,1,1)) )

            return self.render_template('tasks.html',{'tasks':tasks})
        elif self.request.route.name =='standing':

            tasks = StandingTask.query().filter(StandingTask.house_id == house_id,StandingTask.disabled==False).fetch()

            return self.render_template('standing_tasks.html',{'tasks':tasks})

    def post_create(self):

        dict = self.request.POST
        dict['created_by'] = self.request.session.user._get_id()
        dict['house_id'] = self.request.session.user.house_id

        if self.request.route.name == 'tasks':

            rt = RepeatedTask.create(dict)

            hse = house.House.get_by_id(self.request.session.user.house_id)
            hse.add_house_event(user_id = self.request.session.user._get_id(),
                            desc = 'created a task named {0}'.format(dict['name']),
                            points = 0,
                            reference=rt.key)

            return self.json_response(json.dumps({'success':'Task created','redirect':'/tasks'}))
        elif self.request.route.name == 'standing':
            st = StandingTask()
            dict = shg_utils.encapsulate_dict(self.request.POST,StandingTask)
            st.populate(**dict)
            st.put()

            self.request.session.user.house.add_house_event(
            user_id=self.request.session.user._get_id(),
            desc="created standing task '"+ st.name + "'",
            points=0,
            reference=None)



            return self.json_response(json.dumps({'success':'Task created','redirect':'/standing'}))


    def post_edit(self):

        dict = self.request.POST
        id = dict.pop('id')

        if self.request.route.name == 'tasks':

            if self.task.update(dict):
                self.task.update_events()
                return self.json_response(json.dumps({'success':'Task updated','redirect':'/tasks'}))
            else:
                return self.json_response(json.dumps({'failure':'Unable to update task'}))
        elif self.request.route.name == 'standing':
            dict = shg_utils.encapsulate_dict(dict,StandingTask)
            self.task.populate(**dict)
            self.task.put()

            return self.json_response(json.dumps({'success':'Task updated','redirect':'/standing'}))



    def get_edit(self):

        if self.request.route.name == 'tasks':

            sp_rem = []

            for r in self.task.reminders:
                sp = r.split(' ')
                sp_rem.append([sp[0],' '.join(s for s in sp[1:])])

            return self.render_template('repeating_task.html',{'task':self.task,'task_reminders':sp_rem})
        elif self.request.route.name == 'standing':

            mins_delay = self.task.delay

            if mins_delay < 60:
                delay = mins_delay
                delay_name = 1
            elif mins_delay < 1440:
                delay = mins_delay / 60
                delay_name = 60
            else:
                delay = mins_delay / 1440
                delay_name = 1440


            return self.render_template('standing_task.html',{'task':self.task,'delay':delay,'delay_name':delay_name})

    def get_create(self):
        page_map = {'tasks':'repeating_task.html',
                    'standing':'standing_task.html'}

        return self.render_template(page_map[self.request.route.name])

    def get_complete(self):

        if self.request.get('confirm'):

            if self.request.route.name == 'tasks':

                if self.task.is_completable() and not self.task.is_task_complete():
                    self.task.complete_task(task_instance_key=None,user_id=self.request.session.user._get_id())
                else:
                    logging.info('task trying to be completed, but shouldnt be {0}'.format(self.task.key.id()))
                return self.redirect('/tasks')
            elif self.request.route.name == 'standing':

                self.task.complete_task(user_id=self.request.session.user._get_id())
                return self.redirect('/standing')



        else:

            if self.request.route.name == 'tasks':

                if self.request.session.user._get_id() in self.task.housemates_completed():

                    return self.generic_success(title='Already completed',
                                                message="You've already completed this task!")

                elif self.task.is_task_complete():
                    return self.generic_success(title='Already completed',
                                                message="One of your housemates has already completed this task")

                elif self.task.is_completable() == False:
                    return self.generic_error(title="Task not yet completable",
                    message="You will be able to complete this task in {0}".format(self.task.human_relative_time(self.task.completable_from())))

                tvars = {'title':format(self.task.name),
                    'message':"Please confirm you have completed this task",
                    'action':"I have completed this task &raquo;",
                    'action_link':"/task/complete?id={0}&confirm=yes".format(self.task.key.id())}

                return self.render_template('actions/complete_task.html',tvars)

            elif self.request.route.name == 'standing':
                if not self.task.is_completable():

                    return self.generic_error(title='Task not yet completable',
                    message="You will have to wait...")


                return self.generic_success(title=format(self.task.name),
                             message="Please confirm you have completed this task",
                                action="I have completed this task &raquo;",
                                action_link="/standing/complete?id={0}&confirm=yes".format(self.task.key.id()))


    def get_delete(self):


        if self.request.get('confirm'):

            if self.task.disabled is True:
                return self.generic_error(title='Task is already deleted',message='This task has already been deleted')

            hse = house.House.get_by_id(self.request.session.user.house_id)
            hse.add_house_event(user_id = self.request.session.user._get_id(),
                                desc = "deleted '{0}'".format(self.task.name),
                                points=0,
                                reference=self.task.key)


            self.task.disabled = True
            self.task.put()
            if self.request.route.name =='tasks':

                for instance in self.task.instance_keys(limit=None):
                    tasks.remove_children_of_instance(instance)

                inst = self.task.last_instance_key.get()
                inst.action_reqd = None
                inst.put()
                sleep(1)
                return self.redirect('/tasks?deleted')
            elif self.request.route.name == 'standing':
                return self.redirect('/standing?deleted')
        else:

            if self.request.route.name == 'tasks':
                action_link="/task/delete?id={0}&confirm=yes".format(self.task.key.id())
            elif self.request.route.name == 'standing':
                action_link="/standing/delete?id={0}&confirm=yes".format(self.task.key.id())

            return self.generic_error(title="Delete task '{0}?'".format(self.task.name),
                message="Please confirm you want to delete this task",
                action="Delete task &raquo;", action_link=action_link)


    def get_info(self):

        results = get_task_info(self.task)
        return self.json_response(json.dumps(results))

    def send_reminders(self):
        """Cron job that is run every 15 minutes"""
        
        action_entities = [tasks.TaskReminder,tasks.TaskInstance]
        
        td = timedelta()

        for ae in action_entities:
            for task_event in ae.query().filter(ae.action_reqd < (datetime.now() + td),ae.action_reqd != None).fetch():
                assert task_event.action_reqd != None,'action_reqd is None'
                task_event.action()

        return


def get_task_info(task):
    prev_ti = task.get_children_instance(limit=10)
    results ={}
    for ti_key in prev_ti:

        instance = {}

        child_reminders = tasks.TaskReminder.query().filter(tasks.TaskReminder.owner_instance==ti_key).fetch(10)

        for c in child_reminders:
            instance['Reminder ' + str(c.key)] = str(c)

        child_completions = task.completed_info(ti_key)

        instance['Completed ' + str(ti_key)] = str(child_completions)

        results[str(ti_key)] = instance


    return results
from google.appengine.ext import ndb
import json
import logging
import session
import shg_utils
import re
from models import house, authprovider,user, tasks
from models.email import EmailHash
from handlers.jinja import Jinja2Handler
from models.repeatedtask import RepeatedTask
from pytz.gae import pytz
from datetime import datetime, timedelta, time
from time import sleep
import calendar
import os
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')


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
                
            return self.json_response(json.dumps({'success':'Task created','redirect':'/tasks'}))

        elif action=="edit":

            dict = self.request.POST

            id = dict.pop('id')
            task = ndb.Key('RepeatedTask',int(id)).get()

            if not task or task.house_id != self.request.session.user.house_id:
                return self.json_response(json.dumps({'error':'Sorry, something went wrong!'}))

            if task.update(dict):
                return self.json_response(json.dumps({'success':'Task updated','redirect':'/tasks'}))
            else:
                return self.json_response(json.dumps({'failure':'Unable to update task'}))

    @house.manage_house
    def list(self):
        house_id = self.request.session.user.house_id
        assert int(house_id) > 0,'No house ID?'

        tasks = RepeatedTask.query(RepeatedTask.house_id == house_id).fetch()

        #assert len(tasks) > 0,'No tasks found'
        return self.render_template('tasks.html',{'tasks':tasks})
    
    @house.manage_house
    def get(self,action):
            
        if action == 'edit':
            id = self.request.GET['id']
            task = ndb.Key('RepeatedTask',int(id)).get()

            if not task or task.house_id != self.request.session.user.house_id:
               return self.generic_error(title='Unknown task',message="We're sorry, but we can't find that task")

            sp_rem = []

            for r in task.reminders:
                sp = r.split(' ')
                sp_rem.append([sp[0],' '.join(s for s in sp[1:])])

            return self.render_template('repeating_task.html',{'task':task,'task_reminders':sp_rem})
        
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
        
        action_entities = [tasks.TaskReminder,tasks.TaskInstance]
        
        td = timedelta()

        for ae in action_entities:
            for task_event in ae.query(ae.action_reqd < (datetime.now() + td)).fetch():
                task_event.action()

        return

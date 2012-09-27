
import webapp2
import json
import logging
import session
from models import authprovider,house,user
from google.appengine.ext import ndb
from time import sleep
from handlers.jinja import Jinja2Handler

class API(Jinja2Handler):
    
    @session.manage_user
    def api(self):
        
        session_user = self.request.session.user
        
        if session_user:
            
            what = self.request.get('what')
            
            if what == "house-setup":
                return self.house_setup(session_user)
            elif what == "refer":
                return self.refer(session_user)
                
            elif what == "leave-house":
                return self.leave_house(session_user)
                
    @ndb.transactional(xg=True)
    def leave_house(self,session_user):
        
        if session_user.house_id:
                
            hse = house.House._get_house_by_id(session_user.house_id)
    
            if hse:
                hse.remove_user(session_user._get_id())
    
            session_user.house_id = None
            session_user.put()
        sleep(1)   
        return self.redirect('/')
        
             
    def refer(self,session_user):
        
        id = int(self.request.get('housemate_id'))
        
        hse = house.House._get_house_by_id(session_user.house_id)
        assert hse, 'Error retreiving house'
        assert len(hse.invited_users) >= id, 'Unknown housemate ID'
        
        mail_hash = user.EmailHash.get_or_create(
                                    house_id    = session_user.house_id,
                                    name        = hse.invited_users[id].name,
                                    email       = hse.invited_users[id].email,
                                    referred_by = session_user.display_name
                                )
        
        reason = mail_hash.limited()
        
        if reason:
            return self.json_response(json.dumps( { 'failure' : reason ,'hm':repr(id)} ))
        
        
        if mail_hash.send_email(self.request.host_url,'invite_user'):
            return self.json_response(json.dumps({'success':repr(id)}))
        else:
            return self.json_response(json.dumps({'failure':"Sorry: we're unable to send the email! Please try again shortly.",'hm':repr(id)}))
    
                
    @ndb.transactional(xg=True)
    def house_setup(self,session_user):
                
        if session_user._get_house_id():
            raise Exception('User already has house_id, should not be in house setup')
        
        name = self.request.get('houseName')
        
        my_name = session_user.display_name
        
        housemates = []
        i = 0
        
        while True:
            hm_name,hm_email = self.request.get('hm{0}_name'.format(i),None),self.request.get('email_hm_{0}'.format(i),None)
            
            if not (hm_name or hm_email):
                break
            
            if len(hm_name) > 0:
                
                if i == 0:
                
                    if hm_name != session_user.display_name:
                        session_user.display_name = hm_name.strip()
                    
                    i+=1
                    continue
                else:
                    hu = house.InvitedUser(name = hm_name,email=hm_email)
                housemates.append(hu)
            i+=1
            if i > 10:
                break
        
        if len(housemates) > 0:
            hse = house.House(name = name,invited_users=housemates,users=[session_user._get_id()])
            hse.put()
            
        session_user.house_id = hse.get_house_id()
        session_user.put()
        
        session_user.insert_points_transaction(points=100,desc='Setup your sharehouse')
        hse.add_house_event(user_id=session_user._get_id(),desc='setup the house',points=100)
        
        resp = {
            'redirect':'/dashboard',
            'success':'House created {0} with {1} housemates'.format(name,i)
        }
    
        return self.json_response(json.dumps(resp)) #self.request.params)
	

def wipe_datastore():
    w = [
        authprovider.AuthProvider.query().fetch()
    ,   house.House.query().fetch()
    ,   house.HouseLog.query().fetch()
    ,   user.Points.query().fetch()
    ,   user.EmailHash.query().fetch()
    ,   session.Session.query().fetch()
    ,   user.User.query().fetch() ]
    

    for t in w:
        for i in t:
            i.key.delete()
            print i.key

class WipeDSHandler(webapp2.RequestHandler):

    def get(self):
        # TODO: discover why importing deferred outside of a
        # function causes problems with jinja2 filters.
        #from google.appengine.ext import deferred
        #deferred.defer(wipe_datastore)
        wipe_datastore()   
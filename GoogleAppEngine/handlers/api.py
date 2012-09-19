
import webapp2
import json
import logging
import session
from models import authprovider,house,user



class API(webapp2.RequestHandler):
    
    @session.manage_user
    def api(self):
        
        resp = {'redirect':''}
        session_user = self.request.session.user
        
        if session_user:
            
            what = self.request.get('what')
            
            if what == "house-setup":
                
                if session_user._get_house_id():
                    logging.error('User already has house_id, should not be in house setup userid {0}'.format(user._get_id()))
                    return
                
                name = self.request.get('houseName')
                
                my_name = session_user.display_name
                my_email = None
                
                housemates = []
                i = 0
                
                while True:
                    hm_name,hm_email = self.request.get('hm{0}_name'.format(i),None),self.request.get('email_hm_{0}'.format(i),None)
                    
                    if not (hm_name or hm_email):
                        break
                    
                    if len(hm_name) > 0:
                        
                        if hm_name == my_name or hm_email == my_email:
                            if not my_name or my_name.strip() == "":
                                session_user.display_name = hm_name
                            
                            i+=1
                            continue
                        else:
                            hu = house.InvitedUser(name = hm_name,email=hm_email)
                        housemates.append(hu)
                    i+=1
                
                if len(housemates) > 0:
                    hse = house.House(name = name,invited_users=housemates,users=[session_user._get_id()])
                    hse.put()
                    
                session_user.house_id = hse.get_house_id()
                session_user.put()
                
                session_user.insert_points_transaction(points=100,desc='Setup your sharehouse')
                hse.add_house_event(user_id=session_user._get_id(),desc='setup the house',points=100)
                
                resp = {
                    'redirect':'?home',
                    'success':'House created {0} with {1} housemates'.format(name,i)
                }
        
        self.response.out.write(json.dumps(resp)) #self.request.params)




def wipe_datastore():
    w = [
        authprovider.AuthProvider.query().fetch()
    ,   house.House.query().fetch()
    ,   house.HouseLog.query().fetch()
    ,   user.Points.query().fetch()
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
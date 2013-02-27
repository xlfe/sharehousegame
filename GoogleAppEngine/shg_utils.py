import datetime
import sys

from pytz.gae import pytz

def prettydate(d):

    if type(d) == type(datetime.datetime.now()) and d.tzinfo:
        now = pytz.UTC.localize(datetime.datetime.now())
    else:
        now = datetime.datetime.utcnow()

    diff = abs(now - d)
    s = diff.seconds
    
    length = ''
    
    if diff.days > 14:
        length = 'more than 2 weeks'
    elif diff.days == 1:
        length = '1 day'
    elif diff.days > 1:
        length = '{} days'.format(diff.days)
    elif s <= 1:
        length = 'just now'
    elif s < 60:
        length = '{} seconds'.format(s)
    elif s < 120:
        length = '1 minute'
    elif s < 3600:
        length = '{} minutes'.format(s/60)
    elif s < 7200:
        length = '1 hour'
    else:
        length = '{} hours'.format(s/3600)
        
    if (now - d).days >= 0:
        return '{0} ago'.format(length)
    else:
        return '~ {0}'.format(length)

from google.appengine.ext import ndb
import datetime

def encapsulate_dict(dict,model):
    """Only supports repeated strings currently
    will convert integers and bools """
    
    #encapsulate repeated properties
    for k,v in model._properties.iteritems():
        
        if type(v) == type(ndb.BooleanProperty()):
            if k in dict:
                dict[k] = dict.pop(k) == "True"
            else:
                dict[k] = False
                
        if type(v) == type(ndb.IntegerProperty()):
            if k in dict:
                d = dict.pop(k)
                if d == '':
                    dict[k] = None
                else:
                    dict[k] = int(d)
                
        if type(v) == type(ndb.DateProperty()):
            if k in dict:
                #Tuesday 09 October, 2012
                dict[k] = datetime.datetime.strptime(dict.pop(k),'%A %d %B, %Y')
            
            
        if v._repeated:
            l = []
            while k in dict:
                
                element = dict.pop(k)
                if element.strip() != '':
                    l.append(element)
            dict[k] = l
        
        
    
    return dict

import logging
def get_class(module,cls):
    
    exec('import {0}'.format(module))
    mod = sys.modules[module]
    return mod.__dict__[cls]
    
    


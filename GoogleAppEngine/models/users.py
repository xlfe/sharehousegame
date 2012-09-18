


class User(ndb.Model):
    """
    The user is the actual individual"""
    
    _default_indexed=False
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)
    primary_email = ndb.StringProperty(indexed=True)
    display_name = ndb.StringProperty()
    house_id = ndb.StringProperty()

    #authenticated = ndb.BooleanProperty(default=False)
    
    def _get_id(self):
        """Returns this user's unique ID, which is an integer."""
        return self.key.id()
    
    def _get_house_id(self):
        return self.house_id
    
    def _get_key(self):
        """gets the key for the user (ID and entity type)"""
        return self.key
    
    @classmethod
    def _get_first_name(cls,user_id):
        
        return cls._get_user_from_id(user_id).get_first_name()
    
    def get_first_name(self):
        return self.display_name.split(' ')[0]
        
    
    @classmethod
    def _create(cls):
        
        new_user = cls()
        new_user.put()
        new_user.insert_points_transaction(points=100,desc='Joined Sharehouse Game!')
        logging.info('New user signed up - userid:{0}'.format(new_user._get_id()))
        return new_user
    
    def points_log(self):
        pl = []
        
        for h in Points.query(ancestor=self.key).order(Points.when):
            a = {'when':prettydate(h.when)
                 ,'desc':h.desc
                 ,'points':h.points}
            pl.append(a)
            
        return pl
    
    def points_balance(self):
        balance = 0
        for p in Points.query(ancestor=self.key):
            balance += p.points
            
        return balance
            
    
    
    def insert_points_transaction(self,points,desc,link=None):
        pl = Points(parent=self.key,desc=desc,points=points,link=link)
        pl.put()
    
    
    @classmethod
    def _get_user_from_id(cls, id):
        """Gets a user based on their ID"""
        
        return cls.get_by_id(int(id))
        
    @classmethod
    def _get_user_from_email(cls,email):
        """returns a user based on their primary email"""
        try:
            return cls.query(cls.primary_email == email).iter().next()
        except StopIteration:
            return None
        
        
    
class Points(ndb.Model):
    _default_indexed=False
    when = ndb.DateTimeProperty(auto_now_add=True,indexed=True)
    desc = ndb.StringProperty()
    link = ndb.StringProperty()
    points = ndb.IntegerProperty(required=True)
    
   
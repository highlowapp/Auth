import pymysql
import bleach
import uuid
import bcrypt
import jwt
import random
import datetime
import time
import requests
import Helpers

#Email Config
email_config = Helpers.read_json_from_file("config/email_config.json")

#Email service
email_service = Helpers.service("email")

#Load secret key from file
SECRET_KEY = ""
with open("config/encryption_key.txt", 'r') as file:
    SECRET_KEY = file.read() 

class Auth:

    def __init__(self, servername, host, username, password, database):
        self.servername = servername
        self.host = host
        self.username = username
        self.password = password
        self.database = database
        
        #Run the tests
        self.run_tests()
        
        #Blacklisted tokens cache
        self.blacklisted_tokens = []

        self.SECRET_KEY = SECRET_KEY

        ## Load blacklisted tokens ##

        #Connect to the MySQL server
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()

        #Refresh blacklisted_tokens cache
        cursor.execute("SELECT token FROM blacklisted_tokens;")

        token_list = cursor.fetchall()

        for i in range(len(token_list)):
            self.blacklisted_tokens.append(token_list[i]["token"])

        conn.commit()
        conn.close()

    #Sign up
    def sign_up(self, firstname, lastname, email, password, confirmpassword):

        #Make a MySQL connection
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)

        cursor = conn.cursor()

        #Get and sanitize the input
        firstname = bleach.clean(firstname)
        lastname = bleach.clean(lastname)
        email = bleach.clean( email.lower() )
        password = bleach.clean(password)
        confirmpassword = bleach.clean(confirmpassword)

        #Keep track of errors
        error = ""


        #Check for empty firstname, lastname, or email
        if len(firstname) == 0:
            error = "empty-first-name"
        
        if len(lastname) == 0:
            error = "empty-last-name"
        
        if len(email) == 0:
            error = "empty-email"
        

        #Check for email duplicates
        cursor.execute("SELECT uid FROM users WHERE email='" + email + "';")

        if len( cursor.fetchall() ) > 0:

            error = "email-already-taken"

        #Is the email a valid email?
        if not ( ("@" in email) and ("." in email) ):
            error = "invalid-email"

        #Is the password long enough?
        #TODO: Determine our personal specifications for passwords
        if len(password) < 6:
            error = "password-too-short"

        #Do the passwords match?
        if password != confirmpassword:
            error = "passwords-no-match"
        

        if error == "":

            #Create a new user

            #Generate a uid
            uid = uuid.uuid1()

            #Hash the password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

            #Insert into the database
            cursor.execute("INSERT INTO users(uid, firstname, lastname, email, password, profileimage, streak) VALUES('" + str(uid) + "', '" + firstname + "', '" + lastname + "', '" + email + "', '" + hashed_password + "', '', 0);")

            #Commit and close
            conn.commit()
            conn.close()

            #Create and return an auth token
            token = self.create_token(str(uid))
            return token

        else:
            #Close the connection
            conn.close()
            return error

    #Sign in
    def sign_in(self, email, password):

        #Make a connection to MySQL
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)

        cursor = conn.cursor()

        #Get and sanitize the input
        email = bleach.clean(email.lower() )
        password = bleach.clean(password)

        #Keep track of errors
        error = ""

        #Does a user exist with that email?
        cursor.execute("SELECT uid, password FROM users WHERE email='" + email + "';")
        
        existingUser = cursor.fetchone()
        
        
        if existingUser != None:

            #If the password is correct...
            if bcrypt.checkpw(password.encode('utf-8'), existingUser["password"]):

                #The user is authenticated; create and return a token
                token = self.create_token( existingUser["uid"] )

                return token


            else:
                #The password is wrong
                error = "incorrect-email-or-password"
        else:
            error = "user-no-exist"

        #If the user was not authenticated, return the error
        return error

    #Create Token
    def create_token(self, uid, expiration_minutes= 60 * 24 * 365 / 2 ):

        #Calculate time half a year in the future (approximately)
        current_time = datetime.datetime.now()
        expiration = current_time + datetime.timedelta( minutes=expiration_minutes ) #Defaults to six months in the future



        token_payload = {
            "iss": "highlow",
            "exp": time.mktime( expiration.timetuple() ),
            "sub": uid,
            "iat": time.mktime( current_time.timetuple() )
        }

        token = jwt.encode(token_payload, self.SECRET_KEY, algorithm="HS256")

        return token

    #Validate Token
    def validate_token(self, token):
        
        payload = jwt.decode(token, self.SECRET_KEY, algorithms=["HS256"])

        current_timestamp = time.mktime( datetime.datetime.now().timetuple() )

        if payload["exp"] > current_timestamp and token not in self.blacklisted_tokens:
            return payload["sub"]

        return "ERROR-INVALID-TOKEN"

    #Send password reset email
    def send_password_reset_email(self, email):

        #Clean the email
        email = bleach.clean(email)

        ## Find user with that email ##

        #Connect to the MySQL server
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()

        #Get the relevant user(s)
        cursor.execute("SELECT firstname, lastname, uid, email FROM users WHERE email='" + email + "';")
        user = cursor.fetchone()

        #Commit and close the connection
        conn.commit()
        conn.close()

        #Check and see if any users existed with that email
        if user == None:
            return "user-no-exist"

        #Create a "password reset id" token that expires in a day
        token = self.create_token( user["uid"], expiration_minutes= 60 * 24 )

        ## Fetch the password reset email HTML and insert user information and the link we just generated ##
        password_reset_html = ""

        with open("passwordResetEmail.html", "r") as file:
            password_reset_html = file.read()

        
        
        password_reset_html = password_reset_html.format(user["firstname"], user["lastname"], 'http://' + self.servername + '/password_reset/' + token)

        #Send the email
        requests.post("http://{}/send_html_email".format(email_service) , data = {'email': user["email"], 'message': password_reset_html, 'password': email_config["password"]}) 
        


        return "success"

    #Reset password
    def reset_password(self, token, password, confirmpassword):

        #Clean the passwords
        password = bleach.clean(password)
        confirmpassword = bleach.clean(confirmpassword)

        #Make sure the id token is valid
        uid = self.validate_token(token)

        if uid == "ERROR-INVALID-TOKEN":
            return "ERROR-INVALID-TOKEN"

        #Confirm the passwords match
        if password != confirmpassword:
            return "passwords-no-match"

        #If the passwords matched and the token is valid, go ahead and reset the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        #Connect to MySQL
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()

        #Update the password
        cursor.execute("UPDATE users SET password = '" + hashed_password + "' WHERE uid='" + uid + "';")

        #Commit and close the connection
        conn.commit()
        conn.close()

        #Return success message
        return "success"

    def blacklist_token(self, token):
        #Connect to the MySQL server
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()

        token = bleach.clean(token)

        cursor.execute("INSERT INTO blacklisted_tokens(token) VALUES('{}');".format(token))

        #Refresh blacklisted_tokens cache
        cursor.execute("SELECT token FROM blacklisted_tokens;")

        token_list = cursor.fetchall()

        self.blacklisted_tokens = []

        for i in range(len(token_list)):
            self.blacklisted_tokens.append(token_list[i]["token"])

        conn.commit()
        conn.close()
        
    def sign_up_test(self):
        #Make sure the user is already deleted
        conn = pymysql.connect(self.host, self.username, self.password, self.database, cursorclass=pymysql.cursors.DictCursor)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM users WHERE email='test@example.com';")

        conn.commit()
        conn.close()
            
        error_messages = ["empty-first-name", "empty-last-name", "empty-email", 
                              "email-already-taken", "invalid-email", 
                              "password-too-short", "passwords-no-match"]
        result = self.sign_up( "Test", "Test", "test@example.com", "longpassword", "longpassword")

        if result in error_messages:
            print("Something went wrong in the sign_up_test, the error was: " + result)
        else:
            print("Everything went fine in the sign_up_test")
        
        

    def sign_in_test(self):
        error_messages = ["user-no-exist", "incorrect-email-or-password"]

        result = self.sign_in( "test@example.com", "longpassword")

        if result in error_messages:
            print("Something went wrong in the sign_in_test, the error was: " + result)
        else: 
            print("Everything went fine in the sign_in_test")
        

    def validate_token_test(self):

        token = self.sign_in( "test@example.com", "longpassword" )

        result = self.validate_token( token )

        if len( result.split(".") ) == 3:
            print("Everything went fine in the validate_token_test")  
        else:
            print("Something went wrong in the validate_token_test, the error was: " + result)    
        

    def send_password_reset_email_test(self):
        result = self.send_password_reset_email("test@example.com")

        if result == "success":
            print("send_password_reset_email was a success")
        else:
            print("send_password_reset_email was not a success, the error is: " + result)
        

    def reset_password_test(self):
        token = self.sign_in("test@example.com", "longpassword")

        result = self.reset_password( token , "longpassword", "longpassword")
            
        error_messages = ["ERROR-INVALID_TOKEN", "passwords-no-match"] 
            
        if result in error_messages:
            print("Something went wrong in the reset_password_test, the error is " + result)
        elif result == "success":
            print("Everything went fine in the reset_password_test")
        

    def run_tests(self):
        self.sign_up_test()
        self.sign_in_test()
        self.validate_token_test()
        self.send_password_reset_email_test()
        self.reset_password_test()

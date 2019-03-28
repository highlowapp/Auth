# import the Flask class from the flask module
from flask import Flask, render_template, redirect, url_for, request
from Auth import Auth
host = "localhost"
username = "root"
password = "password"
database = "database"
# create the application object
app = Flask(__name__)
sign_up = Auth("auth_server_name", host, username, password, database)
# use decorators to link the function to a url

@app.route('/')
def home():
    return render_template('home.html')  # return a string

@app.route('/signin', methods=['GET', 'POST'])
def signin():

  error = None
  if request.method == 'POST':
    if request.form['email'] != 'admin@gmail.com' or request.form['password'] != 'admin':
        error = 'Invalid Credentials. Please try again.'
    else:
        return redirect(url_for('HighLowInput'))
  return render_template('signin.html', error=error)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
  error = None
  #We can add any needed errors
  if request.method == 'POST':
    if request.form['confirmpassword'] != request.form['password']:
        error = 'Your password doesn\'t match. Please try again.'
    else:
      return redirect(url_for('HighLowInput'))
      sign_up.sign_up(firstname=request.form['firstname'], lastname=request.form['lastname'], email=request.form['email'], password=request.form['password'], confirmpassword=request.form['confirmpassword'])

  return render_template('signup.html', error=error)  # render a template
 

@app.route('/resetPassword', methods=['GET', 'POST'])
def resetPassword():
  return render_template('resetPassword.html', methods=['GET', 'POST'])  # render a template

@app.route('/input', methods=['GET', 'POST'])
def HighLowInput():
  error = None
  if request.method == 'POST':
    return redirect(url_for('delay'))
    #return 'High: {} <br> Low: {}'.format(request.form['high'], request.form['low'])
  return render_template('HighLow_Input.html', error=error)


@app.route('/display', methods=['GET', 'POST'])
def display():
  if request.method == 'POST':
    return 'High: {} <br> Low: {}'.format(request.form['high'], request.form['low']) 
#start the server with the 'run()' method
if __name__ == '__main__':
  app.run(debug=True)

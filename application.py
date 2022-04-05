import os
import csv
from cs50 import SQL
from flask import Flask, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import collections, functools, operator
import json

from helpers import login_required

app = Flask(__name__)

app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = SQL("sqlite:///budget.db")

@app.route('/')
@login_required
def index():

    groups = db.execute("SELECT * FROM groups WHERE id IN (SELECT group_id FROM group_users WHERE user_id = ?)", session["user_id"])
    rows = len(groups)
    return render_template("index.html", groups=groups, rows=rows)

@app.route('/createGroup', methods=["GET", "POST"])
@login_required
def create_group(): 
    if request.method == "POST":
        groupname = request.form.get("groupname")
        totalbudget = request.form.get("totalbudget")
        groupdescription = request.form.get("groupdescription")
        groupList = db.execute("SELECT group_name FROM groups")

        if not groupname:
            message = "Please input Group name"
            return render_template("createGroup.html", message=message)

        if any(dic['group_name'] == groupname for dic in groupList):
            message = "Groupname Taken"
            return render_template("createGroup.html", message=message)    

        if not totalbudget:
            message = "Please input Total Budget"
            return render_template("createGroup.html", message=message)

        if not groupdescription:
            message = "Please input Group Description"
            return render_template("createGroup.html", message=message)        

        db.execute("INSERT INTO groups (group_name, total_budget, group_description, admin1) VALUES (?, ?, ?, ?)", groupname, totalbudget, groupdescription, session["user_id"]) 
        groupid = db.execute("SELECT id FROM groups ORDER BY id DESC")
        db.execute("INSERT INTO group_users (group_id, user_id) VALUES (?, ?)", groupid[0]["id"], session["user_id"])   
        return redirect("/")

    else:    
        return render_template("createGroup.html") 

@app.route('/createBudget/<int:groupid>', methods=["GET", "POST"])
@login_required
def create_budget(groupid): 
    if request.method == "POST":
        item = request.form.get("item")
        price = request.form.get("price")

        if not item:
            message = json.dumps({"message": "Please input item"})
            session['message'] = message
            return redirect(url_for('create_budget', groupid=groupid, message=message))

        if not price:
            message = json.dumps({"message": "Please input price"})
            session['message'] = message
            return redirect(url_for('create_budget', groupid=groupid, message=message)) 

        get_total_budget = db.execute("SELECT total_budget FROM groups WHERE id = ?", groupid) 

        total_budget = get_total_budget[0]["total_budget"]

        get_prices = db.execute("SELECT prices FROM budget WHERE group_id = ?", groupid) 

        result = dict(functools.reduce(operator.add,
            map(collections.Counter, get_prices)))

        sum_of_prices = int(result["prices"])  + int(price)  

        if total_budget >= sum_of_prices: 
            db.execute("INSERT INTO budget (group_id, goods, prices) VALUES (?, ?, ?)", groupid, item, price) 
            message = json.dumps({"message": "Item added"})
            session['message'] = message
            return redirect(url_for('create_budget', groupid=groupid, message=message))  
        else:
            message = json.dumps({"message": "You have exceeded the group budget"})
            session['message'] = message
            return redirect(url_for('create_budget', groupid=groupid, message=message)) 

    else:
        budgets = db.execute("SELECT goods, prices FROM budget WHERE group_id = ?", groupid)
        groupname = db.execute("SELECT group_name FROM groups WHERE id = ?", groupid)
        rows = len(budgets)
        message = 'message'
        if message in session:
            message = session['message']
            return render_template("createBudget.html", groupid=groupid, groupname=groupname[0]["group_name"], budgets=budgets, rows=rows, message=json.loads(message)) 
        else:    
            message = json.dumps({"message": "Nothing"})
            session['message'] = message
            return render_template("createBudget.html", groupid=groupid, groupname=groupname[0]["group_name"], budgets=budgets, rows=rows, message=json.loads(message))        


@app.route('/dashboard/<int:groupid>', methods=["GET", "POST"])
@login_required
def dashboard(groupid): 
    
    teamMembers = db.execute("SELECT * FROM users WHERE id IN (SELECT user_id FROM group_users WHERE group_id = ?)", groupid)
    group =  db.execute("SELECT * FROM groups WHERE id = ?", groupid)
    total_budget = int(group[0]["total_budget"])
    prices = db.execute("SELECT prices FROM budget_activity WHERE group_id = ? AND removed = ?", groupid, 0)
    result = dict(functools.reduce(operator.add,
        map(collections.Counter, prices)))

    total_spent = int(result["prices"])
    budget_left = total_budget - total_spent
    # history = db.execute("SELECT * FROM history WHERE budget_activity_id IN (SELECT id FROM budget_activity WHERE group_id = ?)", groupid)
    history = db.execute("SELECT goods, header_id, user_id, added, edited, deleted FROM budget_activity JOIN history ON budget_activity.id = history.budget_activity_id WHERE budget.group_id = ?", groupid)
    for x in history:
        goods_header = db.execute("SELECT headers FROM folders WHERE id = ?", x["header_id"])
        theuser = db.execute("SELECT username FROM users WHERE id = ?", x["user_id"])
        x["header"] = goods_header
        x["username"] = theuser

    message = 'message'
    if message in session:
        message = session['message']
        return render_template("dashboard.html", teamMembers=teamMembers, total_budget=total_budget, total_spent=total_spent, budget_left=budget_left, history=history, group=group, groupid=groupid, message=json.loads(message))
    else:    
        message = json.dumps({"message": "Nothing"})
        session['message'] = message    

        return render_template("dashboard.html", teamMembers=teamMembers, total_budget=total_budget, total_spent=total_spent, budget_left=budget_left, history=history, group=group, groupid=groupid, message=json.loads(message))     
    pass  

@app.route('/groupSettings/<int:groupid>', methods=["GET", "POST"])
@login_required
def group_settings(groupid):   
    get_group = db.execute("SELECT * FROM groups WHERE id = ?", groupid)
    if request.method == "POST":
        if request.form['username'] == 'Add User':
            username = request.form.get("username")

            if not username:
                message = json.dumps({"message": "Please input Username"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))

            usernameList = db.execute("SELECT * FROM users WHERE username = ?", username)
            if len(usernameList) != 1:
                message = json.dumps({"message": "Username doesn't exists"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))
            else:
                db.execute("INSERT INTO group_users (groupid, user_id) VALUES (?, ?)", groupid, usernameList[0]["id"]) 
                message = json.dumps({"message": "Nothing"})
                session['message'] = message   
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))
        elif request.form['admin2'] == 'Add Admin':    
            username = request.form.get("admin2")

            if not username:
                message = json.dumps({"message": "Please input Username"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))

            usernameList = db.execute("SELECT username FROM users JOIN group_users ON users.id = group_users.user_id WHERE users.username = ? AND group_users.group_id = ?", username, groupid)
            if len(usernameList) != 1:
                message = json.dumps({"message": "User doesn't belong to this group yet"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))
            else:
                userid = db.execute("SELECT id FROM users WHERE username = ?", username)
                db.execute("UPDATE groups SET admin2 = ? WHERE id = ?", userid[0]["id"], groupid)  
                message = json.dumps({"message": "Nothing"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))  

        elif request.form['editBudget'] == 'Edit Budget':         

            newbudget = request.form.get("editBudget")

            get_prices = db.execute("SELECT prices FROM budget WHERE group_id = ?", groupid) 

            result = dict(functools.reduce(operator.add,
                map(collections.Counter, get_prices)))

            sum_of_prices = int(result["prices"])
            if not newbudget:
                message = json.dumps({"message": "Please input New Budget"})
                session['message'] = message
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message)) 

            if newbudget < sum_of_prices: 
                message = json.dumps({"message": "Total price of planned budget is greater than new budget, please edit planned budget or input a new higher total budget"})
                session['message'] = message   
                return redirect(url_for('/dashboard'+str(groupid), groupid=groupid, message=message))
            else:
                db.execute("UPDATE groups SET total_budget = ? WHERE id = ?", newbudget, groupid)    
    else:
        message = json.dumps({"message": "Nothing"})
        session['message'] = message
        return redirect(url_for('/dashboard'+str(groupid), message=message)
    pass          

@app.route('/planning/<int:groupid>/<str:folder>', methods=["GET", "POST"])
@login_required
def planning(groupid, folder): 
    if request.method == "POST":
        folderName = request.form.get("create")
        if not folderName:
            message = json.dumps({"message": "Please input Folder Name"})
            session['message'] = message
            return redirect(url_for('planning/'+str(groupid)+'/'+folder, groupid=groupid, message=message))    

        folderList = db.execute("SELECT headers from folders WHERE group_id = ?", groupid)   
        if any(dic['headers'] == folderName for dic in folderList):
            message = json.dumps({"message": "Folder already exists"})
            session['message'] = message
            return redirect(url_for('planning/'+str(groupid)+'/'+folder, groupid=groupid, message=message))

        db.execute("INSERT INTO folders (headers, group_id) VALUES (?, ?)", folderName, groupid)    
        message = json.dumps({"message": "Nothing"})
        session['message'] = message
        return redirect(url_for('planning/'+str(groupid)+'/'+folder, groupid=groupid, message=message))
        
    else:            
        if folder == "combination":
            plans = db.execute("SELECT * FROM budget_activity WHERE group_id = ? AND removed = ?", groupid, 0)  
            result = dict(functools.reduce(operator.add,
                map(collections.Counter, plans["prices"])))

            sum_of_prices = int(result["prices"])
            for x in plans:
                theuser = db.execute("SELECT username FROM users WHERE id = ?", x["user_id"])
                goods_header = db.execute("SELECT headers FROM folders WHERE id = ?", x["header_id"])
                x["header"] = goods_header
                x["username"] = theuser
            message = 'message'
            if message in session:
                message = session['message']
                return render_template("planning.html", groupid=groupid, plans=plans, totalPrice=sum_of_prices, message=json.loads(message))
            else:    
                message = json.dumps({"message": "Nothing"})
                session['message'] = message    
                return render_template("planning.html", groupid=groupid, plans=plans, totalPrice=sum_of_prices, message=json.loads(message))
        else:    
            plans = db.execute("SELECT * FROM budget_activity WHERE group_id = ? AND removed = ? AND header_id IN (SELECT id FROM folders WHERE headers = ?)", groupid, 0, folder)  
            result = dict(functools.reduce(operator.add,
                map(collections.Counter, plans["prices"])))

            sum_of_prices = int(result["prices"])
            for x in plans:
                theuser = db.execute("SELECT username FROM users WHERE id = ?", x["user_id"])
                x["username"] = theuser

            message = 'message'
            if message in session:
                message = session['message']
                return render_template("planning.html", groupid=groupid, plans=plans, totalPrice=sum_of_prices, folder=folder, message=json.loads(message))
            else:    
                message = json.dumps({"message": "Nothing"})
                session['message'] = message    
                return render_template("planning.html", groupid=groupid, plans=plans, totalPrice=sum_of_prices, folder=folder, message=json.loads(message))
    pass   

@app.route('/action/<int:groupid>', methods=["GET", "POST"])
@login_required
def handleplanning(groupid): 
    if request.method == "POST":
        if "Add" in request.form:
            the_item = request.form.get("goods")
            price = request.form.get("price")
            foldername = request.form.get("foldername")
            if not the_item:
                message = json.dumps({"message": "Please input item name"})
                session['message'] = message
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))
            if not price:    
                message = json.dumps({"message": "Please input price"})
                session['message'] = message
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))

            header = db.execute("SELECT id FROM folders WHERE headers = ? and group_id = ?", foldername, groupid)    
            headerid = header[0]["id"]

            db.execute("INSERT INTO budget_activity (goods, header_id, group_id, user_id, prices) VALUES (?, ?, ?, ?, ?)", the_item, headerid, groupid, session["user_id"], price)  
            budegtActivityId = db.lastInsertRowId
            print(budegtActivityId)  
            db.execute("INSERT INTO history (budget_activity_id, added) VALUES (?, ?)", budegtActivityId, 1)

        elif "Edit" in request.form:
            the_item = request.form.get("goods")
            price = request.form.get("price")
            foldername = request.form.get("foldername")
            budegtActivityId = request.form.get("budegtActivityId")
            if not the_item:
                message = json.dumps({"message": "Please input item name"})
                session['message'] = message
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))
            if not price: 
                message = json.dumps({"message": "Please input price"})
                session['message'] = message   
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))

            db.execute("UPDATE budget_activity SET goods = ?, prices = ? WHERE id = ?", the_item, price budegtActivityId)    

            print(budegtActivityId)  
            db.execute("INSERT INTO history (budget_activity_id, edited) VALUES (?, ?)", budegtActivityId, 1)   

        elif "Delete" in request.form:
            the_item = request.form.get("goods")
            price = request.form.get("price")
            foldername = request.form.get("foldername")
            budegtActivityId = request.form.get("budegtActivityId")
            if not the_item:
                message = json.dumps({"message": "Please input item name"})
                session['message'] = message
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))
            if not price:   
                message = json.dumps({"message": "Please input price"})
                session['message'] = message 
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))

            db.execute("UPDATE budget_activity SET removed = ? WHERE id = ?", 1, budegtActivityId)    

            print(budegtActivityId)  
            db.execute("INSERT INTO history (budget_activity_id, deleted) VALUES (?, ?)", budegtActivityId, 1)     

        elif "Comment" in request.form:
            the_comment = request.form.get("comment")
            if not the_comment:
                message = json.dumps({"message": "Please input comment"})
                session['message'] = message
                return redirect(url_for('planning/'+str(groupid)+'/'+foldername, groupid=groupid, message=message))

            db.execute("INSERT INTO comments (group_id, user_id, comment) VALUES (?, ?, ?)", groupid, session["user_id"], the_comment)                          

    pass        

@app.route('/profileSettings/<int:groupid>/<str:folder>', methods=["GET", "POST"])
@login_required
def profileSettings(groupid):      
    if request.method == "POST":  
        username = request.form.get("username")  
        if not username:
            message = "Please input Username"
            return render_template("register.html", message=message)

        if any(dic['username'] == username for dic in usernameList):
            message = "Username Taken"
            return render_template("register.html", message=message) 

        db.execute("UPDATE users SET username = ? WHERE id = ?", username, session["user_id"])

    else:
        groups = db.execute("SELECT * FROM groups WHERE id IN (SELECT group_id FROM group_users WHERE user_id = ?)", session["user_id"])
        rows = len(groups)
        return render_template("profileSettings.html", groups=groups, rows=rows)    
pass        

@app.route('/joinGroup/<int:groupid>', methods=["GET", "POST"])
@login_required
def join_group(groupid):
    if request.method == "POST":
        db.execute("INSERT INTO group_users (group_id, user_id) VALUES (?, ?)", groupid, session["user_id"])     

    else:
        return redirect(url_for('dasboard', groupid=groupid))    
    pass 

# @app.route('/addMember/<int:groupid>', methods=["GET", "POST"])
# @login_required   
# def add_member(groupid):
#     if request.method == "POST":
#         username = request.form.get("username")

#         if not username:
#             message = "Please input Username"
#             return redirect(url_for('add_member', groupid=groupid, message=message))

#         usernameList = db.execute("SELECT * FROM users WHERE username = ?", username)
#         if len(usernameList) != 1:
#             return redirect(url_for('add_member', groupid=groupid, message=message))

#     else:
#         teamMembers = groups = db.execute("SELECT * FROM users WHERE id IN (SELECT user_id FROM group_users WHERE group_id = ?)", groupid)        
#     pass    


@app.route('/register', methods=["GET", "POST"])  
def register():
    if request.method == "POST":
        firstname = request.form.get("firstname")
        lastname = request.form.get("lastname")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        password_confirmation = request.form.get("confirmation")
        
        usernameList = db.execute("SELECT username FROM users")

        if not firstname:
            message = "Please input Firstname"
            return render_template("register.html", message=message)

        if not lastname:
            message = "Please input Lastname"
            return render_template("register.html", message=message)

        if not username:
            message = "Please input Username"
            return render_template("register.html", message=message)

        if any(dic['username'] == username for dic in usernameList):
            message = "Username Taken"
            return render_template("register.html", message=message)    

        if not email:
            message = "Please input Email"
            return render_template("register.html", message=message)

        if not password or password != password_confirmation:
            message = "Ensure Passwords match"
            return render_template("register.html", message=message)  

        hashPassword = generate_password_hash(password)              

        db.execute("INSERT INTO users (first_name, last_name, username, email, password) VALUES (?, ?, ?, ?, ?)", firstname, lastname, username, email, hashPassword)        

        return redirect("/")
        
    else:    
        return render_template("register.html")  

@app.route('/login', methods=["GET", "POST"])
def login():
    # Forget any user_id
    session.clear()

    if request.method == "POST":

        username = request.form.get("username")
 
        password = request.form.get("password")

        if not username:
            message = "Please input Username"
            return render_template("login.html", message=message)

        elif not password:
            message = "Ensure Passwords match"
            return render_template("login.html", message=message)

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)   

        if len(rows) != 1 or not check_password_hash(rows[0]["password"], password):
            message = "Username/Password incorrect"
            return render_template("login.html", message=message)

        session["user_id"] = rows[0]["id"]

        return redirect("/")   

    else:
        return render_template("login.html")   

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")        
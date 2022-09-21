from selenium.common.exceptions import NoSuchElementException
import json
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.firefox.options import Options as ffOptions
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import Select
import datetime as d
from datetime import datetime
import time
import csv
import mysql.connector
import requests
import traceback
import os
from spotbanc_api import spotbanc_api
import getpass
import sys
import re
import pickle
import shutil
from multiprocessing import Process

#TODO
#3) Cross check customer details
#4) Test progress data as script runs

global log_file
log_file = "logs/get-customers.log"
def print_mod(text, end='\n'):
	global log_file
	with open(log_file, "a") as f:
		print(text, file=f, end=end)
	print(text, end=end)

#Get user input as either yes/no
def get_yes_no_input(message):
        while True:
                response = input(message + " (y/n)").lower()
                if response in ['y', 'yes']:
                        return True
                elif response in ['n', 'no']:
                        return False
                else:

                     	print_mod("Please enter either y/yes or n/no")



def get_progress():
        if(not get_yes_no_input("Continue from saved progress")):
                with open("config.json", 'w') as f:
                        config["progress"] = {"get_customers": False, "get_accounts": 0, "get_transactions": 0}
                        json.dump(config, f, indent=4)
                #Clear database before starting
                mydb, cursor = connect_to_db()
                clear_table("suspended_jscript", cursor)
                clear_table("transaction", cursor)
                clear_table("account", cursor)
                clear_table("customer", cursor)
                mydb.commit()
                disconnect_from_db(mydb, cursor)

global config
with open("config.json", 'r') as f:
	config=json.load(f)
global config_common
config_common=config['common']

config_env=""

def init_environment():
	global base_url
	global config_env
	config_env = config["environment"]["staging"]
	print_mod("-----------------------------------------")
	print_mod(datetime.today())
	#TODO modified init_environment
	#Production/Staging?
	print_mod("Running on STAGING ENVIRONEMNT as default... ")
	if(get_yes_no_input("Run on PRODUCTION ENVIRONMENT?")):
		print_mod("Running on PRODUCTION ENVIRONMENT")
		config_env = config["environment"]["production"]
	base_url = config_env["url"]
	global spotbanc
	spotbanc = spotbanc_api(base_url + config_env['api'], '200', 'app')

def connect_to_db():
        global config_env

        db_config = config_env["database"]
        host = db_config["host"]
        user = db_config["user"]
        password = db_config["password"]
        database = db_config["database"]
        mydb = mysql.connector.connect(
                host=host,
                user=user,
                password=password,
                database=database
        )
        cursor = mydb.cursor()
        return mydb, cursor

def clear_table(table, cursor):
	clear_table = "DELETE FROM " + table
	cursor.execute(clear_table)

def disconnect_from_db(db, cursor):
	cursor.close()
	db.close()

def get_page(url, check_current_page, driver):
	print_mod("Getting page " + url)
	max_wait = 80
	if(check_current_page and driver.current_url == url):
		return
	else:
		driver.get(url)
		time.sleep(5)
		attempts = config["common"]["no_of_refreshes"]
		for i in range(attempts):
			wait = WebDriverWait(driver, max_wait)
			print_mod("Attempt " + str(i) + "/" + str(attempts) + "... ", end='')
			try:
				wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
				print_mod("SUCCESS")
				return
			except:
				print_mod("FAILED. Reloading Page")
				driver.refresh()

				print_mod("Page refreshed")
				max_wait = 10
	raise ValueError("Couldn't load page. Returning")

def get_account_ledger(customer_id, customer_code):
	transactions = []
	wait = WebDriverWait(driver, 60)
	try:
		wait.until(EC.presence_of_element_located((By.ID, 'j_idt62:fromDate_input')))
	except:
		print_mod("Page not loading. Returning")
		return transactions
	start = driver.find_element(By.ID, 'j_idt62:fromDate_input')
	end = driver.find_element(By.ID, 'j_idt62:toDate_input')
	end.clear()
	start.clear()
	start.send_keys("23/05/2020")
	end.send_keys((datetime.today() + d.timedelta(days=1*365)).strftime("%d/%m/%Y"))
	Select(driver.find_element(By.ID, 'j_idt62:customer_search')).select_by_value(customer_id)
	time.sleep(2)
	accounts = driver.find_element(By.ID, 'j_idt62:wallet-accounts-list').find_elements(By.TAG_NAME, 'option')
	account_numbers = {}
	for account in accounts:
		account_number = account.text.replace('[', '').replace(']','').split()
		#TODO removed customer_code from account_numbers. Account code = Account Number + Currency
		account_numbers[account.get_attribute('value')] = account_number[0] + account_number[1][0:3]
	for account_number in account_numbers:
		Select(driver.find_element(By.ID, 'j_idt62:wallet-accounts-list')).select_by_value(account_number)
		driver.find_element(By.XPATH, "//input[@name='j_idt62:j_idt84']").click()
		table_id = 'tbl'
		time.sleep(3)
		wait.until(EC.presence_of_element_located((By.ID, table_id)))
		while True:
			table = driver.find_element(By.ID, table_id)
			headers = table.find_element(By.TAG_NAME, 'thead').find_elements(By.TAG_NAME, 'th')
			rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
			for row in rows:
				transaction = {"Last entry": datetime.today().strftime("%Y-%m-%d")}
				data = row.find_elements(By.TAG_NAME, 'td')
				#No transactions on this page
				if(len(data) == 1):
					break
				for i, header in enumerate(headers):
					transaction[header.text] = data[i].text
				transaction["Account Code"] = account_numbers[account_number]
				transaction["Customer Code"] = customer_id
				transaction['Last entry'] = datetime.now().strftime("%Y-%m-%d")
				transactions.append(transaction)
			#Go to next page
			has_next_page,next_button = next_page('tbl_next')
			if(has_next_page):
				next_button.click()
			else:
				print_mod("No next page")
				break
	return transactions

def sleep(n):
	for i in range(n):
		time.sleep(1)

def get_transactions_worker(customers_id, index, workers, driver):
	#Open up ledger page again.
	wait = WebDriverWait(driver, 60)
	get_page(base_url + "manager-area/wallet_statement_manager."+config_common["extension"]+"?search-type=REGISTERED_CUSTOMER", True, driver)
	try:
		wait.until(EC.presence_of_element_located((By.ID, 'j_idt62:fromDate_input')))
	except:
		print_mod("Page not loading. Returning")
		return
	#Set start and end date
	start = driver.find_element(By.ID, 'j_idt62:fromDate_input')
	end = driver.find_element(By.ID, 'j_idt62:toDate_input')
	end.clear()
	start.clear()

	start.send_keys("16/09/2022")
	end.send_keys((datetime.today() + d.timedelta(days=1*365)).strftime("%d/%m/%Y"))
	j= 0
	#for each customer in that this worker with work on
	while(j*workers + index < len(customers_id)):
		#Scrape their data and save it to database
		customer_id = customers_id[j*workers + index]
		transactions = []
		print_mod(str(j*workers + index) + "/" + str(len(customers_id)) + " customers")
		Select(driver.find_element(By.ID, 'j_idt62:customer_search')).select_by_value(customer_id)
		time.sleep(1)
		wait.until(EC.presence_of_element_located((By.ID, 'j_idt62:wallet-accounts-list')))
		accounts = driver.find_element(By.ID, 'j_idt62:wallet-accounts-list').find_elements(By.TAG_NAME, 'option')
		account_numbers = {}
		for account in accounts:
			account_number = account.text.replace('[', '').replace(']','').split()
			account_numbers[account.get_attribute('value')] = account_number[0] + account_number[1][0:3]

		for account_number in account_numbers:
			print_mod("   Account Number " + str(account_number))
			Select(driver.find_element(By.ID, 'j_idt62:wallet-accounts-list')).select_by_value(account_number)
			driver.find_element(By.XPATH, "//input[@name='j_idt62:j_idt84']").click()
			#Special case for customer Smile Money Limited
			if(customer_id=="ae96be7f-7d9a-4209-a476-222fdfc35a09"):
				sleep(60*5)
			else:
				sleep(1)
			table_id = 'tbl'
			#Wait for next button to appear
			wait.until(EC.presence_of_element_located((By.ID, 'tbl_next')))
			while True:
				table = driver.find_element(By.ID, table_id)
				headers = table.find_element(By.TAG_NAME, 'thead').find_elements(By.TAG_NAME, 'th')
				rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
				for row in rows:
					transaction = {"Last entry": datetime.today().strftime("%Y-%m-%d")}
					data = row.find_elements(By.TAG_NAME, 'td')
					#No transactions on this page
					if(len(data) == 1):
						break
					for i, header in enumerate(headers):
						transaction[header.text] = data[i].text
					transaction["Account Code"] = account_numbers[account_number]
					transaction["Customer Code"] = customer_id
					transaction['Last entry'] = datetime.now().strftime("%Y-%m-%d")
					transactions.append(transaction)
				#Go to next page
				has_next_page,next_button = next_page('tbl_next')
				if(has_next_page):
					next_button.click()
				else:
					break
		mydb, cursor = connect_to_db()
		for transaction in transactions:
			add_transaction_to_db(transaction, cursor, "transaction_tmp2")
			mydb.commit()
		disconnect_from_db(mydb, cursor)
		j = j + 1

def get_transactions(driver, worker, workers):
	mydb, cursor = connect_to_db()
	#TODO Move delete from transaction_tmp somewhere else?
	if(worker == 0):
		cursor.execute("DELETE FROM transaction_tmp2")
		cursor.execute("DELETE FROM customer_id_from_trans_page")
		mydb.commit()
		get_page(base_url + "manager-area/wallet_statement_manager."+config_common["extension"]+"?search-type=REGISTERED_CUSTOMER", True, driver)
		wait = WebDriverWait(driver, 60)
		try:
			wait.until(EC.presence_of_element_located((By.ID, 'j_idt62:fromDate_input')))
		except:
			print_mod("Page not loading. Returning")
			return

		customers = driver.find_element(By.ID, 'j_idt62:customer_search').find_elements(By.TAG_NAME, 'option')
		customers_id = []
		for c in customers:
			customers_id.append(c.get_attribute("value"))
			cursor.execute("INSERT INTO customer_id_from_trans_page (customer_id) VALUES (%s)", [c.get_attribute("value")])
		mydb.commit()
	cursor.execute("SELECT * FROM customer_id_from_trans_page")
	customers_id = cursor.fetchall()

	#TODO Parallel split up work
	Pros = []
	p = Process(target=get_transactions_worker, args=(customers_id, worker, workers, driver))
	Pros.append(p)
	p.start()
	"""
	for i in range(1, workers):
		driver_parallel = init_driver("Chrome", 2+i)
		p = Process(target=get_transactions_worker, args=(customers_id, i, workers, driver_parallel))	
		Pros.append(p)
		p.start()
		time.sleep(10)
		print("Waiting...")
	"""
	for t in Pros:
		t.join()
	print("Finished getting transactions")

def merge_accounts_and_transactions():
	mydb, cursor = connect_to_db()
	cursor.execute("SELECT customer_code, customer_id FROM customer")
	customers = cursor.fetchall()
	for customer in customers:
		print(customer)
		query = "UPDATE transaction_tmp2 set account_code=concat(account_code,%s) WHERE customer_code=%s"
		values = [customer[0], customer[1]]
		cursor.execute(query,values)
	mydb.commit()
	disconnect_from_db(mydb, cursor)
					
		
		

	

def add_transaction_to_db(transaction, cursor, table):
	amount = transaction["Amount"].split()
	amount[0] = amount[0].replace(',','')
	balance = transaction["Balance"].split(' ')
	balance[0] = balance[0].replace(',','')
	add_transaction_query = "INSERT INTO " + table + " (ref, customer_code, account_code, counter_party, date, amount, cr_or_dr, balance, currency, more_info, fund_depositor, payment_reference, last_entry) VALUES (%s, %s,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
	values = [transaction["REF#"], transaction["Customer Code"], transaction["Account Code"], transaction["Counter Party"], transaction["Date"], amount[0], amount[1],  balance[0], balance[1], transaction["More Info"], transaction["Fund Depositor"], transaction["Payment Reference"], transaction["Last entry"]]
	try:
		cursor.execute(add_transaction_query, values)
	except Exception as e:
		print_mod(e)

def add_account_to_db(account):
	print_mod("Added account to DB")



#TODO ADDED Customer Sign up Date to Database
def add_customer_to_db(customer, cursor):
	cursor.execute("DELETE FROM account WHERE customer_code=%s", [customer['Code']])
	
	add_customer_query = "REPLACE INTO customer (signup_date, customer_id, full_name,status, last_login, customer_code, first_name, last_name, email, phone_number, account_type, dob, address_line1, address_line2, city, state, postcode, employer, annual_salary, currency_salary, last_entry) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
	add_account_query = """INSERT INTO account (account_code, date, currency, balance, status, account_name, account_number, customer_code, last_entry) VALUES (%s,%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE account_code=%s"""
	try:
		dob = customer['Date Of Birth']
	except:
		print_mod("Couldn't find DOB")
		return
	try:
		dob = datetime.strptime(dob, "%d/%m/%Y").strftime("%Y-%m-%d")
	except:
		dob=None
		pass
	try:
		values = [customer['Signup Date'], customer['Id'], customer['Full Name'], customer['Status'], customer['Last Login'], customer['Code'], customer['First Name'], customer['Last Name'], customer['Sender Email address'], customer['Phone Number'], customer['Account Type'], dob, customer['Address Line 1'], customer['Address Line 2'],
customer['City'], customer['State'], customer['Area/Post code'], customer['Employer'], customer['Annual Salary'], customer['Currency Salary'], customer['Last entry']]
	except Exception as e:
		print_mod(str(traceback.format_exc()))
		print_mod("Couldn't add customer to DB")
		return
	cursor.execute(add_customer_query, values)
	for account in customer['accounts']:
		cursor.execute("DELETE FROM transaction where account_code=%s",[account['Account Code'] + customer['Code']])
		values = [account['Account Code'] + customer['Code'], account['Date'], account['Balance'][:3], account['Balance'][3:], account['Status'], account['Account Name'], account['Account Number'], customer['Code'],  customer['Last entry'], account['Account Code'] + customer['Code']]
		cursor.execute(add_account_query, values)

def get_accounts_no_owner():
	with open("all_accounts.json", 'r') as f:
		accounts = json.load(f)
	no_owner = []
	multiple_owners = []
	mydb, cursor = connect_to_db()
	query = "SELECT * FROM account WHERE (account_number=%s AND account_name=%s AND currency=%s)"
	for account in accounts:
		values = [account["Find beneficiary by their Account Number"], account["Account Holder Name"], account["Balance"][-3:]]
		cursor.execute(query, values)
		result = cursor.fetchall()
		if not result:
			no_owner.append(account)
		elif (len(result) > 1):
			multiple_owners.append(account)
	no_owner.insert(0, {"number of accounts" : len(no_owner)})
	multiple_owners.insert(0, {"number of accounts" : len(multiple_owners)})
	with open("accounts_no_owners.json", 'w') as f:
		json.dump(no_owner, f)
	with open("accounts_multiple_owners.json", 'w') as f:
		json.dump(multiple_owners, f)
	disconnect_from_db(mydb, cursor)

#TODO added function to init driver in parallel
def init_driver_parallel(browser, index):
	driver = init_driver(browser, index)
	shutil.rmtree(dest + str(index)+"/Profile3")
	print("Done")
	shutil.copytree(dest+"0/Profile3", dest + str(index)+"/Profile3")

def init_driver(browser, index):
        PATH = config["driver"]["path"]
        config_driver = config["driver"][browser]
        options = Options()
        print(PATH + "chromedriver")
        if(browser == "Chrome"):
                options = Options()
        elif(browser == "Firefox"):
	        options = ffOptions()
        for option in config_driver:
                options.add_argument(option)
        if(browser == "Chrome"):
                dest = config["common"]["path"] + "/selenium_profiles/selenium"
	
                user_dir = "--user-data-dir="+ dest + str(index)
                options.add_argument(user_dir)
                driver = webdriver.Chrome(PATH + "chromedriver", options=options)
                if index!=0:
                         close_driver(driver)
			#TODO copy profile to other directory
			#Create directory and point to the profile
                         shutil.rmtree(dest + str(index)+"/Default")
                         shutil.copytree(dest+"0/Default", dest + str(index)+"/Default")
                         driver = webdriver.Chrome(PATH + "chromedriver", options=options)
        elif (browser == "Firefox"):
		#TODO Firefox profile
                driver = webdriver.Firefox(options=options)
        driver.maximize_window()
        driver.set_window_position(0,0)
        driver.set_window_size(1920, 1080)
        return driver


def close_driver(driver):
	print_mod("Closing Driver... ", end='')
	try:
		driver.close()
		driver.quit()
		print_mod("SUCCESS")
	except:
		print_mod("FAILED.")


def is_logged_in():
	try:
		driver.find_element(By.ID, 'loginForm:agentCommandButton')
		return False;
	except NoSuchElementException:
		return True;

def login():
	print_mod("Logging In")
	try:
		#TODO Email and Password are inputs
		email = input("Enter Email: ")
		password = getpass.getpass()
		spotbanc.login(email, password)
		#Log into API first to see if credentials correct
		if not spotbanc.is_logged_in():
			return True
		get_page(base_url, False, driver)
		#Email, password and submit
		driver.find_element(By.ID,'loginForm:email').send_keys(email)
		driver.find_element(By.ID,'loginForm:password').send_keys(password)
		driver.find_element(By.ID,'loginForm:agentCommandButton').click()
		time.sleep(4)
		try:
			warning = driver.find_element(By.XPATH, "//div[@class='notification notification--warning notification--login']").find_element(By.TAG_NAME, 'p')
			print_mod(warning.text)
			return False
		except:
			pass
		get_page(base_url + "manager-area/home."+ config_common["extension"], False, driver)
		print_mod("Successfully Logged in")
		#TODO added pickle
		pickle.dump(driver.get_cookies(), open("cookies.pkl", 'wb'))
		return True
	except Exception as e:
		print_mod(traceback.format_exc())
		print_mod("Something went wrong")

def logout():
	print_mod("Logging out... ", end='')
	try:
		spotbanc.logout()
	except Exception as e:
		print_mod("FAILED. " + e)
	if not is_logged_in():
		print_mod("Not logged in")
		return
	logout_xpath = 'j_idt28:j_idt32'
	try:
		driver.find_element(By.ID, logout_xpath).click()
		print_mod("SUCCESS")
	except:
		print_mod("Couldn't find logout button. Reloading page... ")
		get_page(base_url + "manager-area/home."+config_common["extension"], False, driver)
		wait = WebDriverWait(driver, 100)
		wait.until(EC.presence_of_element_located((By.ID, logout_xpath)))
		driver.find_element(By.ID, logout_xpath).click()
		print_mod("SUCCESS")


def get_suspend_javascript(element):
		jscript = element.get_attribute('onclick')
		jscript = jscript.split(',')
		j_exec = jscript[3][1::] + ',' + jscript[4] + ',\'\');'
		j_exec = j_exec.replace("\\", '')
		return j_exec
	
def add_customer_code_to_db(customer, cursor):
	data = [customer['Id'], customer['Signup Date'], customer['Code'], customer['Last Login'], customer['Full Name'], customer['Sender Phone'], customer['Status'], customer['Last entry'], customer['Code']]
	cursor.execute("INSERT INTO customer (customer_id, signup_date, customer_code, last_login, full_name, phone_number, status, last_entry) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE customer_code=%s", data)


def suspend_customers(action="SUSPEND"):
	mydb, cursor = connect_to_db()
	cursor.execute("SELECT customer_code, script FROM suspended_jscript")
	customers = cursor.fetchall()
	get_page(base_url + "manager-area/manage-customers."+config_common["extension"], False, driver)
	for customer in customers:
		script = customer[1]
		if(action == "SUSPEND"):
			script = customer[1].replace('j_idt97\'', 'j_idt95\'')
		driver.execute_script(script)
		time.sleep(3)
	disconnect_from_db(mydb, cursor)

def get_suspended_customer_transactions():
	#Unsuspend
	suspend_customers(action="UNSUSPEND")
	get_page(base_url + "manager-area/wallet_statement_manager."+config_common["extension"]+"?search-type=REGISTERED_CUSTOMER", True, driver)
	mydb, cursor = connect_to_db()
	cursor.execute("SELECT customer_id, customer_code FROM customer WHERE status='SUSPENDED'")
	customers = cursor.fetchall()
	for customer in customers:
		print("CUSTOMER: " + customer[1])
		transactions = get_account_ledger(customer[0],customer[1])
		for transaction in transactions:
			print(transaction)
			add_transaction_to_db(transaction, cursor, "transaction_tmp2")
			mydb.commit()
	time.sleep(2)
	disconnect_from_db(mydb, cursor)
	#Suspend again
	suspend_customers()

#TODO added get_signup date finder
def get_signup():
	url = base_url + "manager-area/manage-customers."+config_common["extension"]
	get_page(url, False, driver)
	wait = WebDriverWait(driver, 100)
	table_xpath = 'table'
	mydb, cursor = connect_to_db()
	while True:
		wait.until(EC.presence_of_element_located((By.ID, table_xpath)))
		table = driver.find_element(By.ID, table_xpath)
		rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
		headers = table.find_element(By.TAG_NAME, 'thead').find_elements(By.TAG_NAME, 'th')
		for row in rows:
			row = row.find_elements(By.TAG_NAME, 'td')
			signup_date = row[1].text
			code = row[2].text
			cursor.execute("UPDATE customer SET signup_date=%s WHERE customer_code=%s",[signup_date, code])
			mydb.commit()
		has_next_page, next_button = next_page('table_next')
		if(has_next_page):
			print_mod("Going to next page")
			next_button.click()
		else:
			break
	disconnect_from_db(mydb, cursor)

def get_customers():
	print_mod("Getting Customers... ", end='')
	customers = {}
	suspended = []
	try:
		url = base_url + "manager-area/manage-customers."+config_common["extension"]
		get_page(url, False, driver)
		wait = WebDriverWait(driver, 100)
		table_xpath = 'table'
		mydb, cursor = connect_to_db()
		while True:
			wait.until(EC.presence_of_element_located((By.ID, table_xpath)))
			table = driver.find_element(By.ID, table_xpath)
			rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
			headers = table.find_element(By.TAG_NAME, 'thead').find_elements(By.TAG_NAME, 'th')
			for row in rows:
				customer = {}
				row_all = row.find_elements(By.TAG_NAME, 'td')
				row = row_all[0:7]
				for i, r in enumerate(row):
					customer[headers[i].text]=r.text
				cursor.execute("SELECT customer_id FROM customer_code_to_id WHERE customer_code=%s", [customer['Code']])
				result = cursor.fetchall()
				if not len(result):
					customer['Id'] = spotbanc.get_customer_id_from_code(customer['Code'])
					cursor.execute("INSERT INTO customer_code_to_id (customer_code, customer_id) VALUES (%s, %s)", [customer['Code'], customer['Id']])
					mydb.commit()
				else:
					customer['Id'] = result[0][0]
				customer['Last entry'] = datetime.today().strftime("%Y-%m-%d")
				customers[customer['Code']] = customer

				add_customer_code_to_db(customer, cursor)
				mydb.commit()
				if(customer["Status"] == 'SUSPENDED'):
					suspend_script = get_suspend_javascript(row_all[8].find_element(By.TAG_NAME, 'a'))
					cursor.execute("INSERT INTO suspended_jscript (customer_code, script) VALUES (%s, %s)",[customer['Code'], suspend_script])
					mydb.commit()
					suspended.append(suspend_script)
			#Get next button
			has_next_page, next_button = next_page('table_next')
			if(has_next_page):
				print_mod("Going to next page")
				next_button.click()
			else:
				break
		disconnect_from_db(mydb, cursor)
		with open("config.json", 'w') as f:
			config["progress"]["get_customers"] = True
			json.dump(config, f, indent=4)
	except Exception as e:
		print_mod(traceback.format_exc())
	finally:
		with open("customers.json", "w") as f:
			json.dump(customers, f)

def get_suspended_accounts():
	query = "SELECT * FROM customer WHERE status='SUSPENDED'"
	mydb, cursor = connect_to_db()
	cursor.execute(query)
	suspended = cursor.fetchall()



def get_customer_accounts(code, driver):
	url = base_url + "manager-area/user-profile."+config_common["extension"]+"?code=" + code
	get_page(url, False, driver)
	customer = {"accounts": []}
	accounts = []
	wait = WebDriverWait(driver, 50)
	try:
		table_xpath = 'acct-table'
		print_mod("Waiting for Table")
		try:
			wait.until(EC.presence_of_element_located((By.ID, table_xpath)))
		except:
			get_page(url, False, driver)
			wait.until(EC.presence_of_element_located((By.ID, table_xpath)))
		customer_details = driver.find_element(By.ID, 'transaction4')
		labels = customer_details.find_elements(By.TAG_NAME,'label')
		inputs = customer_details.find_elements(By.TAG_NAME, 'input')
		for i in range(len(labels)):
			label = labels[i].text
			input = inputs[i].get_attribute('value')
			if(label == 'Name'):
				account_type = re.search("\((.*)\)", input)
				name = input.replace(account_type.group(0), '')
				name = name.split()
				try:
					customer['First Name'] = name[0]
				except IndexError:
					customer['First Name'] = ''
				try:
					customer['Last Name'] = name[1]
				except:
					customer['Last Name'] = ''
				try:
					customer['Account Type'] = account_type.group(1)
				except IndexError:
					#If list less than 3, check last entry to see if it is account type
					if(name[len(name) -1] in ["INDIVIDUAL, COMPANY"]):
						customer['Account Type'] = name[len(name) - 1]
					else:
						customer['Account Type'] = ''
			else:
				customer[label] = input

		table = driver.find_element(By.ID, table_xpath)
		tbody = table.find_element(By.TAG_NAME, 'tbody')
		thead = table.find_element(By.TAG_NAME, 'thead')
		#Each account
		rows = tbody.find_elements(By.TAG_NAME, 'tr')
		headers = thead.find_elements(By.TAG_NAME, 'th')
		for row in rows:
			account = {}
			row = row.find_elements(By.TAG_NAME, 'td')[0:5]
			if(row[0].text == "No data available in table"):
				return customer
			for i, r in enumerate(row):
				account[headers[i].text] = r.text
			account["Account Code"] = account["Account Number"] + account["Balance"][0:3]
			account['Last entry'] = datetime.today().strftime("%Y-%m-%d")
			accounts.append(account)
		customer["accounts"] = accounts
		return customer
	except NoSuchElementException as e:
		return customer
	except Exception as e:
		print(e)
		return customer

#Get accounts from Accounting > View Customer Accounts:
def get_all_accounts():
	url = base_url + "manager-area/account_wallet_statement_manager."+ config_common["extension"]+"?walletaccounttype=REGISTERED_CUSTOMER"
	get_page(url, False, driver)
	accounts = []
	time.sleep(10)
	driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/form[2]/div[2]/div/input").click()
	time.sleep(5)
	while True:
		table = driver.find_element(By.ID, 'tbl')
		thead = table.find_element(By.TAG_NAME, 'thead')
		tbody = table.find_element(By.TAG_NAME, 'tbody')
		headers = thead.find_elements(By.TAG_NAME, 'th')
		rows = tbody.find_elements(By.TAG_NAME, 'tr')
		print_mod(len(rows))
		for row in rows:
			account = {}
			row_data = row.find_elements(By.TAG_NAME, 'td')[0:4]
			for i, r in enumerate(row_data):
				print_mod(r.text)
				account[headers[i].text] = r.text
			accounts.append(account)
		#Get Next Button
		has_next_page, next_button = next_page('tbl_next')
		if(has_next_page):
			print_mod("Clicking next page")
			next_button.click()
		else:
			print_mod("Last Page")
			break
	with open("all_accounts.json", 'w') as f:
		json.dump(accounts, f)

#Check if next button on page.
def next_page(button_xpath):
	next_button = driver.find_element(By.ID, button_xpath)
	if("disabled" in next_button.get_attribute("class")):
		return False, None
	else:
		return True, next_button

#Runs get_customer_accounts() for every customer
#TODO validate customers are being updated correctly
#TODO changed get_customer_accounts to include driver
def get_all_customers_accounts(index, workers, driver):
	headers = ["Date", "Balance", "Account Name", "Account Number", "Status", "Customer Code"]
	mydb, cursor = connect_to_db()
	cursor.execute("SELECT customer_code, signup_date, last_login, full_name, phone_number, status, customer_id, last_entry FROM customer")
	customers = cursor.fetchall()
	
	with open('customers.json', 'r') as f:
		c = json.load(f)
	keys_list = list(c)
	progress_start = config["progress"]["get_accounts"]
	#TODO changed to while for parallel
	i = 0
	workers = int(workers)
	index = int(index)
	while(i*workers + index < len(customers)):
		customer_index = i*workers + index
		c = customers[customer_index]
		customer = {"Code" : c[0], "Signup Date" : c[1],"Last Login": c[2], "Full Name": c[3], "Sender Phone": c[4], "Status" : c[5], "Id": c[6], "Last entry": c[7]}
		print_mod(str(customer_index) + ") ",end='')
		print_mod("Getting accounts of " + customer["Code"])
		#TODO changed get_customer_accounts to include driver
		customer_account = get_customer_accounts(customer['Code'], driver)
		for detail in customer_account:
			customer[detail] = customer_account[detail]
		mydb,cursor = connect_to_db()
		add_customer_to_db(customer, cursor)
		mydb.commit()
		disconnect_from_db(mydb, cursor)
		#Start with the one above this one
		#TODO commented out config progress	
		#with open("config.json", 'w') as f:
		#	config["progress"]["get_accounts"] += 1
		#	json.dump(config, f, indent=4)
		i = i + 1
	#Close this driver if it's not the first	
	#if(index  != 0):
		#close_driver(driver)

def get_all_transactions():
	log_file = "get-transactions.log"
	mydb,cursor = connect_to_db()
	cursor.execute("SELECT customer_code FROM customer")
	customers = cursor.fetchall()
	get_page(base_url + "manager-area/wallet_statement_manager."+config_common["extension"]+"?search-type=REGISTERED_CUSTOMER", True, driver)
	transactions_start = config["progress"]["get_transactions"]
	for i in range(transactions_start, len(customers)):
		code = customers[i][0]
		print_mod(str(i) + "/" + str(len(customers)) + ") Getting customer transactions (" + code)
		query = "SELECT customer_id, customer_code, status FROM customer WHERE customer_code='%s'" % (code)
		cursor.execute(query)
		customer_id = cursor.fetchone()
		if(customer_id[1] not in ["PENDING", "SUSPENDED"]):
			c = get_account_ledger(customer_id[0], customer_id[1])
			cursor.execute("DELETE FROM transaction WHERE account_code IN (SELECT account_code FROM account WHERE customer_code='%s')" % (code))
			for transaction in c:
				add_transaction_to_db(transaction, cursor, "transaction")
				mydb.commit()
		with open("config.json", "w") as f:
			config["progress"]["get_transactions"] = i+1
			json.dump(config, f, indent=4)
	print_mod(cursor.rowcount, " record inserted")
	disconnect_from_db(mydb, cursor)

#Def added run_get_signups
def run_get_signups():
	init_environment()
	global driver
	driver = init_driver("Chrome", 0)
	try:
		if not login(email, password):
			raise ValueError("Failed to Login")
		get_signup()
	except:
		print_mod(str(traceback.format_exc()))
	finally:
		logout()
		close_driver(driver)

def get_google(index, driver):
	print("Worker " + str(index))
	try:
		driver.get("https://www.google.com/")
		time.sleep(100)
	except Exception:
		print_mod(str(traceback.format_exc()))	
	close_driver(driver)

def run_get_customers(worker, workers):
	global log_file
	log_file = "logs/get_customers/worker" + str(worker)
	init_environment()
	#TODO removed get_progress
	if(worker == 0):
		get_progress()
	#TODO added index for driver
	global driver
	driver = init_driver("Chrome", 0)
	try:
		if not login():
			raise ValueError("Failed to Login in")

		print_mod("Getting Customers")
		#Only run if set to false
		if worker == 0:
			get_customers()
		print_mod("Getting Customers with accounts")
		#TODO Added how many workers there are
		#Runs this part in parallel
		#-------------------------------------------------------------
		Pros = []
		p = Process(target=get_all_customers_accounts, args=(worker, workers, driver))
		Pros.append(p)
		p.start()
		"""
		for i in range(1, int(workers)):
			driver_parallel = init_driver("Chrome", i)
			p = Process(target=get_all_customers_accounts, args=(i, workers, driver_parallel))
			
			Pros.append(p)
			p.start()
			time.sleep(10)
			print("Waiting...")
		"""
		for t in Pros:
			t.join()
		print("Done")
		
		#-------------------------------------------------------------

	except Exception:
		print_mod(str(traceback.format_exc()))
	finally:
		logout()
		close_driver(driver)


def run_get_transactions(worker, workers):
        global log_file
        log_file = "logs/get_transactions/worker"+str(worker)
        init_environment()
        global driver
	#TODO changed from Firefox to Chrome
        driver = init_driver("Chrome", worker)
        #TODO remove driver domain get
        try:
                if not login():
                        raise ValueError("Failed to Login in")

                print_mod("Getting transactions")
                get_transactions(driver, worker, workers)
		#Unsuspends, gets transactions and then suspends again
                #TODO disabled get_suspended_customers
		#get_suspended_customer_transactions()
		#TODO check that account codes are correctly generated
                print_mod("Updating transaction account codes...")
                #merge_accounts_and_transactions()

        except Exception:
                print_mod(str(traceback.format_exc()))
        finally:
                logout()
                close_driver(driver)


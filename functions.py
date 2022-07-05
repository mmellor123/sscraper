from selenium.common.exceptions import NoSuchElementException
import json
from selenium.webdriver.chrome.options import Options
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



def print_mod(text, end='\n'):
	with open("logs/functions-log", "a") as f:
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

print_mod("-----------------------------------------")
print_mod(datetime.today())
with open("config.json", 'r') as f:
	config = json.load(f)
config_common = config['common']

def connect_to_db():
        db_config = config["database"]
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

def disconnect_from_db(db, cursor):
        cursor.close()
        db.close()

def clear_table(table, cursor):
        clear_table = "DELETE FROM " + table
        cursor.execute(clear_table)

progress = {"get_customers": False, "get_accounts" : 0, "get_transactions" : 0}
if(get_yes_no_input("Continue from saved progress")):
	with open("progress.json", 'r') as f:
		progress = json.load(f)
else:
	#Clear database before starting
	mydb, cursor = connect_to_db()
	clear_table("transaction", cursor)
	clear_table("account", cursor)
	clear_table("customer", cursor)
	mydb.commit()
	disconnect_from_db(mydb, cursor)

#Select either staging or production environment
base_url = config_common["staging_url"]
print_mod("Running on STAGING ENVIRONEMNT as default... ")

if(get_yes_no_input("Run on PRODUCTION ENVIRONMENT?")):
	print_mod("Running on PRODUCTION ENVIRONMENT")
	base_url = config_common["production_url"]
spotbanc = spotbanc_api(base_url + config_common['api'], '200', 'app')


def get_page(url, check_current_page):
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
	wait = WebDriverWait(driver, 50)
	try:
		wait.until(EC.presence_of_element_located((By.XPATH, "//input[@id='j_idt62:fromDate_input']")))
	except:
		print_mod("Page not loading. Returning")
		return transactions
	start = driver.find_element(By.XPATH, "//input[@id='j_idt62:fromDate_input']")
	end = driver.find_element(By.XPATH, "//input[@id='j_idt62:toDate_input']")
	end.clear()
	start.clear()
	start.send_keys("23/05/2020")
	end.send_keys((datetime.today() + d.timedelta(days=1*365)).strftime("%d/%m/%Y"))
	Select(driver.find_element(By.XPATH, "//select[@id='j_idt62:customer_search']")).select_by_value(customer_id)
	time.sleep(2)
	accounts = driver.find_element(By.XPATH, "//select[@id='j_idt62:wallet-accounts-list']").find_elements(By.TAG_NAME, 'option')
	account_numbers = {}
	for account in accounts:
		account_number = account.text.replace('[', '').replace(']','').split()
		account_numbers[account.get_attribute('value')] = account_number[0] + account_number[1][0:3] + customer_code
	for account_number in account_numbers:
		Select(driver.find_element(By.XPATH, "//select[@id='j_idt62:wallet-accounts-list']")).select_by_value(account_number)
		driver.find_element(By.XPATH, "//input[@name='j_idt62:j_idt84']").click()
		while True:
			table = driver.find_element(By.XPATH, "//table[@id='tbl']")
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
				transaction["Customer Code"] = customer_code
				transaction['Last entry'] = datetime.now().strftime("%Y-%m-%d")
				transactions.append(transaction)
			#Go to next page
			has_next_page,next_button = next_page("//a[@id='tbl_next']")
			if(has_next_page):
				next_button.click()
			else:
				print_mod("No next page")
				break
	return transactions

def add_transaction_to_db(transaction, cursor):
	amount = transaction["Amount"].split()
	amount[0] = amount[0].replace(',','')
	balance = transaction["Balance"].split(' ')
	balance[0] = balance[0].replace(',','')
	add_transaction_query = "INSERT INTO transaction (ref, account_code, counter_party, date, amount, cr_or_dr, balance, currency, more_info, fund_depositor, payment_reference, last_entry) VALUES (%s, %s,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
	values = [transaction["REF#"], transaction["Account Code"], transaction["Counter Party"], transaction["Date"], amount[0], amount[1],  balance[0], balance[1], transaction["More Info"], transaction["Fund Depositor"], transaction["Payment Reference"], transaction["Last entry"]]
	try:
		cursor.execute(add_transaction_query, values)
	except Exception as e:
		print_mod(e)

def add_account_to_db(account):
	print_mod("Added account to DB")



def add_customer_to_db(customer, cursor):
	add_customer_query = "INSERT INTO customer (customer_id, full_name,status, last_login, customer_code, first_name, last_name, email, phone_number, account_type, dob, address_line1, address_line2, city, state, postcode, employer, annual_salary, currency_salary, last_entry) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE customer_code=%s"
	add_account_query = """INSERT INTO account (account_code, date, currency, balance, status, account_name, account_number, customer_code, last_entry) VALUES (%s,%s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE account_code=%s"""
	delete_accounts_query = "DELETE FROM account WHERE customer_code='%s'" % (customer['Code'])
	try:
		dob = customer['Date Of Birth']
	except:
		print_mod("Couldn't find DOB")
		return
	try:
		dob = datetime.strptime(dob, "%d/%m/%Y").strftime("%Y-%m-%d")
	except:
		print("FAILED")
		pass
	try:
		values = [customer['Id'], customer['Full Name'], customer['Status'], customer['Last Login'], customer['Code'], customer['First Name'], customer['Last Name'], customer['Sender Email address'], customer['Phone Number'], customer['Account Type'], dob, customer['Address Line 1'], customer['Address Line 2'],
customer['City'], customer['State'], customer['Area/Post code'], customer['Employer'], customer['Annual Salary'], customer['Currency Salary'], customer['Last entry'], customer['Code']]
	except Exception as e:
		print(e)
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


def init_driver():
        PATH = config["common"]["path"]
        config_driver = config["driver"]
        options = Options()
        for option in config_driver["options"]:
                options.add_argument(option)
        if(config_driver["browser"] == "Chrome"):
                driver = webdriver.Chrome(config_driver["path"], options=options)
        driver.maximize_window()
        driver.set_window_position(0,0)
        driver.set_window_size(1920, 1080)
        return driver

def close_driver():
	print_mod("Closing Driver... ", end='')
	try:
		driver.close()
		driver.quit()
		print_mod("SUCCESS")
	except:
		print_mod("FAILED.")


def is_logged_in():
	try:
		driver.find_element(By.XPATH, "//input[@id='loginForm:agentCommandButton']")
		return False;
	except NoSuchElementException:
		return True;

def login():
	print_mod("Logging In")
	try:
		email = input("Enter Email: ")
		password = getpass.getpass()
		spotbanc.login(email, password)
		#Log into API first to see if credentials correct
		if not spotbanc.is_logged_in():
			return True
		get_page(base_url, False)
		#Email, password and submit
		driver.find_element(By.XPATH,"//input[@id='loginForm:email']").send_keys(email)
		driver.find_element(By.XPATH, "//input[@id='loginForm:password']").send_keys(password)
		driver.find_element(By.XPATH, "//input[@id='loginForm:agentCommandButton']").click()
		time.sleep(4)
		try:
			warning = driver.find_element(By.XPATH, "//div[@class='notification notification--warning notification--login']").find_element(By.TAG_NAME, 'p')
			print_mod(warning.text)
			return False
		except:
			pass
		get_page(base_url + "manager-area/home.xhtml", False)
		print_mod("Successfully Logged in")
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
	logout_xpath = "//a[@id='j_idt28:j_idt32']"
	try:
		driver.find_element(By.XPATH, logout_xpath).click()
		print_mod("SUCCESS")
	except:
		print_mod("Couldn't find logout button. Reloading page... ")
		get_page(base_url + "manager-area/home.xhtml", False)
		wait = WebDriverWait(driver, 100)
		wait.until(EC.presence_of_element_located((By.XPATH, logout_xpath)))
		driver.find_element(By.XPATH, logout_xpath).click()
		print_mod("SUCCESS")

def get_customers():
	print_mod("Getting Customers... ", end='')
	customers = {}
	suspended = []
	try:
		url = base_url + "manager-area/manage-customers.xhtml"
		get_page(url, False)
		wait = WebDriverWait(driver, 100)
		table_xpath = "//table[@id='table']"
		while True:
			wait.until(EC.presence_of_element_located((By.XPATH, table_xpath)))
			table = driver.find_element(By.XPATH, table_xpath)
			rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
			headers = table.find_element(By.TAG_NAME, 'thead').find_elements(By.TAG_NAME, 'th')
			for row in rows:
				customer = {}
				row_all = row.find_elements(By.TAG_NAME, 'td')
				row = row_all[0:7]
				for i, r in enumerate(row):
					customer[headers[i].text]=r.text
				customer['Id'] = spotbanc.get_customer_id_from_code(customer['Code'])
				customer['Last entry'] = datetime.today().strftime("%Y-%m-%d")
				customers[customer['Code']] = customer
				if(customer["Status"] == 'SUSPENDED'):
					suspended.append(customer['Code'])
			#Get next button
			has_next_page, next_button = next_page("//a[@id='table_next']")
			if(has_next_page):
				print_mod("Going to next page")
				next_button.click()
			else:
				#Unsuspend accounts
				searchbox = driver.find_element(By.XPATH, "//input[@id='searchbox']")
				for code in suspended:
					searchbox.clear()
					searchbox.send_keys(code)
					wait.until(EC.presence_of_element_located((By.XPATH, table_xpath)))
					table = driver.find_element(By.XPATH, table_xpath)
					rows = table.find_element(By.TAG_NAME, 'tbody').find_elements(By.TAG_NAME, 'tr')
					for row in rows:
						unsuspend_btn = row.find_elements(By.TAG_NAME, 'td')[8].find_element(By.TAG_NAME, 'a')
						unsuspend_btn.click()
						time.sleep(2)
						driver.send_keys(Keys.ENTER)
				break
		progress["get_customers"] = True
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
	


def get_customer_accounts(code):
	url = base_url + "manager-area/user-profile.xhtml?code=" + code
	get_page(url, False)
	customer = {"accounts": []}
	accounts = []
	wait = WebDriverWait(driver, 50)
	try:
		table_xpath = "//table[@id='acct-table']"
		print_mod("Waiting for Table")
		try:
			wait.until(EC.presence_of_element_located((By.XPATH, table_xpath)))
		except:
			get_page(url, False)
			wait.until(EC.presence_of_element_located((By.XPATH, table_xpath)))
		customer_details = driver.find_element(By.XPATH, "//div[@id='transaction4']")
		labels = customer_details.find_elements(By.TAG_NAME,'label')
		inputs = customer_details.find_elements(By.TAG_NAME, 'input')
		for i in range(len(labels)):
			label = labels[i].text
			input = inputs[i].get_attribute('value')
			if(label == 'Name'):
				input = input.replace(')', '')
				input = input.replace('(','')
				name = input.split()
				try:
					customer['First Name'] = name[0]
				except IndexError:
					customer['First Name'] = ''
				try:
					customer['Last Name'] = name[1]
				except:
					customer['Last Name'] = ''
				try:
					customer['Account Type'] = name[2]
				except IndexError:
					#If list less than 3, check last entry to see if it is account type
					if(name[len(name) -1] in ["INDIVIDUAL, COMPANY"]):
						customer['Account Type'] = name[len(name) - 1]
					else:
						customer['Account Type'] = ''
			else:
				customer[label] = input

		table = driver.find_element(By.XPATH, table_xpath)
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
		return customer

#Get accounts from Accounting > View Customer Accounts:
def get_all_accounts():
	url = base_url + "manager-area/account_wallet_statement_manager.xhtml?walletaccounttype=REGISTERED_CUSTOMER"
	get_page(url, False)
	accounts = []
	time.sleep(10)
	driver.find_element(By.XPATH, "/html/body/div[1]/div[4]/form[2]/div[2]/div/input").click()
	time.sleep(5)
	while True:
		table = driver.find_element(By.XPATH, "//table[@id='tbl']")
		thead = table.find_element(By.TAG_NAME, 'thead')
		tbody = table.find_element(By.TAG_NAME, 'tbody')
		headers = thead.find_elements(By.TAG_NAME, 'th')
		rows = tbody.find_elements(By.TAG_NAME, 'tr')
		print_mod("Got elements")
		print_mod(len(rows))
		for row in rows:
			account = {}
			row_data = row.find_elements(By.TAG_NAME, 'td')[0:4]
			for i, r in enumerate(row_data):
				print_mod(r.text)
				account[headers[i].text] = r.text
			accounts.append(account)
		#Get Next Button
		has_next_page, next_button = next_page("//a[@id='tbl_next']")
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
	next_button = driver.find_element(By.XPATH, button_xpath)
	if("disabled" in next_button.get_attribute("class")):
		return False, None
	else:
		return True, next_button

#Runs get_customer_accounts() for every customer
def get_all_customers_accounts():
	headers = ["Date", "Balance", "Account Name", "Account Number", "Status", "Customer Code"]
	with open('customers.json', 'r') as f:
		c = json.load(f)
	keys_list = list(c)
	progress_start = progress["get_accounts"]
	for i in range(progress_start, len(c)):
		code = keys_list[i]
		customer = c[code]
		print_mod(str(i) + ") ",end='')
		print_mod("Getting accounts of " + code)
		customer_account = get_customer_accounts(code)
		for detail in customer_account:
			customer[detail] = customer_account[detail]
		customer["Code"] = code
		mydb,cursor = connect_to_db()
		add_customer_to_db(customer, cursor)
		mydb.commit()
		disconnect_from_db(mydb, cursor)
		#Start with the one above this one
		progress["get_accounts"] = i+1

def get_all_transactions():
	mydb,cursor = connect_to_db()
	cursor.execute("SELECT customer_code FROM customer")
	customers = cursor.fetchall()
	get_page(base_url + "manager-area/wallet_statement_manager.xhtml?search-type=REGISTERED_CUSTOMER", True)
	transactions_start = progress["get_transactions"]
	for i in range(transactions_start, len(customers)):
		code = customers[i][0]
		print_mod("Getting customer transactions (" + code)
		query = "SELECT customer_id, customer_code, status FROM customer WHERE customer_code='%s'" % (code)
		cursor.execute(query)
		customer_id = cursor.fetchone()
		if(customer_id[1] not in ["PENDING", "SUSPENDED"]):
			c = get_account_ledger(customer_id[0], customer_id[1])
			cursor.execute("DELETE FROM transaction WHERE account_code IN (SELECT account_code FROM account WHERE customer_code='%s')" % (code))
			for transaction in c:
				add_transaction_to_db(transaction, cursor)
				mydb.commit()
		progress["get_transactions"] = i+1
	print_mod(cursor.rowcount, " record inserted")
	disconnect_from_db(mydb, cursor)


driver = init_driver()
try:
	if not login():
		raise ValueError("Failed to Login in")
	

	print_mod("Getting Customers")
	#Only run if set to false
	if not progress["get_customers"]:
		get_customers()
	print_mod("Getting Customers with accounts")
	get_all_customers_accounts()
	print_mod("Added customers to database")
	print_mod("Getting customer transactions")
	get_all_transactions()

except Exception:
	print_mod(traceback.format_exc())
finally:
	with open("progress.json", 'w') as f:
		json.dump(progress, f)
        logout()
        close_driver()


from functions import run_get_customers, login, print_mod,init_driver, get_progress, init_environment, get_customers, get_all_customers_accounts, logout, close_driver
import sys

#arguments: worker, workers, email, password, production?
print(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], bool(sys.argv[5]))
run_get_customers(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], bool(sys.argv[5]))

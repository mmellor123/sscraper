from functions import login, run_get_transactions, init_driver, init_environment, get_customers, get_all_customers_accounts
import sys

print(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], bool(sys.argv[5]))
run_get_transactions(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], bool(sys.argv[5]))

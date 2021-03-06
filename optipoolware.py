# optipoolware.py v 0.31 to be used with Python3.5
# Bismuth pool mining software
# Copyright Hclivess, Maccaspacca 2017
# for license see LICENSE file
# .

import socketserver, connections, time, options, log, sqlite3, socks, hashlib, random, re, keys, base64, sys, os, math
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA
from Crypto import Random
import threading
import statistics

config = options.Get()
config.read()
port = config.port
node_ip_conf = config.node_ip_conf
ledger_path_conf = config.ledger_path_conf
tor_conf = config.tor_conf
debug_level_conf = config.debug_level_conf
version = config.version_conf

# print(version)

# load config

(key, private_key_readable, public_key_readable, public_key_hashed, address) = keys.read() #import keys
app_log = log.log("pool.log",debug_level_conf)
print("Pool Address: {}".format(address))

# load config
try:
	
	lines = [line.rstrip('\n') for line in open('pool.txt')]
	for line in lines:
		try:
			if "mine_diff=" in line:
				mdiff = int(line.split('=')[1])
		except Exception as e:
			mdiff = 65
		try:
			if "min_payout=" in line:
				min_payout = float(line.split('=')[1])
		except Exception as e:
			min_payout = 1
		try:
			if "pool_fee=" in line:
				pool_fee = float(line.split('=')[1])
		except Exception as e:
			pool_fee = 0
		try:
			if "alt_fee=" in line:
				alt_fee = float(line.split('=')[1])
		except Exception as e:
			alt_fee = 0
		try:
			if "worker_time=" in line:
				w_time = int(line.split('=')[1])
		except Exception as e:
			w_time = 10
		try:
			if "alt_add=" in line:
				alt_add = str(line.split('=')[1])
		except Exception as e:
			alt_add = "92563981cc1e70d160c176edf368ea4bbc1d8d5ba63aceee99ef6ebd"

except Exception as e:
	min_payout = 1
	mdiff = 65
	pool_fee = 0
	alt_fee = 0
	w_time = 10
	alt_add = "92563981cc1e70d160c176edf368ea4bbc1d8d5ba63aceee99ef6ebd"
# load config

bin_format_dict = dict((x, format(ord(x), '8b').replace(' ', '0')) for x in '0123456789abcdef')

def percentage(percent, whole):
	return int((percent * whole) / 100)
	
def checkdb():
	shares = sqlite3.connect('shares.db')
	shares.text_factory = str
	s = shares.cursor()
	s.execute("SELECT * FROM shares")
	present = s.fetchall()
	
	if not present:
		return False
	else:
		return True

# payout processing

def payout(payout_threshold,myfee,othfee):

	print("Minimum payout is {} Bismuth".format(str(payout_threshold)))
	print("Current pool fee is {} Percent".format(str(myfee)))
	
	shares = sqlite3.connect('shares.db')
	shares.text_factory = str
	s = shares.cursor()

	conn = sqlite3.connect(ledger_path_conf)
	conn.text_factory = str
	c = conn.cursor()
	
	#get sum of all shares not paid
	s.execute("SELECT sum(shares) FROM shares WHERE paid != 1")
	shares_total = s.fetchone()[0]
	#get sum of all shares not paid
	
	#get block threshold
	try:
		s.execute("SELECT min(timestamp) FROM shares WHERE paid != 1")
		block_threshold = float(s.fetchone()[0])
	except:
		block_threshold = time.time()
	#get block threshold
	
	#get eligible blocks
	reward_list = []
	for row in c.execute("SELECT * FROM transactions WHERE address = ? AND CAST(timestamp AS INTEGER) >= ? AND reward != 0", (address,) + (block_threshold,)):
		reward_list.append(float(row[9]))

	super_total = sum(reward_list)
	#get eligible blocks
	
	# so now we have sum of shares, total reward, block threshold
	
	# reduce total rewards by total fees percentage
	reward_total = "%.8f" % (((100-(myfee+othfee))*super_total)/100)
	reward_total = float(reward_total)
	
	if reward_total > 0:
	
		# calculate alt address fee
		
		ft = super_total - reward_total
		try:
			at = "%.8f" % (ft * (othfee/(myfee+othfee)))
		except:
			at = 0
			
		# calculate reward per share
		reward_per_share = reward_total / shares_total
		
		# calculate shares threshold for payment
		
		shares_threshold = math.floor(payout_threshold/reward_per_share)
		
		#get unique addresses
		addresses = []
		for row in s.execute("SELECT * FROM shares"):
			shares_address = row[0]

			if shares_address not in addresses:
				addresses.append(shares_address)
		print (addresses)
		#get unique addresses
		
		# prepare payout address list with number of shares and new total shares
		payadd = []
		new_sum = 0
		for x in addresses:
			s.execute("SELECT sum(shares) FROM shares WHERE address = ? AND paid != 1", (x,))
			shares_sum = s.fetchone()[0]

			if shares_sum == None:
				shares_sum = 0
			if shares_sum > shares_threshold:
				payadd.append([x,shares_sum])
				new_sum = new_sum + shares_sum
		#prepare payout address list with number of shares and new total shares

		# recalculate reward per share now we have removed those below payout threshold
		try:
		
			reward_per_share = reward_total / new_sum
		
		except:
			reward_per_share = 0
		
		print(reward_per_share)
		
		paylist = []
		for p in payadd:
			payme =  "%.8f" % (p[1] * reward_per_share)
			paylist.append([p[0],payme])

		if othfee > 0:
			paylist.append([alt_add,at])
		
		payout_passed = 0
		for r in paylist:
			print(r)
			recipient = r[0]
			claim = float(r[1])
					
			payout_passed = 1
			openfield = "pool"
			keep = 0
			fee = float('%.8f' % float(0.01 + (float(len(openfield)) / 100000) + (keep)))  # 0.01 + openfield fee + keep fee
			#make payout

			timestamp = '%.2f' % time.time()
			transaction = (str(timestamp), str(address), str(recipient), '%.8f' % float(claim - fee), str(keep), str(openfield))  # this is signed
			# print transaction

			h = SHA.new(str(transaction).encode("utf-8"))
			signer = PKCS1_v1_5.new(key)
			signature = signer.sign(h)
			signature_enc = base64.b64encode(signature)
			print("Encoded Signature: {}".format(signature_enc.decode("utf-8")))

			verifier = PKCS1_v1_5.new(key)
			if verifier.verify(h, signature) == True:
				print("The signature is valid, proceeding to save transaction to mempool")

				mempool = sqlite3.connect('mempool.db')
				mempool.text_factory = str
				m = mempool.cursor()

				m.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", (str(timestamp), str(address), str(recipient), '%.8f' % float(claim - fee), str(signature_enc.decode("utf-8")), str(public_key_hashed), str(keep), str(openfield)))
				mempool.commit()  # Save (commit) the changes
				mempool.close()
				print("Mempool updated with a received transaction")

			s.execute("UPDATE shares SET paid = 1 WHERE address = ?",(recipient,))
			shares.commit()

		if payout_passed == 1:
			s.execute("UPDATE shares SET timestamp = ?", (time.time(),))
			shares.commit()

		# calculate payouts
		#payout
		
		# archive paid shares
		s.execute("SELECT * FROM shares WHERE paid = 1")
		pd = s.fetchall()
	
		if pd == None:
			pass
		else:
			archive = sqlite3.connect('archive.db')
			archive.text_factory = str
			a = archive.cursor()
			
			for sh in pd:
				a.execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)", (sh[0],sh[1],sh[2],sh[3],sh[4],sh[5],sh[6],sh[7]))

			archive.commit()
			a.close()
		# archive paid shares
	
	# clear nonces
	s.execute("DELETE FROM nonces")
	s.execute("DELETE FROM shares WHERE paid = 1")
	shares.commit()
	s.execute("VACUUM")
	#clear nonces
	s.close()

	
def commit(cursor):
	# secure commit for slow nodes
	passed = 0
	while passed == 0:
		try:
			cursor.commit()
			passed = 1
		except Exception as e:
			app_log.warning("Retrying database execute due to " + str(e))
			time.sleep(random.random())
			pass
			# secure commit for slow nodes


def execute(cursor, what):
	# secure execute for slow nodes
	passed = 0
	while passed == 0:
		try:
			# print cursor
			# print what

			cursor.execute(what)
			passed = 1
		except Exception as e:
			app_log.warning("Retrying database execute due to {}".format(e))
			time.sleep(random.random())
			pass
			# secure execute for slow nodes
	return cursor


def execute_param(cursor, what, param):
	# secure execute for slow nodes
	passed = 0
	while passed == 0:
		try:
			# print cursor
			# print what
			cursor.execute(what, param)
			passed = 1
		except Exception as e:
			app_log.warning("Retrying database execute due to " + str(e))
			time.sleep(0.1)
			pass
			# secure execute for slow nodes
	return cursor

	
def bin_convert(string):
	return ''.join(bin_format_dict[x] for x in string)

def bin_convert_orig(string):
	return ''.join(format(ord(x), '8b').replace(' ', '0') for x in string)

def s_test(testString):

	if testString.isalnum():
		if (re.search('[abcdef]',testString)):
			if len(testString) == 56:
				return True
	else:
		return False
		
def n_test(testString):

	if testString.isalnum():
		if (re.search('[abcdef]',testString)):
			if len(testString) < 129:
				return True
	else:
		return False
	
def paydb():

	while True:
		app_log.warning("Payout run finished")
		time.sleep(3601)
		#time.sleep(60) # test
		v = float('%.2f' % time.time())
		v1 = new_time
		v2 = v - v1

		if v2 < 300:
			payout(min_payout,pool_fee,alt_fee)
			app_log.warning("Payout running...")
		else:
			app_log.warning("Node over 5 mins out...payout delayed")			
		
def worker(s_time):

	global new_diff
	global new_hash
	global new_time
	doclean = 0

	n = socks.socksocket()
	n.connect((node_ip_conf, int(port)))  # connect to local node

	while True:
	
		time.sleep(s_time)
		doclean +=1
	
		try:

			app_log.warning("Worker task...")
			connections.send(n, "blocklast", 10)
			blocklast = connections.receive(n, 10)

			connections.send(n, "diffget", 10)
			diff = connections.receive(n, 10)

			new_hash = blocklast[7]
			new_time = blocklast[1]
			new_diff = math.ceil(diff[1])

			app_log.warning("Difficulty = {}".format(str(new_diff)))
			app_log.warning("Blockhash = {}".format(str(new_hash)))
		
			# clean mempool
			if doclean == (3600/s_time):
				app_log.warning("Begin mempool clean...")
				mempool = sqlite3.connect("mempool.db")
				mempool.text_factory = str
				m = mempool.cursor()
				m.execute("SELECT * FROM transactions ORDER BY timestamp;")
				result = m.fetchall()  # select all txs from mempool
				
				for r in result:
					ts = r[4]
					c.execute("SELECT block_height FROM transactions WHERE signature = ?;",(ts,))
					try:
						nok = c.fetchall()[0]
						m.execute("DELETE FROM transactions WHERE signature = ?;",(ts,))
					except:
						pass
				mempool.commit()
				m.execute("VACUUM")
				mempool.close()
				doclean = 0
				app_log.warning("End mempool clean...")
			# clean mempool

		except Exception as e:
			app_log.warning(str(e))
	n.close()
		
if not os.path.exists('shares.db'):
	# create empty shares
	shares = sqlite3.connect('shares.db')
	shares.text_factory = str
	s = shares.cursor()
	execute(s, "CREATE TABLE IF NOT EXISTS shares (address, shares, timestamp, paid, rate, name, workers, subname)")
	execute(s, "CREATE TABLE IF NOT EXISTS nonces (nonce)") #for used hash storage
	app_log.warning("Created shares file")
	s.close()
	# create empty shares
if not os.path.exists('archive.db'):
	# create empty archive
	archive = sqlite3.connect('archive.db')
	archive.text_factory = str
	a = archive.cursor()
	execute(a, "CREATE TABLE IF NOT EXISTS shares (address, shares, timestamp, paid, rate, name, workers, subname)")
	app_log.warning("Created archive file")
	a.close()
	# create empty archive
	
if checkdb():
	payout(min_payout,pool_fee,alt_fee)

class MyTCPHandler(socketserver.BaseRequestHandler):

	def handle(self):
		from Crypto.PublicKey import RSA
		key = RSA.importKey(private_key_readable)
		
		self.allow_reuse_address = True

		peer_ip = self.request.getpeername()[0]

		try:
			data = connections.receive(self.request, 10)
	
			app_log.warning("Received: {} from {}".format(data, peer_ip))  # will add custom ports later

			if data == "getwork":  # sends the miner the blockhash and mining diff for shares
			
				work_send = []
				work_send.append((new_hash, mdiff, address, mdiff))

				connections.send(self.request, work_send, 10)
				
				print("Work package sent.... {}".format(str(new_hash)))

			elif data == "block":  # from miner to node

				# sock
				#s1 = socks.socksocket()
				#if tor_conf == 1:
				#	s1.setproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
				#s1.connect(("127.0.0.1", int(port)))  # connect to local node,
				# sock


				# receive nonce from miner
				miner_address = connections.receive(self.request, 10)
				
				if not s_test(miner_address):
					
					app_log.warning("Bad Miner Address Detected - Changing to default")
					miner_address = alt_add
					#s1.close()
				
				else:
					
					app_log.warning("Received a solution from miner {} ({})".format(peer_ip,miner_address))

					block_nonce = connections.receive(self.request, 10)
					block_timestamp = (block_nonce[-1][0])
					nonce = (block_nonce[-1][1])
					mine_hash = ((block_nonce[-1][2])) # block hash claimed
					ndiff = ((block_nonce[-1][3])) # network diff when mined
					sdiffs = ((block_nonce[-1][4])) # actual diff mined
					mrate = ((block_nonce[-1][5])) # total hash rate in khs
					bname = ((block_nonce[-1][6])) # base worker name
					wnum = ((block_nonce[-1][7])) # workers
					wstr = ((block_nonce[-1][8])) # worker number
					wname = "{}{}".format(bname, wstr) # worker name
					
					app_log.warning("Mined nonce details: {}".format(block_nonce))
					app_log.warning("Claimed hash: {}".format(mine_hash))
					app_log.warning("Claimed diff: {}".format(sdiffs))
					
					if not n_test(nonce):
						app_log.warning("Bad Nonce Format Detected - Closing Connection")
						self.close
					app_log.warning("Processing nonce.....")

					diff = new_diff
					db_block_hash = mine_hash
					
					mining_hash = bin_convert_orig(hashlib.sha224((address + nonce + db_block_hash).encode("utf-8")).hexdigest())
					mining_condition = bin_convert_orig(db_block_hash)[0:diff]

					if mining_condition in mining_hash:

						app_log.warning("Difficulty requirement satisfied for mining")
						app_log.warning("Sending block to node {}".format(peer_ip))

						mempool = sqlite3.connect("mempool.db")
						mempool.text_factory = str
						m = mempool.cursor()
						execute(m, ("SELECT * FROM transactions ORDER BY timestamp;"))
						result = m.fetchall()  # select all txs from mempool
						mempool.close()

						# include data
						block_send = []
						del block_send[:]  # empty
						removal_signature = []
						del removal_signature[:]  # empty

						for dbdata in result:
							transaction = (
								str(dbdata[0]), str(dbdata[1][:56]), str(dbdata[2][:56]), '%.8f' % float(dbdata[3]),
								str(dbdata[4]), str(dbdata[5]), str(dbdata[6]),
								str(dbdata[7]))  # create tuple
							# print transaction
							block_send.append(transaction)  # append tuple to list for each run
							removal_signature.append(str(dbdata[4]))  # for removal after successful mining

						# claim reward
						transaction_reward = tuple
						transaction_reward = (str(block_timestamp), str(address[:56]), str(address[:56]), '%.8f' % float(0), "0", str(nonce))  # only this part is signed!
						print(transaction_reward)

						h = SHA.new(str(transaction_reward).encode("utf-8"))
						signer = PKCS1_v1_5.new(key)
						signature = signer.sign(h)
						signature_enc = base64.b64encode(signature)

						if signer.verify(h, signature) == True:
							app_log.warning("Signature valid")

							block_send.append((str(block_timestamp), str(address[:56]), str(address[:56]), '%.8f' % float(0), str(signature_enc.decode("utf-8")), str(public_key_hashed), "0", str(nonce)))  # mining reward tx
							app_log.warning("Block to send: {}".format(block_send))
							
							if not any(isinstance(el, list) for el in block_send):  # if it's not a list of lists (only the mining tx and no others)
								new_list = []
								new_list.append(block_send)
								block_send = new_list  # make it a list of lists

						global peer_dict
						peer_dict = {}
						with open("peers.txt") as f:
							for line in f:
								line = re.sub("[\)\(\:\\n\'\s]", "", line)
								peer_dict[line.split(",")[0]] = line.split(",")[1]

							for k, v in peer_dict.items():
								peer_ip = k
								# app_log.info(HOST)
								peer_port = int(v)
								# app_log.info(PORT)
								# connect to all nodes

								try:
									s = socks.socksocket()
									s.settimeout(0.3)
									if tor_conf == 1:
										s.setproxy(socks.PROXY_TYPE_SOCKS5, "127.0.0.1", 9050)
									s.connect((peer_ip, int(peer_port)))  # connect to node in peerlist
									app_log.warning("Connected")

									app_log.warning("Miner: Proceeding to submit mined block")

									connections.send(s, "block", 10)
									connections.send(s, block_send, 10)

									app_log.warning("Miner: Block submitted to {}".format(peer_ip))
								except Exception as e:
									app_log.warning("Miner: Could not submit block to {} because {}".format(peer_ip, e))
									pass

					if diff < mdiff:
						diff_shares = diff
					else:
						diff_shares = mdiff
						
					shares = sqlite3.connect('shares.db')
					shares.text_factory = str
					s = shares.cursor()

					# protect against used share resubmission
					execute_param(s, ("SELECT nonce FROM nonces WHERE nonce = ?"), (nonce,))

					try:
						result = s.fetchone()[0]
						app_log.warning("Miner trying to reuse a share, ignored")
					except:
						# protect against used share resubmission
						mining_condition = bin_convert_orig(db_block_hash)[0:diff_shares] #floor set by pool
						if mining_condition in mining_hash:
							app_log.warning("Difficulty requirement satisfied for saving shares \n")

							execute_param(s, ("INSERT INTO nonces VALUES (?)"), (nonce,))
							commit(shares)

							timestamp = '%.2f' % time.time()

							s.execute("INSERT INTO shares VALUES (?,?,?,?,?,?,?,?)", (str(miner_address), str(1), timestamp, "0", str(mrate), bname, str(wnum), wname))
							shares.commit()

						else:
							app_log.warning("Difficulty requirement not satisfied for anything \n")

					s.close()

			self.request.close()
		except Exception as e:
			pass
	app_log.warning("Starting up...")

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
	pass

if __name__ == "__main__":

	background_thread = threading.Thread(target=paydb)
	background_thread.daemon = True
	background_thread.start()
	
	worker_thread = threading.Thread(target=worker, args=(w_time,))
	worker_thread.daemon = True
	worker_thread.start()
	app_log.warning("Starting up background tasks....")
	time.sleep(10)

	try:
		pool_port = int(sys.argv[1])
	except Exception as e:
		pool_port = 8525

	HOST, PORT = "0.0.0.0", pool_port
	
	# Create the server thread handler, binding to localhost on port above
	server = ThreadedTCPServer((HOST, PORT), MyTCPHandler)
	ip, port = server.server_address
	
	server_thread = threading.Thread(target=server.serve_forever)
	
	server_thread.daemon = True
	server_thread.start()
	server_thread.join()
	server.shutdown()
	server.server_close()
	
sys.exit()

import sys
import os
from datetime import datetime

abspath = os.path.dirname(__file__)
sys.path.append(abspath)
os.chdir(abspath)

import web
import simplejson
import logging
import opentok1

# uncomment for one session after changes to opentok.py
#reload(opentok)

web.config.debug = False										
openTokSDK = opentok1.OpenTokSDK('', '')
db = web.database(dbn='mysql', user='telephone', pw='ca4nuhearmenow', db='tokbox_telephone')
render = web.template.render('templates/')



urls = (
	'/', 'index',
	'/todo', 'todo',	
	'/requirements', 'requirements',
	'/api/find-game', 'find_game',
 	'/api/add-player', 'add_player',
 	'/api/remove-player', 'remove_player',	
	'/api/get-state', 'get_state',
	'/api/set-state', 'set_state',
	'/api/touch', 'touch'	
	)


# site pages

def notfound():
	return web.notfound(str(render.notfound()))


class todo:		
	def GET(self):
		web.header('Cache-Control', 'no-store, no-cache, must-revalidate')
		web.header('Content-Type', 'text/html; charset=utf-8')
		return render.todo()


class index:		
	def GET(self):
		web.header('Cache-Control', 'no-store, no-cache, must-revalidate')
		web.header('Content-Type', 'text/html; charset=utf-8')
		name = web.input(name = 'Your Name').name
		return render.index(name)

	POST = GET

class requirements:
	def GET(self):
		web.header('Content-Type', 'text/html; charset=utf-8')
		return render.requirements()		


# api pages

def set_api_headers():
	web.header('Cache-Control', 'no-store, no-cache, must-revalidate')
	web.header('Content-Type', 'application/json')

class find_game:
	def GET(self):
		set_api_headers()
		player_limit = 5
		wait_time = 3 #seconds between joins
		session_id = 0
		first_in = False

		# find an active game
		games = db.select('games', order = 'time_created DESC')

		for game in games:
			#count players		
			player_count = 0	
			players = simplejson.loads(game.players)
				
			for player in players:
				if player is not "0":
					player_count += 1

			# will this game work?
			if (player_count < player_limit) and (game.status_message != 'abandoned') and (game.status_message != 'finished'):
				
				# check time since creation, if not enough time, tell client to wait, or just delay response here...
				time_elapsed = datetime.now() - game.time_last_joined

				if time_elapsed.seconds <= wait_time:
					# tell the person to wait the balance of the time and try again!
					return simplejson.dumps({'status': 'wait', 'duration': wait_time - time_elapsed.seconds})
				else:
					# good to go
					session_id = game.session_id						
					
					# update time joined
					db.update('games', where = "session_id = '" + session_id + "'", time_last_joined = datetime.now())
					break

		if session_id is 0:
			# if none of the existing games will work, create our own
			first_in = True # for the empty check
			session = openTokSDK.create_session(web.ctx.ip, {'echoSuppression_enabled': True})
			db.insert('games', session_id = session.session_id, status_message = 'just created')
			db.update('games', where = "session_id = '" + session.session_id + "'", time_last_joined = datetime.now())						
			session_id = session.session_id

		token = openTokSDK.generate_token(session_id)
		
		return simplejson.dumps({'status': 'success', 'session_id': session_id, 'token': token, 'first_in': first_in})


class add_player:
	def POST(self):
		set_api_headers()	
		i = web.input(session_id = '', player_id = '', player_name = '')
				
		# download the current player list, append the new player to it
		result = db.select('games', what = "games.players,games.id", where = "session_id = '" + i.session_id + "'")
		game = result[0]
		players = simplejson.loads(game.players)
		
		if len(players) == 0:
			# set this player as the starting operator
			db.update('games', where = "id = '" + str(game.id) + "'", operator_id = i.player_id, founder_name = i.player_name)

		
		players.append(i.player_id)
		json_players = simplejson.dumps(players)
		
		db.update('games', where = "id = '" + str(game.id) + "'", players = json_players)
		
		return json_players


class remove_player:
	def POST(self):
		set_api_headers()	
		i = web.input(session_id = '', player_id = '')
		
		# download the current player list
		result = db.select('games', what = "games.players,games.id", where = "session_id = '" + i.session_id + "'")
		game = result[0]
		players = simplejson.loads(game.players)
			
		if i.player_id in players:
			# remove the player we ant to remove
			players.remove(str(i.player_id))
			#zero out the player we want to remove
			#players[players.index(i.player_id)] = '0'
			

		# back to json string
		json_players = simplejson.dumps(players)
		
		#update the game
		db.update('games', where = "id = '" + str(game.id) + "'", players = json_players)

		return json_players	

# sets the 'time_last_joined' field to now
class touch:
	def POST(self):
		set_api_headers()	
		session_id = web.input(session_id = '').session_id
		db.update('games', where = "session_id = '" + session_id + "'", time_last_joined = datetime.now())		
		return simplejson.dumps({'status' : 'success', 'message' : 'touched'})		

class get_state:
	def POST(self):
		set_api_headers()	
		session_id = web.input(session_id = '').session_id
		
		# get the current game for the room
		result = db.select('games', where = "games.session_id = '" + session_id + "'")
		game = result[0]
		
		# convert the players list back to python...
		game.players = simplejson.loads(game.players)
		
		# datetime json conversion via http://stackoverflow.com/questions/455580/json-datetime-between-python-and-javascript/2680060#2680060
		dthandler = lambda obj: obj.isoformat() if isinstance(obj, datetime) else None
		return simplejson.dumps(game, default=dthandler)


class set_state:
	def POST(self):
		set_api_headers()	
		i = web.input(session_id = '')
		session_id = i.session_id
		del i.session_id
		
		change = 0
		if len(i) > 0:
			change = db.update('games', where = "games.session_id = '" + session_id + "'", **i)	

		return simplejson.dumps({'status' : 'success', 'message' : str(change) + ' rows changed'})

	
if __name__ == "__main__":
	app.run()
	
app = web.application(urls, globals(), autoreload=False) # ammended for mod_wsgi
app.notfound = notfound	
application = app.wsgifunc()

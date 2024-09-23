import base64
import json
import coloredlogs
import logging
import traceback
import uuid
import urllib.request
from functools import wraps
import gasp_server.db as db

from flask import Flask, request, url_for, current_app
from gasp_server.auction_runner import start_auction, submit_bid, get_state,\
    SUPPORTED_AUCTIONS, UnsupportedAuction


WITH_TRACES = True

def with_valid_competition(with_goods=False, with_agents=False):
    def _with_valid_competition_decorator(fn):
        @wraps(fn)  # This is needed to keep the original function's name (used by the flask route)
        def _wrapped(*args, **kwargs):
            competition_id = args[0]
            try:
                cursor = db.execute_query(
                    """
                    SELECT competitionId, title, description, responseClock, bidClock, mechanism, auctionType
                    FROM Competition
                    WHERE Competition.competitionId = %s""",
                    competition_id)
                row = cursor.fetchone()
                cursor.close()
                if row is None:
                    return {"message": "Unknown competition id"}, 404
                competition = {
                    "competition_id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "response_clock": int(row[3]),
                    "bid_clock": int(row[4]),
                    "mechanism": row[5],
                    "auction_type": row[6],
                    "url": f'http://{request.host}/{row[0]}'}
                if competition['mechanism'] not in SUPPORTED_AUCTIONS:
                    raise UnsupportedAuction()
                if with_goods:
                    cursor = db.execute_query(
                        "SELECT goodName FROM Good WHERE competitionId = %s",
                        competition_id)
                    competition["goods"] = [row[0] for row in cursor]
                    cursor.close()
                if with_agents:
                    cursor = db.execute_query(
                        "SELECT agentName, url, valuation, budget, allocation, agentType, utility, rationality FROM Agent WHERE competitionId = %s",
                        competition_id)
                    competition["agents"] = [
                        {
                            "id": row[0],
                            "url": row[1],
                            "valuation": json.loads(row[2]),
                            "budget": row[3],
                            "allocation": json.loads(row[4]),
                            "agent_type": row[5],
                            "utility": row[6],
                            "rationality": row[7]
                        }
                        for row in cursor]
                    cursor.close()
                SUPPORTED_AUCTIONS[competition['mechanism']]['load'](competition)
                return fn(competition, *args[1:], **kwargs)
            except Exception as e:
                current_app.logger.warning(repr(e))
                if WITH_TRACES:
                    traceback.print_exc()
                return {"message": f"Bad request: {repr(e)}"
                        if current_app.config['DEBUG'] else "Bad request"}, 400
        return _wrapped

    return _with_valid_competition_decorator


def create_app(logging_level=logging.WARNING, config='gasp_server.config.DevConfig'):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)
    coloredlogs.install(logger=app.logger, level='DEBUG')

    from . import db
    db.init_app(app)

    @app.route('/competitions', methods=['GET', 'POST'])
    def competitions():
        if request.method == 'POST':
            return new_competition()
        return competition_list()

    @app.route('/<uuid:competition_id>', methods=['GET', 'POST', 'DELETE', 'PATCH'])
    def competition(competition_id):
        if request.method == 'POST':
            return new_bidder()
        if request.method == 'DELETE':
            return delete_competition(str(competition_id))
        if request.method == 'PATCH':
            return update_bidder()
        return competition_info(str(competition_id))

    @app.route('/<uuid:competition_id>/start', methods=['GET'])
    def start(competition_id):
        return start_competition(str(competition_id))
    
    @app.route('/<uuid:competition_id>/next', methods=['GET'])
    def goto_next_state(competition_id):
        return force_update_state(str(competition_id))
    
    @app.route('/<uuid:competition_id>/goods/<good_name>', methods=['GET'])
    def get_image(competition_id, good_name):
        return get_img(str(competition_id), str(good_name))
    
    @app.route('/<uuid:competition_id>/<agent_id>/bid', methods=['POST'])
    def bid(competition_id, agent_id):
        return send_bid(str(competition_id), agent_id)
    
    return app

def new_competition():
    content = request.get_json()
    new_id = uuid.uuid4()
    try:
        if content["mechanism"] not in SUPPORTED_AUCTIONS:
            raise UnsupportedAuction()
        content["competition_id"] = str(new_id)
        cursor = db.execute_query(
            """
            INSERT INTO Competition (
                competitionId, title, description, responseClock, bidClock, mechanism, auctionType
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            content["competition_id"],
            content["title"],
            content["description"],
            content["response_clock"],
            content["bid_clock"],
            content["mechanism"],
            content["auction_type"])
        cursor.close()
        for good in content["goods"]:
            cursor = db.execute_query(
                """
                INSERT INTO Good (
                    competitionId, goodName, goodImage
                ) VALUES (%s, %s, %s)""",
                content["competition_id"],
                good['good_name'], good['good_image'])
            cursor.close()
        if content["agents"] != []:
            for agent in content["agents"]:
                cursor = db.execute_query(
                    """
                    INSERT INTO Agent (
                        competitionId, agentName, url, valuation, budget, allocation, agentType, utility, rationality
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    content["competition_id"],
                    agent["id"],
                    agent["url"],
                    json.dumps(agent["valuation"]),
                    agent['budget'],
                    json.dumps(agent["allocation"]),
                    agent["agent_type"],
                    agent["utility"],
                    agent["rationality"])
                cursor.close()
        SUPPORTED_AUCTIONS[content['mechanism']]['create'](content)
        db.commit()
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Bad request: {e}"
                if current_app.config['DEBUG'] else "Bad request"}, 400
    return {"message": "Competition created",
            "url": "http://" + request.host + url_for("competition", competition_id=new_id)}

def new_bidder():
    agent = request.get_json()
    try:
        cursor = db.execute_query(
            """
            INSERT INTO Agent (
                competitionId, agentName, url, valuation, budget, allocation, agentType, utility, rationality
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            agent["competition_id"],
            agent["id"],
            agent["url"],
            json.dumps(agent["valuation"]),
            agent['budget'],
            json.dumps(agent["allocation"]),
            agent["agent_type"],
            agent["utility"],
            agent["rationality"])
        cursor.close()
        db.commit()
        req = urllib.request.Request(
            'http://localhost:9000/launch',
            headers={'Content-type': 'text/plain'},
            data=agent['id'].encode('utf-8')
        )
        res = urllib.request.urlopen(req)
        msg = res.read().decode('utf-8')
        # print(msg)
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Bad request: {e}"
                if current_app.config['DEBUG'] else "Bad request"}, 400
    return {"message": f"{agent['id']} joined {agent['competition_id']}",
            "url": "http://" + request.host + url_for("competition", competition_id=agent['competition_id']) + '/' + agent['id']}

def update_bidder():
    update_agent = request.get_json()
    print(update_agent)
    try:
        cursor = db.execute_query(
            """
            UPDATE Agent
            SET budget = %s
            WHERE competitionId = %s
            AND agentName = %s""",
            update_agent['final_budget'],
            update_agent['competition_id'],
            update_agent['agent_id']
        )
        cursor.close()
        cursor = db.execute_query(
            """
            UPDATE Agent
            SET allocation = %s
            WHERE competitionId = %s
            AND agentName = %s""",
            json.dumps(update_agent['new_allocation']),
            update_agent['competition_id'],
            update_agent['agent_id']
        )
        cursor.close()
        cursor = db.execute_query(
            """
            UPDATE Agent
            SET utility = %s
            WHERE competitionId = %s
            AND agentName = %s""",
            update_agent['utility'],
            update_agent['competition_id'],
            update_agent['agent_id']
        )
        cursor.close()
        cursor = db.execute_query(
            """
            UPDATE Agent
            SET rationality = %s
            WHERE competitionId = %s
            AND agentName = %s""",
            update_agent['rationality'],
            update_agent['competition_id'],
            update_agent['agent_id']
        )
        cursor.close()
        db.commit()
        if update_agent['final'] == 'False':
            req = urllib.request.Request(
                'http://localhost:9000/preliminary-results',
                headers={'Content-type': 'text/plain'},
                data=json.dumps(update_agent).encode('utf-8')
            )
            res = urllib.request.urlopen(req)
            msg = res.read().decode('utf-8')
            print(msg)
        else:
            req = urllib.request.Request(
                'http://localhost:9000/final-results',
                headers={'Content-type': 'text/plain'},
                data=json.dumps(update_agent).encode('utf-8')
            )
            res = urllib.request.urlopen(req)
            msg = res.read().decode('utf-8')
            print(msg)
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Bad request: {e}"
                if current_app.config['DEBUG'] else "Bad request"}, 400
    return {"message": f"{update_agent['agent_id']} updated its budget for {update_agent['competition_id']}",
            "url": "http://" + request.host + url_for("competition", competition_id=update_agent['competition_id']) + '/' + update_agent['agent_id'] + '/play'}

def competition_list():
    cursor = db.execute_query(
        """
        SELECT title, competitionId, description, mechanism, auctionType, COUNT(DISTINCT goodName)
        FROM Competition NATURAL JOIN Good
        GROUP BY competitionId, title, description, mechanism, auctionType""")
    response = [
        {"title": row[0],
         "competition_id": row[1],
         "description": row[2],
         "mechanism": row[3],
         "auction_type": row[4],
         "nb_goods": int(row[5])
         } for row in cursor]
    cursor.close()
    return response

@with_valid_competition(with_goods=False, with_agents=False)
def delete_competition(competition):
    SUPPORTED_AUCTIONS[competition['mechanism']]['delete'](competition)
    competition_id = competition['competition_id']
    cursor = db.execute_query(
        """
        DELETE FROM CompetitionState
        WHERE competitionId = %s
        """,
        competition_id
    )
    cursor.close()
    cursor = db.execute_query(
        """
        DELETE FROM Agent
        WHERE competitionId = %s""",
        competition_id)
    cursor.close()
    cursor = db.execute_query(
        """
        DELETE FROM Good
        WHERE competitionId = %s""",
        competition_id)
    cursor.close()
    cursor = db.execute_query(
        """
        DELETE FROM Competition
        WHERE competitionId = %s""",
        competition_id)
    db.commit()
    if cursor.rowcount == 1:
        cursor.close()
        return {"message": "Competition deleted"}
    cursor.close()
    return {"message": "Unknown competition id"}, 404

@with_valid_competition(with_goods=True, with_agents=True)
def competition_info(competition):
    return competition

def get_img(competition_id, good_name):
    print(competition_id, good_name)
    cursor = db.execute_query(
        """
        SELECT goodName, goodImage
        FROM Good
        WHERE goodName = %s 
        AND competitionId = %s""", 
        good_name, 
        competition_id
    )
    response = [
        {"good_name": row[0],
         "good_image": row[1]
        } for row in cursor]
    cursor.close()
    return response


@with_valid_competition(with_goods=True, with_agents=True)
def start_competition(competition):
    try:
        start_auction(competition)
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Error: {e}"}
    return {"message": "Competition started"}


@with_valid_competition(with_goods=True, with_agents=True)
def send_bid(competition, agent_id):
    content = request.get_json()
    bid = content['bid']
    current_app.logger.debug(f'Bid received from {agent_id}: {bid}')
    try:
        submit_bid(competition, agent_id, bid)
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Error: {e}"}
    return {"message": "Bid submitted"}

@with_valid_competition(with_goods=True, with_agents=True)
def force_update_state(competition):
    try:
        # competition = json.loads(competition)
        for agent in competition["agents"]:
            if get_state(competition, agent) == 'PREPARING BID' and agent["agent_type"] == "human":
                msg = {}
                if competition["mechanism"] == "SAA" or competition["mechanism"] == "SDA":
                    msg = {
                        "message_type": "bid",
                        "competition_id": competition["competition_id"],
                        "agent_id": agent["id"],
                        "bid": []
                    }
                else:
                    msg = {
                        "message_type": "bid",
                        "competition_id": competition["competition_id"],
                        "agent_id": agent["id"],
                        "bid": {}
                    }  
                req = urllib.request.Request(f'http://localhost:5000/{competition["competition_id"]}/{agent["id"]}/bid',
                                            headers={'Content-type': 'application/json'},
                                            data=json.dumps(msg).encode('utf-8'))
                res = urllib.request.urlopen(req)
                htmldoc = res.read().decode('utf-8')
                print(htmldoc)
    except Exception as e:
        current_app.logger.warning(e)
        if WITH_TRACES:
            traceback.print_exc()
        return {"message": f"Error: {e}"}
    return {"message": "Every agent has sent a bid."}

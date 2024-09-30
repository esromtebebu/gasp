
from aiohttp import ClientError, http_exceptions, ClientSession, \
    ClientTimeout
import asyncio
from flask import current_app
import urllib.request
import aiohttp
import json
import pickle
import gasp_server.db as db
from gasp_server.auction_persistance import \
    init_saa, load_saa_variables, save_saa_variables, delete_saa_variables, \
    init_ce, load_ce_variables, save_ce_variables, delete_ce_variables, \
    init_sda, load_sda_variables, save_sda_variables, delete_sda_variables, \
    init_ssba1, load_ssba1_variables, save_ssba1_variables, delete_ssba1_variables, \
    init_ssba2, load_ssba2_variables, save_ssba2_variables, delete_ssba2_variables, \
    init_ssba3, load_ssba3_variables, save_ssba3_variables, delete_ssba3_variables
class UnsupportedAuction(Exception):
    pass


class BadResponseMessage(Exception):
    pass


class IncorrectState(Exception):
    pass


class IllegalAction(Exception):
    pass


SUPPORTED_AUCTIONS = {
    "SAA": {
        "init": init_saa,
        "load": load_saa_variables,
        "create": save_saa_variables,
        "delete": delete_saa_variables
    },
    "CE": {
        "init": init_ce,
        "load": load_ce_variables,
        "create": save_ce_variables,
        "delete": delete_ce_variables
    },
    "SDA": {
        "init": init_sda,
        "load": load_sda_variables,
        "create": save_sda_variables,
        "delete": delete_sda_variables
    },
    "SSBA1": {
        "init": init_ssba1,
        "load": load_ssba1_variables,
        "create": save_ssba1_variables,
        "delete": delete_ssba1_variables
    },
    "SSBA2": {
        "init": init_ssba2,
        "load": load_ssba2_variables,
        "create": save_ssba2_variables,
        "delete": delete_ssba2_variables
    },
    "SSBA3": {
        "init": init_ssba3,
        "load": load_ssba3_variables,
        "create": save_ssba3_variables,
        "delete": delete_ssba3_variables
    }
}

async def _update_auction_manager(competition, session):
    auction = get_instance(competition)
    json_body = {}
    if competition["mechanism"] != "SSBA3":
        json_body = {
            "competition_id": competition['competition_id'],
            "title": competition["title"],
            "description": competition["description"],
            "auction_state": json.dumps(auction.state()),
            "mechanism": competition["mechanism"],
            "goods": competition['goods'],
            "auction_type": competition["auction_type"]
            }
    else:
        json_body = {
            "competition_id": competition['competition_id'],
            "title": competition["title"],
            "description": competition["description"],
            "auction_state": json.dumps(auction.state()),
            "mechanism": competition["mechanism"],
            "auction_type": competition["auction_type"],
            "goods": competition['goods'],
            "agents": json.dumps(competition["agents"])
            }       
    try:
        json_resp = await _send_update(competition, session, json_body,
                                        expected={'response': 'received'})
    except asyncio.exceptions.TimeoutError:
        json_resp = {'message': f'AUCTION MANAGER timeout'}
    return json_resp

async def _make_request(url, json_body, session, **kwargs):
    """
    Makes a post request to the given URL, with the current json posted as body.
    """

    resp = await session.post(url, json=json_body, **kwargs)
    resp.raise_for_status()
    json_resp = await resp.json()
    return json_resp

async def _send_message(competition, agent, session, message, **kwargs):
    json_resp = None
    try:
        competition_id = competition["competition_id"]
        agent_id = agent["id"]
        json_resp = await _make_request(f'{agent["url"]}/play', message, session)
        # json_resp = await _make_request(agent['url'], message, session)
        if json_resp is None:
            await _send_abort_messages(competition, session)
            raise BadResponseMessage("No response received")
        elif "expected" in kwargs:
            for key, value in kwargs["expected"].items():
                if key not in json_resp or json_resp[key] != value:
                    current_app.logger.error(f"Incorrect response message received: {json_resp}"
                                             + f" (expected: {kwargs['expected']})")
                    await _send_abort_messages(competition, session)
                    raise BadResponseMessage(f"Incorrect response message received: {json_resp}"
                                             + f" (expected: {kwargs['expected']})")
    except (
        ClientError,
        http_exceptions.HttpProcessingError,
    ) as e:
        current_app.logger.warning(f'aiohttp exception for {agent["url"]}/play' +
                                   f'[{getattr(e, "status", None)}]: {getattr(e, "message", None)}')
        raise e
    return json_resp

async def _send_update(competition, session, message, **kwargs):
    json_resp = None
    try:
        AUCTION_MANAGER_SERV = 'http://localhost:9000'
        competition_id = competition["competition_id"]
        json_resp = await _make_request(f'{AUCTION_MANAGER_SERV}/launch/{competition_id}', message, session)
        if json_resp is None:
            raise BadResponseMessage("No response received")
        elif "expected" in kwargs:
            for key, value in kwargs["expected"].items():
                if key not in json_resp or json_resp[key] != value:
                    current_app.logger.error(f"Incorrect response message received: {json_resp}"
                                             + f" (expected: {kwargs['expected']})")
                    raise BadResponseMessage(f"Incorrect response message received: {json_resp}"
                                             + f" (expected: {kwargs['expected']})")
    except (
        ClientError,
        http_exceptions.HttpProcessingError,
    ) as e:
        current_app.logger.warning(f'aiohttp exception for {AUCTION_MANAGER_SERV}/launch/{competition_id}' +
                                   f'[{getattr(e, "status", None)}]: {getattr(e, "message", None)}')
        raise e
    return json_resp


async def _send_abort_messages(competition, session):
    tasks = []
    for agent in competition['agents']:
        tasks.append(
            _send_abort_message(competition, agent, session)
        )
    await asyncio.gather(*tasks)


async def _send_abort_message(competition, agent, session):
    current_app.logger.debug(f'Sending Abort message to {agent["id"]}')
    json_body = {
        "message_type": "abort",
        "agent_id": agent['id'],
        "competition_id": competition['competition_id'],
    }
    json_resp = await _send_message(competition, agent, session, json_body,
                                    expected={'response': 'done'})
    update_state(competition, agent, 'ABORTED')
    return json_resp

async def _send_start_message(competition, agent, session):
    current_app.logger.debug(f'Sending Start message to {agent["id"]}')
    json_body = {
        "message_type": "start",
        "agent_id": agent['id'],
        "competition_id": competition['competition_id'],
        "mechanism": competition['mechanism'],
        "auction_type": competition["auction_type"],
        "url": competition['url'],
        "response_clock": competition['response_clock'],
        "bid_clock": competition['bid_clock'],
        "goods": competition['goods'],
        "valuation": json.dumps(agent['valuation']),
        "budget": agent['budget'],
        "allocation": json.dumps(agent['allocation']),
        "agent_type": agent['agent_type'],
        "utility": agent['utility'],
        "rationality": agent['rationality']
    }
    try:
        json_resp = await _send_message(competition, agent, session, json_body,
                                        expected={'response': 'ready'})
    except asyncio.exceptions.TimeoutError:
        current_app.logger.info(
            f'{agent["id"]} did not answer within {competition["response_clock"]} seconds.'
            + ' Assuming ready.')
        json_resp = {'message': f'{agent["id"]} timeout'}
    update_state(competition, agent, 'READY')
    return json_resp

async def _send_bid_request(competition, agent, session):
    def bid_noop(auction):
        auction.does(
            agent['id'],
            'noop')
        return auction

    current_app.logger.debug(f'Sending Bid request to {agent["id"]}')
    auction = get_instance(competition)
    json_body = {
        "message_type": "bid_request",
        "agent_id": agent['id'],
        "competition_id": competition['competition_id'],
        "auction_state": json.dumps(auction.state())
        }
    try:
        json_resp = await _send_message(competition, agent, session, json_body,
                                        expected={'response': 'received'})
    except asyncio.exceptions.TimeoutError:
        current_app.logger.info(
            f'{agent["id"]} did not answer within {competition["bid_clock"]} seconds.'
            + ' Assuming noop.')
        json_resp = {'message': f'{agent["id"]} timeout'}
        update_instance(competition, bid_noop)
        update_state(competition, agent, 'READY')
    return json_resp

async def _send_stop_message(competition, agent, session):
    current_app.logger.debug(f'Sending Stop message to {agent["id"]}')
    auction = get_instance(competition)
    json_body = {
        "message_type": "stop",
        "agent_id": agent['id'],
        "competition_id": competition['competition_id'],
        "auction_state": json.dumps(auction.state())
        }
    try:
        json_resp = await _send_message(competition, agent, session, json_body,
                                        expected={'response': 'done'})
    except asyncio.exceptions.TimeoutError:
        current_app.logger.info(
            f'{agent["id"]} did not answer within {competition["response_clock"]} seconds.'
            + ' Assuming done.')
        json_resp = {'message': f'{agent["id"]} timeout'}
    update_state(competition, agent, 'STOPPED')
    return json_resp

async def _broadcast_messages(competition, send_fonction):
    async with ClientSession(timeout=ClientTimeout(total=competition['response_clock'])) as session:
        tasks = []
        for agent in competition['agents']:
            tasks.append(
                send_fonction(competition, agent, session)
            )
        await asyncio.gather(*tasks)

async def _broadcast_updates(competition, send_fonction):
    async with ClientSession(timeout=ClientTimeout(total=competition['response_clock'])) as session:
        tasks = []
        tasks.append(
            send_fonction(competition, session)
        )
        await asyncio.gather(*tasks)


def update_instance(competition, update_function):
    try:
        auction = update_function(get_instance(competition, release_after_read=False))
        cursor = db.execute_query(
            """
            UPDATE Competition SET currentInstance = %s
            WHERE competitionId = %s""",
            pickle.dumps(auction), competition["competition_id"]
        )
        cursor.close()
    except Exception as e:
        raise e
    finally:
        db.commit()


def get_instance(competition, release_after_read=True):
    """
    Loads the latests version of the instance.
    Caution: someone else can possibly be updating it at the same time. If the lock has not
    been acquired before reading, then this is not thread-safe.
    """
    competition_id = competition["competition_id"]
    cursor = db.execute_query(
        """
        SELECT currentInstance
        FROM Competition
        WHERE competitionId = %s FOR UPDATE""",
        competition_id)
    row = cursor.fetchone()
    cursor.close()
    if release_after_read:
        db.commit()
    return pickle.loads(row[0]) if row[0] else None


def get_state(competition, agent, commit=True):
    """
    Loads the latests version of the state.
    Caution: someone else can possibly be updating it at the same time. If the lock has not
    been acquired before reading, then this is not thread-safe.
    """
    competition_id = competition["competition_id"]
    agent_id = agent["id"]
    cursor = db.execute_query(
        """
        SELECT state FROM CompetitionState
        WHERE competitionId = %s AND agentName = %s""",
        competition_id, agent_id)
    row = cursor.fetchone()
    cursor.close()
    if commit:
        db.commit()
    return row[0] if row else None


def check_all_states(competition, state):
    """
    Returns true iff all the competition states are equal to state.
    """
    competition_id = competition["competition_id"]
    cursor = db.execute_query(
        """
        SELECT state FROM CompetitionState
        WHERE competitionId = %s""",
        competition_id)
    r = True
    for row in cursor:
        if row[0] != state:
            r = False
            break
    cursor.close()
    db.commit()
    return r


def update_state(competition, agent, state, commit=True):
    db.execute_query("LOCK TABLE CompetitionState")
    cursor = db.execute_query(
        """
        DELETE FROM CompetitionState WHERE competitionId = %s AND agentName = %s""",
        competition["competition_id"], agent["id"])
    cursor.close()
    cursor = db.execute_query(
        """
        INSERT INTO CompetitionState(competitionId, agentName, state) VALUES (%s, %s, %s)""",
        competition["competition_id"], agent["id"], state)
    cursor.close()
    if commit:
        db.commit()


def start_auction(competition):
    auction = SUPPORTED_AUCTIONS[competition['mechanism']]['init'](competition)
    update_instance(competition, lambda instance: auction)
    for agent in competition['agents']:
        update_state(competition, agent, 'STARTED')
    asyncio.run(_broadcast_messages(competition, _send_start_message))
    request_bids(competition)

def submit_bid(competition, agent_id, bid):
    def send_bid(auction):
        is_legal = True
        try:
            is_legal = auction.is_legal((agent_id, bid))
        except Exception as e:
            auction.does(agent_id, "noop")
            raise IllegalAction(
                f'Bid syntax error: {e} (bid submitted: {bid}). Changing to "noop".')
        if not is_legal:
            auction.does(agent_id, "noop")
            raise IllegalAction(f'The submitted bid is illegal: {bid}. Changing to "noop".')
        auction.does(agent_id, bid)
        return auction

    def next_state(auction):
        current_app.logger.debug("Before next: " + auction.pretty())
        auction.next()
        current_app.logger.debug("After next: " + auction.pretty())
        return auction

    if get_state(competition, {'id': agent_id}) != 'PREPARING BID':
        state = get_state(competition, {'id': agent_id})
        raise IncorrectState(
            f'Bidder is not ready. Current state: {state}')
    try:
        update_instance(competition, send_bid)
        current_app.logger.debug(
            f'>>> Instance updated. Current bids: {get_instance(competition).bids}')
        update_state(competition, {'id': agent_id}, 'READY', commit=False)
    except IllegalAction as e:
        update_state(competition, {'id': agent_id}, 'READY', commit=False)
        current_app.logger.debug(
            'Illegal bid: Instance updated (with noop bid). '
            + f'Current bids: {get_instance(competition).bids}')
        current_app.logger.debug(f'>>> {get_state(competition, {"id": agent_id}, commit=False)}')
        raise e
    finally:
        current_app.logger.debug(f'>>> {get_state(competition, {"id": agent_id}, commit=False)}')
        if check_all_states(competition, 'READY'):
            update_instance(competition, next_state)
            request_bids(competition)


def request_bids(competition):
    auction = get_instance(competition)
    asyncio.run(_broadcast_updates(competition, _update_auction_manager))
    if not auction.is_terminated():
        if any(get_state(competition, agent) != 'READY'
               for agent in competition['agents']):
            states = [get_state(competition, agent)
                      for agent in competition['agents']]
            raise IncorrectState(
                f'Bidders not ready. Current states: {states}')
        for agent in competition['agents']:
            update_state(competition, agent, 'PREPARING BID')
        asyncio.run(_broadcast_messages(competition, _send_bid_request))
    else:
        asyncio.run(_broadcast_messages(competition, _send_stop_message))


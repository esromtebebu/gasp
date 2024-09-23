from core.ce import CombinatorialExchange
import gasp_server.db as db
from core.saa import SAAuction
from core.sda import SDAuction
from core.ssba1 import SSBAuction1
from core.ssba2 import SSBAuction2
from core.ssba3 import SSBAuction3
from core.model import GoodType, Bidder
from flask import current_app

def load_saa_variables(competition):
    cursor = db.execute_query(
        """
        SELECT startPrice, increment FROM SAACompetition
        WHERE competitionId = %s""",
        competition["competition_id"])
    row = cursor.fetchone()
    cursor.close()
    competition['start_price'] = row[0]
    competition['increment'] = row[1]


def save_saa_variables(competition):
    cursor = db.execute_query(
        """
        INSERT INTO SAACompetition (
        competitionId, startPrice, increment
        ) VALUES (%s, %s, %s)""",
        competition["competition_id"],
        competition["start_price"],
        competition["increment"])
    cursor.close()
    db.commit()


def delete_saa_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM SAACompetition WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_saa(competition):
    return SAAuction([Bidder(agent['id']) for agent in competition['agents']],
                     [GoodType(g) for g in competition['goods']],
                     competition['start_price'],
                     competition['increment'])


def load_ce_variables(competition):
    if 'agents' not in competition:
        return  # Agents have not been loaded, we do nothing...
    cursor = db.execute_query(
        """
        SELECT agentName, goodName, quantity FROM InitialCEAllocation
        WHERE competitionId = %s""",
        competition["competition_id"])
    for row in cursor:
        for agent in competition["agents"]:
            if agent['id'] == row[0]:
                if 'allocation' not in agent:
                    agent['allocation'] = {}
                agent['allocation'][row[1]] = row[2]
    cursor.close()


def save_ce_variables(competition):
    for agent in competition['agents']:
        for good, quantity in agent['allocation'].items():
            cursor = db.execute_query(
                """
                INSERT INTO InitialCEAllocation (
                    competitionId, agentName, goodName, quantity
                ) VALUES (%s, %s, %s, %s)""",
                competition["competition_id"],
                agent["id"],
                good,
                quantity)
    cursor.close()
    db.commit()


def delete_ce_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM InitialCEAllocation WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_ce(competition):
    allocation = [
        [agent['allocation'][good] for good in competition['goods']]
        for agent in competition['agents']
    ]
    return CombinatorialExchange([Bidder(agent['id']) for agent in competition['agents']],
                                 [GoodType(g) for g in competition['goods']],
                                 allocation,
                                 current_app.config)

def load_sda_variables(competition):
    cursor = db.execute_query(
        """
        SELECT startPrice, increment FROM SDACompetition
        WHERE competitionId = %s""",
        competition["competition_id"])
    row = cursor.fetchone()
    cursor.close()
    competition['start_price'] = row[0]
    competition['increment'] = row[1]


def save_sda_variables(competition):
    cursor = db.execute_query(
        """
        INSERT INTO SDACompetition (
        competitionId, startPrice, increment
        ) VALUES (%s, %s, %s)""",
        competition["competition_id"],
        competition["start_price"],
        competition["increment"])
    cursor.close()
    db.commit()


def delete_sda_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM SDACompetition WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_sda(competition):
    return SDAuction([Bidder(agent['id']) for agent in competition['agents']],
                     [GoodType(g) for g in competition['goods']],
                     competition['start_price'],
                     competition['increment'])

def load_ssba1_variables(competition):
    cursor = db.execute_query(
        """
        SELECT competitionId FROM SSBA1Competition
        WHERE competitionId = %s""",
        competition["competition_id"])
    row = cursor.fetchone()
    cursor.close()
    competition['competition_id'] = row[0]

def save_ssba1_variables(competition):
    cursor = db.execute_query(
        """
        INSERT INTO SSBA1Competition (
        competitionId
        ) VALUES (%s)""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def delete_ssba1_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM SSBA1Competition WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_ssba1(competition):
    return SSBAuction1([Bidder(agent['id']) for agent in competition['agents']],
                     [GoodType(g) for g in competition['goods']])

def load_ssba2_variables(competition):
    cursor = db.execute_query(
        """
        SELECT competitionId FROM SSBA2Competition
        WHERE competitionId = %s""",
        competition["competition_id"])
    row = cursor.fetchone()
    cursor.close()
    competition['competition_id'] = row[0]

def save_ssba2_variables(competition):
    cursor = db.execute_query(
        """
        INSERT INTO SSBA2Competition (
        competitionId
        ) VALUES (%s)""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def delete_ssba2_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM SSBA2Competition WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_ssba2(competition):
    return SSBAuction2([Bidder(agent['id']) for agent in competition['agents']],
                     [GoodType(g) for g in competition['goods']])

def load_ssba3_variables(competition):
    cursor = db.execute_query(
        """
        SELECT competitionId FROM SSBA3Competition
        WHERE competitionId = %s""",
        competition["competition_id"])
    row = cursor.fetchone()
    cursor.close()
    competition['competition_id'] = row[0]

def save_ssba3_variables(competition):
    cursor = db.execute_query(
        """
        INSERT INTO SSBA3Competition (
        competitionId
        ) VALUES (%s)""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def delete_ssba3_variables(competition):
    cursor = db.execute_query(
        """
        DELETE FROM SSBA3Competition WHERE competitionId = %s""",
        competition["competition_id"])
    cursor.close()
    db.commit()


def init_ssba3(competition):
    return SSBAuction3([Bidder(agent['id']) for agent in competition['agents']],
                     [GoodType(g) for g in competition['goods']])
DROP TABLE IF EXISTS InitialCEAllocation;
-- DROP TABLE IF EXISTS CECompetition;
DROP TABLE IF EXISTS CompetitionState CASCADE;
DROP TABLE IF EXISTS Agent CASCADE;
DROP TABLE IF EXISTS Good CASCADE;
DROP TABLE IF EXISTS SAACompetition CASCADE;
DROP TABLE IF EXISTS SDACompetition CASCADE;
DROP TABLE IF EXISTS SSBA1Competition CASCADE;
DROP TABLE IF EXISTS SSBA2Competition CASCADE;
DROP TABLE IF EXISTS SSBA3Competition CASCADE;
DROP TABLE IF EXISTS Competition CASCADE;

CREATE TABLE Competition (
       competitionId VARCHAR(40) PRIMARY KEY,
       title VARCHAR(200),
       description VARCHAR(500),
       responseClock INTEGER,
       bidClock INTEGER,
       mechanism VARCHAR(30),
       auctionType VARCHAR(30),
       currentInstance BYTEA
);

CREATE TABLE SAACompetition (
       competitionId VARCHAR(40) PRIMARY KEY,
       startPrice INT,
       increment INT,
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE SDACompetition (
       competitionId VARCHAR(40) PRIMARY KEY,
       startPrice INT,
       increment INT,
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE SSBA1Competition (
       competitionId VARCHAR(40) PRIMARY KEY,
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE SSBA2Competition (
       competitionId VARCHAR(40) PRIMARY KEY,
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE SSBA3Competition (
       competitionId VARCHAR(40) PRIMARY KEY,
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE Good (
       competitionId VARCHAR(40),
       goodName VARCHAR(20),
       goodImage VARCHAR,
       PRIMARY KEY (competitionId, goodName),
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE Agent (
       competitionId VARCHAR(40),
       agentName VARCHAR(40),
       agentType VARCHAR(40),
       url VARCHAR(80),
       valuation TEXT,
       budget INT,
       allocation TEXT,
       utility INT,
       rationality INT,
       PRIMARY KEY (competitionId, agentName),
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId)
);

CREATE TABLE CompetitionState (
       competitionId VARCHAR(40),
       agentName VARCHAR(40),
       state VARCHAR(20),
       PRIMARY KEY (competitionId, agentName),
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId),
       FOREIGN KEY (competitionId, agentName) REFERENCES Agent(competitionId, agentName)
);

CREATE TABLE InitialCEAllocation (
       competitionId VARCHAR(40),
       goodName VARCHAR(20),
       agentName VARCHAR(20),
       quantity INT,
       PRIMARY KEY (competitionId, goodName, agentName),
       FOREIGN KEY (competitionId) REFERENCES Competition(competitionId),
       FOREIGN KEY (competitionId, goodName) REFERENCES Good(competitionId, goodName),
       FOREIGN KEY (competitionId, agentName) REFERENCES Agent(competitionId, agentName)
);

-- CREATE TABLE CECompetition (
--        competitionId VARCHAR(40) PRIMARY KEY,
--        startPrice INT,
--        increment INT,
--        FOREIGN KEY (competitionId) REFERENCES Competition(competitionId) ON DELETE CASCADE
-- );
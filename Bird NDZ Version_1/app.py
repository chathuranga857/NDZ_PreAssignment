import json
import threading
import time
import datetime
import requests
import sqlite3
import xmltodict
from math import pow, sqrt
from flask import Flask, render_template


monitoringStarted = False

LastTimeConnected = ""
noOfMonit = None
noOfInside = None
noWithinTenMin = None
listOfViolators = []


app = Flask(__name__)


def dict_drones(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


# conn = sqlite3.connect(':memory:', check_same_thread=False)
conn = sqlite3.connect('DroneSnap.db', check_same_thread=False)
conn.row_factory = dict_drones
c = conn.cursor()


# create a pilot data table in the DB
c.execute("""CREATE TABLE IF NOT EXISTS pilot_data (
             droneSN text,
             firstName text,
             lastName test,
             phone text,
             email text,
             time TIMESTAMP,
             closestDist float,
             UNIQUE(droneSN)
             );""")


# function to get the drone info in xml and return as a dictionary
def getDroneSnapList():
    print("getDroneSnapList function is called..")
    droneSnapResp = requests.get("http://assignments.reaktor.com/birdnest/drones", json={})
    print(droneSnapResp)
    if droneSnapResp.status_code == 200:
        droneSnapXml = droneSnapResp.content
        droneSnap = xmltodict.parse(droneSnapXml)
        timeOfSnap = droneSnap["report"]["capture"]["@snapshotTimestamp"]
        droneList = droneSnap["report"]["capture"]["drone"]
        return timeOfSnap, droneList
    else:
        return "", []


# function to filter drones inside the 100m radius
def filterDronesInside(snapList):
    print("filterDronesInside function is called..")
    listOfDronesIn = []
    for drone in snapList:
        xCord = float(drone["positionX"])
        yCord = float(drone["positionY"])
        # distance to the drone from NDZ center
        distToCenter = sqrt(pow((xCord-250000), 2) + pow((yCord-250000), 2))
        # check if the position is inside the 100m zone
        if distToCenter<100000:
            listOfDronesIn.append({"droneSN": drone["serialNumber"], "distToNest": round(distToCenter/1000, 2)})
    return listOfDronesIn


# function to get the pilot info (only violators) from national registry
def getPilotInfo(serialNos):
    print("getPilotInfo function is called..")
    violatedPilots = []
    for SN in serialNos:
        print(SN["droneSN"])
        requestURL = "https://assignments.reaktor.com/birdnest/pilots/"+SN["droneSN"]
        pilotInfoResp = requests.get(requestURL, json={})
        print(pilotInfoResp)
        if pilotInfoResp.status_code == 200:
            pilotInfoJsonStr = str(pilotInfoResp.content, 'utf-8')
            print(pilotInfoJsonStr)
            pilotInfo = json.loads(pilotInfoJsonStr)
            if pilotInfo:
                pilotInfo["droneSN"] = SN["droneSN"]
                pilotInfo["distToNest"] = SN["distToNest"]
                violatedPilots.append(pilotInfo)
    print(violatedPilots)
    return violatedPilots


# function to keep the violated pilots info DB
def updatePilotDB(violatedPilots, timeOfSnap):
    print("updatePilotDB function is called..")
    for pilot in violatedPilots:
        droneSN = pilot["droneSN"]
        firstName = pilot["firstName"]
        lastName = pilot["lastName"]
        phoneNo = pilot["phoneNumber"]
        email = pilot["email"]
        distToNest = pilot["distToNest"]
        closestDist = distToNest
        with conn:
            if c.execute("SELECT 1 FROM pilot_data WHERE droneSN = '"+droneSN+"'").fetchone():
                currentDistDic = c.execute("SELECT closestDist FROM pilot_data WHERE droneSN = '"+droneSN+"'").fetchone()
                currentDist = currentDistDic["closestDist"]
                if currentDist < distToNest:
                    closestDist = currentDist
            c.execute(
                "INSERT OR REPLACE INTO pilot_data VALUES (:droneSN,:firstName, :lastName, :phone, :email, :time, :closestDist)",
                {'droneSN': droneSN, 'firstName': firstName, 'lastName': lastName, 'phone': phoneNo, 'email': email,
                 'time': timeOfSnap, 'closestDist': closestDist})


# function to keep monitoring
def monitoringLoop():
    print("monitoring loop started..")
    # run the loop every 2 seconds to get the latest update
    while True:
        # getting the drone snapshot info and update the summery
        timeOfSnap, droneList = getDroneSnapList()
        global LastTimeConnected
        LastTimeConnected = timeOfSnap
        global noOfMonit
        noOfMonit = len(droneList)

        # filtering the snap to check identify drones inside the zone
        # and update the DB and variables
        listOfDronesIn = filterDronesInside(droneList)
        global noOfInside
        noOfInside = len(listOfDronesIn)
        print("list of drones in :", listOfDronesIn)
        if len(listOfDronesIn) != 0:
            violatedPilots = getPilotInfo(listOfDronesIn)
            if len(violatedPilots) != 0:
                updatePilotDB(violatedPilots, timeOfSnap)

        # Filtering the DB to fetch the latest update on details
        # pilots violated the zone within last 10mins, and update the variables
        timeNowUTC = datetime.datetime.utcnow()
        tenMinBefore = timeNowUTC - datetime.timedelta(minutes=10)
        tenMinBeforeStr = tenMinBefore.isoformat() + "Z"
        sqlStr = "SELECT * FROM pilot_data WHERE time >= '"+tenMinBeforeStr+"' ORDER BY time DESC"
        # print(sqlStr)
        res = c.execute(sqlStr)
        result = res.fetchall()
        # print(result)
        global noWithinTenMin
        noWithinTenMin = len(result)
        global listOfViolators
        listOfViolators = json.dumps(result)

        time.sleep(2)


# API endpoint to check if the app is running
@app.route("/check", methods=['GET'])
def checkApp():
    print("check app status endpoint..")
    return "Hi there.! App is up and running."


# API endpoint to start the monitoring loop
# @app.route("/start", methods=['GET'])
# def startMonitoring():
#     print("start monitoring endpoint..")
#     global monitoringStarted
#     if (monitoringStarted):
#         return "Monitoring thread has already been started!"
#     else:
#         monitoringStarted = True
#         Thread(target=monitoringLoop())
#         return "Starting thread for NDZ monitoring.."


# API endpoint to return the WebUI
@app.route("/Monitor", methods=['GET'])
def droneZoneMonitor():
    if monitoringStarted:
        return render_template("NDZ_monitor.html")
    else:
        print("web page requested before the start of monitoring thread!")
        return render_template("NDZ_monitor.html")


# API endpoint to provide list of pilots who violated the NDZ within
# last 10min
@app.route("/UpdateList", methods=['GET'])
def UpdatedListOfViolators():
    print("List of violators within 10min endpoint..")
    return listOfViolators


# API endpoint to provide the monitoring summery figures
@app.route("/Summery", methods=['GET'])
def LastConnected():
    print("Summery endpoint..")
    summery = {"lastConnected": LastTimeConnected, "noOfMonitoring": noOfMonit,
               "noOfInside": noOfInside, "noWithinTenMin": noWithinTenMin}
    print(summery)
    return json.dumps(summery)


# starting the thread for continuous monitoring loop
monitoringThread = threading.Thread(target=monitoringLoop, args=())
monitoringThread.start()


# starting a thread for Flask app to activate the API endpoints
appThread = threading.Thread(target=app.run())
appThread.start()
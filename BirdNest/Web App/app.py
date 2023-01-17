# This Python Flask App act as the backend for the NoDronZone Monitor
# which is developed by Chathuranga De Silva for the birdnest pre-assignment
# for 'Developer Trainee, summer 2023' position.
# This web app gets the data drone snap data from the azure function which was
# developed, and keep updated info in a DB, and provide API endpoints for the UIs
# '/Monitor' endpoint returns the WebUI within the program

import json
import datetime
import requests
import sqlite3
from math import pow, sqrt
from flask import Flask, render_template, request


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


# function to keep the violated pilots info DB updated
def updatePilotDB(violatedPilots, timeOfSnap):
    print("updatePilotDB function is called..")

    # loop through the violated pilot list received
    for pilot in violatedPilots:
        # capturing data elements
        droneSN = pilot["droneSN"]
        firstName = pilot["firstName"]
        lastName = pilot["lastName"]
        phoneNo = pilot["phoneNumber"]
        email = pilot["email"]
        distToNest = pilot["distToNest"]
        closestDist = distToNest

        # Update the DB
        with conn:
            # if the pilot is already in the DB, determine the updated 'closest distance' to the nest
            if c.execute("SELECT 1 FROM pilot_data WHERE droneSN = '"+droneSN+"'").fetchone():
                # get the existing closet distance to the nest
                currentDistDic = c.execute("SELECT closestDist FROM pilot_data WHERE droneSN = '"+droneSN+"'").fetchone()
                currentDist = currentDistDic["closestDist"]
                # compare the existing closet distance with recent distance
                if currentDist < distToNest:
                    closestDist = currentDist

            # update the DB with recent data
            c.execute(
                "INSERT OR REPLACE INTO pilot_data VALUES (:droneSN,:firstName, :lastName, :phone, :email, :time, :closestDist)",
                {'droneSN': droneSN, 'firstName': firstName, 'lastName': lastName, 'phone': phoneNo, 'email': email,
                 'time': timeOfSnap, 'closestDist': closestDist})


# API endpoint to check if the app is running
@app.route("/check", methods=['GET'])
def checkApp():
    print("check app status endpoint..")
    return "Hi there.! App is up and running."


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


# API endpoint to receive data (drone snap) from the Azure Function
# and update the global variables and the DB
@app.route("/Snap", methods=['POST'])
def receiveSnap():
    print("Snap end point..")

    # get the payload (data) of the post request
    requestBody = request.json
    print(requestBody)

    # manipulating the data
    timeOfSnap = requestBody["timeOfSnap"]
    droneList = requestBody["droneList"]

    # updating global variables
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
    sqlStr = "SELECT * FROM pilot_data WHERE time >= '" + tenMinBeforeStr + "' ORDER BY time DESC"
    res = c.execute(sqlStr)
    result = res.fetchall()

    # updating global variables
    global noWithinTenMin
    noWithinTenMin = len(result)
    global listOfViolators
    listOfViolators = json.dumps(result)

    return json.dumps({"status": "done"})


if __name__ == "__main__":
    app.run()
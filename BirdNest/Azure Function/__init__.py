# This Azure Function is triggered every two seconds. it gets
# data (drone zone snap as an XML) from Reaktor API, and then convert
# to Python Dictionary, manipulate and send it to the backend application
# in a payload of a post request.

import azure.functions as func
import logging
import requests
import xmltodict
import json

def main(mytimer: func.TimerRequest) -> None:
    logging.info("executing the function..")

    # make the get request to Reaktor API
    droneSnapResp = requests.get("http://assignments.reaktor.com/birdnest/drones", json={})
    logging.info(droneSnapResp)

    # if the get reqeust was successful, then manipulate the data
    if droneSnapResp.status_code == 200:
        droneSnapXml = droneSnapResp.content
        # converting the xml content to python dictionary
        droneSnap = xmltodict.parse(droneSnapXml)
        # manipulating the data
        timeOfSnap = droneSnap["report"]["capture"]["@snapshotTimestamp"]
        droneList = droneSnap["report"]["capture"]["drone"]
        snapBody = {"timeOfSnap": timeOfSnap, "droneList": droneList}
        logging.info("snapBody before dumps: ")
        logging.info(snapBody)
        snapBodyJson = json.dumps(snapBody)
        logging.info("snapBody after dumps: ")
        logging.info(snapBodyJson)

        try:
            # make the post reqeust to backend app
            headers = {'Content-Type': 'application/json'}
            postResp = requests.post("https://birdnest-cds1.azurewebsites.net/Snap", json=snapBody)
            logging.info(postResp)
        except Exception as e:
            print(e)
            logging.info("post request was not successful")

    else:
        logging.info("get request was not successful")
        print("get request was not successful")
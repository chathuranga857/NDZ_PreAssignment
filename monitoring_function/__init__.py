import azure.functions as func
import logging
import requests
import xmltodict
import json

# def main(mytimer: func.TimerRequest) -> None:
logging.info("executing the function..")
droneSnapResp = requests.get("http://assignments.reaktor.com/birdnest/drones", json={})
print(droneSnapResp)
if droneSnapResp.status_code == 200:
    droneSnapXml = droneSnapResp.content
    droneSnap = xmltodict.parse(droneSnapXml)
    timeOfSnap = droneSnap["report"]["capture"]["@snapshotTimestamp"]
    droneList = droneSnap["report"]["capture"]["drone"]
    snapBody = {"timeOfSnap": timeOfSnap, "droneList": droneList}
    logging.info("snapBody before dumps: ")
    print("snapBody before dumps: ")
    logging.info(snapBody)
    print(snapBody)
    snapBodyJson = json.dumps(snapBody)
    logging.info("snapBody after dumps: ")
    logging.info(snapBodyJson)
    print("snapBody after dumps: ")
    print(snapBodyJson)

    try:
        headers = {'content-type': 'application/json'}
        postResp = requests.request("POST", "http://birdnest-cds1.azurewebsites.net/Snap", headers=headers, json=snapBodyJson)
        # postResp = requests.post("http://birdnest-cds1.azurewebsites.net/Snap", json=snapBodyJson)
        logging.info(postResp)
        print(postResp)
    except:
        logging.info("post request was not successful")
        print("post request was not successful")

else:
    logging.info("get request was not successful")
    print("get request was not successful")

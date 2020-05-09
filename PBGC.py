# coding=utf-8
# PBGC.py
# Push Button Get Candy
# Created by Chris Hannemann on 2017-01-23 
# Adapted by Pieter Biemond on 2020-05-09

import urllib.request
import requests
import json
import time
import dateutil.parser
import datetime
import re
from dateutil.tz import tzlocal
from PBGC_config import *
from time import sleep
from rpi_backlight import backlight

def convertGlucose(glucoseMgDl):
   if glucoseUnit[:4]=='mmol': 
     return glucoseMgDl/18.0
   else:
     return glucoseMgDl
	 
	 
def addNSToken(req):
	if (nsToken!=""):
		return req+"&token="+nsToken 
	else:
		return req

def getGlucoseNS():
# Get most recent glucose from NS
	currentGlucoseRequest = "api/v1/entries.json?count=1"
	currentGlucoseURL = addNSToken(nsURL + currentGlucoseRequest)
	currentGlucoseResponse = urllib.request.urlopen(currentGlucoseURL).read().decode('utf-8')
	currentGlucoseData = json.loads(currentGlucoseResponse)
	currentGlucose = convertGlucose(currentGlucoseData[0]["sgv"])
	currentGlucoseTime = dateutil.parser.parse(currentGlucoseData[0]["dateString"])
	print("Current Glucose (Nightscout): %.1f %s at %s" % (currentGlucose, glucoseUnit, currentGlucoseTime.astimezone(tzlocal()).strftime("%Y-%d-%m %H:%M:%S")))
	# Calculate staleness of the data ...
	ageCurrentGlucose = round((datetime.datetime.now().replace(tzinfo=tzlocal()) - currentGlucoseTime).total_seconds())
	print("                              ... {} seconds ago".format(ageCurrentGlucose))
	return currentGlucose

def getGlucoseDex():
	# Get most recent glucose from Dexcom Share
	# Code adapted from the Share to Nightscout bridge, via @bewest and @shanselman
	# https://github.com/bewest/share2nightscout-bridge
	# Login and get a Dexcom Share session ID
	# ... need to only do this once and then refresh the sessionID as necessary
	dexLoginURL = "https://share1.dexcom.com/ShareWebServices/Services/General/LoginPublisherAccountByName"
	dexLoginPayload = {
            "User-Agent": "Dexcom Share/3.0.2.11 CFNetwork/711.2.23 Darwin/14.0.0",
            "applicationId": "d89443d2-327c-4a6f-89e5-496bbb0317db",
            "accountName": dexUsername,
            "password": dexPassword,
        }
	dexLoginHeaders = {
	    'content-type': "application/json",
	    'accept': "application/json",
	    }
	dexLoginResponse = requests.post(dexLoginURL, json=dexLoginPayload, headers=dexLoginHeaders)
	sessionID = dexLoginResponse.json()
	# Use the session ID to retrieve the latest glucose record
	dexGlucoseURL = "https://share1.dexcom.com/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues"
	dexGlucoseQueryString = {"sessionID":sessionID,"minutes":"1440","maxCount":"1"}
	dexGlucoseHeaders = {
	    'content-type': "application/json",
	    'accept': "application/json",
	    }
	dexGlucoseResponse = requests.post(dexGlucoseURL, headers=dexGlucoseHeaders, params=dexGlucoseQueryString)
	dexGlucoseResponseJSON = dexGlucoseResponse.json()
	dexGlucose = dexGlucoseResponseJSON[0]["Value"]
	dexGlucoseEpochString = dexGlucoseResponseJSON[0]["ST"]
	dexGlucoseEpoch = int(re.match('/Date\((\d+)\)/', dexGlucoseEpochString).group(1))/1e3
	dexGlucoseTimestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(dexGlucoseEpoch))
	print("Current Glucose (Share):      " + str(dexGlucose) + " " + glucoseUnit + " at " + time.strftime("%-I:%M:%S %p on %A, %B %d, %Y",time.localtime(dexGlucoseEpoch)))
	return dexGlucose

def getPredictionLoop():
	# Get eventual glucose from Loop via NS
	eventualGlucoseRequest = "api/v1/devicestatus.json?count=2"
	eventualGlucoseURL = addNSToken(nsURL + eventualGlucoseRequest)
	eventualGlucoseResponse = urllib.request.urlopen(eventualGlucoseURL).read().decode('utf-8')
	eventualGlucoseData = json.loads(eventualGlucoseResponse)
	# I'm unsure how to better accomplish what is happening below; the correct device entry may not be the 0th or 1st entry in the returned array ... need to search for it?
	try:
	    eventualGlucose = convertGlucose(eventualGlucoseData[0]["loop"]["predicted"]["values"][-1])
	    predictionStartTime = dateutil.parser.parse(eventualGlucoseData[0]["loop"]["predicted"]["startDate"])
	    predictionEndTime = predictionStartTime + datetime.timedelta(minutes=(5*(len(eventualGlucoseData[0]["loop"]["predicted"]["values"])-5)))
	except:
	    eventualGlucose = convertGlucose(eventualGlucoseData[1]["loop"]["predicted"]["values"][-1])
	    predictionStartTime = dateutil.parser.parse(eventualGlucoseData[1]["loop"]["predicted"]["startDate"])
	    predictionEndTime = predictionStartTime + datetime.timedelta(minutes=(5*(len(eventualGlucoseData[1]["loop"]["predicted"]["values"])-5)))
	print("Eventual Glucose (Loop):  %.1f %s at %s" % (eventualGlucose, glucoseUnit, predictionEndTime.astimezone(tzlocal()).strftime("%Y-%d-%m %H:%M:%S")))
	print("                              ... predicted at " + predictionStartTime.astimezone(tzlocal()).strftime("%Y-%d-%m %H:%M:%S"))
	return eventualGlucose

def main():
	# Set timing for checking on Skittle availability
	checkTime = time.time() + 1
	while True:
		# See if it is time to do the periodic check	
		if time.time() > checkTime:
			try:
				currentGlucoseNS = getGlucoseNS()
				eventualGlucoseLoop = getPredictionLoop()
				# Set the backlight on if currentGlucoseNS or eventualGlucoseLoop is below lowGlucoseThreshold. Otherwise turn off backlight
				enableScreen = (currentGlucoseNS < lowGlucoseThreshold) || (eventualGlucoseLoop < lowGlucoseThreshold )
				backLightOn=backlight.power
				if (enableScreen && !backLightOn)
					backlight.power=True
					#xscreensaver-command -deactivate
				elif (!enableScreen && backLightOn)
					backlight.power=False

				#currentGlucoseDex = getGlucoseDex()
			except:
				pass
			checkTime = time.time() + 60
		sleep(1)
        
if __name__ == "__main__":
	print("rpi-backlight for nightscout started")
	main()

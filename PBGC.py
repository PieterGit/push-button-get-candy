# coding=utf-8
# PBGC.py
# Push Button Get Candy
# Created by Chris Hannemann on 2017-01-23

import urllib
import requests
import json
import time
import dateutil.parser
import datetime
from dateutil.tz import tzlocal
from PBGC_config import *
from pivotpi import *
from time import sleep
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
skittle_pivot = PivotPi()

def getGlucoseNS():
# Get most recent glucose from NS
	currentGlucoseRequest = "api/v1/entries.json?count=1"
	currentGlucoseURL = nsURL + currentGlucoseRequest
	currentGlucoseResponse = urllib.urlopen(currentGlucoseURL).read().decode('utf-8')
	currentGlucoseData = json.loads(currentGlucoseResponse)
	currentGlucose = currentGlucoseData[0]["sgv"]
	currentGlucoseTime = dateutil.parser.parse(currentGlucoseData[0]["dateString"])
	print("Current Glucose (Nightscout) = " + str(currentGlucose) + " " + glucoseUnit + " at " + currentGlucoseTime.astimezone(tzlocal()).strftime("%-I:%M:%S %p on %A, %B %d, %Y"))
	# Calculate staleness of the data ...
	ageCurrentGlucose = round((datetime.datetime.now().replace(tzinfo=tzlocal()) - currentGlucoseTime).total_seconds())
	print("   ... {} seconds ago".format(ageCurrentGlucose))
	return currentGlucose


def getGlucoseDex():
	# Get most recent glucose from Dexcom Share
	# Code adapted from the Share to Nightscout bridge, via @bewest and @shanselman
	# https://github.com/bewest/share2nightscout-bridge
	# Login and get a Dexcom Share session ID
	# ... need to only do this once and then refresh the sessionID as necessary
	dexLoginURL = "https://share1.dexcom.com/ShareWebServices/Services/General/LoginPublisherAccountByName"
	dexLoginPayload = "{\n\t\"User-Agent\":\"Dexcom Share/3.0.2.11 CFNetwork/711.2.23 Darwin/14.0.0\",\n\t\"applicationId\":\"d89443d2-327c-4a6f-89e5-496bbb0317db\",\n\t\"accountName\":\""+dexUsername+"\",\n\t\"password\":\""+dexPassword+"\"\n}"
	dexLoginHeaders = {
	    'content-type': "application/json",
	    'accept': "application/json",
	    }
	dexLoginResponse = requests.request("POST", dexLoginURL, data=dexLoginPayload, headers=dexLoginHeaders)
	sessionID = json.loads(dexLoginResponse.text)
	# print(sessionID)
	# Use the session ID to retrieve the latest glucose record
	dexGlucoseURL = "https://share1.dexcom.com/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues"
	dexGlucoseQueryString = {"sessionID":sessionID,"minutes":"1440","maxCount":"1"}
	dexGlucoseHeaders = {
	    'content-type': "application/json",
	    'accept': "application/json",
	    }
	dexGlucoseResponse = requests.request("POST", dexGlucoseURL, headers=dexGlucoseHeaders, params=dexGlucoseQueryString)
	dexGlucoseResponseJSON = json.loads(dexGlucoseResponse.text)
	# print(json.dumps(dexGlucoseResponseJSON, indent=2, sort_keys=False))
	dexGlucose = dexGlucoseResponseJSON[0]["Value"]
	dexGlucoseEpochString = dexGlucoseResponseJSON[0]["ST"]
	dexGlucoseEpoch = int(dexGlucoseEpochString[dexGlucoseEpochString.find("(")+1:dexGlucoseEpochString.find(")")])/1e3
	dexGlucoseTimestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(dexGlucoseEpoch))
	print("Current Glucose (Share) = " + str(dexGlucose) + " " + glucoseUnit + " at " + time.strftime("%-I:%M:%S %p on %A, %B %d, %Y",time.localtime(dexGlucoseEpoch)))
	return dexGlucose


def getPredictionLoop():
	# Get eventual glucose from Loop via NS
	eventualGlucoseRequest = "api/v1/devicestatus.json"
	eventualGlucoseURL = nsURL + eventualGlucoseRequest
	eventualGlucoseResponse = urllib.urlopen(eventualGlucoseURL).read().decode('utf-8')
	eventualGlucoseData = json.loads(eventualGlucoseResponse)
	# I'm unsure how to better accomplish what is happening below; the correct device entry may not be the 0th or 1st entry in the returned array ... need to search for it?
	try:
	    eventualGlucose = eventualGlucoseData[0]["loop"]["predicted"]["values"][-1]
	    predictionStartTime = dateutil.parser.parse(eventualGlucoseData[0]["loop"]["predicted"]["startDate"])
	    predictionEndTime = predictionStartTime + datetime.timedelta(minutes=(5*(len(eventualGlucoseData[0]["loop"]["predicted"]["values"])-5)))
	except:
	    eventualGlucose = eventualGlucoseData[1]["loop"]["predicted"]["values"][-1]
	    predictionStartTime = dateutil.parser.parse(eventualGlucoseData[1]["loop"]["predicted"]["startDate"])
	    predictionEndTime = predictionStartTime + datetime.timedelta(minutes=(5*(len(eventualGlucoseData[1]["loop"]["predicted"]["values"])-5)))
	# Or just hard-code it, for testing
	# eventualGlucose = 70
	print("Eventual Glucose (Loop) = " + str(eventualGlucose) + " " + glucoseUnit + " at " + predictionEndTime.astimezone(tzlocal()).strftime("%-I:%M:%S %p on %A, %B %d, %Y"))
	print("   ... predicted at " + predictionStartTime.astimezone(tzlocal()).strftime("%-I:%M:%S %p on %A, %B %d, %Y"))
	return eventualGlucose


def calculateSkittles(glucose):
	# Calculate the number of Skittles to deliver
	# this could be done in many ways:
	#  1. Current glucose is low
	#  2. Eventual glucose is low <- what is being done in this example
	#  3. Near-term predicted glucose is low (30 min to 120 min, for example)
	if glucose <= lowGlucoseThreshold:
	    nSkittles = min(int(round((treatmentTarget - glucose) / CSF / carbsPerSkittle)), maxSkittles)
	else:
	    nSkittles = 0
	print("PBGC calculates that " + str(nSkittles) + " should be delivered.")
	return nSkittles


def skittleWiggle(sNum):
	# Turn the motor! Deliver the goods!
	# https://www.dexterindustries.com/pivotpi-tutorials-documentation/pivotpi-program-the-servo-controller-for-the-raspberry-pi/program-the-raspberry-pi-servo-controller-in-python/
	# https://github.com/DexterInd/PivotPi/tree/master/Software/Python
    # Turn on the LED for each Skittle
    skittle_pivot.led(SERVO_1,100)
    # Rotate from 0 deg to 175 deg, stopping at 135 deg and 45 deg in a wiggle pattern: 0 - 135 - 45 - 175 (drop Skittle)
    # Note: servo appears to be out of calibration; a set point of 175 deg seems to result in 180 deg
    # Because of dual Skittle slots in platter, rotation order needs to reverse after each Skittle (hence the modulo operator)
    skittle_pivot.angle(SERVO_1,45+sNum%2*90)
    # print(str(45+sNum%2*90))
    sleep(.3)
    skittle_pivot.angle(SERVO_1,135-sNum%2*90)
    # print(str(135-sNum%2*90))
    sleep(.3)    
    skittle_pivot.angle(SERVO_1,sNum%2*175)
    # print(str(sNum%2*175))
    print("Skittle #: " + str(sNum+1))
    sleep(.5)
    # Turn the LED off
    skittle_pivot.led(SERVO_1,0)
    sleep(.5)	    


# Other functions to be written:

	# Confirm the Skittles were delivered; locally, temporarily adjust the predicted value
	# Depending on the hardware, you could use an encoder to check that Skittles actually went down the chute, for example
	# To prevent repeated delivery, the carb value of the delivered Skittles can be accounted for in future calculations, at least in the near-term

	# Tell (Nightscout? Loop? Another nutrition app?) that carbs were consumed!

def main():
	# Listen for the trigger
	while True:
		input_state = GPIO.input(18)
		if input_state == False:
			# Acknowledge button press
			print("Button Pressed! P. B. G. C. GO! GO! GO!")
			# Calculate the number of Skittles to deliver
			currentGlucoseDex = getGlucoseDex()
			currentGlucoseNS = getGlucoseNS()
			eventualGlucoseLoop = getPredictionLoop()
			nSkittles = calculateSkittles(eventualGlucoseLoop)       
			# Make sure the LED corresponding to the particular servo is off
			# For the code below, we've attached the servo to the first port
			skittle_pivot.led(SERVO_1,0) 
			# Iterate over the number of Skittles to deliver       
			for sNum in range(0,nSkittles):	
				skittleWiggle(sNum)
			print("PBGC delivered " + str(nSkittles) + " Skittles!")
	        # Return to a neutral state so that it is ready to deliver next batch
	        skittle_pivot.angle(SERVO_1,90)
        

if __name__ == "__main__":
	main()

# coding=utf-8
# PBGC.py
# Push Button Get Candy
# Created by Chris Hannemann on 2017-01-23

import urllib.request
import json
import dateutil.parser
import datetime
from dateutil.tz import tzlocal

# Set user parameters
# Perhaps this would be better done in a config file ...
nsURL = "https://MyNightscoutURL.herokuapp.com/" # or perhaps like "https://MyNightscoutURL.azurewebsites.net/"
glucoseUnit = "mg/dL" # selected unit
carbRatio = 12 # grams of carbohydrate per unit of fast-acting insulin
ISF = 40 # mg/dL or mmol/L per unit fast-acting insulin
CSF = ISF / carbRatio # mg/dL or mmol/L per gram of carbohydrate
carbsPerSkittle = 0.88 # grams of carbohydrate per Skittle
lowGlucoseThreshold = 70 # mg/dL or mmol/L, below which the user requires Skittles
treatmentTarget = 90 # mg/dL or mmol/L, the target glucose to treat to

# Listen for the trigger!

# Get most recent glucose from NS
currentGlucoseRequest = "api/v1/entries.json?count=1"
currentGlucoseURL = nsURL + currentGlucoseRequest
currentGlucoseResponse = urllib.request.urlopen(currentGlucoseURL).read().decode('utf-8')
currentGlucoseData = json.loads(currentGlucoseResponse)
currentGlucose = currentGlucoseData[0]["sgv"]
currentGlucoseTime = dateutil.parser.parse(currentGlucoseData[0]["dateString"])
print("Current Glucose = " + str(currentGlucose) + " " + glucoseUnit + " at " + currentGlucoseTime.astimezone().strftime("%-I:%M:%S %p on %A, %B %d, %Y"))

# Calculate staleness of the data ...
ageCurrentGlucose = round((datetime.datetime.now().replace(tzinfo=tzlocal()) - currentGlucoseTime).total_seconds())
print("                  {} seconds ago".format(ageCurrentGlucose))

# Get eventual glucose from Loop via NS
eventualGlucoseRequest = "api/v1/devicestatus.json"
eventualGlucoseURL = nsURL + eventualGlucoseRequest
eventualGlucoseResponse = urllib.request.urlopen(eventualGlucoseURL).read().decode('utf-8')
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
print("Eventual Glucose = " + str(eventualGlucose) + " " + glucoseUnit + " at " + predictionEndTime.astimezone().strftime("%-I:%M:%S %p on %A, %B %d, %Y"))
print("                  predicted at " + predictionStartTime.astimezone().strftime("%-I:%M:%S %p on %A, %B %d, %Y"))

# Calculate the number of Skittles to deliver
# this could be done in many ways:
#  1. Current glucose is low
#  2. Eventual glucose is low <- what is being done in this example
#  3. Near-term predicted glucose is low (30 min to 120 min, for example)
if eventualGlucose <= lowGlucoseThreshold:
    nSkittles = round((treatmentTarget - eventualGlucose) / CSF / carbsPerSkittle)
else:
    nSkittles = 0

# Turn the motor! Deliver the goods!
# https://www.dexterindustries.com/pivotpi-tutorials-documentation/pivotpi-program-the-servo-controller-for-the-raspberry-pi/program-the-raspberry-pi-servo-controller-in-python/
# https://github.com/DexterInd/PivotPi/tree/master/Software/Python
print("PB→GC delivers " + str(nSkittles) + " Skittles!")

# Confirm the Skittles were delivered; locally, temporarily adjust the predicted value
# Depending on the hardware, you could use an encoder to check that Skittles actually went down the chute, for example
# To prevent repeated delivery, the carb value of the delivered Skittles can be accounted for in future calculations, at least in the near-term

# Tell (Nightscout? Loop? Another nutrition app?) that carbs were consumed!

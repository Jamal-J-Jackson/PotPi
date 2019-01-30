import time
import board
import busio
import adafruit_sht31d
from adafruit_seesaw.seesaw import Seesaw
from decimal import *
from subprocess import check_output
import datetime as dt
import urllib.request
import logging
import configparser
import sys
import math
import os
from influxdb import InfluxDBClient

#global loopcount, humidifierstatusm heaterstatus, fanstatus, templow, temphigh, humlow, humhigh, heateroncycles, heateroffcycles, fanoncycles, fanoffcycles, humidifieroncycles humidifieroffcycles, lastpictime, i2c, sensor, logger, handler, formatter, coldprotecttemp, coldprotecttriggered, client

#Set up logging
logger = logging.getLogger()
handler = logging.FileHandler('/home/pi/Desktop/growPi.log', 'a+')
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
logger.debug("Script started.")
ss = []
# set up i2c connections
try:
#connect i2c bus 1
    i2c = busio.I2C(board.SCL, board.SDA)
#connect i2c bus 3
    i2c3 = busio.I2C(board.D17, board.D4)
except Exception as e:
    logger.debug("Could not get i2c bus: "+str(e))
#Connect to sensors
try:
    sensor = adafruit_sht31d.SHT31D(i2c)
    ss.insert(0, Seesaw(i2c, addr=0x36))
    ss.insert(1, Seesaw(i2c, addr=0x37))
    ss.insert(2, Seesaw(i2c3, addr=0x36))
    ss.insert(3, Seesaw(i2c3, addr=0x37))

except Exception as e:
    logger.debug("Could not get SHT31-D Temp/Humidity or soil sensors: "+str(e))

# Configure InfluxDB connection variables
host = "localhost" # My Ubuntu NUC
port = 8086 # default port
user = "" # the user/password created for the pi, with write access
password = "" 
dbname = "_internal" # the database we created earlier
# Create the InfluxDB client object
client = InfluxDBClient(host, port, user, password, dbname)
loopcount = 0
fanoncycles = 0
fanoffcycles = 0
humidifieroncycles = 0
humidifieroffcycles = 0
heateroncycles = 0
heateroffcycles = 0
humidifierstatus = "not set"
fanstatus = "not set"
heaterstatus = "not set" 
coldprotecttriggered = 0    
starthr = 8 # must be before stop hr, same day
startmin = 1
stophr = 16 # must be after start hr, same day
stopmin = 1
piccount = 0
lastpictime = dt.datetime.now()
picfoldername = dt.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
vpdset = 9.0 #set default value
nightvpdset = 7.5 #set default value

def getsoilmoisture(i):
    global ss
    try:
        #get moisture
        sens = ss[i].moisture_read()
        return sens
    except Exception as e:
        logging.debug("Could not get temperature from Sensor "+str(i)+": "+str(e))

def getsoiltemp(i):
    global ss
    try:
        #read temperature from the temperature sensor
        temp = ss[i].get_temp()
        return temp
    except Exception as e:
        logging.debug("Could not get moisture reading from Sensor "+str(i)+": "+str(e))

def makepicdir(folder):
    try:
        os.makedirs("/home/pi/Pictures/"+folder)
    except Exception as e:
        logger.debug("Could not create picture folder: "+str(e))

def shipEnviroData(grafTemp, grafHum, grafvpd, soil0, soil1, soil2, soil3):
    global sensortype
    iso = time.ctime()
    # Create the JSON data structure
    enviroData = [
        {
            "measurement": "rpi-sht-31d",
            "tags": {
                "sensortype": "environmental",
            },
            "time": iso,
            "fields": {
                "1.01" : grafTemp,
                "2.01": grafHum,
                "3.01": grafvpd,
                "4.01": soil0,
                "5.01": soil1,
                "6.01": soil2,
                "7.01": soil3
            }
        }
    ]
    try:
        client.write_points(enviroData, time_precision='ms')
    except Exception as e:
        logger.debug("Cannot ship data to grafana: "+str(e))

#Read config
def readconfig():
    global lastpictime, nighttemphigh, nighttemplow, nighthumhigh, nighthumlow, temphigh, templow, humhigh, humlow, coldprotecttemp, sleeptime, vpdset, nightvpdset,units
    try:
        config = configparser.ConfigParser()
        config.read('config.ini')
        temphigh = Decimal(config['DEFAULT']['HIGHTEMP']) #28.0
        templow = Decimal(config['DEFAULT']['LOWTEMP']) #25.0
        humhigh = Decimal(config['DEFAULT']['HIGHHUM']) #40.0
        humlow = Decimal(config['DEFAULT']['LOWHUM']) #30.0
        nighttemphigh = Decimal(config['DEFAULT']['NIGHTHIGHTEMP']) #28.0
        nighttemplow = Decimal(config['DEFAULT']['NIGHTLOWTEMP']) #25.0
        nighthumhigh = Decimal(config['DEFAULT']['NIGHTHIGHHUM']) #40.0
        nighthumlow = Decimal(config['DEFAULT']['NIGHTLOWHUM']) #30.0
        sleeptime = Decimal(config['DEFAULT']['SLEEPTIME']) #1
        coldprotecttemp = Decimal(config['DEFAULT']['COLDPROTECTTEMP']) #15.0
        honcount = Decimal(config['DEFAULT']['HONCOUNT'])
        hoffcount = Decimal(config['DEFAULT']['HOFFCOUNT'])
        humoncount = Decimal(config['DEFAULT']['HUMONCOUNT'])
        humoffcount = Decimal(config['DEFAULT']['HUMOFFCOUNT'])
        fanoncount = Decimal(config['DEFAULT']['FANONCOUNT'])
        fanoffcount = Decimal(config['DEFAULT']['FANOFFCOUNT'])
        vpdset = Decimal(config['DEFAULT']['VPD'])
        nightvpdset = Decimal(config['DEFAULT']['NIGHTVPD'])
        units = config['DEFAULT']['UNITS']
        
    except Exception as e:
        logger.debug("Could not read configuration: "+str(e))
        exit()

def calcVPD():
    global temp, humidity, vpd
    try:
        ftemp=float(temp)
        fhumidity=float(humidity)
        VPsat = 6.11*(10**((7.5 * ftemp) / (237.3 + ftemp)))#  Saturation vapor pressure
        vpd = ((100.0 - fhumidity) /100.0)/10 * VPsat # Vapor Pressure Deficit in Pascals
        logger.debug("VPD: "+str(round(Decimal(vpd),2)))
        return vpd
    except Exception as e:
        logger.debug("Could not calculate VPD: "+str(e))

def takepic():
    if when == True:
#Day
        global lastpictime, piccount, picfoldername
        split = dt.datetime.now() - lastpictime
#Take a picture if 5 minutes have passed
        if (split.total_seconds() > 298) or (piccount == 0):
            try:
                urllib.request.urlretrieve("http://192.168.0.90/axis-cgi/jpg/image.cgi?resolution=1280x720", "/home/pi/Pictures/"+picfoldername+"/"+str(piccount)+".jpg")
                lastpictime = dt.datetime.now()
                piccount += 1
                logger.debug("Image saved")
            except Exception as e:
                logger.debug("Could not take picture: "+str(e))

def fanon():
    global fanoncycles
    try:
        check = check_output("python /usr/local/bin/wemo switch fan on",shell=True)
        fanoncycles += 1
        logger.debug("Fan turned on. Count: "+str(fanoncycles))
    except Exception as e:
        logger.debug("Could not turn on fan: "+str(e))

def humidifieron():
    global humidifieroncycles
    try:
        check = check_output("python /usr/local/bin/wemo switch humidifier on",shell=True)
        humidifieroncycles += 1    
        logger.debug("Humidifier turned on. Count: "+str(humidifieroffcycles))
    except Exception as e:
        logger.debug("Could not turn humidifier on: "+str(e))

def fanoff():
    global fanoffcycles
    try:
        check = check_output("python /usr/local/bin/wemo switch fan off",shell=True)
        fanoffcycles += 1
        logger.debug("Fan turned off. Count: "+str(fanoffcycles))
    except Exception as e:
        logger.debug("Could not turn fan off: "+str(e))

def humidifieroff():
    global humidifieroffcycles
    try:
        check_output("python /usr/local/bin/wemo switch humidifier off",shell=True)
        humidifieroffcycles += 1
        logger.debug("Humidifier turned off. Count: "+str(humidifieroffcycles))
    except Exception as e:
        logger.debug("Could not turn humidifier off: "+str(e))

def heateron():
    global heateroncycles
    try:
        check_output("python /usr/local/bin/wemo switch 'heater' on",shell=True)
        heateroncycles += 1
        logger.debug("Heater turned on. Count: "+str(heateroncycles))
    except Exception as e:
        logger.debug("Could not turn heater on: "+str(e))

def heateroff():
    global heateroffcycles
    try:
        check_output("python /usr/local/bin/wemo switch 'heater' off",shell=True)
        heateroffcycles += 1
        logger.debug("Heater turned off. Count: "+str(heateroffcycles))
    except Exception as e:
        logger.debug("Could not turn heater off: "+str(e))

def gettemp():
    #Get current temperature
    try:
        temp = round(sensor.temperature,1)
        return round(Decimal(temp),2)
    except Exception as e:
        logger.debug("Could not get temperature: "+str(e))

def gettempf():
   #Get temp in freedom units
   try:
        temp = round(sensor.temperature*1.8+32,1)
        return round(Decimal(temp),2)
   except Exception as e:
        logger.debug("Could not calculate freedom units: " +str(e))

def tempunit():
    global units

  #Determine what unit to use
    if units == 'F':
      try:
        temp = round(sensor.temperature*1.8+32,1)
        return round(Decimal(temp),2)
      except Exception as e:
        logger.debug("Could not calculate freedom units: " +str(e))
    elif units == 'C':
        temp = round(sensor.temperature,1)
        return round(Decimal(temp),2)


def gethum():
    #Get current humidity
    try:
        humidity = round(sensor.relative_humidity,1)
        return round(Decimal(humidity),2)
    except Exception as e:
        logger.debug("Could not get humidity: "+str(e))

def checkfan():
    try:
        check = check_output("python /usr/local/bin/wemo -v switch fan status",shell=True)
        return str(check)
    except Exception as e:
        logger.debug("Could not get fan status: "+str(e))

def checkhumidifier():
    try:
        check = check_output("python /usr/local/bin/wemo -v switch humidifier status",shell=True)
        return str(check)
    except Exception as e:
        logger.debug("Could not get humidifier status: "+str(e))

def checkheater():
    try:
        check = check_output("python /usr/local/bin/wemo -v switch 'heater' status",shell=True)
        return str(check)
    except Exception as e:
        logger.debug("Could not get heater status: "+str(e))


def fixvpd():
    global vpd, when, vpdset, nightvpdset
#day
    if when == True:
        if vpd < vpdset:
            if "on" in humidifierstatus:
                logger.debug("VPD is below target, turning humidifier off.")
                humidifieroff()
        elif vpd > vpdset:
            if "off" in humidifierstatus:
                logger.debug("VPD is above target, turning humidifier on.")
                humidifieron()
#night
    elif when == False:
        if vpd < nightvpdset:
            if "on" in humidifierstatus:
                logger.debug("VPD is below target, turning humidifier off.")
                humidifieroff()
            if "off" in fanstatus:
                if humidity >= nighthumhigh:
                    logger.debug("Humidity is "+str(humidity)+", turning fan on.")
                    fanon()

        elif vpd > nightvpdset:
            if "off" in humidifierstatus:
                logger.debug("VPD is above target, turning humidifier on.")
                humidifieron()
            if "on" in fanstatus:
                if humidity <= nighthumhigh:
                    logger.debug("Humidity is "+str(humidity)+", turning fan off.")
                    fanoff()

            


def fixtemp():
    global temp, temphigh, nighttemphigh, fanstatus, fanoncycles, templow, nighttemplow, fanoffcycles, coldprotecttriggered, coldprotecttemp, when, heaterstatus
    if temp <= coldprotecttemp:
        try:
            if "off" in heaterstatus:
                logger.debug("Temperature has fallen below Cold Protect temperature of "+str(coldprotecttemp)+", turning heater on.")
                heateron()
                coldprotecttriggered = 1
                return
        except Exception as e:
            logger.debug("Could not turn on heater for cold protection: "+str(e))
    if when == False:
#Night
        logger.debug("Night temp adjustment:")
        if temp >= (nighttemphigh):
            if "on" in heaterstatus:
                logger.debug("Temperature is "+str(temp)+", turning heater off.")
                heateroff()
            elif "off" in heaterstatus:
                logger.debug("Temp is above High Temp setting. Heater is off already.")
            else:
                logger.debug(type(fanstatus))
                logger.debug("Fan status is "+fanstatus)
        elif temp <= (nighttemplow):
            if "off" in heaterstatus:
                logger.debug("Temperature is "+str(temp)+", turning heater on.")
                heateron()
            elif  "on" in heaterstatus:
                logger.debug("Temp is below Low Temp setting. Heater is on already.")
            else:
                logger.debug(type(fanstatus))
                logger.debug("Fan status is "+fanstatus)

        if coldprotecttriggered == 1:
            if temp >= nighttemplow:
                try:
                    if "on" in heaterstatus:
                        logger.debug("Temperature has recovered to Low Temperature setting. Turning heater off.")
                        heateroff()
                        coldprotecttriggered = 0
                except Exception as e:
                    logger.debug("Could not turn off heater to exit cold protection: "+str(e))

    elif when == True:
#Day
        logger.debug("Day temp adjustment:")
        if temp >= temphigh:
            if "off" in fanstatus:
                logger.debug("Temperature is "+str(temp)+", turning fan on.")
                fanon()
            elif "on" in fanstatus:
                logger.debug("Temp is above High Temp setting. Fan is on already.")
            else:
                logger.debug(type(fanstatus))
                logger.debug("Fan status is "+fanstatus)
        elif temp <= templow:
            if "on" in fanstatus:
                logger.debug("Temperature is "+str(temp)+", turning fan off.")
                fanoff()
            elif  "off" in fanstatus:
                logger.debug("Temp is below Low Temp setting. Fan is off already.")
            else:
                logger.debug(type(fanstatus))
                logger.debug("Fan status is "+fanstatus)
        if coldprotecttriggered == 1:
            if temp >= templow:
                try:
                    heaterstatus = checkheater()
                    if "on" in heaterstatus:
                        logger.debug("Temperature has recovered to Low Temperature setting. Turning heater off.")
                        heateroff()
                        coldprotecttriggered = 0
                except Exception as e:
                    logger.debug("Could not turn off heater to exit cold protection: "+str(e))

def fixhum():
    global humidity, humhigh, nighthumhigh, humlow, nighthumlow, humidifierstatus, humidifieroffcycles, humidifieroncycles, when, heaterstatus, fanstatus
    if when == False:
#Night
        logger.debug("Night hum adjustment:")
        if humidity >= nighthumhigh:
            if "on" in humidifierstatus:
                logger.debug("Humidity is "+str(humidity)+", turning humidifier off.")
                humidifieroff()
            if "off" in fanstatus:
                if humidity >= 60:
                    logger.debug("Humidity is "+str(humidity)+", turning fan on.")
                    fanon()
            elif "on" in fanstatus:
                if humidity <= nighthumhigh:
                    logger.debug("Humidity is "+str(humidity)+", turning fan off.")
                    fanoff()
            
        if humidity <= nighthumlow:
            if "off" in humidifierstatus:
                logger.debug("Humidity is "+str(humidity)+", turning humidifier on.")
                humidifieron()
            if "on" in humidifierstatus:
                logger.debug("Humidifier is on already.")
            if "on" in fanstatus:
                logger.debug("Turning fan off.")
                fanoff()

    elif when == True:
#Day
        logger.debug("Day hum adjustment:")
        if humidity >= humhigh:
            if "on" in humidifierstatus:
                logger.debug("Humidity is "+str(humidity)+", turning humidifier off.")
                humidifieroff()
            elif "off" in humidifierstatus:
                logger.debug("Humidifier is off already")
        if humidity <= humlow:
            if "off" in humidifierstatus:
                logger.debug("Humidity is "+str(humidity)+", turning humidifier on.")
                humidifieron()
            elif "on" in humidifierstatus:
                logger.debug("Humidifier is on already.")
                
#only works if start and stop are same day
def checktime(starthour, startmin, stophour, stopmin):
    n = dt.datetime.now()
    str = dt.time(starthour, startmin)
    stp = dt.time(stophour, stopmin)
    if n.hour >= str.hour and n.hour < stp.hour:
            return True #Lights On
    return False #Lights Off

def pilightsoff():
    try:
        check_output("sudo sh -c 'echo 0 > /sys/class/leds/led0/brightness'",shell=True)
        check_output("sudo sh -c 'echo 0 > /sys/class/leds/led1/brightness'",shell=True)
    except Exception as e:
        logger.debug("Cannot disable Pi LEDs: "+str(e))

def getsoilinfo(i):
    try:
        ssm = getsoilmoisture(i)
        sst = getsoiltemp(i) 
        logger.debug("Soil "+str(i)+" Moisture: "+str(ssm)+" Temp: "+str(round(Decimal(sst),2)))
    except Exception as e:
        logger.debug("Could not read soil moisture/temp sensor "+str(i)+": "+str(e))

makepicdir(picfoldername)
pilightsoff()
####MAIN LOOP####
while True:
    try:
        logger.debug("\r")
        when = checktime(starthr,startmin,stophr,stopmin)
        if when == False:
            logger.debug("Lights Off Detected.")
        elif when == True:
            logger.debug("Lights On Detected.")
        getsoilinfo(0)
        getsoilinfo(1)
        getsoilinfo(2)
        getsoilinfo(3)
        ssm0 = getsoilmoisture(0)
        ssm1 = getsoilmoisture(1)
        ssm2 = getsoilmoisture(2)
        ssm3 = getsoilmoisture(3)
        if ssm0 > 2000:
            ssm0=0
        if ssm1 > 2000:
            ssm1=0
        if ssm2 > 2000:
            ssm2=0
        if ssm3 > 2000:
            ssm3=0
        readconfig()
        temp = gettemp()
        tempf = gettempf()
        tempu = tempunit()
        humidity = gethum()
        fanstatus = checkfan()
        humidifierstatus = checkhumidifier()
        heaterstatus = checkheater()
        logger.debug("Temperature: "+str(temp))
        logger.debug("Humidity: "+str(humidity))
        calcVPD()
        shipEnviroData(float(temp),float(humidity),float(vpd),float(ssm0),float(ssm1), float(ssm2), float(ssm3))
        fixtemp()
        fixvpd()
        fixhum()
       #takepic()
        loopcount += 1
        time.sleep(int(sleeptime))
    except Exception as e:
        logger.debug("Loop failed: "+str(e))

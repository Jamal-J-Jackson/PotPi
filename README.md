JustinCredible:
# PotPi
Software to control a grow cabinet
you will need:

Soldering pen & electronics solder

Adafruit SHT31D Temperature/Humidity sensor: https://learn.adafruit.com/adafruit-sht31-d-temperature-and-humidity-sensor-breakout/overview

Female/Female Dupont wire or some other way to connect the sensor to the Pi

Raspberry Pi 3 Model B+ (could probably make it work with different ones, this is what I used)

3x Wemo Smart Switch 

Honeywell Heater Bud (chosen for its price, small size and relatively low power consumption at 280w)

Honeywell Cool Mist Humidifier (was $75 Canadian at Walmart, I liked it for it's large capacity)

Exhaust fan


Axis M1034W IP camera - any Axis will work with this script but you'll need to change the IP. If you don't have an IP camera that can serve up single images without authentication, comment out the takepic() line at the bottom of the script. 


Set up your Wemo's as instructed in the box. Label them for which device they're controlling. I called mine "heater bud 1", "fan" and "humidifier". If you choose different names you'll need to edit the script to match.


Run these commands on your Pi to install Python packages for the sensor and for communicating with the database:

sudo pip3 install adafruit-circuitpython-sht31d

sudo pip3 install influxdb

You'll need to edit your influxdb server/username/password in the script

More instructions to come... you can piece it together until then

To use this system only to monitor your grow, comment out the following lines at the bottom of the script:

fanstatus = checkfan()
humidifierstatus = checkhumidifier()
heaterstatus = checkheater()
fixtemp()
fixvpd()
fixhum()

